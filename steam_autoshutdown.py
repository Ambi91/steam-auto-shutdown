#!/usr/bin/env python3
"""
steam_autoshutdown.py - shuts down the computer once Steam finishes all downloads.

How it works:
  For every game Steam keeps a file steamapps/appmanifest_<appid>.acf with
  the fields StateFlags, BytesToDownload and BytesDownloaded. The script reads
  them regularly in all Steam libraries (libraryfolders.vdf). Once nothing has
  downloaded for --quiet seconds in a row, it starts a countdown and then
  shuts down the computer.

Usage:
  python3 steam_autoshutdown.py                  # watch, then shut down
  python3 steam_autoshutdown.py --dry-run        # only print, never shut down
  python3 steam_autoshutdown.py --action sleep   # sleep instead of shutting down
  python3 steam_autoshutdown.py --status         # print the state once
  python3 steam_autoshutdown.py --lang cs        # in Czech (English is the default)

No dependencies, Python 3.8+ standard library only.
"""

import argparse
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

from i18n import LANGUAGES, load_saved_language, set_language, t

# --- StateFlags (Steam bit mask) --------------------------------------------
UPDATE_REQUIRED = 2
UPDATE_RUNNING = 256
UPDATE_PAUSED = 512
UPDATE_STARTED = 1024
VALIDATING = 131072
ADDING_FILES = 262144
PREALLOCATING = 524288
DOWNLOADING = 1048576
STAGING = 2097152
COMMITTING = 4194304

ACTIVE_MASK = (UPDATE_RUNNING | UPDATE_STARTED | VALIDATING | ADDING_FILES
               | PREALLOCATING | DOWNLOADING | STAGING | COMMITTING)

# Names of all known flags (EAppState). Order = display order: what is
# happening right now first, then pauses, and finally persistent states.
# The value is the translation key in i18n.py.
FLAG_NAMES = [
    (DOWNLOADING, "flag_downloading"),
    (PREALLOCATING, "flag_preallocating"),
    (ADDING_FILES, "flag_adding_files"),
    (STAGING, "flag_staging"),
    (COMMITTING, "flag_committing"),
    (VALIDATING, "flag_validating"),
    (UPDATE_RUNNING, "flag_update_running"),
    (UPDATE_STARTED, "flag_update_started"),
    (8388608, "flag_update_stopping"),
    (65536, "flag_reconfiguring"),
    (UPDATE_PAUSED, "flag_update_paused"),
    (UPDATE_REQUIRED, "flag_update_required"),
    (2048, "flag_uninstalling"),
    (4096, "flag_backing_up"),
    (64, "flag_app_running"),
    (16, "flag_locked"),
    (8, "flag_encrypted"),
    (32, "flag_files_missing"),
    (128, "flag_files_corrupt"),
    (4, "flag_installed"),
    (1, "flag_uninstalled"),
]


def describe_flags(flags):
    """Split StateFlags into a list of state names (unknown bits as 'bit N')."""
    names, known = [], 0
    for value, key in FLAG_NAMES:
        known |= value
        if flags & value:
            names.append(t(key))
    rest = flags & ~known
    names += [f"bit {i}" for i in range(rest.bit_length()) if rest >> i & 1]
    return names or [t("flag_invalid")]


# --- Minimal VDF/ACF parser ------------------------------------------------
_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])')


def parse_vdf(text):
    """Convert VDF text into a nested dict (keys in lowercase)."""
    root, stack, key = {}, [], None
    cur = root
    for m in _TOKEN.finditer(text):
        s, brace = m.group(1), m.group(2)
        if brace == "{":
            new = {}
            cur[(key or "").lower()] = new
            stack.append(cur)
            cur, key = new, None
        elif brace == "}":
            cur = stack.pop() if stack else root
            key = None
        elif key is None:
            key = s
        else:
            cur[key.lower()] = s.replace('\\\\', '\\')
            key = None
    return root


# --- Finding Steam and its libraries ---------------------------------------
def default_steam_roots():
    home = Path.home()
    system = platform.system()
    if system == "Darwin":
        return [home / "Library/Application Support/Steam"]
    if system == "Windows":
        roots = []
        try:
            import winreg
            for hive, sub in [(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                              (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")]:
                try:
                    with winreg.OpenKey(hive, sub) as k:
                        for name in ("SteamPath", "InstallPath"):
                            try:
                                roots.append(Path(winreg.QueryValueEx(k, name)[0]))
                            except OSError:
                                pass
                except OSError:
                    pass
        except ImportError:
            pass
        roots.append(Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam")
        return roots
    # Linux (incl. Flatpak)
    return [home / ".steam/steam", home / ".local/share/Steam",
            home / ".var/app/com.valvesoftware.Steam/.local/share/Steam"]


def find_libraries(steam_root=None):
    roots = [Path(steam_root)] if steam_root else default_steam_roots()
    libs = []
    for root in roots:
        steamapps = root / "steamapps"
        if not steamapps.is_dir():
            continue
        libs.append(steamapps)
        vdf = steamapps / "libraryfolders.vdf"
        if vdf.is_file():
            data = parse_vdf(vdf.read_text(encoding="utf-8", errors="replace"))
            folders = data.get("libraryfolders", {})
            for entry in folders.values():
                p = entry.get("path") if isinstance(entry, dict) else entry
                if p and (Path(p) / "steamapps").is_dir():
                    libs.append(Path(p) / "steamapps")
        break  # the first installation found is enough
    # remove duplicates
    seen, out = set(), []
    for lib in libs:
        r = lib.resolve()
        if r not in seen:
            seen.add(r)
            out.append(lib)
    return out


# --- Download state --------------------------------------------------------
def scan(libraries):
    """Return the games being downloaded: [(name, downloaded, total, StateFlags)]."""
    return [item[1:] for item in scan_states(libraries)[0]]


def scan_states(libraries):
    """One pass over all manifests. Returns (active, paused), both as lists of
    (appid, name, downloaded, total, StateFlags).

    active – downloading now or waiting in Steam's download queue
             (updates scheduled for later are left out)
    paused – download paused in Steam (not active)
    """
    active, paused_items = [], []
    now = time.time()
    for lib in libraries:
        for acf in lib.glob("appmanifest_*.acf"):
            try:
                app = parse_vdf(acf.read_text(encoding="utf-8", errors="replace")).get("appstate", {})
            except OSError:
                continue  # Steam is rewriting the file right now
            flags = int(app.get("stateflags", "0") or 0)
            to_dl = int(app.get("bytestodownload", "0") or 0)
            done = int(app.get("bytesdownloaded", "0") or 0)
            paused = bool(flags & UPDATE_PAUSED)
            running = bool(flags & ACTIVE_MASK)
            # "Update required" without a pause means the app is waiting in Steam's
            # download queue (possibly with 0 bytes known so far), so wait for it too.
            # Byte counts alone are ignored: Steam sometimes leaves stale ones behind
            # on a fully installed app (StateFlags = Installed only).
            # An update Steam has scheduled for later (Downloads → "Scheduled") has a
            # future ScheduledAutoUpdate timestamp. It isn't queued yet, so skip it;
            # once its time comes, Steam starts it and the active flags pick it up.
            scheduled = int(app.get("scheduledautoupdate", "0") or 0) > now
            queued = bool(flags & UPDATE_REQUIRED) and not scheduled
            # A paused app keeps "Update started" set, so pause wins over the
            # active flags – unless Steam reports it is actually downloading.
            downloading = bool(flags & DOWNLOADING)
            appid = app.get("appid") or acf.stem
            item = (appid, app.get("name", acf.stem), done, to_dl, flags)
            if downloading or (not paused and (running or queued)):
                active.append(item)
            elif paused:
                paused_items.append(item)
    return active, paused_items


def fmt_bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024


# --- Shutdown --------------------------------------------------------------
def power_command(action):
    system = platform.system()
    if system == "Darwin":
        verb = {"shutdown": "shut down", "sleep": "sleep", "restart": "restart"}[action]
        return ["osascript", "-e", f'tell application "System Events" to {verb}']
    if system == "Windows":
        return {"shutdown": ["shutdown", "/s", "/t", "0"],
                "restart": ["shutdown", "/r", "/t", "0"],
                "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]}[action]
    return {"shutdown": ["systemctl", "poweroff"],
            "restart": ["systemctl", "reboot"],
            "sleep": ["systemctl", "suspend"]}[action]


def countdown(seconds, action):
    print(t("cli_countdown", action=action, seconds=seconds))
    try:
        for left in range(seconds, 0, -1):
            print(f"\r  {left:3d} s ", end="", flush=True)
            time.sleep(1)
        print()
        return True
    except KeyboardInterrupt:
        print(t("cli_cancelled"))
        return False


# --- Main loop -------------------------------------------------------------
def _utf8_output():
    """On Windows, redirected output uses cp1252, where characters like "↓" or "™"
    crash print(). Switch stdout/stderr to UTF-8 and replace what can't be written."""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def main():
    _utf8_output()
    # The language must be known before the help text is built, hence two passes.
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--lang", choices=list(LANGUAGES))
    lang = pre.parse_known_args()[0].lang
    set_language(lang or load_saved_language())

    ap = argparse.ArgumentParser(description=t("cli_description"))
    ap.add_argument("--steam-path", help=t("arg_steam_path"))
    ap.add_argument("--interval", type=int, default=15, help=t("arg_interval"))
    ap.add_argument("--quiet", type=int, default=60, help=t("arg_quiet"))
    ap.add_argument("--countdown", type=int, default=10, help=t("arg_countdown"))
    ap.add_argument("--action", choices=["shutdown", "sleep", "restart"], default="shutdown",
                    help=t("arg_action"))
    ap.add_argument("--no-wait-start", action="store_true", help=t("arg_no_wait_start"))
    ap.add_argument("--dry-run", action="store_true", help=t("arg_dry_run"))
    ap.add_argument("--status", action="store_true", help=t("arg_status"))
    ap.add_argument("--lang", choices=list(LANGUAGES), help=t("arg_lang"))
    args = ap.parse_args()

    libs = find_libraries(args.steam_path)
    if not libs:
        sys.exit(t("cli_steam_not_found"))
    print(t("cli_libraries") + "\n  " + "\n  ".join(str(l) for l in libs))

    if args.status:
        active = scan(libs)
        if not active:
            print(t("nothing_downloading"))
        for name, done, total, flags in active:
            print(f"  ↓ {name}: {fmt_bytes(done)} / {fmt_bytes(total)}  "
                  f"[{flags}: {', '.join(describe_flags(flags))}]")
        return

    seen_download = args.no_wait_start
    idle_since = None
    watched = set()  # appids seen active during this watch; pausing one of them holds the action
    print(t("cli_watching", interval=args.interval))
    try:
        while True:
            active, paused = scan_states(libs)
            watched.update(item[0] for item in active)
            held = [item for item in paused if item[0] in watched]
            now = time.time()
            stamp = time.strftime("%H:%M:%S")
            if active:
                seen_download, idle_since = True, None
                desc = ", ".join(f"{n} ({fmt_bytes(d)}/{fmt_bytes(t)})" if t else n
                                 for _, n, d, t, _ in active)
                print(t("cli_downloading", stamp=stamp, desc=desc))
            elif held:
                idle_since = None
                print(t("cli_paused", stamp=stamp, names=", ".join(item[1] for item in held)))
            elif not seen_download:
                print(t("cli_waiting_start", stamp=stamp))
            else:
                idle_since = idle_since or now
                idle = int(now - idle_since)
                print(t("cli_idle", stamp=stamp, idle=idle, quiet=args.quiet))
                if idle >= args.quiet:
                    if countdown(args.countdown, args.action):
                        cmd = power_command(args.action)
                        if args.dry_run:
                            print(t("cli_dry_run"), " ".join(cmd))
                        else:
                            subprocess.run(cmd, check=False)
                    return
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print(t("cli_stopped"))


if __name__ == "__main__":
    main()

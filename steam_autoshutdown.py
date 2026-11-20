#!/usr/bin/env python3
"""
steam_autoshutdown.py - vypne počítač, jakmile Steam dokončí všechna stahování.

Jak to funguje:
  Steam má pro každou hru soubor steamapps/appmanifest_<appid>.acf, kde jsou
  položky StateFlags, BytesToDownload a BytesDownloaded. Skript je pravidelně
  čte ve všech knihovnách Steamu (libraryfolders.vdf). Když se nic nestahuje
  po dobu --quiet sekund za sebou, spustí odpočet a potom vypne počítač.

Použití:
  python3 steam_autoshutdown.py                  # hlídá a pak vypne PC
  python3 steam_autoshutdown.py --dry-run        # jen vypíše, nic nevypne
  python3 steam_autoshutdown.py --action sleep   # uspí místo vypnutí
  python3 steam_autoshutdown.py --status         # jednorázový výpis stavu

Bez závislostí, jen standardní knihovna Pythonu 3.8+.
"""

import argparse
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

# --- StateFlags (bitová maska Steamu) ---------------------------------------
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

# Slovní popis všech známých příznaků (EAppState). Pořadí = pořadí ve výpisu:
# nejdřív to, co se právě děje, pak pozastavení a nakonec trvalé stavy.
FLAG_NAMES = [
    (DOWNLOADING, "Stahuje"),
    (PREALLOCATING, "Alokuje místo"),
    (ADDING_FILES, "Přidává soubory"),
    (STAGING, "Zpracovává data"),
    (COMMITTING, "Zapisuje"),
    (VALIDATING, "Ověřuje"),
    (UPDATE_RUNNING, "Aktualizace běží"),
    (UPDATE_STARTED, "Aktualizace zahájena"),
    (8388608, "Zastavuje aktualizaci"),
    (65536, "Mění konfiguraci"),
    (UPDATE_PAUSED, "Pozastaveno"),
    (UPDATE_REQUIRED, "Čeká aktualizace"),
    (2048, "Odinstalovává"),
    (4096, "Zálohuje"),
    (64, "Hra běží"),
    (16, "Uzamčeno"),
    (8, "Zašifrováno"),
    (32, "Chybí soubory"),
    (128, "Poškozené soubory"),
    (4, "Nainstalováno"),
    (1, "Neinstalováno"),
]


def describe_flags(flags):
    """Rozloží StateFlags na seznam slovních stavů (neznámé bity jako 'bit N')."""
    names, known = [], 0
    for value, label in FLAG_NAMES:
        known |= value
        if flags & value:
            names.append(label)
    rest = flags & ~known
    names += [f"bit {i}" for i in range(rest.bit_length()) if rest >> i & 1]
    return names or ["Neplatný stav"]


# --- Minimalistický parser formátu VDF/ACF ----------------------------------
_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])')


def parse_vdf(text):
    """Převede text VDF na vnořený dict (klíče v lowercase)."""
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


# --- Hledání Steamu a knihoven ----------------------------------------------
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
    # Linux (vč. Flatpaku)
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
        break  # první nalezená instalace stačí
    # odstranit duplicity
    seen, out = set(), []
    for lib in libs:
        r = lib.resolve()
        if r not in seen:
            seen.add(r)
            out.append(lib)
    return out


# --- Stav stahování ---------------------------------------------------------
def scan(libraries):
    """Vrátí seznam aktivně stahovaných her: [(název, staženo, celkem, StateFlags)]."""
    active = []
    for lib in libraries:
        for acf in lib.glob("appmanifest_*.acf"):
            try:
                app = parse_vdf(acf.read_text(encoding="utf-8", errors="replace")).get("appstate", {})
            except OSError:
                continue  # Steam soubor právě přepisuje
            flags = int(app.get("stateflags", "0") or 0)
            to_dl = int(app.get("bytestodownload", "0") or 0)
            done = int(app.get("bytesdownloaded", "0") or 0)
            paused = bool(flags & UPDATE_PAUSED)
            running = bool(flags & ACTIVE_MASK)
            unfinished = to_dl > 0 and done < to_dl and not paused
            if running or unfinished:
                active.append((app.get("name", acf.stem), done, to_dl, flags))
    return active


def fmt_bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024


# --- Vypnutí ----------------------------------------------------------------
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
    print(f"\nVšechna stahování dokončena. Akce '{action}' za {seconds} s. "
          "Zrušíš ji klávesami Ctrl+C.")
    try:
        for left in range(seconds, 0, -1):
            print(f"\r  {left:3d} s ", end="", flush=True)
            time.sleep(1)
        print()
        return True
    except KeyboardInterrupt:
        print("\nZrušeno uživatelem.")
        return False


# --- Hlavní smyčka ----------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Vypne PC po dokončení stahování ve Steamu.")
    ap.add_argument("--steam-path", help="cesta ke složce Steamu (jinak se najde sama)")
    ap.add_argument("--interval", type=int, default=15, help="jak často kontrolovat, v sekundách (15)")
    ap.add_argument("--quiet", type=int, default=120,
                    help="kolik sekund se nesmí nic stahovat, než se to považuje za hotové (120)")
    ap.add_argument("--countdown", type=int, default=60, help="odpočet před vypnutím, v sekundách (60)")
    ap.add_argument("--action", choices=["shutdown", "sleep", "restart"], default="shutdown")
    ap.add_argument("--no-wait-start", action="store_true",
                    help="nečekat, až nějaké stahování začne (jinak se vypne až po prvním zachyceném)")
    ap.add_argument("--dry-run", action="store_true", help="nic nevypínat, jen vypsat")
    ap.add_argument("--status", action="store_true", help="jednou vypsat stav a skončit")
    args = ap.parse_args()

    libs = find_libraries(args.steam_path)
    if not libs:
        sys.exit("Steam se nepodařilo najít. Zadej cestu přes --steam-path.")
    print("Knihovny Steamu:\n  " + "\n  ".join(str(l) for l in libs))

    if args.status:
        active = scan(libs)
        if not active:
            print("Nic se nestahuje.")
        for name, done, total, flags in active:
            print(f"  ↓ {name}: {fmt_bytes(done)} / {fmt_bytes(total)}  "
                  f"[{flags}: {', '.join(describe_flags(flags))}]")
        return

    seen_download = args.no_wait_start
    idle_since = None
    print(f"Hlídám stahování (kontrola každých {args.interval} s). Ukončíš to Ctrl+C.\n")
    try:
        while True:
            active = scan(libs)
            now = time.time()
            stamp = time.strftime("%H:%M:%S")
            if active:
                seen_download, idle_since = True, None
                desc = ", ".join(f"{n} ({fmt_bytes(d)}/{fmt_bytes(t)})" if t else n
                                 for n, d, t, _ in active)
                print(f"[{stamp}] Stahuje se: {desc}")
            elif not seen_download:
                print(f"[{stamp}] Čekám, až začne nějaké stahování…")
            else:
                idle_since = idle_since or now
                idle = int(now - idle_since)
                print(f"[{stamp}] Nic se nestahuje už {idle} s (potřeba {args.quiet} s)")
                if idle >= args.quiet:
                    if countdown(args.countdown, args.action):
                        cmd = power_command(args.action)
                        if args.dry_run:
                            print("[dry-run] Spustil bych:", " ".join(cmd))
                        else:
                            subprocess.run(cmd, check=False)
                    return
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nUkončeno.")


if __name__ == "__main__":
    main()

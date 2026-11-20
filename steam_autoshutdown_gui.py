#!/usr/bin/env python3
"""
Steam Auto-Shutdown – graphical version.

Shows what Steam is downloading right now and, once watching is on, shuts down /
sleeps / restarts the computer when all downloads are finished.
The logic (finding libraries, reading manifests, power commands) is shared
with the terminal version in steam_autoshutdown.py.
"""

import os
import subprocess
import sys
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, font as tkfont, messagebox, ttk

from i18n import LANGUAGES, get_language, load_saved_language, save_language, set_language, t
from steam_autoshutdown import FLAG_NAMES, describe_flags, find_libraries, fmt_bytes, power_command, scan

APP_NAME = "Steam Auto-Shutdown"
SCAN_INTERVAL_MS = 5000
DONATE_URL = "https://ko-fi.com/ambi91"
KOFI_COLOR = "#29ABE0"   # Ko-fi blue
KOFI_HOVER = "#1E8BBA"

ACTIONS = ("shutdown", "sleep", "restart")  # texts: action_<key>, countdown_<key> in i18n.py


class CountdownDialog(tk.Toplevel):
    """Cancellable countdown window. Stays on top of other windows."""

    def __init__(self, parent, seconds, action, on_done, on_cancel):
        super().__init__(parent)
        self.title(APP_NAME)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.left, self.action = seconds, action
        self.on_done, self.on_cancel = on_done, on_cancel

        frm = ttk.Frame(self, padding=24)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=t("dlg_finished"),
                  font=("TkDefaultFont", 13, "bold")).pack()
        self.msg = ttk.Label(frm, font=("TkDefaultFont", 12))
        self.msg.pack(pady=(8, 4))
        self.num = ttk.Label(frm, font=("TkDefaultFont", 40, "bold"))
        self.num.pack(pady=(0, 12))
        btns = ttk.Frame(frm)
        btns.pack()
        ttk.Button(btns, text=t("dlg_cancel"), command=self.cancel).pack(side="left", padx=6)
        ttk.Button(btns, text=t("dlg_now"), command=self.finish).pack(side="left", padx=6)

        self.bind("<Escape>", lambda e: self.cancel())
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.lift()
        self.focus_force()
        self._job = None
        self.tick()

    def tick(self):
        if self.left <= 0:
            self.finish()
            return
        self.msg.config(text=t(f"countdown_{self.action}"))
        self.num.config(text=f"{self.left} s")
        self.left -= 1
        self._job = self.after(1000, self.tick)

    def _close(self):
        if self._job:
            self.after_cancel(self._job)
        self.destroy()

    def cancel(self):
        self._close()
        self.on_cancel()

    def finish(self):
        self._close()
        self.on_done()


class FlagsTooltip(tk.Toplevel):
    """Borderless popup listing every StateFlags bit and its meaning."""

    def __init__(self, parent, x, y):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        frm = tk.Frame(self, bg="#ffffe1", bd=1, relief="solid", padx=8, pady=6)
        frm.pack()
        tk.Label(frm, text=t("flags_help_title"), bg="#ffffe1", fg="black",
                 font=("TkDefaultFont", 9, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        for i, (value, key) in enumerate(sorted(FLAG_NAMES), start=1):
            tk.Label(frm, text=str(value), bg="#ffffe1", fg="black",
                     font="TkFixedFont").grid(row=i, column=0, sticky="e", padx=(0, 10))
            tk.Label(frm, text=t(key), bg="#ffffe1", fg="black").grid(row=i, column=1, sticky="w")
        tk.Label(frm, text=t("flags_help_note"), bg="#ffffe1", fg="gray25", justify="left").grid(
            row=len(FLAG_NAMES) + 1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.geometry(f"+{x}+{y}")


class App(ttk.Frame):
    def __init__(self, root):
        super().__init__(root, padding=14)
        self.root = root
        self.pack(fill="both", expand=True)

        # None = find automatically; the environment variable is for tests and unusual installs
        self.steam_path = os.environ.get("STEAM_AUTOSHUTDOWN_PATH") or None
        self.libs = []
        self.armed = False
        self.seen_download = False
        self.idle_since = None
        self.countdown = None
        # The status line is kept as (key, params) so it can be re-translated on language change.
        self._status = ("status_off", {})

        self.action_key = ACTIONS[0]
        self.action_label = tk.StringVar()
        self.language = tk.StringVar()
        self.quiet_s = tk.IntVar(value=60)
        self.countdown_s = tk.IntVar(value=10)
        self.dry_run = tk.BooleanVar(value=False)

        self._build()
        self.load_libraries()
        self.refresh()

    # ---------- layout ----------
    def _build(self):
        self.action_label.set(t(f"action_{self.action_key}"))
        self.language.set(LANGUAGES[get_language()])

        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text=APP_NAME, font=("TkDefaultFont", 16, "bold")).pack(side="left")
        lang_box = ttk.Combobox(top, textvariable=self.language, values=list(LANGUAGES.values()),
                                state="readonly", width=10)
        lang_box.pack(side="right")
        lang_box.bind("<<ComboboxSelected>>", self.change_language)
        ttk.Label(top, text=t("language")).pack(side="right", padx=(0, 4))

        box = ttk.LabelFrame(self, text=t("box_downloading"), padding=8)
        box.pack(fill="both", expand=True)
        cols = ("game", "progress", "pct", "state")
        self.tree = ttk.Treeview(box, columns=cols, show="headings", height=6)
        self.tree.heading("game", text=t("col_game"))
        self.tree.heading("progress", text=t("col_progress"))
        self.tree.heading("pct", text="%")
        # The "(?)" in the heading shows a list of all possible states on hover.
        self.tree.heading("state", text=f"{t('col_state')}  (?)")
        self._flags_tip = None
        self.tree.bind("<Motion>", self._on_tree_motion)
        self.tree.bind("<Leave>", lambda e: self._hide_flags_tip())
        self.tree.column("game", width=200, minwidth=120)
        self.tree.column("progress", width=150, minwidth=110, anchor="center", stretch=False)
        self.tree.column("pct", width=50, minwidth=40, anchor="center", stretch=False)
        self.tree.column("state", width=340, minwidth=160)
        self.tree.pack(fill="both", expand=True)
        self.empty_label = ttk.Label(box, text=t("nothing_downloading"), foreground="gray")

        # Two columns under the download list: settings on the left, Steam libraries on the right.
        row = ttk.Frame(self)
        row.pack(fill="x", pady=10)
        row.columnconfigure(0, weight=1, uniform="cols")
        row.columnconfigure(1, weight=1, uniform="cols")

        libs = ttk.LabelFrame(row, text=t("box_libraries"), padding=8)
        libs.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        ttk.Button(libs, text=t("btn_steam_folder"), command=self.choose_path).pack(side="bottom", anchor="w",
                                                                                    pady=(6, 0))
        # width=1: a long Steam path gets clipped instead of widening the window
        self.lib_label = ttk.Label(libs, foreground="gray", width=1, justify="left", anchor="nw")
        self.lib_label.pack(fill="both", expand=True)

        opts = ttk.LabelFrame(row, text=t("box_settings"), padding=8)
        opts.grid(row=0, column=0, sticky="nsew")
        opts.columnconfigure(1, weight=1)
        ttk.Label(opts, text=t("opt_action")).grid(row=0, column=0, sticky="w", pady=3)
        action_box = ttk.Combobox(opts, textvariable=self.action_label,
                                  values=[t(f"action_{k}") for k in ACTIONS],
                                  state="readonly", width=26)
        action_box.grid(row=0, column=1, sticky="w")
        action_box.bind("<<ComboboxSelected>>",
                        lambda e: setattr(self, "action_key", ACTIONS[action_box.current()]))
        ttk.Label(opts, text=t("opt_quiet")).grid(row=1, column=0, sticky="w", pady=3)
        ttk.Spinbox(opts, from_=10, to=3600, increment=10, textvariable=self.quiet_s, width=6).grid(row=1, column=1, sticky="w")
        ttk.Label(opts, text=t("opt_countdown")).grid(row=2, column=0, sticky="w", pady=3)
        ttk.Spinbox(opts, from_=10, to=600, increment=10, textvariable=self.countdown_s,
                    width=6).grid(row=2, column=1, sticky="w")
        ttk.Checkbutton(opts, text=t("opt_dry_run"),
                        variable=self.dry_run).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

        self.status = ttk.Label(self, font=("TkDefaultFont", 12))
        self.status.pack(fill="x", pady=(0, 8))
        self.btn = ttk.Button(self, command=self.toggle)
        self.btn.pack(fill="x", ipady=6)
        self._render_status()
        self._render_button()

        # Support development: a separate footer with a short text and a coloured
        # Ko-fi button. Visible, but nothing pops up or gets in the way – just a static element.
        ttk.Separator(self).pack(fill="x", pady=(14, 8))
        footer = ttk.Frame(self)
        footer.pack(fill="x")
        ttk.Label(footer, text=t("footer_question"), foreground="gray").pack(side="left")
        base = tkfont.nametofont("TkDefaultFont")
        bold = tkfont.Font(family=base.cget("family"), size=base.cget("size"), weight="bold")
        self._fonts = (bold,)  # keep a reference, otherwise Tk frees it
        self.donate = tk.Label(footer, text=t("btn_donate"), font=bold,
                               bg=KOFI_COLOR, fg="white", padx=12, pady=5,
                               cursor="hand2", borderwidth=0, highlightthickness=0)
        self.donate.pack(side="right")
        self.donate.bind("<Button-1>", lambda e: webbrowser.open(DONATE_URL))
        self.donate.bind("<Enter>", lambda e: self.donate.config(bg=KOFI_HOVER))
        self.donate.bind("<Leave>", lambda e: self.donate.config(bg=KOFI_COLOR))

    # ---------- StateFlags help ----------
    def _on_tree_motion(self, event):
        over_state_heading = (self.tree.identify_region(event.x, event.y) == "heading"
                              and self.tree.identify_column(event.x) == "#4")
        if over_state_heading and self._flags_tip is None:
            self._flags_tip = FlagsTooltip(self.root, event.x_root + 12, event.y_root + 16)
        elif not over_state_heading:
            self._hide_flags_tip()

    def _hide_flags_tip(self):
        if self._flags_tip is not None:
            self._flags_tip.destroy()
            self._flags_tip = None

    # ---------- language ----------
    def change_language(self, _event=None):
        lang = next(code for code, name in LANGUAGES.items() if name == self.language.get())
        if lang == get_language():
            return
        set_language(lang)
        save_language(lang)
        # Rebuild the whole window in the new language; settings and watching state are kept.
        for child in self.winfo_children():
            child.destroy()
        self._build()
        self._render_libraries()
        self.refresh(reschedule=False)

    # ---------- state-dependent texts ----------
    def set_status(self, key, **kwargs):
        self._status = (key, kwargs)
        self._render_status()

    def _render_status(self):
        key, kwargs = self._status
        self.status.config(text=t(key, **kwargs))

    def _render_button(self):
        self.btn.config(text=t("btn_stop") if self.armed else t("btn_start"))

    def _render_libraries(self):
        if self.libs:
            # One line with the count, then each library root on its own line.
            lines = [t("libs_found", n=len(self.libs))]
            lines += [f"  •  {lib.parent}" for lib in self.libs]
            self.lib_label.config(text="\n".join(lines), foreground="gray")
        else:
            self.lib_label.config(text=t("steam_not_found"), foreground="#c0392b")

    # ---------- Steam ----------
    def load_libraries(self):
        self.libs = find_libraries(self.steam_path)
        self._render_libraries()

    def choose_path(self):
        path = filedialog.askdirectory(title=t("choose_folder_title"))
        if path:
            self.steam_path = path
            self.load_libraries()
            self.refresh(reschedule=False)

    # ---------- watching ----------
    def toggle(self):
        if self.armed:
            self.disarm("status_off")
            return
        if not self.libs:
            messagebox.showwarning(APP_NAME, t("choose_folder_first"))
            return
        self.armed, self.idle_since = True, None
        self.seen_download = bool(self.tree.get_children())
        self._render_button()
        self.refresh(reschedule=False)

    def disarm(self, key, **kwargs):
        self.armed = False
        self._render_button()
        self.set_status(key, **kwargs)

    def refresh(self, reschedule=True):
        active = scan(self.libs) if self.libs else []
        self.tree.delete(*self.tree.get_children())
        for name, done, total, flags in active:
            pct = f"{done * 100 // total} %" if total else "–"
            prog = f"{fmt_bytes(done)} / {fmt_bytes(total)}" if total else t("preparing")
            state = f"{' · '.join(describe_flags(flags))}  ({flags})"
            self.tree.insert("", "end", values=(name, prog, pct, state))
        if active:
            self.empty_label.place_forget()
        else:
            self.empty_label.place(relx=0.5, rely=0.55, anchor="center")

        if self.armed and self.countdown is None:
            self.evaluate(bool(active))
        if reschedule:
            self.root.after(SCAN_INTERVAL_MS, self.refresh)

    def evaluate(self, downloading):
        if downloading:
            self.seen_download, self.idle_since = True, None
            self.set_status("status_downloading")
            return
        if not self.seen_download:
            self.set_status("status_waiting")
            return
        now = time.time()
        self.idle_since = self.idle_since or now
        need = max(10, self.quiet_s.get())
        left = int(need - (now - self.idle_since))
        if left > 0:
            self.set_status("status_verifying", left=left)
            return
        self.set_status("status_countdown")
        self.countdown = CountdownDialog(self.root, max(5, self.countdown_s.get()), self.action_key,
                                         self.execute, self.cancelled)

    def cancelled(self):
        self.countdown = None
        self.disarm("status_cancelled")

    def execute(self):
        self.countdown = None
        cmd = power_command(self.action_key)
        if self.dry_run.get():
            self.disarm("status_dry_run", action=t(f"action_{self.action_key}"))
            messagebox.showinfo(APP_NAME, t("msg_dry_run", cmd=" ".join(cmd)))
            return
        self.disarm("status_executing")
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.strip() or t("return_code", code=r.returncode))
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(APP_NAME, t("msg_action_failed", error=e))
            self.set_status("status_action_failed")


def main():
    set_language(load_saved_language())
    root = tk.Tk()
    root.title(APP_NAME)
    root.minsize(780, 540)
    try:
        ttk.Style().theme_use("vista" if sys.platform == "win32" else
                              "aqua" if sys.platform == "darwin" else "clam")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Steam Auto-Shutdown – grafická verze.

Ukazuje, co Steam právě stahuje, a po zapnutí hlídání vypne / uspí /
restartuje počítač, jakmile jsou všechna stahování hotová.
Logiku (hledání knihoven, čtení manifestů, příkazy pro vypnutí) sdílí
s konzolovou verzí v steam_autoshutdown.py.
"""

import os
import subprocess
import sys
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, font as tkfont, messagebox, ttk

from steam_autoshutdown import find_libraries, fmt_bytes, power_command, scan

APP_NAME = "Steam Auto-Shutdown"
SCAN_INTERVAL_MS = 5000
DONATE_URL = "https://ko-fi.com/ambi91"
KOFI_COLOR = "#29ABE0"   # modrá Ko-fi
KOFI_HOVER = "#1E8BBA"

ACTIONS = {  # text v nabídce -> (klíč akce, sloveso pro odpočet)
    "Vypnout počítač": ("shutdown", "vypne"),
    "Uspat počítač": ("sleep", "uspí"),
    "Restartovat počítač": ("restart", "restartuje"),
}


class CountdownDialog(tk.Toplevel):
    """Okno s odpočtem, které jde zrušit. Zůstává nad ostatními okny."""

    def __init__(self, parent, seconds, verb, on_done, on_cancel):
        super().__init__(parent)
        self.title(APP_NAME)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.left, self.verb = seconds, verb
        self.on_done, self.on_cancel = on_done, on_cancel

        frm = ttk.Frame(self, padding=24)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Stahování ve Steamu je dokončeno.",
                  font=("TkDefaultFont", 13, "bold")).pack()
        self.msg = ttk.Label(frm, font=("TkDefaultFont", 12))
        self.msg.pack(pady=(8, 4))
        self.num = ttk.Label(frm, font=("TkDefaultFont", 40, "bold"))
        self.num.pack(pady=(0, 12))
        btns = ttk.Frame(frm)
        btns.pack()
        ttk.Button(btns, text="Zrušit", command=self.cancel).pack(side="left", padx=6)
        ttk.Button(btns, text="Provést hned", command=self.finish).pack(side="left", padx=6)

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
        self.msg.config(text=f"Počítač se {self.verb} za:")
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


class App(ttk.Frame):
    def __init__(self, root):
        super().__init__(root, padding=14)
        self.root = root
        self.pack(fill="both", expand=True)

        # None = najít automaticky; proměnná prostředí slouží pro testy a nestandardní instalace
        self.steam_path = os.environ.get("STEAM_AUTOSHUTDOWN_PATH") or None
        self.libs = []
        self.armed = False
        self.seen_download = False
        self.idle_since = None
        self.countdown = None

        self.action = tk.StringVar(value=next(iter(ACTIONS)))
        self.quiet_min = tk.IntVar(value=2)
        self.countdown_s = tk.IntVar(value=60)
        self.dry_run = tk.BooleanVar(value=False)

        self._build()
        self.load_libraries()
        self.refresh()

    # ---------- rozložení ----------
    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text=APP_NAME, font=("TkDefaultFont", 16, "bold")).pack(side="left")
        ttk.Button(top, text="Složka Steamu…", command=self.choose_path).pack(side="right")
        self.lib_label = ttk.Label(self, foreground="gray")
        self.lib_label.pack(fill="x", pady=(2, 10))

        box = ttk.LabelFrame(self, text="Právě se stahuje", padding=8)
        box.pack(fill="both", expand=True)
        cols = ("game", "progress", "pct")
        self.tree = ttk.Treeview(box, columns=cols, show="headings", height=6)
        self.tree.heading("game", text="Hra")
        self.tree.heading("progress", text="Staženo")
        self.tree.heading("pct", text="%")
        self.tree.column("game", width=260)
        self.tree.column("progress", width=170, anchor="center")
        self.tree.column("pct", width=60, anchor="center")
        self.tree.pack(fill="both", expand=True)
        self.empty_label = ttk.Label(box, text="Nic se nestahuje.", foreground="gray")

        opts = ttk.LabelFrame(self, text="Nastavení", padding=8)
        opts.pack(fill="x", pady=10)
        opts.columnconfigure(1, weight=1)
        ttk.Label(opts, text="Po dokončení:").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Combobox(opts, textvariable=self.action, values=list(ACTIONS),
                     state="readonly", width=22).grid(row=0, column=1, sticky="w")
        ttk.Label(opts, text="Počkat bez stahování (min):").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Spinbox(opts, from_=1, to=60, textvariable=self.quiet_min, width=6).grid(row=1, column=1, sticky="w")
        ttk.Label(opts, text="Odpočet před akcí (s):").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Spinbox(opts, from_=10, to=600, increment=10, textvariable=self.countdown_s,
                    width=6).grid(row=2, column=1, sticky="w")
        ttk.Checkbutton(opts, text="Zkušební režim (počítač nevypínat, jen ukázat odpočet)",
                        variable=self.dry_run).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

        self.status = ttk.Label(self, text="Hlídání je vypnuté.", font=("TkDefaultFont", 12))
        self.status.pack(fill="x", pady=(0, 8))
        self.btn = ttk.Button(self, text="▶  Spustit hlídání", command=self.toggle)
        self.btn.pack(fill="x", ipady=6)

        # Podpora vývoje: oddělená patička s krátkým textem a barevným tlačítkem
        # Ko-fi. Je vidět, ale nic nevyskakuje a nepřekáží – jen statický prvek.
        ttk.Separator(self).pack(fill="x", pady=(14, 8))
        footer = ttk.Frame(self)
        footer.pack(fill="x")
        ttk.Label(footer, text="Ušetřila ti aplikace čas?", foreground="gray").pack(side="left")
        base = tkfont.nametofont("TkDefaultFont")
        bold = tkfont.Font(family=base.cget("family"), size=base.cget("size"), weight="bold")
        self._fonts = (bold,)  # držet referenci, jinak ji Tk uvolní
        self.donate = tk.Label(footer, text="☕  Podpořit na Ko-fi", font=bold,
                               bg=KOFI_COLOR, fg="white", padx=12, pady=5,
                               cursor="hand2", borderwidth=0, highlightthickness=0)
        self.donate.pack(side="right")
        self.donate.bind("<Button-1>", lambda e: webbrowser.open(DONATE_URL))
        self.donate.bind("<Enter>", lambda e: self.donate.config(bg=KOFI_HOVER))
        self.donate.bind("<Leave>", lambda e: self.donate.config(bg=KOFI_COLOR))

    # ---------- Steam ----------
    def load_libraries(self):
        self.libs = find_libraries(self.steam_path)
        if self.libs:
            n = len(self.libs)
            self.lib_label.config(text=f"Nalezeno knihoven: {n}  ·  {self.libs[0].parent}")
        else:
            self.lib_label.config(text="Steam nebyl nalezen. Vyber jeho složku tlačítkem vpravo.",
                                  foreground="#c0392b")

    def choose_path(self):
        path = filedialog.askdirectory(title="Vyber složku, kde je nainstalovaný Steam")
        if path:
            self.steam_path = path
            self.lib_label.config(foreground="gray")
            self.load_libraries()
            self.refresh(reschedule=False)

    # ---------- hlídání ----------
    def toggle(self):
        if self.armed:
            self.disarm("Hlídání je vypnuté.")
            return
        if not self.libs:
            messagebox.showwarning(APP_NAME, "Nejdřív vyber složku Steamu.")
            return
        self.armed, self.idle_since = True, None
        self.seen_download = bool(self.tree.get_children())
        self.btn.config(text="■  Zastavit hlídání")
        self.refresh(reschedule=False)

    def disarm(self, text):
        self.armed = False
        self.btn.config(text="▶  Spustit hlídání")
        self.status.config(text=text)

    def refresh(self, reschedule=True):
        active = scan(self.libs) if self.libs else []
        self.tree.delete(*self.tree.get_children())
        for name, done, total in active:
            pct = f"{done * 100 // total} %" if total else "–"
            prog = f"{fmt_bytes(done)} / {fmt_bytes(total)}" if total else "připravuje se"
            self.tree.insert("", "end", values=(name, prog, pct))
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
            self.status.config(text="Hlídám… stahování probíhá.")
            return
        if not self.seen_download:
            self.status.config(text="Hlídám… čekám, až nějaké stahování začne.")
            return
        now = time.time()
        self.idle_since = self.idle_since or now
        need = max(1, self.quiet_min.get()) * 60
        left = int(need - (now - self.idle_since))
        if left > 0:
            self.status.config(text=f"Stahování skončilo, ověřuji… ještě {left} s.")
            return
        _, verb = ACTIONS[self.action.get()]
        self.status.config(text="Probíhá odpočet…")
        self.countdown = CountdownDialog(self.root, max(5, self.countdown_s.get()), verb,
                                         self.execute, self.cancelled)

    def cancelled(self):
        self.countdown = None
        self.disarm("Akce byla zrušena. Hlídání je vypnuté.")

    def execute(self):
        self.countdown = None
        key, _ = ACTIONS[self.action.get()]
        cmd = power_command(key)
        if self.dry_run.get():
            self.disarm(f"Zkušební režim: teď by se provedla akce „{self.action.get()}“.")
            messagebox.showinfo(APP_NAME, "Zkušební režim – nic se nevypnulo.\n\nSpustil by se příkaz:\n"
                                + " ".join(cmd))
            return
        self.disarm("Provádím akci…")
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.strip() or f"návratový kód {r.returncode}")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(APP_NAME, f"Akci se nepodařilo provést:\n{e}")
            self.status.config(text="Akci se nepodařilo provést.")


def main():
    root = tk.Tk()
    root.title(APP_NAME)
    root.minsize(520, 520)
    try:
        ttk.Style().theme_use("vista" if sys.platform == "win32" else
                              "aqua" if sys.platform == "darwin" else "clam")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()

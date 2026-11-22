#!/usr/bin/env python3
"""
Auto Shutdown for Steam – graphical version.

Shows what Steam is downloading right now and, once watching is on, shuts down /
sleeps / restarts the computer when all downloads are finished.
The logic (finding libraries, reading manifests, power commands) is shared
with the terminal version in steam_autoshutdown.py.
"""

import math
import os
import subprocess
import sys
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

from i18n import LANGUAGES, get_language, load_saved_language, save_language, set_language, t
from steam_autoshutdown import (DOWNLOADING, FLAG_NAMES, describe_flags, find_libraries, fmt_bytes, power_command,
                                scan_states)

APP_NAME = "Auto Shutdown for Steam"
SCAN_INTERVAL_MS = 5000   # how often Steam manifests are read
TICK_MS = 200             # how often the status (quiet-period countdown) is updated
DONATE_URL = "https://ko-fi.com/ambi91"
KOFI_COLOR = "#29ABE0"   # Ko-fi blue
KOFI_HOVER = "#1E8BBA"

ACTIONS = ("shutdown", "sleep", "restart")  # texts: action_<key>, countdown_<key> in i18n.py


# State colours used by the status indicator and the countdown ring.
COLORS = {
    "off": "#9AA0A6",          # grey – not watching
    "waiting": "#3B82F6",      # blue – watching, nothing downloading yet
    "downloading": "#22C55E",  # green – downloads in progress
    "verifying": "#F59E0B",    # amber – quiet period before the countdown
    "paused": "#8B5CF6",       # violet – a watched download is paused, action on hold
    "countdown": "#EF4444",    # red – countdown running / action in progress
    "error": "#EF4444",
}
CANCEL_COLOR = "#3B82F6"
CANCEL_HOVER = "#2563EB"
START_COLOR = "#16A34A"   # green – "Start watching"
START_HOVER = "#15803D"
STOP_COLOR = "#DC2626"    # red – "Stop watching"
STOP_HOVER = "#B91C1C"
BADGE_COLOR = "#D97706"   # amber – the TEST MODE badge


def theme_colors(widget):
    """Window background and text colour of the current ttk theme (works in dark mode too)."""
    style = ttk.Style()
    bg = style.lookup("TFrame", "background") or widget.winfo_toplevel().cget("background")
    fg = style.lookup("TLabel", "foreground") or "black"
    return bg, fg


def blend(widget, c1, c2, amount):
    """Mix colour c1 with c2 (amount 0 = c1, 1 = c2). Accepts any Tk colour name."""
    a, b = widget.winfo_rgb(c1), widget.winfo_rgb(c2)
    return "#" + "".join(f"{int(x + (y - x) * amount) >> 8:02x}" for x, y in zip(a, b))


def ui_font(size, bold=False):
    family = tkfont.nametofont("TkDefaultFont").cget("family")
    return (family, size, "bold") if bold else (family, size)


class FlatButton(tk.Label):
    """Coloured button that looks the same on every system (ttk buttons can't be coloured on macOS)."""

    def __init__(self, parent, text, command, color, hover, **kw):
        kw.setdefault("padx", 14)
        kw.setdefault("pady", 6)
        super().__init__(parent, text=text, bg=color, fg="white", cursor="hand2",
                         borderwidth=0, highlightthickness=0, **kw)
        self.color, self.hover = color, hover
        self.bind("<Button-1>", lambda e: command())
        self.bind("<Enter>", lambda e: self.config(bg=self.hover))
        self.bind("<Leave>", lambda e: self.config(bg=self.color))

    def set_colors(self, color, hover):
        """Change the colours, e.g. when the button switches between Start and Stop."""
        self.color, self.hover = color, hover
        self.config(bg=color)


class StatusIndicator(tk.Canvas):
    """Animated status line: a coloured dot with "radar" pulses while watching,
    a filling ring during the quiet period, and a headline with a smaller subline."""

    SIZE = 64
    FRAME_MS = 33  # ~30 fps while animating

    def __init__(self, parent):
        super().__init__(parent, height=self.SIZE, highlightthickness=0, borderwidth=0)
        self.mode, self.text, self.sub = "off", "", ""
        self.badge = ""   # text of a pill on the right (e.g. TEST MODE), "" = hidden
        self.ring = None  # (start, duration) in time.time() seconds, for the quiet period
        self.t0 = time.monotonic()
        self.bind("<Configure>", lambda e: self.draw())
        self._job = None
        self._animate()

    def set(self, mode, text, sub="", ring=None):
        changed = (mode, text, sub, ring) != (self.mode, self.text, self.sub, self.ring)
        self.mode, self.text, self.sub, self.ring = mode, text, sub, ring
        if changed:
            self.draw()

    def set_badge(self, text):
        if text != self.badge:
            self.badge = text
            self.draw()

    def _draw_badge(self, cy):
        """Amber pill aligned to the right edge."""
        font = ui_font(11, True)
        text_w = tkfont.Font(font=font).measure(self.badge)
        h, pad = 22, 10
        right = self.winfo_width() - 2
        left = right - text_w - 2 * pad
        top, bottom = cy - h / 2, cy + h / 2
        self.create_oval(left, top, left + h, bottom, fill=BADGE_COLOR, outline="")
        self.create_oval(right - h, top, right, bottom, fill=BADGE_COLOR, outline="")
        self.create_rectangle(left + h / 2, top, right - h / 2, bottom, fill=BADGE_COLOR, outline="")
        self.create_text((left + right) / 2, cy, text=self.badge, fill="white", font=font)

    def _animate(self):
        self.draw()
        animated = self.mode in ("waiting", "downloading", "verifying", "countdown", "paused")
        # Static states still redraw now and then to follow a light/dark mode switch.
        self._job = self.after(self.FRAME_MS if animated else 1000, self._animate)

    def destroy(self):
        if self._job:
            self.after_cancel(self._job)
        super().destroy()

    def draw(self):
        bg, fg = theme_colors(self)
        self.config(bg=bg)
        self.delete("all")
        color = COLORS.get(self.mode, COLORS["off"])
        cx = cy = self.SIZE // 2
        r = 9
        t = time.monotonic() - self.t0

        if self.mode in ("waiting", "downloading", "countdown"):
            # Expanding rings that fade out – slow while waiting, faster while downloading.
            period = {"waiting": 2.6, "downloading": 1.6, "countdown": 1.0}[self.mode]
            for offset in (0.0, 0.5):
                p = (t / period + offset) % 1.0
                rr = r + p * (cx - r - 2)
                self.create_oval(cx - rr, cy - rr, cx + rr, cy + rr,
                                 outline=blend(self, color, bg, p), width=2)
        if self.mode == "verifying" and self.ring:
            start, duration = self.ring
            frac = min(1.0, max(0.0, (time.time() - start) / duration)) if duration else 1.0
            rr = cx - 6
            self.create_oval(cx - rr, cy - rr, cx + rr, cy + rr,
                             outline=blend(self, color, bg, 0.75), width=5)
            if frac > 0:
                self.create_arc(cx - rr, cy - rr, cx + rr, cy + rr, start=90, extent=-359.9 * frac,
                                style="arc", outline=color, width=5)

        # The dot "breathes" gently while watching.
        if self.mode in ("waiting", "downloading", "verifying", "countdown", "paused"):
            r += 1.5 * math.sin(t * 2 * math.pi / 1.6)
        self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color, outline="")

        x = self.SIZE + 8
        if self.sub:
            self.create_text(x, cy - 10, text=self.text, anchor="w", fill=fg, font=ui_font(13, True))
            self.create_text(x, cy + 12, text=self.sub, anchor="w",
                             fill=blend(self, fg, bg, 0.45), font=ui_font(11))
        else:
            self.create_text(x, cy, text=self.text, anchor="w", fill=fg, font=ui_font(13, True))
        if self.badge:
            self._draw_badge(cy)


class CountdownDialog(tk.Toplevel):
    """Cancellable countdown window with a smoothly draining ring. Stays on top of other windows."""

    RING = 220
    FRAME_MS = 33

    def __init__(self, parent, seconds, action, on_done, on_cancel):
        super().__init__(parent)
        self.title(APP_NAME)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.total, self.action = seconds, action
        self.deadline = time.monotonic() + seconds
        self.on_done, self.on_cancel = on_done, on_cancel
        self._last_left = None

        bg, _fg = theme_colors(parent)
        self.config(bg=bg)
        frm = ttk.Frame(self, padding=(28, 22))
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=t("dlg_finished"), font=ui_font(15, True)).pack()
        ttk.Label(frm, text=t(f"countdown_{action}"), font=ui_font(12),
                  foreground="gray").pack(pady=(4, 10))
        self.canvas = tk.Canvas(frm, width=self.RING, height=self.RING, highlightthickness=0,
                                borderwidth=0, bg=bg)
        self.canvas.pack(pady=(0, 16))
        btns = ttk.Frame(frm)
        btns.pack(fill="x")
        cancel = FlatButton(btns, t("dlg_cancel"), self.cancel, CANCEL_COLOR, CANCEL_HOVER,
                            font=ui_font(13, True), pady=8)
        cancel.pack(fill="x")
        ttk.Button(btns, text=t("dlg_now"), command=self.finish).pack(pady=(8, 0))

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
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            self.finish()
            return
        left = math.ceil(remaining)
        if left != self._last_left:
            self._last_left = left
            self.title(t("dlg_title", left=left, action=t(f"action_{self.action}")))
        self.draw(remaining, left)
        self._job = self.after(self.FRAME_MS, self.tick)

    def draw(self, remaining, left):
        c = self.canvas
        bg, fg = theme_colors(self)
        c.config(bg=bg)
        c.delete("all")
        frac = remaining / self.total
        # Blue while there's plenty of time, amber in the last 10 s, red in the last 5 s.
        color = COLORS["countdown"] if left <= 5 else COLORS["verifying"] if left <= 10 else COLORS["waiting"]
        pad, width = 12, 14
        box = (pad, pad, self.RING - pad, self.RING - pad)
        c.create_oval(*box, outline=blend(self, color, bg, 0.82), width=width)
        c.create_arc(*box, start=90, extent=359.9 * frac, style="arc", outline=color, width=width)
        # A small dot at the moving end of the ring.
        ang = math.radians(90 + 360 * frac)
        mid, rad = self.RING / 2, (self.RING - 2 * pad) / 2
        ex, ey = mid + rad * math.cos(ang), mid - rad * math.sin(ang)
        c.create_oval(ex - width / 2, ey - width / 2, ex + width / 2, ey + width / 2, fill=color, outline="")
        # The number "pops" at the start of each of the last 5 seconds.
        size = 60
        if left <= 5:
            size = int(60 + 14 * max(0.0, (remaining % 1) - 0.75) * 4)
        c.create_text(mid, mid - 8, text=str(left), fill=fg, font=ui_font(size, True))
        c.create_text(mid, mid + 42, text=t("dlg_seconds"), fill=blend(self, fg, bg, 0.45),
                      font=ui_font(12))

    def _close(self):
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        self.destroy()

    def cancel(self):
        self._close()
        self.on_cancel()

    def finish(self):
        self._close()
        self.on_done()


class HelpWindow(tk.Toplevel):
    """Read-only help text. Lines starting with "# " are headings."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title(t("help_title"))
        self.geometry("560x520")
        self.minsize(420, 320)
        bg, fg = theme_colors(parent)
        self.config(bg=bg)
        frm = ttk.Frame(self, padding=(16, 14))
        frm.pack(fill="both", expand=True)
        ttk.Button(frm, text=t("help_close"), command=self.destroy).pack(side="bottom", anchor="e", pady=(10, 0))
        text = tk.Text(frm, wrap="word", relief="flat", borderwidth=0, highlightthickness=0,
                       bg=bg, fg=fg, font=ui_font(12), padx=4, pady=4, spacing2=2, cursor="arrow")
        scroll = ttk.Scrollbar(frm, command=text.yview)
        text.config(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        text.tag_configure("h", font=ui_font(14, True), spacing1=10, spacing3=4)
        text.tag_configure("p", spacing3=2)
        for line in t("help_text").splitlines():
            if line.startswith("# "):
                text.insert("end", line[2:] + "\n", "h")
            else:
                text.insert("end", line + "\n", "p")
        text.config(state="disabled")
        text.mark_set("insert", "1.0")
        self.after_idle(lambda: text.yview_moveto(0))  # start at the top
        self.bind("<Escape>", lambda e: self.destroy())
        self.transient(parent)
        self.focus_force()


class FlagsTooltip(tk.Frame):
    """Panel listing every StateFlags bit and its meaning.

    Drawn inside the main window (not as a separate borderless window, which macOS
    may refuse to show). The states are laid out in two columns so the panel fits."""

    def __init__(self, root, x, y):
        # Follows the current theme (light/dark): a slightly lifted panel with a thin border.
        bg, fg = theme_colors(root)
        panel = blend(root, bg, fg, 0.06)
        muted = blend(root, fg, panel, 0.45)
        super().__init__(root, bg=panel, highlightthickness=1,
                         highlightbackground=blend(root, bg, fg, 0.25), padx=12, pady=10)
        flags = sorted(FLAG_NAMES)
        half = (len(flags) + 1) // 2
        tk.Label(self, text=t("flags_help_title"), bg=panel, fg=fg,
                 font=ui_font(12, True)).grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 4))
        for i, (value, key) in enumerate(flags):
            row, col = 1 + i % half, 0 if i < half else 3
            tk.Label(self, text=str(value), bg=panel, fg=muted,
                     font="TkFixedFont").grid(row=row, column=col, sticky="e", padx=(0, 8))
            tk.Label(self, text=t(key), bg=panel, fg=fg, font=ui_font(11)).grid(row=row, column=col + 1, sticky="w")
        self.columnconfigure(2, minsize=24)  # gap between the two columns
        tk.Label(self, text=t("flags_help_note"), bg=panel, fg=muted, font=ui_font(11), justify="left").grid(
            row=half + 1, column=0, columnspan=5, sticky="w", pady=(8, 0))
        # Keep the panel inside the window: shift it left/up if it would stick out.
        self.update_idletasks()
        x = max(4, min(x, root.winfo_width() - self.winfo_reqwidth() - 4))
        y = max(4, min(y, root.winfo_height() - self.winfo_reqheight() - 4))
        self.place(x=x, y=y)
        self.lift()


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
        self.active = []
        self.paused = []
        self.watched = set()  # appids seen downloading during this watch
        self.help_window = None

        self.action_key = ACTIONS[0]
        self.action_label = tk.StringVar()
        self.language = tk.StringVar()
        self.quiet_s = tk.IntVar(value=60)
        self.countdown_s = tk.IntVar(value=10)
        self.dry_run = tk.BooleanVar(value=False)
        self.dry_run.trace_add("write", lambda *_: self._render_badge())

        self._build()
        self.load_libraries()
        self.refresh()

    # ---------- layout ----------
    def _build(self):
        self.action_label.set(t(f"action_{self.action_key}"))
        self.language.set(LANGUAGES[get_language()])

        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text=APP_NAME, font=ui_font(16, True)).pack(side="left")
        lang_box = ttk.Combobox(top, textvariable=self.language, values=list(LANGUAGES.values()),
                                state="readonly", width=10)
        lang_box.pack(side="right")
        lang_box.bind("<<ComboboxSelected>>", self.change_language)
        ttk.Label(top, text=t("language")).pack(side="right", padx=(0, 4))
        ttk.Button(top, text=t("btn_help"), command=self.show_help).pack(side="right", padx=(0, 16))

        box = ttk.LabelFrame(self, text=t("box_downloading"), padding=8)
        box.pack(fill="both", expand=True)
        self.list_box = box  # its title also shows live counts, see _render_list_title()
        cols = ("game", "progress", "pct", "state")
        self.tree = ttk.Treeview(box, columns=cols, show="headings", height=6)
        self.tree.heading("game", text=t("col_game"))
        self.tree.heading("progress", text=t("col_progress"))
        self.tree.heading("pct", text="%")
        # The "(?)" in the heading shows a list of all possible states on hover.
        self.tree.heading("state", text=f"{t('col_state')}  (?)")
        self._flags_tip = None
        self.tree.bind("<Motion>", self._on_tree_motion)
        self.tree.bind("<Leave>", self._on_tree_leave)
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

        self.status = StatusIndicator(self)
        self.status.pack(fill="x", pady=(0, 8))
        self._render_badge()
        # The main action gets a large coloured button (ttk buttons ignore height and colour on macOS).
        self.btn = FlatButton(self, "", self.toggle, START_COLOR, START_HOVER,
                              font=ui_font(14, True), pady=11)
        self.btn.pack(fill="x")
        self._render_status()
        self._render_button()

        # Support development: a separate footer with a short text and a coloured
        # Ko-fi button. Visible, but nothing pops up or gets in the way – just a static element.
        ttk.Separator(self).pack(fill="x", pady=(14, 8))
        footer = ttk.Frame(self)
        footer.pack(fill="x")
        ttk.Label(footer, text=t("footer_question"), foreground="gray").pack(side="left")
        base = tkfont.nametofont("TkDefaultFont")
        self.donate = FlatButton(footer, t("btn_donate"), lambda: webbrowser.open(DONATE_URL),
                                 KOFI_COLOR, KOFI_HOVER, padx=12, pady=5,
                                 font=ui_font(base.cget("size"), True))
        self.donate.pack(side="right")

    # ---------- help ----------
    def show_help(self):
        if self.help_window is not None and self.help_window.winfo_exists():
            self.help_window.lift()
            self.help_window.focus_force()
            return
        self.help_window = HelpWindow(self.root)

    # ---------- StateFlags help ----------
    def _on_tree_motion(self, event):
        over_state_heading = (self.tree.identify_region(event.x, event.y) == "heading"
                              and self.tree.identify_column(event.x) == "#4")
        if over_state_heading and self._flags_tip is None:
            # Just under the heading row, so the panel never covers the pointer.
            x = event.x_root - self.root.winfo_rootx() - 40
            y = self.tree.winfo_rooty() - self.root.winfo_rooty() + 34
            self._flags_tip = FlagsTooltip(self.root, x, y)
        elif not over_state_heading:
            self._hide_flags_tip()

    def _on_tree_leave(self, _event):
        # Showing the tooltip can send a stray <Leave> although the pointer is still over the
        # list – hide only when the pointer has really left it.
        x, y = self.tree.winfo_pointerxy()
        if self.tree.winfo_containing(x, y) is not self.tree:
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

    # status key -> (indicator mode, subline key)
    STATUS_LOOK = {
        "status_off": ("off", "sub_off"),
        "status_waiting": ("waiting", "sub_waiting"),
        "status_downloading": ("downloading", "sub_downloading"),
        "status_verifying": ("verifying", "sub_verifying"),
        "status_paused": ("paused", "sub_paused"),
        "status_countdown": ("countdown", "sub_countdown"),
        "status_executing": ("countdown", None),
        "status_action_failed": ("error", None),
    }

    def _render_status(self):
        key, kwargs = self._status
        mode, sub = self.STATUS_LOOK.get(key, ("off", None))
        ring = None
        if mode == "verifying" and self.idle_since:
            ring = (self.idle_since, max(10, self.quiet_s.get()))
        held = ", ".join(item[1] for item in self.held())
        self.status.set(mode, t(key, **kwargs), t(sub, n=len(self.active), names=held) if sub else "", ring)

    def _render_badge(self):
        """Show a TEST MODE pill next to the status while Test mode is on."""
        self.status.set_badge(t("badge_test_mode") if self.dry_run.get() else "")

    def _render_button(self):
        self.btn.config(text=t("btn_stop") if self.armed else t("btn_start"))
        if self.armed:
            self.btn.set_colors(STOP_COLOR, STOP_HOVER)
        else:
            self.btn.set_colors(START_COLOR, START_HOVER)

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
        self.watched = set()
        self.seen_download = bool(self.tree.get_children())
        self._render_button()
        self.refresh(reschedule=False)

    def disarm(self, key, **kwargs):
        self.armed = False
        self._render_button()
        self.set_status(key, **kwargs)

    def refresh(self, reschedule=True):
        self.active, self.paused = scan_states(self.libs) if self.libs else ([], [])
        if self.armed:
            self.watched.update(item[0] for item in self.active)
        active = self.active + self.held()  # paused downloads that hold the action are listed too
        self.tree.delete(*self.tree.get_children())
        for _appid, name, done, total, flags in active:
            pct = f"{done * 100 // total} %" if total else "–"
            prog = f"{fmt_bytes(done)} / {fmt_bytes(total)}" if total else t("preparing")
            state = f"{' · '.join(describe_flags(flags))}  ({flags})"
            self.tree.insert("", "end", values=(name, prog, pct, state))
        if active:
            self.empty_label.place_forget()
        else:
            self.empty_label.place(relx=0.5, rely=0.55, anchor="center")
        self._render_list_title()

        self.tick(reschedule=False)
        if reschedule:
            self.root.after(SCAN_INTERVAL_MS, self.refresh)
            self.root.after(TICK_MS, self.tick)

    def _render_list_title(self):
        """List title with counts, so it's clear the app waits for queued games too."""
        title = t("box_downloading")
        if self.active or self.held():
            downloading = sum(1 for item in self.active if item[4] & DOWNLOADING)
            counts = t("box_counts", d=downloading, q=len(self.active) - downloading)
            if self.held():
                counts += t("box_counts_paused", p=len(self.held()))
            title = f"{title}  ·  {counts}"
        self.list_box.config(text=title)

    def held(self):
        """Paused downloads that were downloading during this watch – they hold the action."""
        return [item for item in self.paused if item[0] in self.watched] if self.armed else []

    def tick(self, reschedule=True):
        """Update the status from the last scan – often, so the quiet-period countdown runs smoothly."""
        if self.armed and self.countdown is None:
            self.evaluate(bool(self.active), bool(self.held()))
        if reschedule:
            self.root.after(TICK_MS, self.tick)

    def evaluate(self, downloading, paused=False):
        if downloading:
            self.seen_download, self.idle_since = True, None
            self.set_status("status_downloading")
            return
        if paused:
            self.idle_since = None
            self.set_status("status_paused")
            return
        if not self.seen_download:
            self.set_status("status_waiting")
            return
        now = time.time()
        self.idle_since = self.idle_since or now
        need = max(10, self.quiet_s.get())
        left = math.ceil(need - (now - self.idle_since))
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


def resource_path(name):
    """Path to a bundled file – next to this script, or inside the PyInstaller bundle."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def main():
    set_language(load_saved_language())
    root = tk.Tk()
    root.title(APP_NAME)
    try:
        root._icon = tk.PhotoImage(file=str(resource_path("assets/icon.png")))
        root.iconphoto(True, root._icon)
    except tk.TclError:
        pass  # no icon is not a reason to fail
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

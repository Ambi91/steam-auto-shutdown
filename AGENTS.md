# Instructions for AI agents

## Language

The app is being distributed to people outside the Czech Republic, so **everything
new is written in English**: code comments, docstrings, commit messages, README
and other docs, and these instructions. Existing Czech comments and docs may be
translated to English when you touch them.

The only exception is the Czech UI translation in `i18n.py`, which stays as a
supported language. English is the default UI language.

## Git: commit and push

- **Ask the user for the commit message before every commit.** Propose a message
  and wait until the user approves or edits it. Never commit with a message they
  haven't seen.
- **Push only with approval.** Don't push anything to GitHub until the user
  explicitly agrees. Approval covers that one push only, not later ones.
- Write commit messages in English, in the imperative mood
  (e.g. "Add…", "Fix…").

## About the project

- Auto Shutdown for Steam: shuts down, sleeps or restarts the computer once Steam
  finishes downloading. Runs on Windows, macOS and Linux.
- Python 3.8+ standard library only (tkinter), no dependencies.
- `steam_autoshutdown.py` – core logic and the terminal version.
- `steam_autoshutdown_gui.py` – the graphical version (tkinter).
- `download_progress.py` – live progress estimate (Steam's content log + network
  bytes received), since Steam doesn't update the manifests while downloading.
- `i18n.py` – all user-facing text, in English (default) and Czech.
  Add every new string in both languages and use it in code via `t("key")`.
- `SteamAutoShutdown.spec` and `.github/workflows/build.yml` – PyInstaller builds.

## Running and testing

- GUI: `python steam_autoshutdown_gui.py`, terminal: `python steam_autoshutdown.py --status`.
- Never trigger a real shutdown while testing: enable Test mode in the GUI,
  use `--dry-run` or `--status` in the terminal.
- On Windows, set `PYTHONIOENCODING=utf-8` when output is redirected, otherwise
  test scripts crash on characters like "↓" or "▶".
- **After every change to the app, launch it for the user to preview.** Start the
  GUI (`python steam_autoshutdown_gui.py`) in the background so the user can see
  the change before committing. If the change only affects the terminal version,
  run `python steam_autoshutdown.py --status` and show the output instead. Close
  any previous instance you started first, so only one window is open.

# Steam Auto-Shutdown

A small app that shuts down, sleeps or restarts your computer once Steam finishes downloading.
Works on Windows, macOS and Linux.

## Usage

1. Start the app. It finds Steam on its own and shows what is downloading right now.
   If Steam is installed somewhere else, pick its folder with the **Steam folder…** button.
2. Choose what should happen: **Shut down**, **Sleep** or **Restart**.
3. Click **Start watching** and let Steam download.
4. Once nothing has downloaded for the set time (2 min by default), a countdown window
   appears (60 s by default). Click **Cancel** to stop the action.

Tip: the first time, try **Test mode**. Nothing shuts down, it only shows the countdown.

Language: the app starts in English. Switch to Czech in the **Language** drop-down
in the top right; your choice is remembered. The terminal version takes `--lang cs`.

## Installation

Ready-to-run files are on GitHub under **Releases**:
https://github.com/Ambi91/steam-auto-shutdown/releases

| System  | File                                | How to run |
|---------|-------------------------------------|------------|
| Windows | `SteamAutoShutdown-windows-*.zip`   | Unzip and run `SteamAutoShutdown.exe`. SmartScreen may show a warning: *More info → Run anyway*. |
| macOS   | `SteamAutoShutdown-macos-*.zip`     | Unzip, move `Steam Auto-Shutdown.app` to Applications and open it the first time via *right-click → Open* (the app is not signed). The first time it shuts down, allow it to control "System Events". |
| Linux   | `SteamAutoShutdown-linux-*.tar.gz`  | Extract and run `./SteamAutoShutdown`. It shuts down via `systemctl`, which works without sudo on common desktop distributions. |

## How it works

For every game, Steam keeps a file `steamapps/appmanifest_<id>.acf` with its state
(`StateFlags`) and how many bytes are left to download. The app reads these files every
5 s in all Steam libraries (listed in `libraryfolders.vdf`). Games you have paused in
Steam are ignored.

## Building

PyInstaller only builds for the system it runs on. So:

### All systems – GitHub Actions (automatic, recommended)

The configuration is in `.github/workflows/build.yml`. GitHub builds the Windows, macOS
and Linux versions on its own servers. To run it:

- manually: *Actions → Build → Run workflow*. The files are then under *Artifacts* on that run.
- by releasing a version: `git tag v1.0.0 && git push origin v1.0.0`. This creates a Release
  with all three files.

### Manually on a given computer

All you need is [uv](https://docs.astral.sh/uv/). It downloads Python with tkinter by itself.

macOS (the same on Linux, just without the last line):

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv pyinstaller==6.22.3
.venv/bin/python -m PyInstaller --noconfirm --clean SteamAutoShutdown.spec
ditto -c -k --keepParent "dist/Steam Auto-Shutdown.app" dist/SteamAutoShutdown-macos-v1.0.0.zip
```

Windows (PowerShell):

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv pyinstaller==6.22.3
.venv\Scripts\python -m PyInstaller --noconfirm --clean SteamAutoShutdown.spec
Compress-Archive dist\SteamAutoShutdown.exe dist\SteamAutoShutdown-windows-v1.0.0.zip
```

You can also run it directly without building: `python3 steam_autoshutdown_gui.py`
(GUI) or `python3 steam_autoshutdown.py` (terminal version).

## Support

The app is free. If it saved you time and you'd like to support further development,
you can chip in on **Ko-fi**: https://ko-fi.com/ambi91. Donations are entirely voluntary.

## License

Freeware for personal use. Redistribution, modifying the source code and commercial
use require prior written permission from the author. See the [LICENSE](LICENSE) file
for details.

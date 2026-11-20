# PyInstaller spec – builds a single executable (Windows, Linux)
# or a .app bundle (macOS).   Usage:  pyinstaller SteamAutoShutdown.spec
import sys

a = Analysis(["steam_autoshutdown_gui.py"], excludes=["unittest", "pydoc", "doctest"])
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SteamAutoShutdown",
              console=False, argv_emulation=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="SteamAutoShutdown")
    app = BUNDLE(
        coll,
        name="Steam Auto-Shutdown.app",
        bundle_identifier="cz.local.steamautoshutdown",
        info_plist={
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
            # without this key macOS silently blocks shutting down via "System Events"
            "NSAppleEventsUsageDescription":
                "The app needs to control System Events to shut down, sleep or "
                "restart the computer after Steam downloads finish.",
        },
    )
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="SteamAutoShutdown",
              console=False, upx=False)

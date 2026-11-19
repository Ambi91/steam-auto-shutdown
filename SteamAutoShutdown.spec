# PyInstaller spec – sestaví jeden spustitelný soubor (Windows, Linux)
# nebo aplikaci .app (macOS).   Použití:  pyinstaller SteamAutoShutdown.spec
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
            # bez tohoto klíče macOS vypnutí přes "System Events" tiše zablokuje
            "NSAppleEventsUsageDescription":
                "Aplikace potřebuje ovládat System Events, aby mohla po dokončení "
                "stahování vypnout, uspat nebo restartovat počítač.",
        },
    )
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="SteamAutoShutdown",
              console=False, upx=False)

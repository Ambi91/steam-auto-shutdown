# Steam Auto-Shutdown

Malá aplikace, která po dokončení stahování ve Steamu vypne, uspí nebo restartuje počítač.
Funguje na Windows, macOS i Linuxu.

## Používání

1. Spusť aplikaci. Sama najde Steam a ukáže, co se právě stahuje.
   Pokud máš Steam jinde, vyber jeho složku tlačítkem **Složka Steamu…**.
2. Zvol, co se má stát: **Vypnout**, **Uspat** nebo **Restartovat**.
3. Klikni na **Spustit hlídání** a nech Steam stahovat.
4. Když se nic nestahuje po nastavenou dobu (výchozí 2 min), objeví se okno s odpočtem
   (výchozí 60 s). Kliknutím na **Zrušit** akci stopneš.

Tip: poprvé zkus **Zkušební režim**, ve kterém se nic nevypne, jen se ukáže odpočet.

## Instalace

Hotové soubory najdeš na GitHubu v sekci **Releases**:
https://github.com/Ambi91/steam-auto-shutdown/releases

| Systém  | Soubor                              | Spuštění |
|---------|-------------------------------------|----------|
| Windows | `SteamAutoShutdown-windows-*.zip`   | Rozbal a spusť `SteamAutoShutdown.exe`. SmartScreen může zobrazit varování: *Další informace → Přesto spustit*. |
| macOS   | `SteamAutoShutdown-macos-*.zip`     | Rozbal, přesuň `Steam Auto-Shutdown.app` do Aplikací a poprvé ji otevři přes *pravé tlačítko → Otevřít* (aplikace není podepsaná). Při prvním vypínání povol ovládání „System Events“. |
| Linux   | `SteamAutoShutdown-linux-*.tar.gz`  | Rozbal a spusť `./SteamAutoShutdown`. Vypíná přes `systemctl`, což na běžných desktopových distribucích funguje bez sudo. |

## Jak to funguje

Steam si u každé hry vede soubor `steamapps/appmanifest_<id>.acf`, ve kterém je stav
(`StateFlags`) a kolik bajtů zbývá stáhnout. Aplikace tyto soubory každých 5 s čte
ve všech knihovnách Steamu (podle `libraryfolders.vdf`). Hru, kterou máš ve Steamu
pozastavenou, ignoruje.

## Sestavení

PyInstaller sestavuje vždy jen pro systém, na kterém běží. Proto:

### Všechny systémy – GitHub Actions (automaticky, doporučeno)

Konfigurace je v `.github/workflows/build.yml`. GitHub sestaví verze pro
Windows, macOS i Linux na svých serverech. Spuštění:

- ručně: *Actions → Build → Run workflow*. Soubory pak najdeš u běhu v sekci *Artifacts*.
- vydáním verze: `git tag v1.0.0 && git push origin v1.0.0`. Vytvoří se Release
  se všemi třemi soubory.

### Ručně na daném počítači

Potřebuješ jen [uv](https://docs.astral.sh/uv/). Python s tkinterem si stáhne sám.

macOS (na Linuxu stejně, jen bez posledního řádku):

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

Bez sestavování to jde spustit i přímo: `python3 steam_autoshutdown_gui.py`
(GUI) nebo `python3 steam_autoshutdown.py` (verze pro terminál).

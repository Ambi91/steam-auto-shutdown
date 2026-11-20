# Publishing to the Microsoft Store

The Windows build is packaged as **MSIX** by GitHub Actions (artifact
`MicrosoftStore-msix`). The Store signs the package itself, so no code-signing
certificate is needed.

## 1. One-time setup

1. Create a developer account at https://partner.microsoft.com/dashboard
   (choose an **individual** account).
2. **Apps and games → New product → MSIX or PWA app** and reserve the name,
   e.g. **Auto Shutdown for Steam**. Avoid a name that starts with "Steam":
   it's Valve's trademark and such names tend to be rejected.
3. Open the new app → **Product management → Product identity** and copy:

   | Partner Center field          | GitHub repository variable     |
   |-------------------------------|--------------------------------|
   | Package/Identity/Name         | `MSIX_IDENTITY_NAME`           |
   | Package/Identity/Publisher    | `MSIX_PUBLISHER`               |
   | Package/Properties/PublisherDisplayName | `MSIX_PUBLISHER_DISPLAY_NAME` |
   | the reserved app name         | `MSIX_DISPLAY_NAME`            |

4. Add them on GitHub: **Settings → Secrets and variables → Actions →
   Variables → New repository variable**. They are not secret.

## 2. Each release

1. Create a release with a tag like `v1.0.0` (Releases → Draft a new release).
   The MSIX version is taken from the tag (`v1.0.0` → `1.0.0.0`) and **must be
   higher** than the one already in the Store.
2. When the workflow finishes, download the `MicrosoftStore-msix` artifact from
   the run and unzip it.
3. In Partner Center: **Start submission**, fill in the sections below and upload
   the `.msix` under **Packages**. Certification usually takes a few days.

## 3. Submission answers

- **Pricing:** Free. **Markets:** all.
- **Category:** Utilities & tools.
- **Privacy policy URL:**
  https://github.com/Ambi91/steam-auto-shutdown/blob/main/PRIVACY.md
- **Support/website:** https://github.com/Ambi91/steam-auto-shutdown
- **Age ratings (IARC questionnaire):** category "Utility"; answer *No* to
  everything (no violence, no user interaction or sharing, no location, no
  purchases, no unrestricted internet). Expected rating: 3+ / Everyone.
- **Restricted capability `runFullTrust`** – justification:
  > This is a classic desktop (Win32) app packaged as MSIX. It needs full trust
  > to read Steam's library files and to run the Windows "shutdown" command
  > when the user's Steam downloads finish.
- **Notes for certification:**
  > The app watches Steam download status by reading Steam's local manifest
  > files. To test without shutting down the PC, enable "Test mode" in the app
  > and press "Start watching". Steam does not need to be installed: the app
  > then shows that no Steam library was found.
- **Screenshots:** at least one, taken on Windows (1366×768 or larger): the
  main window while watching, and the countdown window.

## 4. Store listing – English

**Short description**
Shuts down, sleeps or restarts your PC automatically once Steam finishes downloading.

**Description**
Downloading a big game overnight? Auto Shutdown for Steam waits until every
Steam download is finished and then shuts down, sleeps or restarts your
computer – so it doesn't run all night for nothing.

• Finds Steam and all your game libraries automatically, on every drive
• Shows what is downloading, with progress and the exact Steam state
• Waits a little after the last download, in case Steam starts another one
• Big countdown before the action, which you can cancel any time
• Test mode to try it safely
• English and Czech
• Free, no ads, no accounts, collects no data

Not affiliated with Valve Corporation. Steam is a trademark of Valve Corporation.

**Features** (one per line)
Automatic shutdown, sleep or restart after Steam downloads
Works with Steam libraries on multiple drives
Cancellable countdown before the action
Test mode
No data collection

**Keywords:** steam, shutdown, download, auto shutdown, sleep, timer, games

## 5. Store listing – Czech

**Krátký popis**
Po dokončení stahování ve Steamu automaticky vypne, uspí nebo restartuje počítač.

**Popis**
Stahuješ přes noc velkou hru? Auto Shutdown for Steam počká, až Steam dokončí
všechna stahování, a pak vypne, uspí nebo restartuje počítač – aby zbytečně
neběžel celou noc.

• Sám najde Steam a všechny knihovny her, i na více discích
• Ukazuje, co se stahuje, jak daleko to je a přesný stav ve Steamu
• Po posledním stahování chvíli počká, kdyby Steam začal stahovat něco dalšího
• Před akcí velký odpočet, který můžeš kdykoli zrušit
• Zkušební režim pro bezpečné vyzkoušení
• Čeština a angličtina
• Zdarma, bez reklam, bez účtu, nesbírá žádná data

Aplikace není nijak spojena se společností Valve Corporation. Steam je ochranná
známka společnosti Valve Corporation.

**Funkce**
Automatické vypnutí, uspání nebo restart po stažení ve Steamu
Podpora knihoven Steamu na více discích
Odpočet před akcí s možností zrušení
Zkušební režim
Žádný sběr dat

**Klíčová slova:** steam, vypnutí, stahování, automatické vypnutí, uspání, časovač, hry

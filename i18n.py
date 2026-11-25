"""
i18n.py – app texts in English (default) and Czech.

Usage:
    from i18n import t, set_language
    set_language("cs")
    t("nothing_downloading")            # -> "Nic se nestahuje." (Czech for "Nothing is downloading.")
    t("idle", stamp=..., idle=5, quiet=120)

The GUI saves the chosen language to settings.json in the app's settings folder
(Windows: %APPDATA%\\SteamAutoShutdown, macOS: ~/Library/Application Support/
SteamAutoShutdown, Linux: ~/.config/steam-auto-shutdown). The CLI reads it from
there unless --lang is given.
"""

import json
import os
import platform
from pathlib import Path

DEFAULT_LANGUAGE = "en"
LANGUAGES = {"en": "English", "cs": "Čeština"}  # code -> name in that language

STRINGS = {
    "en": {
        # --- StateFlags ---
        "flag_downloading": "Downloading",
        "flag_preallocating": "Preallocating",
        "flag_adding_files": "Adding files",
        "flag_staging": "Staging",
        "flag_committing": "Committing",
        "flag_validating": "Validating",
        "flag_update_running": "Update running",
        "flag_update_started": "Update started",
        "flag_update_stopping": "Stopping update",
        "flag_reconfiguring": "Reconfiguring",
        "flag_update_paused": "Paused",
        "flag_update_required": "Update required",
        "flag_uninstalling": "Uninstalling",
        "flag_backing_up": "Backing up",
        "flag_app_running": "Game running",
        "flag_locked": "Locked",
        "flag_encrypted": "Encrypted",
        "flag_files_missing": "Files missing",
        "flag_files_corrupt": "Files corrupt",
        "flag_installed": "Installed",
        "flag_uninstalled": "Not installed",
        "flag_invalid": "Invalid state",

        # --- CLI ---
        "cli_description": "Shuts down the PC once Steam finishes downloading.",
        "arg_steam_path": "path to the Steam folder (found automatically otherwise)",
        "arg_interval": "how often to check, in seconds (15)",
        "arg_quiet": "how many seconds nothing may download before it counts as done (60)",
        "arg_countdown": "countdown before the action, in seconds (10)",
        "arg_action": "what to do when downloads finish (shutdown)",
        "arg_no_wait_start": "don't wait for a download to start (otherwise acts only after one was seen)",
        "arg_dry_run": "don't shut anything down, just print",
        "arg_status": "print the current state once and exit",
        "arg_lang": "language: en or cs (default: last used, otherwise en)",
        "cli_steam_not_found": "Steam could not be found. Pass its location with --steam-path.",
        "cli_libraries": "Steam libraries:",
        "nothing_downloading": "Nothing is downloading or queued.",
        "cli_watching": "Watching downloads (checking every {interval} s). Press Ctrl+C to stop.\n",
        "cli_downloading": "[{stamp}] Downloading: {desc}",
        "cli_paused": "[{stamp}] Paused in Steam: {names} – not shutting down until it is resumed.",
        "cli_waiting_start": "[{stamp}] Waiting for a download to start…",
        "cli_idle": "[{stamp}] Nothing downloading for {idle} s (need {quiet} s)",
        "cli_dry_run": "[dry-run] Would run:",
        "cli_stopped": "\nStopped.",
        "cli_countdown": "\nAll downloads finished. Action '{action}' in {seconds} s. Press Ctrl+C to cancel.",
        "cli_cancelled": "\nCancelled by user.",

        # --- GUI ---
        "action_shutdown": "Shut down the computer",
        "action_sleep": "Put the computer to sleep",
        "action_restart": "Restart the computer",
        "countdown_shutdown": "The computer will shut down in:",
        "countdown_sleep": "The computer will go to sleep in:",
        "countdown_restart": "The computer will restart in:",
        "dlg_finished": "Steam downloads are finished.",
        "dlg_cancel": "Cancel",
        "dlg_now": "Do it now",
        "language": "Language:",
        "btn_steam_folder": "Steam folder…",
        "box_downloading": "Downloading and queued – waiting for all of them",
        "box_counts": "{d} downloading, {q} queued",
        "box_counts_paused": ", {p} paused",
        "col_game": "Game",
        "col_progress": "Downloaded",
        "col_state": "State",
        "flags_help_title": "Possible states (StateFlags bits)",
        "flags_help_note": "StateFlags is the sum of these values,\ne.g. 6 = 4 (Installed) + 2 (Update required).",
        "box_settings": "Settings",
        "box_libraries": "Steam libraries",
        "opt_action": "When finished:",
        "opt_quiet": "Wait with no downloads (s):",
        "opt_countdown": "Countdown before action (s):",
        "opt_dry_run": "Test mode (don't shut down, just show the countdown)",
        "status_off": "Watching is off.",
        "status_paused": "Watching… a download is paused.",
        "sub_paused": "Paused in Steam: {names}. I won't shut down until it's resumed.",
        "btn_feedback": "✉  Feedback",
        "feedback_bug": "Report a problem…",
        "feedback_idea": "Suggest an improvement…",
        "feedback_email": "Send an email ({email})",
        "feedback_mail_subject": "{app} – feedback",
        "feedback_mail_body": "Hi,\n\n\n\n---\nSystem: {env}\n",
        "btn_help": "?  Help",
        "help_title": "Help",
        "help_close": "Close",
        "help_text": """# What the app watches
The app watches Steam's download queue: games that are downloading right now and games waiting in the queue, ready to download. It looks at all your Steam libraries, on every drive.

# When it shuts down
Only once the whole queue is empty. When the last download finishes, the app waits for the set time (“Wait with no downloads”) in case Steam starts another one. Then a countdown window appears and, when it ends, the computer shuts down, sleeps or restarts – whichever you chose.

# Paused downloads
If you pause a download in Steam, the app will not shut the computer down. It waits until you resume the download or remove it from the queue. Games that were already paused before you started watching are ignored, so an old, forgotten download doesn't block the shutdown forever.

# Progress
Steam doesn't update its files while it downloads, only when a download starts, pauses or finishes. So for the game being downloaded the app shows an estimate marked with “~”, together with the download speed. It adds what Steam has received over the network to what Steam last reported. The estimate can be a little off – on Windows and Linux other network traffic counts too – and the exact figure appears again whenever Steam writes it.

# Cancelling
You can cancel at any time: press Cancel (or Esc) in the countdown window, or Stop watching in the main window.

# Test mode
With Test mode on, nothing shuts down – you only see the countdown and a message about what would happen. Good for trying the app out.

# Tips
• Keep Steam running – the app only reads Steam's files, it doesn't download anything itself.
• Make sure the computer doesn't go to sleep on its own before the downloads finish (Windows power settings).
• The “State” column shows exactly what Steam reports for each game. Hover over “(?)” in its heading for an explanation.

# Problems and ideas
Found a bug or have an idea? Click “Feedback” at the top of the main window. You can report it on GitHub (the form already contains your system version) or send an email to jan.ambroz.91@gmail.com. Thank you!""",
        "sub_off": "Press Start watching and let Steam download.",
        "sub_waiting": "Nothing is downloading yet. Start a download in Steam.",
        "sub_downloading": "Active downloads: {n}. I'll act once they're all done.",
        "sub_verifying": "Making sure Steam doesn't start another download.",
        "sub_countdown": "You can still cancel it in the countdown window.",
        "dlg_seconds": "seconds",
        "dlg_title": "{left} s – {action}",
        "btn_start": "▶  Start watching",
        "btn_stop": "■  Stop watching",
        "badge_test_mode": "TEST MODE",
        "footer_question": "Saved your PC from running all night for nothing?",
        "btn_donate": "☕  Support on Ko-fi",
        "libs_found": "Libraries found: {n}",
        "steam_not_found": "Steam was not found.\nChoose its folder with the button below.",
        "choose_folder_title": "Choose the folder where Steam is installed",
        "choose_folder_first": "Choose the Steam folder first.",
        "preparing": "preparing",
        "status_downloading": "Watching… downloads in progress.",
        "status_waiting": "Watching… waiting for a download to start.",
        "status_verifying": "Downloads finished, verifying… {left} s left.",
        "status_countdown": "Countdown in progress…",
        "status_cancelled": "Action cancelled. Watching is off.",
        "status_dry_run": "Test mode: the action “{action}” would run now.",
        "msg_dry_run": "Test mode – nothing was shut down.\n\nThis command would run:\n{cmd}",
        "status_executing": "Running the action…",
        "return_code": "return code {code}",
        "msg_action_failed": "The action could not be performed:\n{error}",
        "status_action_failed": "The action could not be performed.",
    },
    "cs": {
        # --- StateFlags ---
        "flag_downloading": "Stahuje",
        "flag_preallocating": "Alokuje místo",
        "flag_adding_files": "Přidává soubory",
        "flag_staging": "Zpracovává data",
        "flag_committing": "Zapisuje",
        "flag_validating": "Ověřuje",
        "flag_update_running": "Aktualizace běží",
        "flag_update_started": "Aktualizace zahájena",
        "flag_update_stopping": "Zastavuje aktualizaci",
        "flag_reconfiguring": "Mění konfiguraci",
        "flag_update_paused": "Pozastaveno",
        "flag_update_required": "Čeká aktualizace",
        "flag_uninstalling": "Odinstalovává",
        "flag_backing_up": "Zálohuje",
        "flag_app_running": "Hra běží",
        "flag_locked": "Uzamčeno",
        "flag_encrypted": "Zašifrováno",
        "flag_files_missing": "Chybí soubory",
        "flag_files_corrupt": "Poškozené soubory",
        "flag_installed": "Nainstalováno",
        "flag_uninstalled": "Neinstalováno",
        "flag_invalid": "Neplatný stav",

        # --- CLI ---
        "cli_description": "Vypne PC po dokončení stahování ve Steamu.",
        "arg_steam_path": "cesta ke složce Steamu (jinak se najde sama)",
        "arg_interval": "jak často kontrolovat, v sekundách (15)",
        "arg_quiet": "kolik sekund se nesmí nic stahovat, než se to považuje za hotové (60)",
        "arg_countdown": "odpočet před vypnutím, v sekundách (10)",
        "arg_action": "co udělat po dokončení stahování (shutdown)",
        "arg_no_wait_start": "nečekat, až nějaké stahování začne (jinak se vypne až po prvním zachyceném)",
        "arg_dry_run": "nic nevypínat, jen vypsat",
        "arg_status": "jednou vypsat stav a skončit",
        "arg_lang": "jazyk: en nebo cs (výchozí: naposledy použitý, jinak en)",
        "cli_steam_not_found": "Steam se nepodařilo najít. Zadej cestu přes --steam-path.",
        "cli_libraries": "Knihovny Steamu:",
        "nothing_downloading": "Nic se nestahuje ani nečeká ve frontě.",
        "cli_watching": "Hlídám stahování (kontrola každých {interval} s). Ukončíš to Ctrl+C.\n",
        "cli_downloading": "[{stamp}] Stahuje se: {desc}",
        "cli_paused": "[{stamp}] Pozastaveno ve Steamu: {names} – nevypnu, dokud se nespustí znovu.",
        "cli_waiting_start": "[{stamp}] Čekám, až začne nějaké stahování…",
        "cli_idle": "[{stamp}] Nic se nestahuje už {idle} s (potřeba {quiet} s)",
        "cli_dry_run": "[dry-run] Spustil bych:",
        "cli_stopped": "\nUkončeno.",
        "cli_countdown": "\nVšechna stahování dokončena. Akce '{action}' za {seconds} s. "
                         "Zrušíš ji klávesami Ctrl+C.",
        "cli_cancelled": "\nZrušeno uživatelem.",

        # --- GUI ---
        "action_shutdown": "Vypnout počítač",
        "action_sleep": "Uspat počítač",
        "action_restart": "Restartovat počítač",
        "countdown_shutdown": "Počítač se vypne za:",
        "countdown_sleep": "Počítač se uspí za:",
        "countdown_restart": "Počítač se restartuje za:",
        "dlg_finished": "Stahování ve Steamu je dokončeno.",
        "dlg_cancel": "Zrušit",
        "dlg_now": "Provést hned",
        "language": "Jazyk:",
        "btn_steam_folder": "Složka Steamu…",
        "box_downloading": "Stahuje se a čeká ve frontě – čekám na všechny",
        "box_counts": "stahuje se {d}, ve frontě {q}",
        "box_counts_paused": ", pozastaveno {p}",
        "col_game": "Hra",
        "col_progress": "Staženo",
        "col_state": "Stav",
        "flags_help_title": "Možné stavy (bity StateFlags)",
        "flags_help_note": "StateFlags je součet těchto hodnot,\nnapř. 6 = 4 (Nainstalováno) + 2 (Čeká aktualizace).",
        "box_settings": "Nastavení",
        "box_libraries": "Knihovny Steamu",
        "opt_action": "Po dokončení:",
        "opt_quiet": "Počkat bez stahování (s):",
        "opt_countdown": "Odpočet před akcí (s):",
        "opt_dry_run": "Zkušební režim (počítač nevypínat, jen ukázat odpočet)",
        "status_off": "Hlídání je vypnuté.",
        "status_paused": "Hlídám… stahování je pozastavené.",
        "sub_paused": "Pozastaveno ve Steamu: {names}. Dokud se znovu nespustí, nevypnu.",
        "btn_feedback": "✉  Zpětná vazba",
        "feedback_bug": "Nahlásit problém…",
        "feedback_idea": "Navrhnout vylepšení…",
        "feedback_email": "Napsat e-mail ({email})",
        "feedback_mail_subject": "{app} – zpětná vazba",
        "feedback_mail_body": "Dobrý den,\n\n\n\n---\nSystém: {env}\n",
        "btn_help": "?  Nápověda",
        "help_title": "Nápověda",
        "help_close": "Zavřít",
        "help_text": """# Co aplikace hlídá
Aplikace hlídá frontu stahování ve Steamu: hry, které se právě stahují, i hry, které čekají ve frontě připravené ke stažení. Prochází všechny tvoje knihovny Steamu na všech discích.

# Kdy dojde k vypnutí
Až když se celá fronta vyprázdní. Po dokončení posledního stahování aplikace ještě počká nastavenou dobu („Počkat bez stahování“), kdyby Steam začal stahovat něco dalšího. Pak se objeví okno s odpočtem a po jeho skončení se počítač vypne, uspí nebo restartuje – podle toho, co sis vybral.

# Pozastavené stahování
Když ve Steamu stahování pozastavíš, aplikace počítač nevypne. Počká, dokud stahování znovu nespustíš nebo ho nevyřadíš z fronty. Hry, které byly pozastavené už před spuštěním hlídání, se nepočítají, aby staré zapomenuté stahování neblokovalo vypnutí navždy.

# Průběh
Steam během stahování neaktualizuje své soubory, jen když stahování začne, pozastaví se nebo skončí. U hry, která se právě stahuje, proto aplikace ukazuje odhad označený „~“ spolu s rychlostí stahování. K poslednímu údaji ze Steamu přičítá, co Steam přijal po síti. Odhad se může trochu lišit – na Windows a Linuxu se počítá i jiný síťový provoz – a přesný údaj se objeví, jakmile ho Steam zapíše.

# Zrušení
Kdykoli můžeš zrušit: v okně s odpočtem tlačítkem Zrušit (nebo klávesou Esc), případně v hlavním okně tlačítkem Zastavit hlídání.

# Zkušební režim
Se zapnutým zkušebním režimem se nic nevypne – uvidíš jen odpočet a zprávu, co by se stalo. Hodí se na vyzkoušení.

# Tipy
• Nech Steam zapnutý – aplikace jen čte soubory Steamu, sama nic nestahuje.
• Zkontroluj, že se počítač neuspí sám dřív, než stahování skončí (nastavení napájení ve Windows).
• Sloupec „Stav“ ukazuje přesně to, co Steam u hry hlásí. Vysvětlivky uvidíš po najetí myší na „(?)“ v záhlaví.

# Problémy a nápady
Narazil jsi na chybu nebo máš nápad? Klikni nahoře v hlavním okně na „Zpětná vazba“. Můžeš to nahlásit na GitHubu (formulář už obsahuje verzi tvého systému), nebo napsat e-mail na jan.ambroz.91@gmail.com. Díky!""",
        "sub_off": "Klikni na Spustit hlídání a nech Steam stahovat.",
        "sub_waiting": "Zatím se nic nestahuje. Spusť stahování ve Steamu.",
        "sub_downloading": "Aktivních stahování: {n}. Zasáhnu, až všechna skončí.",
        "sub_verifying": "Ověřuji, že Steam nezačne stahovat něco dalšího.",
        "sub_countdown": "V okně s odpočtem ho ještě můžeš zrušit.",
        "dlg_seconds": "sekund",
        "dlg_title": "{left} s – {action}",
        "btn_start": "▶  Spustit hlídání",
        "btn_stop": "■  Zastavit hlídání",
        "badge_test_mode": "ZKUŠEBNÍ REŽIM",
        "footer_question": "Nemusel ti díky aplikaci počítač zbytečně běžet celou noc?",
        "btn_donate": "☕  Podpořit na Ko-fi",
        "libs_found": "Nalezeno knihoven: {n}",
        "steam_not_found": "Steam nebyl nalezen.\nVyber jeho složku tlačítkem níže.",
        "choose_folder_title": "Vyber složku, kde je nainstalovaný Steam",
        "choose_folder_first": "Nejdřív vyber složku Steamu.",
        "preparing": "připravuje se",
        "status_downloading": "Hlídám… stahování probíhá.",
        "status_waiting": "Hlídám… čekám, až nějaké stahování začne.",
        "status_verifying": "Stahování skončilo, ověřuji… ještě {left} s.",
        "status_countdown": "Probíhá odpočet…",
        "status_cancelled": "Akce byla zrušena. Hlídání je vypnuté.",
        "status_dry_run": "Zkušební režim: teď by se provedla akce „{action}“.",
        "msg_dry_run": "Zkušební režim – nic se nevypnulo.\n\nSpustil by se příkaz:\n{cmd}",
        "status_executing": "Provádím akci…",
        "return_code": "návratový kód {code}",
        "msg_action_failed": "Akci se nepodařilo provést:\n{error}",
        "status_action_failed": "Akci se nepodařilo provést.",
    },
}

_current = DEFAULT_LANGUAGE


def set_language(lang):
    """Set the language; an unknown code falls back to the default."""
    global _current
    _current = lang if lang in STRINGS else DEFAULT_LANGUAGE


def get_language():
    return _current


def t(key, **kwargs):
    """Translated text; a missing translation falls back to English, then to the key."""
    text = STRINGS[_current].get(key) or STRINGS[DEFAULT_LANGUAGE].get(key, key)
    return text.format(**kwargs) if kwargs else text


# --- Saved settings ---------------------------------------------------------
def settings_path():
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming")
        return base / "SteamAutoShutdown" / "settings.json"
    if system == "Darwin":
        return Path.home() / "Library/Application Support/SteamAutoShutdown/settings.json"
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "steam-auto-shutdown" / "settings.json"


def load_saved_language():
    """The last chosen language, or the default (en)."""
    try:
        lang = json.loads(settings_path().read_text(encoding="utf-8")).get("language")
    except (OSError, ValueError, AttributeError):
        return DEFAULT_LANGUAGE
    return lang if lang in STRINGS else DEFAULT_LANGUAGE


def save_language(lang):
    """Save the language to settings.json; a write error never crashes the app."""
    path = settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    data["language"] = lang
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass

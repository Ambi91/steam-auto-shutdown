# Privacy Policy

*Last updated: 22 November 2026*

Auto Shutdown for Steam ("the app") is made by Jan Ambrož. This policy explains what
the app does with your data. In short: **it collects nothing and sends nothing.**

## What the app reads

- Steam's own files on your computer (`libraryfolders.vdf` and
  `appmanifest_*.acf` in your Steam libraries) to see which games are
  downloading, and Steam's download log (`logs/content_log.txt`) to see which game
  is downloading right now. They are only read, never changed, and never leave your
  computer.
- How many bytes have been received over the network (by Steam's processes on macOS,
  by all network interfaces on Windows and Linux), to estimate download progress and
  speed. Only these totals are read – never what is downloaded, from where, or any
  other traffic details – and they are not stored or sent anywhere.
- On Windows, the Steam installation path from the Windows registry.

## What the app stores

- Your chosen interface language, in a small settings file on your computer
  (`%APPDATA%\SteamAutoShutdown\settings.json` on Windows). Nothing else is saved.

## What the app sends

- Nothing. The app makes no network connections, has no analytics, no
  advertising and no accounts.
- If you click **Support on Ko-fi**, your web browser opens
  https://ko-fi.com/ambi91. What happens there is covered by
  [Ko-fi's privacy policy](https://more.ko-fi.com/privacy).

## Power actions

When downloads finish, the app runs your operating system's standard command to
shut down, sleep or restart the computer, only if you started watching.

## Children

The app collects no personal information from anyone, including children.

## Changes and contact

Changes to this policy are published at
https://github.com/Ambi91/steam-auto-shutdown/blob/main/PRIVACY.md.
Questions: open an issue at https://github.com/Ambi91/steam-auto-shutdown/issues.

---

Auto Shutdown for Steam is not affiliated with, endorsed by or sponsored by Valve
Corporation. Steam and the Steam logo are trademarks of Valve Corporation.

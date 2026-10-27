# AmneziaDashboard 1.3.0 — AmneziaWG profiles / Конфиги AmneziaWG

One issued guest, two formats:

- **AmneziaVPN**: the original .vpn and vpn:// key remain unchanged.
- **AmneziaWG**: a standalone .conf using the same keys, address, endpoint and AWG 3.1 parameters. DNS placeholders are resolved for standalone import.
- **iPhone/iPad**: explicit app choice, AmneziaVPN marked recommended, and the official AmneziaWG Russian App Store link.
- **Android, Windows, macOS and Linux**: alternative options remain collapsed.
- Administrator .conf downloads and capability-based invitation file sharing have manual import fallbacks. There is no invented deep link or third-party profile relay.

Добавлен экспорт .conf для AmneziaWG из того же гостевого профиля. Новый пир не создаётся; .vpn, ключи, срок, ручная пауза, квота и накопленный трафик сохраняются. На iPhone/iPad выбор приложений показан явно, на других ОС альтернатива свёрнута. Отозванные и защищённые старые профили не становятся доступными для скачивания.

Use a current AmneziaWG client supporting AWG 3.1; Apple 3.1.4 supports this generation. This is not a standard WireGuard configuration. A .conf contains a private client key: protect it like a password and do not use the same profile on several devices or enable both apps at once.

## Downloads / Скачать

- **AmneziaDashboardSetup.exe** — self-contained Windows 10/11 x64 installer, unsigned.
- **AmneziaDashboard.zip** — complete sanitized source.
- **Windows-licenses.zip** — bundled dependency/runtime notices.
- **SHA256SUMS** — verify files from this exact release.

[Русская инструкция](https://github.com/AstolfoSan/AmneziaDashboard/blob/v1.3.0/docs/INSTALL_RU.md) · [English guide](https://github.com/AstolfoSan/AmneziaDashboard/blob/v1.3.0/docs/INSTALL_EN.md)

360 automated tests and five engine-free Compose variants are checked. Russian/English iPhone-size previews use synthetic data. Existing guest conversion and the deployed backend API were checked without changing an issued peer; production API testing used a disposable DB/session copy and export-only RPC.

Physical mobile import and full clean-VPS installer acceptance remain pending. Changing the app does not repair a provider/network outage. Do not rerun the fresh installer over a working VPN: there is no automatic in-place updater.

No production addresses, credentials, databases, issued profiles or invitations are included. Publication itself does not install/update a server. Original code: MIT; third-party rights remain applicable.

[Official AmneziaWG app guidance](https://docs.amnezia.org/documentation/alternative-clients/) · [Russian App Store](https://apps.apple.com/ru/app/amneziawg/id6478942365)

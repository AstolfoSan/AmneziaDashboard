# AmneziaDashboard 1.1.1 — Download for your device / Загрузка для вашего устройства

Invitation pages now detect the device OS and show only relevant downloads by default:

- Android: APK and Google Play.
- iPhone/iPad: App Store, including iPadOS using a desktop-style browser.
- Windows, macOS and Linux: the matching official app download.
- Another device reveals other platforms; unknown OS retains manual choices.

На пригласительной странице теперь показывается загрузка для ОС текущего устройства. Остальные варианты спрятаны под «Другое устройство». Определение выполняется локально, без стороннего сервиса; ничего не скачивается и профиль не создаётся автоматически.

Latest stable upstream resolution, manual import, issued configs, subscriptions, keys, database and lifetime counters are unchanged. Russian and English are supported; invitation screenshots are updated.

## Downloads / Скачать

- **AmneziaDashboardSetup.exe** — self-contained Windows 10/11 x64 setup, unsigned.
- **AmneziaDashboard.zip** — complete source package.
- **Windows-licenses.zip** — bundled dependency/runtime notices.
- **SHA256SUMS** — verify files from this same release.

[Русская инструкция](https://github.com/AstolfoSan/AmneziaDashboard/blob/v1.1.1/docs/INSTALL_RU.md) · [English guide](https://github.com/AstolfoSan/AmneziaDashboard/blob/v1.1.1/docs/INSTALL_EN.md)

327 automated tests and five engine-free Compose variants are checked. Browser QA uses synthetic data; physical phone acceptance and full clean-VPS provisioning remain pending. Do not rerun the fresh installer over a working VPN. There is no automatic in-place updater.

This publication does not change live servers. No production addresses, credentials, databases, issued profiles or invitations are included. Original code: MIT; third-party rights remain applicable.

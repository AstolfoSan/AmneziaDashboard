# AmneziaDashboard 1.2.0 — A familiar setup / Установщик в стиле дашборда

The Windows wizard now follows the dashboard's visual language:

- Rounded dark cards, the original dashboard icon and blue/purple/orange accents.
- Clear direct/cascade selection and fields only for the selected SSH login method.
- Fixed main actions, slimmer scrolling, aligned tabs and a calmer progress view.
- Native dark title bar on supported Windows, with a matching EXE icon.
- Refreshed Russian/English setup screenshots and GUI regression coverage.
- Faster card repaints: large texture centres and native solid fills avoid thousands of tiny draw calls at HiDPI. Local DEMO window preparation is measured separately from cold EXE extraction; no fixed launch-time promise.
- Initial layout is prepared before the window appears; language/mode changes keep the previous view until the replacement is ready, avoiding visible piece-by-piece assembly.
- Personal invitation guide without marketing slogans; profile retrieval is part of step two on every screen size.

Windows-мастер теперь оформлен как дашборд: скруглённые карточки, фирменные оттенки и значок, аккуратные поля, фиксированные кнопки и более понятные шаги. Способ входа показывает только нужные поля, а переключение языка и режима не теряет введённые значения. Обе инструкции обновлены свежими снимками DEMO.

No new UI dependencies. Host-key verification, explicit plan and CA consent, backups, verified official downloads and DEMO safeguards are unchanged. This is not a provisioning-engine update and does not install or update any live server.

## Downloads / Скачать

- **AmneziaDashboardSetup.exe** — self-contained Windows 10/11 x64 setup, unsigned.
- **AmneziaDashboard.zip** — complete source package.
- **Windows-licenses.zip** — bundled dependency/runtime notices.
- **SHA256SUMS** — verify files from this same release.

[Русская инструкция](https://github.com/AstolfoSan/AmneziaDashboard/blob/v1.2.0/docs/INSTALL_RU.md) · [English guide](https://github.com/AstolfoSan/AmneziaDashboard/blob/v1.2.0/docs/INSTALL_EN.md)

340 automated tests and five engine-free Compose variants are checked. Native Windows QA uses synthetic data; physical phone acceptance and full clean-VPS provisioning remain pending. Do not rerun the fresh installer over a working VPN. There is no automatic in-place updater.

This publication does not change live servers. No production addresses, credentials, databases, issued profiles or invitations are included. Original code: MIT; third-party rights remain applicable.

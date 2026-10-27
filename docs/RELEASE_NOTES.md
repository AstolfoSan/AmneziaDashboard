# AmneziaDashboard 1.3.2 — Existing-client QR / QR в списке клиентов

- **QR** beside .vpn/.conf in client rows opens a read-only dialog for an already issued profile.
- Select **AmneziaVPN (.vpn)** or **AmneziaWG (.conf)**. The original authorized export is encoded locally; no second client, replacement key or external QR service.
- Requests are authenticated, no-store and bounded. Format caching lives only in the open dialog. Close/Escape/pagehide clears the SVG and cache and aborts unfinished exports.
- Late responses cannot redraw a closed or replaced dialog. Legacy, pending, error, revoked and out-of-scope clients stay protected.
- Russian/English instructions and synthetic screenshots are included. Access pause, expiry, traffic quota and lifetime counters are unchanged.

В списке клиентов появилась кнопка **QR** рядом с **.vpn** и **.conf**. Выберите приложение в окне и считайте код сканером внутри AmneziaVPN или AmneziaWG. Повторная выдача профиля не нужна. QR содержит приватный ключ: не публикуйте его; после импорта закройте окно.

## Downloads / Скачать

- **AmneziaDashboardSetup.exe** — self-contained Windows 10/11 x64 installer, unsigned.
- **AmneziaDashboard.zip** — sanitized source package.
- **Windows-licenses.zip** — bundled runtime/dependency notices.
- **SHA256SUMS** — verify files from this same release.

[Русская инструкция](https://github.com/AstolfoSan/AmneziaDashboard/blob/v1.3.2/docs/INSTALL_RU.md) · [English guide](https://github.com/AstolfoSan/AmneziaDashboard/blob/v1.3.2/docs/INSTALL_EN.md)

379 automated tests and five engine-free Compose variants passed locally. Administrator scope, repeated clicks, both formats, pause/expiry preservation, aborts, timeouts, stale responses, malformed/oversized payloads and private-key cleanup are covered. Independent ZXing decoding recovered exact expected synthetic bytes from both new browser screenshots.

Windows builds and frozen offline self-tests are required gates of the release workflow. The native installer GUI is unchanged from 1.2.0. Physical camera/application import and full clean-VPS direct/cascade acceptance remain pending. Do not run the fresh installer over an existing VPN; there is no automatic in-place updater.

No production addresses, credentials, databases, issued profiles or invitations are included. Documentation QR images are deliberately synthetic and do not connect to a VPN. Original code: MIT; all bundled and upstream third-party rights remain applicable.

# AmneziaDashboard 1.3.1 — Private QR import / Подключение по QR

- **Show QR code** appears below an issued profile. It encodes the original `vpn://` key for AmneziaVPN or the exact `.conf` for AmneziaWG.
- QR generation is browser-local using the bundled MIT Project Nayuki library. No QR service, CDN, external relay or stored QR image is involved.
- Switching apps replaces the code; closing or leaving the page clears its SVG. Stale export responses cannot display the wrong app's profile.
- If a full profile exceeds one QR's medium-correction capacity, file/key import remains available. No truncation, splitting, replacement peer or access-policy changes.
- Russian/English instructions and synthetic mobile screenshots are included.

После выдачи появилась кнопка **Показать QR-код**. Выберите приложение в первом шаге: QR будет для AmneziaVPN либо AmneziaWG. Он содержит приватный клиентский ключ — не публикуйте снимок и не передавайте его другим людям. Сканируйте внутри выбранного приложения с другого экрана; на том же телефоне удобнее импорт файла. Ключи, .vpn/.conf, сроки, паузы, квоты и накопленный трафик сохранены.

## Downloads / Скачать

- **AmneziaDashboardSetup.exe** — self-contained Windows 10/11 x64 installer, unsigned.
- **AmneziaDashboard.zip** — sanitized source package.
- **Windows-licenses.zip** — bundled runtime/dependency notices.
- **SHA256SUMS** — verify files from this same release.

[Русская инструкция](https://github.com/AstolfoSan/AmneziaDashboard/blob/v1.3.1/docs/INSTALL_RU.md) · [English guide](https://github.com/AstolfoSan/AmneziaDashboard/blob/v1.3.1/docs/INSTALL_EN.md)

369 automated tests and five engine-free Compose variants passed locally. Independent ZXing decoding recovered exact bytes from five synthetic matrices, including AWG 3.1, UTF-8 and a 2331-byte payload, and from both mobile browser screenshots. Physical camera/application import remains pending; generated QR correctness is not a claim of mobile-device or network acceptance.

Windows builds and frozen offline self-tests are required gates of the release workflow. The native installer GUI is unchanged from 1.2.0. Full clean-VPS direct/cascade acceptance remains pending; do not run the fresh installer over an existing VPN. There is no automatic in-place updater.

No production addresses, credentials, databases, issued profiles or invitations are included. QR images in the documentation are deliberately synthetic and do not connect to a VPN. Original code: MIT; bundled Project Nayuki license and all third-party rights remain applicable.

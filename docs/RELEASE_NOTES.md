# AmneziaDashboard 1.3.3 — QR import compatibility / Исправление импорта QR

- Fixed **AmneziaVPN on iPhone: Scanned 0 of 0**. QR now wraps the existing compressed guest profile in the app scanner's native frame, not a `vpn://` paste link. Original .vpn files, copied links and credentials remain unchanged.
- **AmneziaWG on iPhone** asks for a name after scanning; QR cannot set it automatically. The dialog shows the client name and **Copy name**. Download/share `.conf` files are named after the client, enabling file-based naming without changing config bytes.
- Larger desktop QR display, RU/EN guidance and reviewed synthetic screenshots. No new peers, key replacements, access-policy changes or counter resets.

Исправлен QR AmneziaVPN, который мог оставлять iPhone на **«0 из 0»**. Для AmneziaWG добавлены имя клиента и **Скопировать имя**: вставьте его в запрос приложения после сканирования. Для автоматического имени используйте `.conf` — файл теперь называется как клиент. Уже импортированные туннели сами не переименовываются.

## Downloads / Скачать

- **AmneziaDashboardSetup.exe** — self-contained Windows 10/11 x64 installer, unsigned.
- **AmneziaDashboard.zip** — sanitized source package.
- **Windows-licenses.zip** — bundled runtime/dependency notices.
- **SHA256SUMS** — verify files from this same release.

[Русская инструкция](https://github.com/AstolfoSan/AmneziaDashboard/blob/v1.3.3/docs/INSTALL_RU.md) · [English guide](https://github.com/AstolfoSan/AmneziaDashboard/blob/v1.3.3/docs/INSTALL_EN.md) · [Official parser references](https://github.com/AstolfoSan/AmneziaDashboard/blob/v1.3.3/docs/QR_COMPATIBILITY.md)

386 automated tests and five engine-free Compose variants passed locally. Native framing and decompression back to the original guest JSON are tested, not just QR symbol decoding. Independent ZXing recovered exact expected bytes from four synthetic matrices and three actual browser screenshots.

Windows builds and frozen offline self-tests are required release-workflow gates. The native installer GUI is unchanged from 1.2.0. **Physical iPhone camera/app re-testing is still required**, as is clean-VPS direct/cascade acceptance. Do not run the fresh installer over an existing VPN; there is no automatic in-place updater.

No production addresses, credentials, databases, issued profiles or invitations are included. Documentation QR images are synthetic and cannot connect to a VPN. Original code: MIT; bundled and upstream third-party rights remain applicable.

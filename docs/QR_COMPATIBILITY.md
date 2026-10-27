# QR compatibility / Совместимость QR

Version 1.3.3 corrects the AmneziaVPN QR transport. A paste link beginning
with `vpn://` is not the scanner's native QR payload. The old code could be
read by a QR decoder but leave the app showing **Scanned 0 of 0**.

The new code Base64URL-decodes the existing guest link and wraps its unchanged
qCompress bytes in a QDataStream-compatible frame: signed 16-bit magic 1984,
unsigned 8-bit total 1, unsigned 8-bit index 0, unsigned 32-bit byte length,
then the original bytes. Integers are big-endian; the frame is Base64URL
without padding. The official parser supports this single-frame envelope.
Nothing is added to the stored `.vpn`, copied link or WireGuard configuration.
Large profiles retain file/key import instead of being truncated.

В 1.3.3 исправлен формат QR AmneziaVPN, вызывавший **«Сканировано 0 из 0»**.
QR теперь содержит совместимый кадр с исходными сжатыми данными профиля,
а не ссылку для вставки. Выданный `.vpn`, ключи, адрес, срок и лимиты не меняются.

## Names in AmneziaWG for iPhone / Имена в AmneziaWG на iPhone

The official QR scanner asks the user to name the tunnel after scanning.
It does not read a tunnel name from wg-quick text. The dashboard therefore
shows the client's name and a **Copy name** button; paste it into that prompt.
No unsupported `Name =` field is inserted. Importing a downloaded/shared
`.conf` instead uses its filename: panel buttons now name that file after
the client, with unsafe filename characters replaced. Config contents and
keys are identical in both paths. Renaming a download does not rename an
already imported tunnel inside the app.

QR-сканер AmneziaWG на iPhone сам просит имя туннеля. Панель показывает имя
клиента и кнопку **Скопировать имя** — вставьте его в запрос приложения.
Если нужно автоматическое имя, используйте **.conf**: кнопки скачивания и
передачи приложению теперь сохраняют файл с именем клиента. Уже добавленный
туннель в приложении сам не переименуется.

## Primary references / Официальный код

- [AmneziaVPN 5.0.3.0 scanner and import parser](https://github.com/amnezia-vpn/amnezia-client/blob/5.0.3.0/client/core/controllers/selfhosted/importController.cpp)
- [AmneziaVPN frame generator](https://github.com/amnezia-vpn/amnezia-client/blob/5.0.3.0/client/core/utils/qrCodeUtils.cpp)
- [AmneziaWG Apple QR name prompt](https://github.com/amnezia-vpn/amneziawg-apple/blob/811f5c8213e6b257e9520fff713ec4d22086e9ac/Sources/WireGuardApp/UI/iOS/ViewController/QRScanViewController.swift)
- [AmneziaWG file importer](https://github.com/amnezia-vpn/amneziawg-apple/blob/811f5c8213e6b257e9520fff713ec4d22086e9ac/Sources/WireGuardApp/UI/TunnelImporter.swift)

Automated tests verify framing, decompression back to the original JSON,
exact wg-quick bytes, filename safety and scoped read-only UI behavior.
Independent ZXing decoding is an additional check, not physical iPhone
camera/application acceptance. Real-device re-testing remains required.

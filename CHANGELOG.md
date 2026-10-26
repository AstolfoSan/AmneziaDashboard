# Changelog

All user-visible changes are recorded here. Versions follow Semantic Versioning.

## [Unreleased]

### Planned / Запланировано

- Clean-VPS direct/cascade acceptance and real-device validation.
- Reviewed in-place upgrade/migration tooling; the installer remains fresh-only.

## [1.2.0] — 2026-10-27

### Improved / Улучшено

- Redesigned the Windows wizard to match the dashboard: rounded dark cards, original dashboard icon and blue/purple/orange accents.
- Clear route selection, focused password/SSH-key forms, fixed action bar, slim scrollbars and a quieter installation log.
- Matching dark native title bar on supported Windows versions, bundled EXE icon and refreshed RU/EN screenshots.
- Form values survive language, mode and advanced-options changes. Hidden authentication fields are retained in memory, not submitted for the other method.
- No new UI dependencies. SSH host approval, plan consent, backup workflow, DEMO safeguards and provisioning logic are unchanged.
- Local synthetic GUI checks cover both languages/modes, secret masking, no implicit CA consent, small-window scrolling and disabled controls.
- Larger nine-slice texture centres avoid thousands of tiny Tk blits per card repaint; minimum widget geometry stays unchanged, including at HiDPI.
- The initial window stays hidden until layout is complete. Language/mode/advanced changes prepare a replacement off-screen and keep the old view until the swap, avoiding visible widget-by-widget assembly.
- Windows is realised at zero opacity so its initial native Map/Configure and paint events finish before the complete view is revealed. The regression checks both SSH cards, final input geometry and the main action before visibility.
- Invitation pages use a compact personal setup guide instead of marketing slogans; profile issuance and import controls are inside step two, before the illustrated third step, on mobile and desktop.
- Работающие VPN, выданные профили, клиенты и серверная панель не изменяются.

## [1.1.1] — 2026-10-26

### Improved / Улучшено

- Invitation links detect Android, iPhone/iPad (including desktop-style iPadOS), Windows, macOS and Linux locally in the browser.
- Only downloads for the current OS appear by default. Android keeps both APK and Google Play; other platforms and compatibility help remain under Another device.
- Unknown/unsupported OS and unavailable JavaScript retain manual download options. Detection never starts downloads or issues VPN profiles automatically.
- Russian/English captions, updated invitation screenshots and nine regression tests.
- No VPN, credentials, database, lifetime meters or existing profile/subscription changes.

## [1.1.0] — 2026-10-26

### Added / Добавлено

- Russian/English web UI, public invitation guide, system errors and terminal wizard.
- Persistent browser language preference; user names, profile payloads and stored state are not translated.
- Self-contained Windows x64 GUI EXE with embedded Python, Tk and SSH/crypto dependencies.
- Direct/cascade setup forms, explicit host/plan approval and an optional official Windows client download with required SHA-256 verification.
- Detailed RU/EN installation and recovery guides with real synthetic-data screenshots in each language.
- Windows CI build, frozen offline self-test, dependency notices and release checksums for all assets.

### Compatibility / Совместимость

- No VPN keys, routes, protocol settings, issued profiles, database schema or lifetime-counter reset is introduced by localization.
- No automatic in-place updater; the provisioning wizard remains fresh-only.
- Full clean-VPS/direct/cascade and real-device acceptance remain pending.

## [1.0.0] — 2026-10-26

### Added / Добавлено

- Initial public source package with MIT license and Russian/English installation guides.
- Direct/cascade terminal setup with verified SSH, recovery snapshots and explicit approval.
- Personal `.vpn` exports, native import/copy controls and screenshot-based key instructions.
- Administrator/group/device hierarchy, scoped access and audit trail.
- Pausing, expiry, default group duration and traffic quotas without replacing profiles.
- Persistent lifetime counters and bounded hourly/daily traffic history.
- Official APK, Google Play, App Store, Windows, macOS and Linux download links.
- Super-administrator password reset without an old password, with target-session invalidation.
- Privacy checks, CI configuration, reproducible source archives and release checksums.

### Validation / Проверка

- Local automated checks are distinct from real clean-VPS deployment acceptance.
- The installer has not yet completed that clean-VPS acceptance; see VALIDATION.json.
- No production server or existing VPN profile is included in this repository.

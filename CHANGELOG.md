# Changelog

All user-visible changes are recorded here. Versions follow Semantic Versioning.

## [Unreleased]

### Planned / Запланировано

- Clean-VPS direct/cascade acceptance and real-device validation.
- Reviewed in-place upgrade/migration tooling; the installer remains fresh-only.

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

# Changelog

All user-visible changes are recorded here. Versions follow Semantic Versioning.

## [Unreleased]

### Planned / Запланировано

- English interface localization (not included in 1.0.0).
- Clean-VPS direct/cascade acceptance and real-device validation.
- Reviewed in-place upgrade/migration tooling; the installer remains fresh-only.

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

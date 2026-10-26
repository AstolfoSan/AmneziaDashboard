# AmneziaDashboard 1.0.0 / Первый публичный исходный релиз

Independent self-hosted AmneziaWG dashboard with personal `.vpn` exports,
administrator/group/device hierarchy, lifetime traffic, charts, access pause,
expiry and traffic quotas. Includes the current dashboard UI and an interactive
fresh-VPS direct/cascade installer, plus Russian and English installation guides.
The interface and terminal wizard are currently Russian-only.

Панель выдачи `.vpn`, администраторы и группы, статистика, пауза, сроки и лимиты.
Включены свежий интерфейс, инструкция со скриншотами и мастер прямой/каскадной
установки. Документация — RU/EN; интерфейс — пока русский.

## Downloads / Скачать

- **AmneziaDashboard.zip** — complete source installer package; requires Python 3.12+.
- **SHA256SUMS** — verify the archive before extracting/running it.

Read `docs/INSTALL_RU.md` or `docs/INSTALL_EN.md` in the package. No credentials,
production databases, private profiles or server backups are included.

> **Fresh-VPS acceptance is still pending.** This release number does not turn
> mock/local regression tests into a clean-Linux deployment test. Use separate
> test VPSs first; never run the fresh installer over an existing production VPN.
> Existing deployments require a reviewed backup and migration plan, not a rerun.

Original code is MIT licensed; third-party licenses/rights remain unchanged.

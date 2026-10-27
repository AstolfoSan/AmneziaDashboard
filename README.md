<div align="center">
  <img src="installer/portable/app/static/dashboard-icon.svg" width="88" height="88" alt="AmneziaDashboard logo">
  <h1>AmneziaDashboard</h1>
  <p>A clear home for your self-hosted VPN.</p>
  <p><strong>Profiles · People · Traffic · Access</strong></p>
  <p><a href="README_RU.md">Русский</a> · English · <a href="docs/INSTALL_EN.md">Installation</a> · <a href="https://github.com/AstolfoSan/AmneziaDashboard/releases">Downloads</a></p>
  <img alt="Version 1.3.0" src="https://img.shields.io/badge/version-1.3.0-F6A453">
  <img alt="MIT License" src="https://img.shields.io/badge/license-MIT-9B8BC1">
  <img alt="Self hosted" src="https://img.shields.io/badge/self--hosted-AmneziaWG-7EBAD2">
</div>

## Your server. Your connections.

AmneziaDashboard is an independent web dashboard for a compatible **AmneziaWG 3.1**
VPN. Create personal `.vpn` profiles for AmneziaVPN and `.conf` profiles for AmneziaWG, organize
devices by administrator and group, and understand usage without editing configs
by hand. It is not an official Amnezia product or a VPN subscription service.

> [!IMPORTANT]
> **1.3.0 identifies this source/package release, not completed fresh-VPS acceptance.**
> The dashboard has automated regression tests. The new direct/cascade installer
> still needs end-to-end acceptance on clean Ubuntu VPSs and real client devices.
> Do not run it over an existing production VPN. See [validation](VALIDATION.json).

### What is included

- One guest identity: `.vpn` for AmneziaVPN or `.conf` for AmneziaWG, with the same access policy.
- iPhone/iPad: explicit app choice and an official Russian App Store AmneziaWG option. Other OS alternatives remain collapsed.
- Device-aware app downloads: Android, iPhone/iPad, Windows, macOS and Linux; other systems stay collapsed.
- Super-administrator → administrator → group → device hierarchy.
- Invitations, per-device access pause, expiry and total traffic limits.
- Default access duration for newly issued group profiles.
- Lifetime device counters and group/administrator traffic totals.
- Rolling 1/6/24-hour charts; 7/31 completed-day views with bounded retention.
- Session-based login, role isolation, CSRF/Origin checks and readable audit events.
- A step-by-step terminal installer: **direct** or **two-server cascade**.
- A dashboard-styled Windows wizard: rounded cards, matching accents and focused password/key forms.
- A restricted SSH worker; the web app does not receive a Docker socket.

The web dashboard, Windows setup and terminal wizard support **Russian and English**.
Switch languages in the interface or use `--lang en` / `--lang ru` in the terminal.

![English dashboard with synthetic data](docs/images/dashboard-en.png)

## Choose your route

| Mode | Client traffic | Where the panel runs |
| --- | --- | --- |
| Direct | Device → VPN server → Internet | The same server |
| Cascade | Device → entry server → exit server → Internet | The exit server |

One dashboard manages one VPN entry. Cascade mode uses a separate inter-server
AWG tunnel carried over mutually authenticated TLS. It is not automatic
multi-exit selection, and it does not import an existing fleet of servers.

## Install

Use a **fresh Ubuntu 24.04 VPS** (two for cascade), public IPv4, root SSH access,
`/dev/net/tun`, at least 1 GB RAM and 3 GB free disk per host. The currently
supported upstream image architecture must be available; start with amd64.
Windows 10/11 x64: download the self-contained EXE; no Python installation is needed.
Linux/macOS or source mode: use Python 3.12+ on the operator computer.

1. Download [**AmneziaDashboardSetup.exe**](https://github.com/AstolfoSan/AmneziaDashboard/releases/latest/download/AmneziaDashboardSetup.exe) for Windows, or the source ZIP from Releases.
2. Verify its SHA-256 using **SHA256SUMS from the same release**.
3. Follow the illustrated steps in [English](docs/INSTALL_EN.md) or [Русский](docs/INSTALL_RU.md).
4. Open the EXE, choose a language and direct/cascade mode, then enter the new VPS details. Source alternative: `python installer/cli.py --lang en`.
5. Verify SSH fingerprints, approve the exact plan and keep the private recovery
   directory on your own computer. Never upload it to GitHub.

The installer checks official upstream releases at installation time and pins
selected image digests/commits. It does **not** silently update running servers.
There is no `curl | bash` command and no requirement to paste SSH credentials
into a website.

## Updates and releases

New versions are published as immutable version tags and GitHub Releases.
The stable source asset keeps the name **AmneziaDashboard.zip**, with a
**SHA256SUMS** file. A fixed latest-download URL is documented in
[release maintenance](docs/RELEASING.md). Installing a new package is **not** a
safe in-place database/VPN upgrade: existing deployments need a reviewed backup
and migration plan. Never rerun the fresh-install wizard over them.

## Documentation

- [Installation: English](docs/INSTALL_EN.md) / [Установка: Русский](docs/INSTALL_RU.md)
- [Architecture and security](docs/ARCHITECTURE.md)
- [Changelog](CHANGELOG.md) · [Validation status](VALIDATION.json)
- [Security reporting](SECURITY.md) · [Contributing](CONTRIBUTING.md)
- [Release checklist](docs/RELEASING.md) · [Third-party notices](THIRD_PARTY_NOTICES.md)

## Development

```sh
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r installer/requirements.txt -r installer/portable/app/requirements.txt
python tools/check.py
```

Node.js 20+ is required for the JavaScript tests. No server credentials are
needed for local checks. Checks never install a VPN on a real VPS.

## License and privacy

Original dashboard and installer code: [MIT](LICENSE). Third-party software,
trademarks and application screenshots retain their own rights; see the notices.
Examples use documentation-only addresses. Releases contain no production
database, issued profiles, private keys, invitation tokens or server backups.
Do not attach these to issues, pull requests or support messages.

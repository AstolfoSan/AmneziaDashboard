# Installing AmneziaDashboard 1.0.0

[Русский](INSTALL_RU.md) · [Home](../README.md)

> [!WARNING]
> This wizard is **fresh-VPS only**, not an upgrade for an existing VPN.
> Full clean-VPS direct/cascade acceptance is still pending. Use separately
> allocated test VPSs first, not your only production deployment.

## 1. Requirements

Each VPS needs Ubuntu 24.04, systemd, public IPv4, root SSH and `/dev/net/tun`.
Minimum 1 GB RAM / 3 GB free disk; 2 GB / 5 GB is recommended for image builds
and backups. Use amd64 unless the official AWG image offers the architecture
you need. Home routers and NAT-port-forwarding setups are not supported.

- **Direct:** one VPN server, with the dashboard on the same host.
- **Cascade:** an entry VPS and a separate exit VPS; the dashboard runs on the exit.
- Your operator computer needs Python 3.12+ and access to GitHub/PyPI and the
  official Docker, Ubuntu, Amnezia and Let's Encrypt sources.
- Have the root SSH password or private key ready (not a `.pub` file), plus a
  fallback provider-console login.

Open the required ports in the **provider's firewall** yourself:

| Host | Default port | Purpose |
| --- | --- | --- |
| Every VPS | TCP 22, or your SSH port | Administration |
| VPN entry | UDP 39265 | AmneziaVPN clients |
| Dashboard/exit | TCP 10443 | Dashboard HTTPS |
| Dashboard/exit | TCP 80 | HTTP-01 and certificate renewal |
| Exit, cascade only | TCP 443 **from the entry IPv4 only** | Inter-server TLS |

In direct mode, entry and dashboard are the same host. The wizard can change
ports if they are free. Keep TCP 80 reachable for renewal. It does not change
the provider's control-panel firewall settings.

## 2. Download and verify

Download **AmneziaDashboard.zip** and **SHA256SUMS** from the same
[GitHub release](https://github.com/AstolfoSan/AmneziaDashboard/releases).
Check the repository is exactly `AstolfoSan/AmneziaDashboard`.

Windows PowerShell:

```powershell
Get-FileHash .\AmneziaDashboard.zip -Algorithm SHA256
```

Linux:

```sh
sha256sum -c SHA256SUMS
```

On macOS, run `shasum -a 256 AmneziaDashboard.zip` and compare with SHA256SUMS.
Do not run files if the hash differs. Extract the entire archive and open a
terminal in the **AmneziaDashboard** directory containing VERSION.

## 3. Start the terminal wizard

### Windows 10/11

Install Python 3.12+ from the official Python website, then:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r installer\requirements.txt
.\.venv\Scripts\python.exe installer\cli.py --self-test
.\.venv\Scripts\python.exe installer\cli.py
```

No venv activation or ExecutionPolicy change is needed. If a release also
provides **AmneziaDashboardSetup.exe**, it is an optional frozen build that
does not need Python; verify its own SHA-256 first. It is unsigned. Any Windows
security-warning decision belongs to the user; the installer does not bypass it.

### Linux / macOS

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r installer/requirements.txt
.venv/bin/python installer/cli.py --self-test
.venv/bin/python installer/cli.py
```

Linux may need the venv package for your Python version. Run the wizard on
your operator computer; it connects to the VPSs over SSH.
The interactive wizard is currently **Russian-only**. Use this prompt guide:

| Prompt | Meaning |
| --- | --- |
| Режим: 1 — каскад, 2 — только зарубежный | 1 = two-server cascade, 2 = direct |
| Зарубежный VPS | Exit/dashboard host |
| RU-вход каскада | Entry host; only needed in cascade mode |
| Публичный IPv4 / SSH-порт | Public IPv4 / SSH port |
| 1 — пароль root, 2 — приватный SSH-ключ | Root password or private-key file |
| да / нет | yes / no; the default is no |
| Отпечаток | SSH host-key fingerprint; verify independently |
| УСТАНОВИТЬ | Exact confirmation word to start the approved changes |

## 4. Review and approve

1. Select direct or cascade mode and enter the exit host's SSH details.
   Cascade also asks for the entry host. Password input is hidden and is never
   placed in command-line arguments.
2. Change ports if necessary.
3. Read the Let's Encrypt terms and explicitly accept only if you agree.
   The panel IP will be sent to the CA and entered in public Certificate
   Transparency logs.
4. Verify each SSH fingerprint using the provider console or a previously
   trusted connection. Stop on a mismatch; do not disable host-key checks.
5. Read the exact plan and type **УСТАНОВИТЬ**. Changes do not start before approval.

The wizard inventories hosts, creates verified local before-snapshots, installs
dependencies/Docker, and creates the VPN, panel and restricted worker. It
resolves official upstream versions again and pins selected commits/digests.
Its READY state requires its live gates to pass; that is not an independent
security audit or the missing clean-VPS release acceptance.

It refuses existing deployment paths, containers, VPN interfaces, incompatible
routing or occupied required ports. Never delete another service to bypass a refusal.

## 5. First login and profiles

The final output shows the HTTPS panel address, **owner** login and private
directory containing **result-private.json** with the initial password.
Open that file locally yourself, sign in and change the password. Never attach
it to a public issue or support chat.

Create an administrator if needed, then a group and personal profile. Clients
install official AmneziaVPN and use `.vpn` or the add-to-app button. Manual key
import is **Copy key → plus in AmneziaVPN → Paste → confirm → Connect**.
Use one profile per device.

Pause, expiry and traffic quotas preserve a profile for later reuse. Revocation
is different. Closing an administrator's dashboard account does not by itself
disconnect previously issued VPN profiles.

## 6. Recovery and private files

Default session paths:

- Windows: `%LOCALAPPDATA%\AmneziaDashboardInstaller\sessions\<id>`.
- Linux/macOS: `~/.local/share/AmneziaDashboardInstaller/sessions/<id>` if
  LOCALAPPDATA is unset.
- Override with `--home` to choose a private local directory.

Plans, stage journals, before/after archives and the initial password live
there. Root-only copies also remain under `/root/amnezia-dashboard-installer-<id>`
on the VPSs. These are **secrets**, not release source: keep them outside GitHub
and public storage, with restrictive permissions and a protected off-host copy.

A before-snapshot is not a complete disk image. Stop/rollback is ownership-scoped
and best-effort; lost SSH can prevent cleanup. After failure, do not rerun the
wizard over partial state. Preserve the private journal, inspect the exact stage
and prepare a recovery plan. Never restore an old database over newer clients
or counters. Use Ctrl+C and wait for the current stage to finish when stopping.

## 7. Future versions

Use GitHub Releases, check the version and verify SHA256SUMS. A new source
archive is suitable for a **new** installation. An existing deployment requires
a verified backup, changelog review and compatible migration plan first.
Automatic in-place production upgrades are **not implemented** in 1.0.0.

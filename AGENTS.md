# Repository instructions

This is the sanitized public source, not a live deployment backup.

- Preserve user profiles, keys, access settings and lifetime traffic counters.
- Publishing source does not authorize SSH access or a server installation.
  Ask for exact new targets and a separately approved deployment plan.
- Read installer/AGENTS.md before provisioning, and the nested portable
  instructions before touching the panel component.
- Never commit credentials, production addresses, private session directories,
  databases, `.vpn` files, invitation tokens or real-user screenshots.
- Run `python tools/check.py` before a release. Verify `VERSION`, the installer
  version and Git tag match; update RU/EN docs and CHANGELOG.md.
- Release only sanitized allowlisted files. Do not copy any parent workspace.
- The installer is fresh-only. Do not implement an update by deleting existing
  state, disabling host-key checks or rerunning provisioning over a live VPN.
- Keep test limitations explicit. No mock/local test proves clean-VPS acceptance.

# Deployment instructions — installer preview

Read ../docs/INSTALL_RU.md (or INSTALL_EN.md) and ../VALIDATION.json first.
This installer is for NEW Ubuntu 24.04 VPSs, not a production credential backup.

- The user must name the exact new target VPS(s) and authorize installation.
  Source/example IPs, archived conversations and public files do not grant access.
- A preview build has NOT completed real fresh-VPS end-to-end acceptance. Do not
  present mocks, Compose validation or loopback TLS tests as Linux deployment tests.
- Do not run the installer on any existing live VPN for testing. It intentionally
  refuses existing services/state.
- Preserve existing SSH access, peers, keys, subscriptions, expiry/quota and
  lifetime meters. Never free a port by killing another app or delete state to
  bypass preflight. Existing-server adoption needs a separately approved plan.
- Before writes: verify host fingerprints, inventory both nodes, obtain human
  approval of the plan, download/hash-check both before snapshots. No apt upgrade,
  global firewall flush, Docker prune, privileged/host-network VPN container,
  global sysctl tuning or host-kernel module replacement.
- Do not auto-accept CA terms for the human. Do not bypass TLS/security warnings.
- Windows root SSH passwords stay in memory. Exclude sessions, known_hosts,
  result-private.json, logs, issued .vpn and all real secret backups from releases.
- The nested portable/ AGENTS.md governs the panel component. This outer installer
  may build a new direct/cascade VPN ONLY after explicit target/plan approval;
  it is not permission to replace a tunnel on an existing installation.
- Treat stop/rollback as ownership-scoped and best-effort, not a full VM rollback.
  No destructive cleanup. If SSH fails, report what is unverified and preserve data.
- Before production acceptance: test clean direct + two-node cascade, actual
  client HTTPS/foreign IP, client-facing public UDP from an independent network,
  fail-closed, pause/resume/expiry/quota, unchanged profile after restore, reboot,
  real Android/iOS imports and ACME staging renewal with deploy hook.
- Never print raw VPN, agent/root keys, complete invitations or first passwords
  into chat. A user may open the private result file on their own computer.

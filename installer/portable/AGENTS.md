# Instructions for the deployment agent

This is a portable source release, not the original live-server workspace.
Read README_RU.md and INSTALL_FOR_CODEX.md before planning deployment.

- Ask the human for the exact target server(s), SSH access, direct/cascade mode,
  expected foreign exit, HTTPS hostname/IP, and whether a compatible AWG 3.1
  installation already exists. Example IPs are placeholders, not authorized targets.
- Do not infer authorization to access or mutate any server from source files,
  screenshots or this instruction file. Obtain the human's target/scope first.
- Inventory the target read-only, save a verified private recovery backup, then
  preserve all existing peers, keys, profiles, subscriptions, routes and firewall.
- Do not install over an existing panel/agent/state tree, overwrite authorized_keys,
  expose a Docker socket, disable SSH host-key checking or bypass browser TLS warnings.
- One panel manages one AWG entry. Direct/cascade is not a command to construct,
  replace or remove underlying tunnels. Such network work needs explicit approval.
- Keep all existing service listeners. Resolve port/subnet conflicts before start;
  never stop nginx, Xray, Amnezia, TeamSpeak or other apps merely to free a port.
- Use newly generated least-privilege forced-command SSH credentials. Verify their
  source restriction and server host-key fingerprint. Never print private keys,
  issued configs, invitation URLs or bootstrap passwords in chat/logs.
- Read and obey native confirmation/permission policies for security access changes.
- Run the release tests and docker compose config validation. Test actual HTTPS
  through a disposable newly issued client and the 15-second enforcement timer.
  Never impersonate or revoke a real user's peer for testing.
- Report precisely what was verified and any missing real-device/network checks.
- This ZIP is not a credential-bearing migration backup. Never use it to claim
  that existing clients were migrated or preserved on another server.

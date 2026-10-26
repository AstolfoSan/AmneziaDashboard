# Security / Безопасность

## Supported version

Security fixes are developed against the latest published 1.x source release.
Fresh-VPS installer acceptance is still pending; this is not a security audit.

## Reporting a vulnerability

Do not open a public issue containing a working exploit, private key, password,
database, `.vpn`, invitation URL or production address. If this repository has
GitHub private vulnerability reporting enabled, use **Security → Report a
vulnerability**. Otherwise contact the maintainer through their GitHub profile
before sharing sensitive details. Private reporting availability must not be
assumed from this document alone.

Не публикуйте ключи, пароли, рабочие адреса, базы, `.vpn` или приглашения.
Используйте приватное сообщение об уязвимости в Security, если оно включено,
либо сначала договоритесь с владельцем репозитория о приватном канале.

## Threat boundaries

- The worker has narrowly scoped, source-restricted forced-command SSH access.
- The web container has no Docker socket and is not a general root shell.
- The host administrator, Docker daemon and root SSH remain trusted.
- TLS verification and host-key checking are never disabled for convenience.
- Download checksums detect mismatches; a checksum on the same compromised
  release page is not independent proof of authorship.
- Backups contain credentials. Encryption/ACLs and private off-host storage
  are the operator's responsibility.
- Exposing the panel publicly requires strong unique passwords, working TLS
  renewal, host maintenance and appropriate provider firewall rules.

# Release maintenance / Выпуск версий

The public repository is the canonical installation source:
`https://github.com/AstolfoSan/AmneziaDashboard`.
Never publish a whole private development/deployment workspace.

## Every version

1. Update `VERSION` and `installer/version.py` together using `MAJOR.MINOR.PATCH`.
2. Update CHANGELOG.md, both READMEs and RU/EN installation guides as needed.
3. Refresh the portable manifest using `python tools/manifest.py`.
4. Run `python tools/check.py` and `python tools/build_source.py --output dist`.
5. Review the source diff, privacy scan and ZIP members/checksums. PNG assets
   must be reviewed separately; never use real user tables in public screenshots.
6. Keep VALIDATION.json honest. Only mark fresh-VPS/device acceptance passed
   after actual direct/cascade, UDP, fail-closed, expiry/quota, restore and
   renewal/reboot checks on separately authorized test hosts.
7. Push the reviewed commit, then create tag `vMAJOR.MINOR.PATCH` at that commit.
8. The release workflow tests, builds and creates a **draft** release, so the
   maintainer can review artifacts before making the release public.
9. Verify draft assets and publish. Never replace assets on an old tag; fix
   defects in a new version. Do not use real names/emails in build metadata.

Only the release job receives `contents:write`; normal CI is read-only.
Third-party Actions are pinned to reviewed commit SHAs. Build artifacts contain
no deployment state. Upstream runtime releases are resolved separately at
installation; project release numbers do not claim an Amnezia protocol upgrade.

## Stable download links

- Release list: https://github.com/AstolfoSan/AmneziaDashboard/releases
- Latest stable release: https://github.com/AstolfoSan/AmneziaDashboard/releases/latest
- Source installer ZIP: https://github.com/AstolfoSan/AmneziaDashboard/releases/latest/download/AmneziaDashboard.zip
- Checksums: https://github.com/AstolfoSan/AmneziaDashboard/releases/latest/download/SHA256SUMS

Latest links only resolve when a non-draft stable release exists. They follow
future published stable releases because the source asset name remains fixed.
Checksums should always be downloaded from the **same release** as the archive.

## Existing installations

1. Inventory the live deployment and preserve a consistent private DB/worker/
   key/config backup outside the repository.
2. Read the exact version-to-version migration notes and verify compatibility.
3. Stage changed application files/images without changing peer identity,
   routes, bootstrap/master keys, credentials or client subscriptions.
4. Verify real client traffic and non-regressing lifetime counters before/after.
5. Roll back application code separately from newer DB state whenever possible.

There is no universal live updater in 1.0.0. Do not replace this process with a
second run of the fresh-VPS wizard. / Повторный запуск мастера не является
обновлением действующей установки.

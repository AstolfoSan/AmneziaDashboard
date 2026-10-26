# Contributing / Участие в разработке

Start with an issue describing the problem, without private server data.
Use synthetic examples and documentation IP ranges. Keep changes focused.

1. Create a branch and add tests for the changed behavior.
2. Install requirements from both `installer/requirements.txt` and
   `installer/portable/app/requirements.txt` in a virtual environment.
3. Use Node.js 20+ and run `python tools/check.py`.
4. Add a changelog entry; update both installation guides if behavior changes.
5. Never test provisioning against an existing production VPS.

Do not commit snapshots, sessions, credentials, personal identifiers, issued
profiles or screenshots of real user tables. A passing unit test is not a
clean-VPS/network acceptance test. Describe exactly what was tested in your PR.

Проверки и примеры должны быть на синтетических данных. Не прикладывайте
реальные конфиги, ключи, базы клиентов и журналы с адресами. Перед публикацией
выполните `python tools/privacy_check.py` и проверьте diff.

By contributing original work, you agree to license it under the project's MIT
license. Preserve third-party notices; do not copy incompatible licensed code.

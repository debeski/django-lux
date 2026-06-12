# Migrating from `django-microsys` to `django-lux`

`django-lux` (import package `dlux`) is the renamed successor to the now-archived
`django-microsys`. The framework is unchanged — only the brand. An existing
`django-microsys` database stores everything under the `microsys` app label
(`microsys_*` tables, `microsys` content types, `microsys.*` permission/log
keys); moving to `django-lux` is a one-time **relabelling**, not a schema change.

The `dlux_migrate_from_microsys` management command performs that relabelling
in place, without data loss.

## Prerequisites

- A **fully migrated `django-microsys` 2.4.1** database (all `microsys`
  migrations applied). Migrating from older versions is not supported — bring the
  deployment up to 2.4.1 on `django-microsys` first.
- **A fresh database backup.** This rewrites tables, content types, and
  migration history. Test on a copy first.

## Steps

1. **Back up the database.**

2. **Swap the package.**
   ```bash
   pip uninstall django-microsys
   pip install django-lux
   ```
   (Update `requirements.txt`/lockfiles accordingly.)

3. **Update your project code** (find/replace `microsys` → `dlux`):
   - `from microsys.utils import microsys_settings` → `from dlux.utils import dlux_settings`
   - `microsys_settings(globals())` → `dlux_settings(globals())`
   - `MICROSYS_CONFIG` → `DLUX_CONFIG`
   - `include("microsys.urls")` → `include("dlux.urls")`
   - any other `microsys` imports/references in your own code, templates, or
     settings.

4. **Preview the migration** (dry-run is the default — nothing changes):
   ```bash
   python manage.py dlux_migrate_from_microsys
   ```
   Review the table list and counts.

5. **Apply it:**
   ```bash
   python manage.py dlux_migrate_from_microsys --yes
   ```
   This renames every `microsys_*` table to `dlux_*`, repoints
   `django_content_type` (permissions follow automatically), records dlux's
   `0001_initial` as applied while dropping the old `microsys` migration history,
   and rewrites `UserActivityLog.model_key` values (`microsys.*` → `dlux.*`).

6. **Confirm and finish:**
   ```bash
   python manage.py migrate          # should report "No migrations to apply"
   python manage.py collectstatic --noinput
   # restart the app / workers
   ```

## Notes & caveats

- **Atomicity:** on PostgreSQL and SQLite the whole migration runs in one
  transaction. **MySQL auto-commits DDL**, so the steps are not rolled back
  together if one fails — your backup is your safety net there.
- **Index/constraint names:** existing indexes keep their original
  `microsys_*`/`ms_*` names. This is cosmetic and does not affect runtime; future
  `dlux` migrations that rebuild those objects will normalise the names.
- **Old `.msb` backups:** a system backup taken under `django-microsys` is a
  `.msb` whose payload is labelled `microsys.*`, so it will **not** restore into
  `django-lux` (which expects `dlux.*`). After migrating, take a fresh `.dlb`
  backup from `/sys/backup/`. To merely *inspect* an old `.msb`, use the archived
  `django-microsys` viewer.
- **Rollback:** restore the database backup from step 1 and reinstall
  `django-microsys`.

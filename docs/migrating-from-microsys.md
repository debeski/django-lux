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
   `django_content_type` (permissions follow automatically), creates any Dlux
   `0001_initial` tables missing from the source Microsys schema, records dlux's
   `0001_initial` as applied while dropping the old `microsys` migration history,
   and rewrites activity-log `model_key` values (`microsys.*` → `dlux.*`).

   The migration command retains the historical `UserActivityLog` wording in
   some console output for compatibility with the Microsys source schema. In
   current DjangoLux code the model is `ActivityLog`; `UserActivityLog` is only
   an import alias.

6. **Confirm and finish:**
   ```bash
   python manage.py migrate
   python manage.py collectstatic --noinput
   # restart the app / workers
   ```

   `migrate` should not recreate the relabelled framework tables, but it may
   apply newer `dlux` migrations released after the rebrand baseline, including
   the unified SystemSettings/notifications migration.

7. **Clear the old Django cache after updating (Compose/Redis deployments).**

   The generated Compose configuration uses Redis database `1` for Django's
   cache-backed sessions. After the package swap and database migrations are
   complete, clear that database before reopening the deployment to users:

   ```bash
   docker compose exec redis redis-cli -n 1 FLUSHDB
   ```

   A successful command prints `OK`. This removes cached objects created by the
   old package, including potentially incompatible serialized settings, but it
   also invalidates every active Django session and signs users out. Run it
   during the migration maintenance window, after `migrate` and before the final
   web/worker restart.

   Confirm your deployment's Django cache URL before running the command. Use
   the database number from `REDIS_URL_DB` if it is not `/1`, and do not flush a
   Redis database shared with another application. Use `FLUSHDB`, not
   `FLUSHALL`: the latter would also erase unrelated Redis databases such as the
   generated Celery broker/result databases (`2` and `3`). This operation does
   not alter PostgreSQL application data.

## Notes & caveats

- **Branding media (logo/favicon 404 after migrating):** django-microsys stored
  the system logo and favicon under `media/microsys/branding/`, while DjangoLux's
  `ImageField` upload path is `dlux/branding/`. The migration now rewrites those
  stored paths (`microsys/branding/*` → `dlux/branding/*`) and moves the files on
  the media storage as part of the main run. If you migrated with an older command
  version and the logo still 404s under `.../microsys/branding/…`, fix it in place:
  ```bash
  python manage.py dlux_migrate_from_microsys --repair-branding-media        # dry-run
  python manage.py dlux_migrate_from_microsys --repair-branding-media --yes
  ```
  The path is corrected even when the original file is absent (it was never copied
  into the new media volume) — in that case simply re-upload the logo/favicon in
  System Settings and it will land in the correct `dlux/branding/` path.
- **Older Microsys repair:** if an earlier command version was already run
  against a pre-2.4.x Microsys database and Dlux pages fail because tables such
  as `dlux_systembackup`, `dlux_reportbackup`, or `dlux_systemrestore` are
  missing, upgrade to a fixed DjangoLux build and run:
  ```bash
  python manage.py dlux_migrate_from_microsys --repair-missing-tables
  python manage.py dlux_migrate_from_microsys --repair-missing-tables --yes
  python manage.py migrate
  ```
- **Atomicity:** on PostgreSQL and SQLite the whole migration runs in one
  transaction. **MySQL auto-commits DDL**, so the steps are not rolled back
  together if one fails — your backup is your safety net there.
- **App translation dicts:** `django-lux` reads each app's translations from a
  `DLUX_STRINGS` dict in `translations.py`. The legacy `MS_TRANSLATIONS` name is
  still honoured as an inert fallback, so pre-rebrand apps keep loading their
  strings unchanged — but rename `MS_TRANSLATIONS` → `DLUX_STRINGS` at your
  convenience to drop the legacy alias. (Fresh `dlux startapp` scaffolds already
  emit `DLUX_STRINGS`.)
- **Index/constraint names:** a database migrated in place keeps its original
  `microsys_*`/`ms_*` index names, while fresh `django-lux` installs create them
  as `dlux_*`. This is cosmetic and does not affect runtime; a later
  `makemigrations` may surface a no-op index rename you can apply when convenient.
- **Old `.msb` backups:** a system backup taken under `django-microsys` is a
  `.msb` whose payload is labelled `microsys.*`, so it will **not** restore into
  `django-lux` (which expects `dlux.*`). After migrating, take a fresh `.dlb`
  backup from `/sys/backup/`. To merely *inspect* an old `.msb`, use the archived
  `django-microsys` viewer.
- **Rollback:** restore the database backup from step 1 and reinstall
  `django-microsys`.

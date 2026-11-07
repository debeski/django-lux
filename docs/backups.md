# Backups

DjangoLux backs up the whole system into `.dlb` files and restores them on the same
or another deployment. This page is the backup policy reference for operators and
developers. [Operations](operations.md#backup-and-restore) has the short day-to-day
summary, and the read-only [DLB viewer](../tools/dlb-viewer/README.md) opens a
`.dlb` offline.

Backups live on the superuser-only **Backup & Restore** page (`/sys/backup/`, opened
from **Options → Admin panel**). The policy is the **System Backup** step of the
setup wizard (step 18 of 19) and the same group in System Settings. It is stored in
`SystemSettings.backup_config`.

## What a backup contains

A backup is a snapshot of every concrete, managed model in the project. Rows are
written as Django JSON fixtures with natural foreign keys, in dependency order
(foreign-key and many-to-many targets before the rows that point at them).

These are never included:

- sessions, content types, permissions and admin log entries (`sessions.session`,
  `contenttypes.contenttype`, `auth.permission`, `admin.logentry`);
- backup bookkeeping: `dlux.systembackup`, `dlux.systemrestore` and
  `dlux.reportbackup`;
- updater state and runs: `dlux.dluxupdatestate` and `dlux.dluxupdaterun`;
- the notifications that report backup progress;
- any model listed in [`exclude_models`](#policy-backup_config).

Superuser password hashes are never written: superuser rows are kept with their
password left out. Every other user's password hash is included, so treat each
backup file as sensitive.

Each backup makes three choices on the create form:

| Choice | Options |
| --- | --- |
| **Scope** | **Full**: database rows plus every stored file a `FileField` references. **Quick**: data only, no media. |
| **Include system data** | On by default. Off writes a [portable backup](#portable-backups) of project data only. |
| **Encryption** | **Server key** (default): a key derived from Django `SECRET_KEY`. **Passphrase**: a one-off passphrase, see [Passphrases](#passphrases). **None**: an unencrypted file. |

An unencrypted file exposes all data, regular users' password hashes included, to
whoever holds it. The page warns before you choose **None**. A server-key backup
opens only where the same `SECRET_KEY` is set.

### Portable backups

With **Include system data** off, the backup leaves out the Dlux bookkeeping models
listed in `dlux.backup.SYSTEM_DATA_MODELS`:

- System Settings, its snapshots and scope settings;
- managed font families and variants, and ScanLink releases;
- notifications, their states, rules and watches;
- profiles, trusted devices, known devices and presence sessions;
- public registrations, image updates, control-link requests, Operations runs and
  the activity log.

Users, groups, scopes, group access and managed assets stay in, because project rows
reference them. A listed model that a kept model still references is kept as well.

### Consistency and speed

On PostgreSQL a backup reads the whole database inside one read-only
`REPEATABLE READ` transaction, so the archive is a single point-in-time snapshot
while the site keeps writing. Other engines read model by model. The manifest
records which one applied (`consistency: snapshot` or `live`).

Rows are read in primary-key pages of 1,000, with related rows joined or prefetched
and natural-key lookups cached for the run. A backup-local JSON serializer does the
writing, so PostgreSQL needs no server-side named cursors. The archive is encrypted
on a background thread while it is written, with no separate encryption pass.
Media that is already compressed (images, PDFs, archives, office files) is stored
rather than deflated again.

### Triggers

Each `SystemBackup` row records what started it:

- `manual`: the create form, or `manage.py dlux_backup`.
- `scheduled`: the [schedule](#schedules-and-retention).
- `update`: the backup that an inline apply or rollback started from DjangoLux takes
  before maintenance. It is data-only unless the run's `backup_mode` is `full`, and
  `skip` leaves it out. A failed backup fails the update. See
  [Verified Inline Updates](inline-updater.md).

`python manage.py dlux_backup [--scope data|full] [--trigger update|manual|scheduled]
[--requested-by NAME]` takes a backup in the foreground, with the server key and
system data included. It prints one JSON result line and exits non-zero unless the
backup completed. Composer runs it with `--trigger update` before an operator's
`dlux update` or `dlux rollback`, which do not pass through DjangoLux.

Only one backup runs at a time. While one is pending or running, the create form is
disabled and `POST sys/backup/create/` answers HTTP 409. The check is repeated under
the settings-row lock that the scheduler also takes, so two simultaneous submits
create one backup.

A manual backup is queued on Celery when a worker answers. Otherwise, or with
`use_celery` off, it runs inline in the web request, which suits small installs
only.

## Policy (`backup_config`)

| Key | Default | Meaning |
| --- | --- | --- |
| `scheduled_enabled` | `false` | Create backups on a schedule through Celery beat. |
| `schedule_interval_hours` | `24` | Hours between scheduled backups, 1–8760. Beat checks every 15 minutes. |
| `retention_days` | `0` | Delete completed backups older than this many days, 0–3650. `0` keeps them indefinitely. |
| `max_backups_to_keep` | `0` | Keep only the newest completed backups, 0–10000, counting a chain as one. `0` means no count limit. |
| `auto_export_target` | `dlux_backups` | The folder, relative to Django `default_storage`, that holds every backup and that restore reads. |
| `stall_timeout_minutes` | `30` | 2–1440. A pending or running backup with no heartbeat for this long is failed. |
| `auto_retry_enabled` | `true` | Re-run a failed or stalled backup automatically. |
| `max_attempts` | `3` | Attempts per backup, 1–10, counting the first. `1` disables retrying. |
| `retry_delay_minutes` | `5` | Minutes to wait between attempts, 0–1440. |
| `incremental_enabled` | `false` | Scheduled runs continue the open [chain](#incremental-chains) as increments. |
| `full_every_days` | `7` | 1–365. A chain whose full backup is older than this is closed. |
| `max_chain_length` | `24` | Increments per chain, 1–500, before the next backup is full. |
| `use_celery` | `true` | Queue backups and restores on Celery when a worker answers. Off runs them inline and disables automatic retries. |
| `exclude_models` | `[]` | Extra `app_label.model_name` keys, lower-cased, to leave out of every backup. |

Numbers outside their range are clamped to it. The settings form rejects an invalid
`auto_export_target`. On any other path a value falls back to `dlux_backups` when it
contains `.` or `..` segments, uses characters other than letters, digits, `.`, `_`,
`-` and `/`, is longer than 180 characters, or names a public folder.

`use_celery` and `exclude_models` have no field on the settings page. Saving the page
keeps their stored values, and a settings import carries them. Until System Settings
stores a backup policy, the whole group comes from the `DLUX_CONFIG['backup']`
fallback.

The app serves backups only through its superuser views, and `/media/` never serves
one, whatever the folder: the media access check refuses any `.dlb` file, the backup
folder in use, and any file a backup record still names after the folder changed (see
[Stored files](deployment-configuration.md#stored-files-media)). The folder can't be a
public folder (`public/`, `dlux/branding/`, `dlux/assets/image/`, `dlux/assets/font/`
or a `DLUX_PUBLIC_MEDIA` entry), because the proxy serves those without asking the
app: the settings form refuses one.

## Schedules and retention

DjangoLux adds the beat entry `dlux-scheduled-system-backup-check` to
`CELERY_BEAT_SCHEDULE`, unless the project defines an entry of that name. It runs
every 15 minutes. With `scheduled_enabled` on, each check first reaps
[stalled backups](#stalled-backups). It then creates a backup when no scheduled
backup is pending or running and the last one is older than
`schedule_interval_hours`.

Scheduled backups are full scope, include system data and use the server key. With
`incremental_enabled` on, a scheduled run continues the newest open chain of exactly
that kind. When there is none, it takes a full backup, which starts a new chain.

Retention runs after every successful backup and works on whole chains:

- A full backup and its increments are kept or removed together. A backup outside
  any chain counts as a chain of one.
- `retention_days` compares the age of a chain's newest member.
- `max_backups_to_keep` counts chains.
- The chain of the backup that just completed is never removed, so a pre-update
  backup survives the retention run it starts.

Removal is best effort for each backup: a storage error never fails the new backup.

## Incremental chains

A full backup is the base of a chain (`kind=full`, `sequence=0`, `chain_id` set to
its own token). An increment (`kind=incremental`) continues the newest completed
member of a chain, its `parent`, and stores only:

- rows whose digest changed. Every row's serialized JSON is hashed (BLAKE2b, 8-byte
  digest) while it is written, so detection needs no timestamps and covers every
  model;
- `deleted/<app>/<model>.json`: primary keys present in the parent and gone now;
- media whose storage name is not in the parent's index.

Every member, full or incremental, writes its index,
`{"models": {label: {pk: digest}}, "files": [storage names]}`. The index goes into
`index.json` inside the `.dlb` and into a `.idx` sidecar beside it with the same
encryption, so the next increment reads one small file instead of decrypting its
parent. `SystemBackup.index_root` is the SHA-256 of that index.

A chain is **closed**, and the next backup must be full, when:

- its base is gone, or older than `full_every_days`;
- it reached `max_chain_length` increments;
- the applied migrations differ from the chain's (`migration_digest`);
- its newest member lost its sidecar.

Increments inherit the chain's scope and encryption. A passphrase chain keeps one
passphrase, because each increment must open its parent's sidecar.

### Choosing the parent

The create form's **Type** selector offers *Incremental* only while a chain is open,
and says why when none is. The **Parent backup** selector defaults to **Automatic**:
the newest completed indexed backup, of any scope. If that chain is closed,
Automatic does not fall back to an older one.

A superuser can instead pick the latest eligible member of another chain. Earlier
members of a chain cannot be picked, so a chain stays linear. Chains closed by age,
length, a schema change or a missing index are not offered. The chosen chain sets
the scope and encryption, and a passphrase chain still asks for its passphrase.
Eligibility is checked again under the creation lock.

`POST sys/backup/create/` takes `backup_kind=incremental` and an optional
`backup_parent=<token>`. A missing or empty value means Automatic. The list-status
GET (`sys/backup/status/`) accepts the same parameter and returns selection-aware
`chain` availability and translated parent options.

### Deleting and downloading members

Deleting a member deletes every later member of its chain, and the confirmation says
so. An increment's **Download** returns the chain up to it as one ZIP
(`GET sys/backup/<token>/download-chain/`), because a lone increment cannot be
restored. The DLB viewer opens a chain ZIP, or an increment beside its earlier
members, as the merged state.

## Interrupted backups

### Progress and heartbeats

Every progress write updates `SystemBackup.heartbeat_at`, together with `stage`,
`attempt_count` and `next_attempt_at`. A running backup writes about every
3 seconds. The heartbeat is the only reliable evidence that a run is alive. A
worker killed mid-build (out of memory, restarted, disconnected) never reaches the
failure path, so without the heartbeat its row would stay `running` with a frozen
percentage and no error.

Each row's **Details** console shows the run's timestamped progress log (the last
200 messages, `SystemBackup.progress_log`), the elapsed time and, while it runs, the
estimated time remaining. The create form estimates a new backup's duration from
the last three completed backups of the same kind: full, data-only or incremental.

### Stalled backups

`reap_stalled_system_backups()` fails every pending or running backup whose
heartbeat is older than `stall_timeout_minutes`, whatever its trigger. It then
starts any retry that is due. A pending backup that is waiting for its own retry
time is not stalled.

The reaper runs from:

- the Backup & Restore page and its status poller;
- the scheduled-backup beat task;
- Celery's `worker_ready` signal, when a worker starts.

A restarted worker therefore retires exactly the backups it abandoned: a run in a
sibling worker heartbeats every few seconds and never falls inside the window.
Retries started from the web tier go to a worker or wait. The page never builds a
backup inside a status request.

### Retries

A failed or stalled attempt is retried automatically when all of these hold:

- `auto_retry_enabled` is on;
- fewer than `max_attempts` attempts have run;
- a Celery worker is available to run it;
- the backup has no passphrase (see [Passphrases](#passphrases)).

The row returns to `pending` with `next_attempt_at` set `retry_delay_minutes` ahead.
A retry re-runs the whole snapshot on the same history row, so the history keeps one
line per requested backup and `attempt_count` shows what it took. A partly written
`.dlb` is one encrypted stream over one snapshot, so there is nothing in it to
resume.

An increment whose chain became unusable is not retried: its parent is gone, its
parent's index cannot be read, or the schema changed. Take a full backup instead.

**Retry** on a failed or cancelled row (`POST sys/backup/<token>/resume/`) starts a
fresh attempt on the same row. It asks for the passphrase when the backup has one.

### Cancelling

**Cancel** on a pending or running row (`POST sys/backup/<token>/cancel/`) sets it
to `cancelled`, and a pending backup is then never started. Every progress write a
running backup makes is conditional on the row still being `running`, so the write
that matches nothing is the cancellation signal. The run stops within a heartbeat
(about 3 seconds), deletes any file it already stored and unlocks its drawer item
without a failure notice.

A cancelled backup can be retried. A running backup offers **Cancel** instead of
**Delete**: cancel it before deleting it.

## Passphrases

A passphrase is entered twice and cleared from the form as soon as the backup
starts. It is stored nowhere: not on the row and not in the file. It reaches the run
only as an argument of the Celery task, or of the inline call.

- **Never retried unattended.** A blind re-run cannot reproduce the passphrase and
  would silently write a server-key file instead. The one exception is a retry that
  the Celery task queues for itself, because it still holds the passphrase in its
  arguments. Every other path leaves the row failed, with a **Retry** action that
  asks for the passphrase.
- **One per chain.** Every increment of a passphrase chain needs the same passphrase.
- **Needed to read the file.** Restore and the DLB viewer ask for it, and a lost
  passphrase cannot be recovered.

The file key is derived with PBKDF2-SHA256 (390,000 iterations, random 16-byte salt)
from the passphrase, or from Django `SECRET_KEY` for a server-key backup.

## Restore

Restore is superuser-only. It asks for the current password and an explicit
confirmation that this system's data will be replaced. The source is a backup in the
history, or a `.dlb` file in the backup folder: one uploaded through the page (saved
as `uploaded-<timestamp>-<token>.dlb`) or one copied there by hand, which the page lists.

Uploads are capped by `DLUX_DLB_UPLOAD_MAX_MB` (default 512), and the reverse
proxy's body limit applies first. See
[Deployment Configuration](deployment-configuration.md).

A restore runs on Celery when a worker answers, otherwise inline. It:

1. Reads and decrypts the file and, for an increment, every earlier member of its
   chain.
2. Compares the backup's applied migrations with this system's. A mismatch fails
   the restore unless **Ignore version mismatch** was chosen. A chain whose members
   span a schema change is always refused.
3. Replaces the data in one transaction with foreign-key checks deferred. A full
   backup replaces every backed-up model, so a model with no rows in the archive is
   emptied. Implicit many-to-many tables are cleared first, and integrity is
   verified before commit.
4. Restores the media files, replacing any stored file of the same name.
5. Clears the cache.

A portable backup replaces only the tables it carries and keeps this system's
settings, logs and notifications. A kept row that points at a user the backup does
not contain loses that link when it is nullable, and is removed when it is required.

Superuser password hashes are not in the backup. A restored superuser whose username
exists on this system keeps this system's password. Any other restored superuser
gets an unusable password and must reset it.

Inline-update rollback changes code and static files only. It never reverses
database migrations or restores a backup by itself.

### Restoring a chain

Restoring an increment resolves the chain from base to member using the cleartext
headers of the `.dlb` files in the backup folder, so uploaded chains work too. It
follows `parent_root` → `root` links and refuses a missing, foreign or swapped member
before anything is wiped. Every member must share the base's migration state.

The base loads as a normal restore. Then each increment, in order and in the same
transaction, upserts its rows (deserialized saves update by primary key) and
raw-deletes its `deleted/` keys and their implicit many-to-many links. The chain
commits as a whole or not at all. To restore a chain elsewhere, upload each member
`.dlb`.

## The `.dlb` format

```
"DLB1"                 4-byte magic
u32 (big-endian)       header length
header JSON            cleartext metadata
payload                the inner ZIP, as Fernet frames or plain
```

The cleartext header carries:

- `format` (`1`) and `kind`: `dlux-system-backup` for a full backup,
  `dlux-system-backup-increment` for an increment. A reader that knows only full
  backups refuses an increment instead of restoring it as one.
- `created_at`, `dlux_version`, and the `models`, `rows` and `files` counts;
- `media_included`, `system_data_included` and `consistency`;
- `chain` (`id`, `sequence`, `token`, `parent`, `root`, `parent_root`, `kind`) and
  `migration_digest`;
- `passphrase_required` and `encryption`. An encrypted file has `scheme`
  `fernet-chunked`, `kdf` `pbkdf2-sha256`, a hex `salt`, `iterations` and a
  `key_source` of `passphrase` or `django-secret-key`. An unencrypted one has
  `scheme: "none"`.

With encryption the payload is a series of frames, each a big-endian u64 length
followed by one Fernet token. The streaming writer uses 8 MB frames, and readers
take each frame's length from its prefix. With `scheme: "none"` the plain ZIP follows
the header directly.

The inner ZIP is written as a stream, so its members use ZIP data descriptors:

| Member | Content |
| --- | --- |
| `manifest.json` | Dlux version, migration state and digest, `media_included`, `system_data_included`, `consistency`, the superuser password policy, per-model row counts, the file list and missing files, `chain`, and a relation `schema` that lets the viewer label references without the project. |
| `data/<app>/<model>.json` | The model's rows as Django fixtures. |
| `files/<app>/<model>/<pk>/<field>/<name>` | Stored files, in a full-scope backup. |
| `deleted/<app>/<model>.json` | Primary keys removed since the parent (increments only). |
| `index.json` | The member's row and file index. |

The `.idx` sidecar is the same container, with a header that names
`content: "index"` and the zlib-compressed index as its payload.

A General Reports ZIP is a different archive: it has no `data/*.json` and is never a
restore source. See [Operations](operations.md#activity-logs-and-reports).

### The `SystemBackup` row

| Field | Holds |
| --- | --- |
| `token` | The backup's public identifier, used in its file name (`system-<token>.dlb`) and routes. |
| `trigger` | `manual`, `scheduled` or `update`. |
| `kind`, `parent`, `chain_id`, `sequence` | Chain position: `full` or `incremental`, the member it continues, its chain and its place in it. |
| `index_root`, `migration_digest` | SHA-256 of its index and of its applied migrations. |
| `status` | `pending`, `running`, `completed`, `failed` or `cancelled`. |
| `media_included`, `system_data_included` | Its scope. |
| `encryption`, `passphrase_required` | `server_key`, `passphrase` or `none`, and whether reading it needs a passphrase. |
| `file_path`, `file_size` | Where the `.dlb` is stored, and its size. The sidecar sits beside it as `.idx`. |
| `model_count`, `row_count`, `file_count`, `missing_file_count` | What it holds. |
| `heartbeat_at`, `stage`, `progress_percent`, `progress_message`, `progress_log` | Live progress; `progress_log` keeps the last 200 messages. |
| `attempt_count`, `next_attempt_at`, `error` | Retry state and the last error. |

The [DLB viewer](../tools/dlb-viewer/README.md) reads this format offline. Its
[container reference](../tools/dlb-viewer/README.md#container-format-reference)
covers how it opens files and merges chains.

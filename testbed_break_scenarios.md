# Testbed break scenarios — 1.11.0b4 (2026-10-08)

Driven on `~/Desktop/depy/testbed-dlux` (decrees app, PostgreSQL 17, Celery,
Composer beta channel) with 20k decrees, 20k activity logs and 300 PDFs.
Path: baked 1.11.0b3 → inline update to published 1.11.0b4 (CLI) → CLI rollback
to b3 → inline update to b4 from the UI. Each entry: what was done, what
happened, severity, status.

## Broke

### S1 — Inline updates and rollbacks take no pre-update backup (since 1.10.0)

- **Do**: Options → update to 1.11.0b4 from 1.11.0b3 with the backup mode
  *data* (`POST sys/api/dlux-update/apply/`, `backup_mode=data`).
- **Got**: run completed, `backup_token` empty, no `trigger=update` backup
  created. Run log: "Started apply request. Handed the apply to Composer…".
- **Expected**: Backup settings say "Inline updates and rollbacks always create
  and verify a full system backup before maintenance. An update is stopped if
  that backup fails."
- **Cause**: `9745606` (removal of the in-container executor for 1.10.0) deleted
  the `_create_backup` calls from the apply/rollback paths; the Composer
  hand-off only forwards `backup_mode`, and Composer documents backups as
  "DjangoLux-side". Image updates still back up.
- **Severity**: high — every inline update since 1.10.0 (stable) ran without
  its safety snapshot while the UI implied one.
- **Status**: fixed on `fix/testbed-findings` (backup before the hand-off;
  failure stops the run). Re-checked on the testbed with a 1.11.0b5
  candidate: the run logged "Creating a data-only pre-update DjangoLux
  backup.", stored the token of a completed 40,291-row `update` backup, then
  handed off. The backup runs in the release updated *from*, so updates to
  1.11.0b5 from b4 still take none; updates started on b5 do.

### S2 — Rolling back below 1.11.0b4 breaks deleting a chain base

- **Do**: on b4 make a full + incremental; CLI rollback to b3; Backup page →
  Delete the full backup.
- **Got**: HTTP 500 `ForeignKeyViolation` on
  `dlux_systembackup_parent_id_…_fk`, and the `.dlb` was already gone (b3
  deletes the file before the row): a "completed" row with no file, and a
  chain without its base. b3's retention would do the same, silently.
- **Cause**: b4's `SystemBackup.parent` self-FK is enforced by the database; b3
  does not know the column.
- **Severity**: medium — only after a rollback, but it corrupts backup
  bookkeeping and loses a file.
- **Status**: fixed on `fix/testbed-findings`: completed members no longer hold a
  `parent` link (chains are tracked by `chain_id`/`sequence`/roots), and
  existing links are cleared; only an increment in flight references its parent.
  Re-checked: on the b5 candidate the old b4 links were released by the next
  backup; a new chain was made, the testbed switched to the b3 image, and
  b3's Delete removed the chain's base cleanly (302, no FK error).

### S3 — Pre-chain releases restore an increment as a full backup

- **Do**: on b3, restore an increment written before the kind change.
- **Got**: b3 wiped and started loading the delta; this time it failed on a
  missing natural-key user and rolled back. A self-contained delta would have
  committed, leaving only the changed rows.
- **Status**: fixed before release in 1.11.0b4: increments use header kind
  `dlux-system-backup-increment`; b3 then refuses ("Unsupported backup kind",
  verified on the testbed with a b4 increment).

### S4 — `./start.sh dlux update` bypasses DjangoLux entirely

- **Do**: update from the CLI.
- **Got**: no `DluxUpdateRun`, no admission checks, no backup — Composer
  installs and restarts directly.
- **Severity**: medium (operator tool), but it is the documented acceptance
  path. **Status**: open — Composer-side; should either queue through
  DjangoLux or take the backup itself.

### S5 — An update run's "completed" is not checked against what runs (observation)

- **Do**: with a newer release baked into the image (b5), queue an apply of the
  older published b4 directly through `UpdateService` (bypassing admission).
- **Got**: Composer exited 0, the run said "Composer applied the release" and
  completed, yet reconcile kept the newer baked release active.
- **Severity**: low — admission never offers an older release, so the UI
  cannot request this. **Status**: open; completion could compare the active
  version with the run's target.

## Held (with notes)

- **Backup running during an inline update** — the backup finished before the
  restart in this run (3 s backups); not reproduced as a race.
- **Worker killed mid-incremental** — row stays `running` (5%); the create form
  is locked by it until the stall timeout (30 min) unless someone presses
  Cancel, which works immediately; a restarted worker does not resurrect it.
- **Two/twelve simultaneous creates** — exactly one created, the rest 409.
  The guard was check-then-create (not atomic); now re-checked under a row lock
  on `fix/testbed-findings`.
- **Corrupted `.idx` sidecar** — the increment fails without writing anything.
  The message blamed the passphrase and an automatic retry was armed for a
  failure that cannot heal; message and retry fixed on `fix/testbed-findings`.
- **Forged increment header** (parent root rewritten) — restore refused before
  wiping: "chain is broken at member 1".
- **b3 creating backups on the b4 schema** — fine (`db_default` on every new
  column).
- **Restoring an increment whose base file was deleted (S2 aftermath)** on b4 —
  refused: member 0 missing.

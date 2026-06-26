# Dlux Backup Viewer (`.dlb`)

A standalone, **zero-dependency** desktop viewer for the encrypted system
backups (`.dlb`) produced by [django-lux](../../). It decrypts a backup
locally, prompts for the password on entry, and lets you browse the contents —
models, rows, the migration state, the manifest, and every stored file — in your
browser.

Nothing is uploaded anywhere: the binary serves a small UI on `127.0.0.1` only,
and all decryption happens on your machine.

## Why Go

The viewer must read the exact `.dlb` container that `dlux/backup.py`
writes: a cleartext `DLB1` header followed by Fernet-encrypted ZIP chunks
(PBKDF2-SHA256 key derivation). Go's standard library covers AES, HMAC,
SHA-256, and ZIP; Fernet and PBKDF2 are implemented from those primitives in
[`dlb.go`](dlb.go). The result is a **single static binary with no third-party
modules** and trivial cross-compilation — the lightest way to ship a
cross-platform viewer that needs no runtime installed on the target machine.

## Build

Requires Go 1.21+.

```sh
cd tools/dlb-viewer
go build -o dlb-viewer .
```

Cross-compile for other platforms (no CGo, so this just works):

```sh
GOOS=windows GOARCH=amd64 go build -o dlb-viewer.exe .
GOOS=darwin  GOARCH=arm64 go build -o dlb-viewer-macos .
GOOS=linux   GOARCH=amd64 go build -o dlb-viewer-linux .
```

## Run

```sh
./dlb-viewer                       # opens the UI; pick a file in the browser
./dlb-viewer path/to/system-backup.dlb
```

It starts a local server, prints the URL, and opens your default browser. Press
`Ctrl-C` to quit — temporary decrypted files are removed on exit.

## The password

Every `.dlb` header records, in cleartext, how it was encrypted. The viewer
reads that and labels the prompt accordingly:

| Backup `key_source`    | What to enter                                              |
| ---------------------- | ---------------------------------------------------------- |
| `passphrase`           | The one-off **passphrase** chosen when the backup was made |
| `django-secret-key`    | The originating project's Django **`SECRET_KEY`**          |

(A legacy `sha256-salt-seed` KDF is also accepted; it is `SECRET_KEY`-only.)

A wrong password fails immediately on the first chunk's Fernet HMAC check, with
a clear "incorrect password or corrupted backup" message.

## What you can browse

- **Overview** — counts, generation time, Dlux version, encryption params,
  superuser policy, and the **backup scope**: *Full (database + media)* or
  *Data only — media excluded* (the Quick scope), read from the `media_included`
  flag in the header/manifest. Pre-1.2.10 backups predate the flag and show
  *Unknown*. The same scope is shown on the unlock screen before you decrypt.
- **Models** — each model's serialized rows, paginated, rendered as a table.
  (Superuser password hashes are omitted in the backup itself, by design.)
  Relation columns (foreign keys, one-to-one, many-to-many) are marked with a
  `↗`. A **"Resolve relations"** toggle in the top bar swaps them between the
  raw stored reference (a PK or natural key) and a readable name resolved from
  the related model's rows. This relies on a `schema` block the backup records
  in `manifest.json`; backups written before that feature shipped have no
  schema, so the toggle is hidden and references are shown as stored.
  **File-field cells** (e.g. a profile picture or an uploaded document) link
  straight to the stored file by its readable name instead of the raw random
  storage path — the name opens the file inline in a new tab, and a `↓` next to
  it downloads. In a data-only (Quick) backup the blob isn't in the container,
  so those cells stay as plain text.
- **Stored files** — the full table of captured file fields; **open** renders a
  viewable file (PDF, image, plain text) inline in a new tab, **download** saves
  it. When a backup has no stored files the view explains why — a data-only
  (Quick) backup says media was intentionally excluded, versus a full backup
  that simply had none.
- **Migration state** — the applied migrations recorded at backup time.
- **Raw manifest** — the full `manifest.json`.

### Opening files inline

"Open" serves the file with a real `Content-Type` derived from its extension, so
the browser renders it: **PDF** via the built-in PDF viewer, **images**
(`png`/`jpg`/`gif`/`webp`/`bmp`) directly, and plain-text/`csv`/`json` as text.
Unknown types — and active content like HTML/SVG/XML — are forced to download
instead of rendering, so a malicious `.dlb` can't run script in the viewer's own
origin. Responses always carry `X-Content-Type-Options: nosniff`.

## Container format (reference)

```
"DLB1"                 4-byte magic
u32 (big-endian)       metadata-JSON length
metadata JSON          cleartext: kind, created_at, version, counts, encryption{}
repeated frames:
  u64 (big-endian)     Fernet-token length
  Fernet token         one <=32 MB plaintext chunk of the inner ZIP
```

The decrypted payload is a ZIP with `manifest.json`, `data/<app>/<model>.json`
(Django fixtures), and `files/<app>/<model>/<pk>/<field>/<name>`.

## Security notes

- Binds to `127.0.0.1` only; API calls require a random per-run token and a
  local `Host` header (basic DNS-rebinding protection).
- Read-only: the viewer never writes back to the backup or to any system.
- Treat the decrypted contents as sensitive — they include user records and
  settings. Run it on a trusted machine.

# Releasing django-lux

This project uses **tag-driven releases**. The git tag *is* the release; PyPI
and the GitHub Release page are produced automatically from it by
[`.github/workflows/release.yml`](../.github/workflows/release.yml).

There is **one source of truth for the version**: the `version` field in
[`dlux/release-manifest.json`](../dlux/release-manifest.json). `dlux/__init__.py`
reads it into `__version__`, and `pyproject.toml` derives the package version from
that attribute. The manifest already ships inside the wheel (remote updaters read
it to verify a downloaded release), so the package version, the updater's
compatibility checks, and the release tag all follow from this one field. Bump it
(and the manifest's `release_url`/`summary`/`migration_policy` for the release) and
everything else follows. The release workflow refuses to run if the pushed tag
doesn't match the manifest version.

---

## One-time setup (do this once, ever)

### 1. PyPI Trusted Publisher (no API token needed)

This lets the GitHub workflow publish to PyPI over OIDC, with no stored secret —
and it works **before the project has ever been published**, via a *pending
publisher*. The first successful run creates the project and binds the publisher.

1. Sign in to PyPI → <https://pypi.org/manage/account/publishing/>.
2. Under **Add a new pending publisher → GitHub**, enter:
   - **PyPI Project Name:** `django-lux`
   - **Owner:** `debeski`
   - **Repository name:** `django-lux`
   - **Workflow name:** `release.yml`
   - **Environment name:** `pypi`
3. Save. That's it — no token, nothing to rotate, no manual first upload.

> Once `django-lux` exists on PyPI, the same publisher is managed at
> <https://pypi.org/manage/project/django-lux/settings/publishing/>.

### 2. GitHub environment

In the repo: **Settings → Environments → New environment → name it `pypi`**.
(Optional but recommended: add yourself as a required reviewer so a release
pauses for your approval before the PyPI upload.) The name must match the
`environment: pypi` in `release.yml` and the trusted-publisher form above.

---

## Cutting a release (the ~30-second ritual)

```sh
# 0. main is green and your working tree is clean
git switch main && git pull

# 1. bump the single version source (patch=fix, minor=feature, major=breaking):
#    set "version" (and "release_url" v-tag, summary, migration_policy) in the manifest
$EDITOR dlux/release-manifest.json

# 2. add a CHANGELOG section for it (newest at top): "## vX.Y.Z"
$EDITOR CHANGELOG.md

# 3. commit, tag, push
git commit -am "release: vX.Y.Z"
git tag -a vX.Y.Z -m "vX.Y.Z"
git push && git push --tags

# or just use a one line command like this:
git add -A && git commit -m "release: vX.Y.Z" && git tag -a vX.Y.Z -m "vX.Y.Z" && git push origin --follow-tags
```

Pushing the tag triggers the pipeline:

1. **build-dist** — checks `tag == dlux/release-manifest.json` version, validates the packaged release
   manifest and inline-safe migration policy, builds the sdist + wheel, and
   `twine check`s them.
2. **publish-pypi** — uploads to PyPI via Trusted Publishing.
3. **build-viewer** — runs `make all` in `tools/dlb-viewer/`, producing the 5
   platform binaries.
4. **github-release** — extracts the matching `## vX.Y.Z` section from `CHANGELOG.md` as
   the release notes and publishes a GitHub Release with the wheel/sdist **and**
   the viewer binaries attached.

Watch it under the repo's **Actions** tab.

### Inline-safe release declaration

Every core wheel includes `dlux/release-manifest.json`. Before tagging, update
its version, summary, release URL, updater schema, and migration policy. Set
`inline_safe` to `true` only when all of these hold:

- the dependency metadata is unchanged from the activation/current release;
- supported Python versions are unchanged;
- Dlux migration changes use only `CreateModel`, `AddIndex`, or `AddField`
  operations that are insertable by the *previous* release's code — i.e. the new
  column is `null=True` **or** carries a `db_default` (a plain Python `default` is
  **not** enough: Django backfills existing rows but drops the column default, so
  old code inserting a row after the migration would hit a NOT NULL violation);
- the release remains compatible with the immediately previous code during a
  manual or automatic pointer rollback.

`v1.2.7` is the current repaired updater bootstrap baseline and is installed
through a normal image rebuild. It supersedes v1.2.4-v1.2.6 because the health
orchestration that races Celery startup runs from the baked updater and cannot
repair itself from a candidate wheel. The unchanged-dependency rule governs
subsequent releases that can actually be selected by the repaired inline updater.

`python -m dlux.updater.release_check --base-tag vX.Y.Z` runs the same manifest
and changed-migration gate locally. The tag workflow determines the prior `v*`
tag automatically. Use `inline_safe: false` and `migration_policy:
image_rebuild` for destructive/renaming/data migrations. Dependency changes or
unsupported updater/Python baselines also require `inline_safe: false` even when
their migration policy remains backward-compatible. The deployed UI then reports
**Project image rebuild required** instead of offering an Update button.

## Manifest schema 2

Schema 1 published a *conclusion* — `inline_safe` — which freezes the policy in
force on release day into an artifact that outlives it, and split the reasoning
across `inline_safe` and `migration_policy`, whose values came from different
axes. Schema 2 states facts and lets the updater decide:

```json
{
  "schema_version": 2,
  "version": "1.9.0",
  "display": { "summary": "...", "highlights": ["..."], "release_url": "..." },
  "requires": {
    "updater_schema": ">=1",
    "baked_image": ">=1.2.7",
    "services": { "composer": ">=5.3.0" }
  },
  "migrations": { "effect": "additive", "rollback_compatible": true, "downtime": "none" },
  "install":  { "inline": "allowed" },
  "rollback": { "supported": true }
}
```

`migrations.effect` is one of `none`, `state_only`, `additive`, `altering`,
`destructive`. A release is offered inline only when `install.inline` is
`allowed` **and** the effect is one of the first three — `install.inline` is a
permission, not an override, so an author cannot wave a destructive migration
through.

`requires` describes the **deployment**, never the package. There is deliberately
no `python` or dependency key: the wheel already declares those in
`Requires-Python`/`Requires-Dist`, pip enforces them, and a second copy here
could only ever disagree with the authority. `services` is what schema 1 had no
way to state — 1.8.0 requires Composer as a running service, and the manifest
could not say so.

**Unknown values fail closed.** An unrecognised `migrations.effect`, an
unrecognised `install.inline`, or *any* unknown key inside `requires` is refused
rather than ignored. That last rule is what makes `requires` safely extensible:
add `"postgres": ">=14"` in a later schema and older updaters correctly refuse
instead of installing while ignoring a constraint they cannot evaluate. Unknown
keys outside `requires` (display metadata) are ignored, so cosmetic additions
never break an older reader.

Schema 1 manifests are still accepted and normalised onto the same internal
shape, so there is one code path downstream:

| schema 1 | schema 2 |
|---|---|
| `inline_safe: true/false` | `install.inline: allowed/forbidden` |
| `migration_policy: backward_compatible` | `migrations.rollback_compatible: true` |
| `migration_policy: image_rebuild` | `effect: destructive`, `rollback_compatible: false` |
| `image_baseline: "1.2.7"` | `requires.baked_image: ">=1.2.7"` |
| `minimum_updater_schema: 1` | `requires.updater_schema: ">=1"` |

`rollback.supported: false` is representable but **not yet actionable**: the
automatic health-failure path restores the previous release by swapping the
pointer, it does not restore the database (see `inline-updater.md`). Until that
path can restore the pre-update backup, do not ship a release that needs it.

### State-only field changes (`SeparateDatabaseAndState`)

`AlterField` is rejected by the gate outright, and that is deliberate: Django
serialises the *whole* field into the migration, so a harmless `choices` edit and
a `max_length` shrink are byte-for-byte indistinguishable to anything reading the
file. The gate cannot tell them apart, so it refuses the operation rather than
guess.

Some field edits genuinely touch no column — adding a value to `choices` is the
common one, since Django validates choices in Python and never in the schema. For
those, do not leave a bare `AlterField` and downgrade the release. Wrap it:

```python
migrations.SeparateDatabaseAndState(
    database_operations=[],
    state_operations=[
        migrations.AlterField(model_name="...", name="...", field=...),
    ],
)
```

`makemigrations` still sees no drift, `sqlmigrate` reports `-- (no-op)`, and the
empty `database_operations` list makes the zero-SQL claim *checkable* instead of
assumed — the gate verifies that list is empty and accepts nothing else. A
non-empty `database_operations` is rejected with a distinct message.

**Use it only where the change genuinely needs no DDL.** The gate checks that the
list is empty; it cannot check that the list *should* be empty. Wrapping a field
change that really does require a column change — widening `max_length`, adding
`null=True`, changing a type — makes Django record the new state while leaving the
old column in place. Nothing fails at migrate time; the schema and Django's idea
of it simply diverge, and the breakage surfaces later somewhere unrelated. That is
a worse outcome than an honest `inline_safe: false`.

The test: run `sqlmigrate` on the migration with the operation as a plain
`AlterField` first. If it prints `-- (no-op)`, the wrapper is stating a fact. If
it prints DDL, it is not, and the release needs `inline_safe: false` and
`migration_policy: image_rebuild`.

A non-destructive column change is still a column change. Widening a `varchar` is
safe for the schema but not automatically safe for a rollback: the previous
release can read the wider rows but may refuse to re-save them if its own
validation still caps the old length. Backward compatibility covers the data the
new release writes, not just the shape of the table.

Note that Composer executing the update (`DLUX_UPDATE_EXECUTOR=composer`, the
default from 1.8.0) does **not** relax any of this. `inline_safe` is a statement
about the database, not about who runs the command: rollback returns the
*previous* release to the *same* schema. Composer made rollback an automated,
health-gated path that is actually taken, so backward-compatible migrations
matter more under it, not less. The admission check in `queue_run()` refuses an
APPLY of a release that is not inline-safe under either executor.

### Inline floor after an image-required release (`image_baseline`)

The inline updater always offers the single **highest** available release, not a
step-by-step walk, so a box on an old version can be offered a much later one
directly — skipping over any image-required release in between. Marking a later
release `inline_safe: true` is only true *relative to the image the release
before it left baked*; it is **not** safe to drop onto an older image.

To make this an enforced invariant instead of an authoring convention, set the
optional `image_baseline` manifest field to the most recent version that required
an image rebuild. `assess_wheel` compares it against the box's **baked image**
version and refuses the inline update (fails closed on an unknown image version)
until the project image is rebuilt to at least that baseline:

```
"image_baseline": "1.7.0"
```

This floor is **computed, not carried by hand**. `release_check.expected_image_baseline()`
walks the published tags and returns the highest version whose manifest forbade an
inline install (either schema); `validate_image_baseline()` refuses a manifest that
declares a lower floor, or none at all when one is outstanding.

That replaced an authoring convention which had already failed in practice: v1.2.7
shipped `image_rebuild`, and every release from v1.3.0 to v1.7.1 omitted the floor,
so a box on a pre-1.2.7 image could be offered a later inline-safe release and skip
the rebuild entirely. A rule a human has to remember on a release day is a rule
that eventually gets missed.
A box at or above the baseline updates inline as normal; a box below it is told to
image-update first.

PyPI must continue publishing through repository `debeski/django-lux`, workflow
`.github/workflows/release.yml`, and environment `pypi`; deployed updaters verify
that exact attested publisher identity. PyPI's integrity response represents the
workflow field as the basename `release.yml`; the updater checks that canonical
API value after cryptographic attestation verification.

---

## Rules that keep it from getting chaotic again

- **Never edit a version twice.** Only the `version` field in
  `dlux/release-manifest.json`. Two places drift; one can't.
- **A published version is frozen.** PyPI rejects re-uploads of an existing
  version, and a tag is immutable. So any change after a release = a new version.
  (This replaces the old "check `dist/` before editing the changelog" workaround
  — the tooling now enforces it.)
- **Tag from `main` only**, after CI is green. `git checkout vX.Y.Z` will always
  show exactly what shipped.
- **If a release run fails before PyPI upload**, fix forward: bump to the next
  patch and re-tag. Don't try to reuse a tag.

---

## Companion packages (optional SSO)

The two SSO companions in `tools/` publish **independently** of the main package,
each via its own tag prefix and workflow:

| Package | Source | Tag prefix | Workflow |
| --- | --- | --- | --- |
| `django-lux-sso` | `tools/django-lux-sso/` | `sso-v*` | `release-sso.yml` |
| `django-lux-sso-client` | `tools/django-lux-sso-client/` | `sso-client-v*` | `release-sso-client.yml` |

Their versions live in package-local version files:
`tools/django-lux-sso/dlux_sso/VERSION` and
`tools/django-lux-sso-client/dlux_sso_client/VERSION`. Each package's
`pyproject.toml` derives metadata from `__version__`, so bump the package's
`VERSION` file and the workflow checks the tag matches it. To release one:

```sh
# bump tools/django-lux-sso/dlux_sso/VERSION, then:
git tag -a sso-v0.1.1 -m "django-lux-sso 0.1.1"
git push origin sso-v0.1.1
```

The companion release jobs build through each package's `build.py` helper. Do
not replace that with `python -m build` while the job working directory is the
package directory: each companion also has a local `build.py`, which would shadow
PyPA's `build` module and recursively invoke itself.

**One-time setup per companion** (same pending-publisher flow as above): add a
PyPI pending publisher for project `django-lux-sso` bound to workflow
`release-sso.yml`, and another for `django-lux-sso-client` bound to
`release-sso-client.yml` — both using the `pypi` environment. Until
`django-lux-sso` is published, `pip install django-lux[sso]` will fail (base
`pip install django-lux` is unaffected).

---

## CI test suite

The CI workflow ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) runs
the curated package Django suite through
[`dlux/tests/test_all.py`](../dlux/tests/test_all.py). That runner uses
`dlux.tests.settings` as the shared package-local test settings module and
includes `test_defaults_and_urls`, scaffold checks, backup/report coverage,
notifications, permissions, middleware, and utility tests.

Projects that call `dlux_settings(globals())` automatically replace the default
cache with a process-local memory cache during `manage.py test` and pytest runs.
This prevents test `SystemSettings`, sessions, and throttles from leaking into a
development stack's shared Redis. Set `DLUX_ISOLATE_TEST_CACHE=False` only when
the test environment already points at a dedicated disposable cache.

Keep external/manual probes such as `test_m2m.py` and `verify_detailed_logs.py`
out of `TEST_LABELS` unless they are converted to the shared package harness.
Once CI is green on `main`, it can be treated as the required branch-protection
gate for package changes.

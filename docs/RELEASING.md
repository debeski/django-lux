# Releasing django-lux

This project uses **tag-driven releases**. The git tag *is* the release; PyPI
and the GitHub Release page are produced automatically from it by
[`.github/workflows/release.yml`](../.github/workflows/release.yml).

There is **one source of truth for the version**: [`dlux/VERSION`](../dlux/VERSION).
`dlux/__init__.py` reads it into `__version__`, and `pyproject.toml` derives
the package version from that attribute. Bump that one file and everything else
follows. The release workflow refuses to run if the pushed tag doesn't match it.

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

# 1. bump the single version source
#    e.g. 1.0.0 -> 1.0.1   (patch=fix, minor=feature, major=breaking)
echo "1.0.1" > dlux/VERSION

# 2. add a CHANGELOG section for it (newest at top): "## v1.0.1"
$EDITOR CHANGELOG.md

# 3. commit, tag, push
git commit -am "release: v1.0.1"
git tag -a v1.0.1 -m "v1.0.1"
git push && git push --tags

# or just use a one line command like this:
git add -A && git commit -m "release: v1.0.1" && git tag -a v1.0.1 -m "v1.0.1" && git push origin --follow-tags
```

Pushing the tag triggers the pipeline:

1. **build-dist** — checks `tag == dlux/VERSION`, builds the sdist + wheel,
   `twine check`s them.
2. **publish-pypi** — uploads to PyPI via Trusted Publishing.
3. **build-viewer** — runs `make all` in `tools/dlb-viewer/`, producing the 5
   platform binaries.
4. **github-release** — extracts the `## v1.0.1` section from `CHANGELOG.md` as
   the release notes and publishes a GitHub Release with the wheel/sdist **and**
   the viewer binaries attached.

Watch it under the repo's **Actions** tab.

---

## Rules that keep it from getting chaotic again

- **Never edit a version twice.** Only `dlux/VERSION`. Two places drift; one
  can't.
- **A published version is frozen.** PyPI rejects re-uploads of an existing
  version, and a tag is immutable. So any change after a release = a new version.
  (This replaces the old "check `dist/` before editing the changelog" workaround
  — the tooling now enforces it.)
- **Tag from `main` only**, after CI is green. `git checkout v1.0.1` will always
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

Keep external/manual probes such as `test_m2m.py` and `verify_detailed_logs.py`
out of `TEST_LABELS` unless they are converted to the shared package harness.
Once CI is green on `main`, it can be treated as the required branch-protection
gate for package changes.

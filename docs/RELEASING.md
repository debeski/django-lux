# Releasing django-microsys

This project uses **tag-driven releases**. The git tag *is* the release; PyPI
and the GitHub Release page are produced automatically from it by
[`.github/workflows/release.yml`](../.github/workflows/release.yml).

There is **one source of truth for the version**: [`microsys/VERSION`](../microsys/VERSION).
`microsys/__init__.py` reads it into `__version__`, and `pyproject.toml` derives
the package version from that attribute. Bump that one file and everything else
follows. The release workflow refuses to run if the pushed tag doesn't match it.

---

## One-time setup (do this once, ever)

### 1. PyPI Trusted Publisher (no API token needed)

This lets the GitHub workflow publish to PyPI over OIDC, with no stored secret.

1. Go to <https://pypi.org/manage/project/django-microsys/settings/publishing/>
   (project already exists). Under **Add a new trusted publisher → GitHub**, enter:
   - **Owner:** `debeski`
   - **Repository name:** `django-microsys`
   - **Workflow name:** `release.yml`
   - **Environment name:** `pypi`
2. Save. That's it — no token, nothing to rotate.

> If the project did *not* yet exist on PyPI, you'd instead add a *pending*
> publisher under your account settings; the first successful run creates it.

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
#    e.g. 2.4.0 -> 2.4.1   (patch=fix, minor=feature, major=breaking)
echo "2.4.1" > microsys/VERSION

# 2. add a CHANGELOG section for it (newest at top): "## v2.4.1"
$EDITOR CHANGELOG.md

# 3. commit, tag, push
git commit -am "release: v2.4.1"
git tag -a v2.4.1 -m "v2.4.1"
git push && git push --tags
```

Pushing the tag triggers the pipeline:

1. **build-dist** — checks `tag == microsys/VERSION`, builds the sdist + wheel,
   `twine check`s them.
2. **publish-pypi** — uploads to PyPI via Trusted Publishing.
3. **build-viewer** — runs `make all` in `tools/msb-viewer/`, producing the 5
   platform binaries.
4. **github-release** — extracts the `## v2.4.1` section from `CHANGELOG.md` as
   the release notes and publishes a GitHub Release with the wheel/sdist **and**
   the viewer binaries attached.

Watch it under the repo's **Actions** tab.

---

## Rules that keep it from getting chaotic again

- **Never edit a version twice.** Only `microsys/VERSION`. Two places drift; one
  can't.
- **A published version is frozen.** PyPI rejects re-uploads of an existing
  version, and a tag is immutable. So any change after a release = a new version.
  (This replaces the old "check `dist/` before editing the changelog" workaround
  — the tooling now enforces it.)
- **Tag from `main` only**, after CI is green. `git checkout v2.4.1` will always
  show exactly what shipped.
- **If a release run fails before PyPI upload**, fix forward: bump to the next
  patch and re-tag. Don't try to reuse a tag.

---

## Known follow-up: test suite consolidation

The CI workflow ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) runs
only the **self-contained** test modules. Three modules (`test_m2m`,
`test_scaffold`, `verify_detailed_logs`) require an external project's
`DJANGO_SETTINGS_MODULE`, and `test_defaults_and_urls` has a known harness issue.
Until those are made standalone (or moved behind a proper Django test settings
module), CI is informational — don't mark it a *required* check in branch
protection yet.

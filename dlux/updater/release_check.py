import argparse
import ast
import json
import sys
import os
from pathlib import Path
import subprocess
import urllib.request

from packaging.version import InvalidVersion, Version

from .manifest import validate_local_release_manifest


#: Channels a tag may publish to. A tag classifies itself; there is no keyword,
#: no branch convention and no workflow input that can override it.
STABLE = "stable"
BETA = "beta"


# AlterModelOptions is metadata-only (permissions, ordering, verbose_name, ...) —
# it makes no schema change, and permission rows are synced by the post_migrate
# signal the inline updater's `migrate` step triggers. So it is inline-safe.
ALLOWED_MIGRATION_OPERATIONS = frozenset({"CreateModel", "AddField", "AddIndex", "AlterModelOptions"})

# SeparateDatabaseAndState is inline-safe ONLY with an empty `database_operations`:
# that combination runs nothing against the database by construction, so it cannot
# rewrite a column or break a rollback to the previous release. It is the honest
# way to express a state-only change such as adding a value to a field's `choices`,
# which Django validates in Python and never in the schema.
#
# This is checkable where a bare AlterField is not. Django serialises the WHOLE
# field into the migration, so a choices edit and a max_length shrink look
# identical in the file — there is no way to tell them apart statically, which is
# why AlterField stays rejected outright.
SEPARATE_STATE_OPERATION = "SeparateDatabaseAndState"


def _release_tags():
    """Merged ``v*`` tags, newest first, ordered by PEP 440.

    Not by ``--sort=-version:refname``: git's version sort has no concept of a
    prerelease unless ``versionsort.suffix`` is configured, and a repository
    where it is not will happily place ``v1.9.0b1`` *above* ``v1.9.0``. Every
    baseline in this module is "the newest release that did X", so getting that
    order wrong picks the wrong baseline silently.
    """
    completed = subprocess.run(
        ["git", "tag", "--merged", "HEAD"],
        check=True, capture_output=True, text=True,
    )
    found = []
    for line in completed.stdout.splitlines():
        tag = line.strip()
        if not tag.startswith("v"):
            continue
        try:
            found.append((Version(tag[1:]), tag))
        except InvalidVersion:
            continue
    return [tag for _version, tag in sorted(found, reverse=True)]


def _previous_release_tag(current_tag, *, stable_only=True):
    """The tag this release's migrations are validated against.

    ``stable_only`` by default, and that is the whole point. Validating 1.9.0b2
    against 1.9.0b1 would check only the migrations added between the two betas
    and silently bless everything b1 introduced. A beta is a candidate for the
    stable release that follows it, so the span that has to be inline-safe is the
    one a stable deployment will actually traverse: from the last stable release
    to here.
    """
    for tag in _release_tags():
        if tag == current_tag:
            continue
        try:
            version = Version(tag[1:])
        except InvalidVersion:
            continue
        if stable_only and version.is_prerelease:
            continue
        return tag
    raise RuntimeError(
        "An inline-safe release requires a previous stable v* tag for migration comparison."
    )


def _changed_migrations(base_tag):
    changed = subprocess.run(
        ["git", "diff", "--name-only", base_tag, "--", "dlux/migrations/*.py"],
        check=True,
        capture_output=True,
        text=True,
    )
    untracked = subprocess.run(
        [
            "git", "ls-files", "--others", "--exclude-standard", "--",
            "dlux/migrations/*.py",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    paths = {
        line.strip()
        for output in (changed.stdout, untracked.stdout)
        for line in output.splitlines()
        if line.strip()
    }
    return [Path(path) for path in sorted(paths)]


def _migration_operations(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "operations" for target in node.targets):
            continue
        if not isinstance(node.value, (ast.List, ast.Tuple)):
            raise RuntimeError(f"{path}: Migration.operations must be a literal list for release validation.")
        return node.value.elts
    raise RuntimeError(f"{path}: Migration.operations was not found.")


def _operation_name(call):
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
        return ""
    if not isinstance(call.func.value, ast.Name) or call.func.value.id != "migrations":
        return ""
    return call.func.attr


def _add_field_is_safe(call):
    field = next((keyword.value for keyword in call.keywords if keyword.arg == "field"), None)
    if not isinstance(field, ast.Call):
        return False
    keywords = {keyword.arg: keyword.value for keyword in field.keywords}
    nullable = isinstance(keywords.get("null"), ast.Constant) and keywords["null"].value is True
    # A Python ``default`` only backfills existing rows during migration; Django
    # normally drops it from the database column afterwards. The previous release
    # can still INSERT without the new field during rollback, so a NOT NULL field
    # is inline-safe only with a persistent database default.
    return nullable or "db_default" in keywords


def _separate_state_is_safe(operation):
    """True only when `database_operations` is present and an empty list."""
    for keyword in operation.keywords:
        if keyword.arg == "database_operations":
            return isinstance(keyword.value, ast.List) and not keyword.value.elts
    # Positional form is `SeparateDatabaseAndState(database_operations, ...)`.
    if operation.args:
        first = operation.args[0]
        return isinstance(first, ast.List) and not first.elts
    return False


def _manifest_at_tag(tag):
    """The release manifest as it was published at `tag`, or None."""
    completed = subprocess.run(
        ["git", "show", f"{tag}:dlux/release-manifest.json"],
        capture_output=True, text=True,
    )
    if completed.returncode != 0:
        return None
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None


def _forbids_inline(manifest):
    """True when that release required a project image rebuild, either schema."""
    if manifest.get("schema_version") == 2:
        install = manifest.get("install") or {}
        return install.get("inline") != "allowed"
    return not manifest.get("inline_safe", False)


def _carries_migrations(manifest):
    """True when that release's own hop changed the database or model state."""
    if manifest.get("schema_version") == 2:
        effect = (manifest.get("migrations") or {}).get("effect")
        return bool(effect) and effect != "none"
    return bool(manifest.get("migration_effect")) and manifest.get("migration_effect") != "none"


def expected_migration_baseline():
    """The highest published version that introduced a migration.

    A manifest's `migrations.effect` describes one hop — its own. A deployment
    several releases behind reads only the target's manifest, so an update from
    1.8.6 to 1.8.11 reported `none` while actually crossing migration 0020, which
    shipped in 1.8.9. Nothing warned that the update carried a migration.

    Declaring the floor makes the span knowable from the target alone: any active
    version below it is crossing at least one migration. Same shape as
    `expected_image_baseline()`, and derived rather than remembered.
    """
    for tag in _release_tags():
        manifest = _manifest_at_tag(tag)
        if manifest and _carries_migrations(manifest):
            return tag[1:]
    return None


def validate_declared_migration_effect(manifest, base_tag):
    """Refuse a manifest that claims no migrations while shipping one.

    `migrations.effect` is the release's own statement about its own hop, and
    every downstream decision trusts it: whether the update is inline-safe,
    whether the operator is told to take a backup, and — through
    `migration_baseline` — whether a deployment several versions behind learns
    that its span crosses a migration at all.

    Nothing checked it against the repository. The floor validator below only
    compares declared-vs-computed *baselines*, and a release that adds a
    migration while declaring `none` satisfies it trivially: it is not treated as
    carrying migrations, so it is measured against the previous release's floor,
    which it meets. This is the check that reads the actual migration files.
    """
    changed = [path for path in _changed_migrations(base_tag) if path.name != "__init__.py"]
    if not changed:
        return []
    if _carries_migrations(manifest):
        return []
    names = ", ".join(sorted(path.name for path in changed))
    return [
        f"This release adds migrations ({names}) but the manifest declares "
        "migrations.effect 'none'. Declare the real effect, or the update will "
        "tell operators it changes nothing while it migrates their database."
    ]


def validate_migration_baseline(manifest):
    """Refuse a manifest whose declared migration floor is below the computed one."""
    expected = expected_migration_baseline()
    requires = manifest.get("requires") or {}
    declared = str(
        requires.get("migration_baseline") or manifest.get("migration_baseline") or ""
    ).lstrip(">=").strip()
    if _carries_migrations(manifest):
        # This release introduces one, so it is its own floor.
        return []
    if not expected:
        return []
    if not declared:
        return [
            f"v{expected} introduced a migration, so this manifest must declare "
            f"requires.migration_baseline >={expected}"
        ]
    if Version(declared) < Version(expected):
        return [
            f"requires.migration_baseline is {declared} but v{expected} introduced a "
            f"migration; the floor must not go backwards"
        ]
    return []


def expected_image_baseline():
    """The floor this release should declare, computed from published history.

    RELEASING.md used to make this an authoring convention: "once any release
    ships inline_safe: false, carry image_baseline on every subsequent manifest
    until the next image-required release". A rule a human has to remember on a
    release day is a rule that eventually gets missed, and missing it lets a box
    several versions behind skip the image rebuild entirely.

    So derive it: the highest published version that forbade an inline install.
    Returns None when there is no outstanding image dependency.
    """
    for tag in _release_tags():
        manifest = _manifest_at_tag(tag)
        if manifest and _forbids_inline(manifest):
            return tag[1:]
    return None


def validate_image_baseline(manifest):
    """Refuse a manifest whose declared floor is below the computed one."""
    expected = expected_image_baseline()
    if not expected:
        return []
    requires = manifest.get("requires") or {}
    declared = str(requires.get("baked_image") or manifest.get("image_baseline") or "").lstrip(">=").strip()
    if not declared:
        return [
            f"v{expected} required an image rebuild, so this manifest must declare "
            f"requires.baked_image >={expected}"
        ]
    if Version(declared) < Version(expected):
        return [
            f"requires.baked_image is {declared} but v{expected} required an image "
            f"rebuild; the floor must not go backwards"
        ]
    return []


def classify_tag(tag, *, manifest_version=""):
    """Turn a Git tag into a publication decision, or refuse it.

    The tag is the only input. There is no commit-message keyword and no
    workflow toggle, because a publication that can be steered by prose is one
    that eventually gets steered by a typo.

    Refused outright: anything ``packaging`` will not parse, development
    releases, local versions, post-releases, and epochs. Each of those either
    cannot be published to PyPI as intended or would land in the index ordered
    somewhere no one expects.
    """
    raw = str(tag or "").strip()
    if not raw.startswith("v"):
        raise RuntimeError(f"Release tag {raw!r} must start with 'v'.")
    text = raw[1:]
    try:
        version = Version(text)
    except InvalidVersion as exc:
        raise RuntimeError(f"Release tag {raw!r} is not a valid PEP 440 version.") from exc
    if str(version) != text:
        # `v1.9.0.b1`, `v1.9.0-beta1` and `V1.09` all parse but are not the
        # canonical spelling. Accepting them means the tag, the wheel filename
        # and the changelog heading stop being the same string.
        raise RuntimeError(
            f"Release tag {raw!r} is not canonical; tag v{version} instead."
        )
    if version.is_devrelease:
        raise RuntimeError(f"Release tag {raw!r} is a development release and is never published.")
    if version.local:
        raise RuntimeError(f"Release tag {raw!r} carries a local version segment.")
    if version.is_postrelease:
        raise RuntimeError(
            f"Release tag {raw!r} is a post-release. Publish a new patch version instead: "
            "a post-release cannot carry code changes."
        )
    if version.epoch:
        raise RuntimeError(f"Release tag {raw!r} declares an epoch, which this project does not use.")
    if manifest_version:
        try:
            declared = Version(str(manifest_version))
        except InvalidVersion as exc:
            raise RuntimeError(
                f"dlux/release-manifest.json declares an invalid version {manifest_version!r}."
            ) from exc
        if declared != version or str(declared) != text:
            raise RuntimeError(
                f"Release tag {raw!r} does not match dlux/release-manifest.json "
                f"({manifest_version}). Bump the manifest before tagging."
            )
    prerelease = bool(version.is_prerelease)
    return {
        "tag": raw,
        "version": text,
        "channel": BETA if prerelease else STABLE,
        "prerelease": prerelease,
        # GitHub's "latest release" pointer. A prerelease must never claim it:
        # that pointer is what an operator and every download link resolve to.
        "make_latest": not prerelease,
    }


def changelog_section(version, path="CHANGELOG.md"):
    """The body of this exact version's ``## vX.Y.Z`` section.

    Matched on the whole heading, not a prefix. ``^## v1.8.14`` also matches
    ``## v1.8.14b1``, so a stable release could have published its beta's notes —
    the mistake is invisible because the output looks like release notes either
    way.
    """
    wanted = f"## v{version}"
    body = []
    grabbing = False
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.rstrip()
        if stripped.startswith("## "):
            if grabbing:
                break
            grabbing = stripped == wanted
            continue
        if grabbing:
            body.append(line)
    return "\n".join(body).strip()


PYPI_JSON_URL = "https://pypi.org/pypi/django-lux/json"


def requires_beta_first(version):
    """True for a stable release that opens a new line: X.Y.0.

    A patch may still ship stable directly — a hotfix held back for a beta cycle
    is usually worse than the risk it avoids. What must never happen is a new
    minor or major reaching the stable channel before anyone ran it as a beta.
    """
    parsed = Version(str(version))
    if parsed.is_prerelease:
        return False
    return (tuple(parsed.release) + (0, 0, 0))[2] == 0


def prerelease_tags_for(version, tags):
    """The ``vX.Y.ZbN``/``rcN`` tags that are prereleases of exactly ``version``."""
    base = Version(Version(str(version)).base_version)
    found = []
    for tag in tags:
        tag = str(tag).strip()
        if not tag.startswith("v"):
            continue
        try:
            parsed = Version(tag[1:])
        except InvalidVersion:
            continue
        if parsed.is_prerelease and not parsed.is_devrelease and Version(parsed.base_version) == base:
            found.append(tag)
    return found


def published_prereleases_on_pypi(version, *, opener=urllib.request.urlopen):
    """Prereleases of ``version`` that PyPI serves with at least one non-yanked file."""
    base = Version(Version(str(version)).base_version)
    request = urllib.request.Request(
        PYPI_JSON_URL,
        headers={"Accept": "application/json", "User-Agent": "django-lux-release-check/1"},
    )
    with opener(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    published = set()
    for raw, files in (data.get("releases") or {}).items():
        try:
            parsed = Version(raw)
        except InvalidVersion:
            continue
        if not parsed.is_prerelease or Version(parsed.base_version) != base:
            continue
        if any(isinstance(item, dict) and not item.get("yanked") for item in files or []):
            published.add(parsed)
    return published


def validate_beta_first(version, *, tags=None, fetch_published=published_prereleases_on_pypi):
    """Refuse a new minor or major stable release that no published beta preceded.

    Enforces release_channels_plan.md §1 — 1.9.0 must not first appear as stable
    — in CI rather than in someone's memory. Two conditions, both required: a
    prerelease tag of this exact version is in the tagged commit's history, and
    PyPI actually serves it. A tag whose release job died before upload was never
    installable, so it was never tested either.

    Deliberately narrower than the plan's final gate. It proves a beta was
    published, not that it passed acceptance; recording acceptance evidence and
    requiring it (plan §3.5/§3.8) is still ahead. PyPI being unreachable refuses
    rather than waves the release through.
    """
    if not requires_beta_first(version):
        return []
    tags = _release_tags() if tags is None else list(tags)
    betas = prerelease_tags_for(version, tags)
    if not betas:
        return [
            f"v{version} opens a new release line and must be published as a beta first: "
            f"no v{version}bN or v{version}rcN tag is in this commit's history."
        ]
    try:
        live = set(fetch_published(version))
    except Exception as exc:
        return [
            f"Could not confirm on PyPI that a beta of v{version} was published ({exc}). "
            "Refusing to publish stable without that evidence; re-run once PyPI is reachable."
        ]
    if not {Version(tag[1:]) for tag in betas} & live:
        names = ", ".join(sorted(betas, key=lambda tag: Version(tag[1:])))
        return [
            f"v{version} has beta tags ({names}) but PyPI serves none of them. "
            "A beta that never reached PyPI was never installable, so it was never tested."
        ]
    return []


def validate_inline_migrations(base_tag):
    errors = []
    for path in _changed_migrations(base_tag):
        if path.name == "__init__.py":
            continue
        for operation in _migration_operations(path):
            name = _operation_name(operation)
            if name == SEPARATE_STATE_OPERATION:
                if not _separate_state_is_safe(operation):
                    errors.append(
                        f"{path}: {SEPARATE_STATE_OPERATION} is inline-safe only with "
                        f"an empty database_operations list"
                    )
            elif name not in ALLOWED_MIGRATION_OPERATIONS:
                errors.append(f"{path}: migration operation {name or '<dynamic>'} is not inline-safe")
            elif name == "AddField" and not _add_field_is_safe(operation):
                errors.append(f"{path}: AddField must be nullable or define db_default")
    if errors:
        raise RuntimeError("\n".join(errors))
    return True


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-tag")
    parser.add_argument(
        "--classify", action="store_true",
        help="Validate the tag and emit its publication decision as JSON.",
    )
    parser.add_argument(
        "--github-output", action="store_true",
        help="Also append the classification to $GITHUB_OUTPUT.",
    )
    args = parser.parse_args(argv)
    manifest = validate_local_release_manifest()
    current_tag = os.getenv("GITHUB_REF_NAME") or f"v{manifest['version']}"
    base_tag = args.base_tag or None

    if args.classify:
        try:
            decision = classify_tag(current_tag, manifest_version=manifest["version"])
        except RuntimeError as exc:
            print(f"::error::{exc}", file=sys.stderr)
            return 1
        notes = changelog_section(decision["version"])
        if not notes:
            print(
                f"::error::CHANGELOG.md has no '## v{decision['version']}' section. "
                "Add it before tagging.",
                file=sys.stderr,
            )
            return 1
        errors = validate_beta_first(decision["version"])
        if errors:
            for error in errors:
                print(f"::error::{error}", file=sys.stderr)
            return 1
        print(json.dumps(decision, sort_keys=True))
        output = os.getenv("GITHUB_OUTPUT")
        if args.github_output and output:
            with open(output, "a", encoding="utf-8") as handle:
                for key, value in decision.items():
                    handle.write(f"{key}={json.dumps(value) if isinstance(value, bool) else value}\n")
        return 0

    if manifest["inline_safe"]:
        base_tag = base_tag or _previous_release_tag(current_tag)
        validate_inline_migrations(base_tag)

    # Both floors are derived from published history rather than remembered on
    # release day. `validate_image_baseline` existed but was never called from
    # here, so the convention it replaced was still only a convention.
    raw = json.loads(
        (Path(__file__).resolve().parents[1] / "release-manifest.json").read_text(encoding="utf-8")
    )
    errors = validate_image_baseline(raw) + validate_migration_baseline(raw)
    if base_tag:
        errors += validate_declared_migration_effect(raw, base_tag)
    if errors:
        for error in errors:
            print(f"::error::{error}", file=sys.stderr)
        return 1

    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

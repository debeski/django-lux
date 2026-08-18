import argparse
import ast
import json
import os
from pathlib import Path
import subprocess

from packaging.version import Version

from .manifest import validate_local_release_manifest


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


def _previous_release_tag(current_tag):
    completed = subprocess.run(
        ["git", "tag", "--merged", "HEAD", "--sort=-version:refname"],
        check=True,
        capture_output=True,
        text=True,
    )
    tags = [line.strip() for line in completed.stdout.splitlines() if line.startswith("v")]
    for tag in tags:
        if tag != current_tag:
            return tag
    raise RuntimeError("An inline-safe release requires a previous v* tag for migration comparison.")


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
    completed = subprocess.run(
        ["git", "tag", "--merged", "HEAD", "--sort=-version:refname"],
        check=True, capture_output=True, text=True,
    )
    for tag in (line.strip() for line in completed.stdout.splitlines()):
        if not tag.startswith("v"):
            continue
        manifest = _manifest_at_tag(tag)
        if manifest and _forbids_inline(manifest):
            return tag.lstrip("v")
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
    args = parser.parse_args(argv)
    manifest = validate_local_release_manifest()
    current_tag = os.getenv("GITHUB_REF_NAME") or f"v{manifest['version']}"
    if manifest["inline_safe"]:
        validate_inline_migrations(args.base_tag or _previous_release_tag(current_tag))
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

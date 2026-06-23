import argparse
import ast
import json
import os
from pathlib import Path
import subprocess

from .manifest import validate_local_release_manifest


ALLOWED_MIGRATION_OPERATIONS = frozenset({"CreateModel", "AddField", "AddIndex"})


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
    return nullable or "default" in keywords


def validate_inline_migrations(base_tag):
    errors = []
    for path in _changed_migrations(base_tag):
        if path.name == "__init__.py":
            continue
        for operation in _migration_operations(path):
            name = _operation_name(operation)
            if name not in ALLOWED_MIGRATION_OPERATIONS:
                errors.append(f"{path}: migration operation {name or '<dynamic>'} is not inline-safe")
            elif name == "AddField" and not _add_field_is_safe(operation):
                errors.append(f"{path}: AddField must be nullable or define a default")
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

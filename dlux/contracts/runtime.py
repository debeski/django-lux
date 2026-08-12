"""The machine-readable spec of the DjangoLux runtime volume.

``runtime_contract.json`` is the single source of truth for the layout Composer
writes and the supervisor reads: which directories exist, what ``active.json``
contains, what a generation bump means, and which side owns each file.

Before v1.8.0 the layout was an implicit detail of ``dlux/updater/runtime.py``,
because only DjangoLux ever wrote it. Composer now stages and activates releases
(see ``docs/updater-consolidation.md``), so it is a cross-repo interface and has
to be written down. This mirrors ``dlux/stack_contract.py`` exactly, including
how it travels: ``manage.py dlux_runtime_contract`` prints the contract for the
release that is *actually running*, so a consumer never diffs against whatever
happened to be baked into an image.

Adding a directory or an optional key is backwards-compatible. Renaming one, or
changing what an existing key means, requires a ``schema_version`` bump on both
sides.
"""
import json
from pathlib import Path

from .. import __version__

CONTRACT_PATH = Path(__file__).resolve().parent / "runtime.json"


def load_contract():
    """Return the contract dict, stamped with the running dlux version.

    The version is added at load time rather than stored in the file, so it
    reflects the release actually imported — the same discipline
    ``stack_contract.load_contract()`` and the doctor report use.
    """
    data = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    data["dlux_version"] = __version__
    return data


def diff_layout(contract, present_dirs):
    """Compare a deployment's runtime directories against the contract.

    ``present_dirs`` is an iterable of directory names directly under the runtime
    root. Returns human-readable drift strings; empty means the layout matches.
    Extra directories are not flagged — a deployment may hold artefacts the
    contract does not describe.
    """
    drift = []
    have = set(present_dirs)
    for name, spec in sorted(contract["directories"].items()):
        if spec.get("required") and name not in have:
            drift.append(f"missing runtime directory '{name}' ({spec.get('purpose', '')})".strip())
    return drift


def diff_active(contract, active):
    """Validate an ``active.json`` payload against the contract.

    Returns drift strings. An empty/absent pointer is valid — it means the
    release baked into the image is in force — so ``{}`` yields no drift.
    """
    if not active:
        return []
    drift = []
    spec = contract["active_json"]
    if not isinstance(active, dict):
        return ["active.json is not a JSON object"]
    for key in spec["required_keys"]:
        if key not in active:
            drift.append(f"active.json is missing '{key}'")
    source = active.get("source")
    if source is not None and source not in spec["source_values"]:
        drift.append(
            f"active.json source '{source}' is not one of {sorted(spec['source_values'])}"
        )
    if source == "volume" and not str(active.get("path") or "").strip():
        drift.append("active.json source is 'volume' but path is empty")
    if source == "image" and str(active.get("path") or "").strip():
        drift.append("active.json source is 'image' but a release path is set")
    generation = active.get("generation")
    if generation is not None and (not isinstance(generation, int) or generation < 0):
        drift.append("active.json generation must be a non-negative integer")
    return drift


def writer_of(contract, filename):
    """Which side owns a state file: 'dlux', 'composer', or None if unknown."""
    return contract["state_files"].get(filename, {}).get("writer")

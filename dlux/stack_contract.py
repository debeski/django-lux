"""The machine-readable spec of the expected DjangoLux Compose stack.

`stack-contract.json` is the single source of truth for the generated stack's
shape: which services exist, which networks each joins, which network is the
only published ingress, where the Docker socket may be mounted, and the runtime
volume's read/write split. `ComposeNetworkTopologyTests` asserts the scaffold
satisfies it; Composer's `composer check` drift-diff checks a *deployed*
compose.yml against it, fetched version-correct through the `dlux_stack_contract`
management command (so the contract always travels with the dlux version that is
actually running, not whatever was baked into the image).

Adding services/keys is backwards-compatible; renaming a field or the meaning of
an invariant requires a `schema_version` bump.
"""
import json
from pathlib import Path

from . import __version__

CONTRACT_PATH = Path(__file__).resolve().parent / "stack_contract.json"

_ALL_NETWORKS = frozenset({"frontend", "egress", "internal", "docker_proxy"})


def load_contract():
    """Return the contract dict, stamped with the running dlux version.

    The version is added at load time (never stored in the file) so it reflects
    the release actually imported — the same discipline the doctor report uses.
    """
    data = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    data["dlux_version"] = __version__
    return data


def _service_networks(contract):
    return {name: set(spec.get("networks", [])) for name, spec in contract["services"].items()}


def diff_attachments(contract, attachments):
    """Compare a parsed ``{service: {networks}}`` map against the contract.

    Returns a list of human-readable drift strings (empty when the deployment
    matches). Kept dependency-free and pure so both the scaffold tests and an
    external consumer (Composer) can share the exact comparison. Only the
    contract's own services are checked; extra services a deployment adds are not
    flagged (a project may run its own sidecars).
    """
    drift = []
    expected = _service_networks(contract)
    for service, want in sorted(expected.items()):
        if service not in attachments:
            drift.append(f"missing service '{service}'")
            continue
        have = attachments[service]
        if have != want:
            drift.append(
                f"service '{service}' joins {sorted(have) or ['<none>']}, "
                f"contract expects {sorted(want)}"
            )
    unknown = {
        net
        for networks in attachments.values()
        for net in networks
        if net not in _ALL_NETWORKS
    }
    for net in sorted(unknown):
        drift.append(f"service attached to undeclared network '{net}'")
    # The ingress/egress isolation only holds while no service bridges the two
    # public bridges. Checked across ALL services (contract and project-added),
    # because a sidecar on both networks collapses the boundary just as badly.
    if contract.get("invariants", {}).get("frontend_egress_disjoint"):
        for service in sorted(attachments):
            if {"frontend", "egress"} <= attachments[service]:
                drift.append(
                    f"service '{service}' bridges frontend and egress; the two public "
                    "networks must stay disjoint"
                )
    return drift


def retired_command_modules(contract):
    """``{retired module: current module}`` for dlux-owned service entrypoints.

    Both the SMTP relay and the runtime supervisor moved out of per-project
    ``tools/`` files into the package, so fixes to them travel with the dlux
    version rather than being frozen at whatever a project was scaffolded with.
    A deployment generated before either move keeps invoking its own stale copy
    until the Compose command is rewritten — which is Composer's job, not a
    manual edit.
    """
    return dict(contract.get("invariants", {}).get("retired_command_modules", {}))


def diff_command_modules(contract, service_commands):
    """Compare a parsed ``{service: command string}`` map against the contract.

    Returns ``[(service, retired_module, current_module), ...]`` for every service
    still invoking a retired entrypoint — everything Composer needs to report the
    drift and to repair it by substitution. Pure and dependency-free so the check
    and the fix share one definition of "wrong".
    """
    retired = retired_command_modules(contract)
    drift = []
    for service, command in sorted((service_commands or {}).items()):
        text = command if isinstance(command, str) else " ".join(map(str, command or []))
        for old_module, new_module in retired.items():
            if old_module in text:
                drift.append((service, old_module, new_module))
    return drift


def fix_command_modules(contract, contents):
    """Rewrite retired entrypoints in a Compose file's text, idempotently."""
    for old_module, new_module in retired_command_modules(contract).items():
        contents = contents.replace(old_module, new_module)
    return contents


def removed_services_present(contract, service_names):
    """Advisory list for services DjangoLux used to ship and has since dropped
    but are still running in a deployment.

    Distinct from ``diff_attachments`` (which ignores extra services, since a
    project may run its own sidecars): ``removed_services`` names services the
    stack *once included*, so Composer's check can tell an operator they are now
    safe to remove rather than silently ignoring them.
    """
    removed = contract.get("removed_services", {})
    advisories = []
    for name in sorted(set(service_names) & set(removed)):
        info = removed[name]
        advisories.append(
            f"'{name}' was removed from the DjangoLux stack in {info.get('since', '?')} "
            f"({info.get('reason', '')}) and can be dropped."
        )
    return advisories

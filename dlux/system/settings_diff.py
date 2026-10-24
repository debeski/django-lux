"""Change set between the live system settings and an uploaded config file.

The Options page import is a different operation from the first-launch one.
First-launch fills an empty form: take everything, nothing to lose. This one
runs against a populated, live system, so the rules are inverted:

* nothing is applied until the operator says so — this module only *describes*
  the difference, it never writes;
* the default for every change is **keep the current value**, so an import can
  only add what was explicitly ticked;
* a key **absent** from the file means *leave the current value alone*, never
  "reset to default". `normalize_system_settings_import_payload` already drops
  absent keys rather than defaulting them, so that falls out naturally — the
  change set reports them separately so the operator can see what the file did
  not cover.

Both sides are normalised through the same pair of functions
(`export_system_settings_payload` for current, the import normaliser for the
file), so formatting differences cannot show up as false changes.
"""
from copy import deepcopy
from functools import lru_cache

from .constants import SYSTEM_SETTINGS_EXPORT_FIELDS

# A storage field no single form control renders, mapped to the step that edits it.
UNOWNED_FIELD_STEPS = {'extra_config': 'extras', 'tables_config': 'tables'}


@lru_cache(maxsize=1)
def review_groups():
    """Exported fields grouped by the setup step that edits them, in step order.

    Ownership is the settings layout's own (`SystemSettingsForm.field_steps`, the
    map single-step saves use), so the review reads in the steps the operator
    knows, labelled with the step tiles' strings.
    """
    from ..forms import SystemSettingsForm
    from .constants import SETUP_STEP_SLUGS

    owners = SystemSettingsForm().field_steps
    by_step = {}
    for field in SYSTEM_SETTINGS_EXPORT_FIELDS:
        slug = SETUP_STEP_SLUGS[owners[field]] if field in owners else UNOWNED_FIELD_STEPS[field]
        by_step.setdefault(slug, []).append(field)
    return tuple(
        (slug, f'system_settings_{slug}', tuple(by_step[slug]))
        for slug in SETUP_STEP_SLUGS if slug in by_step
    )


def field_group(field):
    return next(slug for slug, _label, fields in review_groups() if field in fields)


# Nested structures with their own builder UI. A two-column value diff of these
# is unreadable, so they are all-or-nothing with a plain-language summary.
ATOMIC_FIELDS = frozenset({
    'sidebar_config', 'navbar_config', 'log_config', 'profile_config',
    'languages', 'system_names', 'translations_override', 'default_fonts',
    'extra_config', 'allowed_themes', 'allowed_fonts', 'homepage_config',
})

# Flat key/value config blobs. Worth expanding into one row per key, so a
# one-setting change does not read as "the whole email config differs".
MAPPING_FIELDS = frozenset({
    'email_config', 'titlebar_config', 'notification_config', 'login_config',
    'backup_config', 'client_ip_config', 'search_config',
})

def _kind(field):
    if field in ATOMIC_FIELDS:
        return 'atomic'
    if field in MAPPING_FIELDS:
        return 'mapping'
    return 'scalar'


def summarize(current, incoming):
    """Plain-language counts for an atomic value.

    Deliberately generic. A bespoke summariser per builder would drift the
    moment a builder changes shape; counts of added/removed/changed keys or
    items are always true and always readable.
    """
    if isinstance(current, dict) and isinstance(incoming, dict):
        cur_keys, inc_keys = set(current), set(incoming)
        return {
            'added': sorted(inc_keys - cur_keys),
            'removed': sorted(cur_keys - inc_keys),
            'changed': sorted(k for k in cur_keys & inc_keys if current[k] != incoming[k]),
        }
    if isinstance(current, list) and isinstance(incoming, list):
        # Lists of scalars diff by membership; lists of objects only by count,
        # because their identity is builder-specific.
        if all(not isinstance(v, (dict, list)) for v in current + incoming):
            cur_set, inc_set = set(current), set(incoming)
            return {
                'added': sorted(inc_set - cur_set),
                'removed': sorted(cur_set - inc_set),
                'changed': [],
            }
        return {'count_current': len(current), 'count_incoming': len(incoming)}
    return {}


def field_labels():
    """Map export keys to the labels the System Settings form already uses.

    The review must read in the operator's language. Rendering the raw export
    key left every row in English while the group headings were translated —
    the settings form has done this work already, so borrow it rather than
    inventing a second set of strings that would drift.

    Mapping fields are flattened by the form (`email_config.host` is the form's
    `email_config_host`), so sub-keys are looked up under that name.
    """
    try:
        from ..forms import SystemSettingsForm
        form = SystemSettingsForm()
    except Exception:
        # A label is a nicety; never let it break the review.
        return {}
    return {name: str(field.label) for name, field in form.fields.items() if field.label}


def _label_for(labels, field, sub_key=None):
    if sub_key:
        return labels.get(f'{field}_{sub_key}') or f'{labels.get(field, field)} · {sub_key}'
    return labels.get(field, field)


def build_change_set(current_settings, incoming_settings, source=None):
    """Describe what an import would change. Never mutates either side.

    `incoming_settings` must already be normalised, and must contain only the
    keys the file actually carried — that is what `leave alone` depends on.
    """
    from .settings_patch import merge_settings_patch
    labels = field_labels()
    groups = []
    for key, label_key, fields in review_groups():
        changes = []
        for field in fields:
            if field not in incoming_settings:
                continue
            if field in {
                'home_url', 'public_root', 'public_root_split_enabled',
                'public_root_url', 'public_root_theme', 'public_root_title',
                'public_root_meta_description', 'show_titlebar_on_public',
                'show_sidebar_on_public',
            } and 'homepage_config' in incoming_settings:
                continue
            current = current_settings.get(field)
            incoming_patch = incoming_settings[field]
            incoming = merge_settings_patch(current, incoming_patch)
            if current == incoming:
                continue

            kind = _kind(field)
            if kind == 'mapping' and isinstance(current, dict) and isinstance(incoming, dict):
                for sub in sorted(incoming_patch):
                    if (
                        field == 'titlebar_config'
                        and 'search_config' in incoming_settings
                        and sub in {'global_search_mode', 'global_search_include_data'}
                    ):
                        continue
                    cur_v, inc_v = current.get(sub), incoming.get(sub)
                    if cur_v == inc_v or sub not in incoming:
                        continue
                    changes.append({
                        'field': field,
                        'sub_key': sub,
                        'label': _label_for(labels, field, sub),
                        'kind': 'scalar',
                        'current': deepcopy(cur_v),
                        'incoming': deepcopy(inc_v),
                        'patch': deepcopy(incoming_patch[sub]),
                    })
                continue

            entry = {
                'field': field,
                'sub_key': None,
                'label': _label_for(labels, field),
                'kind': kind,
                'current': deepcopy(current),
                'incoming': deepcopy(incoming),
                'patch': deepcopy(incoming_patch),
            }
            if kind == 'atomic':
                entry['summary'] = summarize(current, incoming)
            changes.append(entry)

        if changes:
            groups.append({'key': key, 'label_key': label_key, 'changes': changes})

    known = set(SYSTEM_SETTINGS_EXPORT_FIELDS)
    return {
        'source': dict(source or {}),
        'groups': groups,
        'change_count': sum(len(g['changes']) for g in groups),
        # In the file but not a setting this version knows — a newer export.
        'unknown_keys': sorted(set(incoming_settings) - known),
        # Known here but absent from the file. Left alone, never reset; listed
        # so the operator can see the file did not cover them.
        'absent_keys': sorted(known - set(incoming_settings)),
    }


def selected_settings(change_set, selections, current_settings):
    """The settings dict to apply, given the operator's ticked changes.

    `selections` are `"<field>"` or `"<field>:<sub_key>"` tokens. Anything not
    ticked is omitted entirely, so applying the result can only move the values
    the operator chose.

    Mapping fields are rebuilt from the *current* value with the ticked keys
    overlaid. Sending only the ticked keys would post a config blob missing
    every key the operator left alone — ticking one SMTP host would wipe the
    port, the credentials and the from-address.
    """
    chosen = set(selections or ())
    out = {}
    for group in change_set.get('groups', ()):
        for change in group['changes']:
            field, sub = change['field'], change.get('sub_key')
            token = f'{field}:{sub}' if sub else field
            if token not in chosen:
                continue
            if sub is None:
                out[field] = deepcopy(change.get('patch', change['incoming']))
                continue
            if field not in out:
                base = current_settings.get(field)
                out[field] = deepcopy(base) if isinstance(base, dict) else {}
            from .settings_patch import merge_settings_patch
            out[field][sub] = merge_settings_patch(out[field].get(sub), change.get('patch', change['incoming']))
    return out

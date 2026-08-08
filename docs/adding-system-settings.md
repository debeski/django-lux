# Adding a System Setting (A → Z)

The definitive procedure for adding a new **first-class** DjangoLux system setting:
one that lives in the `SystemSettings` singleton, is editable from the Setup wizard
and the Options → System Settings form, survives export/import and `config.json`
bootstrap, and is readable app-wide through `get_system_config()`.

---

## 0. First decide: do you even need a first-class setting?

There are **two** ways to add configuration, and picking the wrong one wastes hours.

| You want… | Use | Where it's documented |
|:--|:--|:--|
| A **project-owned** flag/value for *your* app (a downstream project using dlux) | The `extra_config['app'][<namespace>]` app-config namespace + `register_app_settings()` | `reference.md` → "App-owned **system** config" |
| A **framework-level** setting that ships with dlux, belongs to a settings group (layout, auth, titlebar…), and is exposed to every project | The full pipeline **in this document** | this file |

If you are building on top of dlux in your own project, you almost always want the
**app-config namespace** — it needs zero framework edits, is superuser-guarded,
audit-logged, size-capped, and gives you an Options tile for free. Do **not** patch
the dlux internals below just to store one project flag. The rest of this document
is for changes to the `dlux` package itself.

---

## 1. The mental model

A setting has up to **three representations**. Understanding which you need drives
everything else.

```
                    ┌─────────────────────────────────────────────────┐
   1. STORAGE       │  SystemSettings.<group>_config  (a JSON field)   │
                    │      e.g. layout_config = {"zebra_striping": …}  │
                    └─────────────────────────────────────────────────┘
                                        │
                    ┌───────────────────┴───────────────────┐
   2. FLAT KEY      │  optional legacy_flat mirror:          │
      (optional)    │  SystemSettings.zebra_striping property │  ← model attr + import alias
                    └───────────────────┬───────────────────┘
                                        │
                    ┌───────────────────┴───────────────────┐
   3. RUNTIME       │  get_system_config()["zebra_striping"] │  ← what the whole app reads
                    └────────────────────────────────────────┘
```

- **Every** setting lives inside a **group** JSON field on `SystemSettings`
  (`layout_config`, `auth_config`, `titlebar_config`, …). This is the source of truth.
- A setting is either **`legacy_flat`** (gets an auto-generated flat model property
  `SystemSettings.<name>`, a flat import alias, and flat form handling) or
  **JSON-only** (read/written only through the group dict). Pick `legacy_flat=True`
  for anything the Setup wizard / SystemSettingsForm edits as a top-level field
  (this is the common case). JSON-only keys need manual routing in a couple of
  places (§4, §5) — `options_style` / `show_audit_fields` are JSON-only examples.
- Runtime code reads the resolved value from **`get_system_config()`**, never from
  the model directly. `get_system_config()` merges three layers, in order:
  1. package defaults (`build_default_system_config()`)
  2. `settings.DLUX_CONFIG` (project code)
  3. the `SystemSettings` DB singleton (UI edits)

### The canonical module: `dlux/system/`

All group defaults, normalizers, and the typed schema live in `dlux.system`, split
so migration callables and Django startup stay import-safe:

| File | Owns | Import rule |
|:--|:--|:--|
| `system/constants.py` | choice tuples, `*_VALUES` sets, `SYSTEM_SETTINGS_EXPORT_FIELDS` | leaf only |
| `system/defaults.py` | `default_<group>_config()` factories | **no** model/form/view/translations imports |
| `system/normalizers.py` | `normalize_<group>_config()` validators | leaf registries (themes/fonts) only, lazily |
| `system/schema.py` | `SYSTEM_SETTING_GROUPS` — the typed `SettingField`/`SettingGroup` table | imports defaults + normalizers |
| `system/registry.py` | derived lookups (`get_flat_config_fields()`, aliases, …) | imports schema |

Keeping `defaults.py`/`normalizers.py` import-free is not a style choice — migration
`0011` and startup call these; a stray model import there causes circular-import
crashes at `migrate` time. (Trap 7.)

---

## 2. Anatomy of the save/load pipeline

Trace one save so you know every function your key must pass through:

```
SystemSettingsForm (POST)
  → clean_<name>()                     validate/preserve per-step   (forms.py)
  → SystemSettingsForm.save()          packs group dict + normalizes (forms.py)
  → SystemSettings.<group>_config = …  persisted JSON

Export / Import / config.json bootstrap
  → normalize_system_settings_import_payload(payload)               (utils/import_export.py)
      → expand_system_config_groups()  flat ⇄ group reconciliation  (utils/config.py)
      → **whitelists to SYSTEM_SETTINGS_EXPORT_FIELDS**  ← drops anything not listed
  → apply_system_settings_import(instance, payload)                 (utils/import_export.py)
      → routes each field onto the instance (flat→group elif chains)

Read (everywhere)
  → get_system_config()                merges defaults+DLUX_CONFIG+DB              (utils/config.py)
```

The single most important line: **`normalize_system_settings_import_payload`
whitelists the payload to `SYSTEM_SETTINGS_EXPORT_FIELDS` and silently discards
every key not in that tuple.** Export, import, *and* first-launch `config.json`
bootstrap all pass through it. If your key isn't listed, it evaporates on any of
those paths.

---

## 3. The checklist (do every step)

Adding a `legacy_flat` boolean to the **layout** group (`show_audit_fields`) as the
worked example. Adapt the group/type as needed.

### Step 1 — Default (`system/defaults.py`)
Add the key to the group factory with its shipped default:
```python
def default_layout_config():
    return {
        ...
        'show_audit_fields': False,
    }
```

### Step 2 — Normalizer (`system/normalizers.py`)
Add the key to the group normalizer. **Coerce/clamp** — never trust the stored
shape. For a bool: `bool(cfg.get('show_audit_fields', False))`. For a choice:
validate against a `*_VALUES` set and fall back to the default (Trap 8):
```python
def normalize_layout_config(value):
    cfg = value if isinstance(value, dict) else {}
    ...
    return {
        ...
        'show_audit_fields': bool(cfg.get('show_audit_fields', False)),
    }
```

### Step 3 — Constants (`system/constants.py`) — TWO edits
1. If it's a **choice**, add its `_CHOICES` tuple and derived `_VALUES` set here.
2. **Add the key to `SYSTEM_SETTINGS_EXPORT_FIELDS`.** This is not optional and it
   is the step everyone forgets. Without it the key is dropped by the import
   normalizer (§2). Put flat keys in this tuple by their flat name; whole groups
   (`layout_config`) are also listed for nested-payload passthrough.

### Step 4 — Schema (`system/schema.py`)
Add a `_field(...)` to the group's `fields=(...)`:
```python
_field('layout', 'show_audit_fields', field_type='bool', default=False,
       widget='switch', legacy_flat=True),
```
`legacy_flat=True` auto-generates: the `SystemSettings.show_audit_fields` property
(via `get_flat_config_fields()` → `models.py`), the flat import alias, and the
`form_sys_<name>` / `help_sys_<name>` label/help keys. `field_type` ∈
`str|bool|int|email|dict|list`; `widget` ∈ `switch|choice|multiselect|json|text`.

### Step 5 — Form field (`forms.py`, `SystemSettingsForm`) — FIVE edits
1. **Declare** the field near the other group fields:
   ```python
   show_audit_fields = forms.BooleanField(required=False, initial=False)
   ```
2. **Add to `Meta.fields`** and to the per-step
   field partition list. Both. (Trap 6.)
3. **Label + help** in `__init__` from `DLUX_STRINGS`:
   ```python
   self.fields['show_audit_fields'].label = s.get('form_sys_show_audit_fields', 'Show audit fields')
   self.fields['show_audit_fields'].help_text = s.get('help_sys_show_audit_fields', '…')
   ```
4. **Render** it in the step layout via `build_settings_toggle_field(self, 'show_audit_fields', css_class='col-12 col-lg-6')`.
5. **`clean_<name>()`** using the preservation helper with the **correct step index**:
   ```python
   def clean_show_audit_fields(self):
       return self._clean_preserved_toggle('show_audit_fields', 9, False)
   ```
   The `9` is the 0-indexed layout step. If it's wrong (or you skip the helper),
   saving *any other* step reads the absent checkbox as `False` and wipes your
   value (Trap 2). Choice/text fields have `_clean_preserved_choice` /
   `_clean_preserved_text` equivalents.
6. **Pack on save**: in the layout-group build block, add the key
   to the dict that becomes `layout_config`, preferring an already-present grouped
   value then the cleaned flat value:
   ```python
   'show_audit_fields': bool(layout_config.get(
       'show_audit_fields', self.cleaned_data.get('show_audit_fields', False))),
   ```

### Step 6 — Runtime exposure (`utils/config.py`, `get_system_config()`)
- **`legacy_flat` scalars** (density, footer_text…) are surfaced by the existing
  gated blocks — add one following the `_should_apply_db_override()` pattern so a
  DB value only wins when configured **or** non-default (Trap 4).
- **JSON-only opt-in flags** are **not** auto-exposed by a property; read them from
  the stored `layout_config` dict and set the flat key explicitly, as done for
  `show_audit_fields` / `show_soft_deleted` / `options_style`:
  ```python
  _layout_json = getattr(sys_settings, 'layout_config', None)
  if isinstance(_layout_json, dict):
      for _flag in ('show_audit_fields', 'show_soft_deleted'):
          if bool(_layout_json.get(_flag)):
              db_config[_flag] = True
  ```
  (Trap 5.)

### Step 7 — Import routing for JSON-only keys (`utils/import_export.py`)
`legacy_flat` keys route themselves via the generic `hasattr(instance, field_name)`
setter. A **JSON-only** key needs an explicit `elif` in `apply_system_settings_import`
to fold it into its group dict (see the `options_style` branch). Skip this and
import/bootstrap won't apply it. (Trap 9.)

### Step 8 — Translations (`translations.py`)
Add `form_sys_<name>` and `help_sys_<name>` to **both** the EN and AR dicts. No raw
HTML in i18n strings (crispy renders help unescaped).

### Step 9 — Consume it
Read via `get_system_config().get('show_audit_fields')` — or, better, wrap policy in
a helper (e.g. `dlux/utils/authorization.py::audit_fields_visible()`) so callers
don't re-implement the permission/superuser gate. Never read `SystemSettings`
directly in view/template code.

### Step 10 — Migration (only if needed)
Adding a JSON key needs **no migration** — the group field already exists and
`normalize_*` fills defaults on read. You only need a migration for a **new model
field** or a **new permission** (`AlterModelOptions`). If you add one, it must be in
`ALLOWED_MIGRATION_OPERATIONS` (`updater/release_check.py`) to pass the inline
updater's migration-safety gate.

### Step 11 — Tests, docs, changelog (same turn)
- **Test through the save path** (§6). A test that only sets `layout_config`
  directly proves nothing (Trap 3).
- Update `docs/` (reference/admin/FEATURES as relevant), `CHANGELOG.md`, and
  `tracker.md`. Check `git tag` first — never append to a published version.

---

## 4. Flat (`legacy_flat`) vs JSON-only — how to choose

| | `legacy_flat=True` | JSON-only |
|:--|:--|:--|
| Model access | `SystemSettings.<name>` property (auto) | `settings.<group>_config['<name>']` |
| Import alias | auto (flat name accepted) | must add `elif` in `apply_system_settings_import` |
| Form handling | flat field + `clean_<name>` | flat field, but pack + `get_system_config` need manual routing |
| `get_system_config` exposure | via a gated `_should_apply_db_override` block | must read group dict and set flat key manually |
| Use when | the wizard/form edits it as a top-level control (most cases) | new opt-in flags where you want to avoid a model property |

Both still **must** be in `SYSTEM_SETTINGS_EXPORT_FIELDS`.

---

## 5. Where each piece lives (quick file map)

| Concern | File · symbol |
|:--|:--|
| Group default | `dlux/system/defaults.py` · `default_<group>_config()` |
| Validation | `dlux/system/normalizers.py` · `normalize_<group>_config()` |
| Choices / **export whitelist** | `dlux/system/constants.py` · `*_CHOICES`, `SYSTEM_SETTINGS_EXPORT_FIELDS` |
| Typed field | `dlux/system/schema.py` · `SYSTEM_SETTING_GROUPS` → `_field(...)` |
| Flat property generation | `dlux/models.py` · `get_flat_config_fields()` loop (auto) |
| Form field / clean / save | `dlux/forms.py` · `SystemSettingsForm` |
| Per-step preservation | `dlux/forms.py` · `_clean_preserved_toggle/_choice/_text` |
| Import whitelist + apply | `dlux/utils/import_export.py` · `normalize_system_settings_import_payload`, `apply_system_settings_import` |
| Flat⇄group reconcile | `dlux/utils/config.py` · `expand_system_config_groups` |
| Runtime merge/expose | `dlux/utils/config.py` · `get_system_config` |
| Strings | `dlux/translations.py` · EN + AR |
| `config.json` bootstrap | `dlux/utils/config.py` · `bootstrap_system_settings_config_json` |

---

## 6. Verification recipe (run before claiming it works)

Prove the **round-trip through the real save path**, not a direct dict write:

```python
from dlux.models import SystemSettings
from dlux.utils.import_export import apply_system_settings_import

s = SystemSettings.load()

# 1. Applies and persists via the import normalizer (exercises the whitelist).
apply_system_settings_import(s, {'show_audit_fields': True})
assert SystemSettings.load().show_audit_fields is True          # survives reload

# 2. Survives a save of a DIFFERENT settings step (exercises preservation).
#    Bind the form in single-step mode for another step and save; the flag must hold.

# 3. Reaches runtime config.
from dlux.utils.config import get_system_config
assert get_system_config().get('show_audit_fields') is True

# 4. Is in the export whitelist.
from dlux.system.constants import SYSTEM_SETTINGS_EXPORT_FIELDS
assert 'show_audit_fields' in SYSTEM_SETTINGS_EXPORT_FIELDS
```

Then run the full suite. See `dlux/tests/test_audit_visibility.py::SettingsPersistenceTests`
for the pattern that would have caught the whitelist drop.

---

## 7. Known traps (the things that actually bite)

1. **Not in `SYSTEM_SETTINGS_EXPORT_FIELDS`** — the #1 bug. The import normalizer
   whitelists to this tuple, so an unlisted key is dropped on export, import, and
   `config.json` bootstrap. Symptom: setting saves via the form but "turns itself
   off on its own" whenever any settings step is saved. **Always add it.**
2. **Wrong/missing step index in `clean_<name>`** — `_clean_preserved_toggle` needs
   the correct 0-indexed step. A checkbox is absent from POST both when unchecked
   *and* when another step is being saved; without preservation the second case
   writes `False`. Use the helper, pass the right index.
3. **Tests that bypass the save path** — setting `layout_config` directly and
   asserting behavior tests nothing about persistence. It passes while the real
   feature is broken (this exact gap hid trap 1). Drive tests through
   `apply_system_settings_import` and the bound form.
4. **Unconditional DB override in `get_system_config`** — applying a value without
   `_should_apply_db_override()` materializes the whole group via `expand`, which
   can clobber a `settings.DLUX_CONFIG` override on an unconfigured system. Gate it.
5. **JSON-only key with no explicit exposure** — a property alone does **not** put a
   key into the flat `get_system_config()` dict. Read the group dict and set the
   flat key (the `show_audit_fields` loop).
6. **Adding to only one `Meta.fields` location** — `SystemSettingsForm` lists fields
   in `Meta.fields` *and* in the per-step partition. Miss one and the field either
   isn't saved or isn't rendered in its step.
7. **Model/form/view/translations imports in `defaults.py`/`normalizers.py`** —
   breaks migration callables and startup with circular imports. Keep them leaf.
8. **Choice not validated in the normalizer** — always check membership in a
   `*_VALUES` set and fall back to the default, or garbage persists.
9. **Converting a step's dependents from hidden to disabled without a save guard**
   — a disabled control is absent from POST, so a group pack that rebuilds from
   flat fields reads every dependent as its default and wipes the configuration
   the admin was only switching off. Guard the pack on the master toggle (see
   `if sidebar['enabled']` / `notifications_master_off` in `SystemSettingsForm`)
   and prove it with a test that saves the step with the master off.
10. **JSON-only key not routed in `apply_system_settings_import`** — `legacy_flat`
   keys route via the generic setter; JSON-only keys need an explicit `elif`
   (mirror the `options_style` branch) or import/bootstrap silently skips them.

---

## 8. Related

- `reference.md` — app-owned config namespace (`extra_config['app']`),
  `register_app_settings()`, runtime config keys.
- `developer-guide.md` — configuration layers, `ScopedModel`, startup patches.
- `docs/RELEASING.md` — tag-driven release + migration-safety rules.

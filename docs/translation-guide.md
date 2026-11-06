# Translations

DjangoLux uses `DLUX_STRINGS` dictionaries in `translations.py` files. The runtime
merges package, installed-app, project, and database override strings for the
current language; database overrides are for administrator edits, not a copy of the
entire discovered catalog.

## Project strings

Create a project or app `translations.py`:

```python
DLUX_STRINGS = {
    "en": {"billing_invoice": "Invoice"},
    "ar": {"billing_invoice": "فاتورة"},
}
```

Use stable semantic keys. Do not put raw HTML in translated form help or
notification strings: Crispy help text is unescaped. Translate labels and option
values separately when their meaning differs by context.

A lookup with a default — `DLUX_STRINGS.<key>|default:'…'` in a template,
`strings.get('<key>', '…')` in Python — falls back to that literal when the key is
absent. A missing key therefore renders English in every language with no error;
the [audit](#auditing-strings) is what finds it.

## Administrator overrides

The translation editor in the **Languages** setup step shows discovered keys by
source. It persists only edited values in `language_config.translations_override`;
code-owned values remain the fallback. This makes imports portable and lets a
project upgrade its source catalog without copying stale rows into the database.

Language catalogs define the display name, direction, and optional flag. A language
is available to users only after an administrator includes it in the system catalog.
Keep the source string complete for both LTR and RTL languages; CSS handles
direction, while prose needs a deliberate translation.

## Labels and permissions

Model, section, route, and permission labels resolve through the same catalog.
Provide project keys for custom models and actions rather than hard-coding English
in a template or view. Per-language sidebar/Navbar labels are optional overrides: a
blank value falls back to the discovered translated route name.

## Auditing strings

`python manage.py dlux_translations` compares every project app's `translations.py`
with the code that reads it and prints one section per check:

| Check | Finds |
| --- | --- |
| `missing` | A key one language of a `translations.py` defines and another lacks. |
| `undefined` | A key looked up in code (`t()`, `lazy_t()`, `strings.get()`, `get_strings().get()`, `label_key`) or templates (`DLUX_STRINGS.key`, `{# #}` comments ignored) that no language defines, after following `STRING_ALIASES`. Shows the template `\|default:` text that users see instead. |
| `models` | `app_<label>`, `model_<model>` and `perm_<codename>` keys the permission manager and model labels read, for every non-English language (English falls back to verbose names). |
| `duplicates` | A key written twice in one dict literal (Python keeps the second silently), two apps defining one key differently (the app loaded last wins), and keys overriding a DjangoLux string (reported, never failing). |
| `same` | A non-English value identical to English, i.e. probably never translated. |
| `unused` | Opt-in (`--check unused`): keys with no reference, ignoring DjangoLux naming conventions, f-string prefixes and `<namespace>_<url name>` route keys. Heuristic; review before removing. |

Options:

| Option | Effect |
| --- | --- |
| `--lang ar` | Limits the audit to one language. |
| `--app catalog` | Limits the audit to one app. |
| `--check <name>` | Runs only the named checks. |
| `--json` | Machine-readable output for tooling. |
| `--fail` | Exits 1 when `missing`, `undefined`, `models` or `duplicates` finds anything (CI). |
| `--stub ar` | Prints every Arabic gap as paste-ready `"key": "English draft",  # TODO translate` lines, grouped by the file they belong in. |
| `--core` | Runs the same checks on DjangoLux's own `translations/strings/*.py` and package code. |

### DjangoLux's own catalogue

`dlux/tests/test_translation_coverage.py` fails the package build when:

- a key referenced in a template, in Python or in the tutorial script does not
  resolve in every shipped language;
- the language dicts in `dlux/translations/strings/` define different key sets;
- a `STRING_ALIASES` entry points at nothing.

Retired keys may resolve through `STRING_ALIASES` (`dlux/translations/aliases.py`)
instead of being defined directly. Keys a template deliberately presence-tests
(`footer_text`) are listed in that test's `_OPTIONAL_OVERRIDE_KEYS`. To run the
checks outside the suite, use `python manage.py dlux_translations --core`.

## Verification

Run `python manage.py dlux_translations --lang <code>`, then check an English and an
Arabic request after adding strings. Verify that controls with directional meaning
mirror correctly, especially navigation arrows, action rails, table pagination, and
titlebar/sidebars. See
[Developer Guide](developer-guide.md#translation-and-scope-behavior) for the runtime
resolver and [Template Customization](template-customization.md) for direction-safe
template patterns.

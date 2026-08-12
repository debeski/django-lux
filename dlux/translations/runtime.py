"""Translation runtime: language resolution, string lookup and overrides.

The bundled tables live in `dlux.translations.strings`; this module decides
which language a request gets and merges project overrides on top.
"""

from django.apps import apps
from django.conf import settings
from importlib import import_module
from functools import lru_cache
import logging

from .strings import DLUX_STRINGS


logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _discover_and_merge_translations():
    """
    Auto-discover translations from all installed apps.
    Looks for 'translations.py' in each app and a 'DLUX_STRINGS' dict
    (legacy 'MS_TRANSLATIONS' from pre-rebrand apps is still honored).
    Returns a merged dictionary of all translations.
    """
    # Keep source ownership intact for the translation matrix while merging app keys.
    merged_strings = {
        lang: dict(strings) if isinstance(strings, dict) else strings
        for lang, strings in DLUX_STRINGS.items()
    }

    for app_config in apps.get_app_configs():
        # Skip dlux itself as we already loaded it
        if app_config.name == 'dlux':
            continue
            
        try:
            # Try to import translations module
            module = import_module(f"{app_config.name}.translations")
            
            # Primary DLUX_STRINGS, with an inert fallback to the legacy
            # MS_TRANSLATIONS name so apps not yet migrated keep loading.
            app_strings = getattr(module, 'DLUX_STRINGS', None) or getattr(module, 'MS_TRANSLATIONS', None)

            if app_strings and isinstance(app_strings, dict):
                # Deep merge logic
                for lang, keys in app_strings.items():
                    if lang not in merged_strings:
                        merged_strings[lang] = {}
                    merged_strings[lang].update(keys)
                    
        except ImportError:
            # App has no translations.py, just skip
            continue
        except Exception as e:
            logger.warning(f"Error loading translations from {app_config.name}: {e}")
            continue
            
    return merged_strings


def _normalize_translation_lookup_text(value):
    return str(value or '').strip()


@lru_cache(maxsize=1)
def _translation_reverse_index():
    index = {}
    for _lang, strings in _discover_and_merge_translations().items():
        if not isinstance(strings, dict):
            continue
        for key, value in strings.items():
            text = _normalize_translation_lookup_text(value)
            if text:
                index.setdefault(text, str(key))
    return index


def resolve_translation_key_for_text(text, overrides=None):
    """
    Return the DLUX_STRINGS key for an exact translated value, when known.

    This lets persisted UI text such as old notification rows render in the
    current request language after a user switches languages. Free-form or
    interpolated messages intentionally fall back to their stored text.
    """
    needle = _normalize_translation_lookup_text(text)
    if not needle:
        return ''

    if overrides is None and apps.ready:
        try:
            from dlux.utils import get_system_config

            overrides = get_system_config().get('translations', {})
        except Exception:
            overrides = None

    if isinstance(overrides, dict):
        for _lang, strings in overrides.items():
            if not isinstance(strings, dict):
                continue
            for key, value in strings.items():
                if _normalize_translation_lookup_text(value) == needle:
                    return str(key)

    return _translation_reverse_index().get(needle, '')


@lru_cache(maxsize=1)
def _discover_translation_source_layers():
    """
    Return source-aware translation layers for matrix grouping.
    The merged runtime catalog still uses _discover_and_merge_translations().
    """
    sources = [
        {
            'id': 'dlux',
            'label': 'Dlux',
            'type': 'core',
            'translations': DLUX_STRINGS,
        }
    ]

    for app_config in apps.get_app_configs():
        if app_config.name == 'dlux':
            continue

        try:
            module = import_module(f"{app_config.name}.translations")
            app_strings = getattr(module, 'DLUX_STRINGS', None) or getattr(module, 'MS_TRANSLATIONS', None)
        except ImportError:
            continue
        except Exception as e:
            logger.warning(f"Error loading translations from {app_config.name}: {e}")
            continue

        if not isinstance(app_strings, dict) or not app_strings:
            continue

        sources.append({
            'id': str(app_config.label or app_config.name).replace('.', '_'),
            'label': str(getattr(app_config, 'verbose_name', '') or app_config.label or app_config.name),
            'type': 'app',
            'translations': app_strings,
        })

    return sources


def _translation_layer_keys(layer):
    keys = set()
    if not isinstance(layer, dict):
        return keys
    for values in layer.values():
        if isinstance(values, dict):
            keys.update(str(key) for key in values.keys())
    return keys


def discover_translation_languages(*extra_layers):
    """Return language codes that have translation strings, without enabling them."""
    languages = set()
    for layer in (_discover_and_merge_translations(), *extra_layers):
        if not isinstance(layer, dict):
            continue
        for code, values in layer.items():
            if isinstance(values, dict) and values:
                languages.add(str(code).split('-')[0].lower())
    return sorted(languages)


def _build_translation_matrix_row(key, enabled_codes, base_strings, project_strings, overrides):
    values = {}
    base_values = {}
    override_values = {}
    sources = {}
    for lang in enabled_codes:
        core_value = DLUX_STRINGS.get(lang, {}).get(key)
        discovered_value = base_strings.get(lang, {}).get(key)
        project_value = project_strings.get(lang, {}).get(key) if isinstance(project_strings.get(lang), dict) else None
        override_value = overrides.get(lang, {}).get(key) if isinstance(overrides.get(lang), dict) else None

        base_value = project_value if project_value is not None else discovered_value
        value = override_value if override_value is not None else base_value
        values[lang] = '' if value is None else str(value)
        base_values[lang] = '' if base_value is None else str(base_value)
        override_values[lang] = '' if override_value is None else str(override_value)
        if override_value is not None:
            sources[lang] = 'override'
        elif project_value is not None:
            sources[lang] = 'project'
        elif core_value is not None:
            sources[lang] = 'core'
        elif discovered_value is not None:
            sources[lang] = 'app'
        else:
            sources[lang] = 'missing'

    cells = [
        {
            'language': lang,
            'value': values.get(lang, ''),
            'base_value': base_values.get(lang, ''),
            'override_value': override_values.get(lang, ''),
            'source': sources.get(lang, 'missing'),
        }
        for lang in enabled_codes
    ]
    return {
        'key': key,
        'values': values,
        'base_values': base_values,
        'override_values': override_values,
        'sources': sources,
        'cells': cells,
    }


def _enabled_language_codes(enabled_languages):
    return [
        str(code).split('-')[0].lower()
        for code in (enabled_languages or {})
        if str(code or '').strip()
    ]


def build_translation_matrix_groups(enabled_languages, overrides=None):
    """
    Build grouped editor data. Groups are used as UI tabs: Dlux, each app,
    project settings translations, and override-only keys.
    """
    enabled_codes = _enabled_language_codes(enabled_languages)
    base_strings = _discover_and_merge_translations()
    project_config = getattr(settings, 'DLUX_CONFIG', {})
    project_strings = project_config.get('translations', {}) if isinstance(project_config, dict) else {}
    overrides = overrides if isinstance(overrides, dict) else {}

    groups = []
    claimed_keys = set()
    for source in _discover_translation_source_layers():
        source_keys = sorted(_translation_layer_keys(source.get('translations')))
        rows = []
        for key in source_keys:
            if key in claimed_keys:
                continue
            claimed_keys.add(key)
            rows.append(_build_translation_matrix_row(key, enabled_codes, base_strings, project_strings, overrides))
        if rows:
            groups.append({
                'id': source['id'],
                'label': source['label'],
                'type': source['type'],
                'rows': rows,
            })

    project_keys = sorted(_translation_layer_keys(project_strings) - claimed_keys)
    if project_keys:
        groups.append({
            'id': 'project',
            'label': 'Project translations',
            'type': 'project',
            'rows': [
                _build_translation_matrix_row(key, enabled_codes, base_strings, project_strings, overrides)
                for key in project_keys
            ],
        })
        claimed_keys.update(project_keys)

    override_only_keys = sorted(_translation_layer_keys(overrides) - claimed_keys)
    if override_only_keys:
        groups.append({
            'id': 'runtime',
            'label': 'Settings overrides',
            'type': 'override',
            'rows': [
                _build_translation_matrix_row(key, enabled_codes, base_strings, project_strings, overrides)
                for key in override_only_keys
            ],
        })

    return groups


def build_translation_matrix(enabled_languages, overrides=None):
    """
    Build editor data for enabled languages.
    Existing code/app/project values prefill cells; overrides remain the only saved layer.
    """
    rows = []
    for group in build_translation_matrix_groups(enabled_languages, overrides):
        rows.extend(group.get('rows', []))
    return rows


def get_current_language_code(request=None):
    from django.utils.translation import get_language
    
    # ── 1. Fetch System Settings ──
    try:
        from dlux.utils import get_system_config
        sys_config = get_system_config()
        default_sys_lang = sys_config.get('default_language', 'en')
        allow_user_language_override = bool(sys_config.get('allow_user_language_override', True))
        available_languages = sys_config.get('languages', {}) or {}
    except Exception:
        default_sys_lang = 'en'
        allow_user_language_override = True
        available_languages = {}
        
    lang_code = None
    
    # ── 2. Resolve Language Code ──
    if not request:
        try:
            from dlux.middleware import get_current_request
            request = get_current_request()
        except Exception:
            pass

    if request:
        preview_lang = None
        if hasattr(request, 'session'):
            preview_lang = request.session.get('lang')
            if request.session.get('dlux_force_language_preview') and preview_lang:
                lang_code = preview_lang

        # 2.A User Profile Preference
        if not lang_code and allow_user_language_override and hasattr(request, 'user') and getattr(request.user, 'is_authenticated', False):
            profile = getattr(request.user, 'profile', None)
            if profile:
                user_prefs = getattr(profile, 'preferences', None) or {}
                lang_code = user_prefs.get('language')
        
        # 2.B Session
        if not lang_code and allow_user_language_override and hasattr(request, 'session'):
            lang_code = request.session.get('lang') or request.session.get('django_language')
    
    # 2.C System Default Language
    if not lang_code:
        lang_code = default_sys_lang
    
    # 2.D Django Thread Local
    if not lang_code:
        lang_code = get_language()
        
    lang = lang_code or default_sys_lang
    if available_languages and lang.split('-')[0] not in available_languages:
        lang = default_sys_lang
    # handle en-us -> en
    return lang.split('-')[0]


try:
    from .aliases import STRING_ALIASES as _STRING_ALIASES
except Exception:
    _STRING_ALIASES = {}


def get_strings(lang_code=None, overrides=None):
    """
    Get the translation dict for a given language code.
    If lang_code is not provided, dynamically resolves it using get_current_language_code().
    Merges project-level overrides on top of the base strings automatically.
    """
    from django.apps import apps
    apps_ready = apps.ready

    default_sys_lang = 'en'
    if apps_ready:
        try:
            from dlux.utils import get_system_config
            sys_config = get_system_config()
            default_sys_lang = sys_config.get('default_language', 'en')
            if overrides is None:
                overrides = sys_config.get('translations', {})
        except Exception:
            overrides = overrides or {}
    else:
        # During app initialization Django runs AppConfig.ready() and resolves lazy
        # translations before `apps.ready` is set. The dlux gettext patch routes those
        # through here, so touching the DB now triggers Django 6.0's "database access
        # during app initialization" warning — and opening a connection at init is
        # genuinely risky (pre-migrate boots, forking/pre-loaded WSGI servers). Serve
        # the in-memory catalog with safe defaults; the DB override + active-language
        # layer resumes automatically once apps are ready.
        overrides = overrides or {}

    lang = lang_code
    if not lang:
        lang = get_current_language_code() if apps_ready else default_sys_lang
    else:
        lang = lang.split('-')[0]
    
    # ── 3. Merge Strings ──
    all_strings = _discover_and_merge_translations()
    base = dict(all_strings.get(default_sys_lang, {}))

    if lang != default_sys_lang:
        lang_strings = all_strings.get(lang, {})
        base.update(lang_strings)

    lang_overrides = {}
    if overrides and isinstance(overrides, dict):
        lang_overrides = overrides.get(lang, {})
        base.update(lang_overrides)

    # ── 4. Resolve unified-key aliases ──
    # Retired duplicate keys are kept working (backward compatible) by pointing
    # them at their canonical key's *final* value — so editing the canonical once
    # changes them all. Applied after overrides (so a canonical override
    # propagates), but an explicit override of a retired key still wins.
    if _STRING_ALIASES:
        for alias, canonical in _STRING_ALIASES.items():
            if alias in lang_overrides:
                continue
            if canonical in base:
                base[alias] = base[canonical]

    return base


class MigrationSafeTranslation(str):
    """
    Runtime-translated string that Django migrations can serialize stably.

    Django's migration serializer resolves django.utils.functional.Promise
    values with str(value), which makes generated migrations depend on the
    active language. This object is intentionally not a Promise; it behaves
    like its stable default string for migration serialization while str()
    resolves through the active Dlux translation table at runtime.
    """

    def __new__(cls, key, default_val, fallback_keys=None):
        obj = super().__new__(cls, default_val)
        obj.key = key
        obj.default_val = default_val
        # Ordered secondary keys tried at runtime when `key` is absent. Kept out
        # of migration serialization (_migration_value/_migration keep using the
        # primary key) so generated migrations never depend on fallback state.
        obj.fallback_keys = tuple(fallback_keys or ())
        return obj

    def __getnewargs__(self):
        # str subclasses are reconstructed via __new__ during copy/pickle.
        # str's default __getnewargs__ returns only (str_value,), which calls
        # __new__(cls, value) and raises "missing 'default_val'". Supplying all
        # constructor args keeps deepcopy/pickle (e.g. Django form/widget
        # deepcopy of translated labels) working.
        return (self.key, self.default_val, self.fallback_keys)

    def _resolve(self):
        try:
            strings = get_strings()
            for k in (self.key, *self.fallback_keys):
                if k in strings:
                    return strings[k]
            return self.default_val
        except Exception:
            return self.default_val

    def _migration_value(self):
        try:
            all_strings = _discover_and_merge_translations()
            return all_strings.get('en', {}).get(self.key, self.default_val)
        except Exception:
            return self.default_val

    def __str__(self):
        return str(self._resolve())

    def __repr__(self):
        return repr(self._migration_value())

    def __format__(self, format_spec):
        return format(str(self), format_spec)

    def __html__(self):
        return str(self)

    def __eq__(self, other):
        if isinstance(other, MigrationSafeTranslation):
            return (self.key, self.default_val) == (other.key, other.default_val)
        return self._migration_value() == other

    def __hash__(self):
        return hash(self._migration_value())


def lazy_translator(key, default_val, fallback_keys=None):
    """
    Returns a migration-safe object that evaluates to the translated string
    at render time, using the current thread's language.

    ``fallback_keys`` is an optional ordered sequence of secondary DLUX_STRINGS
    keys tried (in order) at render time when ``key`` is missing, before finally
    falling back to ``default_val``.
    """
    return MigrationSafeTranslation(key, default_val, fallback_keys)


def resolve_model_label(model, strings=None, lang=None):
    """Canonical display label for a content/user model.

    This is the single entry point every Dlux component (nav, sidebar, section
    manager, etc.) uses so they always agree on the same string for a given
    model. Resolution order:

        models_<model_name>  (plural key)   →
        model_<model_name>   (singular key) →
        raw verbose_name_plural            (final fallback)

    ``strings`` may be supplied to resolve against an already-loaded table (e.g.
    a specific language); otherwise the active language table is used.
    """
    if model is None:
        return ''
    if strings is None:
        strings = get_strings(lang) if lang else get_strings()
    name = model._meta.model_name
    for key in (f'models_{name}', f'model_{name}'):
        val = strings.get(key)
        if val:
            return str(val)
    return str(model._meta.verbose_name_plural)

# dlux/management/commands/dlux_translations.py
"""Audit DLUX_STRINGS against the code that looks them up.

    python manage.py dlux_translations                  # every check, every language
    python manage.py dlux_translations --lang ar        # only what Arabic is missing
    python manage.py dlux_translations --app catalog    # one app's strings and code
    python manage.py dlux_translations --stub ar        # paste-ready entries for the gaps
    python manage.py dlux_translations --core           # DjangoLux's own strings and code
    python manage.py dlux_translations --fail           # exit 1 on gaps (CI)

Checks (``--check`` picks a subset; ``unused`` runs only when asked):
  missing     a key one language of a translations file has and another lacks
  undefined   a key the code looks up that no translations file defines for a language
  models      app_/model_/perm_ keys the permission manager and model labels read
              (non-English only: English falls back to verbose names)
  duplicates  a key written twice in one dict, defined differently by two apps, or
              overriding a DjangoLux string (reported, never fails)
  same        a non-English value identical to English (likely never translated)
  unused      keys nothing references (heuristic, never fails)
"""
import ast
import json
import re
from collections import defaultdict
from importlib import import_module
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

import dlux

CHECKS = ('missing', 'undefined', 'models', 'duplicates', 'same', 'unused')
DEFAULT_CHECKS = tuple(check for check in CHECKS if check != 'unused')
FAILING = {'missing', 'undefined', 'models', 'duplicates'}
BASE_LANG = 'en'
DLUX_DIR = Path(dlux.__file__).resolve().parent
STRINGS_DIR = DLUX_DIR / 'translations' / 'strings'
KEY = r'[a-z][a-z0-9_]*'
CODE_SUFFIXES = {'.py', '.html', '.js', '.txt'}
SKIP_PARTS = {'migrations', 'tests', '__pycache__', 'node_modules', 'staticfiles', '.xclude'}
PY_LOOKUPS = (
    re.compile(rf"""\b(?:lazy_t|t|_t|_s|lazy_translator)\(\s*["']({KEY})["'](?:\s*,\s*["']([^"'\n]*)["'])?"""),
    re.compile(
        rf"""(?:\b(?:strings|s|S|_s|translations|DLUX_STRINGS)|get_strings\([^()]*\))\.get\(\s*["']({KEY})["'](?:\s*,\s*["']([^"'\n]*)["'])?"""
    ),
    re.compile(rf"""["']label_key["']\s*:\s*["']({KEY})["']()"""),
)
DJANGO_COMMENT = re.compile(r'\{#.*?#\}', re.S)
# Optional overrides: templates test for these and fall through when absent (projects
# set them through language_config.translations_override), so absence is not a gap.
OPTIONAL_KEYS = {'footer_text'}
TEMPLATE_LOOKUP = re.compile(rf"""DLUX_STRINGS\.({KEY})(?:\|default:["']([^"'\n]*)["'])?""")
DYNAMIC_PREFIX = re.compile(r"""\bf["']([a-z][a-z0-9_]*_)\{""")
LITERAL = re.compile(rf"""["']({KEY})["']""")
# Keys DjangoLux builds from model/field/route names at runtime (dlux.patches, discovery).
CONVENTION_PREFIXES = (
    'app_', 'model_', 'models_', 'perm_', 'label_', 'form_', 'tbl_', 'page_', 'help_', 'options_', 'choice_',
)
# English already shows these through app/model verbose names and Permission.name.
FALLBACK_PREFIXES = ('app_', 'model_', 'perm_')
LATIN = re.compile(r'[A-Za-z]{4,}')
TITLES = {
    'missing': 'Keys missing from a language in the same translations file',
    'undefined': 'Keys the code looks up that are not defined',
    'models': 'App / model / permission labels (permission manager, model names)',
    'duplicates': 'Duplicated or conflicting definitions',
    'same': 'Values identical to English (likely untranslated)',
    'unused': 'Keys nothing references (heuristic, review before removing)',
}


class Command(BaseCommand):
    help = 'Find missing, undefined, duplicated and untranslated DLUX_STRINGS keys.'

    def add_arguments(self, parser):
        parser.add_argument('--lang', action='append', help='Language(s) to audit (default: all with strings).')
        parser.add_argument('--app', action='append', help='Limit to these app labels.')
        parser.add_argument('--check', action='append', choices=CHECKS, help='Run only these checks.')
        parser.add_argument('--core', action='store_true', help="Audit DjangoLux's own strings and code.")
        parser.add_argument('--stub', metavar='LANG', help="Print paste-ready entries for LANG's gaps, per file.")
        parser.add_argument('--json', action='store_true', help='Machine-readable output.')
        parser.add_argument('--fail', action='store_true', help='Exit 1 when a failing check finds anything.')

    def handle(self, *args, **opts):
        from dlux.translations import DLUX_STRINGS as core

        self.core_mode = opts['core']
        self.base_dir = DLUX_DIR.parent if self.core_mode else Path(settings.BASE_DIR).resolve()
        self.app_filter = opts['app']
        layers = self._core_layers(core) if self.core_mode else self._layers()
        if not layers:
            raise CommandError('No project app has a translations.py with DLUX_STRINGS.')

        languages = sorted({lang for layer in layers for lang in layer['strings']} | set(core))
        if opts['lang']:
            unknown = set(opts['lang']) - set(languages)
            if unknown:
                raise CommandError(f"No strings for language(s): {', '.join(sorted(unknown))}")
            languages = opts['lang']
        merged = {lang: dict(core.get(lang, {})) for lang in set(languages) | {BASE_LANG}}
        if not self.core_mode:
            for layer in layers:
                for lang in merged:
                    merged[lang].update(layer['strings'].get(lang, {}))
        self.references, self.dynamic, self.literals = self._scan_code()

        context = {'layers': layers, 'core': core, 'merged': merged, 'languages': languages}
        checks = opts['check'] or (list(DEFAULT_CHECKS) if not self.core_mode else ['missing', 'undefined', 'duplicates', 'same'])
        report = {check: getattr(self, f'_check_{check}')(**context) for check in checks}

        if opts['stub']:
            self._print_stub(opts['stub'], report, merged)
        elif opts['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            self._print_report(report, languages)
        if opts['fail'] and self._failures(report):
            raise SystemExit(1)

    @staticmethod
    def _failures(report):
        return [
            row for check, rows in report.items() if check in FAILING
            for row in rows if row.get('kind') != 'overrides DLux'
        ]

    # ----------------------------------------------------------------- sources
    def _project_apps(self):
        for config in apps.get_app_configs():
            path = Path(config.path).resolve()
            if path == DLUX_DIR or DLUX_DIR in path.parents:
                continue
            if (self.base_dir in path.parents or path == self.base_dir) and (
                not self.app_filter or config.label in self.app_filter
            ):
                yield config

    def _relative(self, path):
        path = Path(path).resolve()
        return str(path.relative_to(self.base_dir)) if self.base_dir in path.parents else str(path)

    def _layers(self):
        layers = []
        for config in self._project_apps():
            try:
                module = import_module(f'{config.name}.translations')
            except ImportError:
                continue
            strings = getattr(module, 'DLUX_STRINGS', None) or getattr(module, 'MS_TRANSLATIONS', None)
            if isinstance(strings, dict) and strings:
                layers.append({
                    'app': config.label,
                    'file': self._relative(module.__file__),
                    'paths': {lang: Path(module.__file__) for lang in strings},
                    'strings': strings,
                })
        return layers

    def _core_layers(self, core):
        paths = {lang: STRINGS_DIR / f'{lang}.py' for lang in core}
        return [{
            'app': 'dlux',
            'file': self._relative(STRINGS_DIR),
            'files': {lang: self._relative(path) for lang, path in paths.items()},
            'paths': paths,
            'strings': core,
        }]

    def _code_roots(self):
        if self.core_mode:
            return [DLUX_DIR]
        roots = [Path(config.path) for config in self._project_apps()]
        if not self.app_filter:
            for engine in getattr(settings, 'TEMPLATES', []):
                roots += [Path(directory) for directory in engine.get('DIRS', [])]
        return roots

    def _code_files(self):
        seen = set()
        for root in self._code_roots():
            for path in root.rglob('*'):
                if (
                    path.suffix in CODE_SUFFIXES and path.is_file() and path.name != 'translations.py'
                    and not SKIP_PARTS.intersection(path.relative_to(root).parts) and STRINGS_DIR not in path.parents
                    and path not in seen
                ):
                    seen.add(path)
                    yield path

    def _scan_code(self):
        references = defaultdict(lambda: {'locations': [], 'default': ''})
        dynamic, literals = set(), set()
        for path in self._code_files():
            text = path.read_text(encoding='utf-8', errors='ignore')
            if path.suffix == '.html':
                text = DJANGO_COMMENT.sub(lambda match: '\n' * match.group(0).count('\n'), text)
            patterns = PY_LOOKUPS if path.suffix == '.py' else (TEMPLATE_LOOKUP,)
            relative = self._relative(path)
            for pattern in patterns:
                for match in pattern.finditer(text):
                    key, default = match.group(1), match.group(2) or ''
                    if key.endswith('_'):
                        dynamic.add(key)  # "prefix_" + value
                        continue
                    entry = references[key]
                    entry['locations'].append(f"{relative}:{text.count(chr(10), 0, match.start()) + 1}")
                    entry['default'] = entry['default'] or default
            dynamic.update(DYNAMIC_PREFIX.findall(text))
            literals.update(LITERAL.findall(text))
        return references, dynamic, literals

    # ------------------------------------------------------------------ checks
    @staticmethod
    def _keys(strings):
        return set().union(*(set(values) for values in strings.values() if isinstance(values, dict)))

    def _file(self, layer, lang):
        return layer.get('files', {}).get(lang, layer['file'])

    def _check_missing(self, layers, languages, **_):
        found = []
        for layer in layers:
            strings = layer['strings']
            for key in sorted(self._keys(strings)):
                absent = [
                    lang for lang in languages
                    if key not in strings.get(lang, {}) and not (lang == BASE_LANG and key.startswith(FALLBACK_PREFIXES))
                ]
                if absent:
                    present = next((lang for lang in [BASE_LANG, *strings] if key in strings.get(lang, {})), '')
                    found.append({
                        'key': key, 'missing': absent, 'file': layer['file'],
                        'source': strings.get(present, {}).get(key, ''),
                    })
        return found

    @staticmethod
    def _resolves(key, strings):
        """Follow STRING_ALIASES the way get_strings() does."""
        try:
            from dlux.translations.aliases import STRING_ALIASES
        except ImportError:
            STRING_ALIASES = {}

        seen = set()
        while key and key not in seen:
            if key in strings:
                return True
            seen.add(key)
            key = STRING_ALIASES.get(key)
        return False

    def _check_undefined(self, merged, languages, layers, **_):
        found = []
        for key in sorted(set(self.references) - OPTIONAL_KEYS):
            absent = [lang for lang in languages if not self._resolves(key, merged[lang])]
            if absent:
                ref = self.references[key]
                found.append({
                    'key': key, 'missing': absent, 'default': ref['default'],
                    'locations': ref['locations'][:5], 'uses': len(ref['locations']),
                    'file': self._home_file(ref['locations'], layers),
                })
        return found

    def _check_models(self, merged, languages, layers, **_):
        found = []
        for config in self._project_apps():
            wanted = {f'app_{config.label}': str(config.verbose_name)}
            for model in config.get_models():
                opts = model._meta
                wanted[f'model_{opts.model_name}'] = str(opts.verbose_name)
                for action in opts.default_permissions:
                    wanted[f'perm_{action}_{opts.model_name}'] = f'Can {action} {opts.verbose_name}'
                for codename, label in opts.permissions:
                    wanted[f'perm_{codename}'] = str(label)
            file = next(
                (layer['file'] for layer in layers if layer['app'] == config.label),
                self._relative(Path(config.path) / 'translations.py'),
            )
            for key, label in wanted.items():
                absent = [lang for lang in languages if lang != BASE_LANG and key not in merged[lang]]
                if absent:
                    found.append({'key': key, 'missing': absent, 'default': label, 'file': file})
        return found

    def _check_duplicates(self, layers, core, **_):
        found = []
        for layer in layers:
            for lang, key, where in self._literal_duplicates(layer):
                found.append({'kind': 'repeated in file', 'key': key, 'lang': lang, 'where': where})
        if self.core_mode:
            return found
        owners = defaultdict(list)
        for layer in layers:
            for lang, values in layer['strings'].items():
                for key, value in (values or {}).items():
                    owners[(lang, key)].append((layer['file'], value))
        for (lang, key), defs in sorted(owners.items()):
            if len(defs) > 1 and len({value for _file, value in defs}) > 1:
                found.append({
                    'kind': 'conflicting apps', 'key': key, 'lang': lang,
                    'where': [f'{file} = {value!r}' for file, value in defs],
                    'note': 'the app loaded last wins',
                })
            core_value = core.get(lang, {}).get(key)
            if core_value is not None and any(value != core_value for _file, value in defs):
                found.append({
                    'kind': 'overrides DLux', 'key': key, 'lang': lang,
                    'where': [f'dlux = {core_value!r}'] + [f'{file} = {value!r}' for file, value in defs],
                })
        return found

    def _check_same(self, layers, merged, languages, **_):
        keys = set().union(*(self._keys(layer['strings']) for layer in layers))
        found = []
        for lang in languages:
            if lang == BASE_LANG:
                continue
            for key in sorted(keys):
                value = merged[lang].get(key)
                if value and value == merged[BASE_LANG].get(key) and LATIN.search(str(value)):
                    found.append({'key': key, 'lang': lang, 'value': value})
        return found

    def _check_unused(self, layers, core, **_):
        core_keys = set() if self.core_mode else self._keys(core)
        route_keys = self._route_keys()
        prefixes = tuple(self.dynamic) + CONVENTION_PREFIXES
        found = []
        for layer in layers:
            for key in sorted(self._keys(layer['strings'])):
                if not (
                    key in self.references or key in self.literals or key in core_keys
                    or key in route_keys or key.startswith(prefixes)
                ):
                    found.append({'key': key, 'file': layer['file']})
        return found

    # ----------------------------------------------------------------- helpers
    def _literal_duplicates(self, layer):
        """Keys written twice in one dict literal: Python keeps the last silently."""
        for path in set(layer['paths'].values()):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            flat_lang = next((lang for lang, lang_path in layer['paths'].items() if lang_path == path), None)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Dict):
                    continue
                nested = [
                    (lang_node.value, value) for lang_node, value in zip(node.keys, node.values)
                    if isinstance(lang_node, ast.Constant) and isinstance(value, ast.Dict)
                ]
                for lang, value in nested or ([(flat_lang, node)] if len(layer['paths']) > 1 else []):
                    lines = defaultdict(list)
                    for key_node in value.keys:
                        if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                            lines[key_node.value].append(key_node.lineno)
                    for key, at in lines.items():
                        if len(at) > 1:
                            yield lang, key, [f'{self._relative(path)}:{line}' for line in at]

    @staticmethod
    def _route_keys():
        """DjangoLux names discovered pages '<namespace>_<url name>' (nested namespaces joined)."""
        from django.urls import URLPattern, URLResolver, get_resolver

        keys = set()

        def walk(patterns, namespace):
            for entry in patterns:
                if isinstance(entry, URLResolver):
                    walk(entry.url_patterns, '_'.join(filter(None, [namespace, entry.namespace])))
                elif isinstance(entry, URLPattern) and entry.name:
                    keys.update({'_'.join(filter(None, [namespace, entry.name])), entry.name})

        walk(get_resolver().url_patterns, '')
        return keys

    @staticmethod
    def _home_file(locations, layers):
        files = {layer['app']: layer['file'] for layer in layers}
        for location in locations:
            app = location.split('/', 1)[0]
            if app in files:
                return files[app]
        return layers[0]['file']

    # ------------------------------------------------------------------ output
    def _print_report(self, report, languages):
        style = self.style
        scope = 'DjangoLux core' if self.core_mode else 'project'
        self.stdout.write(style.MIGRATE_HEADING(f"Translation audit: {scope} ({', '.join(languages)})"))
        for check, rows in report.items():
            self.stdout.write('')
            heading = f'{TITLES[check]}: {len(rows)}'
            self.stdout.write(style.WARNING(heading) if rows else style.SUCCESS(heading))
            for row in rows:
                self.stdout.write('  ' + self._describe(check, row))
        self.stdout.write('')
        totals = ', '.join(f'{check} {len(rows)}' for check, rows in report.items())
        self.stdout.write(style.MIGRATE_HEADING(f'Summary: {totals}'))

    @staticmethod
    def _describe(check, row):
        if check == 'missing':
            return f"{row['key']}  [{','.join(row['missing'])}]  {row['file']}  ({row['source']!r})"
        if check == 'undefined':
            fallback = f"  default {row['default']!r}" if row['default'] else ''
            return f"{row['key']}  [{','.join(row['missing'])}]  {row['locations'][0]} (+{row['uses'] - 1}){fallback}"
        if check == 'models':
            return f"{row['key']}  [{','.join(row['missing'])}]  {row['default']!r}"
        if check == 'duplicates':
            note = f"  ({row['note']})" if row.get('note') else ''
            return f"{row['key']} [{row['lang']}] {row['kind']}: " + ' | '.join(row['where']) + note
        if check == 'same':
            return f"{row['key']} [{row['lang']}] {row['value']!r}"
        return f"{row['key']}  {row['file']}"

    def _print_stub(self, lang, report, merged):
        """Every gap for ``lang``, grouped by the file it belongs in, English text as the draft."""
        entries = defaultdict(dict)
        for check in ('missing', 'undefined', 'models'):
            for row in report.get(check, []):
                if lang in row['missing']:
                    text = row.get('source') or merged[BASE_LANG].get(row['key']) or row.get('default', '')
                    entries[row['file']].setdefault(row['key'], text)
        if not entries:
            self.stdout.write(self.style.SUCCESS(f"Nothing missing for '{lang}'."))
            return
        target = f'STRINGS ({lang}.py)' if self.core_mode else f'DLUX_STRINGS[{lang!r}]'
        for file, keys in sorted(entries.items()):
            self.stdout.write(self.style.MIGRATE_HEADING(f'# {file} -> {target}'))
            for key, text in sorted(keys.items()):
                note = '  # TODO translate' if lang != BASE_LANG else ''
                self.stdout.write(f"    {json.dumps(key)}: {json.dumps(text or '', ensure_ascii=False)},{note}")

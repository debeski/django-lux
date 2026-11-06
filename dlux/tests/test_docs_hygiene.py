"""Keep the manual navigable and free of release narration.

The manual (``docs/``, the root README and the tool READMEs) describes current
behaviour. Release history belongs in ``CHANGELOG.md``; these checks fail when
links rot, a doc drops out of the index, or prerelease notes creep back in.
"""
import re
import unicodedata
from pathlib import Path

from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / 'docs'

ROOT_DOCS = ('README.md', 'CONTRIBUTING.md', 'SECURITY.md', 'CODE_OF_CONDUCT.md')

# Docs whose subject is versions themselves.
VERSIONED_DOCS = {'RELEASING.md', 'deprecation-countdown.md', 'stack-schema.md'}

FENCE = re.compile(r'^(```|~~~).*?^\1', re.M | re.S)
INLINE_CODE = re.compile(r'`[^`\n]*`')
HEADING = re.compile(r'^#{1,6}\s+(.+?)\s*#*\s*$', re.M)
LINK = re.compile(r'!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+"[^"]*")?\s*\)')
HTML_ANCHOR = re.compile(r'<a\s+(?:name|id)="([^"]+)"')
PRERELEASE = re.compile(r'\bv?\d+\.\d+\.\d+(?:a|b|rc)\d+\b')
NARRATION = re.compile(r'\bunreleased\b', re.I)


def manual_files():
    files = [REPO_ROOT / name for name in ROOT_DOCS if (REPO_ROOT / name).exists()]
    files += sorted(DOCS.rglob('*.md'))
    files += sorted(REPO_ROOT.glob('tools/*/README.md'))
    tests_e2e = REPO_ROOT / 'tests-e2e' / 'README.md'
    if tests_e2e.exists():
        files.append(tests_e2e)
    return files


def slugify(heading):
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', heading)
    text = text.replace('`', '').strip().lower()
    text = ''.join(
        ch for ch in text
        if ch in ' -_' or unicodedata.category(ch)[0] in 'LNM'
    )
    return text.replace(' ', '-')


def anchors_of(path):
    source = FENCE.sub('', path.read_text(encoding='utf-8'))
    found, seen = set(HTML_ANCHOR.findall(source)), {}
    for heading in HEADING.findall(source):
        slug = slugify(heading)
        if slug in seen:
            seen[slug] += 1
            found.add(f'{slug}-{seen[slug]}')
        else:
            seen[slug] = 0
            found.add(slug)
    return found


def links_of(path):
    source = INLINE_CODE.sub('', FENCE.sub('', path.read_text(encoding='utf-8')))
    return LINK.findall(source)


def prose_of(path):
    return FENCE.sub('', path.read_text(encoding='utf-8'))


class DocsHygieneTests(SimpleTestCase):
    def setUp(self):
        if not DOCS.is_dir():
            self.skipTest('source documentation is not installed')

    def test_relative_links_and_anchors_resolve(self):
        anchor_cache, broken = {}, []
        for path in manual_files():
            for target in links_of(path):
                if re.match(r'^[a-z][a-z0-9+.-]*:', target, re.I):
                    continue
                file_part, _, anchor = target.partition('#')
                resolved = (path.parent / file_part).resolve() if file_part else path
                rel = path.relative_to(REPO_ROOT)
                if not resolved.exists():
                    broken.append(f'{rel} -> {target} (missing file)')
                    continue
                if anchor and resolved.suffix == '.md':
                    if resolved not in anchor_cache:
                        anchor_cache[resolved] = anchors_of(resolved)
                    if anchor not in anchor_cache[resolved]:
                        broken.append(f'{rel} -> {target} (missing anchor)')
        self.assertEqual(broken, [])

    def test_every_doc_is_in_the_index(self):
        index = DOCS / 'README.md'
        linked = {
            (index.parent / target.partition('#')[0]).resolve()
            for target in links_of(index)
            if target.partition('#')[0]
        }
        missing = sorted(
            path.name for path in DOCS.glob('*.md')
            if path != index and path.resolve() not in linked
        )
        self.assertEqual(missing, [])

    def test_manual_has_no_prerelease_narration(self):
        hits = []
        for path in manual_files():
            if path.parent == DOCS and path.name in VERSIONED_DOCS:
                continue
            prose = prose_of(path)
            rel = path.relative_to(REPO_ROOT)
            hits += [f'{rel}: {m}' for m in PRERELEASE.findall(prose) + NARRATION.findall(prose)]
        self.assertEqual(hits, [])

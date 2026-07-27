"""Arabic search normalization helpers.

Arabic free text is written with well-documented orthographic variance: the
alef hamza forms (ا/أ/إ/آ), final ya vs alef maqsura (ي/ى), ta marbuta vs ha
(ة/ه), regional consonant swaps such as Maghrebi ق↔غ for the "ga" sound,
optional diacritics/tatweel, Farsi keyboard look-alikes (ی/ک), and
Arabic-Indic vs ASCII digits. Exact `icontains` matching misses records whose
stored spelling differs from the typed search term.

Two complementary tools are provided:

- ``normalize_arabic(value)`` folds a string to one canonical form (for
  Python-side comparison, dedup keys, or a stored shadow column).
- ``arabic_search_q(term, fields)`` builds a ``Q`` that matches *unmodified*
  database values against every spelling variant of the term, by compiling the
  term into a case-insensitive regex whose confusable letters become character
  classes and whose letters may be separated by diacritics/tatweel. Backed by
  ``__iregex``, which Django supports on PostgreSQL, MySQL/MariaDB, and SQLite.

Typical FilterSet usage::

    from dlux.utils import arabic_search_q

    def filter_keyword(self, queryset, name, value):
        return queryset.filter(
            arabic_search_q(value, ["title", "keywords", "category__name"])
        )
"""
import re

from django.db.models import Q

# Each group is one equivalence class; the FIRST character is the canonical
# fold target used by normalize_arabic(). Letter groups cover:
#  - alef with/without hamza/madda/wasla
#  - ya, alef maqsura, hamza-on-ya, Farsi yeh (mobile keyboards)
#  - waw with/without hamza
#  - ha vs ta marbuta
#  - qaf vs ghayn (Maghrebi/Libyan "ga" interchange)
#  - Arabic kaf vs Farsi keheh (mobile keyboards)
# Digit groups fold Arabic-Indic and Extended (Persian) digits onto ASCII.
ARABIC_EQUIVALENCE_GROUPS = (
    "اأإآٱ",  # ا أ إ آ ٱ
    "يىئی",        # ي ى ئ ی
    "وؤ",                    # و ؤ
    "هة",                    # ه ة
    "قغ",                    # ق غ
    "كک",                    # ك ک
    "0٠۰", "1١۱", "2٢۲", "3٣۳",
    "4٤۴", "5٥۵", "6٦۶", "7٧۷",
    "8٨۸", "9٩۹",
)

# Characters ignored entirely on both sides of a match: harakat/Quranic marks
# (U+064B–U+065F), superscript alef, tatweel, and the standalone hamza (often
# omitted or added inconsistently, e.g. بناء vs بنا).
_IGNORABLE_RANGE = "\u064B-\u065F\u0670\u0640\u0621"
_IGNORABLE_RE = re.compile(f"[{_IGNORABLE_RANGE}]")
_IGNORABLE_SKIP = f"[{_IGNORABLE_RANGE}]*"

def _char_maps(groups):
    fold, variants = {}, {}
    for group in groups:
        for char in group:
            fold[char] = group[0]
            variants[char] = group
    return fold, variants

_DEFAULT_FOLD, _DEFAULT_VARIANTS = _char_maps(ARABIC_EQUIVALENCE_GROUPS)


def normalize_arabic(value, *, groups=None):
    """Fold *value* to its canonical spelling.

    Confusable letters collapse to the first character of their equivalence
    group, digits become ASCII, and diacritics/tatweel/standalone hamza are
    removed. Non-Arabic characters pass through unchanged.
    """
    if not value:
        return ""
    fold = _DEFAULT_FOLD if groups is None else _char_maps(groups)[0]
    stripped = _IGNORABLE_RE.sub("", str(value))
    return "".join(fold.get(char, char) for char in stripped)


def arabic_search_pattern(term, *, groups=None):
    """Compile *term* into a regex matching every orthographic variant.

    Each confusable character becomes its full equivalence class, other
    characters are regex-escaped literally, and any run of ignorable marks may
    appear between characters — so the stored value never needs normalizing.
    Returns ``""`` for an empty/ignorable-only term.
    """
    variants = _DEFAULT_VARIANTS if groups is None else _char_maps(groups)[1]
    parts = []
    for char in str(term or ""):
        if _IGNORABLE_RE.match(char):
            continue
        group = variants.get(char)
        parts.append(f"[{group}]" if group else re.escape(char))
    return _IGNORABLE_SKIP.join(parts)


def arabic_search_q(term, fields, *, groups=None):
    """Build an OR'd ``Q`` matching *term* (and its variants) in *fields*.

    Uses ``__iregex`` per field, so it behaves like a variant-aware
    ``icontains``. An empty term yields an empty ``Q`` (matches everything),
    mirroring how django-filter skips blank filter values.
    """
    pattern = arabic_search_pattern(term, groups=groups)
    condition = Q()
    if not pattern:
        return condition
    for field in fields:
        condition |= Q(**{f"{field}__iregex": pattern})
    return condition

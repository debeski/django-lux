"""Deciding which existing record a typed name means.

A dropdown makes a reader scroll a register of hundreds; a free text box makes a
second "Acme Trading" the moment somebody types a space differently. This is the
middle, and it is the matching half — `DluxLookupField` is the form half.

Three outcomes, in order, because only the last is a new record:

1. an exact name (case- and space-insensitive) is *that* record, reused;
2. a name close to an existing one is refused with the suggestion, because a
   typo is far likelier than two records whose names differ by a letter;
3. anything else is genuinely new.

Case 2 is a question rather than a verdict — two real bodies can have very
similar names — so the refusal is answerable, and a submit carrying that consent
goes ahead.

Matching lives on the server because the browser can be skipped: a form posted
by a script must not create the duplicate the page would have caught.
"""
from collections import Counter
from difflib import SequenceMatcher

#: How alike two names must be before one is treated as a typo of the other.
#: Measured against a live supplier register of 92 Arabic company names (4,186
#: pairs): at 0.90 every simulated typo — a dropped letter, a swapped pair, a
#: stray space, a missing leading word — is caught, while five pairs of genuinely
#: different records are flagged. The trade is deliberate: a false positive costs
#: one click on "add it anyway", a false negative costs the duplicate this exists
#: to prevent. A register of part numbers or postcodes will want its own value —
#: pass `near_ratio` to the field.
DEFAULT_NEAR_RATIO = 0.90

#: A word appearing in this share of a register carries no information about
#: *which* record is meant. Derived per register rather than hardcoded, because
#: every register has its own: companies repeat "Company", streets repeat "Road".
DEFAULT_BOILERPLATE_SHARE = 0.15


#: Letters Arabic writes more than one way for the same word. These are not
#: typos to be scored — they are the same name spelled two legal ways, and a
#: register accumulates both. Folding them means "شركه النور" *is* "شركة النور",
#: reused exactly, with nothing to confirm. Latin text contains none of them, so
#: the folding costs other alphabets nothing.
ARABIC_EQUIVALENTS = str.maketrans({
    'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ٱ': 'ا',   # hamzated alef
    'ة': 'ه',                                   # taa marbuta / haa
    'ى': 'ي',                                   # alef maqsura / yaa
    'ـ': '',                                    # tatweel, a stretching mark
})

#: Harakat: pronunciation marks that are almost never typed consistently.
ARABIC_DIACRITICS = dict.fromkeys(range(0x064B, 0x0653))


def normalize(name):
    """Collapse the differences that never mean a different record.

    Case, repeated spaces, and — for Arabic — the letters the script writes more
    than one way. Without the last, the commonest slip in an Arabic register
    (`ة` for `ه`) scored 0.94: caught by the default threshold, missed by any
    project that tightened it, and never treated as what it is, which is the
    same name.
    """
    text = ' '.join((name or '').split()).casefold()
    return text.translate(ARABIC_EQUIVALENTS).translate(ARABIC_DIACRITICS)


def boilerplate_words(names, share=DEFAULT_BOILERPLATE_SHARE):
    """The words too common in this register to distinguish anything in it."""
    names = list(names)
    if not names:
        return frozenset()
    counts = Counter()
    for name in names:
        counts.update(set(normalize(name).split()))
    # The floor of 3 keeps a handful of rows from declaring their shared word
    # boilerplate: below that there is no way to tell repetition from signal.
    threshold = max(3, len(names) * share)
    return frozenset(word for word, count in counts.items() if count >= threshold)


def distinctive(name, common):
    """The part of a name that says which record it is."""
    words = [word for word in normalize(name).split() if word not in common]
    return ' '.join(words) or normalize(name)


def similarity(left, right, common=frozenset()):
    """How alike two names are, by the more forgiving of two readings.

    Neither reading works alone. Whole-string comparison is fooled by shared
    boilerplate — two different companies sharing a leading and trailing phrase
    score higher than a record against its own name with the leading word
    dropped. Comparing only the distinctive words fixes both of those and breaks
    the opposite case: stripped to one short word, a single-letter typo is a
    large proportional difference. So the closer of the two wins.
    """
    whole = SequenceMatcher(None, normalize(left), normalize(right)).ratio()
    if not common:
        return whole
    stripped = SequenceMatcher(
        None, distinctive(left, common), distinctive(right, common)).ratio()
    return max(whole, stripped)


def find_exact(records, name, *, attr='name'):
    """The record this name *is*, ignoring case and repeated spaces.

    A plain `iexact` lookup would miss "Acme  Trading" with two spaces, which is
    among the most common ways one record gets entered twice.
    """
    wanted = normalize(name)
    if not wanted:
        return None
    for record in records:
        if normalize(getattr(record, attr, '')) == wanted:
            return record
    return None


def find_near(records, name, *, attr='name', ratio=DEFAULT_NEAR_RATIO, share=DEFAULT_BOILERPLATE_SHARE):
    """The closest existing record, when it is close enough to be a typo."""
    wanted = normalize(name)
    if not wanted:
        return None, 0.0
    records = list(records)
    common = boilerplate_words(
        (getattr(record, attr, '') for record in records), share=share)
    best, best_ratio = None, 0.0
    for record in records:
        score = similarity(wanted, getattr(record, attr, ''), common)
        if score > best_ratio:
            best, best_ratio = record, score
    if best is not None and best_ratio >= ratio:
        return best, best_ratio
    return None, best_ratio


def resolve(records, name, *, attr='name', allow_new=False,
            ratio=DEFAULT_NEAR_RATIO, share=DEFAULT_BOILERPLATE_SHARE):
    """What a typed name means against `records`.

    Returns `(record, near)`:

    * `(record, None)` — an exact match, reused;
    * `(None, near)`   — close to `near`, with no consent to add anyway;
    * `(None, None)`   — nothing like it, so the caller may create it.

    `allow_new` is the reader's consent, gathered after a refusal. It skips the
    near-match check only: an exact name is still reused, because consenting to
    "add anyway" answers "is this a typo?", never "make me a second copy of this
    very name".
    """
    exact = find_exact(records, name, attr=attr)
    if exact is not None:
        return exact, None
    if not normalize(name):
        return None, None
    if allow_new:
        return None, None
    near, _score = find_near(records, name, attr=attr, ratio=ratio, share=share)
    return None, near

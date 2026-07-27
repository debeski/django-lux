import re

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.test import TestCase

from dlux.utils import (
    arabic_search_pattern,
    arabic_search_q,
    normalize_arabic,
)

User = get_user_model()


class NormalizeArabicTests(TestCase):
    def test_folds_alef_hamza_variants(self):
        self.assertEqual(normalize_arabic("أحمد"), normalize_arabic("احمد"))
        self.assertEqual(normalize_arabic("إدارة"), normalize_arabic("ادارة"))
        self.assertEqual(normalize_arabic("آمال"), normalize_arabic("امال"))

    def test_folds_ya_and_alef_maqsura(self):
        self.assertEqual(normalize_arabic("علي"), normalize_arabic("على"))
        self.assertEqual(normalize_arabic("مصطفى"), normalize_arabic("مصطفي"))

    def test_folds_ta_marbuta_and_ha(self):
        self.assertEqual(normalize_arabic("وزارة"), normalize_arabic("وزاره"))

    def test_folds_qaf_and_ghayn(self):
        self.assertEqual(normalize_arabic("القذافي"), normalize_arabic("الغذافي"))

    def test_strips_diacritics_and_tatweel(self):
        self.assertEqual(normalize_arabic("مُحَمَّد"), normalize_arabic("محمد"))
        self.assertEqual(normalize_arabic("محـــمد"), normalize_arabic("محمد"))

    def test_folds_digits_to_ascii(self):
        self.assertEqual(normalize_arabic("قرار ١٢٣"), normalize_arabic("قرار 123"))
        self.assertEqual(normalize_arabic("۴۵"), "45")

    def test_empty_and_non_arabic_passthrough(self):
        self.assertEqual(normalize_arabic(""), "")
        self.assertEqual(normalize_arabic(None), "")
        self.assertEqual(normalize_arabic("Decree 2024"), "Decree 2024")


class ArabicSearchPatternTests(TestCase):
    def assertVariantMatch(self, term, value):
        pattern = arabic_search_pattern(term)
        self.assertTrue(
            re.search(pattern, value),
            f"pattern for {term!r} should match {value!r}",
        )

    def test_matches_variants_in_both_directions(self):
        self.assertVariantMatch("احمد", "أحمد")
        self.assertVariantMatch("أحمد", "احمد")
        self.assertVariantMatch("على", "علي")
        self.assertVariantMatch("وزاره", "وزارة")
        self.assertVariantMatch("الغذافي", "القذافي")
        self.assertVariantMatch("مكتب", "مکتب")

    def test_matches_through_diacritics_and_tatweel(self):
        self.assertVariantMatch("محمد", "مُحَمَّد")
        self.assertVariantMatch("محمد", "محـــمد")
        self.assertVariantMatch("مُحَمَّد", "محمد")

    def test_matches_digit_variants(self):
        self.assertVariantMatch("123", "قرار رقم ١٢٣")
        self.assertVariantMatch("١٢٣", "Decree 123")

    def test_escapes_regex_metacharacters(self):
        pattern = arabic_search_pattern("قرار (1)")
        self.assertTrue(re.search(pattern, "قرار (١)"))
        self.assertFalse(re.search(pattern, "قرار 1"))

    def test_empty_or_ignorable_only_term(self):
        self.assertEqual(arabic_search_pattern(""), "")
        self.assertEqual(arabic_search_pattern("ـً"), "")


class ArabicSearchQTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for i, name in enumerate(["أحمد القذافي", "مصطفى وزاره", "قرار ١٢٣", "John"]):
            User.objects.create_user(username=f"arabic-q-{i}", first_name=name)

    def search(self, term):
        return set(
            User.objects.filter(arabic_search_q(term, ["first_name"]))
            .values_list("first_name", flat=True)
        )

    def test_queryset_matches_spelling_variants(self):
        self.assertEqual(self.search("احمد"), {"أحمد القذافي"})
        self.assertEqual(self.search("الغذافي"), {"أحمد القذافي"})
        self.assertEqual(self.search("مصطفي وزارة"), {"مصطفى وزاره"})
        self.assertEqual(self.search("قرار 123"), {"قرار ١٢٣"})

    def test_empty_term_matches_everything(self):
        self.assertEqual(User.objects.filter(arabic_search_q("", ["first_name"])).count(),
                         User.objects.count())

    def test_multiple_fields_or_together(self):
        q = arabic_search_q("john", ["first_name", "username"])
        self.assertEqual(
            set(User.objects.filter(q).values_list("first_name", flat=True)),
            {"John"},
        )

"""`DluxLookupField`: search a ForeignKey by name, and add what is missing.

The matching rules are covered against a model-free register; the field is
covered against dlux's own `Scope`, which has a name and nothing else — which is
also the point, since a project adds one field declaration and no plumbing.
"""
from dlux.tests.harness import setup_test_environment  # noqa: F401

from django import forms
from django.test import TestCase

from dlux import lookup
from dlux.forms import DluxLookupField
from dlux.models import Scope


class MatchingTests(TestCase):
    """`dlux.lookup`, without a form in the way."""

    class Row:
        def __init__(self, name):
            self.name = name

    def rows(self, *names):
        return [self.Row(name) for name in names]

    def test_an_exact_name_is_that_record(self):
        rows = self.rows('Acme Trading', 'Beta Supplies')
        self.assertIs(lookup.resolve(rows, 'acme trading')[0], rows[0])

    def test_repeated_spaces_never_make_a_second_record(self):
        rows = self.rows('Acme Trading')
        self.assertIs(lookup.resolve(rows, '  Acme   Trading ')[0], rows[0])

    def test_arabic_spelling_variants_are_the_same_name(self):
        """Not typos to be scored — the script writes these letters more than one
        way, and a register accumulates both. Folded, they match exactly, so
        there is nothing to confirm."""
        rows = self.rows('شركة النور للتجارة')
        for variant in ('شركه النور للتجاره',      # ة written as ه
                        'شركة النور للتجارة',      # identical
                        'شركة الّنور للتجارة'):     # with a haraka
            with self.subTest(variant=variant):
                self.assertIs(lookup.resolve(rows, variant)[0], rows[0])

    def test_hamzated_alef_is_the_same_letter(self):
        rows = self.rows('مؤسسة الأمل')
        self.assertIs(lookup.resolve(rows, 'مؤسسة الامل')[0], rows[0])

    def test_folding_does_not_merge_genuinely_different_names(self):
        rows = self.rows('شركة كيان للاتصالات', 'شركة ليبيا للاتصالات')
        record, near = lookup.resolve(rows, 'شركة ليبيا للاتصالات')
        self.assertIs(record, rows[1])
        self.assertIsNone(near)

    def test_a_typo_is_refused_with_what_it_resembles(self):
        rows = self.rows('Acme Trading', 'Beta Supplies')
        record, near = lookup.resolve(rows, 'Acme Tradng')
        self.assertIsNone(record)
        self.assertIs(near, rows[0])

    def test_consent_lets_a_near_match_through(self):
        rows = self.rows('Acme Trading')
        self.assertEqual(lookup.resolve(rows, 'Acme Tradng', allow_new=True), (None, None))

    def test_consent_never_duplicates_an_exact_name(self):
        rows = self.rows('Acme Trading')
        self.assertIs(lookup.resolve(rows, 'Acme Trading', allow_new=True)[0], rows[0])

    def test_a_shared_leading_word_stops_distinguishing_records(self):
        """The failure that makes a plain ratio unusable: records sharing a long
        prefix and suffix look like each other, while one missing its prefix
        looks like nobody."""
        names = ['Company %s Limited' % letter for letter in 'ABCDEFGH']
        common = lookup.boilerplate_words(names)
        self.assertIn('company', common)
        self.assertIn('limited', common)
        self.assertNotIn('a', common)

    def test_a_handful_of_rows_declares_nothing_boilerplate(self):
        """Below a few rows there is no telling repetition from signal."""
        self.assertEqual(lookup.boilerplate_words(['Company A', 'Company B']), frozenset())

    def test_the_threshold_is_a_parameter_not_a_law(self):
        """A register of part numbers wants a different one from company names."""
        rows = self.rows('Acme Trading')
        self.assertIsNone(lookup.resolve(rows, 'Acme Tradng', ratio=0.99)[1])


class _PickScopeForm(forms.Form):
    """What a project writes: one field, and nothing else at all."""

    scope = DluxLookupField(queryset=Scope.objects.all(), create={})


class FieldTests(TestCase):
    """One declaration, and dlux does the rest."""

    def setUp(self):
        self.acme = Scope.objects.create(name='Acme Trading')
        Scope.objects.create(name='Beta Supplies')

    def _field(self, **kwargs):
        kwargs.setdefault('queryset', Scope.objects.all())
        return DluxLookupField(**kwargs)

    def _clean(self, field, posted):
        field.widget.value_from_datadict(posted, {}, 'scope')
        return field.clean(field.widget.value_from_datadict(posted, {}, 'scope'))

    def test_a_key_resolves_as_a_plain_choice_field_would(self):
        field = self._field()
        self.assertEqual(self._clean(field, {'scope': self.acme.pk}), self.acme)

    def test_a_name_resolves_to_its_record(self):
        field = self._field()
        self.assertEqual(self._clean(field, {'scope': 'acme trading'}), self.acme)

    def test_a_typo_is_refused(self):
        field = self._field(create={})
        with self.assertRaises(forms.ValidationError) as caught:
            self._clean(field, {'scope': 'Acme Tradng'})
        self.assertEqual(caught.exception.code, 'near_match')

    def test_consent_creates_an_unsaved_record(self):
        """Unsaved on purpose: validating must not write, or a form failing a
        later rule leaves a record behind."""
        field = self._field(create={})
        value = self._clean(field, {'scope': 'Acme Tradng', 'scope__confirm': 'on'})
        self.assertIsNone(value.pk)
        self.assertEqual(value.name, 'Acme Tradng')

    def test_a_new_name_carries_the_create_defaults(self):
        """The mapping that scopes the search is usually the right one here,
        which keeps a created record findable by the field that created it."""
        field = self._field(create={'description': 'added from a document'})
        value = self._clean(field, {'scope': 'Gamma Holdings'})
        self.assertIsNone(value.pk)
        self.assertEqual(value.name, 'Gamma Holdings')
        self.assertEqual(value.description, 'added from a document')

    def test_create_true_adds_a_record_carrying_only_the_name(self):
        """The documented shorthand for "add it, no extra columns"."""
        field = self._field(create=True)
        value = self._clean(field, {'scope': 'Gamma Holdings'})
        self.assertIsNone(value.pk)
        self.assertEqual(value.name, 'Gamma Holdings')

    def test_search_field_can_be_something_other_than_name(self):
        Scope.objects.create(name='Delta', description='D-77')
        field = self._field(search_field='description')
        self.assertEqual(self._clean(field, {'scope': 'd-77'}).name, 'Delta')

    def test_without_create_the_field_only_searches(self):
        field = self._field()
        with self.assertRaises(forms.ValidationError) as caught:
            self._clean(field, {'scope': 'Gamma Holdings'})
        self.assertEqual(caught.exception.code, 'no_such_record')

    def test_a_search_only_field_suggests_rather_than_offering_to_add(self):
        """Promising "confirm you are adding a new one" on a field that cannot
        add led straight to "no entry called that" — a dead end."""
        field = self._field()
        with self.assertRaises(forms.ValidationError) as caught:
            self._clean(field, {'scope': 'Acme Tradng'})
        self.assertEqual(caught.exception.code, 'no_such_record')
        self.assertIn('Acme Trading', caught.exception.messages[0])

    def test_consent_cannot_force_a_search_only_field_to_add(self):
        field = self._field()
        with self.assertRaises(forms.ValidationError) as caught:
            self._clean(field, {'scope': 'Acme Tradng', 'scope__confirm': 'on'})
        self.assertEqual(caught.exception.code, 'no_such_record')

    def test_a_search_only_field_renders_no_consent_box(self):
        """The panel itself still appears — the suggestion is useful — but with
        nothing offering to add, because this field cannot."""
        class SearchOnly(forms.Form):
            scope = DluxLookupField(queryset=Scope.objects.all())

        # One instance throughout: a form deep-copies its fields, so priming a
        # widget on one and rendering another asserts nothing at all.
        form = SearchOnly(data={'scope': 'Acme Tradng'})
        form.is_valid()
        html = str(form['scope'])
        self.assertIn('data-lookup-near', html, 'the suggestion should still be shown')
        self.assertNotIn('data-lookup-consent', html)

    def test_a_field_that_may_add_renders_the_consent_box(self):
        class CanAdd(forms.Form):
            scope = DluxLookupField(queryset=Scope.objects.all(), create={})

        form = CanAdd(data={'scope': 'Acme Tradng'})
        form.is_valid()
        self.assertIn('data-lookup-consent', str(form['scope']))

    def test_a_record_added_as_a_side_effect_does_not_flash_at_the_actor(self):
        """It is still logged — a record appearing deserves an audit trail — but
        adding it was a side effect of saving the form, not a second thing the
        reader did, and a success banner for it reads as one.
        """
        class CanAdd(forms.ModelForm):
            scope = DluxLookupField(queryset=Scope.objects.all(), create={})

            class Meta:
                model = Scope
                fields = ['name']

        form = CanAdd(data={'name': 'Parent', 'scope': 'Gamma Holdings'})
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        # The instance the form saved, not a re-fetch: the flag is a Python
        # attribute the signal reads, and a fresh query cannot carry it.
        created = form.cleaned_data['scope']
        self.assertIsNotNone(created.pk, 'the record should have been written')
        self.assertIs(getattr(created, '_dlux_notify_flash', None), False)
        self.assertTrue(Scope.objects.filter(name='Gamma Holdings').exists())

    def test_the_threshold_reaches_the_browser(self):
        """It governs what the typeahead offers as a guess, not only what the
        server refuses — a project raising it saw no change at all while typing,
        because the attribute was rendered and never read."""
        class Tighter(forms.Form):
            scope = DluxLookupField(queryset=Scope.objects.all(), near_ratio=0.95)

        html = str(Tighter()['scope'])
        self.assertIn('data-lookup-ratio="0.95"', html)

    def test_the_threshold_reaches_the_matcher(self):
        field = self._field(create={}, near_ratio=0.99)
        # A typo that 0.90 would refuse is accepted as new at 0.99.
        value = self._clean(field, {'scope': 'Acme Tradng'})
        self.assertIsNone(value.pk)

    def test_the_rows_come_from_the_queryset_already_declared(self):
        """Why searching needs no configuration at all."""
        form = _PickScopeForm()
        str(form['scope'])
        self.assertEqual(
            {row['label'] for row in form.fields['scope'].widget.rows},
            {'Acme Trading', 'Beta Supplies'},
        )

    def test_the_widget_renders_its_own_control_rows_and_key(self):
        """A project writes no template: the box, the rows to search and the
        hidden key it fills all come out of the widget."""
        html = str(_PickScopeForm()['scope'])
        for marker in ('data-dlux-lookup', 'data-lookup-text', 'data-lookup-value',
                       'data-lookup-options', 'Acme Trading'):
            self.assertIn(marker, html)

    def test_a_form_declaring_only_the_field_resolves_a_typed_name(self):
        """End to end through a real form, which is the whole claim."""
        form = _PickScopeForm(data={'scope': 'acme trading'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['scope'], self.acme)

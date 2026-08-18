"""Tests for the Options-page config import change set.

This import runs against a live, populated system, so the tests are mostly about
what it must *refuse* to do: never touch a key the file did not carry, never
apply anything that was not ticked, and never post a partial config blob.
"""
from django.test import SimpleTestCase, TestCase

from dlux.system.constants import SYSTEM_SETTINGS_EXPORT_FIELDS
from dlux.system.settings_diff import (
    ATOMIC_FIELDS,
    FIELD_GROUP,
    GROUPS,
    MAPPING_FIELDS,
    build_change_set,
    field_labels,
    selected_settings,
    summarize,
)


class GroupCoverageTests(SimpleTestCase):
    def test_every_exported_field_belongs_to_exactly_one_group(self):
        """Otherwise a new setting silently never appears in the review.

        This is the drift guard: add a field to SYSTEM_SETTINGS_EXPORT_FIELDS
        without grouping it and the import would quietly ignore it.
        """
        grouped = [field for _, _, fields in GROUPS for field in fields]
        self.assertEqual(
            sorted(grouped), sorted(set(grouped)),
            'a field is listed in more than one group',
        )
        self.assertEqual(
            sorted(set(SYSTEM_SETTINGS_EXPORT_FIELDS)), sorted(set(grouped)),
            'ungrouped: {}; grouped but not exported: {}'.format(
                sorted(set(SYSTEM_SETTINGS_EXPORT_FIELDS) - set(grouped)),
                sorted(set(grouped) - set(SYSTEM_SETTINGS_EXPORT_FIELDS)),
            ),
        )

    def test_atomic_and_mapping_fields_are_real_and_distinct(self):
        known = set(SYSTEM_SETTINGS_EXPORT_FIELDS)
        self.assertEqual(ATOMIC_FIELDS - known, set())
        self.assertEqual(MAPPING_FIELDS - known, set())
        self.assertEqual(
            ATOMIC_FIELDS & MAPPING_FIELDS, set(),
            'a field cannot be both all-or-nothing and expanded per key',
        )

    def test_group_order_follows_the_wizard(self):
        keys = [key for key, _, _ in GROUPS]
        self.assertEqual(keys[0], 'branding')
        self.assertIn('security', keys)
        self.assertEqual(FIELD_GROUP['home_url'], 'homepage')
        self.assertEqual(FIELD_GROUP['homepage_config'], 'homepage')
        self.assertEqual(FIELD_GROUP['search_config'], 'search')
        self.assertEqual(FIELD_GROUP['sidebar_config'], 'sidebar')


class ChangeSetTests(SimpleTestCase):
    def test_identical_settings_produce_no_changes(self):
        current = {'home_url': '/x/', 'footer_enabled': True}
        result = build_change_set(current, dict(current))
        self.assertEqual(result['groups'], [])
        self.assertEqual(result['change_count'], 0)

    def test_a_key_absent_from_the_file_is_left_alone(self):
        """The central rule. Absent must never mean "reset to default"."""
        current = {'home_url': '/x/', 'footer_text': 'keep me'}
        result = build_change_set(current, {'home_url': '/y/'})

        fields = [c['field'] for g in result['groups'] for c in g['changes']]
        self.assertEqual(fields, ['home_url'])
        self.assertNotIn('footer_text', fields)
        self.assertIn('footer_text', result['absent_keys'])

    def test_a_key_the_file_has_and_we_do_not_is_reported_not_applied(self):
        result = build_change_set({}, {'home_url': '/y/', 'from_the_future': 1})
        self.assertIn('from_the_future', result['unknown_keys'])
        fields = [c['field'] for g in result['groups'] for c in g['changes']]
        self.assertNotIn('from_the_future', fields)

    def test_scalar_change_carries_both_sides(self):
        result = build_change_set({'home_url': '/x/'}, {'home_url': '/y/'})
        change = result['groups'][0]['changes'][0]
        self.assertEqual(change['kind'], 'scalar')
        self.assertEqual(change['current'], '/x/')
        self.assertEqual(change['incoming'], '/y/')
        self.assertIsNone(change['sub_key'])

    def test_a_mapping_field_expands_to_one_row_per_changed_key(self):
        # One SMTP host change should read as one change, not "email differs".
        current = {'email_config': {'host': 'a', 'port': 25, 'username': 'u'}}
        incoming = {'email_config': {'host': 'b', 'port': 25, 'username': 'u'}}
        result = build_change_set(current, incoming)

        changes = result['groups'][0]['changes']
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['sub_key'], 'host')
        self.assertEqual(changes[0]['current'], 'a')
        self.assertEqual(changes[0]['incoming'], 'b')

    def test_a_mapping_key_missing_from_the_file_is_not_a_change(self):
        current = {'email_config': {'host': 'a', 'port': 25}}
        incoming = {'email_config': {'host': 'a'}}
        result = build_change_set(current, incoming)
        self.assertEqual(result['groups'], [], 'a key the file omitted must be left alone')

    def test_an_atomic_field_is_one_change_with_a_summary(self):
        current = {'sidebar_config': {'entries': [{'id': 'a'}, {'id': 'b'}]}}
        incoming = {'sidebar_config': {'entries': [{'id': 'a'}]}}
        result = build_change_set(current, incoming)

        change = result['groups'][0]['changes'][0]
        self.assertEqual(change['kind'], 'atomic')
        self.assertEqual(change['field'], 'sidebar_config')
        self.assertIn('summary', change)

    def test_source_metadata_is_carried_through(self):
        result = build_change_set({}, {}, source={'dlux_version': '1.7.1'})
        self.assertEqual(result['source']['dlux_version'], '1.7.1')


class LabelTests(TestCase):
    """Rows must read in the operator's language, not as raw export keys.

    Shipped wrong: the group headings were translated while every row showed its
    raw key, so an Arabic admin saw Arabic sections full of English identifiers.
    The System Settings form already carries these labels; the change set borrows
    them rather than growing a second set of strings that would drift.
    """

    def test_a_change_carries_the_forms_own_label(self):
        result = build_change_set({'home_url': '/x/'}, {'home_url': '/y/'})
        change = result['groups'][0]['changes'][0]
        self.assertIn('label', change)
        self.assertNotEqual(
            change['label'], 'home_url',
            'the row is still showing the raw export key',
        )

    def test_a_mapping_sub_key_gets_the_flattened_form_label(self):
        # The form flattens email_config.host to the field email_config_host.
        result = build_change_set(
            {'email_config': {'host': 'a'}}, {'email_config': {'host': 'b'}},
        )
        change = result['groups'][0]['changes'][0]
        self.assertNotEqual(change['label'], 'email_config')
        self.assertTrue(change['label'], 'a sub-key row must still get a label')

    def test_an_unlabelled_field_falls_back_to_its_key(self):
        labels = field_labels()
        self.assertNotIn('not_a_real_field', labels)
        result = build_change_set({'extra_config': {}}, {'extra_config': {'a': 1}})
        change = result['groups'][0]['changes'][0]
        self.assertTrue(change['label'], 'a fallback label is still a label')


class SummarizeTests(SimpleTestCase):
    def test_dict_summary_reports_added_removed_and_changed(self):
        s = summarize({'a': 1, 'b': 2}, {'b': 9, 'c': 3})
        self.assertEqual(s['added'], ['c'])
        self.assertEqual(s['removed'], ['a'])
        self.assertEqual(s['changed'], ['b'])

    def test_scalar_list_summary_reports_membership(self):
        s = summarize(['light', 'dark'], ['dark', 'neon'])
        self.assertEqual(s['added'], ['neon'])
        self.assertEqual(s['removed'], ['light'])

    def test_object_list_summary_falls_back_to_counts(self):
        # Item identity inside a builder is builder-specific; a wrong guess
        # would report confident nonsense.
        s = summarize([{'id': 'a'}], [{'id': 'a'}, {'id': 'b'}])
        self.assertEqual(s, {'count_current': 1, 'count_incoming': 2})


class SelectionTests(SimpleTestCase):
    def setUp(self):
        self.current = {
            'home_url': '/x/',
            'footer_text': 'old',
            'email_config': {'host': 'a', 'port': 25, 'username': 'keep-me'},
        }
        self.incoming = {
            'home_url': '/y/',
            'footer_text': 'new',
            'email_config': {'host': 'b', 'port': 587, 'username': 'keep-me'},
        }
        self.change_set = build_change_set(self.current, self.incoming)

    def test_nothing_selected_applies_nothing(self):
        self.assertEqual(selected_settings(self.change_set, [], self.current), {})

    def test_only_ticked_scalars_are_applied(self):
        out = selected_settings(self.change_set, ['home_url'], self.current)
        self.assertEqual(out, {'home_url': '/y/'})
        self.assertNotIn('footer_text', out, 'an unticked change must not ride along')

    def test_a_ticked_mapping_key_keeps_the_rest_of_the_config(self):
        """The one that would silently destroy an email setup.

        Applying only the ticked key would post {'host': 'b'} and wipe the port
        and username. The result must be the current config with the ticked key
        overlaid.
        """
        out = selected_settings(self.change_set, ['email_config:host'], self.current)
        self.assertEqual(out['email_config']['host'], 'b')
        self.assertEqual(out['email_config']['port'], 25, 'unticked key must keep its current value')
        self.assertEqual(out['email_config']['username'], 'keep-me')

    def test_selecting_every_mapping_key_applies_them_all(self):
        out = selected_settings(
            self.change_set, ['email_config:host', 'email_config:port'], self.current,
        )
        self.assertEqual(out['email_config']['host'], 'b')
        self.assertEqual(out['email_config']['port'], 587)

    def test_selection_does_not_mutate_the_change_set_or_current(self):
        before = self.current['email_config'].copy()
        out = selected_settings(self.change_set, ['email_config:host'], self.current)
        out['email_config']['host'] = 'mutated'
        self.assertEqual(self.current['email_config'], before)

    def test_an_unknown_token_is_ignored(self):
        out = selected_settings(self.change_set, ['not_a_field', 'home_url'], self.current)
        self.assertEqual(out, {'home_url': '/y/'})

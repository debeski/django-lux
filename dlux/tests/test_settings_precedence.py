"""Which layer wins: framework defaults, then the project's DLUX_CONFIG, then the stored row."""

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.core.cache import cache
from django.test import TestCase, override_settings

from dlux.models import SystemSettings
from dlux.system.registry import db_group_applies, iter_setting_groups
from dlux.utils.config import clear_system_config_cache, get_system_config

# Runtime key, storage field, the project's value and a different stored value.
CASES = (
    ('sidebar', 'sidebar_config', {'density': 'dense'}, {'density': 'roomy'}, 'density'),
    ('navbar', 'navbar_config', {'default_mode': 'history'}, {'default_mode': 'hierarchy', 'allow_user_mode_override': False}, 'default_mode'),
    ('login', 'login_config', {'style': 'centered'}, {'style': 'split', 'hero_message': 'x'}, 'style'),
    ('titlebar', 'titlebar_config', {'title_align': 'center'}, {'title_align': 'start', 'title_size': 'lg'}, 'title_align'),
    ('email_config', 'email_config', {'host': 'smtp.project.test'}, {'host': 'smtp.stored.test'}, 'host'),
)


class SettingsPrecedenceTests(TestCase):
    def tearDown(self):
        clear_system_config_cache()
        cache.clear()

    def stored(self, *, configured, **groups):
        obj = SystemSettings.load()
        obj.is_configured = configured
        for storage, value in groups.items():
            group = next(g for g in iter_setting_groups() if g.storage_field == storage)
            setattr(obj, storage, group.normalizer({**group.default_factory(), **value}))
        obj.save()
        clear_system_config_cache()
        cache.clear()

    def resolved(self, project):
        with override_settings(DLUX_CONFIG=project):
            clear_system_config_cache()
            return get_system_config()

    def test_every_group_declares_a_known_policy(self):
        for group in iter_setting_groups():
            db_group_applies(group.storage_field, group.default_factory() or {'x': 1}, configured=False)

    def test_a_default_valued_row_never_masks_the_project_before_setup(self):
        self.stored(configured=False, **{storage: {} for _key, storage, *_rest in CASES})
        for runtime_key, _storage, project, _stored, leaf in CASES:
            with self.subTest(group=runtime_key):
                self.assertEqual(self.resolved({runtime_key: project})[runtime_key][leaf], project[leaf])

    def test_a_changed_row_wins_before_setup(self):
        for runtime_key, storage, project, stored, leaf in CASES:
            with self.subTest(group=runtime_key):
                self.stored(configured=False, **{storage: stored})
                self.assertEqual(self.resolved({runtime_key: project})[runtime_key][leaf], stored[leaf])

    def test_the_row_wins_once_configured_even_at_its_defaults(self):
        self.stored(configured=True, **{storage: {} for _key, storage, *_rest in CASES})
        for runtime_key, storage, project, _stored, leaf in CASES:
            with self.subTest(group=runtime_key):
                group = next(g for g in iter_setting_groups() if g.storage_field == storage)
                default = group.normalizer(group.default_factory())[leaf]
                self.assertEqual(self.resolved({runtime_key: project})[runtime_key][leaf], default)

    def test_a_group_never_saved_leaves_the_project_in_charge(self):
        self.stored(configured=True)
        self.assertEqual(SystemSettings.load().sidebar_config, {})
        self.assertEqual(self.resolved({'sidebar': {'density': 'dense'}})['sidebar']['density'], 'dense')

    def test_stored_extra_features_merge_with_the_project_per_feature_and_namespace(self):
        obj = SystemSettings.load()
        obj.is_configured = True
        obj.extra_config = {'entry_clipboard': {'enabled': True}, 'app': {'project.stored': {'n': 1}}}
        obj.save()
        project = {'extra': {
            'weather': {'enabled': True},
            'entry_clipboard': {'enabled': False},
            'app': {'project.baseline': {'n': 0}, 'project.stored': {'n': 0}},
        }}
        extra = self.resolved(project)['extra_config']
        self.assertTrue(extra['weather']['enabled'])
        self.assertTrue(extra['entry_clipboard']['enabled'])
        self.assertEqual(extra['app']['project.baseline'], {'n': 0})
        self.assertEqual(extra['app']['project.stored'], {'n': 1})

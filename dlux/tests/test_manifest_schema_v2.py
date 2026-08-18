"""Release manifest schema 2.

Schema 1 published a *conclusion* (`inline_safe`), which freezes the policy in
force on release day into an artifact that outlives it, and split the reasoning
across two fields whose values came from different axes. Schema 2 states facts —
what the migrations do, what the deployment must already provide — and lets the
updater decide admission.

The tests that matter here are the refusals. A manifest is read by updaters older
than itself, so every unknown value has to fail closed; an updater that ignores a
constraint it cannot evaluate is worse than one that refuses the release.
"""
import copy

from django.test import SimpleTestCase

from dlux.updater.manifest import (
    KNOWN_REQUIREMENT_KEYS,
    MIGRATION_EFFECTS,
    SAFE_INLINE_EFFECTS,
    UpdaterError,
    validate_release_manifest,
)

V2 = {
    'schema_version': 2,
    'version': '1.8.0',
    'display': {
        'summary': 'ScanLink distribution moves into DjangoLux.',
        'highlights': ['ScanLink is off until switched on.'],
        'release_url': 'https://github.com/debeski/django-lux/releases/tag/v1.8.0',
    },
    'requires': {
        'updater_schema': '>=1',
        'baked_image': '>=1.7.0',
        'services': {'composer': '>=5.3.0'},
    },
    'migrations': {'effect': 'additive', 'rollback_compatible': True, 'downtime': 'none'},
    'install': {'inline': 'allowed'},
    'rollback': {'supported': True},
}


def _manifest(**overrides):
    manifest = copy.deepcopy(V2)
    for dotted, value in overrides.items():
        section, _, key = dotted.partition('__')
        if key:
            manifest[section][key] = value
        else:
            manifest[section] = value
    return manifest


class NormalisationTests(SimpleTestCase):
    def test_a_v2_manifest_normalises_onto_the_internal_shape(self):
        """Everything downstream keeps consuming one shape, whatever the schema."""
        out = validate_release_manifest(_manifest(), '1.8.0')
        self.assertTrue(out['inline_safe'])
        self.assertEqual(out['migration_policy'], 'backward_compatible')
        self.assertEqual(out['minimum_updater_schema'], 1)

    def test_baked_image_becomes_the_inline_floor(self):
        out = validate_release_manifest(_manifest(), '1.8.0')
        self.assertEqual(out['image_baseline'], '1.7.0')

    def test_a_release_with_no_floor_carries_none(self):
        out = validate_release_manifest(
            _manifest(requires={'updater_schema': '>=1'}), '1.8.0')
        self.assertNotIn('image_baseline', out)

    def test_required_services_survive_normalisation(self):
        """The gap schema 1 had no way to state: Composer is a hard requirement
        from 1.8.0 and the manifest could not say so."""
        out = validate_release_manifest(_manifest(), '1.8.0')
        self.assertEqual(out['required_services'], {'composer': '>=5.3.0'})

    def test_rollback_incompatible_maps_to_the_image_rebuild_policy(self):
        out = validate_release_manifest(
            _manifest(migrations__rollback_compatible=False), '1.8.0')
        self.assertEqual(out['migration_policy'], 'image_rebuild')

    def test_a_v1_manifest_still_validates_unchanged(self):
        v1 = {
            'schema_version': 1, 'version': '1.8.0', 'inline_safe': True,
            'minimum_updater_schema': 1, 'migration_policy': 'backward_compatible',
            'summary': 'x', 'release_url': 'https://github.com/debeski/django-lux/releases/tag/v1.8.0',
        }
        self.assertTrue(validate_release_manifest(v1, '1.8.0')['inline_safe'])


class InlineAdmissionTests(SimpleTestCase):
    def test_the_author_cannot_wave_through_a_destructive_migration(self):
        """`install.inline` is a permission, not an override.

        Both statements must agree: the author allows it AND the migrations are
        actually harmless. This is the whole reason schema 2 records the effect
        rather than trusting a single boolean.
        """
        out = validate_release_manifest(
            _manifest(migrations__effect='destructive'), '1.8.0')
        self.assertFalse(out['inline_safe'])

    def test_forbidding_inline_wins_over_harmless_migrations(self):
        out = validate_release_manifest(_manifest(install={'inline': 'forbidden'}), '1.8.0')
        self.assertFalse(
            out['inline_safe'],
            'a dependency-driven block must survive harmless migrations',
        )

    def test_every_safe_effect_is_a_real_effect(self):
        self.assertTrue(SAFE_INLINE_EFFECTS.issubset(set(MIGRATION_EFFECTS)))

    def test_the_dangerous_effects_are_not_inline(self):
        for effect in set(MIGRATION_EFFECTS) - SAFE_INLINE_EFFECTS:
            with self.subTest(effect=effect):
                out = validate_release_manifest(_manifest(migrations__effect=effect), '1.8.0')
                self.assertFalse(out['inline_safe'])


class FailClosedTests(SimpleTestCase):
    """A manifest outlives the updaters that read it."""

    def test_an_unknown_requirement_is_refused_not_ignored(self):
        """The rule that makes `requires` safely extensible forever.

        A later schema adding `postgres` must make OLDER updaters refuse, not
        silently install while ignoring a constraint they cannot evaluate.
        """
        with self.assertRaises(UpdaterError):
            validate_release_manifest(
                _manifest(requires={**V2['requires'], 'postgres': '>=14'}), '1.8.0')

    def test_an_unknown_migration_effect_is_refused(self):
        with self.assertRaises(UpdaterError):
            validate_release_manifest(
                _manifest(migrations__effect='partitioned_rewrite'), '1.8.0')

    def test_an_unknown_install_mode_is_refused(self):
        with self.assertRaises(UpdaterError):
            validate_release_manifest(_manifest(install={'inline': 'maybe'}), '1.8.0')

    def test_rollback_compatible_must_be_stated_explicitly(self):
        """Defaulting it either way guesses at the operator's safety net."""
        migrations = {'effect': 'additive', 'downtime': 'none'}
        with self.assertRaises(UpdaterError):
            validate_release_manifest(_manifest(migrations=migrations), '1.8.0')

    def test_a_future_schema_is_refused(self):
        with self.assertRaises(UpdaterError):
            validate_release_manifest(_manifest(schema_version=3), '1.8.0')

    def test_python_and_dependencies_are_not_manifest_concerns(self):
        """The wheel declares them in Requires-Python/Requires-Dist and pip
        enforces them; a second copy here could only ever disagree."""
        self.assertNotIn('python', KNOWN_REQUIREMENT_KEYS)
        self.assertNotIn('dependencies', KNOWN_REQUIREMENT_KEYS)


class ImageBaselineAutomationTests(SimpleTestCase):
    """The floor is derived from published history, not carried by hand.

    RELEASING.md made it an authoring convention — "carry image_baseline on every
    subsequent manifest until the next image-required release". It was never
    followed: v1.2.7 shipped image_rebuild and every release from v1.3.0 to
    v1.7.1 omitted the floor, so a box on a pre-1.2.7 image could be offered a
    later inline-safe release and skip the rebuild. Deriving it closes that.
    """

    def test_the_shipped_manifest_declares_the_computed_floor(self):
        import json
        from pathlib import Path
        import dlux
        from dlux.updater.release_check import validate_image_baseline

        manifest = json.loads(
            (Path(dlux.__file__).parent / 'release-manifest.json').read_text(encoding='utf-8')
        )
        self.assertEqual(
            validate_image_baseline(manifest), [],
            'the release manifest floor disagrees with published history',
        )

    def test_a_v1_manifest_forbidding_inline_is_recognised(self):
        from dlux.updater.release_check import _forbids_inline
        self.assertTrue(_forbids_inline({'schema_version': 1, 'inline_safe': False}))
        self.assertFalse(_forbids_inline({'schema_version': 1, 'inline_safe': True}))

    def test_a_v2_manifest_forbidding_inline_is_recognised(self):
        from dlux.updater.release_check import _forbids_inline
        self.assertTrue(
            _forbids_inline({'schema_version': 2, 'install': {'inline': 'forbidden'}}))
        self.assertFalse(
            _forbids_inline({'schema_version': 2, 'install': {'inline': 'allowed'}}))

    def test_a_floor_below_the_computed_one_is_refused(self):
        from dlux.updater.release_check import expected_image_baseline, validate_image_baseline
        expected = expected_image_baseline()
        if not expected:
            self.skipTest('no outstanding image dependency in this history')
        errors = validate_image_baseline(
            {'schema_version': 2, 'requires': {'baked_image': '>=0.0.1'}})
        self.assertTrue(errors, 'a floor below the computed one must be refused')

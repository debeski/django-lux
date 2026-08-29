from dlux.tests.harness import setup_test_environment

setup_test_environment()

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Field, Layout, Row
from django import forms
from django.db import models
from django.template import Context, Template
from django.test import SimpleTestCase
from django.test.utils import isolate_apps
from unittest.mock import patch

from dlux.models import DluxNotificationRule
from dlux.utils import discover_section_models, resolve_form_class_for_model


class DiscoverSectionModelsTests(SimpleTestCase):
    @isolate_apps("dlux")
    def test_generic_table_is_built_for_section_model(self):
        class Document(models.Model):
            is_section = True
            title = models.CharField(max_length=255)

            class Meta:
                app_label = "dlux"

        class StubAppConfig:
            name = "dlux"
            label = "dlux"

            @staticmethod
            def get_models():
                return [Document]

        with patch('dlux.utils.sections.apps.get_app_config', return_value=StubAppConfig()):
            section_models = discover_section_models(app_name="dlux")

        self.assertEqual(len(section_models), 1)
        sm = section_models[0]
        self.assertIs(sm["model"], Document)
        self.assertIsNotNone(sm["table_class"])
        self.assertIs(sm["table_class"].Meta.model, Document)


class ResolveSectionFormTests(SimpleTestCase):
    def test_disabled_scope_is_removed_from_nested_crispy_layout(self):
        class NotificationRuleForm(forms.ModelForm):
            helper = FormHelper()
            helper.form_tag = False
            helper.layout = Layout(
                Row(
                    Column(Field('name')),
                    Column(Field('scope')),
                )
            )

            class Meta:
                model = DluxNotificationRule
                fields = ['name']

        with patch('dlux.utils.discovery._import_by_convention', return_value=NotificationRuleForm), \
             patch('dlux.utils.discovery.is_scope_enabled', return_value=False), \
             patch('dlux.utils.is_scope_enabled', return_value=False):
            form_class = resolve_form_class_for_model(DluxNotificationRule)
            form = form_class()

        self.assertNotIn('scope', form.fields)
        self.assertEqual(
            [pointer.name for pointer in form.helper.layout.get_field_names()],
            ['name'],
        )
        with self.assertNoLogs(level='WARNING'):
            html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(
                Context({'form': form})
            )
        self.assertIn('name="name"', html)

        self.assertIn(
            'scope',
            [pointer.name for pointer in NotificationRuleForm.helper.layout.get_field_names()],
        )
        with patch('dlux.utils.discovery.is_scope_enabled', return_value=True), \
             patch('dlux.utils.is_scope_enabled', return_value=True):
            enabled_form = form_class()
        self.assertIn('scope', enabled_form.fields)
        self.assertIn(
            'scope',
            [pointer.name for pointer in enabled_form.helper.layout.get_field_names()],
        )

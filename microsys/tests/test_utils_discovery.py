from django.db import models
from django.test import SimpleTestCase
from django.test.utils import isolate_apps
from unittest.mock import patch

from microsys.utils import discover_section_models


class DiscoverSectionModelsTests(SimpleTestCase):
    @isolate_apps("microsys")
    def test_generic_table_is_built_for_section_model(self):
        class Document(models.Model):
            is_section = True
            title = models.CharField(max_length=255)

            class Meta:
                app_label = "microsys"

        class StubAppConfig:
            name = "microsys"
            label = "microsys"

            @staticmethod
            def get_models():
                return [Document]

        with patch('microsys.utils.apps.get_app_config', return_value=StubAppConfig()):
            section_models = discover_section_models(app_name="microsys")

        self.assertEqual(len(section_models), 1)
        sm = section_models[0]
        self.assertIs(sm["model"], Document)
        self.assertIsNotNone(sm["table_class"])
        self.assertIs(sm["table_class"].Meta.model, Document)

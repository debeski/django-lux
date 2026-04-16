from django.db import models
from django.test import SimpleTestCase
from django.test.utils import isolate_apps

from microsys.utils import discover_section_models


class DiscoverSectionModelsTests(SimpleTestCase):
    @isolate_apps("tests")
    def test_generic_table_is_built_for_section_model(self):
        class Document(models.Model):
            is_section = True
            title = models.CharField(max_length=255)

            class Meta:
                app_label = "tests"

        section_models = discover_section_models(app_name="tests")

        self.assertEqual(len(section_models), 1)
        sm = section_models[0]
        self.assertIs(sm["model"], Document)
        self.assertIsNotNone(sm["table_class"])
        self.assertIs(sm["table_class"].Meta.model, Document)

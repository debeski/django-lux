"""Tables render a translated field in the viewer's language.

``TranslationMixin`` has always given a model ``t_<field>``, but django-tables2
reads the raw field, so every consuming project had to remember a render method
per table — and a project that forgot one showed the source language under an
English interface with no error to notice. The model half of the feature shipped
without the table half; these cover the table half.
"""
from django.db import models
from django.test import SimpleTestCase
from django.test.utils import isolate_apps
from django.utils import translation

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from dlux.models import TranslationMixin
from dlux.tables import DluxTable


def _translated_model():
    class Product(TranslationMixin, models.Model):
        translated_fields = ["name"]
        name = models.CharField(max_length=255)
        name_en = models.CharField(max_length=255, blank=True)
        sku = models.CharField(max_length=32, blank=True)

        class Meta:
            app_label = "dlux"

        @property
        def name_ar(self):
            return self.name

    return Product


class TranslatedColumnRenderingTests(SimpleTestCase):
    def _cell(self, table, column="name", index=0):
        return table.rows[index].get_cell(column)

    @isolate_apps("dlux")
    def test_the_column_follows_the_active_language(self):
        Product = _translated_model()

        class ProductTable(DluxTable):
            class Meta(DluxTable.Meta):
                model = Product
                fields = ("name", "sku")

        rows = [Product(name="عينة", name_en="Sample")]

        with translation.override("en"):
            self.assertEqual(self._cell(ProductTable(rows)), "Sample")
        with translation.override("ar"):
            self.assertEqual(self._cell(ProductTable(rows)), "عينة")

    @isolate_apps("dlux")
    def test_it_falls_back_to_the_canonical_value_when_untranslated(self):
        Product = _translated_model()

        class ProductTable(DluxTable):
            class Meta(DluxTable.Meta):
                model = Product
                fields = ("name",)

        rows = [Product(name="عينة", name_en="")]

        with translation.override("en"):
            self.assertEqual(self._cell(ProductTable(rows)), "عينة")

    @isolate_apps("dlux")
    def test_a_table_that_defines_its_own_renderer_keeps_it(self):
        """A table that has already said how to draw a column means it."""
        Product = _translated_model()

        class ProductTable(DluxTable):
            class Meta(DluxTable.Meta):
                model = Product
                fields = ("name",)

            def render_name(self, record):
                return f"[{record.name}]"

        with translation.override("en"):
            table = ProductTable([Product(name="عينة", name_en="Sample")])
            self.assertEqual(self._cell(table), "[عينة]")

    @isolate_apps("dlux")
    def test_an_untranslated_column_is_left_alone(self):
        Product = _translated_model()

        class ProductTable(DluxTable):
            class Meta(DluxTable.Meta):
                model = Product
                fields = ("name", "sku")

        with translation.override("en"):
            table = ProductTable([Product(name="عينة", name_en="Sample", sku="A-1")])
            self.assertEqual(self._cell(table, "sku"), "A-1")

    @isolate_apps("dlux")
    def test_a_translated_field_that_is_not_a_column_is_ignored(self):
        """`translated_fields` describes the model, not the table."""
        class Product(TranslationMixin, models.Model):
            translated_fields = ["name", "description"]
            name = models.CharField(max_length=255)
            name_en = models.CharField(max_length=255, blank=True)
            description = models.TextField(blank=True)

            class Meta:
                app_label = "dlux"

        class ProductTable(DluxTable):
            class Meta(DluxTable.Meta):
                model = Product
                fields = ("name",)

        with translation.override("en"):
            table = ProductTable([Product(name="عينة", name_en="Sample")])
            self.assertEqual(self._cell(table), "Sample")

    @isolate_apps("dlux")
    def test_a_model_without_translations_is_untouched(self):
        class Plain(models.Model):
            name = models.CharField(max_length=255)

            class Meta:
                app_label = "dlux"

        class PlainTable(DluxTable):
            class Meta(DluxTable.Meta):
                model = Plain
                fields = ("name",)

        self.assertEqual(self._cell(PlainTable([Plain(name="عينة")])), "عينة")

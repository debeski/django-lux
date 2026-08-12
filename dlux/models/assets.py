"""Managed assets: uploaded images and font families/variants."""

from django.db import models
from django.conf import settings
from django.utils.text import slugify
import uuid
from pathlib import Path
from ..fonts import clear_font_cache


def managed_asset_upload_to(instance, filename):
    suffix = Path(str(filename or '')).suffix.lower()
    return f"dlux/assets/{instance.kind}/{uuid.uuid4().hex}{suffix}"


class ManagedAsset(models.Model):
    KIND_IMAGE = 'image'
    KIND_FONT = 'font'
    KIND_CHOICES = (
        (KIND_IMAGE, 'Image'),
        (KIND_FONT, 'Font'),
    )

    title = models.CharField(max_length=150, verbose_name="Asset Name")
    slug = models.SlugField(max_length=180, unique=True, verbose_name="Asset Slug")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, db_default=KIND_IMAGE, verbose_name="Asset Type")
    file = models.FileField(upload_to=managed_asset_upload_to, verbose_name="Asset File")
    mime_type = models.CharField(max_length=100, blank=True, db_default='', verbose_name="MIME Type")
    size_bytes = models.PositiveBigIntegerField(default=0, db_default=0, verbose_name="File Size")
    checksum = models.CharField(max_length=64, db_index=True, verbose_name="SHA-256")
    width = models.PositiveIntegerField(null=True, blank=True, verbose_name="Image Width")
    height = models.PositiveIntegerField(null=True, blank=True, verbose_name="Image Height")
    is_active = models.BooleanField(default=True, db_default=True, verbose_name="Active")
    created_at = models.DateTimeField(auto_now_add=True, editable=False, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, editable=False, verbose_name="Updated At")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name='+',
        on_delete=models.SET_NULL,
        editable=False,
        verbose_name="Created By",
    )

    class Meta:
        verbose_name = "Managed Asset"
        verbose_name_plural = "Managed Assets"
        default_permissions = ()
        ordering = ('kind', 'title', 'pk')

    def __str__(self):
        return self.title

    @property
    def filename(self):
        return Path(str(getattr(self.file, 'name', '') or '')).name

    @property
    def url(self):
        if not self.file:
            return ''
        try:
            if not self.file.storage.exists(self.file.name):
                return ''
            return self.file.url
        except Exception:
            return ''

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title) or self.kind or 'asset'
            candidate = base[:160]
            index = 2
            while type(self).objects.exclude(pk=self.pk).filter(slug=candidate).exists():
                suffix = f'-{index}'
                candidate = f"{base[:160 - len(suffix)]}{suffix}"
                index += 1
            self.slug = candidate
        super().save(*args, **kwargs)
        clear_font_cache()


    def delete(self, *args, **kwargs):
        storage = getattr(self.file, 'storage', None)
        stored_name = str(getattr(self.file, 'name', '') or '')
        result = super().delete(*args, **kwargs)
        if storage is not None and stored_name:
            from django.db import transaction
            model = type(self)
            transaction.on_commit(
                lambda: None if model.objects.filter(file=stored_name).exists() else storage.delete(stored_name)
            )
        return result
        clear_font_cache()


class ManagedFontFamily(models.Model):
    slug = models.SlugField(max_length=50, unique=True, verbose_name="Font Slug")
    family = models.CharField(max_length=100, verbose_name="CSS Font Family")
    label = models.CharField(max_length=100, verbose_name="Font Label")
    is_active = models.BooleanField(default=True, db_default=True, verbose_name="Active")
    created_at = models.DateTimeField(auto_now_add=True, editable=False, verbose_name="Created At")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name='+',
        on_delete=models.SET_NULL,
        editable=False,
        verbose_name="Created By",
    )

    class Meta:
        verbose_name = "Managed Font Family"
        verbose_name_plural = "Managed Font Families"
        default_permissions = ()
        ordering = ('label', 'pk')

    def __str__(self):
        return self.label

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        clear_font_cache()

    def delete(self, *args, **kwargs):
        result = super().delete(*args, **kwargs)
        clear_font_cache()
        return result


class ManagedFontVariant(models.Model):
    STYLE_NORMAL = 'normal'
    STYLE_ITALIC = 'italic'
    STYLE_CHOICES = (
        (STYLE_NORMAL, 'Normal'),
        (STYLE_ITALIC, 'Italic'),
    )

    font = models.ForeignKey(
        'dlux.ManagedFontFamily',
        on_delete=models.CASCADE,
        related_name='variants',
        verbose_name="Font Family",
    )
    asset = models.ForeignKey(
        'dlux.ManagedAsset',
        on_delete=models.PROTECT,
        related_name='font_variant_uses',
        verbose_name="Font Asset",
    )
    weight = models.PositiveSmallIntegerField(default=400, db_default=400, verbose_name="Font Weight")
    style = models.CharField(max_length=10, choices=STYLE_CHOICES, default=STYLE_NORMAL, db_default=STYLE_NORMAL, verbose_name="Font Style")

    class Meta:
        verbose_name = "Managed Font Variant"
        verbose_name_plural = "Managed Font Variants"
        default_permissions = ()
        ordering = ('font', 'weight', 'style', 'pk')
        unique_together = ('font', 'weight', 'style')

    def __str__(self):
        return f"{self.font.label} {self.weight} {self.style}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        clear_font_cache()

    def delete(self, *args, **kwargs):
        result = super().delete(*args, **kwargs)
        clear_font_cache()
        return result

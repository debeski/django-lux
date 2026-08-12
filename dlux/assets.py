import hashlib
import re
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import transaction


IMAGE_EXTENSIONS = {'.gif', '.ico', '.jpeg', '.jpg', '.png', '.webp'}
FONT_EXTENSIONS = {'.woff2'}
FONT_SLUG_RE = re.compile(r'^[a-z][a-z0-9_-]{0,49}$')
FONT_FAMILY_RE = re.compile(r'^\w[\w .-]{0,99}$')


def _max_bytes(kind):
    setting_name = 'DLUX_ASSET_MAX_FONT_MB' if kind == 'font' else 'DLUX_ASSET_MAX_IMAGE_MB'
    default_mb = 20 if kind == 'font' else 10
    try:
        limit_mb = max(1, int(getattr(settings, setting_name, default_mb)))
    except (TypeError, ValueError):
        limit_mb = default_mb
    return limit_mb * 1024 * 1024


def _checksum(upload):
    digest = hashlib.sha256()
    upload.seek(0)
    for chunk in iter(lambda: upload.read(1024 * 1024), b''):
        digest.update(chunk)
    upload.seek(0)
    return digest.hexdigest()


def validate_asset_upload(upload, kind):
    if kind not in {'image', 'font'}:
        raise ValidationError("Unsupported asset type.")
    if not upload:
        raise ValidationError("Choose a file to upload.")

    size = int(getattr(upload, 'size', 0) or 0)
    if size <= 0:
        raise ValidationError("The uploaded file is empty.")
    if size > _max_bytes(kind):
        raise ValidationError("The uploaded asset exceeds the configured size limit.")

    suffix = Path(str(getattr(upload, 'name', '') or '')).suffix.lower()
    allowed_extensions = FONT_EXTENSIONS if kind == 'font' else IMAGE_EXTENSIONS
    if suffix not in allowed_extensions:
        raise ValidationError("This file type is not allowed for the selected asset type.")

    metadata = {
        'checksum': _checksum(upload),
        'size_bytes': size,
        'mime_type': str(getattr(upload, 'content_type', '') or ''),
        'width': None,
        'height': None,
    }
    if kind == 'font':
        upload.seek(0)
        header = upload.read(48)
        upload.seek(0)
        declared_length = int.from_bytes(header[8:12], 'big') if len(header) >= 12 else 0
        table_count = int.from_bytes(header[12:14], 'big') if len(header) >= 14 else 0
        reserved = int.from_bytes(header[14:16], 'big') if len(header) >= 16 else 1
        sfnt_size = int.from_bytes(header[16:20], 'big') if len(header) >= 20 else 0
        compressed_size = int.from_bytes(header[20:24], 'big') if len(header) >= 24 else 0
        if (
            len(header) != 48
            or header[:4] != b'wOF2'
            or size <= 48
            or declared_length != size
            or table_count < 1
            or reserved != 0
            or sfnt_size < 12
            or compressed_size < 1
            or compressed_size > size - 48
        ):
            raise ValidationError("The font file is not a valid WOFF2 asset.")
        metadata['mime_type'] = 'font/woff2'
        return metadata

    try:
        upload.seek(0)
        with Image.open(upload) as image:
            image.verify()
        upload.seek(0)
        with Image.open(upload) as image:
            metadata['width'], metadata['height'] = image.size
            metadata['mime_type'] = Image.MIME.get(image.format, metadata['mime_type'] or 'application/octet-stream')
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        upload.seek(0)
        raise ValidationError("The uploaded file is not a valid image.") from exc
    upload.seek(0)
    return metadata


def _asset_title(upload, title=''):
    resolved = str(title or '').strip()
    if resolved:
        return resolved[:150]
    return (Path(str(getattr(upload, 'name', '') or '')).stem or 'Asset')[:150]


def create_managed_asset(upload, *, kind, user=None, title=''):
    metadata = validate_asset_upload(upload, kind)
    Asset = apps.get_model('dlux', 'ManagedAsset')
    existing = Asset.objects.filter(
        kind=kind,
        checksum=metadata['checksum'],
        is_active=True,
    ).first()
    if existing:
        return existing, False

    asset = Asset(
        title=_asset_title(upload, title),
        kind=kind,
        file=upload,
        created_by=user if getattr(user, 'is_authenticated', False) else None,
        **metadata,
    )
    asset.full_clean(exclude=('slug',))
    asset.save()
    return asset, True


def adopt_stored_asset(field_file, *, user=None, title=''):
    stored_name = str(getattr(field_file, 'name', '') or '').strip()
    storage = getattr(field_file, 'storage', None)
    return adopt_storage_asset(stored_name, storage=storage, user=user, title=title)


def adopt_storage_asset(stored_name, *, storage=None, user=None, title=''):
    stored_name = str(stored_name or '').strip()
    normalized_parts = Path(stored_name).parts
    if not stored_name or Path(stored_name).is_absolute() or '..' in normalized_parts:
        return None
    storage = storage or default_storage
    try:
        if not storage.exists(stored_name):
            return None
        with storage.open(stored_name, 'rb') as stored:
            wrapped = File(stored, name=Path(stored_name).name)
            metadata = validate_asset_upload(wrapped, 'image')
    except (OSError, ValidationError):
        return None

    Asset = apps.get_model('dlux', 'ManagedAsset')
    existing = Asset.objects.filter(kind='image', checksum=metadata['checksum'], is_active=True).first()
    if existing:
        return existing
    asset = Asset(
        title=_asset_title(Path(stored_name), title),
        kind='image',
        file=stored_name,
        created_by=user if getattr(user, 'is_authenticated', False) else None,
        **metadata,
    )
    asset.full_clean(exclude=('slug',))
    asset.save()
    return asset


def register_managed_font(asset, *, slug, family, label='', weight=400, style='normal', user=None):
    normalized_slug = str(slug or '').strip().lower()
    normalized_family = str(family or '').strip()
    normalized_label = str(label or normalized_family).strip()
    if not FONT_SLUG_RE.fullmatch(normalized_slug):
        raise ValidationError("Font slug must start with a letter and use lowercase letters, numbers, underscores, or hyphens.")
    if not FONT_FAMILY_RE.fullmatch(normalized_family):
        raise ValidationError("Enter a valid CSS font family name.")
    if not normalized_label or len(normalized_label) > 100:
        raise ValidationError("Enter a font label up to 100 characters.")
    if asset.kind != 'font':
        raise ValidationError("Font variants must reference a WOFF2 font asset.")
    try:
        normalized_weight = int(weight)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Font weight must be between 100 and 900.") from exc
    if normalized_weight not in range(100, 901, 100):
        raise ValidationError("Font weight must be between 100 and 900 in steps of 100.")
    if style not in {'normal', 'italic'}:
        raise ValidationError("Unsupported font style.")

    FontFamily = apps.get_model('dlux', 'ManagedFontFamily')
    FontVariant = apps.get_model('dlux', 'ManagedFontVariant')
    with transaction.atomic():
        font, created = FontFamily.objects.get_or_create(
            slug=normalized_slug,
            defaults={
                'family': normalized_family,
                'label': normalized_label,
                'created_by': user if getattr(user, 'is_authenticated', False) else None,
            },
        )
        if not created and font.family != normalized_family:
            raise ValidationError("That font slug is already registered to another family.")
        if not font.is_active:
            font.is_active = True
        if font.label != normalized_label:
            font.label = normalized_label
        font.save(update_fields=['label', 'is_active'])
        variant, _ = FontVariant.objects.update_or_create(
            font=font,
            weight=normalized_weight,
            style=style,
            defaults={'asset': asset},
        )

        SystemSettings = apps.get_model('dlux', 'SystemSettings')
        system_settings = SystemSettings.load()
        allowed_fonts = list(system_settings.allowed_fonts or [])
        if normalized_slug not in allowed_fonts:
            allowed_fonts.append(normalized_slug)
            system_settings.allowed_fonts = allowed_fonts
            system_settings.save(update_fields=['typography_config'])
    return font, variant


def collect_asset_usages(asset):
    from dlux.utils import collect_related_objects
    return collect_related_objects(asset)

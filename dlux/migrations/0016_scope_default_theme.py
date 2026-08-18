# Folded migration. The former 0017 (settings snapshot), 0018 (ScanLink
# releases) and the homepage/search JSON fields were squashed into this file:
# none of them had shipped in a release — v1.7.1 ends at 0015 — so there is no
# deployment with the old numbering to preserve.
#
# The fold also removed 0018's AlterField on ManagedAsset.kind: with CreateModel
# in the same migration, the `installer` choice is simply part of the table's
# definition, so there is no field alteration left to reason about.
import django.db.models.deletion
import dlux.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dlux', '0015_systemrestore_progress'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='scope',
            name='default_theme',
            field=models.CharField(blank=True, db_default='', default='', max_length=50, verbose_name='Default Theme'),
        ),
        migrations.CreateModel(
            name='ManagedAsset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=150, verbose_name='Asset Name')),
                ('slug', models.SlugField(max_length=180, unique=True, verbose_name='Asset Slug')),
                ('kind', models.CharField(choices=[('image', 'Image'), ('font', 'Font'), ('installer', 'Installer')], db_default='image', max_length=20, verbose_name='Asset Type')),
                ('file', models.FileField(upload_to=dlux.models.managed_asset_upload_to, verbose_name='Asset File')),
                ('mime_type', models.CharField(blank=True, db_default='', max_length=100, verbose_name='MIME Type')),
                ('size_bytes', models.PositiveBigIntegerField(db_default=0, default=0, verbose_name='File Size')),
                ('checksum', models.CharField(db_index=True, max_length=64, verbose_name='SHA-256')),
                ('width', models.PositiveIntegerField(blank=True, null=True, verbose_name='Image Width')),
                ('height', models.PositiveIntegerField(blank=True, null=True, verbose_name='Image Height')),
                ('is_active', models.BooleanField(db_default=True, default=True, verbose_name='Active')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('created_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Created By')),
            ],
            options={
                'verbose_name': 'Managed Asset',
                'verbose_name_plural': 'Managed Assets',
                'ordering': ('kind', 'title', 'pk'),
                'default_permissions': (),
            },
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='favicon_asset',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='favicon_uses', to='dlux.managedasset', verbose_name='Favicon Asset'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='login_background_asset',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='login_background_uses', to='dlux.managedasset', verbose_name='Login Background Asset'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='login_logo_asset',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='login_logo_uses', to='dlux.managedasset', verbose_name='Login Logo Asset'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='logo_asset',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='system_logo_uses', to='dlux.managedasset', verbose_name='System Logo Asset'),
        ),
        migrations.CreateModel(
            name='ManagedFontFamily',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(unique=True, verbose_name='Font Slug')),
                ('family', models.CharField(max_length=100, verbose_name='CSS Font Family')),
                ('label', models.CharField(max_length=100, verbose_name='Font Label')),
                ('is_active', models.BooleanField(db_default=True, default=True, verbose_name='Active')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('created_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Created By')),
            ],
            options={
                'verbose_name': 'Managed Font Family',
                'verbose_name_plural': 'Managed Font Families',
                'ordering': ('label', 'pk'),
                'default_permissions': (),
            },
        ),
        migrations.CreateModel(
            name='ManagedFontVariant',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('weight', models.PositiveSmallIntegerField(db_default=400, default=400, verbose_name='Font Weight')),
                ('style', models.CharField(choices=[('normal', 'Normal'), ('italic', 'Italic')], db_default='normal', default='normal', max_length=10, verbose_name='Font Style')),
                ('asset', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='font_variant_uses', to='dlux.managedasset', verbose_name='Font Asset')),
                ('font', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='variants', to='dlux.managedfontfamily', verbose_name='Font Family')),
            ],
            options={
                'verbose_name': 'Managed Font Variant',
                'verbose_name_plural': 'Managed Font Variants',
                'ordering': ('font', 'weight', 'style', 'pk'),
                'default_permissions': (),
                'unique_together': {('font', 'weight', 'style')},
            },
        ),
        migrations.CreateModel(
            name='SystemSettingsSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('reason', models.CharField(default='config_import', max_length=64)),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('applied_keys', models.JSONField(blank=True, default=list)),
                ('reverted_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='dlux_settings_snapshots', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'System Settings Snapshot',
                'verbose_name_plural': 'System Settings Snapshots',
                'ordering': ('-created_at',),
            },
        ),
        migrations.CreateModel(
            name='ScanLinkRelease',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('version', models.CharField(max_length=32, verbose_name='Version')),
                ('arch', models.CharField(choices=[('x64', 'x64'), ('x86', 'x86')], default='x64', max_length=8, verbose_name='Architecture')),
                ('is_active', models.BooleanField(default=True, verbose_name='Active')),
                ('notes', models.CharField(blank=True, max_length=255, verbose_name='Notes')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('asset', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='scanlink_releases', to='dlux.managedasset', verbose_name='Installer')),
                ('created_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'ScanLink Release',
                'verbose_name_plural': 'ScanLink Releases',
                'ordering': ('-created_at',),
                'default_permissions': (),
                'unique_together': {('version', 'arch')},
            },
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='homepage_config',
            field=models.JSONField(
                blank=True,
                db_default={
                    'default_url': '/accounts/profile/',
                    'allow_user_override': False,
                    'public': {
                        'enabled': False,
                        'separate_url': False,
                        'url': '',
                        'theme': '',
                        'title': '',
                        'meta_description': '',
                        'show_titlebar': False,
                        'show_sidebar': False,
                    },
                },
                default=dlux.models.default_homepage_config,
                verbose_name='Homepage Configuration',
            ),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='search_config',
            field=models.JSONField(
                blank=True,
                db_default={'enabled': True, 'display_mode': 'icon', 'include_data': False},
                default=dlux.models.default_search_config,
                verbose_name='Search Configuration',
            ),
        ),
    ]

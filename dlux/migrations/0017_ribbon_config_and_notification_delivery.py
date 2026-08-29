"""Everything added since v1.8.1, in one migration.

Folded rather than left as a chain: neither had shipped, and a release is
easier to reason about when the version that introduces a set of fields adds
them once. `0016_scope_default_theme` is untouched — it ships in v1.8.1, so
editing it would leave every deployment that already applied it without these
columns.
"""
import dlux.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dlux', '0016_scope_default_theme'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='ribbon_config',
            field=models.JSONField(blank=True, db_default={}, default=dict, verbose_name='Ribbon Configuration'),
        ),
        migrations.AddField(
            model_name='dluxnotification',
            name='badge_enabled',
            field=models.BooleanField(db_default=True, default=True, verbose_name='Badge Enabled'),
        ),
        migrations.AddField(
            model_name='dluxnotification',
            name='event_key',
            field=models.CharField(blank=True, max_length=255, null=True, unique=True, verbose_name='Event Key'),
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name='systemsettings',
                    name='public_root_config',
                    field=models.JSONField(blank=True, default=dlux.models.default_public_root_config, verbose_name='Public Page Configuration'),
                ),
            ],
        ),
    ]

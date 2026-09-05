from django.db import migrations, models


class Migration(migrations.Migration):
    """Add the `applying` run status Composer's hand-off reports.

    State-only on purpose: `choices` is validated in Python and never in the
    schema, so an empty `database_operations` runs nothing against the database
    and the release stays inline-safe (see docs/RELEASING.md).
    """

    dependencies = [
        ('dlux', '0019_update_state_worker_report'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name='dluxupdaterun',
                    name='status',
                    field=models.CharField(
                        choices=[
                            ('queued', 'Queued'),
                            ('checking', 'Checking'),
                            ('downloading', 'Downloading'),
                            ('verifying', 'Verifying'),
                            ('applying', 'Applying'),
                            ('staging', 'Staging'),
                            ('preflight', 'Preflight'),
                            ('backing_up', 'Backing Up'),
                            ('maintenance', 'Maintenance'),
                            ('migrating', 'Migrating'),
                            ('collecting_static', 'Collecting Static'),
                            ('switching', 'Switching'),
                            ('restarting', 'Restarting'),
                            ('verifying_health', 'Verifying Health'),
                            ('completed', 'Completed'),
                            ('failed', 'Failed'),
                            ('rolled_back', 'Rolled Back'),
                        ],
                        db_index=True,
                        default='queued',
                        max_length=32,
                        verbose_name='Status',
                    ),
                ),
            ],
        ),
    ]

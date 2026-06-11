from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("microsys", "0012_reportbackup"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="useractivitylog",
            index=models.Index(fields=["created_at"], name="ms_ual_created_idx"),
        ),
        migrations.AddIndex(
            model_name="useractivitylog",
            index=models.Index(fields=["scope", "created_at"], name="ms_ual_scope_created_idx"),
        ),
        migrations.AddIndex(
            model_name="useractivitylog",
            index=models.Index(fields=["created_by", "created_at"], name="ms_ual_actor_created_idx"),
        ),
        migrations.AddIndex(
            model_name="useractivitylog",
            index=models.Index(fields=["model_key", "created_at"], name="ms_ual_model_created_idx"),
        ),
        migrations.AddIndex(
            model_name="useractivitylog",
            index=models.Index(fields=["action", "created_at"], name="ms_ual_action_created_idx"),
        ),
    ]

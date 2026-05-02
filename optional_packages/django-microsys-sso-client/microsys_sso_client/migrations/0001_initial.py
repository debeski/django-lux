from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SSOIdentity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("issuer", models.URLField()),
                ("subject", models.CharField(max_length=255)),
                ("role", models.CharField(blank=True, max_length=20)),
                ("claims", models.JSONField(blank=True, default=dict)),
                ("last_login_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sso_identities", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "SSO identity",
                "verbose_name_plural": "SSO identities",
                "unique_together": {("issuer", "subject")},
            },
        ),
    ]


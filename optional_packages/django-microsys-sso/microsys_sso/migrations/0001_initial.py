from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("oauth2_provider", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SSOClientPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(unique=True)),
                ("display_name", models.CharField(max_length=160)),
                ("is_active", models.BooleanField(default=True)),
                ("allow_all_authenticated", models.BooleanField(default=False, help_text="If enabled, any active authenticated provider user receives the 'user' role for this client.")),
                ("require_pkce", models.BooleanField(default=True)),
                ("require_https_redirects", models.BooleanField(default=True)),
                ("allow_localhost_redirects", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("application", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="microsys_sso_policy", to="oauth2_provider.application")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "SSO client policy",
                "verbose_name_plural": "SSO client policies",
            },
        ),
        migrations.CreateModel(
            name="SSOAuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(max_length=80)),
                ("client_id", models.CharField(blank=True, max_length=255)),
                ("role", models.CharField(blank=True, max_length=20)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("policy", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="microsys_sso.ssoclientpolicy")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "SSO audit event",
                "verbose_name_plural": "SSO audit events",
                "ordering": ("-created_at",),
            },
        ),
        migrations.CreateModel(
            name="SSOAdminInvitation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(max_length=254)),
                ("role", models.CharField(choices=[("admin", "Project admin"), ("staff", "Project staff"), ("user", "Project user")], default="admin", max_length=20)),
                ("token_hash", models.CharField(max_length=64)),
                ("expires_at", models.DateTimeField()),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("accepted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("policy", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="admin_invitations", to="microsys_sso.ssoclientpolicy")),
            ],
            options={
                "verbose_name": "SSO admin invitation",
                "verbose_name_plural": "SSO admin invitations",
                "unique_together": {("policy", "email", "token_hash")},
            },
        ),
        migrations.CreateModel(
            name="SSOClientMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("admin", "Project admin"), ("staff", "Project staff"), ("user", "Project user")], default="user", max_length=20)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("policy", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="microsys_sso.ssoclientpolicy")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sso_client_memberships", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "SSO client membership",
                "verbose_name_plural": "SSO client memberships",
                "unique_together": {("policy", "user")},
            },
        ),
        migrations.CreateModel(
            name="SSOSessionState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token_identifier", models.CharField(max_length=255, unique=True)),
                ("role", models.CharField(blank=True, max_length=20)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("policy", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="microsys_sso.ssoclientpolicy")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sso_sessions", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "SSO session",
                "verbose_name_plural": "SSO sessions",
                "ordering": ("-created_at",),
            },
        ),
    ]


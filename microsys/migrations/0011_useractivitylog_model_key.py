from django.db import migrations, models


def backfill_model_key(apps, schema_editor):
    """Best-effort backfill of the locale-independent model_key for legacy rows.

    Historical rows stored only the translated verbose name in ``model_name`` (e.g.
    Arabic), which is locale-dependent. Resolve each distinct label back to its model
    and record the stable ``app_label.model_name`` key so reports can group/resolve
    without depending on the active language. Rows whose label no longer resolves are
    left null and continue to fall back to ``model_name``.
    """
    UserActivityLog = apps.get_model("microsys", "UserActivityLog")
    db_alias = schema_editor.connection.alias

    try:
        from microsys.utils import resolve_model_by_name, _get_fuzzy_model_mapping
    except Exception:
        return

    # Build the fuzzy map fresh so it reflects the current (system-default) language,
    # which is what produced the stored labels in the first place.
    try:
        _get_fuzzy_model_mapping.cache_clear()
    except Exception:
        pass

    distinct_names = (
        UserActivityLog.objects.using(db_alias)
        .filter(model_key__isnull=True)
        .exclude(model_name__isnull=True)
        .exclude(model_name="")
        .values_list("model_name", flat=True)
        .distinct()
    )

    for name in distinct_names:
        try:
            model = resolve_model_by_name(name)
        except Exception:
            model = None
        if model is None:
            continue
        key = model._meta.label_lower
        (
            UserActivityLog.objects.using(db_alias)
            .filter(model_name=name, model_key__isnull=True)
            .update(model_key=key)
        )


def noop_reverse(apps, schema_editor):
    # Field removal handled by the AddField reversal; nothing to undo for the data.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("microsys", "0010_systemsettings_login_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="useractivitylog",
            name="model_key",
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=100,
                null=True,
                verbose_name="Model Key",
            ),
        ),
        migrations.RunPython(backfill_model_key, noop_reverse),
    ]

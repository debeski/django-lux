from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dlux', '0008_dluximageupdate'),
    ]

    operations = [
        migrations.AddField(
            model_name='scope',
            name='description',
            field=models.TextField(blank=True, null=True, verbose_name='Description'),
        ),
        migrations.AddField(
            model_name='scope',
            name='is_public_registration_default',
            field=models.BooleanField(db_default=False, default=False, verbose_name='Default for Public Registration'),
        ),
        migrations.AddField(
            model_name='groupprofile',
            name='is_public_registration_default',
            field=models.BooleanField(db_default=False, default=False, verbose_name='Default for Public Registration'),
        ),
    ]

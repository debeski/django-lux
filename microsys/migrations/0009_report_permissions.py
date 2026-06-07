from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('microsys', '0008_user_device_presence_history'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='profile',
            options={
                'default_permissions': (),
                'permissions': [
                    ('manage_staff', 'Can manage staff'),
                    ('manage_scopes', 'Can manage scopes and all users'),
                    ('view_reports', 'Can view reports'),
                    ('download_backup', 'Can download backup'),
                ],
                'verbose_name': 'Profile',
                'verbose_name_plural': 'Profiles',
            },
        ),
    ]

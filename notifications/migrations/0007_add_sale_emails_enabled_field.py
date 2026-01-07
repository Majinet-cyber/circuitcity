# Generated migration to add sale_emails_enabled field

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0006_add_commission_and_weekly_digest_preferences"),
    ]

    operations = [
        migrations.AddField(
            model_name="notificationpreference",
            name="sale_emails_enabled",
            field=models.BooleanField(
                default=True,
                help_text="Receive sale completion emails (for managers: True, for agents: False by default)",
            ),
        ),
    ]

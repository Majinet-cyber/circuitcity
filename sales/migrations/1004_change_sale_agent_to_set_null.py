# Generated migration to change Sale.agent from PROTECT to SET_NULL
# This allows safe deletion of users while preserving sales history

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "1003_add_commission_reversal_tracking"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="sale",
            name="agent",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=models.SET_NULL,
                related_name="sales",
                to=settings.AUTH_USER_MODEL,
                help_text="Agent who made the sale (null if agent deleted)",
            ),
        ),
    ]

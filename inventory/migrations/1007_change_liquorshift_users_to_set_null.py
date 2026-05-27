# Generated migration to change LiquorShift user FKs from PROTECT to SET_NULL
# This allows safe deletion of users while preserving shift history

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "1006_fix_null_spec_label_values"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="liquorshift",
            name="barman",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=models.SET_NULL,
                related_name="liquor_shifts_worked",
                to=settings.AUTH_USER_MODEL,
                help_text="Barman working this shift (null if user deleted)",
            ),
        ),
        migrations.AlterField(
            model_name="liquorshift",
            name="created_by",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=models.SET_NULL,
                related_name="liquor_shifts_created",
                to=settings.AUTH_USER_MODEL,
                help_text="User who created this shift (null if user deleted)",
            ),
        ),
    ]

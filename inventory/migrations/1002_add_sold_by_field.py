# Generated migration for sold_by field
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inventory', '1001_alter_merchproduct_kind_delete_alert'),
    ]

    operations = [
        migrations.AddField(
            model_name='inventoryitem',
            name='sold_by',
            field=models.ForeignKey(
                blank=True,
                help_text='Agent/user who sold this item (for commission attribution)',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='items_sold',
                to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.AddIndex(
            model_name='inventoryitem',
            index=models.Index(fields=['sold_by', 'sold_at'], name='inv_sold_by_at_idx'),
        ),
    ]


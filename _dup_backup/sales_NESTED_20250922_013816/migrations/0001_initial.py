# sales/migrations/0001_initial.py
from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

class Migration(migrations.Migration):
    initial = True

    dependencies = [
        # Use your latest inventory migration filename (without .py):
        ('inventory', '0011_remove_inventoryitem_inventory_i_status_214241_idx_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Sale',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sold_at', models.DateField()),
                ('price', models.DecimalField(decimal_places=2, max_digits=12, validators=[MinValueValidator(0)])),
                ('commission_pct', models.DecimalField(decimal_places=2, default=0, max_digits=5, validators=[MinValueValidator(0), MaxValueValidator(100)])),
                ('created_at', models.DateTimeField(default=timezone.now, db_index=True, editable=False)),
                ('agent', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='sales', to=settings.AUTH_USER_MODEL)),
                ('location', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='inventory.location')),
                ('item', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='sale', to='inventory.inventoryitem')),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['created_at'], name='sale_created_at_idx'),
                    models.Index(fields=['sold_at'], name='sale_sold_at_idx'),
                    models.Index(fields=['location', 'created_at'], name='sale_loc_created_idx'),
                    models.Index(fields=['agent', 'created_at'], name='sale_agent_created_idx'),
                ],
                'constraints': [
                    models.CheckConstraint(check=models.Q(('price__gte', 0)), name='sale_price_nonneg'),
                    models.CheckConstraint(
                        check=(models.Q(('commission_pct__gte', 0)) & models.Q(('commission_pct__lte', 100))),
                        name='sale_commission_pct_0_100'
                    ),
                ],
            },
        ),
    ]

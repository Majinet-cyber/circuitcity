# Generated migration for Car Hire Trip driver field
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inventory', '1025_car_hire_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='trip',
            name='driver',
            field=models.ForeignKey(
                blank=True,
                help_text='Driver/agent assigned to this trip',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='car_hire_trips_driven',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]















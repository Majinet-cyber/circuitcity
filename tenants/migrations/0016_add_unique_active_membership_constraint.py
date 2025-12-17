# Manual migration to add unique constraint for active memberships
# Created: 2025-12-17

from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0015_alter_business_business_kind"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="membership",
            constraint=models.UniqueConstraint(
                fields=["user", "business"],
                condition=Q(status="ACTIVE"),
                name="uniq_active_membership_user_business",
            ),
        ),
    ]


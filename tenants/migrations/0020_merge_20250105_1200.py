# Generated manually to merge parallel migration branches in tenants

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0019a_fix_cement_business_kind"),
    ]

    operations = [
        # This is a merge migration with no operations
    ]

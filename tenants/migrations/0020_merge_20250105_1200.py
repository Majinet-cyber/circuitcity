# Generated manually to merge parallel migration branches in tenants

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0019_add_section_flags_with_defaults"),
        ("tenants", "0019_fix_cement_business_kind"),
    ]

    operations = [
        # This is a merge migration with no operations
    ]

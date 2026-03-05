# Generated manually to merge parallel migration branches in tenants

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0019a_fix_cement_business_kind"),
        ("tenants", "0019_add_section_flags_with_defaults"),
    ]

    operations = []

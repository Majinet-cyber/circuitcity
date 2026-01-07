# Generated migration to fix cement businesses with NULL business_kind

from django.db import migrations, models


def fix_cement_businesses(apps, schema_editor):
    """
    Fix businesses where business_kind is NULL but they should be 'cement'.

    Criteria:
    - business_kind is NULL or empty
    - has_cement_section is True
    OR
    - business name contains 'cement' or 'hardware'
    """
    Business = apps.get_model("tenants", "Business")

    # Fix businesses with has_cement_section=True but no business_kind
    cement_flagged = Business.objects.filter(has_cement_section=True).filter(
        models.Q(business_kind__isnull=True) | models.Q(business_kind="")
    )

    count = cement_flagged.update(business_kind="cement")
    if count > 0:
        print(f"Fixed {count} cement businesses (had has_cement_section=True)")

    # Also fix businesses with 'cement' or 'hardware' in name
    cement_named = Business.objects.filter(
        models.Q(name__icontains="cement") | models.Q(name__icontains="hardware")
    ).filter(models.Q(business_kind__isnull=True) | models.Q(business_kind=""))

    count2 = cement_named.update(business_kind="cement", has_cement_section=True)
    if count2 > 0:
        print(f"Fixed {count2} cement businesses (name contains cement/hardware)")


def reverse_fix(apps, schema_editor):
    """
    Reverse migration - set business_kind back to NULL for cement businesses.
    (Not recommended - this would break their dashboard access)
    """
    # We don't actually want to reverse this fix
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0018_add_cement_grocery_sales_and_costs"),
    ]

    operations = [
        migrations.RunPython(fix_cement_businesses, reverse_fix),
    ]

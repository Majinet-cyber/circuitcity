# Generated migration to fix NULL spec_label values
# This migration ensures all existing MerchProduct rows have spec_label set to "" if NULL

from django.db import migrations


def fix_null_spec_labels(apps, schema_editor):
    """
    Fix all existing MerchProduct rows where spec_label is NULL.
    For clothing products, use size if available, otherwise empty string.
    For all other products, use empty string.
    """
    MerchProduct = apps.get_model("inventory", "MerchProduct")

    # Fix all NULL spec_label values
    # For clothing: use size if available, otherwise empty string
    clothing_products = MerchProduct.objects.filter(kind="clothing", spec_label__isnull=True)

    for product in clothing_products:
        # Use size if available, format as "Size X" if it doesn't already start with "Size "
        if product.size:
            spec_value = product.size
            if not spec_value.startswith("Size "):
                spec_value = f"Size {spec_value}"
            product.spec_label = spec_value
        else:
            product.spec_label = ""
        product.save(update_fields=["spec_label"])

    # For all other products: set to empty string
    other_products = MerchProduct.objects.filter(spec_label__isnull=True)

    for product in other_products:
        product.spec_label = ""
        product.save(update_fields=["spec_label"])


def reverse_fix(apps, schema_editor):
    """
    Reverse migration - no-op since we're just fixing data
    """
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "1005_add_inventory_barcode_and_laptop_models"),
    ]

    operations = [
        migrations.RunPython(fix_null_spec_labels, reverse_fix),
    ]

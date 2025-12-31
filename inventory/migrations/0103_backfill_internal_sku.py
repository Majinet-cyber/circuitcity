# Generated migration to backfill internal_sku for any existing products
from django.db import migrations
from django.db.models import Q


def backfill_internal_sku(apps, schema_editor):
    """
    Backfill internal_sku for any products that don't have one.
    This ensures all products have a valid SKU before we enforce NOT NULL.
    """
    MerchProduct = apps.get_model('inventory', 'MerchProduct')
    
    # Find products with empty or NULL internal_sku
    products_needing_sku = MerchProduct.objects.filter(
        Q(internal_sku='') | Q(internal_sku__isnull=True)
    )
    
    if not products_needing_sku.exists():
        return  # Nothing to backfill
    
    # Import the generator
    from inventory.utils_sku import generate_sku
    
    # Generate SKU for each product
    for product in products_needing_sku:
        product.internal_sku = generate_sku(
            business_id=product.business_id,
            name=product.name
        )
    
    # Bulk update for efficiency
    MerchProduct.objects.bulk_update(products_needing_sku, ['internal_sku'])


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0102_add_category_group'),
    ]

    operations = [
        migrations.RunPython(backfill_internal_sku, reverse_code=migrations.RunPython.noop),
    ]


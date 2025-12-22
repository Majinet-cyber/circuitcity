# Generated migration for gym member barcode feature

from django.db import migrations, models
import random


def generate_unique_code(business_id, existing_codes):
    """Generate a unique member code for a given business"""
    for _ in range(20):
        code = f"GYM-{random.randint(100000, 999999)}"
        key = f"{business_id}:{code}"
        if key not in existing_codes:
            existing_codes.add(key)
            return code
    # Ultra-rare fallback
    import uuid
    code = f"GYM-{uuid.uuid4().hex[:6].upper()}"
    existing_codes.add(f"{business_id}:{code}")
    return code


def backfill_member_codes(apps, schema_editor):
    """Generate unique member codes for all existing gym members"""
    GymMember = apps.get_model("inventory", "GymMember")
    
    # Track existing codes to avoid collisions
    existing_codes = set()
    
    # Get all members without member_code
    members_to_update = []
    for member in GymMember.objects.filter(models.Q(member_code='') | models.Q(member_code__isnull=True)):
        member.member_code = generate_unique_code(member.business_id, existing_codes)
        members_to_update.append(member)
    
    # Bulk update all members
    if members_to_update:
        GymMember.objects.bulk_update(members_to_update, ['member_code'], batch_size=500)


def reverse_backfill(apps, schema_editor):
    """Reverse operation - clear member codes"""
    GymMember = apps.get_model("inventory", "GymMember")
    GymMember.objects.all().update(member_code='')


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0056_add_accessories_models'),
    ]

    operations = [
        # Step 1: Add field without unique constraint
        migrations.AddField(
            model_name='gymmember',
            name='member_code',
            field=models.CharField(
                blank=True,
                db_index=True,
                default='',
                help_text='Unique barcode/QR code for member scanning (auto-generated)',
                max_length=20
            ),
        ),
        
        # Step 2: Backfill existing members with unique codes
        migrations.RunPython(backfill_member_codes, reverse_backfill),
        
        # Step 3: Add unique constraint
        migrations.AlterUniqueTogether(
            name='gymmember',
            unique_together={('business', 'phone'), ('business', 'member_code')},
        ),
        
        # Step 4: Add index
        migrations.AddIndex(
            model_name='gymmember',
            index=models.Index(fields=['member_code'], name='inventory_g_member__a3a770_idx'),
        ),
    ]


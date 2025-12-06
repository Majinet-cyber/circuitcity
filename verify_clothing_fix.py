#!/usr/bin/env python
"""
Verification script for the clothing dashboard size field fix.

This script verifies that migration 0045 has been applied correctly
and that the clothing dashboard will work without errors.

Run this after applying the migration:
    python manage.py migrate inventory
    python verify_clothing_fix.py
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'circuitcity.settings')
django.setup()

from django.db import connection
from inventory.models import MerchProduct
from inventory.business_kinds import BusinessKind


def check_migration_status():
    """Check if migration 0045 has been applied"""
    print("=" * 60)
    print("CHECKING MIGRATION STATUS")
    print("=" * 60)
    
    from django.db.migrations.recorder import MigrationRecorder
    recorder = MigrationRecorder(connection)
    applied = recorder.applied_migrations()
    
    target_migration = ('inventory', '0045_clothing_cost_tracking')
    
    if target_migration in applied:
        print("✅ Migration 0045_clothing_cost_tracking is APPLIED")
        return True
    else:
        print("❌ Migration 0045_clothing_cost_tracking is NOT APPLIED")
        print("\n⚠️  You must run: python manage.py migrate inventory")
        return False


def check_database_schema():
    """Check if the size field exists in the database"""
    print("\n" + "=" * 60)
    print("CHECKING DATABASE SCHEMA")
    print("=" * 60)
    
    with connection.cursor() as cursor:
        # Get column names for inventory_merchproduct table
        cursor.execute("PRAGMA table_info(inventory_merchproduct);")
        columns = [row[1] for row in cursor.fetchall()]
        
        required_fields = ['size', 'color', 'quantity_in_stock', 'cost_price', 'selling_price']
        all_present = True
        
        for field in required_fields:
            if field in columns:
                print(f"✅ Column '{field}' exists in database")
            else:
                print(f"❌ Column '{field}' MISSING from database")
                all_present = False
        
        return all_present


def test_merch_product_creation():
    """Test creating a MerchProduct with size field"""
    print("\n" + "=" * 60)
    print("TESTING MERCHPRODUCT CREATION")
    print("=" * 60)
    
    try:
        # Try to create a test product (don't save to avoid needing a business)
        product = MerchProduct(
            name='Test Clothing Item',
            kind=BusinessKind.CLOTHING,
            size='L',
            color='Blue',
            quantity_in_stock=10,
        )
        
        # Check if the field exists
        if hasattr(product, 'size'):
            print(f"✅ MerchProduct.size field exists in model")
            print(f"   Test value: {product.size}")
        else:
            print("❌ MerchProduct.size field MISSING from model")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Error creating MerchProduct: {e}")
        return False


def test_query_with_size():
    """Test querying MerchProduct (simulates the dashboard query)"""
    print("\n" + "=" * 60)
    print("TESTING DATABASE QUERY")
    print("=" * 60)
    
    try:
        # This is similar to the query that was failing in clothing.py line 31
        # We'll try to query and order by -id (which triggers field resolution)
        qs = MerchProduct.objects.filter(kind=BusinessKind.CLOTHING)
        # Force query execution by converting to list (limit to avoid large datasets)
        recent = list(qs.order_by("-id")[:6])
        
        print(f"✅ Query executed successfully")
        print(f"   Found {len(recent)} clothing products")
        
        if recent:
            sample = recent[0]
            print(f"   Sample product: {sample.name}")
            print(f"   Size: {sample.size or '(not set)'}")
            print(f"   Color: {sample.color or '(not set)'}")
        
        return True
        
    except Exception as e:
        print(f"❌ Query failed with error:")
        print(f"   {type(e).__name__}: {e}")
        print("\n⚠️  This is the exact error that was occurring on the dashboard!")
        print("   You need to run: python manage.py migrate inventory")
        return False


def main():
    print("\n" + "=" * 60)
    print("CLOTHING DASHBOARD FIX VERIFICATION")
    print("=" * 60)
    print("\nThis script verifies the fix for:")
    print("django.db.utils.OperationalError: no such column: inventory_merchproduct.size")
    print("")
    
    # Run all checks
    migration_ok = check_migration_status()
    schema_ok = check_database_schema()
    model_ok = test_merch_product_creation()
    query_ok = test_query_with_size()
    
    # Final summary
    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    
    all_ok = migration_ok and schema_ok and model_ok and query_ok
    
    if all_ok:
        print("✅ ALL CHECKS PASSED!")
        print("\nThe clothing dashboard should now work correctly.")
        print("You can test it by visiting: /verticals/clothing/dashboard/")
        return 0
    else:
        print("❌ SOME CHECKS FAILED")
        print("\nPlease run the following command to fix:")
        print("    python manage.py migrate inventory")
        print("\nThen run this verification script again.")
        return 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)


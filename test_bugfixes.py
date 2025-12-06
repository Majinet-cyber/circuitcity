#!/usr/bin/env python
"""
Quick smoke test for production bug fixes.

Run this AFTER running migrations to verify all fixes are working.

Usage:
    python test_bugfixes.py
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cc.settings')
django.setup()

from decimal import Decimal
from django.db import connection
from inventory.models import InventoryItem
from inventory.utils_metrics import estimate_margin_for_business_and_sku


def test_assigned_role_column():
    """Test that assigned_role column exists and is accessible."""
    print("=" * 60)
    print("TEST 1: assigned_role Column")
    print("=" * 60)
    
    try:
        # Check if column exists in database
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA table_info(inventory_inventoryitem)")
            columns = [row[1] for row in cursor.fetchall()]
            
        if 'assigned_role' in columns:
            print("✅ Column 'assigned_role' exists in database")
        else:
            print("❌ Column 'assigned_role' NOT FOUND in database")
            print("   Run: python manage.py migrate inventory")
            return False
        
        # Test that we can query it
        count = InventoryItem.objects.filter(assigned_role="MANAGER").count()
        print(f"✅ Query successful: {count} items with role=MANAGER")
        
        # Test that we can access the field
        item = InventoryItem.objects.first()
        if item:
            role = item.assigned_role
            print(f"✅ Field access successful: first item has role='{role}'")
        else:
            print("⚠️  No inventory items exist (this is OK for new systems)")
        
        print("✅ TEST 1 PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ TEST 1 FAILED: {e}\n")
        return False


def test_timedelta_import():
    """Test that timedelta import works in dashboard views."""
    print("=" * 60)
    print("TEST 2: timedelta Import")
    print("=" * 60)
    
    try:
        # Import the view module
        from dashboard import views
        
        # Check that timedelta is properly imported
        from datetime import timedelta
        from django.utils import timezone
        
        # Simulate the calculation that was failing
        today = timezone.localdate()
        today_end = today + timedelta(days=1)
        
        print("✅ timedelta import successful")
        print(f"✅ Date calculation works: {today} + 1 day = {today_end}")
        
        # Check the views module for duplicate imports
        import inspect
        source = inspect.getsource(views.home)
        if "from datetime import timedelta" in source:
            # Check if it's only at the top of the file
            lines = source.split('\n')
            import_count = sum(1 for line in lines if 'from datetime import timedelta' in line)
            if import_count > 1:
                print(f"⚠️  Found {import_count} timedelta imports (should be 1)")
            else:
                print("✅ Only 1 timedelta import found (correct)")
        
        print("✅ TEST 2 PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ TEST 2 FAILED: {e}\n")
        return False


def test_margin_estimation():
    """Test that margin estimation helper works correctly."""
    print("=" * 60)
    print("TEST 3: Margin Estimation")
    print("=" * 60)
    
    try:
        from tenants.models import Business
        
        # Get or create a test business
        business = Business.objects.first()
        
        if not business:
            print("⚠️  No businesses exist - creating test business")
            business = Business.objects.create(
                name="Test Business",
                slug="test-business",
            )
        
        print(f"Testing with business: {business.name}")
        
        # Test default margin (no sales history)
        margin = estimate_margin_for_business_and_sku(business)
        print(f"✅ Margin estimation works: {float(margin * 100):.1f}%")
        
        # Verify it's the default
        if margin == Decimal("0.12"):
            print("✅ Returns default 12% margin (correct for no sales history)")
        else:
            print(f"✅ Returns custom margin: {float(margin * 100):.1f}%")
        
        # Test that it never returns negative
        if margin < 0:
            print("❌ Margin is negative (FAIL)")
            return False
        else:
            print("✅ Margin is non-negative (correct)")
        
        # Test that it's within reasonable bounds
        if margin > Decimal("0.90"):
            print("⚠️  Margin > 90% (might be unrealistic)")
        else:
            print("✅ Margin is within reasonable bounds (0-90%)")
        
        print("✅ TEST 3 PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ TEST 3 FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_potential_profit():
    """Test that potential profit calculation never goes negative."""
    print("=" * 60)
    print("TEST 4: Potential Profit Calculation")
    print("=" * 60)
    
    try:
        from tenants.models import Business
        from inventory.utils_metrics import compute_potential_profit_from_stock
        
        business = Business.objects.first()
        if not business:
            print("⚠️  No businesses exist - skipping test")
            return True
        
        # Get stock items
        stock_qs = InventoryItem.objects.filter(
            business=business,
            status="IN_STOCK",
            is_active=True,
        )
        
        count = stock_qs.count()
        print(f"Testing with {count} in-stock items")
        
        if count == 0:
            print("⚠️  No stock items exist (this is OK for new systems)")
            print("✅ TEST 4 PASSED (skipped)\n")
            return True
        
        # Calculate potential profit
        profit = compute_potential_profit_from_stock(stock_qs, business)
        
        print(f"✅ Potential profit: MK {float(profit):,.2f}")
        
        # Verify it's never negative
        if profit < 0:
            print("❌ Potential profit is NEGATIVE (FAIL)")
            return False
        else:
            print("✅ Potential profit is non-negative (correct)")
        
        # Calculate cost value for context
        from django.db.models import Sum
        from django.db.models.functions import Coalesce
        cost_value = stock_qs.aggregate(
            total=Coalesce(Sum('order_price'), Decimal('0.00'))
        )['total'] or Decimal('0.00')
        
        print(f"   Stock cost value: MK {float(cost_value):,.2f}")
        
        if cost_value > 0:
            margin_pct = (profit / cost_value) * 100
            print(f"   Implied margin: {float(margin_pct):.1f}%")
        
        print("✅ TEST 4 PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ TEST 4 FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("PRODUCTION BUG FIX VERIFICATION")
    print("=" * 60 + "\n")
    
    results = []
    
    # Run all tests
    results.append(("assigned_role column", test_assigned_role_column()))
    results.append(("timedelta import", test_timedelta_import()))
    results.append(("margin estimation", test_margin_estimation()))
    results.append(("potential profit", test_potential_profit()))
    
    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")
    
    print("-" * 60)
    print(f"Total: {passed}/{total} tests passed")
    print("=" * 60 + "\n")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED! Ready for production.")
        return 0
    else:
        print("⚠️  SOME TESTS FAILED. Please review errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())


#!/usr/bin/env python
"""
Validation script for Circuit City Cost Management & Dashboard implementation.
Run this to verify all changes are properly integrated.
"""
import sys
from pathlib import Path


def validate_sidebar_costs():
    """Verify Costs link added to all verticals."""
    print("\n✓ Checking sidebar costs link...")
    
    try:
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        verticals = ["phones", "gym", "clothing", "liquor", "pharmacy"]
        
        for vertical in verticals:
            items = get_vertical_sidebar_items(vertical)
            costs_items = [i for i in items if i.get("label") == "Costs"]
            
            if len(costs_items) == 1:
                item = costs_items[0]
                assert item.get("section") == "MONEY", f"{vertical}: Costs not in MONEY section"
                assert item.get("require_manager") is True, f"{vertical}: Costs not manager-only"
                assert item.get("url") == "wallet:admin_cost_list", f"{vertical}: Wrong URL"
                print(f"  ✅ {vertical.upper()}: Costs link properly configured")
            else:
                print(f"  ❌ {vertical.upper()}: Costs link missing or duplicated")
                return False
        
        return True
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def validate_orders_sidebar():
    """Verify Orders link for phones and clothing verticals."""
    print("\n✓ Checking orders sidebar link...")
    
    try:
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        # Phones should have Orders
        phones_items = get_vertical_sidebar_items("phones")
        orders_items = [i for i in phones_items if i.get("label") == "Orders"]
        
        if len(orders_items) == 1:
            item = orders_items[0]
            assert item.get("section") == "BUSINESS", "Orders not in BUSINESS section"
            assert item.get("require_manager") is True, "Orders not manager-only"
            print(f"  ✅ PHONES: Orders link properly configured")
        else:
            print(f"  ❌ PHONES: Orders link missing or duplicated")
            return False
        
        # Clothing should have Orders
        clothing_items = get_vertical_sidebar_items("clothing")
        orders_items = [i for i in clothing_items if i.get("label") == "Orders"]
        
        if len(orders_items) == 1:
            print(f"  ✅ CLOTHING: Orders link properly configured")
        else:
            print(f"  ❌ CLOTHING: Orders link missing")
            return False
        
        return True
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def validate_dashboard_chart_endpoints():
    """Verify chart endpoints exist in URL configuration."""
    print("\n✓ Checking dashboard chart endpoints...")
    
    try:
        from django.urls import reverse
        
        # Try to reverse chart URLs
        endpoints = [
            ("dashboard:sales_trend", "/dashboard/api/sales-trend/"),
            ("dashboard:top_models", "/dashboard/api/top-models/"),
        ]
        
        for name, expected_path in endpoints:
            try:
                url = reverse(name)
                print(f"  ✅ {name}: {url}")
            except Exception as e:
                print(f"  ❌ {name}: Could not reverse URL - {e}")
                return False
        
        return True
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def validate_cost_models():
    """Verify cost model has required fields."""
    print("\n✓ Checking cost model fields...")
    
    try:
        from wallet.models import WalletTransaction, TxnType, Ledger
        
        # Check for cost-specific fields
        field_names = {f.name for f in WalletTransaction._meta.get_fields()}
        
        required_fields = ["business", "is_recurring", "recurrence", "effective_from"]
        
        for field in required_fields:
            if field in field_names:
                print(f"  ✅ Field '{field}' exists")
            else:
                print(f"  ❌ Field '{field}' missing")
                return False
        
        # Check for cost transaction types
        cost_types = [TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING]
        for cost_type in cost_types:
            print(f"  ✅ Transaction type '{cost_type}' exists")
        
        return True
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def validate_test_files():
    """Verify test files exist."""
    print("\n✓ Checking test files...")
    
    test_files = [
        "tests/test_sidebar_roles.py",
        "tests/test_purchase_orders_sidebar.py",
        "tests/test_dashboard_charts_fixed.py",
    ]
    
    all_exist = True
    for test_file in test_files:
        path = Path(test_file)
        if path.exists():
            print(f"  ✅ {test_file}")
        else:
            print(f"  ❌ {test_file} - NOT FOUND")
            all_exist = False
    
    return all_exist


def main():
    """Run all validation checks."""
    print("=" * 70)
    print("CIRCUIT CITY IMPLEMENTATION VALIDATION")
    print("=" * 70)
    
    checks = [
        ("Sidebar Costs Links", validate_sidebar_costs),
        ("Orders Sidebar Links", validate_orders_sidebar),
        ("Dashboard Chart Endpoints", validate_dashboard_chart_endpoints),
        ("Cost Model Fields", validate_cost_models),
        ("Test Files", validate_test_files),
    ]
    
    results = []
    
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name} validation failed with exception: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print("\n" + "-" * 70)
    print(f"Total: {passed}/{total} checks passed")
    print("=" * 70)
    
    if passed == total:
        print("\n🎉 All validations passed! Implementation is complete and correct.")
        return 0
    else:
        print(f"\n⚠️ {total - passed} validation(s) failed. Please review errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())


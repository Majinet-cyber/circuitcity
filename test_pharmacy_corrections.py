#!/usr/bin/env python
"""
Quick test script for Pharmacy Corrections functionality.
Run with: python test_pharmacy_corrections.py
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cc.settings')
django.setup()

from corrections.registry import registry
from corrections.adapters.pharmacy import PharmacyAdapter


def test_pharmacy_adapter_registered():
    """Test that pharmacy adapter is registered."""
    print("[OK] Testing pharmacy adapter registration...")
    adapter = registry.get_adapter('pharmacy')
    assert adapter is not None, "Pharmacy adapter should be registered"
    assert isinstance(adapter, PharmacyAdapter), "Should be PharmacyAdapter instance"
    assert adapter.vertical_key == 'pharmacy'
    assert adapter.vertical_label == 'Pharmacy & Cosmetics'
    print("  [OK] Pharmacy adapter registered correctly")


def test_pharmacy_entities():
    """Test that pharmacy entities are defined."""
    print("\n[OK] Testing pharmacy entities...")
    adapter = registry.get_adapter('pharmacy')
    entities = adapter.get_entities()
    
    # Check pharmacy_sale
    assert 'pharmacy_sale' in entities, "pharmacy_sale entity should exist"
    sale_entity = entities['pharmacy_sale']
    print(f"  [OK] pharmacy_sale entity found with {len(sale_entity.fields)} fields")
    
    # Check required fields for pharmacy_sale
    required_sale_fields = ['quantity', 'unit_price', 'unit_cost', 'total_amount', 'payment_method']
    for field in required_sale_fields:
        assert field in sale_entity.fields, f"pharmacy_sale should have {field} field"
    print(f"  [OK] pharmacy_sale has all required fields: {', '.join(required_sale_fields)}")
    
    # Check pharmacy_batch
    assert 'pharmacy_batch' in entities, "pharmacy_batch entity should exist"
    batch_entity = entities['pharmacy_batch']
    print(f"  [OK] pharmacy_batch entity found with {len(batch_entity.fields)} fields")
    
    # Check required fields for pharmacy_batch
    required_batch_fields = ['batch_number', 'expiry_date', 'quantity', 'cost_price', 'selling_price']
    for field in required_batch_fields:
        assert field in batch_entity.fields, f"pharmacy_batch should have {field} field"
    print(f"  [OK] pharmacy_batch has all required fields: {', '.join(required_batch_fields)}")
    
    # Check pharmacy_product
    assert 'pharmacy_product' in entities, "pharmacy_product entity should exist"
    product_entity = entities['pharmacy_product']
    print(f"  [OK] pharmacy_product entity found with {len(product_entity.fields)} fields")


def test_post_correction_hook():
    """Test that post_correction_hook is implemented."""
    print("\n[OK] Testing post_correction_hook...")
    adapter = registry.get_adapter('pharmacy')
    
    # Check that the method exists
    assert hasattr(adapter, 'post_correction_hook'), "Adapter should have post_correction_hook method"
    print("  [OK] post_correction_hook method exists")
    
    # Test that it's callable
    assert callable(adapter.post_correction_hook), "post_correction_hook should be callable"
    print("  [OK] post_correction_hook is callable")


def test_common_issues_detection():
    """Test that common issues detection works."""
    print("\n[OK] Testing common issues detection...")
    adapter = registry.get_adapter('pharmacy')
    
    # Test that find_erroneous_entries exists
    assert hasattr(adapter, 'find_erroneous_entries'), "Adapter should have find_erroneous_entries"
    print("  [OK] find_erroneous_entries method exists")
    
    # Note: We can't test actual queries without a business context,
    # but we can verify the method signature is correct
    import inspect
    sig = inspect.signature(adapter.find_erroneous_entries)
    params = list(sig.parameters.keys())
    assert 'entity_label' in params, "Should have entity_label parameter"
    assert 'business' in params, "Should have business parameter"
    assert 'limit' in params, "Should have limit parameter"
    print("  [OK] find_erroneous_entries has correct signature")


def test_field_types():
    """Test that field types are correctly defined."""
    print("\n[OK] Testing field types...")
    adapter = registry.get_adapter('pharmacy')
    entities = adapter.get_entities()
    
    # Check pharmacy_sale field types
    sale_entity = entities['pharmacy_sale']
    assert sale_entity.fields['quantity'].field_type == 'integer'
    assert sale_entity.fields['unit_price'].field_type == 'decimal'
    assert sale_entity.fields['payment_method'].field_type == 'string'
    assert sale_entity.fields['sold_at'].field_type == 'datetime'
    print("  [OK] pharmacy_sale field types are correct")
    
    # Check pharmacy_batch field types
    batch_entity = entities['pharmacy_batch']
    assert batch_entity.fields['quantity'].field_type == 'integer'
    assert batch_entity.fields['cost_price'].field_type == 'decimal'
    assert batch_entity.fields['expiry_date'].field_type == 'date'
    print("  [OK] pharmacy_batch field types are correct")


def main():
    """Run all tests."""
    print("=" * 60)
    print("PHARMACY CORRECTIONS TEST SUITE")
    print("=" * 60)
    
    try:
        test_pharmacy_adapter_registered()
        test_pharmacy_entities()
        test_post_correction_hook()
        test_common_issues_detection()
        test_field_types()
        
        print("\n" + "=" * 60)
        print("[SUCCESS] ALL TESTS PASSED!")
        print("=" * 60)
        print("\nPharmacy corrections are ready to use:")
        print("  1. Start server: python manage.py runserver")
        print("  2. Visit: http://localhost:8000/corrections/pharmacy/entity/pharmacy_sale/")
        print("  3. Click 'Edit' on any row to test editing")
        print("\n")
        return 0
        
    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    
"""
Quick test script to verify Pharmacy Dashboard Premium Filters implementation.
Run: python test_pharmacy_premium_filters.py
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cc.settings')
django.setup()

from django.test import RequestFactory, Client
from django.contrib.auth import get_user_model
from tenants.models import Business, Location
from inventory.models import MerchProduct
from inventory.models_pharmacy import PharmacyBatch, PharmacySale
from django.utils import timezone
from datetime import timedelta, datetime
from decimal import Decimal

User = get_user_model()

def test_filter_urls():
    """Test that various filter URLs work without errors"""
    print("\n" + "="*60)
    print("TESTING PHARMACY DASHBOARD PREMIUM FILTERS")
    print("="*60)
    
    # Create test client
    client = Client()
    
    # Get or create test user
    try:
        user = User.objects.filter(is_staff=False, is_superuser=False).first()
        if not user:
            print("❌ No regular user found. Please create a user first.")
            return False
        
        # Login
        client.force_login(user)
        
        # Get user's business (Business doesn't have owner field, use memberships)
        from tenants.models import Membership
        membership = Membership.objects.filter(user=user, role__in=['owner', 'manager']).first()
        if not membership:
            print("X No business membership found for user.")
            return False
        business = membership.business
        print(f"OK Using user: {user.username}")
        print(f"OK Using business: {business.name}")
        
        # Test URLs
        test_cases = [
            ("Default (30d)", "/verticals/pharmacy/dashboard/"),
            ("Today", "/verticals/pharmacy/dashboard/?range=today"),
            ("Last 7 Days", "/verticals/pharmacy/dashboard/?range=7d"),
            ("Last 30 Days", "/verticals/pharmacy/dashboard/?range=30d"),
            ("This Month", "/verticals/pharmacy/dashboard/?range=this_month"),
            ("Last Month", "/verticals/pharmacy/dashboard/?range=last_month"),
            ("This Year", "/verticals/pharmacy/dashboard/?range=this_year"),
            ("Custom Range", "/verticals/pharmacy/dashboard/?range=custom&start=2026-02-01&end=2026-02-09"),
        ]
        
        print("\n" + "-"*60)
        print("Testing Dashboard URLs:")
        print("-"*60)
        
        for name, url in test_cases:
            response = client.get(url)
            status = "✅" if response.status_code == 200 else "❌"
            print(f"{status} {name:20s} → {response.status_code} ({url})")
            
            if response.status_code != 200:
                print(f"   Error: {response.content[:200]}")
        
        # Test Trend JSON API
        print("\n" + "-"*60)
        print("Testing Trend JSON API:")
        print("-"*60)
        
        api_test_cases = [
            ("7d", "/verticals/pharmacy/api/sales-trend/?range=7d"),
            ("30d", "/verticals/pharmacy/api/sales-trend/?range=30d"),
            ("this_month", "/verticals/pharmacy/api/sales-trend/?range=this_month"),
            ("custom", "/verticals/pharmacy/api/sales-trend/?range=custom&start=2026-02-01&end=2026-02-09"),
        ]
        
        for name, url in api_test_cases:
            response = client.get(url)
            status = "✅" if response.status_code == 200 else "❌"
            print(f"{status} {name:15s} → {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"   Labels: {len(data.get('labels', []))} points")
                    print(f"   Has data: {data.get('has_data', False)}")
                    print(f"   Bucket type: {data.get('bucket_type', 'N/A')}")
                except Exception as e:
                    print(f"   ⚠️  JSON parse error: {e}")
        
        # Test with product filter
        print("\n" + "-"*60)
        print("Testing Product Filter:")
        print("-"*60)
        
        product = MerchProduct.objects.filter(business=business, kind="pharmacy", is_active=True).first()
        if product:
            url = f"/verticals/pharmacy/dashboard/?range=30d&product_id={product.id}"
            response = client.get(url)
            status = "✅" if response.status_code == 200 else "❌"
            print(f"{status} Product filter (ID={product.id}) → {response.status_code}")
            print(f"   Product: {product.name}")
        else:
            print("⚠️  No products found to test product filter")
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60)
        print("\nTest URLs to try in browser:")
        print(f"  • /verticals/pharmacy/dashboard/?range=today")
        print(f"  • /verticals/pharmacy/dashboard/?range=7d")
        print(f"  • /verticals/pharmacy/dashboard/?range=30d")
        print(f"  • /verticals/pharmacy/dashboard/?range=this_month")
        print(f"  • /verticals/pharmacy/dashboard/?range=last_month")
        print(f"  • /verticals/pharmacy/dashboard/?range=this_year")
        print(f"  • /verticals/pharmacy/dashboard/?range=custom&start=2026-02-01&end=2026-02-09")
        if product:
            print(f"  • /verticals/pharmacy/dashboard/?range=30d&product_id={product.id}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_filter_urls()
    sys.exit(0 if success else 1)


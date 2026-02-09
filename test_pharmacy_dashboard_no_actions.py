"""
Quick test to verify pharmacy dashboard renders without the quick-action buttons.
Run with: python test_pharmacy_dashboard_no_actions.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cc.settings')
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from tenants.models import Business, Location, Membership

User = get_user_model()

def test_pharmacy_dashboard_no_quick_actions():
    """Test that pharmacy dashboard renders without the floating action buttons."""
    import time
    client = Client()
    
    # Create test user with unique email
    timestamp = str(int(time.time()))
    user = User.objects.create_user(
        username=f'test_pharmacy_user_{timestamp}',
        email=f'test_pharmacy_{timestamp}@example.com',
        password='testpass123'
    )
    
    # Create pharmacy business
    business = Business.objects.create(
        name='Test Pharmacy',
        business_kind='pharmacy',
        status='active'
    )
    
    # Create location
    location = Location.objects.create(
        business=business,
        name='Main Branch',
        is_default=True
    )
    
    # Create membership
    Membership.objects.create(
        user=user,
        business=business,
        location=location,
        role='owner',
        status='active'
    )
    
    # Log in
    client.login(username=f'test_pharmacy_user_{timestamp}', password='testpass123')
    
    # Request pharmacy dashboard
    response = client.get('/verticals/pharmacy/dashboard/')
    
    # Check status code
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    # Check that the page content does NOT contain the quick-actions buttons
    content = response.content.decode('utf-8')
    
    # These should NOT appear (the old floating action buttons)
    assert '⚡ Sell</a>' not in content, "Found '⚡ Sell' button that should be removed"
    assert '📦 Stock In</a>' not in content, "Found '📦 Stock In' button that should be removed"
    assert '📋 Batches</a>' not in content, "Found '📋 Batches' button that should be removed"
    assert '🧾 Sales</a>' not in content, "Found '🧾 Sales' button that should be removed"
    assert 'class="quick-actions"' not in content, "Found quick-actions class that should be removed"
    assert 'class="quick-btn"' not in content, "Found quick-btn class that should be removed"
    
    # These SHOULD appear (standard dashboard elements)
    assert 'Pharmacy & Cosmetics Dashboard' in content, "Dashboard title missing"
    assert 'Executive Summary' in content, "Executive Summary section missing"
    
    print("✅ SUCCESS: Pharmacy dashboard renders correctly without quick-action buttons")
    print(f"   Status: {response.status_code}")
    print(f"   Page size: {len(content)} bytes")
    print("   ✓ No '⚡ Sell' button found")
    print("   ✓ No '📦 Stock In' button found")
    print("   ✓ No '📋 Batches' button found")
    print("   ✓ No '🧾 Sales' button found")
    print("   ✓ No 'quick-actions' class found")
    print("   ✓ Dashboard title present")
    print("   ✓ Executive Summary section present")

if __name__ == '__main__':
    try:
        test_pharmacy_dashboard_no_quick_actions()
    except AssertionError as e:
        print(f"❌ FAILED: {e}")
        exit(1)
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)


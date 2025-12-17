#!/usr/bin/env python
"""
Quick test script to reproduce the /pharmacy/batches/ 500 error.
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cc.settings")
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from tenants.models import Business, Membership

User = get_user_model()

def test_pharmacy_batches():
    """Test pharmacy batches page with proper authentication and business context."""
    client = Client()
    
    # Get or create a test user
    user, created = User.objects.get_or_create(
        username="testpharmacy",
        defaults={
            "email": "test@pharmacy.com",
            "is_active": True,
        }
    )
    if created:
        user.set_password("test123")
        user.save()
        print(f"✓ Created test user: {user.username}")
    else:
        print(f"✓ Using existing user: {user.username}")
    
    # Get or create a pharmacy business
    business, created = Business.objects.get_or_create(
        slug="test-pharmacy",
        defaults={
            "name": "Test Pharmacy",
            "business_kind": "pharmacy",
            "created_by": user,
            "status": "ACTIVE",
        }
    )
    if created:
        print(f"✓ Created test business: {business.name}")
    else:
        print(f"✓ Using existing business: {business.name}")
    
    # Ensure membership exists
    membership, created = Membership.objects.get_or_create(
        user=user,
        business=business,
        location=None,
        defaults={
            "role": "MANAGER",
            "status": "ACTIVE",
        }
    )
    if created:
        print(f"✓ Created membership for {user.username} in {business.name}")
    else:
        print(f"✓ Using existing membership")
    
    # Login
    client.force_login(user)
    print(f"✓ Logged in as {user.username}")
    
    # Set active business in session
    session = client.session
    session["active_business_id"] = business.id
    session.save()
    print(f"✓ Set active business to: {business.name} (ID: {business.id})")
    
    # Test the batches page
    print("\n" + "="*60)
    print("Testing GET /pharmacy/batches/")
    print("="*60)
    
    try:
        response = client.get("/pharmacy/batches/")
        print(f"\nStatus Code: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ SUCCESS: Page loaded with status 200")
            return True
        elif response.status_code == 500:
            print("❌ ERROR 500: Internal Server Error")
            print("\nResponse content preview:")
            content = response.content.decode('utf-8')
            if 'Exception' in content or 'Error' in content:
                # Try to extract error details
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if 'Exception' in line or 'Error' in line:
                        print('\n'.join(lines[max(0, i-5):min(len(lines), i+10)]))
                        break
            return False
        else:
            print(f"❌ Unexpected status code: {response.status_code}")
            if response.status_code in [301, 302]:
                print(f"   Redirect to: {response.get('Location', 'unknown')}")
            return False
            
    except Exception as e:
        print(f"❌ EXCEPTION occurred:")
        print(f"   Type: {type(e).__name__}")
        print(f"   Message: {str(e)}")
        
        # Print traceback
        import traceback
        print("\nFull traceback:")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_pharmacy_batches()
    sys.exit(0 if success else 1)


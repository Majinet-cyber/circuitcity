#!/usr/bin/env python
"""
Quick test script to reproduce the /pharmacy/batches/ 500 error using Django TestCase.
"""
import os
import sys

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cc.settings")

import django
django.setup()

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from tenants.models import Business, Membership

User = get_user_model()

@override_settings(ALLOWED_HOSTS=['*'])
class PharmacyBatchesTest(TestCase):
    """Test pharmacy batches page."""
    
    def setUp(self):
        """Set up test user and business."""
        self.user = User.objects.create_user(
            username="testpharmacy",
            email="test@pharmacy.com",
            password="test123",
            is_active=True,
        )
        
        self.business = Business.objects.create(
            slug="test-pharmacy",
            name="Test Pharmacy",
            business_kind="pharmacy",
            created_by=self.user,
            status="ACTIVE",
        )
        
        self.membership = Membership.objects.create(
            user=self.user,
            business=self.business,
            location=None,
            role="MANAGER",
            status="ACTIVE",
        )
    
    def test_pharmacy_batches_page(self):
        """Test that /pharmacy/batches/ loads without error."""
        # Login
        self.client.force_login(self.user)
        
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        print(f"\n{'='*60}")
        print(f"Testing GET /pharmacy/batches/")
        print(f"User: {self.user.username}")
        print(f"Business: {self.business.name} (ID: {self.business.id})")
        print(f"{'='*60}\n")
        
        # Test the batches page
        response = self.client.get("/pharmacy/batches/")
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 500:
            print("\n❌ ERROR 500: Internal Server Error")
            content = response.content.decode('utf-8')
            if 'Exception' in content or 'Error' in content:
                # Extract error from Django error page
                import re
                # Try to find the exception type and message
                exc_match = re.search(r'<h1>(.*?)</h1>', content)
                if exc_match:
                    print(f"\nException: {exc_match.group(1)}")
                
                # Try to find the traceback
                tb_match = re.search(r'<div id="traceback".*?>(.*?)</div>', content, re.DOTALL)
                if tb_match:
                    print("\nTraceback found in response")
                    
        elif response.status_code == 200:
            print("✅ SUCCESS: Page loaded with status 200")
        else:
            print(f"❌ Unexpected status code: {response.status_code}")
            if response.status_code in [301, 302]:
                print(f"   Redirect to: {response.get('Location', 'unknown')}")
        
        # Assert 200 status
        self.assertEqual(
            response.status_code,
            200,
            f"Expected 200 but got {response.status_code}"
        )

if __name__ == "__main__":
    import unittest
    
    # Run the test
    suite = unittest.TestLoader().loadTestsFromTestCase(PharmacyBatchesTest)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    sys.exit(0 if result.wasSuccessful() else 1)


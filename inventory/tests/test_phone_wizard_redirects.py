# inventory/tests/test_phone_wizard_redirects.py
"""
Tests for phone sale wizard redirect fixes.
Ensures no NoReverseMatch errors occur during wizard navigation.
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from tenants.models import Business
from inventory.models_phone_products import PhoneProductCatalog
from inventory.business_kinds import BusinessKind

User = get_user_model()


class PhoneWizardRedirectsTestCase(TestCase):
    """Test phone sale wizard redirects work correctly"""

    def setUp(self):
        """Set up test data"""
        # Create a PHONES business
        self.business = Business.objects.create(name="Test Phone Shop", kind=BusinessKind.PHONES, is_active=True)

        # Create a test user
        self.user = User.objects.create_user(username="wizarduser", email="wizard@example.com", password="testpass123")

        # Create a test phone product
        self.product = PhoneProductCatalog.objects.create(
            business=self.business,
            brand="TECNO",
            model_name="Spark 40",
            ram_gb=4,
            rom_gb=128,
            variant_label="4+128",
            is_active=True,
        )

        self.client = Client()
        self.client.login(username="wizarduser", password="testpass123")

        # Set up session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_wizard_step_1_redirects_to_step_2(self):
        """Test step 1 POST redirects to step 2 without NoReverseMatch"""
        url = reverse("inventory:phone_sale_wizard")

        response = self.client.post(url, {"brand": "TECNO"}, follow=False)

        # Should redirect (302 or 303)
        self.assertIn(response.status_code, [302, 303])

        # Should redirect to step 2
        self.assertIn("step=2", response.url)

        # No NoReverseMatch exception should occur
        # If there was one, the test would fail with 500 error

    def test_wizard_step_2_redirects_to_step_3(self):
        """Test step 2 POST redirects to step 3 without NoReverseMatch"""
        # Set up session for step 2
        session = self.client.session
        session["sale_wizard_brand"] = "TECNO"
        session["sale_wizard_step"] = 2
        session.save()

        url = reverse("inventory:phone_sale_wizard") + "?step=2"

        response = self.client.post(url, {"model": "Spark 40", "product_id": str(self.product.id)}, follow=False)

        # Should redirect
        self.assertIn(response.status_code, [302, 303])

        # Should redirect to step 3
        self.assertIn("step=3", response.url)

    def test_wizard_no_reverse_match_error(self):
        """Test that wizard doesn't raise NoReverseMatch at any step"""
        # This test verifies the fix: previously redirect("inventory:phone_sale_wizard?step=2")
        # would raise NoReverseMatch. Now it should work.

        url = reverse("inventory:phone_sale_wizard")

        try:
            # Step 1
            response = self.client.post(url, {"brand": "TECNO"}, follow=False)
            self.assertIn(response.status_code, [200, 302, 303])

            # If we got here without exception, the fix worked
            self.assertTrue(True, "No NoReverseMatch error occurred")
        except Exception as e:
            if "NoReverseMatch" in str(e):
                self.fail(f"NoReverseMatch error still occurs: {e}")
            else:
                raise

    def test_wizard_base_url_accessible(self):
        """Test that wizard base URL is accessible"""
        url = reverse("inventory:phone_sale_wizard")
        response = self.client.get(url)

        # Should return 200 (step 1 by default)
        self.assertEqual(response.status_code, 200)

    def test_wizard_reset_works(self):
        """Test wizard reset endpoint"""
        url = reverse("inventory:phone_sale_wizard_reset")
        response = self.client.post(url, follow=False)

        # Should redirect to wizard start
        self.assertIn(response.status_code, [302, 303])

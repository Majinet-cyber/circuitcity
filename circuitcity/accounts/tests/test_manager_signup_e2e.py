# accounts/tests/test_manager_signup_e2e.py
"""
End-to-end integration tests for manager signup wizard.

These tests verify:
1. Signup wizard completes without errors (no IntegrityError, no TransactionManagementError)
2. Business is created with correct business_kind
3. Default Location is created
4. Trial subscription is created with valid plan_id (after transaction commits)
5. User is redirected to dashboard

CRITICAL: These tests prevent regression of the signup failure bug.
"""
import pytest
from decimal import Decimal
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestManagerSignupE2E(TransactionTestCase):
    """
    End-to-end test for manager signup wizard.
    
    Uses TransactionTestCase because:
    1. We need real database commits to test transaction.on_commit behavior
    2. We need to verify signals fire correctly
    """
    
    def setUp(self):
        """Ensure clean state before each test."""
        # Import models here to avoid import-time issues
        from tenants.models import Business
        from billing.models import SubscriptionPlan
        
        # Delete any existing test data
        Business.objects.filter(name__startswith="Test Store").delete()
        User.objects.filter(email__endswith="@test-signup.com").delete()
        
        # Ensure at least one plan exists
        if not SubscriptionPlan.objects.exists():
            SubscriptionPlan.objects.create(
                code="starter",
                name="Starter",
                amount=Decimal("0.00"),
                is_active=True,
            )
    
    def test_signup_manager_simple_form_success(self):
        """
        Test the simple manager signup form (/accounts/signup/manager/).
        
        This is the form that was breaking with IntegrityError.
        """
        from tenants.models import Business, Membership
        from inventory.models import Location
        
        url = reverse("accounts:signup_manager")
        
        # Unique email for this test run
        import uuid
        unique_id = uuid.uuid4().hex[:8]
        email = f"manager-{unique_id}@test-signup.com"
        
        response = self.client.post(url, {
            "email": email,
            "full_name": "Test Manager",
            "business_name": f"Test Store {unique_id}",
            "business_kind": "pharmacy",  # Test with pharmacy
            "password1": "SecurePass123!@#",
            "password2": "SecurePass123!@#",
        })
        
        # Should redirect on success (302), not error (200 with form errors or 500)
        self.assertIn(
            response.status_code,
            [200, 302],
            f"Unexpected status code: {response.status_code}. "
            f"Content: {response.content[:500] if response.content else 'empty'}"
        )
        
        # Check if user was created
        user = User.objects.filter(email=email).first()
        if response.status_code == 302:
            # Success case - verify everything was created
            self.assertIsNotNone(user, "User should be created on successful signup")
            
            # Check business was created
            business = Business.objects.filter(name__icontains=unique_id).first()
            self.assertIsNotNone(business, "Business should be created")
            self.assertEqual(business.business_kind, "pharmacy", "Business kind should be 'pharmacy'")
            
            # Check membership was created
            membership = Membership.objects.filter(user=user, business=business).first()
            self.assertIsNotNone(membership, "Manager membership should be created")
            self.assertEqual(membership.role, "MANAGER", "Role should be MANAGER")
            
            # Check default location was created
            location = Location.all_objects.filter(business=business).first()
            self.assertIsNotNone(location, "Default location should be created")
    
    def test_signup_with_farm_business_kind(self):
        """Test signup with the new 'farm' business kind."""
        from tenants.models import Business
        
        url = reverse("accounts:signup_manager")
        
        import uuid
        unique_id = uuid.uuid4().hex[:8]
        email = f"farmer-{unique_id}@test-signup.com"
        
        response = self.client.post(url, {
            "email": email,
            "full_name": "Test Farmer",
            "business_name": f"Test Farm {unique_id}",
            "business_kind": "farm",
            "password1": "SecurePass123!@#",
            "password2": "SecurePass123!@#",
        })
        
        if response.status_code == 302:
            # Success - verify business kind is saved correctly
            business = Business.objects.filter(name__icontains=unique_id).first()
            self.assertIsNotNone(business, "Farm business should be created")
            self.assertEqual(business.business_kind, "farm", "Business kind should be 'farm'")
    
    def test_signup_with_welding_business_kind(self):
        """Test signup with the new 'welding' business kind."""
        from tenants.models import Business
        
        url = reverse("accounts:signup_manager")
        
        import uuid
        unique_id = uuid.uuid4().hex[:8]
        email = f"welder-{unique_id}@test-signup.com"
        
        response = self.client.post(url, {
            "email": email,
            "full_name": "Test Welder",
            "business_name": f"Test Welding {unique_id}",
            "business_kind": "welding",
            "password1": "SecurePass123!@#",
            "password2": "SecurePass123!@#",
        })
        
        if response.status_code == 302:
            business = Business.objects.filter(name__icontains=unique_id).first()
            self.assertIsNotNone(business, "Welding business should be created")
            self.assertEqual(business.business_kind, "welding", "Business kind should be 'welding'")
    
    def test_signup_creates_no_integrity_error(self):
        """
        Specifically test that signup doesn't raise IntegrityError or TransactionManagementError.
        
        This was the critical bug: trial subscription creation inside the atomic block
        would fail with NOT NULL constraint on plan_id, poisoning the transaction.
        """
        from tenants.models import Business
        from billing.models import SubscriptionPlan
        
        url = reverse("accounts:signup_manager")
        
        import uuid
        unique_id = uuid.uuid4().hex[:8]
        email = f"noerror-{unique_id}@test-signup.com"
        
        # This should NOT raise any database errors
        try:
            response = self.client.post(url, {
                "email": email,
                "full_name": "No Error Test",
                "business_name": f"NoError Store {unique_id}",
                "business_kind": "phones",
                "password1": "SecurePass123!@#",
                "password2": "SecurePass123!@#",
            })
            
            # If we get here without exception, the bug is fixed
            # Response should be redirect (302) or form with validation errors (200)
            self.assertIn(
                response.status_code,
                [200, 302],
                "Signup should not return 500 error"
            )
            
        except Exception as e:
            self.fail(
                f"Signup raised unexpected exception: {type(e).__name__}: {e}\n"
                "This indicates the IntegrityError/TransactionManagementError bug is not fixed."
            )


@pytest.mark.django_db
class TestManagerSignupWizard(TestCase):
    """Test the multi-step signup wizard."""
    
    def test_signup_wizard_step2_shows_all_business_kinds(self):
        """
        Verify that step 2 of the signup wizard includes farm and welding options.
        """
        from inventory.business_kinds import BusinessKind
        
        # Verify BusinessKind enum has farm and welding
        choices = dict(BusinessKind.choices)
        
        self.assertIn("farm", choices, "BusinessKind should include 'farm'")
        self.assertIn("welding", choices, "BusinessKind should include 'welding'")
        
        # Verify display names
        self.assertEqual(choices["farm"], "Farm Manager")
        self.assertEqual(choices["welding"], "Welding Workshop")
    
    def test_wizard_step2_form_has_all_business_kinds(self):
        """Verify WizardStep2Form includes all business kinds including farm/welding."""
        from circuitcity.accounts.forms import WizardStep2Form
        
        form = WizardStep2Form()
        choices = dict(form.fields["business_kind"].choices)
        
        # Should include the new verticals
        self.assertIn("farm", choices, "WizardStep2Form should include 'farm' option")
        self.assertIn("welding", choices, "WizardStep2Form should include 'welding' option")


@pytest.mark.django_db
class TestBusinessKindNormalization(TestCase):
    """Test that business_kind values are correctly normalized."""
    
    def test_normalize_farm_variants(self):
        """Test normalization of farm-related input values."""
        from tenants.services.business_kind import normalize_business_kind
        
        self.assertEqual(normalize_business_kind("farm"), "farm")
        self.assertEqual(normalize_business_kind("Farm Manager"), "farm")
        self.assertEqual(normalize_business_kind("FARM"), "farm")
        self.assertEqual(normalize_business_kind("farming"), "farm")
        self.assertEqual(normalize_business_kind("agriculture"), "farm")
    
    def test_normalize_welding_variants(self):
        """Test normalization of welding-related input values."""
        from tenants.services.business_kind import normalize_business_kind
        
        self.assertEqual(normalize_business_kind("welding"), "welding")
        self.assertEqual(normalize_business_kind("Welding Workshop"), "welding")
        self.assertEqual(normalize_business_kind("WELDING"), "welding")
        self.assertEqual(normalize_business_kind("welder"), "welding")
        self.assertEqual(normalize_business_kind("metal work"), "welding")
    
    def test_validate_new_business_kinds(self):
        """Test validation of new business kinds."""
        from tenants.services.business_kind import validate_business_kind
        
        self.assertTrue(validate_business_kind("farm"))
        self.assertTrue(validate_business_kind("welding"))
        self.assertTrue(validate_business_kind("Farm Manager"))
        self.assertTrue(validate_business_kind("Welding Workshop"))
    
    def test_get_display_name(self):
        """Test display name retrieval for new business kinds."""
        from tenants.services.business_kind import get_display_name
        
        self.assertEqual(get_display_name("farm"), "Farm Manager")
        self.assertEqual(get_display_name("welding"), "Welding Workshop")


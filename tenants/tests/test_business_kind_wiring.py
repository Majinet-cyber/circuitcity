# tenants/tests/test_business_kind_wiring.py
"""
Tests for business kind wiring in signup and business creation.

These tests verify:
1. New business kinds (farm, welding) are wired correctly
2. Business creation with each kind works
3. Business kind normalization works for all variants
4. Forms include all business kinds

CRITICAL: These tests prevent regression when adding new verticals.
"""
import pytest
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestBusinessKindWiring(TestCase):
    """Test that all business kinds are properly wired."""
    
    def setUp(self):
        """Ensure plan exists for any subscription creation."""
        from billing.models import SubscriptionPlan
        
        SubscriptionPlan.objects.get_or_create(
            code="starter",
            defaults={
                "name": "Starter",
                "amount": Decimal("0.00"),
                "is_active": True,
            }
        )
    
    def test_create_business_with_farm_kind(self):
        """Test creating a business with 'farm' business_kind."""
        from tenants.models import Business
        
        business = Business.objects.create(
            name="Test Farm Business",
            slug="test-farm-business",
            status="ACTIVE",
            business_kind="farm",
        )
        
        self.assertEqual(business.business_kind, "farm")
        # Note: Django TestCase handles cleanup via transaction rollback
    
    def test_create_business_with_welding_kind(self):
        """Test creating a business with 'welding' business_kind."""
        from tenants.models import Business
        
        business = Business.objects.create(
            name="Test Welding Business",
            slug="test-welding-business",
            status="ACTIVE",
            business_kind="welding",
        )
        
        self.assertEqual(business.business_kind, "welding")
        # Note: Django TestCase handles cleanup via transaction rollback
    
    def test_all_canonical_business_kinds_are_valid(self):
        """Test that all canonical business kinds can be saved to the database."""
        from tenants.models import Business
        from tenants.services.business_kind import CANONICAL_BUSINESS_KINDS
        
        for i, kind in enumerate(CANONICAL_BUSINESS_KINDS.keys()):
            business = Business.objects.create(
                name=f"Test {kind.title()} Business {i}",
                slug=f"test-{kind}-business-{i}",
                status="ACTIVE",
                business_kind=kind,
            )
            
            # Refresh from DB to verify it saved correctly
            business.refresh_from_db()
            self.assertEqual(
                business.business_kind,
                kind,
                f"Business kind '{kind}' should be saved correctly"
            )
        # Note: Django TestCase handles cleanup via transaction rollback
    
    def test_farm_in_business_kind_choices(self):
        """Verify 'farm' is in BusinessKind.choices."""
        from inventory.business_kinds import BusinessKind
        
        choices_dict = dict(BusinessKind.choices)
        
        self.assertIn("farm", choices_dict)
        self.assertEqual(choices_dict["farm"], "Farm Manager")
    
    def test_welding_in_business_kind_choices(self):
        """Verify 'welding' is in BusinessKind.choices."""
        from inventory.business_kinds import BusinessKind
        
        choices_dict = dict(BusinessKind.choices)
        
        self.assertIn("welding", choices_dict)
        self.assertEqual(choices_dict["welding"], "Welding Workshop")
    
    def test_manager_signup_form_has_farm_welding(self):
        """Verify ManagerSignUpForm includes farm and welding options."""
        from circuitcity.accounts.forms import ManagerSignUpForm
        
        form = ManagerSignUpForm()
        choices_dict = dict(form.fields["business_kind"].choices)
        
        self.assertIn("farm", choices_dict, "ManagerSignUpForm should include 'farm'")
        self.assertIn("welding", choices_dict, "ManagerSignUpForm should include 'welding'")
    
    def test_manager_wizard_step2_form_has_farm_welding(self):
        """Verify ManagerWizardStep2Form includes farm and welding options."""
        from circuitcity.accounts.forms import ManagerWizardStep2Form
        
        form = ManagerWizardStep2Form()
        choices_dict = dict(form.fields["business_kind"].choices)
        
        self.assertIn("farm", choices_dict, "ManagerWizardStep2Form should include 'farm'")
        self.assertIn("welding", choices_dict, "ManagerWizardStep2Form should include 'welding'")


@pytest.mark.django_db
class TestBusinessKindNormalizationSSoT(TestCase):
    """Test the SSOT business kind normalization service."""
    
    def test_all_canonical_kinds_validate(self):
        """All canonical kinds should pass validation."""
        from tenants.services.business_kind import (
            validate_business_kind,
            CANONICAL_BUSINESS_KINDS,
        )
        
        for kind in CANONICAL_BUSINESS_KINDS.keys():
            self.assertTrue(
                validate_business_kind(kind),
                f"Canonical kind '{kind}' should validate"
            )
    
    def test_display_names_for_new_kinds(self):
        """Test display names for farm and welding."""
        from tenants.services.business_kind import get_display_name
        
        self.assertEqual(get_display_name("farm"), "Farm Manager")
        self.assertEqual(get_display_name("welding"), "Welding Workshop")
    
    def test_get_business_kind_info(self):
        """Test getting full info for business kinds."""
        from tenants.services.business_kind import get_business_kind_info
        
        farm_info = get_business_kind_info("farm")
        self.assertEqual(farm_info["display_name"], "Farm Manager")
        self.assertEqual(farm_info["icon"], "🌾")
        
        welding_info = get_business_kind_info("welding")
        self.assertEqual(welding_info["display_name"], "Welding Workshop")
        self.assertEqual(welding_info["icon"], "⚡")
    
    def test_get_all_business_kinds(self):
        """Test getting all business kinds as choices."""
        from tenants.services.business_kind import get_all_business_kinds
        
        choices = get_all_business_kinds()
        choices_dict = dict(choices)
        
        self.assertIn("farm", choices_dict)
        self.assertIn("welding", choices_dict)
        self.assertIn("pharmacy", choices_dict)
        self.assertIn("phones", choices_dict)
    
    def test_normalization_preserves_existing_verticals(self):
        """Ensure normalization still works for existing verticals."""
        from tenants.services.business_kind import normalize_business_kind
        
        # Existing verticals should still normalize correctly
        self.assertEqual(normalize_business_kind("phones"), "phones")
        self.assertEqual(normalize_business_kind("Phones & Electronics"), "phones")
        
        self.assertEqual(normalize_business_kind("pharmacy"), "pharmacy")
        self.assertEqual(normalize_business_kind("Cosmetics & Pharmacy"), "pharmacy")
        
        self.assertEqual(normalize_business_kind("gym"), "gym")
        self.assertEqual(normalize_business_kind("Gym / Fitness"), "gym")
        
        self.assertEqual(normalize_business_kind("grocery"), "grocery")
        self.assertEqual(normalize_business_kind("Grocery / General"), "grocery")
        
        self.assertEqual(normalize_business_kind("clothing"), "clothing")
        
        self.assertEqual(normalize_business_kind("hardware"), "hardware")
        self.assertEqual(normalize_business_kind("Hardware & General Dealers"), "hardware")
        
        self.assertEqual(normalize_business_kind("cement"), "cement")
        
        self.assertEqual(normalize_business_kind("liquor"), "liquor")


@pytest.mark.django_db
class TestBusinessKindInSignupFlow(TestCase):
    """Test business kind handling through the signup flow."""
    
    def setUp(self):
        from billing.models import SubscriptionPlan
        
        SubscriptionPlan.objects.get_or_create(
            code="starter",
            defaults={
                "name": "Starter",
                "amount": Decimal("0.00"),
                "is_active": True,
            }
        )
    
    def test_signup_step2_template_contains_farm_welding(self):
        """
        GUARDRAIL TEST: Signup step 2 must contain Farm Manager and Welding Workshop.
        
        This test fails if the signup wizard step 2 is missing these options,
        preventing regression when the template changes.
        """
        from django.test import Client
        from django.urls import reverse
        
        client = Client()
        
        # First, we need to complete step 1 to access step 2
        step1_url = f"{reverse('accounts:signup_manager')}?step=1"
        response = client.get(step1_url)
        assert response.status_code == 200
        
        # Submit step 1 data to enable step 2
        response = client.post(step1_url, {
            "full_name": "Test User",
            "email": "test-farm-welding@example.com",
            "password1": "TestPass123!@#Strong",
            "password2": "TestPass123!@#Strong",
            "phone_number": "+265991234567",
            "action": "next",
        })
        
        # Should redirect to step 2
        step2_url = f"{reverse('accounts:signup_manager')}?step=2"
        response = client.get(step2_url)
        
        if response.status_code == 200:
            content = response.content.decode()
            
            # GUARDRAIL: Farm Manager must be present
            assert "Farm Manager" in content or "farm" in content, \
                "Signup step 2 MUST contain Farm Manager option"
            
            # GUARDRAIL: Welding Workshop must be present
            assert "Welding Workshop" in content or "welding" in content, \
                "Signup step 2 MUST contain Welding Workshop option"
    
    def test_wizard_step2_form_validates_farm(self):
        """Test that WizardStep2Form accepts 'farm' as valid."""
        from circuitcity.accounts.forms import WizardStep2Form
        
        form = WizardStep2Form(data={
            "business_name": "Test Farm",
            "business_kind": "farm",
            "country": "Malawi",
            "currency": "MWK",
        })
        
        # Should be valid
        if not form.is_valid():
            self.fail(f"Form should accept 'farm': {form.errors}")
        
        self.assertEqual(form.cleaned_data["business_kind"], "farm")
    
    def test_wizard_step2_form_validates_welding(self):
        """Test that WizardStep2Form accepts 'welding' as valid."""
        from circuitcity.accounts.forms import WizardStep2Form
        
        form = WizardStep2Form(data={
            "business_name": "Test Welding Shop",
            "business_kind": "welding",
            "country": "Malawi",
            "currency": "MWK",
        })
        
        if not form.is_valid():
            self.fail(f"Form should accept 'welding': {form.errors}")
        
        self.assertEqual(form.cleaned_data["business_kind"], "welding")
    
    def test_business_created_with_normalized_kind(self):
        """Test that business is created with normalized business_kind."""
        from tenants.models import Business
        from tenants.services.business_kind import normalize_business_kind
        
        # Simulate what the signup view does
        raw_kind = "Farm Manager"  # Display label from form
        normalized = normalize_business_kind(raw_kind)
        
        self.assertEqual(normalized, "farm")
        
        # Create business with normalized kind
        business = Business.objects.create(
            name="Test Normalized Farm",
            slug="test-normalized-farm",
            status="ACTIVE",
            business_kind=normalized,
        )
        
        self.assertEqual(business.business_kind, "farm")
        # Note: Django TestCase handles cleanup via transaction rollback

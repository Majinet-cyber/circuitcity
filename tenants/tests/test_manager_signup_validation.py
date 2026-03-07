# tenants/tests/test_manager_signup_validation.py
"""
Tests for manager signup validation:
- Store name must not be numeric-only
- Email must not already exist
- Store name must be unique
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from tenants.models import Business
from tenants.forms import CreateBusinessForm
from tenants.validators import validate_business_name_not_numeric

# Also test the wizard forms
try:
    from circuitcity.accounts.forms import WizardStep1Form, WizardStep2Form
except ImportError:
    WizardStep1Form = None
    WizardStep2Form = None

User = get_user_model()


class ValidatorTestCase(TestCase):
    """Test the validate_business_name_not_numeric validator directly."""
    
    def test_numeric_only_name_rejected(self):
        """Numeric-only names should be rejected."""
        with self.assertRaises(ValidationError) as cm:
            validate_business_name_not_numeric("444444")
        self.assertIn("only numbers", str(cm.exception).lower())
    
    def test_numeric_with_spaces_rejected(self):
        """Numeric-only names with spaces should be rejected."""
        with self.assertRaises(ValidationError) as cm:
            validate_business_name_not_numeric("123 456")
        self.assertIn("only numbers", str(cm.exception).lower())
    
    def test_name_with_letters_and_digits_allowed(self):
        """Names with letters and digits are allowed."""
        # Should not raise
        validate_business_name_not_numeric("Mo Touch 2")
        validate_business_name_not_numeric("Store 123")
        validate_business_name_not_numeric("Circuit City")


class CreateBusinessFormTestCase(TestCase):
    """Test the CreateBusinessForm validation."""
    
    def test_store_name_rejects_numeric_only(self):
        """Form should reject numeric-only store names."""
        form = CreateBusinessForm(data={"name": "444444"})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
        error_msg = str(form.errors["name"])
        self.assertIn("only numbers", error_msg.lower())
    
    def test_duplicate_store_name_rejected(self):
        """Form should reject duplicate store names (case-insensitive)."""
        # Create an existing business
        Business.objects.create(
            name="Empire Phones",
            slug="empire-phones",
            status="ACTIVE"
        )
        
        # Try to create another with the same name (different case)
        form = CreateBusinessForm(data={"name": "empire phones"})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
        error_msg = str(form.errors["name"])
        self.assertIn("already in use", error_msg.lower())
    
    def test_valid_store_name_accepted(self):
        """Form should accept valid store names."""
        form = CreateBusinessForm(data={"name": "Mo Touch Electronics", "business_kind": "phones", "currency": "MWK"})
        self.assertTrue(form.is_valid())


class WizardSignupValidationTestCase(TestCase):
    """Test the signup wizard forms validation."""
    
    def test_duplicate_email_rejected_on_wizard_step1(self):
        """WizardStep1Form should reject duplicate emails."""
        if WizardStep1Form is None:
            self.skipTest("WizardStep1Form not available")
        
        # Pre-create a user with this email
        User.objects.create_user(
            username="owner@example.com",
            email="owner@example.com",
            password="TestPass123!@#"
        )
        
        # Try to sign up with that email
        form = WizardStep1Form(data={
            "full_name": "John Doe",
            "email": "owner@example.com",
            "password1": "StrongPass123!@#",
            "password2": "StrongPass123!@#"
        })
        
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)
        error_msg = str(form.errors["email"])
        self.assertIn("already", error_msg.lower())
    
    def test_duplicate_store_name_rejected_on_wizard_step2(self):
        """WizardStep2Form should reject duplicate store names."""
        if WizardStep2Form is None:
            self.skipTest("WizardStep2Form not available")
        
        # Pre-create a business
        Business.objects.create(
            name="Empire Phones",
            slug="empire-phones",
            status="ACTIVE"
        )
        
        # Try to sign up a new store with the same name
        form = WizardStep2Form(data={
            "business_name": "Empire Phones",
            "country": "Zambia",
            "currency": "ZMW",
            "business_kind": "phones"
        })
        
        self.assertFalse(form.is_valid())
        self.assertIn("business_name", form.errors)
        error_msg = str(form.errors["business_name"])
        self.assertIn("already in use", error_msg.lower())
    
    def test_numeric_only_store_name_rejected_on_wizard_step2(self):
        """WizardStep2Form should reject numeric-only store names."""
        if WizardStep2Form is None:
            self.skipTest("WizardStep2Form not available")
        
        form = WizardStep2Form(data={
            "business_name": "444444",
            "country": "ZM",
            "currency": "ZMW",
            "business_kind": "phones"
        })
        
        self.assertFalse(form.is_valid())
        self.assertIn("business_name", form.errors)
        error_msg = str(form.errors["business_name"])
        self.assertIn("only numbers", error_msg.lower())
    
    def test_valid_wizard_step1_data(self):
        """WizardStep1Form should accept valid data."""
        if WizardStep1Form is None:
            self.skipTest("WizardStep1Form not available")
        
        form = WizardStep1Form(data={
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "password1": "StrongPass123!@#",
            "password2": "StrongPass123!@#"
        })
        
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
    
    def test_valid_wizard_step2_data(self):
        """WizardStep2Form should accept valid data."""
        if WizardStep2Form is None:
            self.skipTest("WizardStep2Form not available")
        
        form = WizardStep2Form(data={
            "business_name": "Mo Touch Electronics",
            "country": "ZM",
            "currency": "ZMW",
            "business_kind": "phones"
        })
        
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")


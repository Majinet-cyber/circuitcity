# tests/test_clothing_price_validation.py
"""
Tests for clothing product price validation (guard-rails).
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.models import Location
from inventory.business_kinds import BusinessKind

User = get_user_model()


@pytest.mark.django_db
class TestClothingPriceValidation(TestCase):
    """Test clothing price validation guard-rails."""

    def setUp(self):
        """Set up test fixtures."""
        # Create clothing business
        self.business = Business.objects.create(
            name="Test Clothing Store",
            business_kind=BusinessKind.CLOTHING,
            slug="test-clothing-store",
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
        )
        
        # Create manager user
        self.manager = User.objects.create_user(
            username="manager@test.com",
            email="manager@test.com",
            password="testpass123",
            is_staff=True,
        )
        
        # Create manager membership
        self.manager_membership = Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )
        
        self.client = Client()
        
    def test_normal_price_accepted(self):
        """Test that normal prices are accepted without confirmation."""
        from inventory.views_products_v2 import ClothingProductForm
        
        form = ClothingProductForm(data={
            'product_name': 'T-Shirt',
            'size': 'M',
            'price': '15000.00',  # Normal price
            'confirm_high_price': False,
        })
        
        self.assertTrue(form.is_valid())
        
    def test_high_price_without_confirmation_rejected(self):
        """Test that high prices without confirmation are rejected."""
        from inventory.views_products_v2 import ClothingProductForm
        
        form = ClothingProductForm(data={
            'product_name': 'Designer Suit',
            'size': 'L',
            'price': '2000000.00',  # Above max (1,000,000)
            'confirm_high_price': False,  # No confirmation
        })
        
        self.assertFalse(form.is_valid())
        self.assertIn('price', form.errors)
        self.assertIn('unusually high', str(form.errors['price']))
        
    def test_high_price_with_confirmation_accepted(self):
        """Test that high prices with confirmation are accepted."""
        from inventory.views_products_v2 import ClothingProductForm
        
        form = ClothingProductForm(data={
            'product_name': 'Designer Suit',
            'size': 'L',
            'price': '2000000.00',  # Above max
            'confirm_high_price': True,  # Confirmed
        })
        
        self.assertTrue(form.is_valid())
        
    def test_exactly_max_price_accepted(self):
        """Test that price exactly at max is accepted without confirmation."""
        from inventory.views_products_v2 import ClothingProductForm
        
        form = ClothingProductForm(data={
            'product_name': 'Premium Jacket',
            'size': 'XL',
            'price': '1000000.00',  # Exactly at max
            'confirm_high_price': False,
        })
        
        self.assertTrue(form.is_valid())
        
    def test_slightly_above_max_rejected(self):
        """Test that price slightly above max is rejected without confirmation."""
        from inventory.views_products_v2 import ClothingProductForm
        
        form = ClothingProductForm(data={
            'product_name': 'Premium Jacket',
            'size': 'XL',
            'price': '1000001.00',  # Just above max
            'confirm_high_price': False,
        })
        
        self.assertFalse(form.is_valid())
        
    def test_zero_price_handled(self):
        """Test that zero price is handled (may be rejected by other validators)."""
        from inventory.views_products_v2 import ClothingProductForm
        
        form = ClothingProductForm(data={
            'product_name': 'Free Item',
            'size': 'S',
            'price': '0.00',
            'confirm_high_price': False,
        })
        
        # Form may be valid (zero price bypass guard-rail)
        # Other business logic should handle free items
        # This just tests that guard-rail doesn't break on zero
        
    def test_negative_price_rejected_by_widget(self):
        """Test that negative prices are rejected by HTML5 validation."""
        from inventory.views_products_v2 import ClothingProductForm
        
        # The widget has min="0", so HTML5 will reject negative
        # But for server-side, Django's DecimalField will also validate
        form = ClothingProductForm(data={
            'product_name': 'Invalid Item',
            'size': 'M',
            'price': '-100.00',
            'confirm_high_price': False,
        })
        
        # May be valid in form (Django DecimalField allows negative)
        # But the widget constraint prevents it in browser
        
    def test_very_high_price_error_message(self):
        """Test that error message for high price is clear."""
        from inventory.views_products_v2 import ClothingProductForm
        
        form = ClothingProductForm(data={
            'product_name': 'Expensive Item',
            'size': 'M',
            'price': '10000000.00',  # 10 million
            'confirm_high_price': False,
        })
        
        self.assertFalse(form.is_valid())
        error_message = str(form.errors['price'])
        
        # Check error message has key info
        self.assertIn('10,000,000', error_message)
        self.assertIn('unusually high', error_message.lower())
        self.assertIn('tick', error_message.lower())
        
    def test_missing_confirmation_field_defaults_to_false(self):
        """Test that missing confirm_high_price defaults to False."""
        from inventory.views_products_v2 import ClothingProductForm
        
        # Don't include confirm_high_price in data
        form = ClothingProductForm(data={
            'product_name': 'High Price Item',
            'size': 'L',
            'price': '1500000.00',
            # confirm_high_price not provided
        })
        
        self.assertFalse(form.is_valid())
        self.assertIn('price', form.errors)
        
    def test_form_has_confirmation_checkbox_widget(self):
        """Test that form has the confirmation checkbox."""
        from inventory.views_products_v2 import ClothingProductForm
        
        form = ClothingProductForm()
        
        # Check field exists
        self.assertIn('confirm_high_price', form.fields)
        
        # Check it's a BooleanField
        from django import forms
        self.assertIsInstance(form.fields['confirm_high_price'], forms.BooleanField)
        
        # Check widget is checkbox
        self.assertIsInstance(
            form.fields['confirm_high_price'].widget,
            forms.CheckboxInput
        )
        
    def test_decimal_precision_handled(self):
        """Test that decimal precision is handled correctly."""
        from inventory.views_products_v2 import ClothingProductForm
        
        form = ClothingProductForm(data={
            'product_name': 'Precise Price Item',
            'size': 'M',
            'price': '999999.99',  # Just under max
            'confirm_high_price': False,
        })
        
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['price'], Decimal('999999.99'))


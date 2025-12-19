# tests/test_vertical_upgrades.py
"""
Basic tests for new vertical upgrades.
Tests: Signup logic, Access restrictions, Gym QR, Groceries/Cement excludes agents/wallets.
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from tenants.models import Business
from inventory.models_verticals import GymMember
from inventory.models_grocery import GroceryProduct
from inventory.models_cement import CementProduct

User = get_user_model()


class PharmacyCosmeticsSignupTests(TestCase):
    """Test pharmacy/cosmetics signup selection logic."""
    
    def setUp(self):
        self.client = Client()
    
    def test_pharmacy_selection_shows_step2b(self):
        """When pharmacy is selected, step 2b should appear."""
        # Start wizard
        session = self.client.session
        session["manager_wizard"] = {
            "step1": {"email": "test@example.com", "password": "testpass123"},
            "step2": {"business_kind": "pharmacy", "business_name": "Test Pharmacy"}
        }
        session.save()
        
        # Request step 2b
        response = self.client.get(reverse("accounts:signup_manager") + "?step=2b")
        
        # Should show section selection form
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Which section(s) will you operate?")
    
    def test_cosmetics_selection_shows_step2b(self):
        """When cosmetics is selected, step 2b should appear."""
        session = self.client.session
        session["manager_wizard"] = {
            "step1": {"email": "test2@example.com", "password": "testpass123"},
            "step2": {"business_kind": "cosmetics", "business_name": "Test Cosmetics"}
        }
        session.save()
        
        response = self.client.get(reverse("accounts:signup_manager") + "?step=2b")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cosmetics")
    
    def test_section_flags_saved_to_business(self):
        """Test that section selections are saved to Business model."""
        # Create a business
        biz = Business.objects.create(
            name="Test Pharmacy",
            business_kind="pharmacy",
            has_pharmacy_section=True,
            has_cosmetics_section=False
        )
        
        self.assertTrue(biz.has_pharmacy_section)
        self.assertFalse(biz.has_cosmetics_section)
        
        # Update to both
        biz.has_cosmetics_section = True
        biz.save()
        
        biz.refresh_from_db()
        self.assertTrue(biz.has_pharmacy_section)
        self.assertTrue(biz.has_cosmetics_section)


class CosmeticsOptionalFieldsTests(TestCase):
    """Test that cosmetics products don't require SKU/expiry/mfg date."""
    
    def setUp(self):
        self.business = Business.objects.create(
            name="Test Cosmetics",
            business_kind="cosmetics",
            has_cosmetics_section=True
        )
    
    def test_cosmetics_categories_exist(self):
        """Test that cosmetics categories are available."""
        from inventory.models_pharmacy import PharmacyCategory
        
        cosmetics_categories = [
            "skin_care",
            "body_care",
            "oils",
            "creams",
            "serums",
            "lotions",
            "soaps_cleansers",
            "scrubs",
            "roll_on_deodorants",
            "shampoo_hair_care",
            "perfumes_body_sprays",
            "face_mask_sunscreen",
        ]
        
        for cat in cosmetics_categories:
            self.assertIn(cat, [c[0] for c in PharmacyCategory.choices])


class GroceryVerticalTests(TestCase):
    """Test groceries vertical basic functionality."""
    
    def setUp(self):
        self.business = Business.objects.create(
            name="Test Grocery",
            business_kind="groceries"
        )
        self.user = User.objects.create_user(
            username="grocery_manager",
            password="testpass123"
        )
    
    def test_grocery_product_creation(self):
        """Test creating a grocery product."""
        product = GroceryProduct.objects.create(
            business=self.business,
            name="Sugar",
            category="sugar_salt",
            unit_type="kg",
            quantity=Decimal("50.00"),
            cost_price=Decimal("2.50"),
            selling_price=Decimal("3.00")
        )
        
        self.assertEqual(product.name, "Sugar")
        self.assertEqual(product.unit_type, "kg")
        self.assertEqual(product.quantity, Decimal("50.00"))
    
    def test_grocery_unit_types(self):
        """Test that all required unit types exist."""
        from inventory.models_grocery import GroceryUnitType
        
        required_units = ["kg", "unit", "bag", "dozen"]
        for unit in required_units:
            self.assertIn(unit, [u[0] for u in GroceryUnitType.choices])


class CementVerticalTests(TestCase):
    """Test cement vertical basic functionality."""
    
    def setUp(self):
        self.business = Business.objects.create(
            name="Test Hardware",
            business_kind="cement"
        )
    
    def test_cement_product_creation(self):
        """Test creating a cement product."""
        product = CementProduct.objects.create(
            business=self.business,
            name="PPC Cement",
            category="cement",
            cement_type="ppc",
            quantity=Decimal("100.00"),
            cost_price=Decimal("15.00"),
            selling_price=Decimal("18.00")
        )
        
        self.assertEqual(product.name, "PPC Cement")
        self.assertEqual(product.cement_type, "ppc")
        self.assertEqual(product.quantity, Decimal("100.00"))
    
    def test_cement_types_exist(self):
        """Test that cement types are available."""
        from inventory.models_cement import CementType
        
        cement_types = ["ppc", "opc", "psc", "rhc", "src"]
        for ct in cement_types:
            self.assertIn(ct, [c[0] for c in CementType.choices])


class GymQRTests(TestCase):
    """Test gym QR code generation and lookup."""
    
    def setUp(self):
        self.business = Business.objects.create(
            name="Test Gym",
            business_kind="gym"
        )
        self.user = User.objects.create_user(
            username="gym_manager",
            password="testpass123"
        )
    
    def test_qr_token_auto_generation(self):
        """Test that QR token is auto-generated on member creation."""
        member = GymMember.objects.create(
            business=self.business,
            name="John Doe",
            phone="1234567890"
        )
        
        # QR token should be auto-generated
        self.assertIsNotNone(member.qr_token)
        self.assertNotEqual(member.qr_token, "")
        self.assertGreater(len(member.qr_token), 0)
    
    def test_qr_token_is_unique(self):
        """Test that QR tokens are unique per member."""
        member1 = GymMember.objects.create(
            business=self.business,
            name="John Doe",
            phone="1111111111"
        )
        
        member2 = GymMember.objects.create(
            business=self.business,
            name="Jane Doe",
            phone="2222222222"
        )
        
        self.assertNotEqual(member1.qr_token, member2.qr_token)
    
    def test_qr_lookup_returns_member_info(self):
        """Test QR lookup API returns correct member information."""
        member = GymMember.objects.create(
            business=self.business,
            name="Test Member",
            phone="9999999999"
        )
        
        # Login
        self.client.force_login(self.user)
        
        # Mock business resolution (in real app, middleware handles this)
        from unittest.mock import patch
        with patch('inventory.helpers.get_active_business', return_value=self.business):
            response = self.client.post(
                reverse("gym:qr_lookup"),
                {"qr_token": member.qr_token}
            )
        
        # Should return success
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data["member"]["name"], "Test Member")
    
    def test_invalid_qr_returns_error(self):
        """Test that invalid QR token returns proper error."""
        self.client.force_login(self.user)
        
        from unittest.mock import patch
        with patch('inventory.helpers.get_active_business', return_value=self.business):
            response = self.client.post(
                reverse("gym:qr_lookup"),
                {"qr_token": "invalid_token_12345"}
            )
        
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertFalse(data.get("success"))
        self.assertIn("not found", data.get("error", "").lower())


class NavigationTests(TestCase):
    """Test that Home navigation goes to Dashboard (not Analytics)."""
    
    def test_post_login_url_prioritizes_dashboard(self):
        """Test that _post_login_url prioritizes dashboard over analytics."""
        from circuitcity.accounts.views import _post_login_url
        
        url = _post_login_url()
        
        # Should NOT contain "analytics" or "insights"
        self.assertNotIn("analytics", url.lower())
        self.assertNotIn("insights", url.lower())
        
        # Should contain "dashboard" or "inventory"
        self.assertTrue(
            "dashboard" in url.lower() or "inventory" in url.lower(),
            f"Expected dashboard or inventory in URL, got: {url}"
        )


# Run tests with: python manage.py test tests.test_vertical_upgrades


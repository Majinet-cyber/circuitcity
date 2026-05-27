"""
Test that /pharmacy/batches/ loads successfully after implementing mul filter.
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from tenants.models import Business, Membership
from inventory.models import MerchProduct
from inventory.models_pharmacy import PharmacyBatch

User = get_user_model()


class PharmacyBatchesPageTest(TestCase):
    """Test the pharmacy batches page loads without 500 errors."""
    
    def setUp(self):
        """Set up test user and pharmacy business."""
        self.client = Client()
        
        # Create test user
        self.user = User.objects.create_user(
            username="pharmacytest",
            email="pharmacy@test.com",
            password="test123"
        )
        
        # Create pharmacy business
        self.business = Business.objects.create(
            name="Test Pharmacy",
            slug="test-pharmacy",
            business_kind="pharmacy",
            created_by=self.user,
            status="ACTIVE"
        )
        
        # Create membership
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
    
    def test_pharmacy_batches_page_loads(self):
        """
        Test that /pharmacy/batches/ returns HTTP 200.
        
        This tests that the mul and div template filters are properly loaded
        and the template renders without TemplateSyntaxError.
        """
        # Login
        self.client.force_login(self.user)
        
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        # Request the batches page
        response = self.client.get(
            "/pharmacy/batches/",
            HTTP_HOST="testserver"  # Explicitly set host to avoid ALLOWED_HOSTS issue
        )
        
        # Assert successful load
        self.assertEqual(
            response.status_code,
            200,
            f"Expected 200 OK, got {response.status_code}. "
            f"This likely means the mul/div filters are not properly loaded."
        )
        
        # Verify the template used
        self.assertTemplateUsed(response, "verticals/pharmacy/batch_list.html")
    
    def test_mul_filter_in_template_context(self):
        """Test that mul filter works in template rendering."""
        from django.template import Context, Template
        
        template_code = "{% load math_extras %}{{ 5|mul:3 }}"
        t = Template(template_code)
        c = Context({})
        result = t.render(c).strip()
        
        self.assertEqual(result, "15", "mul filter should multiply 5 * 3 = 15")
    
    def test_div_filter_in_template_context(self):
        """Test that div filter works in template rendering."""
        from django.template import Context, Template
        
        template_code = "{% load math_extras %}{{ 10|div:2 }}"
        t = Template(template_code)
        c = Context({})
        result = t.render(c).strip()
        
        self.assertEqual(result, "5.0", "div filter should divide 10 / 2 = 5.0")
    
    def test_pharmacy_batches_page_with_products(self):
        """
        Test that /pharmacy/batches/ returns 200 even when products lack reorder fields.
        
        This ensures MerchProduct.reorder_level property safely falls back and
        prevents VariableDoesNotExist crashes in templates.
        """
        # Login
        self.client.force_login(self.user)
        
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        # Create a MerchProduct (without explicit reorder_level field)
        product = MerchProduct.objects.create(
            business=self.business,
            name="Test Medicine",
            kind="pharmacy",
            category="medicine"
        )
        
        # Create a PharmacyBatch for this product
        PharmacyBatch.objects.create(
            business=self.business,
            merch_product=product,
            batch_number="BATCH001",
            expiry_date=timezone.now().date() + timedelta(days=90),
            quantity=50,
            reorder_level=10,
            cost_price=10.00,
            selling_price=15.00
        )
        
        # Request the batches page
        response = self.client.get(
            "/pharmacy/batches/",
            HTTP_HOST="testserver"
        )
        
        # Assert successful load (no 500 error)
        self.assertEqual(
            response.status_code,
            200,
            f"Expected 200 OK, got {response.status_code}. "
            f"The template should not crash when accessing product.reorder_level."
        )
        
        # Verify the template used
        self.assertTemplateUsed(response, "verticals/pharmacy/batch_list.html")


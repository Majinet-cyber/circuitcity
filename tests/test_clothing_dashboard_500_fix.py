"""
Regression test for clothing dashboard 500 error fix.

Root Cause:
    django.db.utils.OperationalError: no such column: inventory_merchproduct.bottles_per_crate
    
    The MerchProduct model had bottles_per_crate field defined but migrations were not applied,
    causing the clothing dashboard to crash when querying products.

Fix:
    Applied migration inventory.1004_merchproduct_bottles_per_crate_and_more to add the missing columns.

This test ensures:
1. Clothing dashboard renders without 500 errors
2. Dashboard works with no data (empty state)
3. Dashboard works with clothing products
4. All KPIs render safely with default values
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct

User = get_user_model()


class ClothingDashboard500FixTest(TestCase):
    """Test that clothing dashboard never returns 500 errors"""
    
    def setUp(self):
        """Create test user and clothing business"""
        self.client = Client()
        
        # Create manager user
        self.user = User.objects.create_user(
            username='clothingmanager',
            email='manager@clothing.test',
            password='testpass123'
        )
        
        # Create clothing business
        self.business = Business.objects.create(
            name='Test Clothing Store',
            slug='test-clothing-store',
            business_kind=BusinessKind.CLOTHING,
            created_by=self.user,
            status='ACTIVE'
        )
        
        # Create membership (manager role)
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role='MANAGER',
            status='ACTIVE'
        )
        
        # Log in the user
        self.client.login(username='clothingmanager', password='testpass123')
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
    
    def test_clothing_dashboard_renders_with_no_data(self):
        """
        Test that dashboard renders successfully with no products or sales.
        This is the critical regression test - dashboard must render even when empty.
        """
        url = reverse('verticals:clothing_dashboard')
        response = self.client.get(url)
        
        # Assert HTTP 200 (not 500)
        self.assertEqual(
            response.status_code, 
            200,
            f"Expected 200 OK but got {response.status_code}. "
            f"Dashboard should never crash with empty data."
        )
        
        # Verify page contains expected content
        self.assertContains(response, 'Clothing')
        
        # Verify KPIs render with safe defaults (0)
        # These should all be present in the template
        self.assertIn('revenue_mtd', response.context)
        self.assertIn('profit_mtd', response.context)
        self.assertIn('total_sales_mtd', response.context)
        self.assertIn('inventory_value', response.context)
        
        # All metrics should be 0 or safe defaults
        self.assertEqual(response.context['revenue_mtd'], Decimal('0.00'))
        self.assertEqual(response.context['profit_mtd'], Decimal('0.00'))
        self.assertEqual(response.context['total_sales_mtd'], 0)
    
    def test_clothing_dashboard_renders_with_products(self):
        """Test that dashboard renders successfully with clothing products"""
        # Create some clothing products
        MerchProduct.objects.create(
            business=self.business,
            name='T-Shirt - M - Black',
            kind=BusinessKind.CLOTHING,
            size='M',
            color='Black',
            quantity_in_stock=10,
            cost_price=Decimal('5000.00'),
            selling_price=Decimal('8000.00'),
            is_active=True
        )
        
        MerchProduct.objects.create(
            business=self.business,
            name='Jeans - 32 - Blue',
            kind=BusinessKind.CLOTHING,
            size='32',
            color='Blue',
            quantity_in_stock=5,
            cost_price=Decimal('12000.00'),
            selling_price=Decimal('18000.00'),
            is_active=True
        )
        
        url = reverse('verticals:clothing_dashboard')
        response = self.client.get(url)
        
        # Assert HTTP 200
        self.assertEqual(response.status_code, 200)
        
        # Verify products are shown
        self.assertIn('product_count', response.context)
        self.assertEqual(response.context['product_count'], 2)
        
        # Verify recent products are returned
        self.assertIn('recent_products', response.context)
        self.assertEqual(len(response.context['recent_products']), 2)
    
    def test_clothing_dashboard_database_query_works(self):
        """
        Test that the exact database query that was failing now works.
        
        This directly tests the fix for:
        File "inventory/verticals/base.py", line 130, in merch_metrics
            recent = list(qs.order_by("-id")[:recent_limit])
        django.db.utils.OperationalError: no such column: inventory_merchproduct.bottles_per_crate
        """
        # Import the exact function that was failing
        from inventory.verticals.base import merch_metrics
        
        # Create a product to query
        MerchProduct.objects.create(
            business=self.business,
            name='Test Product',
            kind=BusinessKind.CLOTHING,
            is_active=True
        )
        
        # This call was causing the 500 error - it should now work
        try:
            metrics = merch_metrics(self.business, BusinessKind.CLOTHING)
        except Exception as e:
            self.fail(
                f"merch_metrics() raised {type(e).__name__}: {e}. "
                f"This means the bottles_per_crate column is still missing from the database. "
                f"Run: python manage.py migrate inventory"
            )
        
        # Verify metrics are returned correctly
        self.assertIsInstance(metrics, dict)
        self.assertIn('total', metrics)
        self.assertIn('active', metrics)
        self.assertIn('recent', metrics)
        self.assertEqual(metrics['total'], 1)
        self.assertEqual(metrics['active'], 1)
    
    def test_clothing_dashboard_page_contains_kpi_labels(self):
        """Test that page contains at least one KPI label (as per requirements)"""
        url = reverse('verticals:clothing_dashboard')
        response = self.client.get(url)
        
        # Assert HTTP 200
        self.assertEqual(response.status_code, 200)
        
        # Verify page contains KPI labels
        # Looking for common KPI text that would appear on the dashboard
        content = response.content.decode('utf-8').lower()
        
        # At least one of these should be present
        kpi_indicators = [
            'revenue',
            'profit',
            'sales',
            'stock',
            'inventory',
            'total'
        ]
        
        found_kpi = any(indicator in content for indicator in kpi_indicators)
        self.assertTrue(
            found_kpi,
            f"Dashboard should contain at least one KPI label. "
            f"Searched for: {kpi_indicators}"
        )
    
    def test_clothing_dashboard_works_for_other_business_kinds(self):
        """
        Verify that other vertical dashboards are not affected by this fix.
        This ensures the migration is safe and doesn't break other verticals.
        """
        # Create a liquor business
        liquor_business = Business.objects.create(
            name='Test Liquor Store',
            slug='test-liquor-store',
            business_kind=BusinessKind.LIQUOR,
            created_by=self.user,
            status='ACTIVE'
        )
        
        Membership.objects.create(
            user=self.user,
            business=liquor_business,
            role='MANAGER',
            status='ACTIVE'
        )
        
        # Create a liquor product (which SHOULD use bottles_per_crate)
        product = MerchProduct.objects.create(
            business=liquor_business,
            name='Test Beer',
            kind=BusinessKind.LIQUOR,
            bottles_per_crate=20,  # This field should work
            supports_crates=True,
            is_active=True
        )
        
        # Verify the liquor product saved correctly
        self.assertEqual(product.bottles_per_crate, 20)
        self.assertTrue(product.supports_crates)
        
        # Test merch_metrics for liquor
        from inventory.verticals.base import merch_metrics
        metrics = merch_metrics(liquor_business, BusinessKind.LIQUOR)
        
        self.assertEqual(metrics['total'], 1)


class ClothingDashboardConsistencyTest(TestCase):
    """
    Test that clothing dashboard behavior is consistent with other vertical dashboards.
    """
    
    def setUp(self):
        """Create test user and businesses for different verticals"""
        self.client = Client()
        
        self.user = User.objects.create_user(
            username='testmanager',
            email='manager@test.com',
            password='testpass123'
        )
        
        # Create businesses for each vertical
        self.clothing_business = Business.objects.create(
            name='Clothing Store',
            slug='clothing-store',
            business_kind=BusinessKind.CLOTHING,
            created_by=self.user,
            status='ACTIVE'
        )
        
        self.pharmacy_business = Business.objects.create(
            name='Pharmacy',
            slug='pharmacy',
            business_kind=BusinessKind.PHARMACY,
            created_by=self.user,
            status='ACTIVE'
        )
        
        # Create memberships
        Membership.objects.create(
            user=self.user,
            business=self.clothing_business,
            role='MANAGER',
            status='ACTIVE'
        )
        
        Membership.objects.create(
            user=self.user,
            business=self.pharmacy_business,
            role='MANAGER',
            status='ACTIVE'
        )
        
        self.client.login(username='testmanager', password='testpass123')
    
    def test_all_vertical_dashboards_return_200(self):
        """
        Test that all vertical dashboards return 200 status.
        This ensures consistency across verticals.
        """
        vertical_tests = [
            ('verticals:clothing_dashboard', self.clothing_business.id),
            ('verticals:pharmacy_dashboard', self.pharmacy_business.id),
        ]
        
        for url_name, business_id in vertical_tests:
            with self.subTest(vertical=url_name):
                # Set active business
                session = self.client.session
                session['active_business_id'] = business_id
                session.save()
                
                url = reverse(url_name)
                response = self.client.get(url)
                
                self.assertEqual(
                    response.status_code,
                    200,
                    f"{url_name} should return 200, got {response.status_code}"
                )


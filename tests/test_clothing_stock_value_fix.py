"""
Test for Clothing Dashboard Stock Value Fix.

Problem:
    Stock Value KPI card on /verticals/clothing/dashboard/ showed K 0 even when
    the business had stock (tracked units and/or common stock).

Solution:
    Updated clothing_inventory_metrics() to compute stock value correctly:
    - Tracked stock: Sum of cost_price for all AVAILABLE ClothingBarcodeUnit
    - Common stock: Sum of (quantity_in_stock * cost_price) for MerchProduct
    - Must not double-count (exclude products with tracked units from common stock)

This test ensures:
1. Stock value includes tracked units (barcoded items)
2. Stock value includes common stock (quantity-based products)
3. No double-counting when products have both
4. Sold tracked units are excluded
5. Location scoping works correctly
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct, Location
from inventory.models_clothing_barcode import ClothingBarcodeUnit
from inventory.verticals.base import compute_clothing_stock_value, clothing_inventory_metrics

User = get_user_model()


class ClothingStockValueFixTest(TestCase):
    """Test that stock value correctly includes tracked + common stock"""
    
    def setUp(self):
        """Create test user, business, and locations"""
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
        
        # Create locations
        self.location_main = Location.objects.create(
            name='Main Store',
            business=self.business,
            is_default=True
        )
        
        self.location_branch = Location.objects.create(
            name='Branch Store',
            business=self.business,
            is_default=False
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
        session['active_location_id'] = self.location_main.id
        session.save()
    
    def test_stock_value_includes_tracked_units(self):
        """
        Test: Stock value counts tracked units (barcoded items).
        
        Setup:
            - Create 4 tracked units, cost=40000 each
            - Expected tracked value = 160000
        """
        # Create a product (parent)
        product = MerchProduct.objects.create(
            business=self.business,
            name='Nike Air Max',
            kind=BusinessKind.CLOTHING,
            category='shoes',
            cost_price=Decimal('40000.00'),
            selling_price=Decimal('55000.00'),
            quantity_in_stock=0,  # No common stock, only tracked units
            is_active=True,
            is_archived=False,
        )
        
        # Create 4 tracked units
        for i in range(4):
            ClothingBarcodeUnit.objects.create(
                business=self.business,
                location=self.location_main,
                product=product,
                barcode=f'NIKE-{i+1}',
                size='42',
                category='shoes',
                brand='Nike',
                cost_price=Decimal('40000.00'),
                selling_price=Decimal('55000.00'),
                status='IN_STOCK',
                is_active=True,
            )
        
        # Compute stock value
        stock_value = compute_clothing_stock_value(self.business, self.location_main)
        
        # Assert: tracked value = 4 × 40000 = 160000
        expected_value = Decimal('160000.00')
        self.assertEqual(
            stock_value,
            expected_value,
            f"Expected stock value {expected_value} but got {stock_value}. "
            f"Tracked units should contribute to stock value."
        )
    
    def test_stock_value_includes_common_stock(self):
        """
        Test: Stock value counts common stock (quantity-based products).
        
        Setup:
            - Create product with qty=3, cost=39000
            - Expected common value = 117000
        """
        MerchProduct.objects.create(
            business=self.business,
            name='Generic T-Shirt',
            kind=BusinessKind.CLOTHING,
            category='shirt',
            cost_price=Decimal('39000.00'),
            selling_price=Decimal('50000.00'),
            quantity_in_stock=3,
            is_active=True,
            is_archived=False,
        )
        
        # Compute stock value
        stock_value = compute_clothing_stock_value(self.business, self.location_main)
        
        # Assert: common value = 3 × 39000 = 117000
        expected_value = Decimal('117000.00')
        self.assertEqual(
            stock_value,
            expected_value,
            f"Expected stock value {expected_value} but got {stock_value}. "
            f"Common stock should contribute to stock value."
        )
    
    def test_stock_value_includes_tracked_and_common(self):
        """
        Test: Stock value counts BOTH tracked + common stock.
        
        Setup:
            - Tracked: 4 units × 40000 = 160000
            - Common: 3 qty × 39000 = 117000
            - Expected total = 277000
        """
        # 1. Tracked product
        tracked_product = MerchProduct.objects.create(
            business=self.business,
            name='Nike Air Max',
            kind=BusinessKind.CLOTHING,
            category='shoes',
            cost_price=Decimal('40000.00'),
            selling_price=Decimal('55000.00'),
            quantity_in_stock=0,  # No common stock
            is_active=True,
            is_archived=False,
        )
        
        for i in range(4):
            ClothingBarcodeUnit.objects.create(
                business=self.business,
                location=self.location_main,
                product=tracked_product,
                barcode=f'NIKE-{i+1}',
                size='42',
                category='shoes',
                brand='Nike',
                cost_price=Decimal('40000.00'),
                selling_price=Decimal('55000.00'),
                status='IN_STOCK',
                is_active=True,
            )
        
        # 2. Common stock product
        MerchProduct.objects.create(
            business=self.business,
            name='Generic T-Shirt',
            kind=BusinessKind.CLOTHING,
            category='shirt',
            cost_price=Decimal('39000.00'),
            selling_price=Decimal('50000.00'),
            quantity_in_stock=3,
            is_active=True,
            is_archived=False,
        )
        
        # Compute stock value
        stock_value = compute_clothing_stock_value(self.business, self.location_main)
        
        # Assert: total = 160000 + 117000 = 277000
        expected_value = Decimal('277000.00')
        self.assertEqual(
            stock_value,
            expected_value,
            f"Expected stock value {expected_value} but got {stock_value}. "
            f"Stock value should include BOTH tracked and common stock."
        )
    
    def test_sold_tracked_units_excluded(self):
        """
        Test: Sold tracked units do NOT contribute to stock value.
        
        Setup:
            - Create 4 tracked units
            - Mark 1 as SOLD
            - Expected value = 3 × 40000 = 120000 (only available units)
        """
        product = MerchProduct.objects.create(
            business=self.business,
            name='Nike Air Max',
            kind=BusinessKind.CLOTHING,
            category='shoes',
            cost_price=Decimal('40000.00'),
            selling_price=Decimal('55000.00'),
            quantity_in_stock=0,
            is_active=True,
            is_archived=False,
        )
        
        # Create 4 units
        units = []
        for i in range(4):
            unit = ClothingBarcodeUnit.objects.create(
                business=self.business,
                location=self.location_main,
                product=product,
                barcode=f'NIKE-{i+1}',
                size='42',
                category='shoes',
                brand='Nike',
                cost_price=Decimal('40000.00'),
                selling_price=Decimal('55000.00'),
                status='IN_STOCK',
                is_active=True,
            )
            units.append(unit)
        
        # Mark 1 unit as SOLD
        units[0].status = 'SOLD'
        units[0].save()
        
        # Compute stock value
        stock_value = compute_clothing_stock_value(self.business, self.location_main)
        
        # Assert: only 3 available units count = 3 × 40000 = 120000
        expected_value = Decimal('120000.00')
        self.assertEqual(
            stock_value,
            expected_value,
            f"Expected stock value {expected_value} but got {stock_value}. "
            f"Sold units should NOT be included in stock value."
        )
    
    def test_location_scoping(self):
        """
        Test: Stock value respects location scoping.
        
        Setup:
            - Main location: 4 tracked units
            - Branch location: 2 tracked units
            - Query for Main location should only count 4 units
        """
        product = MerchProduct.objects.create(
            business=self.business,
            name='Nike Air Max',
            kind=BusinessKind.CLOTHING,
            category='shoes',
            cost_price=Decimal('40000.00'),
            selling_price=Decimal('55000.00'),
            quantity_in_stock=0,
            is_active=True,
            is_archived=False,
        )
        
        # Main location: 4 units
        for i in range(4):
            ClothingBarcodeUnit.objects.create(
                business=self.business,
                location=self.location_main,
                product=product,
                barcode=f'MAIN-{i+1}',
                size='42',
                category='shoes',
                brand='Nike',
                cost_price=Decimal('40000.00'),
                selling_price=Decimal('55000.00'),
                status='IN_STOCK',
                is_active=True,
            )
        
        # Branch location: 2 units
        for i in range(2):
            ClothingBarcodeUnit.objects.create(
                business=self.business,
                location=self.location_branch,
                product=product,
                barcode=f'BRANCH-{i+1}',
                size='42',
                category='shoes',
                brand='Nike',
                cost_price=Decimal('40000.00'),
                selling_price=Decimal('55000.00'),
                status='IN_STOCK',
                is_active=True,
            )
        
        # Compute stock value for Main location only
        stock_value = compute_clothing_stock_value(self.business, self.location_main)
        
        # Assert: only 4 units from Main location = 4 × 40000 = 160000
        expected_value = Decimal('160000.00')
        self.assertEqual(
            stock_value,
            expected_value,
            f"Expected stock value {expected_value} but got {stock_value}. "
            f"Stock value should only include units from specified location."
        )
    
    def test_no_double_counting(self):
        """
        Test: Products with tracked units are NOT counted in common stock.
        
        Setup:
            - Create product with quantity_in_stock=5
            - Create 3 tracked units for same product
            - Expected: Only tracked units count (3 × 40000 = 120000)
            - Common stock should be excluded to avoid double counting
        """
        product = MerchProduct.objects.create(
            business=self.business,
            name='Nike Air Max',
            kind=BusinessKind.CLOTHING,
            category='shoes',
            cost_price=Decimal('40000.00'),
            selling_price=Decimal('55000.00'),
            quantity_in_stock=5,  # This should be IGNORED (has tracked units)
            is_active=True,
            is_archived=False,
        )
        
        # Create 3 tracked units
        for i in range(3):
            ClothingBarcodeUnit.objects.create(
                business=self.business,
                location=self.location_main,
                product=product,
                barcode=f'NIKE-{i+1}',
                size='42',
                category='shoes',
                brand='Nike',
                cost_price=Decimal('40000.00'),
                selling_price=Decimal('55000.00'),
                status='IN_STOCK',
                is_active=True,
            )
        
        # Compute stock value
        stock_value = compute_clothing_stock_value(self.business, self.location_main)
        
        # Assert: only tracked units count = 3 × 40000 = 120000
        # quantity_in_stock=5 should be EXCLUDED to avoid double counting
        expected_value = Decimal('120000.00')
        self.assertEqual(
            stock_value,
            expected_value,
            f"Expected stock value {expected_value} but got {stock_value}. "
            f"Products with tracked units should NOT be counted in common stock."
        )
    
    def test_dashboard_displays_stock_value(self):
        """
        Test: Clothing dashboard displays correct stock value in KPI card.
        
        This is the integration test for the full dashboard view.
        """
        # Create stock
        product = MerchProduct.objects.create(
            business=self.business,
            name='Nike Air Max',
            kind=BusinessKind.CLOTHING,
            category='shoes',
            cost_price=Decimal('40000.00'),
            selling_price=Decimal('55000.00'),
            quantity_in_stock=0,
            is_active=True,
            is_archived=False,
        )
        
        for i in range(4):
            ClothingBarcodeUnit.objects.create(
                business=self.business,
                location=self.location_main,
                product=product,
                barcode=f'NIKE-{i+1}',
                size='42',
                category='shoes',
                brand='Nike',
                cost_price=Decimal('40000.00'),
                selling_price=Decimal('55000.00'),
                status='IN_STOCK',
                is_active=True,
            )
        
        # Request dashboard
        url = reverse('verticals:clothing_dashboard')
        response = self.client.get(url)
        
        # Assert: HTTP 200
        self.assertEqual(response.status_code, 200)
        
        # Assert: inventory_value in context
        self.assertIn('inventory_value', response.context)
        
        # Assert: inventory_value = 160000
        expected_value = Decimal('160000.00')
        actual_value = response.context['inventory_value']
        self.assertEqual(
            actual_value,
            expected_value,
            f"Expected dashboard inventory_value {expected_value} but got {actual_value}. "
            f"Dashboard should display correct stock value."
        )
        
        # Assert: Stock Value KPI card shows the value (rendered in template)
        # The template displays: K {{ inventory_value|floatformat:0|default:"0"|intcomma }}
        # Which formats 160000 as "160,000"
        self.assertContains(response, '160,000')
    
    def test_empty_stock_shows_zero(self):
        """
        Test: Stock value = 0 when no stock exists.
        
        Regression test: dashboard should not crash with empty stock.
        """
        # No stock created
        
        # Compute stock value
        stock_value = compute_clothing_stock_value(self.business, self.location_main)
        
        # Assert: stock value = 0
        self.assertEqual(
            stock_value,
            Decimal('0.00'),
            f"Expected stock value 0 but got {stock_value}. "
            f"Empty stock should return 0."
        )
        
        # Request dashboard (should not crash)
        url = reverse('verticals:clothing_dashboard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['inventory_value'], Decimal('0.00'))
    
    def test_inventory_metrics_function(self):
        """
        Test: clothing_inventory_metrics() returns all expected keys.
        
        This tests the full function used by the dashboard.
        """
        # Create stock
        MerchProduct.objects.create(
            business=self.business,
            name='Generic T-Shirt',
            kind=BusinessKind.CLOTHING,
            category='shirt',
            cost_price=Decimal('10000.00'),
            selling_price=Decimal('15000.00'),
            quantity_in_stock=5,
            is_active=True,
            is_archived=False,
        )
        
        # Call function
        metrics = clothing_inventory_metrics(self.business, location=self.location_main)
        
        # Assert: returns dict with expected keys
        self.assertIn('inventory_value', metrics)
        self.assertIn('retail_value', metrics)
        self.assertIn('expected_margin', metrics)
        
        # Assert: values are correct
        # inventory_value = 5 × 10000 = 50000
        # retail_value = 5 × 15000 = 75000
        # expected_margin = 75000 - 50000 = 25000
        self.assertEqual(metrics['inventory_value'], Decimal('50000.00'))
        self.assertEqual(metrics['retail_value'], Decimal('75000.00'))
        self.assertEqual(metrics['expected_margin'], Decimal('25000.00'))


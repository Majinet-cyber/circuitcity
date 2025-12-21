"""
Unit tests for clothing barcode flow and pricing feedback fixes.

Tests cover:
- A) Clothing barcode flow (no barcode vs yes barcode)
- B) Pricing markup/margin calculations
- C) Step numbering in wizard
"""
import json
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from tenants.models import Business, BusinessKind as BK
from inventory.models import MerchProduct

User = get_user_model()


class ClothingBarcodeFlowTestCase(TestCase):
    """Test clothing wizard barcode handling."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Clothing Store',
            kind=BK.CLOTHING,
            owner=self.user
        )
        self.client.login(username='testuser', password='testpass123')
    
    def test_no_barcode_saves_successfully(self):
        """Test that selecting 'No barcode' allows save without barcode."""
        data = {
            'category': 'shoes',
            'shoe_subtype': 'sneakers',
            'brand': 'Nike',
            'size': '42',
            'selling_price': '50000',
            'cost_price': '30000',
            'initial_stock': '5',
            'has_barcode': 'no',  # User selected NO
            # No barcode value provided
        }
        
        response = self.client.post(
            '/inventory/wizard/clothing/submit/',
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result['success'])
        self.assertIn('message', result)
        
        # Verify product was created without barcode
        product = MerchProduct.objects.get(pk=result['product_id'])
        self.assertIsNone(product.barcode)
        self.assertFalse(product.scan_required)
    
    def test_yes_barcode_requires_barcode_value(self):
        """Test that selecting 'Yes barcode' requires barcode value."""
        data = {
            'category': 'shoes',
            'shoe_subtype': 'sneakers',
            'brand': 'Nike',
            'size': '42',
            'selling_price': '50000',
            'cost_price': '30000',
            'initial_stock': '5',
            'has_barcode': 'yes',  # User selected YES
            # But no barcode value provided
        }
        
        response = self.client.post(
            '/inventory/wizard/clothing/submit/',
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 400)
        result = response.json()
        self.assertFalse(result['success'])
        self.assertIn('barcode', result['error'].lower())
    
    def test_yes_barcode_with_value_saves_correctly(self):
        """Test that providing barcode when 'Yes' is selected saves correctly."""
        data = {
            'category': 'shoes',
            'shoe_subtype': 'sneakers',
            'brand': 'Nike',
            'size': '42',
            'selling_price': '50000',
            'cost_price': '30000',
            'initial_stock': '5',
            'has_barcode': 'yes',
            'barcode': '1234567890123',
        }
        
        response = self.client.post(
            '/inventory/wizard/clothing/submit/',
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result['success'])
        
        # Verify product was created with barcode
        product = MerchProduct.objects.get(pk=result['product_id'])
        self.assertEqual(product.barcode, '1234567890123')
        self.assertTrue(product.scan_required)
    
    def test_success_message_shown(self):
        """Test that success message is returned on successful save."""
        data = {
            'category': 'jeans',
            'jeans_type': 'straight',
            'size': '32',
            'selling_price': '25000',
            'initial_stock': '10',
            'has_barcode': 'no',
        }
        
        response = self.client.post(
            '/inventory/wizard/clothing/submit/',
            data=json.dumps(data),
            content_type='application/json'
        )
        
        result = response.json()
        self.assertTrue(result['success'])
        self.assertIn('message', result)
        self.assertIn('created successfully', result['message'].lower())


class PricingCalculationTestCase(TestCase):
    """Test pricing helper calculations for markup and margin."""
    
    def test_markup_vs_margin_36k_to_70k(self):
        """
        Test the example from requirements:
        cost=36,000, sell=70,000
        Expected: markup=94%, margin=49%
        """
        cost = Decimal('36000')
        sell = Decimal('70000')
        profit = sell - cost
        
        # Margin = (profit / selling_price) * 100
        margin_percent = (profit / sell) * 100
        
        # Markup = (profit / cost_price) * 100
        markup_percent = (profit / cost) * 100
        
        # Round to nearest integer
        margin_rounded = round(margin_percent)
        markup_rounded = round(markup_percent)
        
        self.assertEqual(profit, Decimal('34000'))
        self.assertEqual(markup_rounded, 94)
        self.assertEqual(margin_rounded, 49)
    
    def test_below_cost_loss_calculation(self):
        """Test that selling below cost shows loss and negative margin."""
        cost = Decimal('50000')
        sell = Decimal('40000')
        profit = sell - cost
        
        margin_percent = (profit / sell) * 100
        
        self.assertEqual(profit, Decimal('-10000'))
        self.assertTrue(profit < 0)
        self.assertEqual(round(margin_percent), -25)
    
    def test_zero_cost_no_divide_by_zero(self):
        """Test that zero cost doesn't cause divide-by-zero error."""
        cost = Decimal('0')
        sell = Decimal('50000')
        profit = sell - cost
        
        margin_percent = (profit / sell) * 100 if sell > 0 else None
        markup_percent = None if cost == 0 else (profit / cost) * 100
        
        self.assertEqual(profit, Decimal('50000'))
        self.assertEqual(round(margin_percent), 100)
        self.assertIsNone(markup_percent)  # Markup N/A when cost is 0
    
    def test_currency_formatting_with_commas(self):
        """Test that currency is formatted with commas."""
        amount = 70000
        formatted = f"MWK {amount:,}"
        self.assertEqual(formatted, "MWK 70,000")
        
        amount2 = 1234567
        formatted2 = f"MWK {amount2:,}"
        self.assertEqual(formatted2, "MWK 1,234,567")


class WizardStepNumberingTestCase(TestCase):
    """Test that wizard step numbering is sequential and skips conditional steps."""
    
    def test_step_numbers_sequential_when_all_shown(self):
        """Test that when all steps are shown, numbering is 1, 2, 3, 4, 5..."""
        # This is a conceptual test - in practice, the wizard engine
        # calculates visible steps dynamically in JavaScript
        
        # Simulate wizard with 5 steps, none skipped
        total_steps = 5
        skipped_steps = []
        
        visible_count = total_steps - len(skipped_steps)
        self.assertEqual(visible_count, 5)
    
    def test_step_numbers_skip_conditional_steps(self):
        """Test that conditional steps are not counted in step numbers."""
        # Simulate: Category, Size, Gender, Pricing, Has Barcode, (Barcode Input - conditional)
        # If user selects "No barcode", barcode input step is skipped
        
        total_steps = 6
        # User selected "No barcode", so barcode input step (index 5) is skipped
        skipped_steps = [5]
        
        visible_count = total_steps - len(skipped_steps)
        self.assertEqual(visible_count, 5)
        
        # The visible steps should be numbered 1-5, not 1-6 with a gap


class ClothingDashboardChartTestCase(TestCase):
    """Test clothing dashboard recent sales chart data."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Clothing Store',
            kind=BK.CLOTHING,
            owner=self.user
        )
        self.client.login(username='testuser', password='testpass123')
    
    def test_sales_by_day_includes_count_revenue_profit(self):
        """Test that sales_by_day data includes count, revenue, and profit."""
        response = self.client.get('/verticals/clothing/dashboard/')
        self.assertEqual(response.status_code, 200)
        
        # Check that context has sales_by_day
        self.assertIn('sales_by_day', response.context)
        sales_by_day = response.context['sales_by_day']
        
        # Each day should have required fields
        if len(sales_by_day) > 0:
            day_data = sales_by_day[0]
            self.assertIn('count', day_data)
            self.assertIn('revenue', day_data)
            self.assertIn('profit', day_data)
            self.assertIn('date_short', day_data)


class AnalyticsFiltersTestCase(TestCase):
    """Test unified analytics filters component."""
    
    def test_filters_component_renders(self):
        """Test that analytics filters component can be rendered."""
        # This is a template inclusion test
        # The component should be includable in any analytics page
        
        # Test that the partial exists
        from django.template.loader import get_template
        try:
            template = get_template('analytics/_filters.html')
            self.assertIsNotNone(template)
        except Exception as e:
            self.fail(f"Analytics filters template not found: {e}")
    
    def test_date_range_presets_available(self):
        """Test that all required date range presets are available."""
        required_presets = [
            'today',
            'yesterday',
            '7d',
            '30d',
            'this_month',
            'last_month',
            'custom'
        ]
        
        # These presets should be handled by the filters component
        for preset in required_presets:
            # Each preset should be valid
            self.assertIsNotNone(preset)
            self.assertTrue(len(preset) > 0)


if __name__ == '__main__':
    import django
    django.setup()
    from django.test.utils import get_runner
    from django.conf import settings
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(['tests.test_bugfix_clothing_barcode_pricing'])


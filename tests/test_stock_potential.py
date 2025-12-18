# tests/test_stock_potential.py
"""
Regression tests for Stock Potential KPI - MUST NEVER GO NEGATIVE.

Ensures that Stock Potential = sum(max(0, selling_price - cost_price) * qty)
across all stock items, with proper handling of missing/null prices.
"""
import pytest
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from tenants.models import Business, Membership
from inventory.models import InventoryItem, Product, Location

User = get_user_model()


@pytest.mark.django_db
class TestStockPotentialNeverNegative(TestCase):
    """Test that Stock Potential KPI can never go negative."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create user
        self.user = User.objects.create_user(
            username="testmanager",
            email="manager@test.com",
            password="testpass123"
        )
        
        # Create business
        self.business = Business.objects.create(
            name="Test Phone Shop",
            slug="test-phone-shop",
            business_kind="phones"
        )
        
        # Create membership
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
            is_default=True
        )
        
        # Create product
        self.product = Product.objects.create(
            business=self.business,
            name="iPhone 13",
            code="IPHONE13"
        )
        
        # Login
        self.client.login(username="testmanager", password="testpass123")
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
    
    def test_stock_potential_with_normal_prices(self):
        """Test Stock Potential with normal profit margins."""
        # Create stock with profit
        for i in range(3):
            InventoryItem.objects.create(
                business=self.business,
                imei=f"11111111111111{i}",
                product=self.product,
                current_location=self.location,
                order_price=Decimal("400000.00"),  # Cost
                selling_price=Decimal("500000.00"),  # Selling
                status="IN_STOCK"
            )
        
        # Get dashboard
        from django.urls import reverse
        response = self.client.get(reverse('inventory_verticals:phones_dashboard'))
        
        # Extract stock potential
        dashboard_kpis = response.context.get('dashboard_kpis', {})
        stock_potential = dashboard_kpis.get('stock_potential_profit', Decimal('0'))
        
        # Expected: 3 items × (500k - 400k) = 300k
        expected = Decimal("300000.00")
        self.assertEqual(stock_potential, expected)
        self.assertGreaterEqual(stock_potential, Decimal('0'), 
                                "Stock Potential must never be negative")
    
    def test_stock_potential_with_zero_selling_price(self):
        """Test Stock Potential when selling price is not set (zero/null)."""
        # Create stock with missing selling prices
        for i in range(3):
            InventoryItem.objects.create(
                business=self.business,
                imei=f"22222222222222{i}",
                product=self.product,
                current_location=self.location,
                order_price=Decimal("400000.00"),
                selling_price=None,  # Not set!
                status="IN_STOCK"
            )
        
        # Get dashboard
        from django.urls import reverse
        response = self.client.get(reverse('inventory_verticals:phones_dashboard'))
        
        # Extract stock potential
        dashboard_kpis = response.context.get('dashboard_kpis', {})
        stock_potential = dashboard_kpis.get('stock_potential_profit', Decimal('0'))
        
        # With no selling prices set, potential should be 0 (not negative!)
        self.assertEqual(stock_potential, Decimal('0.00'))
        self.assertGreaterEqual(stock_potential, Decimal('0'), 
                                "Stock Potential must be >= 0 when prices missing")
    
    def test_stock_potential_with_selling_below_cost(self):
        """Test Stock Potential when selling price is below cost (loss scenario)."""
        # Create stock with losses (selling < cost)
        for i in range(3):
            InventoryItem.objects.create(
                business=self.business,
                imei=f"33333333333333{i}",
                product=self.product,
                current_location=self.location,
                order_price=Decimal("500000.00"),  # Cost
                selling_price=Decimal("400000.00"),  # Selling BELOW cost
                status="IN_STOCK"
            )
        
        # Get dashboard
        from django.urls import reverse
        response = self.client.get(reverse('inventory_verticals:phones_dashboard'))
        
        # Extract stock potential
        dashboard_kpis = response.context.get('dashboard_kpis', {})
        stock_potential = dashboard_kpis.get('stock_potential_profit', Decimal('0'))
        
        # Each item has -100k potential, but max(0, -100k) = 0
        # So total should be 0, NOT -300k
        self.assertEqual(stock_potential, Decimal('0.00'))
        self.assertGreaterEqual(stock_potential, Decimal('0'), 
                                "Stock Potential must never be negative (loss items contribute 0)")
    
    def test_stock_potential_with_mixed_scenarios(self):
        """Test Stock Potential with mix of profitable, loss, and missing prices."""
        # Profitable item
        InventoryItem.objects.create(
            business=self.business,
            imei="444444444444440",
            product=self.product,
            current_location=self.location,
            order_price=Decimal("400000.00"),
            selling_price=Decimal("500000.00"),  # +100k profit
            status="IN_STOCK"
        )
        
        # Loss item (should contribute 0)
        InventoryItem.objects.create(
            business=self.business,
            imei="444444444444441",
            product=self.product,
            current_location=self.location,
            order_price=Decimal("500000.00"),
            selling_price=Decimal("400000.00"),  # -100k loss → 0
            status="IN_STOCK"
        )
        
        # Missing price (should contribute 0)
        InventoryItem.objects.create(
            business=self.business,
            imei="444444444444442",
            product=self.product,
            current_location=self.location,
            order_price=Decimal("400000.00"),
            selling_price=None,  # Missing → 0
            status="IN_STOCK"
        )
        
        # Get dashboard
        from django.urls import reverse
        response = self.client.get(reverse('inventory_verticals:phones_dashboard'))
        
        # Extract stock potential
        dashboard_kpis = response.context.get('dashboard_kpis', {})
        stock_potential = dashboard_kpis.get('stock_potential_profit', Decimal('0'))
        
        # Only the profitable item contributes: 100k
        self.assertEqual(stock_potential, Decimal("100000.00"))
        self.assertGreaterEqual(stock_potential, Decimal('0'), 
                                "Stock Potential with mixed scenarios must be >= 0")
    
    def test_stock_potential_with_zero_cost(self):
        """Test Stock Potential when cost price is zero (edge case)."""
        # Create stock with zero cost
        InventoryItem.objects.create(
            business=self.business,
            imei="555555555555550",
            product=self.product,
            current_location=self.location,
            order_price=Decimal("0.00"),  # Zero cost
            selling_price=Decimal("500000.00"),
            status="IN_STOCK"
        )
        
        # Get dashboard
        from django.urls import reverse
        response = self.client.get(reverse('inventory_verticals:phones_dashboard'))
        
        # Extract stock potential
        dashboard_kpis = response.context.get('dashboard_kpis', {})
        stock_potential = dashboard_kpis.get('stock_potential_profit', Decimal('0'))
        
        # Potential = max(0, 500k - 0) = 500k
        self.assertEqual(stock_potential, Decimal("500000.00"))
        self.assertGreaterEqual(stock_potential, Decimal('0'), 
                                "Stock Potential with zero cost must be >= 0")
    
    def test_stock_potential_with_no_stock(self):
        """Test Stock Potential when there is no stock."""
        # No stock created
        
        # Get dashboard
        from django.urls import reverse
        response = self.client.get(reverse('inventory_verticals:phones_dashboard'))
        
        # Extract stock potential
        dashboard_kpis = response.context.get('dashboard_kpis', {})
        stock_potential = dashboard_kpis.get('stock_potential_profit', Decimal('0'))
        
        # With no stock, potential should be 0
        self.assertEqual(stock_potential, Decimal('0.00'))
        self.assertGreaterEqual(stock_potential, Decimal('0'), 
                                "Stock Potential with no stock must be 0")
    
    def test_stock_potential_formula_correctness(self):
        """Test that the formula is correct: sum(max(0, selling - cost))."""
        # Create various scenarios
        test_cases = [
            (Decimal("400000"), Decimal("500000"), Decimal("100000")),  # Profit
            (Decimal("500000"), Decimal("400000"), Decimal("0")),       # Loss → 0
            (Decimal("400000"), None, Decimal("0")),                    # No price → 0
            (Decimal("0"), Decimal("500000"), Decimal("500000")),       # Zero cost
            (Decimal("400000"), Decimal("400000"), Decimal("0")),       # Break-even
        ]
        
        for idx, (cost, selling, expected_contribution) in enumerate(test_cases):
            # Clear existing stock
            InventoryItem.objects.filter(business=self.business).delete()
            
            # Create single item
            InventoryItem.objects.create(
                business=self.business,
                imei=f"66666666666666{idx}",
                product=self.product,
                current_location=self.location,
                order_price=cost,
                selling_price=selling,
                status="IN_STOCK"
            )
            
            # Get dashboard
            from django.urls import reverse
            response = self.client.get(reverse('inventory_verticals:phones_dashboard'))
            
            # Extract stock potential
            dashboard_kpis = response.context.get('dashboard_kpis', {})
            stock_potential = dashboard_kpis.get('stock_potential_profit', Decimal('0'))
            
            # Verify
            self.assertEqual(stock_potential, expected_contribution, 
                            f"Case {idx}: cost={cost}, selling={selling}")
            self.assertGreaterEqual(stock_potential, Decimal('0'), 
                                   f"Case {idx} must be >= 0")


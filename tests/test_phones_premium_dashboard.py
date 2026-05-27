# tests/test_phones_premium_dashboard.py
"""
Tests for the premium PHONES dashboard with KPIs, business panel, and charts.
"""
import pytest
from decimal import Decimal
from datetime import timedelta

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.models import InventoryItem, Product, Location
from inventory.business_kinds import BusinessKind

User = get_user_model()


@pytest.mark.django_db
class TestPhonesPremiumDashboard(TestCase):
    """Test the premium PHONES dashboard KPIs and metrics"""
    
    def setUp(self):
        """Set up test data"""
        # Create business
        self.business = Business.objects.create(
            name="Test Phones Store",
            kind=BusinessKind.PHONES,
            is_active=True
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
            is_default=True
        )
        
        # Create manager
        self.manager = User.objects.create_user(
            username="manager@test.com",
            email="manager@test.com",
            password="testpass123"
        )
        
        # Create membership
        self.membership = Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="manager"
        )
        
        # Create agent
        self.agent = User.objects.create_user(
            username="agent@test.com",
            email="agent@test.com",
            password="testpass123"
        )
        
        Membership.objects.create(
            user=self.agent,
            business=self.business,
            role="agent"
        )
        
        # Create product
        self.product = Product.objects.create(
            code="TECNO_SPARK40_4_128",
            name="TECNO Spark 40",
            brand="TECNO",
            model="Spark 40",
            variant="4+128",
            cost_price=Decimal("450000.00"),
            sale_price=Decimal("550000.00")
        )
        
        self.client = Client()
    
    def test_dashboard_shows_today_kpis(self):
        """Test dashboard shows today's KPIs correctly"""
        # Create sales today
        now = timezone.now()
        for i in range(3):
            InventoryItem.objects.create(
                business=self.business,
                imei=f"12345678901234{i}",
                product=self.product,
                current_location=self.location,
                assigned_agent=self.agent,
                order_price=Decimal("450000.00"),
                selling_price=Decimal("550000.00"),
                status="SOLD",
                sold_at=now
            )
        
        # Login and access dashboard
        self.client.login(username="manager@test.com", password="testpass123")
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get(reverse('inventory:inventory_dashboard'))
        
        # Should return 200
        self.assertEqual(response.status_code, 200)
        
        # Check context has phones_kpis
        self.assertIn('phones_kpis', response.context)
        
        kpis = response.context['phones_kpis']
        
        # Today's KPIs
        self.assertEqual(kpis['today']['units'], 3)
        self.assertEqual(kpis['today']['revenue'], Decimal("1650000.00"))  # 3 × 550,000
        self.assertEqual(kpis['today']['gross_profit'], Decimal("300000.00"))  # 3 × (550k - 450k)
    
    def test_dashboard_shows_7_day_kpis(self):
        """Test dashboard shows last 7 days KPIs correctly"""
        now = timezone.now()
        
        # Create sales over last 7 days
        for day in range(7):
            sale_date = now - timedelta(days=day)
            for i in range(2):  # 2 sales per day
                InventoryItem.objects.create(
                    business=self.business,
                    imei=f"1234567890{day:02d}{i:02d}0",
                    product=self.product,
                    current_location=self.location,
                    assigned_agent=self.agent,
                    order_price=Decimal("450000.00"),
                    selling_price=Decimal("550000.00"),
                    status="SOLD",
                    sold_at=sale_date
                )
        
        # Login
        self.client.login(username="manager@test.com", password="testpass123")
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get(reverse('inventory:inventory_dashboard'))
        
        kpis = response.context['phones_kpis']
        
        # Last 7 days KPIs
        self.assertEqual(kpis['last_7_days']['units'], 14)  # 7 days × 2 sales
        self.assertEqual(kpis['last_7_days']['revenue'], Decimal("7700000.00"))  # 14 × 550k
    
    def test_dashboard_shows_stock_on_hand(self):
        """Test dashboard shows stock on hand correctly"""
        # Create stock items (IN_STOCK)
        for i in range(5):
            InventoryItem.objects.create(
                business=self.business,
                imei=f"99999999999999{i}",
                product=self.product,
                current_location=self.location,
                order_price=Decimal("450000.00"),
                selling_price=Decimal("550000.00"),
                status="IN_STOCK"
            )
        
        # Login
        self.client.login(username="manager@test.com", password="testpass123")
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get(reverse('inventory:inventory_dashboard'))
        
        kpis = response.context['phones_kpis']
        
        # Stock KPIs
        self.assertEqual(kpis['stock']['units'], 5)
        self.assertEqual(kpis['stock']['cost_value'], Decimal("2250000.00"))  # 5 × 450k
        self.assertEqual(kpis['stock']['selling_value'], Decimal("2750000.00"))  # 5 × 550k
        self.assertEqual(kpis['stock']['potential_profit'], Decimal("500000.00"))  # 5 × 100k
    
    def test_dashboard_shows_business_panel_metrics(self):
        """Test dashboard shows business panel metrics"""
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Create MTD sales
        for i in range(10):
            InventoryItem.objects.create(
                business=self.business,
                imei=f"88888888888888{i:02d}",
                product=self.product,
                current_location=self.location,
                assigned_agent=self.agent,
                order_price=Decimal("450000.00"),
                selling_price=Decimal("550000.00"),
                status="SOLD",
                sold_at=month_start + timedelta(days=i)
            )
        
        # Create stock
        for i in range(5):
            InventoryItem.objects.create(
                business=self.business,
                imei=f"77777777777777{i:02d}",
                product=self.product,
                current_location=self.location,
                order_price=Decimal("450000.00"),
                selling_price=Decimal("550000.00"),
                status="IN_STOCK"
            )
        
        # Login
        self.client.login(username="manager@test.com", password="testpass123")
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get(reverse('inventory:inventory_dashboard'))
        
        business_panel = response.context['business_panel']
        
        # Average selling price
        self.assertEqual(business_panel['avg_selling_price_mtd'], Decimal("550000.00"))
        
        # Average gross profit
        self.assertEqual(business_panel['avg_gross_profit_mtd'], Decimal("100000.00"))
        
        # Sell-through rate: 10 sold / (10 sold + 5 in stock) = 66%
        self.assertEqual(business_panel['sell_through_rate'], 66)
        self.assertEqual(business_panel['sell_through_hint'], "Okay")
    
    def test_dashboard_shows_fast_moving_models(self):
        """Test dashboard shows fast-moving models correctly"""
        now = timezone.now()
        last_30_days = now - timedelta(days=30)
        
        # Create another product
        product2 = Product.objects.create(
            code="ITEL_A90_3_128",
            name="ITEL A90",
            brand="ITEL",
            model="A90",
            variant="3+128",
            cost_price=Decimal("350000.00"),
            sale_price=Decimal("450000.00")
        )
        
        # Create sales for product 1 (more popular)
        for i in range(8):
            InventoryItem.objects.create(
                business=self.business,
                imei=f"11111111111111{i:02d}",
                product=self.product,
                current_location=self.location,
                assigned_agent=self.agent,
                order_price=Decimal("450000.00"),
                selling_price=Decimal("550000.00"),
                status="SOLD",
                sold_at=last_30_days + timedelta(days=i)
            )
        
        # Create sales for product 2 (less popular)
        for i in range(3):
            InventoryItem.objects.create(
                business=self.business,
                imei=f"22222222222222{i:02d}",
                product=product2,
                current_location=self.location,
                assigned_agent=self.agent,
                order_price=Decimal("350000.00"),
                selling_price=Decimal("450000.00"),
                status="SOLD",
                sold_at=last_30_days + timedelta(days=i)
            )
        
        # Login
        self.client.login(username="manager@test.com", password="testpass123")
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get(reverse('inventory:inventory_dashboard'))
        
        fast_models = response.context['fast_models_30d']
        
        # Should have 2 models
        self.assertEqual(len(fast_models), 2)
        
        # First model should be TECNO Spark 40 (8 units)
        self.assertEqual(fast_models[0]['brand'], "TECNO")
        self.assertEqual(fast_models[0]['model'], "Spark 40")
        self.assertEqual(fast_models[0]['units'], 8)
        
        # Second model should be ITEL A90 (3 units)
        self.assertEqual(fast_models[1]['brand'], "ITEL")
        self.assertEqual(fast_models[1]['model'], "A90")
        self.assertEqual(fast_models[1]['units'], 3)
    
    def test_dashboard_shows_top_agents(self):
        """Test dashboard shows top agents correctly"""
        now = timezone.now()
        last_30_days = now - timedelta(days=30)
        
        # Create another agent
        agent2 = User.objects.create_user(
            username="agent2@test.com",
            email="agent2@test.com",
            password="testpass123"
        )
        
        Membership.objects.create(
            user=agent2,
            business=self.business,
            role="agent"
        )
        
        # Agent 1 sells more
        for i in range(10):
            InventoryItem.objects.create(
                business=self.business,
                imei=f"33333333333333{i:02d}",
                product=self.product,
                current_location=self.location,
                assigned_agent=self.agent,
                order_price=Decimal("450000.00"),
                selling_price=Decimal("550000.00"),
                status="SOLD",
                sold_at=last_30_days + timedelta(days=i)
            )
        
        # Agent 2 sells less
        for i in range(5):
            InventoryItem.objects.create(
                business=self.business,
                imei=f"44444444444444{i:02d}",
                product=self.product,
                current_location=self.location,
                assigned_agent=agent2,
                order_price=Decimal("450000.00"),
                selling_price=Decimal("550000.00"),
                status="SOLD",
                sold_at=last_30_days + timedelta(days=i)
            )
        
        # Login
        self.client.login(username="manager@test.com", password="testpass123")
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get(reverse('inventory:inventory_dashboard'))
        
        fast_agents = response.context['fast_agents_30d']
        
        # Should have 2 agents
        self.assertEqual(len(fast_agents), 2)
        
        # First agent should have more revenue
        self.assertEqual(fast_agents[0]['units'], 10)
        self.assertEqual(fast_agents[0]['revenue'], Decimal("5500000.00"))
        
        # Second agent should have less revenue
        self.assertEqual(fast_agents[1]['units'], 5)
        self.assertEqual(fast_agents[1]['revenue'], Decimal("2750000.00"))


@pytest.mark.django_db
def test_phones_sidebar_includes_scan_and_sell():
    """
    Test that PHONES vertical sidebar includes "Scan & Sell" link to phone sale wizard.
    """
    from inventory.utils_verticals import get_vertical_sidebar_items
    
    # Get PHONES sidebar items
    sidebar_items = get_vertical_sidebar_items("phones")
    
    # Find the Scan & Sell item
    scan_sell_item = next(
        (item for item in sidebar_items if "Scan & Sell" in item.get("label", "")),
        None
    )
    
    # Should exist
    assert scan_sell_item is not None, "Scan & Sell should be in PHONES sidebar"
    
    # Should point to phone_sale_wizard
    assert scan_sell_item["url"] == "inventory:phone_sale_wizard"
    
    # Should be in MAIN section
    assert scan_sell_item["section"] == "MAIN"
    
    # Should not require manager
    assert scan_sell_item.get("require_manager", False) is False


@pytest.mark.django_db
def test_phone_sale_wizard_url_resolves(client, django_user_model):
    """
    Test that the phone sale wizard URL is accessible.
    """
    # Create business
    business = Business.objects.create(
        name="Test Phones Wizard",
        kind=BusinessKind.PHONES,
        is_active=True
    )
    
    # Create location
    Location.objects.create(
        business=business,
        name="Wizard Store",
        is_default=True
    )
    
    # Create user
    user = django_user_model.objects.create_user(
        username="wizard_user",
        password="wizard_pass",
        email="wizard@test.com",
    )
    Membership.objects.create(
        user=user,
        business=business,
        role="MANAGER",
        status="ACTIVE"
    )
    
    # Login and activate business
    client.login(username="wizard_user", password="wizard_pass")
    session = client.session
    session["active_business_id"] = business.id
    session.save()
    
    # Hit phone sale wizard URL
    response = client.get(reverse("inventory:phone_sale_wizard"))
    
    # Should return 200 (page exists)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

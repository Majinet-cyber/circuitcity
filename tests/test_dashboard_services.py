"""
Tests for inventory/dashboard_services.py shared dashboard helpers.

These functions are used across multiple dashboards to provide
consistent metrics and alerts.
"""
import pytest
from decimal import Decimal
from datetime import timedelta

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from inventory.models import InventoryItem, Product, Location
from inventory.dashboard_services import (
    get_stock_alerts,
    get_cfo_alerts,
    get_ai_insights,
    get_revenue_profit_summary,
    get_stock_battery,
)
from tenants.models import Business

User = get_user_model()


class DashboardServicesTestCase(TestCase):
    """Test dashboard_services.py helper functions"""
    
    def setUp(self):
        """Create test business, location, and products"""
        # Create business
        self.business = Business.objects.create(
            name="Test Services Store",
            business_kind="phones",
            slug="test-services-store",
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
            is_default=True,
        )
        
        # Create products
        self.product_high_stock = Product.objects.create(
            code="HIGH-001",
            brand="TECNO",
            model="Spark 40",
            variant="4+128",
            cost_price=50000,
            sale_price=75000,
            low_stock_threshold=10,
        )
        
        self.product_low_stock = Product.objects.create(
            code="LOW-001",
            brand="ITEL",
            model="A70",
            variant="3+32",
            cost_price=30000,
            sale_price=45000,
            low_stock_threshold=5,
        )
        
        self.product_out_of_stock = Product.objects.create(
            code="OUT-001",
            brand="SAMSUNG",
            model="A15",
            variant="4+64",
            cost_price=60000,
            sale_price=80000,
            low_stock_threshold=3,
        )
    
    def test_get_stock_alerts_returns_low_stock_items(self):
        """Test that stock alerts identify low-stock products"""
        # Create inventory: high stock (15), low stock (3), out of stock (0)
        for i in range(15):
            InventoryItem.objects.create(
                business=self.business,
                product=self.product_high_stock,
                current_location=self.location,
                imei=f"11111111111111{i}",
                order_price=50000,
                status="IN_STOCK",
            )
        
        for i in range(3):
            InventoryItem.objects.create(
                business=self.business,
                product=self.product_low_stock,
                current_location=self.location,
                imei=f"22222222222222{i}",
                order_price=30000,
                status="IN_STOCK",
            )
        
        # product_out_of_stock has 0 items (no inventory created)
        
        # Get alerts
        alerts = get_stock_alerts(self.business, self.location)
        
        # Should have 2 alerts (low stock + out of stock)
        self.assertGreaterEqual(len(alerts), 2)
        
        # Find the alerts by product
        low_alert = next((a for a in alerts if "A70" in a["product_name"]), None)
        out_alert = next((a for a in alerts if "A15" in a["product_name"]), None)
        
        # Low stock alert
        self.assertIsNotNone(low_alert)
        self.assertEqual(low_alert["on_hand"], 3)
        self.assertEqual(low_alert["severity"], "warning")
        
        # Out of stock alert
        self.assertIsNotNone(out_alert)
        self.assertEqual(out_alert["on_hand"], 0)
        self.assertEqual(out_alert["severity"], "critical")
    
    def test_get_cfo_alerts_predicts_stockouts(self):
        """Test that CFO alerts predict stockouts based on run-rate"""
        # Create stock
        for i in range(10):
            InventoryItem.objects.create(
                business=self.business,
                product=self.product_low_stock,
                current_location=self.location,
                imei=f"33333333333333{i}",
                order_price=30000,
                status="IN_STOCK",
            )
        
        # Create recent sales (simulate high demand)
        now = timezone.now()
        for i in range(20):
            sold_item = InventoryItem.objects.create(
                business=self.business,
                product=self.product_low_stock,
                current_location=self.location,
                imei=f"44444444444444{i}",
                order_price=30000,
                selling_price=45000,
                status="SOLD",
                sold_at=now - timedelta(days=i % 10),  # Sold in last 10 days
            )
        
        # Get alerts
        alerts = get_cfo_alerts(self.business, self.location)
        
        # Should have at least one alert
        self.assertGreater(len(alerts), 0)
        
        # Find stockout prediction
        stockout_alert = next((a for a in alerts if "A70" in a.get("message", "")), None)
        
        # Should predict stockout
        if stockout_alert:
            self.assertIn(stockout_alert["severity"], ["high", "medium"])
            self.assertEqual(stockout_alert["category"], "stock")
    
    def test_get_ai_insights_identifies_fast_movers(self):
        """Test that AI insights identify fast-moving products"""
        now = timezone.now()
        
        # Create fast-moving product sales (20 units in last 30 days)
        for i in range(20):
            InventoryItem.objects.create(
                business=self.business,
                product=self.product_high_stock,
                current_location=self.location,
                imei=f"55555555555555{i}",
                order_price=50000,
                selling_price=75000,
                status="SOLD",
                sold_at=now - timedelta(days=i),
            )
        
        # Create slow-moving product (stock but no sales)
        for i in range(5):
            InventoryItem.objects.create(
                business=self.business,
                product=self.product_low_stock,
                current_location=self.location,
                imei=f"66666666666666{i}",
                order_price=30000,
                status="IN_STOCK",
            )
        
        # Get insights
        insights = get_ai_insights(self.business, self.location)
        
        # Should have fast movers
        self.assertGreater(len(insights["fast_movers"]), 0)
        
        # Top fast mover should be product_high_stock
        top_mover = insights["fast_movers"][0]
        self.assertIn("Spark 40", top_mover["product_name"])
        self.assertEqual(top_mover["units_sold"], 20)
        
        # Should have slow movers
        self.assertGreater(len(insights["slow_movers"]), 0)
        
        # Slow mover should be product_low_stock
        slow_mover = next((s for s in insights["slow_movers"] if "A70" in s["product_name"]), None)
        self.assertIsNotNone(slow_mover)
        self.assertEqual(slow_mover["on_hand"], 5)
        
        # Should have recommendations
        self.assertGreater(len(insights["recommendations"]), 0)
    
    def test_get_revenue_profit_summary_this_month(self):
        """Test revenue/profit summary calculation for current month"""
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Create sales this month
        for i in range(10):
            InventoryItem.objects.create(
                business=self.business,
                product=self.product_high_stock,
                current_location=self.location,
                imei=f"77777777777777{i}",
                order_price=50000,
                selling_price=75000,
                status="SOLD",
                sold_at=month_start + timedelta(days=i),
            )
        
        # Get summary
        summary = get_revenue_profit_summary(self.business, self.location, period="this_month")
        
        # Verify calculations
        self.assertEqual(summary["units_sold"], 10)
        self.assertEqual(summary["revenue"], Decimal("750000.00"))
        self.assertEqual(summary["cost"], Decimal("500000.00"))
        self.assertEqual(summary["profit"], Decimal("250000.00"))
        self.assertEqual(summary["profit_margin"], 33)  # (250k/750k) * 100 = 33%
        self.assertEqual(summary["period_label"], "This Month")
    
    def test_get_revenue_profit_summary_today(self):
        """Test revenue/profit summary for today only"""
        now = timezone.now()
        
        # Create sales today
        for i in range(3):
            InventoryItem.objects.create(
                business=self.business,
                product=self.product_high_stock,
                current_location=self.location,
                imei=f"88888888888888{i}",
                order_price=50000,
                selling_price=75000,
                status="SOLD",
                sold_at=now,
            )
        
        # Get summary
        summary = get_revenue_profit_summary(self.business, self.location, period="today")
        
        # Verify
        self.assertEqual(summary["units_sold"], 3)
        self.assertEqual(summary["revenue"], Decimal("225000.00"))
        self.assertEqual(summary["period_label"], "Today")
    
    def test_get_stock_battery_levels(self):
        """Test stock battery health indicator"""
        # Test empty stock (level = 0, color = red)
        battery_empty = get_stock_battery(self.business, self.location)
        self.assertEqual(battery_empty["level"], 0)
        self.assertEqual(battery_empty["color"], "red")
        self.assertEqual(battery_empty["units_on_hand"], 0)
        
        # Create low stock (20 units -> yellow)
        for i in range(20):
            InventoryItem.objects.create(
                business=self.business,
                product=self.product_high_stock,
                current_location=self.location,
                imei=f"99999999999999{i}",
                order_price=50000,
                status="IN_STOCK",
            )
        
        battery_low = get_stock_battery(self.business, self.location)
        self.assertEqual(battery_low["units_on_hand"], 20)
        self.assertEqual(battery_low["color"], "yellow")
        self.assertGreater(battery_low["level"], 0)
        
        # Add more stock (100+ units -> green)
        for i in range(100):
            InventoryItem.objects.create(
                business=self.business,
                product=self.product_low_stock,
                current_location=self.location,
                imei=f"10000000000000{i:03d}",
                order_price=30000,
                status="IN_STOCK",
            )
        
        battery_healthy = get_stock_battery(self.business, self.location)
        self.assertEqual(battery_healthy["units_on_hand"], 120)
        self.assertEqual(battery_healthy["color"], "green")
        self.assertEqual(battery_healthy["level"], 100)
    
    def test_functions_handle_none_business_gracefully(self):
        """Test that all functions handle None business without crashing"""
        # Should return empty/default values, not crash
        self.assertEqual(get_stock_alerts(None), [])
        self.assertEqual(get_cfo_alerts(None), [])
        
        insights = get_ai_insights(None)
        self.assertEqual(insights["fast_movers"], [])
        self.assertEqual(insights["slow_movers"], [])
        
        summary = get_revenue_profit_summary(None)
        self.assertEqual(summary["revenue"], Decimal("0.00"))
        
        battery = get_stock_battery(None)
        self.assertEqual(battery["level"], 0)


@pytest.mark.django_db
def test_dashboard_services_integration():
    """
    Integration test: Ensure all dashboard services work together.
    """
    # Create test data
    business = Business.objects.create(
        name="Integration Test Store",
        business_kind="phones",
        slug="integration-test",
    )
    
    location = Location.objects.create(
        business=business,
        name="Test Location",
        is_default=True,
    )
    
    product = Product.objects.create(
        code="INT-001",
        brand="TEST",
        model="Model X",
        variant="1+1",
        cost_price=10000,
        sale_price=15000,
    )
    
    # Create some stock
    for i in range(5):
        InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location,
            imei=f"10101010101010{i}",
            order_price=10000,
            status="IN_STOCK",
        )
    
    # Call all services (should not crash)
    alerts = get_stock_alerts(business, location)
    assert isinstance(alerts, list)
    
    cfo = get_cfo_alerts(business, location)
    assert isinstance(cfo, list)
    
    insights = get_ai_insights(business, location)
    assert "fast_movers" in insights
    
    summary = get_revenue_profit_summary(business, location)
    assert "revenue" in summary
    
    battery = get_stock_battery(business, location)
    assert "level" in battery
    assert battery["units_on_hand"] == 5


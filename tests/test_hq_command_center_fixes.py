# tests/test_hq_command_center_fixes.py
"""
Tests for HQ Command Center fixes:
1. Sale scoping through location__business (no direct business field)
2. InventoryItem archived filtering through archived_at (no archived boolean)
"""
from decimal import Decimal
from datetime import timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model

from tenants.models import Business, Membership
from inventory.models import Location, Product, InventoryItem
from sales.models import Sale

User = get_user_model()


class HQCommandCenterFixesTestCase(TestCase):
    """Test HQ Command Center business detail page fixes."""

    def setUp(self):
        """Set up test data."""
        # Create HQ admin user
        self.hq_admin = User.objects.create_user(
            username="hqadmin",
            email="hqadmin@test.com",
            password="testpass123"
        )
        # Mark as HQ admin (assuming you have a Profile or permission system)
        # Adjust this based on your actual HQ admin setup
        self.hq_admin.is_staff = True
        self.hq_admin.is_superuser = True
        self.hq_admin.save()
        
        # Create test business
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-business",
        )
        
        # Create location for the business
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
            city="Test City"
        )
        
        # Create another business for cross-business leak testing
        self.other_business = Business.objects.create(
            name="Other Business",
            slug="other-business",
        )
        self.other_location = Location.objects.create(
            business=self.other_business,
            name="Other Store",
            city="Other City"
        )
        
        # Create a test agent
        self.agent = User.objects.create_user(
            username="testagent",
            email="agent@test.com",
            password="testpass123"
        )
        Membership.objects.create(
            business=self.business,
            user=self.agent,
            role="AGENT",
            location=self.location  # Agents require a location
        )
        
        # Create test product
        self.product = Product.objects.create(
            code="TEST-PROD-001",
            brand="TestBrand",
            model="TestModel",
            variant="Test Variant"
        )
        
        self.client = Client()
        self.client.force_login(self.hq_admin)

    def test_command_center_loads_successfully(self):
        """Test that command center page loads without 500 error."""
        url = reverse("hq:business_command_center", kwargs={"business_id": self.business.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn("business", response.context)
        self.assertEqual(response.context["business"].id, self.business.id)

    def test_archived_items_excluded_from_stock_count(self):
        """Test that archived items (archived_at set) are excluded from counts."""
        # Create active inventory item
        active_item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            order_price=Decimal("1000"),
            status="IN_STOCK",
            archived_at=None  # Not archived
        )
        
        # Create archived inventory item
        archived_item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            order_price=Decimal("1000"),
            status="IN_STOCK",
            archived_at=timezone.now(),  # Archived
            archived_by=self.hq_admin
        )
        
        url = reverse("hq:business_command_center", kwargs={"business_id": self.business.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Stock count should only include active items
        stock_count = response.context.get("stock_count", 0)
        self.assertEqual(stock_count, 1, "Stock count should exclude archived items")
        
        # Navigate to data tab to check archived count
        response = self.client.get(url + "?tab=data")
        self.assertEqual(response.status_code, 200)
        
        archived_count = response.context.get("archived_count", 0)
        self.assertEqual(archived_count, 1, "Archived count should be 1")

    def test_sales_scoped_through_location_business(self):
        """Test that sales are correctly scoped through location__business."""
        # Create inventory item for this business
        item1 = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            order_price=Decimal("1000"),
            status="SOLD"
        )
        
        # Create sale for this business
        sale1 = Sale.objects.create(
            item=item1,
            agent=self.agent,
            location=self.location,
            sold_at=timezone.now().date(),
            price=Decimal("1500"),
            commission_pct=Decimal("10")
        )
        
        # Create inventory item for OTHER business
        other_agent = User.objects.create_user(
            username="otheragent",
            email="otheragent@test.com",
            password="testpass123"
        )
        Membership.objects.create(
            business=self.other_business,
            user=other_agent,
            role="AGENT",
            location=self.other_location  # Agents require a location
        )
        
        other_item = InventoryItem.objects.create(
            business=self.other_business,
            product=self.product,
            current_location=self.other_location,
            order_price=Decimal("1000"),
            status="SOLD"
        )
        
        # Create sale for OTHER business
        sale2 = Sale.objects.create(
            item=other_item,
            agent=other_agent,
            location=self.other_location,
            sold_at=timezone.now().date(),
            price=Decimal("2000"),
            commission_pct=Decimal("10")
        )
        
        # Load command center for first business
        url = reverse("hq:business_command_center", kwargs={"business_id": self.business.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Should only count sales from this business
        sales_count_30d = response.context.get("sales_count_30d", 0)
        self.assertEqual(sales_count_30d, 1, "Should only count sales from this business")
        
        sales_total_30d = response.context.get("sales_total_30d", Decimal("0"))
        self.assertEqual(sales_total_30d, Decimal("1500"), "Should only sum sales from this business")

    def test_sales_tab_no_cross_business_leakage(self):
        """Test sales tab shows only sales from the correct business."""
        # Create sale for this business
        item1 = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            order_price=Decimal("1000"),
            status="SOLD"
        )
        sale1 = Sale.objects.create(
            item=item1,
            agent=self.agent,
            location=self.location,
            sold_at=timezone.now().date(),
            price=Decimal("1500")
        )
        
        # Create sale for other business
        other_agent = User.objects.create_user(
            username="otheragent2",
            email="otheragent2@test.com",
            password="testpass123"
        )
        Membership.objects.create(
            business=self.other_business,
            user=other_agent,
            role="AGENT",
            location=self.other_location  # Agents require a location
        )
        other_item = InventoryItem.objects.create(
            business=self.other_business,
            product=self.product,
            current_location=self.other_location,
            order_price=Decimal("1000"),
            status="SOLD"
        )
        sale2 = Sale.objects.create(
            item=other_item,
            agent=other_agent,
            location=self.other_location,
            sold_at=timezone.now().date(),
            price=Decimal("2000")
        )
        
        # Load sales tab
        url = reverse("hq:business_command_center", kwargs={"business_id": self.business.id})
        response = self.client.get(url + "?tab=sales")
        
        self.assertEqual(response.status_code, 200)
        
        recent_sales = response.context.get("recent_sales", [])
        self.assertEqual(len(recent_sales), 1, "Should only show sales from this business")
        self.assertEqual(recent_sales[0].id, sale1.id)

    def test_overview_tab_with_recent_archived_items(self):
        """Test overview shows correct counts when items are recently archived."""
        # Create items from last 7 days
        for i in range(3):
            InventoryItem.objects.create(
                business=self.business,
                product=self.product,
                current_location=self.location,
                order_price=Decimal("1000"),
                status="IN_STOCK",
                created_at=timezone.now() - timedelta(days=i),
                archived_at=None
            )
        
        # Create one archived item from last 7 days
        InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            order_price=Decimal("1000"),
            status="IN_STOCK",
            created_at=timezone.now() - timedelta(days=2),
            archived_at=timezone.now()  # Archived
        )
        
        url = reverse("hq:business_command_center", kwargs={"business_id": self.business.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # stock_in_7d should exclude archived items
        stock_in_7d = response.context.get("stock_in_7d", 0)
        self.assertEqual(stock_in_7d, 3, "Should only count non-archived items from last 7 days")

    def test_all_tabs_load_successfully(self):
        """Test that all tabs load without errors."""
        tabs = ["overview", "subscription", "users", "data", "sales", "health", "tickets", "audit"]
        
        for tab in tabs:
            url = reverse("hq:business_command_center", kwargs={"business_id": self.business.id})
            response = self.client.get(url + f"?tab={tab}")
            
            self.assertEqual(
                response.status_code, 200,
                f"Tab '{tab}' should load successfully"
            )
            self.assertEqual(response.context.get("active_tab"), tab)


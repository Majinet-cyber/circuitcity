"""
Test that Cement vertical UI elements are actually visible in rendered HTML.
This ensures sidebar, mobile nav, and premium features are not just "implemented" but actually render.
"""
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from inventory.business_kinds import BusinessKind
from inventory.mobile_nav import get_mobile_nav_items
from inventory.models import Business
from inventory.utils_verticals import get_vertical_sidebar_items

User = get_user_model()


class CementUIPresenceTest(TestCase):
    """Verify Cement UI elements are present in rendered HTML"""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="cementuser", email="cement@test.com", password="testpass123")
        self.business = Business.objects.create(
            name="Test Cement Store",
            business_kind=BusinessKind.CEMENT,
            owner=self.user,
        )

    def test_cement_sidebar_items_present(self):
        """Cement sidebar must include Stock In, Sell, Costs, Admin Wallet, Analytics, Locations"""
        items = get_vertical_sidebar_items(BusinessKind.CEMENT)

        self.assertGreater(len(items), 0, "Cement should have sidebar items")

        keys = [item["key"] for item in items]
        labels = [item["label"] for item in items]

        # Required MAIN section items
        self.assertIn("dashboard", keys, "Cement sidebar must have Dashboard")
        self.assertIn("stock_in", keys, "Cement sidebar must have Stock In")
        self.assertIn("sell", keys, "Cement sidebar must have Sell")
        self.assertIn("costs", keys, "Cement sidebar must have Costs")
        self.assertIn("admin_wallet", keys, "Cement sidebar must have Admin Wallet")
        self.assertIn("analytics", keys, "Cement sidebar must have Analytics")
        self.assertIn("locations", keys, "Cement sidebar must have Locations")

        # Verify labels match expected text
        self.assertIn("Stock In", labels)
        self.assertIn("Sell", labels)
        self.assertIn("Costs", labels)
        self.assertIn("Admin Wallet", labels)
        self.assertIn("Analytics", labels)
        self.assertIn("Locations", labels)

    def test_cement_mobile_nav_items_present(self):
        """Cement mobile nav must include Home, Stock In, Sell, Products, More"""
        request = self.factory.get("/")
        request.user = self.user
        request.business = self.business

        items = get_mobile_nav_items(request)

        self.assertGreater(len(items), 0, "Cement should have mobile nav items")

        keys = [item["key"] for item in items]
        labels = [item["label"] for item in items]

        # Required mobile nav items
        self.assertIn("home", keys, "Cement mobile nav must have Home")
        self.assertIn("stock_in", keys, "Cement mobile nav must have Stock In")
        self.assertIn("sell", keys, "Cement mobile nav must have Sell")
        self.assertIn("products", keys, "Cement mobile nav must have Products")
        self.assertIn("menu", keys, "Cement mobile nav must have More/Menu")

        # Verify labels
        self.assertIn("Home", labels)
        self.assertIn("Stock In", labels)
        self.assertIn("Sell", labels)
        self.assertIn("Products", labels)
        self.assertIn("More", labels)

    def test_cement_dashboard_renders_with_sidebar(self):
        """Cement dashboard page must render with sidebar items in context"""
        self.client.force_login(self.user)

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        response = self.client.get("/verticals/cement/dashboard/")

        self.assertEqual(response.status_code, 200, "Cement dashboard should load")

        # Check context has sidebar items
        self.assertIn("sidebar_items", response.context, "Context must include sidebar_items")
        sidebar_items = response.context["sidebar_items"]
        self.assertGreater(len(sidebar_items), 0, "Sidebar items should not be empty")

        # Check HTML contains sidebar nav items
        html = response.content.decode("utf-8")
        self.assertIn("Stock In", html, "HTML must contain 'Stock In' nav item")
        self.assertIn("Sell", html, "HTML must contain 'Sell' nav item")
        self.assertIn("Costs", html, "HTML must contain 'Costs' nav item")
        self.assertIn("Analytics", html, "HTML must contain 'Analytics' nav item")

    def test_cement_dashboard_has_premium_header(self):
        """Cement dashboard must show premium header with business name and greeting"""
        self.client.force_login(self.user)

        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        response = self.client.get("/verticals/cement/dashboard/")
        html = response.content.decode("utf-8")

        # Premium header should include business name
        self.assertIn(self.business.name, html, "Dashboard must show business name")

        # Check for greeting context variables (if helpers available)
        if "DASHBOARD_GREETING" in response.context:
            self.assertIsNotNone(response.context["DASHBOARD_GREETING"])

    def test_cement_dashboard_has_date_filters(self):
        """Cement dashboard must show date filter UI (Today, Last 7 Days, MTD, etc.)"""
        self.client.force_login(self.user)

        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        response = self.client.get("/verticals/cement/dashboard/")
        html = response.content.decode("utf-8")

        # Date filter chips should be present
        self.assertIn("Today", html, "Dashboard must have 'Today' filter")
        self.assertIn("Last 7 Days", html, "Dashboard must have 'Last 7 Days' filter")
        self.assertIn("Custom", html, "Dashboard must have 'Custom' date filter")

    def test_cement_dashboard_has_kpi_cards(self):
        """Cement dashboard must show KPI cards (Revenue, Profit, Stock Value, Costs)"""
        self.client.force_login(self.user)

        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        response = self.client.get("/verticals/cement/dashboard/")
        html = response.content.decode("utf-8")

        # KPI labels should be present
        self.assertIn("Revenue", html, "Dashboard must show Revenue KPI")
        self.assertIn("Profit", html, "Dashboard must show Profit KPI")
        self.assertIn("Stock Value", html, "Dashboard must show Stock Value KPI")
        self.assertIn("Costs", html, "Dashboard must show Costs KPI")

    def test_cement_dashboard_has_payment_mix(self):
        """Cement dashboard must show Payment Mix section"""
        self.client.force_login(self.user)

        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        response = self.client.get("/verticals/cement/dashboard/")
        html = response.content.decode("utf-8")

        self.assertIn("Payment Mix", html, "Dashboard must show Payment Mix section")

    def test_cement_dashboard_has_top_products(self):
        """Cement dashboard must show Top Products section"""
        self.client.force_login(self.user)

        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        response = self.client.get("/verticals/cement/dashboard/")
        html = response.content.decode("utf-8")

        self.assertIn("Top Products", html, "Dashboard must show Top Products section")

    def test_cement_dashboard_has_low_stock_alert(self):
        """Cement dashboard must show Low Stock Alert section"""
        self.client.force_login(self.user)

        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        response = self.client.get("/verticals/cement/dashboard/")
        html = response.content.decode("utf-8")

        self.assertIn("Low Stock Alert", html, "Dashboard must show Low Stock Alert section")

    def test_cement_response_headers_present(self):
        """Cement dashboard must include X-Template and X-Cement-Premium headers for verification"""
        self.client.force_login(self.user)

        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        response = self.client.get("/verticals/cement/dashboard/")

        self.assertEqual(
            response["X-Template"], "verticals/cement/dashboard.html", "Response must include X-Template header"
        )
        self.assertEqual(response["X-Cement-Premium"], "v1", "Response must include X-Cement-Premium header")
        self.assertEqual(
            response["X-Business-Kind"], BusinessKind.CEMENT, "Response must include X-Business-Kind header"
        )

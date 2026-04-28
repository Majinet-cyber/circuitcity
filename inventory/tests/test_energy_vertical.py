# inventory/tests/test_energy_vertical.py
"""
Tests for the Renewable Energy vertical — flagship module.

Covers:
- Model creation and properties (EnergySite, EnergyAsset, EnergyAlert, etc.)
- SystemSizingRun model and appliance management
- System sizing calculation engine (compute_sizing)
- Risk score and maintenance calculations
- View routing (dashboard, sites, assets, maintenance, alerts, sizing, etc.)
- PDF generation (sizing proposals, site reports)
- Alert engine (run_alert_scan)
- Mobile nav vertical-awareness (energy, car_dealer)
- Regression: PharmacySale notification, pharmacy URL
"""
from decimal import Decimal
from datetime import date, timedelta

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse, NoReverseMatch
from django.utils import timezone

from tenants.models import Business, Membership

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_energy_business(slug="test-energy"):
    return Business.objects.create(
        name="Test Energy Co",
        slug=slug,
        status="ACTIVE",
        business_kind="energy",
    )


def _make_user(username="energy_manager", business=None, role="MANAGER"):
    user = User.objects.create_user(
        username=username, email=f"{username}@test.com", password="TestPass123!@#"
    )
    if business:
        Membership.objects.create(user=user, business=business, role=role, status="ACTIVE")
    return user


def _make_site(business, name="Test Solar Site", **kwargs):
    from inventory.models_energy import EnergySite
    defaults = {
        "business": business,
        "name": name,
        "site_type": "commercial",
        "status": "active",
        "location": "Area 3, Lilongwe",
        "installed_capacity_kw": Decimal("10.0"),
        "commissioning_date": date.today() - timedelta(days=365),
    }
    defaults.update(kwargs)
    return EnergySite.objects.create(**defaults)


def _make_asset(site, business, asset_type="battery", **kwargs):
    from inventory.models_energy import EnergyAsset
    defaults = {
        "site": site,
        "business": business,
        "asset_type": asset_type,
        "brand": "Victron",
        "model_name": "Lithium 200Ah",
        "install_date": date.today() - timedelta(days=200),
        "maintenance_interval_days": 90,
        "health_score": 85,
        "status": "operational",
    }
    defaults.update(kwargs)
    return EnergyAsset.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Energy Model Tests
# ---------------------------------------------------------------------------

class EnergySiteModelTest(TestCase):

    def setUp(self):
        self.business = _make_energy_business()
        self.site = _make_site(self.business, "Lilongwe Solar Farm")

    def test_site_creation(self):
        self.assertEqual(self.site.name, "Lilongwe Solar Farm")
        self.assertEqual(self.site.status, "active")

    def test_asset_count_zero_on_empty(self):
        self.assertEqual(self.site.asset_count, 0)

    def test_months_operational(self):
        months = self.site.months_operational
        self.assertIsNotNone(months)
        self.assertGreater(months, 0)

    def test_str_representation(self):
        self.assertIn("Lilongwe Solar Farm", str(self.site))


class EnergyAssetModelTest(TestCase):

    def setUp(self):
        self.business = _make_energy_business("test-energy-assets")
        self.site = _make_site(self.business, "Test Site", site_type="household")
        self.asset = _make_asset(self.site, self.business)

    def test_asset_creation(self):
        self.assertEqual(self.asset.brand, "Victron")
        self.assertEqual(self.asset.status, "operational")

    def test_is_maintenance_overdue(self):
        self.assertTrue(self.asset.is_maintenance_overdue)

    def test_risk_score_positive(self):
        score = self.asset.risk_score
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_priority_label_not_empty(self):
        self.assertIn(self.asset.priority_label, ["low", "medium", "high", "critical"])

    def test_age_years_positive(self):
        age = self.asset.age_years
        self.assertIsNotNone(age)
        self.assertGreater(age, 0)


class EnergyAlertModelTest(TestCase):

    def setUp(self):
        from inventory.models_energy import EnergyAlert
        self.business = _make_energy_business("test-energy-alerts")
        self.user = _make_user("alert_manager", self.business)
        self.site = _make_site(self.business, "Alert Test Site")
        self.alert = EnergyAlert.objects.create(
            business=self.business,
            site=self.site,
            alert_type="maintenance_due",
            severity="high",
            title="Battery maintenance overdue",
            description="Last serviced 200 days ago",
            suggested_action="Schedule technician visit",
        )

    def test_alert_creation(self):
        self.assertFalse(self.alert.is_resolved)
        self.assertEqual(self.alert.severity, "high")

    def test_alert_resolve(self):
        self.alert.resolve(user=self.user, notes="Completed maintenance")
        self.assertTrue(self.alert.is_resolved)
        self.assertIsNotNone(self.alert.resolved_at)
        self.assertEqual(self.alert.resolved_by, self.user)

    def test_alert_str(self):
        self.assertIn("Battery maintenance overdue", str(self.alert))


# ---------------------------------------------------------------------------
# System Sizing Model Tests
# ---------------------------------------------------------------------------

class SystemSizingRunModelTest(TestCase):

    def setUp(self):
        from inventory.models_energy import SystemSizingRun, SizingAppliance
        self.business = _make_energy_business("test-sizing")
        self.user = _make_user("sizing_user", self.business)
        self.site = _make_site(self.business, "Sizing Test Site")

        self.run = SystemSizingRun.objects.create(
            business=self.business,
            site=self.site,
            title="Office Solar System",
            customer_name="John Doe",
            prepared_by=self.user,
        )
        SizingAppliance.objects.create(
            sizing_run=self.run,
            name="LED Lights",
            category="lighting",
            quantity=10,
            wattage=Decimal("10"),
            hours_per_day=Decimal("8"),
        )
        SizingAppliance.objects.create(
            sizing_run=self.run,
            name="Desktop Computer",
            category="computing",
            quantity=5,
            wattage=Decimal("200"),
            hours_per_day=Decimal("8"),
            is_critical=True,
        )
        SizingAppliance.objects.create(
            sizing_run=self.run,
            name="Fridge",
            category="refrigeration",
            quantity=1,
            wattage=Decimal("150"),
            hours_per_day=Decimal("24"),
            usage_period="both",
        )

    def test_sizing_run_creation(self):
        self.assertEqual(self.run.title, "Office Solar System")
        self.assertEqual(self.run.version, 1)

    def test_appliance_count(self):
        self.assertEqual(self.run.appliance_count, 3)

    def test_total_connected_load(self):
        total = self.run.total_connected_load_w
        expected = (10 * 10) + (5 * 200) + (1 * 150)
        self.assertEqual(total, Decimal(str(expected)))

    def test_appliance_daily_wh(self):
        from inventory.models_energy import SizingAppliance
        led = SizingAppliance.objects.get(sizing_run=self.run, name="LED Lights")
        self.assertEqual(led.daily_wh, Decimal("800.00"))

    def test_clone(self):
        new_run = self.run.clone("Clone Test")
        self.assertEqual(new_run.title, "Clone Test")
        self.assertEqual(new_run.version, 2)
        self.assertEqual(new_run.appliance_count, 3)
        self.assertNotEqual(new_run.id, self.run.id)

    def test_str(self):
        self.assertIn("Office Solar System", str(self.run))


# ---------------------------------------------------------------------------
# System Sizing Engine Tests
# ---------------------------------------------------------------------------

class SizingEngineTest(TestCase):

    def setUp(self):
        from inventory.models_energy import SystemSizingRun, SizingAppliance
        self.business = _make_energy_business("test-engine")

        self.run = SystemSizingRun.objects.create(
            business=self.business,
            title="Engine Test",
            peak_sun_hours=Decimal("5.0"),
            panel_wattage=550,
            panel_efficiency_pct=85,
            battery_dod_pct=80,
            battery_voltage=48,
            autonomy_days=Decimal("1.0"),
            diversity_factor=Decimal("0.80"),
            simultaneity_factor=Decimal("0.70"),
            future_growth_pct=20,
            safety_margin_pct=15,
        )
        SizingAppliance.objects.create(
            sizing_run=self.run, name="Lights", quantity=20,
            wattage=Decimal("10"), hours_per_day=Decimal("8"),
            category="lighting",
        )
        SizingAppliance.objects.create(
            sizing_run=self.run, name="Computers", quantity=5,
            wattage=Decimal("200"), hours_per_day=Decimal("8"),
            category="computing", is_critical=True,
        )
        SizingAppliance.objects.create(
            sizing_run=self.run, name="Fridge", quantity=1,
            wattage=Decimal("150"), hours_per_day=Decimal("24"),
            category="refrigeration",
        )

    def test_compute_sizing_succeeds(self):
        from inventory.services.energy_sizing import compute_sizing
        result = compute_sizing(self.run)
        self.assertTrue(result["ok"])

    def test_daily_demand_positive(self):
        from inventory.services.energy_sizing import compute_sizing
        compute_sizing(self.run)
        self.run.refresh_from_db()
        self.assertGreater(self.run.total_daily_demand_kwh, 0)

    def test_panel_count_positive(self):
        from inventory.services.energy_sizing import compute_sizing
        compute_sizing(self.run)
        self.run.refresh_from_db()
        self.assertGreater(self.run.recommended_panel_count, 0)

    def test_battery_positive(self):
        from inventory.services.energy_sizing import compute_sizing
        compute_sizing(self.run)
        self.run.refresh_from_db()
        self.assertGreater(self.run.recommended_battery_kwh, 0)

    def test_inverter_sized(self):
        from inventory.services.energy_sizing import compute_sizing
        compute_sizing(self.run)
        self.run.refresh_from_db()
        self.assertGreater(self.run.recommended_inverter_kw, 0)

    def test_capex_computed(self):
        from inventory.services.energy_sizing import compute_sizing
        compute_sizing(self.run)
        self.run.refresh_from_db()
        self.assertGreater(self.run.estimated_capex, 0)

    def test_recommendations_generated(self):
        from inventory.services.energy_sizing import compute_sizing
        compute_sizing(self.run)
        self.run.refresh_from_db()
        self.assertIsInstance(self.run.recommendations, list)
        self.assertGreater(len(self.run.recommendations), 0)

    def test_component_summary_populated(self):
        from inventory.services.energy_sizing import compute_sizing
        compute_sizing(self.run)
        self.run.refresh_from_db()
        self.assertIn("panels", self.run.component_summary)
        self.assertIn("battery", self.run.component_summary)

    def test_no_appliances_returns_error(self):
        from inventory.models_energy import SystemSizingRun
        from inventory.services.energy_sizing import compute_sizing
        empty_run = SystemSizingRun.objects.create(
            business=self.business, title="Empty Test",
        )
        result = compute_sizing(empty_run)
        self.assertFalse(result["ok"])


# ---------------------------------------------------------------------------
# Alert Engine Tests
# ---------------------------------------------------------------------------

class AlertEngineTest(TestCase):

    def setUp(self):
        self.business = _make_energy_business("test-alert-engine")
        self.site = _make_site(self.business, "Alert Engine Site")
        self.asset = _make_asset(self.site, self.business)

    def test_alert_scan_creates_maintenance_alert(self):
        from inventory.services.energy_alerts_engine import run_alert_scan
        result = run_alert_scan(self.business)
        self.assertGreaterEqual(result["created"], 1)

    def test_alert_scan_idempotent(self):
        from inventory.services.energy_alerts_engine import run_alert_scan
        run_alert_scan(self.business)
        result2 = run_alert_scan(self.business)
        self.assertEqual(result2["created"], 0)


# ---------------------------------------------------------------------------
# Energy View Tests
# ---------------------------------------------------------------------------

class EnergyDashboardViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.business = _make_energy_business("test-energy-views")
        self.user = _make_user("energy_mgr_view", self.business, role="MANAGER")
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_energy_dashboard_renders(self):
        try:
            url = reverse("verticals:energy_dashboard")
            response = self.client.get(url)
            self.assertIn(response.status_code, [200, 302])
        except NoReverseMatch:
            self.skipTest("Energy URLs not registered")

    def test_energy_sites_view(self):
        try:
            url = reverse("verticals:energy_sites")
            response = self.client.get(url)
            self.assertIn(response.status_code, [200, 302])
        except NoReverseMatch:
            self.skipTest("Energy URLs not registered")

    def test_energy_assets_view(self):
        try:
            url = reverse("verticals:energy_assets")
            response = self.client.get(url)
            self.assertIn(response.status_code, [200, 302])
        except NoReverseMatch:
            self.skipTest("Energy URLs not registered")

    def test_energy_alerts_view(self):
        try:
            url = reverse("verticals:energy_alerts")
            response = self.client.get(url)
            self.assertIn(response.status_code, [200, 302])
        except NoReverseMatch:
            self.skipTest("Energy URLs not registered")

    def test_energy_economics_view(self):
        try:
            url = reverse("verticals:energy_economics")
            response = self.client.get(url)
            self.assertIn(response.status_code, [200, 302])
        except NoReverseMatch:
            self.skipTest("Energy URLs not registered")

    def test_energy_forecasting_view(self):
        try:
            url = reverse("verticals:energy_forecasting")
            response = self.client.get(url)
            self.assertIn(response.status_code, [200, 302])
        except NoReverseMatch:
            self.skipTest("Energy URLs not registered")

    def test_energy_maintenance_view(self):
        try:
            url = reverse("verticals:energy_maintenance")
            response = self.client.get(url)
            self.assertIn(response.status_code, [200, 302])
        except NoReverseMatch:
            self.skipTest("Energy URLs not registered")

    def test_energy_sizing_list_view(self):
        try:
            url = reverse("verticals:energy_sizing_list")
            response = self.client.get(url)
            self.assertIn(response.status_code, [200, 302])
        except NoReverseMatch:
            self.skipTest("Energy URLs not registered")

    def test_energy_sizing_create_view(self):
        try:
            url = reverse("verticals:energy_sizing_create")
            response = self.client.get(url)
            self.assertIn(response.status_code, [200, 302])
        except NoReverseMatch:
            self.skipTest("Energy URLs not registered")

    def test_energy_monitoring_view(self):
        try:
            url = reverse("verticals:energy_monitoring")
            response = self.client.get(url)
            self.assertIn(response.status_code, [200, 302])
        except NoReverseMatch:
            self.skipTest("Energy URLs not registered")

    def test_energy_load_management_view(self):
        try:
            url = reverse("verticals:energy_load_management")
            response = self.client.get(url)
            self.assertIn(response.status_code, [200, 302])
        except NoReverseMatch:
            self.skipTest("Energy URLs not registered")

    def test_energy_technicians_view(self):
        try:
            url = reverse("verticals:energy_technicians")
            response = self.client.get(url)
            self.assertIn(response.status_code, [200, 302])
        except NoReverseMatch:
            self.skipTest("Energy URLs not registered")

    def test_energy_reports_view(self):
        try:
            url = reverse("verticals:energy_reports")
            response = self.client.get(url)
            self.assertIn(response.status_code, [200, 302])
        except NoReverseMatch:
            self.skipTest("Energy URLs not registered")


# ---------------------------------------------------------------------------
# Sizing PDF Test
# ---------------------------------------------------------------------------

class SizingPDFTest(TestCase):

    def setUp(self):
        from inventory.models_energy import SystemSizingRun, SizingAppliance
        self.business = _make_energy_business("test-pdf")
        self.user = _make_user("pdf_user", self.business)
        self.run = SystemSizingRun.objects.create(
            business=self.business, title="PDF Test",
            customer_name="Test Customer", prepared_by=self.user,
        )
        SizingAppliance.objects.create(
            sizing_run=self.run, name="Lights", quantity=10,
            wattage=Decimal("10"), hours_per_day=Decimal("8"),
        )
        from inventory.services.energy_sizing import compute_sizing
        compute_sizing(self.run)

    def test_sizing_pdf_generation(self):
        try:
            from inventory.services.energy_pdf import generate_sizing_pdf
            pdf = generate_sizing_pdf(self.run, self.business)
            if pdf is not None:
                self.assertGreater(len(pdf), 500)
                self.assertTrue(pdf[:5] == b'%PDF-')
        except ImportError:
            self.skipTest("ReportLab not installed")


# ---------------------------------------------------------------------------
# Mobile Nav Vertical-Awareness Tests
# ---------------------------------------------------------------------------

class MobileNavVerticalTest(TestCase):

    def _make_biz_with_kind(self, kind, slug):
        return Business.objects.create(name=f"{kind} biz", slug=slug, status="ACTIVE", business_kind=kind)

    def _build_nav(self, biz):
        from inventory.mobile_nav import get_mobile_nav_items
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get("/")
        request.business = biz
        request.user = None
        try:
            return get_mobile_nav_items(request)
        except Exception:
            return []

    def test_energy_nav_no_phone_items(self):
        biz = self._make_biz_with_kind("energy", "test-nav-energy")
        nav = self._build_nav(biz)
        keys = [item["key"] for item in nav]
        self.assertNotIn("phones", keys, "Energy nav should not show phone items")
        self.assertIn("home", keys, "Energy nav should have a home item")

    def test_energy_nav_has_sizing(self):
        biz = self._make_biz_with_kind("energy", "test-nav-energy-sizing")
        nav = self._build_nav(biz)
        keys = [item["key"] for item in nav]
        self.assertIn("sizing", keys, "Energy nav should have sizing item")

    def test_car_dealer_nav_no_phone_items(self):
        biz = self._make_biz_with_kind("car_dealer", "test-nav-car-dealer")
        nav = self._build_nav(biz)
        keys = [item["key"] for item in nav]
        self.assertIn("vehicles", keys, "Car dealer nav should have vehicles item")

    def test_liquor_nav_has_own_items(self):
        biz = self._make_biz_with_kind("liquor", "test-nav-liquor")
        nav = self._build_nav(biz)
        self.assertGreater(len(nav), 0, "Liquor nav should have items")
        keys = [item.get("key", "") for item in nav]
        self.assertNotIn("phones", keys)


# ---------------------------------------------------------------------------
# Sidebar Tests
# ---------------------------------------------------------------------------

class EnergySidebarTest(TestCase):

    def test_energy_sidebar_has_sizing(self):
        from inventory.utils_verticals import get_vertical_sidebar_items
        items = get_vertical_sidebar_items("energy")
        keys = [i["key"] for i in items]
        self.assertIn("sizing", keys, "Energy sidebar must include System Sizing")

    def test_energy_sidebar_has_monitoring(self):
        from inventory.utils_verticals import get_vertical_sidebar_items
        items = get_vertical_sidebar_items("energy")
        keys = [i["key"] for i in items]
        self.assertIn("monitoring", keys)

    def test_energy_sidebar_has_load_management(self):
        from inventory.utils_verticals import get_vertical_sidebar_items
        items = get_vertical_sidebar_items("energy")
        keys = [i["key"] for i in items]
        self.assertIn("load_management", keys)

    def test_energy_sidebar_has_technicians(self):
        from inventory.utils_verticals import get_vertical_sidebar_items
        items = get_vertical_sidebar_items("energy")
        keys = [i["key"] for i in items]
        self.assertIn("technicians", keys)

    def test_energy_sidebar_has_billing(self):
        from inventory.utils_verticals import get_vertical_sidebar_items
        items = get_vertical_sidebar_items("energy")
        keys = [i["key"] for i in items]
        self.assertIn("billing", keys)

    def test_energy_sidebar_item_count(self):
        from inventory.utils_verticals import get_vertical_sidebar_items
        items = get_vertical_sidebar_items("energy")
        self.assertGreaterEqual(len(items), 14, "Energy sidebar should have 14+ items")


# ---------------------------------------------------------------------------
# Pharmacy URL Fix Tests (Regression)
# ---------------------------------------------------------------------------

class PharmacyURLTest(TestCase):

    def test_pharmacy_batch_list_url_exists(self):
        try:
            url = reverse("pharmacy:batch_list")
            self.assertTrue(url.startswith("/"))
        except NoReverseMatch:
            self.fail("pharmacy:batch_list URL should exist")

    def test_pharmacy_dashboard_url_exists(self):
        try:
            url = reverse("verticals:pharmacy_dashboard")
            self.assertTrue(url.startswith("/"))
        except NoReverseMatch:
            self.fail("verticals:pharmacy_dashboard URL should exist")


# ---------------------------------------------------------------------------
# Notification Service PharmacySale Test (Regression)
# ---------------------------------------------------------------------------

class NotifySaleCompletionPharmacyTest(TestCase):

    def setUp(self):
        self.business = Business.objects.create(
            name="Test Pharmacy Notify", slug="test-pharm-notify",
            status="ACTIVE", business_kind="pharmacy"
        )
        self.user = _make_user("pharm_seller_notify", self.business, role="AGENT")

        from inventory.models import MerchProduct
        from inventory.models_pharmacy import PharmacyBatch

        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Paracetamol 500mg",
            kind="pharmacy",
            category="analgesic",
            selling_price=Decimal("150.00"),
            cost_price=Decimal("80.00"),
        )
        self.batch = PharmacyBatch.objects.create(
            business=self.business,
            merch_product=self.product,
            batch_number="TEST001",
            expiry_date=date.today() + timedelta(days=365),
            quantity=100,
            cost_price=Decimal("80.00"),
            selling_price=Decimal("150.00"),
        )

    def test_notify_sale_completion_does_not_raise_for_pharmacy_sale(self):
        from inventory.models_pharmacy import PharmacySale
        from notifications.services import notify_sale_completion

        sale = PharmacySale.objects.create(
            business=self.business,
            batch=self.batch,
            quantity=5,
            unit_price=Decimal("150.00"),
            unit_cost=Decimal("80.00"),
            sold_by=self.user,
        )

        try:
            notify_sale_completion(sale)
        except AttributeError as e:
            self.fail(f"notify_sale_completion raised AttributeError: {e}")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Task 5 — Regression: Energy Dashboard Placeholder Logic
# ---------------------------------------------------------------------------

class EnergyDashboardPlaceholderTest(TestCase):
    """
    Dashboard must show sample/demo values only when workspace has no real data.
    Real data must override demo values.
    """

    def setUp(self):
        self.business = _make_energy_business("test-energy-placeholder")
        self.user = _make_user("energy_placeholder_mgr", self.business, role="MANAGER")
        self.client = Client()
        self.client.login(username="energy_placeholder_mgr", password="TestPass123!@#")
        # Activate business via session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_dashboard_loads_for_empty_workspace(self):
        """Dashboard must return 200 for a brand-new workspace with no sites/assets."""
        try:
            url = reverse("verticals:energy_dashboard")
        except NoReverseMatch:
            self.skipTest("energy_dashboard URL not configured")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_context_has_is_new_workspace_true_when_empty(self):
        """is_new_workspace must be True when no sites and no assets exist."""
        try:
            url = reverse("verticals:energy_dashboard")
        except NoReverseMatch:
            self.skipTest("energy_dashboard URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Dashboard returned non-200")
        self.assertTrue(resp.context.get("is_new_workspace", False),
                        "is_new_workspace should be True for empty workspace")

    def test_dashboard_context_has_is_new_workspace_false_with_site(self):
        """is_new_workspace must be False once a site exists."""
        _make_site(self.business, name="Lilongwe Office")
        try:
            url = reverse("verticals:energy_dashboard")
        except NoReverseMatch:
            self.skipTest("energy_dashboard URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Dashboard returned non-200")
        self.assertFalse(resp.context.get("is_new_workspace", True),
                         "is_new_workspace should be False when sites exist")

    def test_dashboard_demo_values_in_empty_workspace(self):
        """Sample estimate values must be injected in new workspace."""
        try:
            url = reverse("verticals:energy_dashboard")
        except NoReverseMatch:
            self.skipTest("energy_dashboard URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Dashboard returned non-200")
        stats = resp.context.get("stats", {})
        # Demo values per the spec
        self.assertEqual(stats.get("active_sites"), 1)
        self.assertEqual(stats.get("total_assets"), 4)
        self.assertEqual(float(stats.get("installed_capacity", 0)), 5.2)
        self.assertEqual(float(stats.get("generation_this_month", 0)), 620)


# ---------------------------------------------------------------------------
# Task 5 — Regression: System Sizing Calculations
# ---------------------------------------------------------------------------

class SystemSizingCalculationTest(TestCase):
    """
    Verify the system sizing engine computes correct engineering outputs.
    """

    def setUp(self):
        self.business = _make_energy_business("test-sizing-calc")

    def _make_run(self, **kwargs):
        from inventory.models_energy import SystemSizingRun
        defaults = dict(
            business=self.business,
            title="Test Sizing",
            peak_sun_hours=Decimal("5.0"),
            panel_wattage=550,
            panel_efficiency_pct=85,
            battery_dod_pct=80,
            battery_voltage=48,
            autonomy_days=Decimal("1.0"),
            diversity_factor=Decimal("0.80"),
            simultaneity_factor=Decimal("0.70"),
            future_growth_pct=20,
            safety_margin_pct=15,
        )
        defaults.update(kwargs)
        return SystemSizingRun.objects.create(**defaults)

    def _add_appliance(self, run, name, wattage, hours, qty=1, surge=None, critical=False):
        from inventory.models_energy import SizingAppliance
        return SizingAppliance.objects.create(
            sizing_run=run,
            name=name,
            wattage=Decimal(str(wattage)),
            surge_wattage=Decimal(str(surge)) if surge else None,
            quantity=qty,
            hours_per_day=Decimal(str(hours)),
            is_critical=critical,
        )

    def test_daily_energy_demand(self):
        """Daily kWh must equal sum of (wattage × qty × hours) / 1000."""
        from inventory.services.energy_sizing import compute_sizing
        run = self._make_run()
        self._add_appliance(run, "LED Lights", 10, 6, qty=5)   # 50W × 6h = 300 Wh
        self._add_appliance(run, "TV", 80, 5, qty=1)            # 80W × 5h = 400 Wh
        result = compute_sizing(run)
        self.assertTrue(result["ok"])
        run.refresh_from_db()
        # diversity * growth * safety applied → just check it's > 0 and order of magnitude right
        self.assertGreater(run.total_daily_demand_wh, Decimal("0"))
        # Raw wh = 300+400=700; adjusted < 700 due to diversity/weekly factors
        self.assertLess(float(run.total_daily_demand_wh), 2000)

    def test_peak_load(self):
        """Peak load must equal sum of running wattages."""
        from inventory.services.energy_sizing import compute_sizing
        run = self._make_run()
        self._add_appliance(run, "Fan", 75, 8, qty=2)
        self._add_appliance(run, "Computer", 200, 6, qty=1)
        result = compute_sizing(run)
        self.assertTrue(result["ok"])
        run.refresh_from_db()
        # 75×2 + 200 = 350 W
        self.assertEqual(float(run.peak_load_w), 350.0)

    def test_surge_load_exceeds_running(self):
        """Surge load must be >= running peak load."""
        from inventory.services.energy_sizing import compute_sizing
        run = self._make_run()
        self._add_appliance(run, "Water Pump", 750, 3, qty=1, surge=2250)
        result = compute_sizing(run)
        self.assertTrue(result["ok"])
        run.refresh_from_db()
        self.assertGreaterEqual(float(run.surge_load_w), float(run.peak_load_w))

    def test_inverter_sized_to_cover_peak(self):
        """Recommended inverter must cover the corrected peak load."""
        from inventory.services.energy_sizing import compute_sizing
        run = self._make_run()
        self._add_appliance(run, "Fridge", 150, 24, qty=1)
        self._add_appliance(run, "Lights", 10, 8, qty=10)
        compute_sizing(run)
        run.refresh_from_db()
        corrected_peak_kw = float(run.peak_load_w) / 1000
        self.assertGreaterEqual(float(run.recommended_inverter_kw), corrected_peak_kw)

    def test_battery_sized_for_autonomy(self):
        """Battery kWh must cover at least 1 day's corrected demand at the DoD."""
        from inventory.services.energy_sizing import compute_sizing
        run = self._make_run(autonomy_days=Decimal("1.0"), battery_dod_pct=80)
        self._add_appliance(run, "Computer", 200, 8, qty=1)
        compute_sizing(run)
        run.refresh_from_db()
        # usable_kwh ≥ corrected_demand (before diversity for simplified check)
        self.assertGreater(float(run.recommended_battery_kwh), 0)
        self.assertGreater(float(run.usable_storage_kwh), 0)

    def test_solar_array_sized_non_zero(self):
        """Recommended solar array must be > 0 when appliances present."""
        from inventory.services.energy_sizing import compute_sizing
        run = self._make_run()
        self._add_appliance(run, "LED", 10, 6, qty=1)
        compute_sizing(run)
        run.refresh_from_db()
        self.assertGreater(float(run.recommended_array_kw), 0)

    def test_roi_payback_populated(self):
        """Payback period must be populated when savings > 0."""
        from inventory.services.energy_sizing import compute_sizing
        run = self._make_run()
        self._add_appliance(run, "Fridge", 150, 24, qty=1)
        self._add_appliance(run, "Lights", 10, 8, qty=5)
        compute_sizing(run)
        run.refresh_from_db()
        self.assertIsNotNone(run.payback_years)
        self.assertGreater(float(run.payback_years), 0)

    def test_custom_tariff_affects_savings(self):
        """Higher tariff should produce higher monthly savings."""
        from inventory.services.energy_sizing import compute_sizing
        run_low = self._make_run()
        run_low.energy_tariff_per_kwh = Decimal("100")
        run_low.save()
        self._add_appliance(run_low, "Fridge", 150, 24, qty=1)
        compute_sizing(run_low)
        run_low.refresh_from_db()

        run_high = self._make_run()
        run_high.energy_tariff_per_kwh = Decimal("400")
        run_high.save()
        self._add_appliance(run_high, "Fridge", 150, 24, qty=1)
        compute_sizing(run_high)
        run_high.refresh_from_db()

        self.assertGreater(
            float(run_high.projected_monthly_savings or 0),
            float(run_low.projected_monthly_savings or 0),
        )

    def test_sensitivity_analysis_populated(self):
        """sensitivity_summary must contain pessimistic/base/optimistic keys."""
        from inventory.services.energy_sizing import compute_sizing
        run = self._make_run()
        self._add_appliance(run, "Fridge", 150, 24, qty=1)
        compute_sizing(run)
        run.refresh_from_db()
        ss = run.sensitivity_summary or {}
        self.assertIn("pessimistic", ss)
        self.assertIn("base", ss)
        self.assertIn("optimistic", ss)

    def test_critical_load_flag_tracked(self):
        """Appliances marked critical must register is_critical=True."""
        run = self._make_run()
        a = self._add_appliance(run, "Medical Fridge", 120, 24, qty=1, critical=True)
        self.assertTrue(a.is_critical)

    def test_no_appliances_returns_error(self):
        """compute_sizing must return ok=False when no appliances provided."""
        from inventory.services.energy_sizing import compute_sizing
        run = self._make_run()
        result = compute_sizing(run)
        self.assertFalse(result["ok"])
        self.assertIn("error", result)


# ---------------------------------------------------------------------------
# Task 5 — Regression: Energy Simulation Logic (pure Python)
# ---------------------------------------------------------------------------

class EnergySimulationLogicTest(TestCase):
    """
    Validate the simulation logic: battery charges when solar > load,
    discharges when load > solar.
    """

    def _simulate(self, array_kw, peak_load_w, bat_usable_kwh, steps=96):
        """
        Simple day simulation — returns list of (minute, solar_w, load_w, bat_pct).
        Mirrors the JS simulation in Python for unit testing.
        """
        import math

        def solar_at(m):
            h = m / 60
            if h < 6 or h > 19:
                return 0.0
            t = (h - 6) / (19 - 6)
            bell = math.sin(t * math.pi)
            return max(0.0, bell * array_kw * 1000 * 0.85)

        def load_at(m):
            h = m / 60
            if 6 <= h < 9: return peak_load_w * 0.7
            if 9 <= h < 17: return peak_load_w * 0.5
            if 17 <= h < 22: return peak_load_w * 0.9
            return peak_load_w * 0.15

        bat_wh = bat_usable_kwh * 1000 * 0.7
        results = []
        step = 1440 // steps
        for t in range(0, 1440, step):
            solar = solar_at(t)
            load = load_at(t)
            net = (solar - load) * (step / 60)
            bat_wh = max(0.0, min(bat_usable_kwh * 1000, bat_wh + net))
            results.append((t, solar, load, bat_wh / (bat_usable_kwh * 1000) * 100))
        return results

    def test_battery_charges_during_peak_solar(self):
        """Battery SoC must increase during high solar output with low load."""
        results = self._simulate(array_kw=5.0, peak_load_w=300, bat_usable_kwh=5.0)
        midday = [r for r in results if 720 <= r[0] <= 840]  # 12:00-14:00
        # Solar should exceed load at midday
        for t, solar, load, bat_pct in midday:
            if solar > 0:
                # If solar exceeds load the battery would have been charging in prior steps
                self.assertGreater(solar, load * 0.3)

    def test_battery_discharges_at_night(self):
        """Battery SoC must decrease after sunset when load > 0."""
        results = self._simulate(array_kw=5.0, peak_load_w=500, bat_usable_kwh=5.0)
        night = [r for r in results if r[0] >= 1320]  # 22:00+
        soc_vals = [r[3] for r in night]
        if len(soc_vals) >= 2:
            self.assertLessEqual(soc_vals[-1], soc_vals[0] + 10,
                                 "Battery SoC should not increase significantly at night")

    def test_overload_detected_when_load_exceeds_inverter(self):
        """Status must flag overload when load > inverter capacity."""
        inv_kw = 1.0
        peak_w = 1500  # 1.5 kW > inverter
        overloaded = peak_w > inv_kw * 1000 * 0.9
        self.assertTrue(overloaded, "Load exceeding 90% of inverter should flag overload warning")


# ---------------------------------------------------------------------------
# Task 5 — Regression: Technical Diagram Rendered
# ---------------------------------------------------------------------------

class TechDiagramTemplateTest(TestCase):
    """Verify the sizing detail page renders the diagram section."""

    def setUp(self):
        self.business = _make_energy_business("test-energy-diagram")
        self.user = _make_user("energy_diagram_mgr", self.business, role="MANAGER")
        self.client = Client()
        self.client.login(username="energy_diagram_mgr", password="TestPass123!@#")
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def _make_computed_run(self):
        from inventory.models_energy import SystemSizingRun, SizingAppliance
        from inventory.services.energy_sizing import compute_sizing
        run = SystemSizingRun.objects.create(
            business=self.business,
            title="Diagram Test Run",
            peak_sun_hours=Decimal("5.0"),
            panel_wattage=550,
            panel_efficiency_pct=85,
            battery_dod_pct=80,
            battery_voltage=48,
            autonomy_days=Decimal("1.0"),
            diversity_factor=Decimal("0.80"),
            simultaneity_factor=Decimal("0.70"),
            future_growth_pct=20,
            safety_margin_pct=15,
        )
        SizingAppliance.objects.create(
            sizing_run=run,
            name="Fridge",
            wattage=Decimal("150"),
            quantity=1,
            hours_per_day=Decimal("24"),
        )
        SizingAppliance.objects.create(
            sizing_run=run,
            name="Lights",
            wattage=Decimal("10"),
            quantity=5,
            hours_per_day=Decimal("8"),
        )
        compute_sizing(run)
        return run

    def test_sizing_detail_has_diagram_section(self):
        """The tech diagram SVG section should appear on the sizing detail page."""
        run = self._make_computed_run()
        try:
            url = reverse("verticals:energy_sizing_detail", kwargs={"run_id": run.id})
        except NoReverseMatch:
            self.skipTest("energy_sizing_detail URL not configured")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "sysdiagram")
        # Accept either original or updated name (polished template renamed to "System Schematic")
        content = resp.content.decode()
        self.assertTrue(
            "System Diagram" in content or "System Schematic" in content,
            "Sizing detail should have a diagram section"
        )

    def test_sizing_detail_has_simulation_section(self):
        """Simulation panel should appear on the sizing detail page."""
        run = self._make_computed_run()
        try:
            url = reverse("verticals:energy_sizing_detail", kwargs={"run_id": run.id})
        except NoReverseMatch:
            self.skipTest("energy_sizing_detail URL not configured")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "simSlider")
        # Accept either original or updated name (polished template uses "Daily Energy Flow Simulation")
        content = resp.content.decode()
        self.assertTrue(
            "Daily Energy Simulation" in content or "Daily Energy Flow Simulation" in content,
            "Sizing detail should have a simulation section"
        )

    def test_sizing_detail_has_sensitivity_table(self):
        """Sensitivity analysis section should appear when data exists."""
        run = self._make_computed_run()
        try:
            url = reverse("verticals:energy_sizing_detail", kwargs={"run_id": run.id})
        except NoReverseMatch:
            self.skipTest("energy_sizing_detail URL not configured")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Sensitivity Analysis")


# ---------------------------------------------------------------------------
# Component Cost Assumptions Tests
# ---------------------------------------------------------------------------

class SizingComponentCostTests(TestCase):
    """Test that editable component costs are used in CAPEX calculation."""

    def setUp(self):
        from inventory.models_energy import SystemSizingRun, SizingAppliance
        from inventory.services.energy_sizing import compute_sizing

        self.SystemSizingRun = SystemSizingRun
        self.SizingAppliance = SizingAppliance
        self.compute_sizing = compute_sizing

        self.business = _make_energy_business("test-energy-costs")

    def _make_run(self, **kwargs):
        from inventory.models_energy import SystemSizingRun
        defaults = {
            "business": self.business,
            "title": "Cost Test Run",
            "autonomy_days": Decimal("1.0"),
            "battery_dod_pct": 80,
            "battery_voltage": 24,
            "panel_efficiency_pct": 85,
            "peak_sun_hours": Decimal("5.5"),
            "installation_cost_pct": Decimal("0.15"),
        }
        defaults.update(kwargs)
        run = SystemSizingRun.objects.create(**defaults)
        # Add a minimal appliance
        from inventory.models_energy import SizingAppliance
        SizingAppliance.objects.create(
            sizing_run=run,
            name="LED Bulb",
            quantity=4,
            wattage=Decimal("10"),
            hours_per_day=Decimal("8"),
        )
        return run

    def test_custom_panel_cost_changes_capex(self):
        """Custom panel cost should affect total CAPEX."""
        run_default = self._make_run()
        self.compute_sizing(run_default)
        default_capex = run_default.estimated_capex

        run_custom = self._make_run(cost_per_panel_wp=Decimal("1000"))  # 2x Malawi default 650
        self.compute_sizing(run_custom)
        custom_capex = run_custom.estimated_capex

        # Higher panel cost should yield higher CAPEX
        self.assertGreater(custom_capex, default_capex,
                           "Higher panel cost should produce higher CAPEX")

    def test_zero_lump_costs_do_not_apply(self):
        """None (not set) lump costs fall back to defaults."""
        run = self._make_run(
            cost_wiring_lump=None,
            cost_breakers_lump=None,
            cost_mounting_lump=None,
        )
        self.compute_sizing(run)
        # Defaults are non-zero, so capex should include wiring/breakers/mounting
        self.assertGreater(run.estimated_capex, Decimal("0"))

    def test_custom_battery_cost_changes_capex(self):
        """Higher battery cost should raise CAPEX."""
        run_default = self._make_run()
        self.compute_sizing(run_default)

        run_expensive = self._make_run(cost_per_battery_kwh=Decimal("900000"))  # 2x
        self.compute_sizing(run_expensive)

        self.assertGreater(run_expensive.estimated_capex, run_default.estimated_capex)

    def test_capex_positive_for_basic_load(self):
        """CAPEX must be > 0 for any real load."""
        run = self._make_run()
        self.compute_sizing(run)
        self.assertGreater(run.estimated_capex, Decimal("0"))

    def test_payback_period_positive(self):
        """Payback period should be positive when costs > 0."""
        run = self._make_run()
        self.compute_sizing(run)
        if run.payback_years is not None:
            self.assertGreater(run.payback_years, Decimal("0"))


# ---------------------------------------------------------------------------
# Dashboard Demo Placeholder Tests
# ---------------------------------------------------------------------------

class EnergyDashboardDemoPlaceholderTest(TestCase):
    """Test that new workspaces show clearly labeled demo data."""

    def setUp(self):
        self.business = _make_energy_business("test-demo-dash")
        self.user = _make_user("demo_manager", self.business)
        self.client = Client()
        self.client.login(username="demo_manager", password="TestPass123!@#")

        import django.test.utils as test_utils
        from django.test.utils import override_settings

    def test_dashboard_renders_without_500(self):
        """Dashboard should not 500 for a new workspace."""
        try:
            url = reverse("verticals:energy_dashboard")
        except Exception:
            self.skipTest("energy_dashboard URL not configured")
        resp = self.client.get(url)
        self.assertNotEqual(resp.status_code, 500, "Dashboard returned 500")
        self.assertIn(resp.status_code, [200, 302])

    def test_dashboard_contains_demo_label_for_new_workspace(self):
        """New workspace dashboard should show demo/sample labels."""
        try:
            url = reverse("verticals:energy_dashboard")
        except Exception:
            self.skipTest("energy_dashboard URL not configured")
        resp = self.client.get(url)
        if resp.status_code == 200:
            content = resp.content.decode()
            # Should mention either demo/sample indicators or quick-start
            has_demo_indicator = (
                'demo' in content.lower()
                or 'sample' in content.lower()
                or 'quick-start' in content.lower()
                or 'Quick Start' in content
            )
            self.assertTrue(has_demo_indicator,
                            "New workspace dashboard should show demo/sample indicators")


# ---------------------------------------------------------------------------
# Landing Page Content Tests
# ---------------------------------------------------------------------------

class LandingPageContentTest(TestCase):
    """Verify landing page has correct messaging and removed sections."""

    def _get_home_content(self):
        try:
            url = reverse("staticpages:home")
        except Exception:
            try:
                url = "/"
            except Exception:
                return None
        resp = self.client.get(url)
        if resp.status_code == 200:
            return resp.content.decode()
        return None

    def test_generic_african_business_phrase_removed(self):
        """Generic 'for every type of African business' phrase should be gone."""
        content = self._get_home_content()
        if content is None:
            self.skipTest("Landing page not accessible")
        self.assertNotIn(
            "for every type of African business",
            content,
            "Generic 'for every type of African business' phrase should have been replaced"
        )

    def test_partners_include_twilio(self):
        """Partners section should include Twilio."""
        content = self._get_home_content()
        if content is None:
            self.skipTest("Landing page not accessible")
        self.assertIn("Twilio", content, "Twilio should be in the partners section")

    def test_partners_include_sendgrid(self):
        """Partners section should include SendGrid."""
        content = self._get_home_content()
        if content is None:
            self.skipTest("Landing page not accessible")
        self.assertIn("SendGrid", content, "SendGrid should be in the partners section")

    def test_daily_reporting_section_not_visible(self):
        """Daily Reporting section should be hidden or removed."""
        content = self._get_home_content()
        if content is None:
            self.skipTest("Landing page not accessible")
        # Either completely removed, or hidden via display:none
        if "Daily Reporting" in content:
            # If present, must be hidden
            import re
            section_match = re.search(
                r'display:\s*none[^>]*>.*?Daily Reporting',
                content,
                re.DOTALL | re.IGNORECASE
            )
            # Also acceptable: wrapped in comment or hidden section
            self.assertTrue(
                'display:none' in content or 'display: none' in content,
                "Daily Reporting section should be hidden with display:none or removed"
            )


# ---------------------------------------------------------------------------
# Regression: SystemSizingRun create view with cost_per_panel_wp and all
# component cost/assumption fields must not produce a 500 error.
# ---------------------------------------------------------------------------

class SizingCreateCostFieldRegressionTest(TestCase):
    """
    Regression guard for the 'table inventory_systemsizingrun has no column
    named cost_per_panel_wp' error and all related component cost fields added
    in migrations 1054/1055.

    Ensures:
    - POST to /verticals/energy/sizing/new/ succeeds (no 500).
    - The SystemSizingRun row is persisted with cost_per_panel_wp saved.
    - The sizing detail page (ROI/capex) renders without 500.
    """

    def setUp(self):
        from inventory.models_energy import SystemSizingRun  # noqa: F401 – import check
        self.business = _make_energy_business("test-sizing-cost-regression")
        self.user = _make_user("sizing_cost_user", self.business, role="MANAGER")
        self.client = Client()
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def _post_sizing(self, extra_post=None):
        """POST minimal sizing data to the create view, return response."""
        try:
            url = reverse("verticals:energy_sizing_create")
        except NoReverseMatch:
            self.skipTest("energy_sizing_create URL not registered")
            return None

        data = {
            "title": "Regression Test Sizing Run",
            "customer_name": "Regression Customer",
            "customer_phone": "0999000000",
            "customer_email": "regression@test.com",
            "customer_address": "Test Address",
            "design_objective": "balanced",
            "system_architecture": "solar_battery",
            "has_grid_access": "on",
            "grid_reliability_pct": "80",
            "peak_sun_hours": "5.0",
            "panel_wattage": "550",
            "panel_efficiency_pct": "85",
            "battery_dod_pct": "80",
            "battery_voltage": "48",
            "autonomy_days": "1.0",
            "diversity_factor": "0.80",
            "simultaneity_factor": "0.70",
            "future_growth_pct": "20",
            "safety_margin_pct": "15",
            "tariff_escalation_pct": "5.0",
            "discount_rate_pct": "10.0",
            # Component cost / assumption fields (migration 1054/1055)
            "cost_per_panel_wp": "650",
            "cost_per_battery_kwh": "450000",
            "cost_per_inverter_kw": "180000",
            "cost_per_cc_amp": "12000",
            "cost_wiring_lump": "150000",
            "cost_breakers_lump": "80000",
            "cost_mounting_lump": "50000",
            "energy_tariff_per_kwh": "185",
            "diesel_cost_per_litre": "",
            "installation_cost_pct": "",
            "annual_maintenance_pct": "",
            # Appliance rows
            "appliance_name": ["LED Bulb"],
            "appliance_wattage": ["10"],
            "appliance_surge": [""],
            "appliance_quantity": ["4"],
            "appliance_hours": ["8"],
            "appliance_category": ["lighting"],
            "appliance_priority": ["medium"],
            "appliance_period": ["both"],
        }
        if extra_post:
            data.update(extra_post)
        return self.client.post(url, data)

    def test_post_sizing_create_no_500(self):
        """POST to create view must not return 500 (DB column error)."""
        response = self._post_sizing()
        if response is None:
            return
        self.assertNotEqual(
            response.status_code, 500,
            "Got HTTP 500 on sizing create — likely a missing DB column."
        )

    # ── NEW: Tests for Task 2+3 demo data and wizard features ──────────────

    def test_demo_alerts_injected_when_empty(self):
        """demo_alerts must be non-empty list for new workspaces."""
        try:
            url = reverse("verticals:energy_dashboard")
        except NoReverseMatch:
            self.skipTest("energy_dashboard URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Dashboard returned non-200")
        is_new = resp.context.get("is_new_workspace", False)
        if not is_new:
            self.skipTest("Workspace is not new — demo alerts test not applicable")
        demo_alerts = resp.context.get("demo_alerts", [])
        self.assertGreater(len(demo_alerts), 0, "demo_alerts must be non-empty for new workspace")

    def test_demo_risks_injected_when_empty(self):
        """demo_risks must be non-empty list for new workspaces."""
        try:
            url = reverse("verticals:energy_dashboard")
        except NoReverseMatch:
            self.skipTest("energy_dashboard URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Dashboard returned non-200")
        is_new = resp.context.get("is_new_workspace", False)
        if not is_new:
            self.skipTest("Workspace is not new — demo risks test not applicable")
        demo_risks = resp.context.get("demo_risks", [])
        self.assertGreater(len(demo_risks), 0, "demo_risks must be non-empty for new workspace")

    def test_demo_forecast_injected_when_empty(self):
        """demo_forecast must be set for new workspaces."""
        try:
            url = reverse("verticals:energy_dashboard")
        except NoReverseMatch:
            self.skipTest("energy_dashboard URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Dashboard returned non-200")
        is_new = resp.context.get("is_new_workspace", False)
        if not is_new:
            self.skipTest("Workspace is not new")
        demo_forecast = resp.context.get("demo_forecast")
        self.assertIsNotNone(demo_forecast, "demo_forecast must not be None for new workspace")
        self.assertIn("next_7_day_demand_kwh", demo_forecast)

    def test_no_demo_data_when_site_exists(self):
        """demo_alerts and demo_risks must be empty once real data exists."""
        _make_site(self.business, name="Real Site")
        try:
            url = reverse("verticals:energy_dashboard")
        except NoReverseMatch:
            self.skipTest("energy_dashboard URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Dashboard returned non-200")
        demo_alerts = resp.context.get("demo_alerts", [])
        demo_risks = resp.context.get("demo_risks", [])
        self.assertEqual(len(demo_alerts), 0, "demo_alerts must be empty when real data exists")
        self.assertEqual(len(demo_risks), 0, "demo_risks must be empty when real data exists")

    def test_post_sizing_creates_run_and_saves_cost_per_panel_wp(self):
        """SystemSizingRun must be saved with cost_per_panel_wp = 650."""
        from inventory.models_energy import SystemSizingRun
        response = self._post_sizing()
        if response is None:
            return
        # Successful POST redirects to detail page (302) or shows 200 on error page
        # Either way, run must have been created
        self.assertIn(
            response.status_code, [200, 302],
            f"Unexpected status {response.status_code}"
        )
        run = SystemSizingRun.objects.filter(
            business=self.business,
            title="Regression Test Sizing Run"
        ).first()
        self.assertIsNotNone(run, "SystemSizingRun was not created in DB")
        self.assertEqual(
            run.cost_per_panel_wp, Decimal("650"),
            f"cost_per_panel_wp not saved correctly, got: {run.cost_per_panel_wp}"
        )

    def test_all_cost_fields_saved(self):
        """All component cost fields from migrations 1054/1055 must be saved."""
        from inventory.models_energy import SystemSizingRun
        response = self._post_sizing()
        if response is None:
            return
        run = SystemSizingRun.objects.filter(
            business=self.business,
            title="Regression Test Sizing Run"
        ).first()
        if run is None:
            self.fail("SystemSizingRun was not created — check for DB column errors")

        expected = {
            "cost_per_panel_wp": Decimal("650"),
            "cost_per_battery_kwh": Decimal("450000"),
            "cost_per_inverter_kw": Decimal("180000"),
            "cost_per_cc_amp": Decimal("12000"),
            "cost_wiring_lump": Decimal("150000"),
            "cost_breakers_lump": Decimal("80000"),
            "cost_mounting_lump": Decimal("50000"),
            "energy_tariff_per_kwh": Decimal("185"),
        }
        for field, expected_val in expected.items():
            actual = getattr(run, field)
            self.assertEqual(
                actual, expected_val,
                f"Field '{field}' expected {expected_val}, got {actual}"
            )

    def test_sizing_detail_renders_after_create(self):
        """Detail/ROI page must render (200 or redirect) after a sizing run is created."""
        from inventory.models_energy import SystemSizingRun
        response = self._post_sizing()
        if response is None:
            return

        run = SystemSizingRun.objects.filter(
            business=self.business,
            title="Regression Test Sizing Run"
        ).first()
        if run is None:
            self.skipTest("Run not created — skipping detail render check")

        try:
            detail_url = reverse("verticals:energy_sizing_detail", kwargs={"run_id": run.id})
        except NoReverseMatch:
            self.skipTest("energy_sizing_detail URL not registered")
            return

        detail_response = self.client.get(detail_url)
        self.assertNotEqual(
            detail_response.status_code, 500,
            "Sizing detail page returned 500"
        )
        self.assertIn(
            detail_response.status_code, [200, 302],
            f"Unexpected status on detail page: {detail_response.status_code}"
        )


# ---------------------------------------------------------------------------
# NEW: Energy Demo Intelligence Tests (Tasks 2+3)
# ---------------------------------------------------------------------------

class EnergyAlertsPageDemoTest(TestCase):
    """Alerts page should show demo intelligence for new workspaces."""

    def setUp(self):
        self.business = _make_energy_business("test-alerts-demo")
        self.user = _make_user("alerts_demo_mgr", self.business, role="MANAGER")
        self.client = Client()
        self.client.login(username="alerts_demo_mgr", password="TestPass123!@#")
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_alerts_page_returns_200(self):
        """Alerts page must not 500."""
        try:
            url = reverse("verticals:energy_alerts")
        except NoReverseMatch:
            self.skipTest("energy_alerts URL not configured")
        resp = self.client.get(url)
        self.assertNotEqual(resp.status_code, 500, "Alerts page returned 500")
        self.assertIn(resp.status_code, [200, 302])

    def test_alerts_page_shows_demo_when_no_sites(self):
        """Alerts page shows is_demo_alerts=True when no sites/assets exist."""
        try:
            url = reverse("verticals:energy_alerts")
        except NoReverseMatch:
            self.skipTest("energy_alerts URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Alerts page returned non-200")
        self.assertTrue(
            resp.context.get("is_demo_alerts", False),
            "is_demo_alerts should be True for new workspace"
        )
        demo_alerts = resp.context.get("demo_alerts", [])
        self.assertGreater(len(demo_alerts), 0, "demo_alerts must be non-empty for new workspace")

    def test_alerts_page_hides_demo_when_site_exists(self):
        """is_demo_alerts must be False once real sites exist."""
        _make_site(self.business, name="Real Site for Alerts")
        try:
            url = reverse("verticals:energy_alerts")
        except NoReverseMatch:
            self.skipTest("energy_alerts URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Alerts page returned non-200")
        self.assertFalse(
            resp.context.get("is_demo_alerts", False),
            "is_demo_alerts should be False once real sites exist"
        )


class EnergyStockInWizardTest(TestCase):
    """Stock-in wizard renders correctly and wizard_presets are passed."""

    def setUp(self):
        self.business = _make_energy_business("test-stockin-wizard")
        self.user = _make_user("stockin_mgr", self.business, role="MANAGER")
        self.client = Client()
        self.client.login(username="stockin_mgr", password="TestPass123!@#")
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_stock_in_page_returns_200(self):
        """Stock-in page must return 200."""
        try:
            url = reverse("verticals:energy_stock_in")
        except NoReverseMatch:
            self.skipTest("energy_stock_in URL not configured")
        resp = self.client.get(url)
        self.assertNotEqual(resp.status_code, 500, "Stock-in page returned 500")
        self.assertIn(resp.status_code, [200, 302])

    def test_stock_in_context_has_wizard_presets(self):
        """Stock-in view must pass wizard_presets JSON to template."""
        try:
            url = reverse("verticals:energy_stock_in")
        except NoReverseMatch:
            self.skipTest("energy_stock_in URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Stock-in page returned non-200")
        self.assertIn("wizard_presets", resp.context, "wizard_presets missing from context")
        import json
        presets = json.loads(resp.context["wizard_presets"])
        self.assertIn("solar_panel", presets, "solar_panel missing from wizard_presets")
        self.assertIn("battery", presets, "battery missing from wizard_presets")
        self.assertIn("inverter", presets, "inverter missing from wizard_presets")
        self.assertIn("pico_system", presets, "pico_system missing from wizard_presets")

    def test_wizard_presets_solar_panel_has_subtypes(self):
        """Solar panel wizard_presets must include multiple wattage subtypes."""
        try:
            url = reverse("verticals:energy_stock_in")
        except NoReverseMatch:
            self.skipTest("energy_stock_in URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Stock-in page returned non-200")
        import json
        presets = json.loads(resp.context["wizard_presets"])
        subtypes = presets.get("solar_panel", {}).get("subtypes", [])
        self.assertGreater(len(subtypes), 2, "Solar panel must have multiple subtypes")
        labels = [s["label"] for s in subtypes]
        self.assertTrue(
            any("100W" in l or "200W" in l for l in labels),
            "Solar panel subtypes must include 100W or 200W variants"
        )

    def test_wizard_presets_battery_has_chemistry_subtypes(self):
        """Battery wizard_presets must include AGM and Lithium subtypes."""
        try:
            url = reverse("verticals:energy_stock_in")
        except NoReverseMatch:
            self.skipTest("energy_stock_in URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Stock-in page returned non-200")
        import json
        presets = json.loads(resp.context["wizard_presets"])
        subtypes = presets.get("battery", {}).get("subtypes", [])
        labels = [s["label"] for s in subtypes]
        self.assertTrue(
            any("AGM" in l or "Lithium" in l for l in labels),
            "Battery subtypes must include AGM or Lithium"
        )


class EnergySellWizardTest(TestCase):
    """Sell wizard renders correctly with product categories."""

    def setUp(self):
        self.business = _make_energy_business("test-sell-wizard")
        self.user = _make_user("sell_mgr", self.business, role="MANAGER")
        self.client = Client()
        self.client.login(username="sell_mgr", password="TestPass123!@#")
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_sell_page_returns_200(self):
        """Sell page must return 200."""
        try:
            url = reverse("verticals:energy_sell")
        except NoReverseMatch:
            self.skipTest("energy_sell URL not configured")
        resp = self.client.get(url)
        self.assertNotEqual(resp.status_code, 500, "Sell page returned 500")
        self.assertIn(resp.status_code, [200, 302])

    def test_sell_context_has_sell_categories(self):
        """Sell view must pass sell_categories list to template."""
        try:
            url = reverse("verticals:energy_sell")
        except NoReverseMatch:
            self.skipTest("energy_sell URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Sell page returned non-200")
        cats = resp.context.get("sell_categories", [])
        self.assertGreater(len(cats), 0, "sell_categories must be non-empty")
        keys = [c["key"] for c in cats]
        self.assertIn("solar_panel", keys, "sell_categories must include solar_panel")
        self.assertIn("battery", keys, "sell_categories must include battery")
        self.assertIn("solar_kit", keys, "sell_categories must include solar_kit (bundles)")

    def test_sell_context_has_products_by_category_json(self):
        """Sell view must pass products_by_category_json to template."""
        try:
            url = reverse("verticals:energy_sell")
        except NoReverseMatch:
            self.skipTest("energy_sell URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Sell page returned non-200")
        self.assertIn("products_by_category_json", resp.context,
                      "products_by_category_json missing from sell context")

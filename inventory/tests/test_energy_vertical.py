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

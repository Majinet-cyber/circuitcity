# inventory/tests/test_phase2.py
"""
Phase 2 comprehensive tests covering:
- Energy: Scenario comparison, proposal lifecycle, advanced financials, copilot, portfolio
- Cross-vertical: Business OS dashboard
- Welding: Workshop intelligence, client analytics, production insights
- Groceries: Inventory intelligence, sales analytics, smart restocking
- Sidebar updates for all verticals
- URL routing for all new views
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

def _biz(kind, slug=None):
    return Business.objects.create(
        name=f"Test {kind.title()} Co",
        slug=slug or f"test-{kind}",
        status="ACTIVE",
        business_kind=kind,
    )


def _user(username, business=None, role="MANAGER"):
    u = User.objects.create_user(username=username, email=f"{username}@test.com", password="Pass123!@#")
    if business:
        Membership.objects.create(user=u, business=business, role=role, status="ACTIVE")
    return u


def _login(client, user, business):
    client.login(username=user.username, password="Pass123!@#")
    session = client.session
    session["active_business_id"] = business.pk
    session.save()


# ===========================================================================
# ENERGY PHASE 2 TESTS
# ===========================================================================

class EnergyAdvancedFinancialsTest(TestCase):
    """Test NPV, IRR, sensitivity analysis in sizing engine."""

    def setUp(self):
        self.biz = _biz("energy")
        self.user = _user("efin_mgr", self.biz)

    def test_compute_sizing_produces_npv_and_irr(self):
        from inventory.models_energy import SystemSizingRun, SizingAppliance
        from inventory.services.energy_sizing import compute_sizing

        run = SystemSizingRun.objects.create(
            business=self.biz, title="NPV Test Run", version=1,
            peak_sun_hours=Decimal("5.0"), panel_wattage=550,
            battery_dod_pct=80, autonomy_days=Decimal("1.0"),
            discount_rate_pct=Decimal("10.0"),
            tariff_escalation_pct=Decimal("5.0"),
        )
        SizingAppliance.objects.create(
            sizing_run=run, name="LED Lights", quantity=10,
            wattage=Decimal("20"), hours_per_day=Decimal("8"),
        )
        SizingAppliance.objects.create(
            sizing_run=run, name="Fridge", quantity=1,
            wattage=Decimal("150"), hours_per_day=Decimal("24"),
            is_critical=True, usage_period="both",
        )

        result = compute_sizing(run)
        self.assertTrue(result["ok"])

        run.refresh_from_db()
        self.assertIsNotNone(run.npv)
        self.assertIsNotNone(run.irr_pct)
        self.assertIsNotNone(run.sensitivity_summary)
        self.assertIn("pessimistic", run.sensitivity_summary)
        self.assertIn("base", run.sensitivity_summary)
        self.assertIn("optimistic", run.sensitivity_summary)

    def test_growth_headroom_and_unmet_load_risk(self):
        from inventory.models_energy import SystemSizingRun, SizingAppliance
        from inventory.services.energy_sizing import compute_sizing

        run = SystemSizingRun.objects.create(
            business=self.biz, title="Headroom Test", version=1,
        )
        SizingAppliance.objects.create(
            sizing_run=run, name="Laptop", quantity=5,
            wattage=Decimal("65"), hours_per_day=Decimal("10"),
        )
        result = compute_sizing(run)
        self.assertTrue(result["ok"])
        run.refresh_from_db()
        self.assertIsNotNone(run.growth_headroom_pct)


class ScenarioComparisonTest(TestCase):
    """Test scenario comparison engine."""

    def setUp(self):
        self.biz = _biz("energy", slug="scn-energy")
        self.user = _user("scn_mgr", self.biz)

    def test_create_scenario_group(self):
        from inventory.models_energy import SystemSizingRun, SizingAppliance
        from inventory.services.energy_sizing import create_scenario_group

        base = SystemSizingRun.objects.create(
            business=self.biz, title="Scenario Base", version=1,
        )
        SizingAppliance.objects.create(
            sizing_run=base, name="AC", quantity=2,
            wattage=Decimal("1500"), hours_per_day=Decimal("8"),
        )

        scenarios = create_scenario_group(base)
        self.assertGreaterEqual(len(scenarios), 3)

        base.refresh_from_db()
        self.assertTrue(len(base.scenario_group) > 0)

        recommended = [s for s in scenarios if s.is_recommended_scenario]
        self.assertEqual(len(recommended), 1)

    def test_get_scenario_comparison(self):
        from inventory.models_energy import SystemSizingRun
        from inventory.services.energy_sizing import get_scenario_comparison

        result = get_scenario_comparison("nonexistent-group")
        self.assertEqual(result, [])


class ProposalLifecycleTest(TestCase):
    """Test proposal status transitions."""

    def setUp(self):
        self.biz = _biz("energy", slug="prop-energy")
        self.user = _user("prop_mgr", self.biz)
        self.client = Client()
        _login(self.client, self.user, self.biz)

    def test_proposal_status_field_exists(self):
        from inventory.models_energy import SystemSizingRun
        run = SystemSizingRun.objects.create(
            business=self.biz, title="Proposal Test", version=1,
        )
        self.assertEqual(run.proposal_status, "sizing")

    def test_proposal_send_action(self):
        from inventory.models_energy import SystemSizingRun, SizingAppliance
        run = SystemSizingRun.objects.create(
            business=self.biz, title="Send Test", version=1,
            customer_name="John Doe",
        )
        SizingAppliance.objects.create(
            sizing_run=run, name="Lights", quantity=5,
            wattage=Decimal("20"), hours_per_day=Decimal("8"),
        )
        resp = self.client.post(
            reverse("verticals:energy_proposal_update", args=[run.id]),
            {"action": "send_proposal"},
        )
        self.assertEqual(resp.status_code, 302)
        run.refresh_from_db()
        self.assertEqual(run.proposal_status, "proposal_sent")
        self.assertIsNotNone(run.proposal_sent_date)

    def test_convert_to_project_creates_site(self):
        from inventory.models_energy import SystemSizingRun, EnergySite
        run = SystemSizingRun.objects.create(
            business=self.biz, title="Project Conv", version=1,
            customer_name="Jane Doe", proposal_status="approved",
            recommended_array_kw=Decimal("5.0"),
            estimated_capex=Decimal("5000000"),
        )
        self.client.post(
            reverse("verticals:energy_proposal_update", args=[run.id]),
            {"action": "convert_to_project"},
        )
        run.refresh_from_db()
        self.assertEqual(run.proposal_status, "project")
        self.assertIsNotNone(run.linked_project_site)
        self.assertTrue(EnergySite.objects.filter(business=self.biz).exists())


class EnergyPhase2ViewTest(TestCase):
    """Smoke tests for all Phase 2 energy views."""

    def setUp(self):
        self.biz = _biz("energy", slug="ep2-energy")
        self.user = _user("ep2_mgr", self.biz)
        self.client = Client()
        _login(self.client, self.user, self.biz)

    def _get(self, name, **kwargs):
        try:
            url = reverse(name, kwargs=kwargs)
            return self.client.get(url)
        except NoReverseMatch:
            self.skipTest(f"URL {name} not found")

    def test_portfolio_view(self):
        resp = self._get("verticals:energy_portfolio")
        self.assertIn(resp.status_code, [200, 302])

    def test_copilot_view(self):
        resp = self._get("verticals:energy_copilot")
        self.assertIn(resp.status_code, [200, 302])

    def test_data_upload_view(self):
        resp = self._get("verticals:energy_data_upload")
        self.assertIn(resp.status_code, [200, 302])


class CopilotServiceTest(TestCase):
    """Test copilot insight generation."""

    def setUp(self):
        self.biz = _biz("energy", slug="cop-energy")

    def test_generates_insights_empty(self):
        from inventory.services.energy_copilot import generate_copilot_insights
        insights = generate_copilot_insights(self.biz)
        self.assertIsInstance(insights, list)

    def test_generates_insights_with_data(self):
        from inventory.models_energy import EnergySite, EnergyAsset
        from inventory.services.energy_copilot import generate_copilot_insights

        site = EnergySite.objects.create(
            business=self.biz, name="Copilot Site", status="active",
            installed_capacity_kw=Decimal("10"),
        )
        EnergyAsset.objects.create(
            site=site, business=self.biz, asset_type="battery",
            health_score=40, status="degraded",
        )
        insights = generate_copilot_insights(self.biz)
        self.assertGreater(len(insights), 0)
        categories = [i["category"] for i in insights]
        self.assertIn("maintenance", categories)


# ===========================================================================
# BUSINESS OS DASHBOARD TESTS
# ===========================================================================

class BusinessOSServiceTest(TestCase):
    """Test cross-vertical Business OS analytics service."""

    def setUp(self):
        self.biz = _biz("energy", slug="bos-energy")

    def test_returns_metrics_dict(self):
        from inventory.services.business_os import get_business_os_metrics
        metrics = get_business_os_metrics(self.biz)
        self.assertIn("business", metrics)
        self.assertIn("verticals_active", metrics)
        self.assertIn("insights", metrics)
        self.assertIn("vertical_metrics", metrics)

    def test_energy_metrics_populated(self):
        from inventory.models_energy import EnergySite
        from inventory.services.business_os import get_business_os_metrics

        EnergySite.objects.create(
            business=self.biz, name="BOS Site", status="active",
            installed_capacity_kw=Decimal("5"),
        )
        metrics = get_business_os_metrics(self.biz)
        self.assertIn("energy", metrics["verticals_active"])
        self.assertIn("energy", metrics["vertical_metrics"])


class BusinessOSViewTest(TestCase):
    """Test Business OS dashboard view."""

    def setUp(self):
        self.biz = _biz("energy", slug="bosv-energy")
        self.user = _user("bosv_mgr", self.biz)
        self.client = Client()
        _login(self.client, self.user, self.biz)

    def test_dashboard_renders(self):
        resp = self.client.get(reverse("dashboard:business_os"))
        self.assertIn(resp.status_code, [200, 302])


# ===========================================================================
# WELDING PHASE 2 TESTS
# ===========================================================================

class WeldingIntelligenceServiceTest(TestCase):
    """Test welding workshop intelligence service."""

    def setUp(self):
        self.biz = _biz("welding", slug="wi-weld")

    def test_workshop_intelligence_empty(self):
        from inventory.services.welding_intelligence import get_workshop_intelligence
        data = get_workshop_intelligence(self.biz)
        self.assertIsInstance(data, dict)

    def test_client_analytics_empty(self):
        from inventory.services.welding_intelligence import get_client_analytics
        data = get_client_analytics(self.biz)
        self.assertIsInstance(data, dict)

    def test_production_insights_empty(self):
        from inventory.services.welding_intelligence import get_production_insights
        insights = get_production_insights(self.biz)
        self.assertIsInstance(insights, list)


class WeldingPhase2ViewTest(TestCase):
    """Smoke tests for welding Phase 2 views."""

    def setUp(self):
        self.biz = _biz("welding", slug="wv-weld")
        self.user = _user("wv_mgr", self.biz)
        self.client = Client()
        _login(self.client, self.user, self.biz)

    def test_intelligence_view(self):
        try:
            resp = self.client.get(reverse("verticals:welding_intelligence"))
            self.assertIn(resp.status_code, [200, 302])
        except NoReverseMatch:
            self.skipTest("URL not found")

    def test_clients_view(self):
        try:
            resp = self.client.get(reverse("verticals:welding_clients"))
            self.assertIn(resp.status_code, [200, 302])
        except NoReverseMatch:
            self.skipTest("URL not found")


class WeldingSidebarTest(TestCase):
    """Test welding sidebar includes new items."""

    def test_sidebar_has_intelligence_and_clients(self):
        from inventory.utils_verticals import get_vertical_sidebar_items
        items = get_vertical_sidebar_items("welding")
        keys = [i["key"] for i in items]
        self.assertIn("intelligence", keys)
        self.assertIn("clients", keys)


# ===========================================================================
# GROCERIES PHASE 2 TESTS
# ===========================================================================

class GroceriesIntelligenceServiceTest(TestCase):
    """Test groceries intelligence service."""

    def setUp(self):
        self.biz = _biz("grocery", slug="gi-groc")

    def test_inventory_intelligence_empty(self):
        from inventory.services.groceries_intelligence import get_inventory_intelligence
        data = get_inventory_intelligence(self.biz)
        self.assertIsInstance(data, dict)

    def test_sales_analytics_empty(self):
        from inventory.services.groceries_intelligence import get_sales_analytics
        data = get_sales_analytics(self.biz)
        self.assertIsInstance(data, dict)

    def test_restock_recommendations_empty(self):
        from inventory.services.groceries_intelligence import get_restock_recommendations
        data = get_restock_recommendations(self.biz)
        self.assertIsInstance(data, list)


class GroceriesPhase2ViewTest(TestCase):
    """Smoke tests for groceries Phase 2 views."""

    def setUp(self):
        self.biz = _biz("grocery", slug="gv-groc")
        self.user = _user("gv_mgr", self.biz)
        self.client = Client()
        _login(self.client, self.user, self.biz)

    def test_intelligence_view(self):
        try:
            resp = self.client.get(reverse("groceries:inventory_intelligence"))
            self.assertIn(resp.status_code, [200, 302])
        except NoReverseMatch:
            self.skipTest("URL not found")

    def test_sales_analytics_view(self):
        try:
            resp = self.client.get(reverse("groceries:sales_analytics"))
            self.assertIn(resp.status_code, [200, 302])
        except NoReverseMatch:
            self.skipTest("URL not found")

    def test_restocking_view(self):
        try:
            resp = self.client.get(reverse("groceries:smart_restocking"))
            self.assertIn(resp.status_code, [200, 302])
        except NoReverseMatch:
            self.skipTest("URL not found")


class GroceriesSidebarTest(TestCase):
    """Test groceries sidebar includes new items."""

    def test_sidebar_has_intelligence_items(self):
        from inventory.utils_verticals import get_vertical_sidebar_items
        items = get_vertical_sidebar_items("grocery")
        keys = [i["key"] for i in items]
        self.assertIn("intelligence", keys)
        self.assertIn("sales_analytics", keys)
        self.assertIn("restocking", keys)


# ===========================================================================
# ENERGY SIDEBAR PHASE 2 TEST
# ===========================================================================

class EnergySidebarPhase2Test(TestCase):
    """Test energy sidebar includes new Phase 2 items."""

    def test_sidebar_has_portfolio_copilot_upload(self):
        from inventory.utils_verticals import get_vertical_sidebar_items
        items = get_vertical_sidebar_items("energy")
        keys = [i["key"] for i in items]
        self.assertIn("portfolio", keys)
        self.assertIn("copilot", keys)
        self.assertIn("data_upload", keys)
        self.assertIn("sizing", keys)
        self.assertIn("monitoring", keys)


# ===========================================================================
# URL ROUTING REGRESSION TESTS
# ===========================================================================

class Phase2URLRoutingTest(TestCase):
    """Verify all Phase 2 URLs resolve without errors."""

    def test_energy_phase2_urls_resolve(self):
        url_names = [
            "verticals:energy_portfolio",
            "verticals:energy_copilot",
            "verticals:energy_data_upload",
        ]
        for name in url_names:
            try:
                url = reverse(name)
                self.assertTrue(url.startswith("/"))
            except NoReverseMatch:
                self.fail(f"URL '{name}' does not resolve")

    def test_welding_phase2_urls_resolve(self):
        url_names = [
            "verticals:welding_intelligence",
            "verticals:welding_clients",
        ]
        for name in url_names:
            try:
                url = reverse(name)
                self.assertTrue(url.startswith("/"))
            except NoReverseMatch:
                self.fail(f"URL '{name}' does not resolve")

    def test_groceries_phase2_urls_resolve(self):
        url_names = [
            "groceries:inventory_intelligence",
            "groceries:sales_analytics",
            "groceries:smart_restocking",
        ]
        for name in url_names:
            try:
                url = reverse(name)
                self.assertTrue(url.startswith("/"))
            except NoReverseMatch:
                self.fail(f"URL '{name}' does not resolve")

    def test_business_os_url_resolves(self):
        try:
            url = reverse("dashboard:business_os")
            self.assertTrue(url.startswith("/"))
        except NoReverseMatch:
            self.fail("dashboard:business_os does not resolve")


# ===========================================================================
# MODEL PHASE 2 TESTS
# ===========================================================================

class EnergyDataUploadModelTest(TestCase):
    """Test EnergyDataUpload model."""

    def setUp(self):
        self.biz = _biz("energy", slug="edu-energy")

    def test_create_upload_record(self):
        from inventory.models_energy import EnergyDataUpload
        upload = EnergyDataUpload.objects.create(
            business=self.biz,
            upload_type="csv",
            filename="readings.csv",
            rows_total=100,
            rows_imported=95,
            rows_skipped=5,
            data_quality_score=95,
        )
        self.assertEqual(str(upload), "readings.csv – 95/100 rows")
        self.assertEqual(upload.data_quality_score, 95)


class CopilotInsightModelTest(TestCase):
    """Test CopilotInsight model."""

    def setUp(self):
        self.biz = _biz("energy", slug="ci-energy")

    def test_create_insight(self):
        from inventory.models_energy import CopilotInsight
        insight = CopilotInsight.objects.create(
            business=self.biz,
            category="performance",
            severity="medium",
            title="Test insight",
            explanation="This is a test.",
        )
        self.assertIn("performance", str(insight))


class SystemSizingRunPhase2FieldsTest(TestCase):
    """Test new Phase 2 fields on SystemSizingRun."""

    def setUp(self):
        self.biz = _biz("energy", slug="ssf-energy")

    def test_proposal_lifecycle_fields(self):
        from inventory.models_energy import SystemSizingRun
        run = SystemSizingRun.objects.create(
            business=self.biz, title="Phase2 Fields", version=1,
            proposal_status="proposal_draft",
            scenario_group="SCN-ABC123",
            scenario_label="Balanced",
            discount_rate_pct=Decimal("12.0"),
            inflation_rate_pct=Decimal("9.0"),
        )
        self.assertEqual(run.proposal_status, "proposal_draft")
        self.assertEqual(run.scenario_group, "SCN-ABC123")
        self.assertEqual(run.discount_rate_pct, Decimal("12.0"))

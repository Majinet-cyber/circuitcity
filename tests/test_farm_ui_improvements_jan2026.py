# tests/test_farm_ui_improvements_jan2026.py
"""
REGRESSION TESTS: Farm UI Improvements (January 2026)

These tests ensure the Farm vertical UI improvements are locked in:
- A) Dashboard no longer shows 4 overlaying action buttons
- B) Dashboard has premium KPI cards and testids  
- C) Crops sidebar link and gamified crops index
- D) Livestock gamified cards and sales implemented
- E) Payment method as clickable cards
- F) Season status as premium cards
- G) Assets quick-pick cards with Malawi farm assets
- H) Locations GPS capture
- I) Expenses gamified category cards + fertiliser cards
- J) Smart Agronomy predictions (estimator exists)
- K) All tests locked in

This test file MUST FAIL if any of these features regress.
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from tenants.models import Business, Membership

User = get_user_model()


class FarmUITestBase(TestCase):
    """Base class for Farm UI tests with common setup."""

    def setUp(self):
        """Set up test data: Farm business + manager user."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="farm_ui_test@test.com",
            email="farm_ui_test@test.com",
            password="SecurePass123!",
        )
        self.business = Business.objects.create(
            name="Test Farm UI",
            slug="test-farm-ui",
            business_kind="farm",
            status="ACTIVE",
            created_by=self.user,
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )
        self.client.login(username="farm_ui_test@test.com", password="SecurePass123!")
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()


class TestFarmDashboardImprovements(FarmUITestBase):
    """Test Farm Dashboard UI improvements (A, B)."""

    def test_dashboard_loads(self):
        """Farm dashboard must load successfully."""
        response = self.client.get("/verticals/farm/dashboard/")
        self.assertEqual(response.status_code, 200)

    def test_dashboard_no_quick_actions_container(self):
        """Dashboard must NOT have quick-actions container."""
        response = self.client.get("/verticals/farm/dashboard/")
        content = response.content.decode("utf-8")
        self.assertNotIn('data-testid="farm-quick-actions"', content)

    def test_dashboard_has_kpis_testid(self):
        """Dashboard must have KPIs section with testid."""
        response = self.client.get("/verticals/farm/dashboard/")
        content = response.content.decode("utf-8")
        self.assertIn('data-testid="farm-kpis"', content)

    def test_dashboard_has_farm_dashboard_testid(self):
        """Dashboard must have main farm-dashboard testid."""
        response = self.client.get("/verticals/farm/dashboard/")
        content = response.content.decode("utf-8")
        self.assertIn('data-testid="farm-dashboard"', content)


class TestFarmCropsSidebar(FarmUITestBase):
    """Test Crops sidebar link (C)."""

    def test_sidebar_has_crops_link(self):
        """Farm sidebar must have 'Crops' navigation item."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        items = get_vertical_sidebar_items("farm")
        keys = [item["key"] for item in items]
        self.assertIn("crops", keys, "Sidebar must have 'crops' key")

    def test_sidebar_crops_label(self):
        """Farm sidebar must have 'Crops' label."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        items = get_vertical_sidebar_items("farm")
        labels = [item["label"] for item in items]
        self.assertIn("Crops", labels, "Sidebar must have 'Crops' label")


class TestFarmCropsIndex(FarmUITestBase):
    """Test Crops index page gamified cards (C)."""

    def test_crops_index_loads(self):
        """Crops index page must load successfully."""
        response = self.client.get("/verticals/farm/crops/")
        self.assertEqual(response.status_code, 200)

    def test_crops_index_has_page_testid(self):
        """Crops index must have page testid."""
        response = self.client.get("/verticals/farm/crops/")
        content = response.content.decode("utf-8")
        self.assertIn('data-testid="farm-crops-page"', content)

    def test_crops_index_has_category_cards(self):
        """Crops index must have crop category sections."""
        response = self.client.get("/verticals/farm/crops/")
        content = response.content.decode("utf-8")
        # Check for crop categories
        self.assertIn('data-testid="crop-category-staples"', content)
        self.assertIn('data-testid="crop-category-legumes"', content)

    def test_crops_index_has_individual_crop_cards(self):
        """Crops index must have individual crop cards."""
        response = self.client.get("/verticals/farm/crops/")
        content = response.content.decode("utf-8")
        # Check for specific crops
        self.assertIn('data-testid="crop-card-maize"', content)
        self.assertIn('data-testid="crop-card-groundnuts"', content)


class TestFarmCropCreateFlow(FarmUITestBase):
    """Test Crop create flow with premium cards and Smart Agronomy (C, F, J)."""

    def test_crop_create_loads(self):
        """Crop create page must load successfully."""
        response = self.client.get("/verticals/farm/crops/add-season/")
        self.assertEqual(response.status_code, 200)

    def test_crop_create_has_form_testid(self):
        """Crop create must have form testid."""
        response = self.client.get("/verticals/farm/crops/add-season/")
        content = response.content.decode("utf-8")
        self.assertIn('data-testid="farm-season-form"', content)

    def test_crop_create_has_crop_type_selector(self):
        """Crop create must have crop type card selector."""
        response = self.client.get("/verticals/farm/crops/add-season/")
        content = response.content.decode("utf-8")
        self.assertIn('data-testid="crop-type-selector"', content)

    def test_crop_create_has_status_card_selector(self):
        """Crop create must have status card selector (not dropdown)."""
        response = self.client.get("/verticals/farm/crops/add-season/")
        content = response.content.decode("utf-8")
        self.assertIn('data-testid="status-card-selector"', content)

    def test_crop_create_has_smart_agronomy_panel(self):
        """Crop create must have Smart Agronomy panel."""
        response = self.client.get("/verticals/farm/crops/add-season/")
        content = response.content.decode("utf-8")
        self.assertIn('data-testid="smart-agronomy-panel"', content)

    def test_crop_create_has_apply_recommendations_btn(self):
        """Crop create must have Apply Recommendations button."""
        response = self.client.get("/verticals/farm/crops/add-season/")
        content = response.content.decode("utf-8")
        self.assertIn('data-testid="apply-recommendations-btn"', content)


class TestFarmLivestockSales(FarmUITestBase):
    """Test Livestock sales gamified cards (D)."""

    def test_livestock_sales_loads(self):
        """Livestock sales page must load successfully."""
        response = self.client.get("/verticals/farm/sales/livestock/")
        self.assertEqual(response.status_code, 200)

    def test_livestock_sales_has_page_testid(self):
        """Livestock sales must have page testid."""
        response = self.client.get("/verticals/farm/sales/livestock/")
        content = response.content.decode("utf-8")
        self.assertIn('data-testid="farm-livestock-sales-page"', content)

    def test_livestock_sales_not_coming_soon(self):
        """Livestock sales must NOT say 'Coming Soon'."""
        response = self.client.get("/verticals/farm/sales/livestock/")
        content = response.content.decode("utf-8")
        self.assertNotIn("Coming Soon", content)

    def test_livestock_sales_has_type_cards(self):
        """Livestock sales must have livestock type cards."""
        response = self.client.get("/verticals/farm/sales/livestock/")
        content = response.content.decode("utf-8")
        self.assertIn('data-testid="livestock-type-cards"', content)

    def test_livestock_sales_has_individual_cards(self):
        """Livestock sales must have individual livestock cards."""
        response = self.client.get("/verticals/farm/sales/livestock/")
        content = response.content.decode("utf-8")
        self.assertIn('data-testid="livestock-card-chickens"', content)
        self.assertIn('data-testid="livestock-card-pigs"', content)
        self.assertIn('data-testid="livestock-card-goats"', content)

    def test_livestock_sales_has_payment_cards(self):
        """Livestock sales must have payment method cards."""
        response = self.client.get("/verticals/farm/sales/livestock/")
        content = response.content.decode("utf-8")
        self.assertIn('data-testid="payment-method-cards"', content)


class TestFarmExpensesGamified(FarmUITestBase):
    """Test Expenses gamified category cards (I)."""

    def test_expenses_landing_loads(self):
        """Expenses landing page must load successfully."""
        response = self.client.get("/verticals/farm/expenses/")
        self.assertEqual(response.status_code, 200)

    def test_expenses_has_page_testid(self):
        """Expenses must have page testid."""
        response = self.client.get("/verticals/farm/expenses/")
        content = response.content.decode("utf-8")
        self.assertIn('data-testid="farm-expenses-page"', content)

    def test_expenses_has_category_cards(self):
        """Expenses must have category cards."""
        response = self.client.get("/verticals/farm/expenses/")
        content = response.content.decode("utf-8")
        self.assertIn('data-testid="expense-category-cards"', content)

    def test_expenses_has_individual_category_cards(self):
        """Expenses must have individual category cards."""
        response = self.client.get("/verticals/farm/expenses/")
        content = response.content.decode("utf-8")
        self.assertIn('data-testid="expense-card-labour"', content)
        self.assertIn('data-testid="expense-card-inputs"', content)
        self.assertIn('data-testid="expense-card-fuel"', content)

    def test_expenses_has_fertiliser_panel(self):
        """Expenses must have fertiliser sub-cards panel."""
        response = self.client.get("/verticals/farm/expenses/")
        content = response.content.decode("utf-8")
        self.assertIn('data-testid="fertiliser-cards-panel"', content)

    def test_expenses_has_fertiliser_cards(self):
        """Expenses must have specific fertiliser cards."""
        response = self.client.get("/verticals/farm/expenses/")
        content = response.content.decode("utf-8")
        self.assertIn('data-testid="fertiliser-card-urea"', content)
        self.assertIn('data-testid="fertiliser-card-npk"', content)


class TestFarmAssetsQuickPick(FarmUITestBase):
    """Test Assets quick-pick cards (G)."""

    def test_assets_landing_loads(self):
        """Assets landing page must load successfully."""
        response = self.client.get("/verticals/farm/assets/")
        self.assertEqual(response.status_code, 200)

    def test_assets_has_page_testid(self):
        """Assets must have page testid."""
        response = self.client.get("/verticals/farm/assets/")
        content = response.content.decode("utf-8")
        self.assertIn('data-testid="farm-assets-page"', content)

    def test_assets_not_coming_soon(self):
        """Assets page must NOT say 'Coming Soon'."""
        response = self.client.get("/verticals/farm/assets/")
        content = response.content.decode("utf-8")
        self.assertNotIn("Coming Soon", content)

    def test_assets_has_category_sections(self):
        """Assets must have category sections."""
        response = self.client.get("/verticals/farm/assets/")
        content = response.content.decode("utf-8")
        self.assertIn('data-testid="asset-category-equipment"', content)
        self.assertIn('data-testid="asset-category-tools"', content)
        self.assertIn('data-testid="asset-category-storage"', content)

    def test_assets_has_malawi_farm_assets(self):
        """Assets must have common Malawi farm assets."""
        response = self.client.get("/verticals/farm/assets/")
        content = response.content.decode("utf-8")
        # Check for required assets
        self.assertIn('data-testid="asset-card-tractor"', content)
        self.assertIn('data-testid="asset-card-ox-plough"', content)
        self.assertIn('data-testid="asset-card-hoe"', content)
        self.assertIn('data-testid="asset-card-sprayer"', content)
        self.assertIn('data-testid="asset-card-water-tank"', content)


class TestFarmLocationsGPS(FarmUITestBase):
    """Test Locations GPS capture (H)."""

    def test_locations_list_loads(self):
        """Locations list page must load successfully."""
        response = self.client.get("/verticals/farm/locations/")
        self.assertEqual(response.status_code, 200)

    def test_locations_create_loads(self):
        """Locations create page must load successfully."""
        response = self.client.get("/verticals/farm/locations/create/")
        self.assertEqual(response.status_code, 200)

    def test_locations_form_has_gps_section(self):
        """Locations form must have GPS section."""
        response = self.client.get("/verticals/farm/locations/create/")
        content = response.content.decode("utf-8")
        self.assertIn('data-testid="gps-section"', content)

    def test_locations_form_has_use_gps_button(self):
        """Locations form must have 'Use GPS' button."""
        response = self.client.get("/verticals/farm/locations/create/")
        content = response.content.decode("utf-8")
        self.assertIn('data-testid="use-gps-btn"', content)

    def test_locations_form_has_lat_lng_fields(self):
        """Locations form must have latitude/longitude fields."""
        response = self.client.get("/verticals/farm/locations/create/")
        content = response.content.decode("utf-8")
        self.assertIn('name="latitude"', content)
        self.assertIn('name="longitude"', content)


class TestSmartAgronomyModule(TestCase):
    """Test Smart Agronomy estimator module (J)."""

    def test_agronomy_module_exists(self):
        """Smart Agronomy module must exist."""
        try:
            from inventory.services.farm_agronomy import get_crop_recommendation
            self.assertTrue(True)
        except ImportError:
            self.fail("farm_agronomy module must exist")

    def test_agronomy_get_maize_recommendation(self):
        """Agronomy must return maize recommendations."""
        from inventory.services.farm_agronomy import get_crop_recommendation
        rec = get_crop_recommendation("maize")
        self.assertEqual(rec.crop_code, "maize")
        self.assertIsNotNone(rec.yield_estimate)
        self.assertIsNotNone(rec.fertiliser_recommendation)

    def test_agronomy_estimate_yield(self):
        """Agronomy must estimate yield for given acres."""
        from decimal import Decimal
        from inventory.services.farm_agronomy import estimate_yield_for_acres
        result = estimate_yield_for_acres("maize", Decimal("2"))
        self.assertIn("low_estimate", result)
        self.assertIn("high_estimate", result)
        self.assertIn("disclaimer", result)

    def test_agronomy_estimate_fertiliser(self):
        """Agronomy must estimate fertiliser for given acres."""
        from decimal import Decimal
        from inventory.services.farm_agronomy import estimate_fertiliser_for_acres
        result = estimate_fertiliser_for_acres("maize", Decimal("2"))
        self.assertIn("stages", result)
        self.assertIn("total_kg_low", result)
        self.assertIn("disclaimer", result)

    def test_agronomy_has_malawi_crops(self):
        """Agronomy must have common Malawi crops."""
        from inventory.services.farm_agronomy import CROP_RECOMMENDATIONS
        self.assertIn("maize", CROP_RECOMMENDATIONS)
        self.assertIn("soya", CROP_RECOMMENDATIONS)
        self.assertIn("groundnuts", CROP_RECOMMENDATIONS)
        self.assertIn("tobacco", CROP_RECOMMENDATIONS)


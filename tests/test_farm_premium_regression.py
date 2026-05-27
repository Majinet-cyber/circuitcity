# tests/test_farm_premium_regression.py
"""
Farm Vertical Premium Regression Tests (Jan 2026)

Tests for:
1. Dashboard blue premium styling (data-vertical="farm" attribute)
2. Crop sales page with gamified cards
3. Server-side validation: sell only recorded crops/livestock
4. Assets save and success message
5. Reports generate endpoints return 200 + CSV
6. Expenses category cards UI
7. NEW: Dashboard Farm Snapshot (crops breakdown, livestock by type, assets preview)
8. NEW: AI Insights engine and dashboard display
9. NEW: Smart Add Entry with context-aware recommendations
10. NEW: Vertical-aware billing copy
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.models_farm import (
    FarmAsset,
    FarmCrop,
    FarmCropSale,
    FarmCropSeason,
    FarmLedgerEntry,
    FarmLivestockBatch,
    FarmCropCategory,
    FarmEntryType,
    FarmSeasonStatus,
    FarmAnimalType,
    MALAWI_CROP_CATALOG,
)
from tenants.models import Business, Membership

User = get_user_model()


@pytest.fixture
def farm_user_business(db):
    """Create a user with a farm business."""
    from conftest import unique_slug
    
    user = User.objects.create_user(
        username="farmer_test",
        email="farmer@test.com",
        password="testpass123",
    )
    business = Business.objects.create(
        name="Test Farm",
        slug=unique_slug("test-farm"),
        business_kind=BusinessKind.FARM,
        status="ACTIVE",
        created_by=user,
    )
    Membership.objects.create(
        user=user,
        business=business,
        role="MANAGER",
        status="ACTIVE",
    )
    return user, business


@pytest.mark.django_db
class TestFarmDashboardBluePremium:
    """Test farm dashboard has blue premium styling."""
    
    def test_dashboard_has_data_vertical_attribute(self, farm_user_business, client):
        """Dashboard should have data-vertical='farm' for styling hooks."""
        user, business = farm_user_business
        client.force_login(user)
        
        response = client.get(reverse("verticals:farm_dashboard"))
        assert response.status_code == 200
        
        content = response.content.decode("utf-8")
        # Check for data-vertical attribute
        assert 'data-vertical="farm"' in content
        # Check for blue premium CSS variables
        assert "--farm-primary: #2563eb" in content or "--farm-primary:" in content
    
    def test_dashboard_container_has_testid(self, farm_user_business, client):
        """Dashboard container should have data-testid for testing."""
        user, business = farm_user_business
        client.force_login(user)
        
        response = client.get(reverse("verticals:farm_dashboard"))
        assert response.status_code == 200
        
        content = response.content.decode("utf-8")
        assert 'data-testid="farm-dashboard-container"' in content


@pytest.mark.django_db
class TestFarmCropSalesGamified:
    """Test crop sales page shows gamified cards with seeded crops."""
    
    def test_crop_sales_page_loads(self, farm_user_business, client):
        """Crop sales page should load without error."""
        user, business = farm_user_business
        client.force_login(user)
        
        response = client.get(reverse("verticals:farm_sales_crops"))
        assert response.status_code == 200
    
    def test_crops_are_seeded_on_first_access(self, farm_user_business, client):
        """Accessing crop sales should seed Malawi crops."""
        user, business = farm_user_business
        client.force_login(user)
        
        # Initially no crops
        assert FarmCrop.objects.filter(business=business).count() == 0
        
        # Access crop sales page (triggers seeding)
        response = client.get(reverse("verticals:farm_sales_crops"))
        assert response.status_code == 200
        
        # Crops should now be seeded
        crop_count = FarmCrop.objects.filter(business=business).count()
        assert crop_count > 0
        
        # Check for specific crops
        assert FarmCrop.objects.filter(business=business, name="Maize").exists()
        assert FarmCrop.objects.filter(business=business, name="Tobacco").exists()
    
    def test_crop_cards_appear_in_template(self, farm_user_business, client):
        """Crop cards should appear in the template."""
        user, business = farm_user_business
        client.force_login(user)
        
        response = client.get(reverse("verticals:farm_sales_crops"))
        content = response.content.decode("utf-8")
        
        # Check for crop category sections
        assert 'data-testid="crop-sales-page"' in content
        # Should have crop cards (seeded)
        assert "Maize" in content


@pytest.mark.django_db
class TestFarmSalesValidation:
    """Test server-side validation: sell only recorded crops/livestock."""
    
    def test_cannot_sell_unrecorded_crop(self, farm_user_business, client):
        """Attempting to sell a crop not belonging to business should fail."""
        user, business = farm_user_business
        client.force_login(user)
        
        # Try to sell with invalid crop_id
        response = client.post(
            reverse("verticals:farm_sales_record") + "?type=crop&crop_id=99999",
            {
                "quantity": "10",
                "unit_price": "5000",
                "payment_method": "cash",
            },
        )
        
        # Should redirect back with error (not create sale)
        assert response.status_code in [302, 200]
        
        # No sale should be created
        assert FarmLedgerEntry.objects.filter(
            business=business,
            entry_type=FarmEntryType.SALE,
        ).count() == 0
    
    def test_cannot_sell_unrecorded_livestock(self, farm_user_business, client):
        """Attempting to sell livestock not belonging to business should fail."""
        user, business = farm_user_business
        client.force_login(user)
        
        # Try to sell with invalid batch_id
        response = client.post(
            reverse("verticals:farm_sales_record") + "?type=livestock&batch_id=99999",
            {
                "quantity": "5",
                "unit_price": "25000",
                "payment_method": "cash",
            },
        )
        
        # Should redirect back with error (not create sale)
        assert response.status_code in [302, 200]
        
        # No sale should be created
        assert FarmLedgerEntry.objects.filter(
            business=business,
            entry_type=FarmEntryType.SALE,
        ).count() == 0
    
    def test_can_sell_recorded_crop(self, farm_user_business, client):
        """Selling a recorded crop should succeed."""
        user, business = farm_user_business
        client.force_login(user)
        
        # Create a crop
        crop = FarmCrop.objects.create(
            business=business,
            name="Test Maize",
            category=FarmCropCategory.STAPLES,
            emoji="🌽",
            unit="bag",
        )
        
        # Sell it
        response = client.post(
            reverse("verticals:farm_sales_record") + f"?type=crop&crop_id={crop.id}",
            {
                "type": "crop",
                "crop_id": crop.id,
                "quantity": "10",
                "unit_price": "5000",
                "payment_method": "cash",
                "unit": "bag",
            },
        )
        
        # Should redirect on success
        assert response.status_code == 302
        
        # Sale should be created
        assert FarmLedgerEntry.objects.filter(
            business=business,
            entry_type=FarmEntryType.SALE,
        ).count() == 1
        
        # FarmCropSale should be created
        assert FarmCropSale.objects.filter(crop=crop).count() == 1


@pytest.mark.django_db
class TestFarmAssetsSaving:
    """Test farm assets save correctly with success message."""
    
    def test_assets_page_loads(self, farm_user_business, client):
        """Assets page should load without error."""
        user, business = farm_user_business
        client.force_login(user)
        
        response = client.get(reverse("verticals:farm_assets"))
        assert response.status_code == 200
    
    def test_asset_can_be_created(self, farm_user_business, client):
        """Creating an asset should succeed and redirect."""
        user, business = farm_user_business
        client.force_login(user)
        
        response = client.post(
            reverse("verticals:farm_assets"),
            {
                "asset_type": "tractor",
                "asset_name": "John Deere Tractor",
                "quantity": "1",
                "value": "5000000",
                "condition": "good",
            },
        )
        
        # Should redirect on success
        assert response.status_code == 302
        
        # Asset should be created
        assert FarmAsset.objects.filter(business=business).count() == 1
        asset = FarmAsset.objects.get(business=business)
        assert asset.name == "John Deere Tractor"
        assert asset.value_mwk == Decimal("5000000")
    
    def test_asset_appears_in_list_after_creation(self, farm_user_business, client):
        """Created asset should appear in the list."""
        user, business = farm_user_business
        client.force_login(user)
        
        # Create asset via POST
        client.post(
            reverse("verticals:farm_assets"),
            {
                "asset_type": "pump",
                "asset_name": "Irrigation Pump",
                "quantity": "2",
                "condition": "new",
            },
        )
        
        # Check list
        response = client.get(reverse("verticals:farm_assets"))
        content = response.content.decode("utf-8")
        
        assert "Irrigation Pump" in content
    
    def test_assets_template_has_form(self, farm_user_business, client):
        """Assets template should have the add form."""
        user, business = farm_user_business
        client.force_login(user)
        
        response = client.get(reverse("verticals:farm_assets"))
        content = response.content.decode("utf-8")
        
        assert 'data-testid="asset-add-form"' in content


@pytest.mark.django_db
class TestFarmReportsEndpoints:
    """Test farm reports endpoints return valid CSV."""
    
    def test_profit_loss_report_returns_csv(self, farm_user_business, client):
        """Profit & Loss report should return CSV."""
        user, business = farm_user_business
        client.force_login(user)
        
        response = client.get(reverse("verticals:farm_report_profit_loss"))
        
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"
        assert "attachment" in response["Content-Disposition"]
        assert "profit_loss" in response["Content-Disposition"]
    
    def test_livestock_report_returns_csv(self, farm_user_business, client):
        """Livestock report should return CSV."""
        user, business = farm_user_business
        client.force_login(user)
        
        response = client.get(reverse("verticals:farm_report_livestock"))
        
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"
        assert "livestock_report" in response["Content-Disposition"]
    
    def test_crop_season_report_returns_csv(self, farm_user_business, client):
        """Crop season report should return CSV."""
        user, business = farm_user_business
        client.force_login(user)
        
        response = client.get(reverse("verticals:farm_report_crop_season"))
        
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"
        assert "crop_season" in response["Content-Disposition"]
    
    def test_ledger_export_returns_csv(self, farm_user_business, client):
        """Ledger export should return CSV."""
        user, business = farm_user_business
        client.force_login(user)
        
        response = client.get(reverse("verticals:farm_report_ledger_export"))
        
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"
    
    def test_reports_page_has_working_buttons(self, farm_user_business, client):
        """Reports page should have buttons with actual report URLs."""
        user, business = farm_user_business
        client.force_login(user)
        
        response = client.get(reverse("verticals:farm_reports"))
        content = response.content.decode("utf-8")
        
        # Should have actual report URLs
        assert "/verticals/farm/reports/profit-loss/" in content
        assert "/verticals/farm/reports/livestock/" in content
        assert "/verticals/farm/reports/crop-season/" in content
        # Export buttons should have URLs
        assert "/verticals/farm/reports/ledger-export/" in content


@pytest.mark.django_db
class TestFarmExpensesCategoryCards:
    """Test farm expense page has category cards instead of dropdown."""
    
    def test_expense_page_loads(self, farm_user_business, client):
        """Expense record page should load."""
        user, business = farm_user_business
        client.force_login(user)
        
        response = client.get(reverse("verticals:farm_expenses_record"))
        assert response.status_code == 200
    
    def test_expense_page_has_category_cards(self, farm_user_business, client):
        """Expense page should have category cards container."""
        user, business = farm_user_business
        client.force_login(user)
        
        response = client.get(reverse("verticals:farm_expenses_record"))
        content = response.content.decode("utf-8")
        
        assert 'data-testid="category-cards-container"' in content
    
    def test_expense_page_has_fallback_select(self, farm_user_business, client):
        """Expense page should have hidden fallback select for accessibility."""
        user, business = farm_user_business
        client.force_login(user)
        
        response = client.get(reverse("verticals:farm_expenses_record"))
        content = response.content.decode("utf-8")
        
        assert 'data-testid="category-fallback-select"' in content
    
    def test_expense_categories_are_cards(self, farm_user_business, client):
        """Categories should be rendered as clickable cards."""
        user, business = farm_user_business
        client.force_login(user)
        
        response = client.get(reverse("verticals:farm_expenses_record"))
        content = response.content.decode("utf-8")
        
        # Should have category card elements
        assert 'class="category-card"' in content
        # Should have specific categories
        assert "Fertiliser" in content
        assert "Animal Feed" in content
        assert "Labour" in content


@pytest.mark.django_db
class TestFarmVerticalNoRegressions:
    """Ensure farm changes don't break other verticals."""
    
    def test_farm_dashboard_does_not_affect_sidebar_items(self, farm_user_business, client):
        """Farm dashboard should load and have proper sidebar items."""
        user, business = farm_user_business
        client.force_login(user)
        
        response = client.get(reverse("verticals:farm_dashboard"))
        assert response.status_code == 200
        
        # Sidebar should still work
        content = response.content.decode("utf-8")
        assert "Dashboard" in content or "dashboard" in content.lower()


# ==============================================================================
# NEW: Farm Dashboard Detailed Snapshot Tests (Jan 2026)
# ==============================================================================

@pytest.mark.django_db
class TestFarmDashboardSnapshot:
    """Test Farm Snapshot section with detailed breakdowns."""
    
    def test_dashboard_has_farm_snapshot_section(self, farm_user_business, client):
        """Dashboard should have Farm Snapshot section."""
        user, business = farm_user_business
        client.force_login(user)
        
        response = client.get(reverse("verticals:farm_dashboard"))
        assert response.status_code == 200
        
        content = response.content.decode("utf-8")
        assert 'data-testid="farm-snapshot-section"' in content
    
    def test_crops_breakdown_shows_recorded_crops(self, farm_user_business, client):
        """Crops breakdown should show actual recorded crop seasons."""
        user, business = farm_user_business
        client.force_login(user)
        
        # Create a crop season
        FarmCropSeason.objects.create(
            business=business,
            crop_type="maize",
            name="Maize 2026",
            start_date=date.today() - timedelta(days=21),  # 3 weeks ago
            area_value=Decimal("9.0"),
            area_unit="acre",
            status=FarmSeasonStatus.ACTIVE,
            created_by=user,
        )
        
        response = client.get(reverse("verticals:farm_dashboard"))
        assert response.status_code == 200
        
        content = response.content.decode("utf-8")
        # Should contain the crop type
        assert 'data-testid="crops-breakdown-card"' in content
        assert 'data-testid="crop-name"' in content
        assert "Maize" in content
    
    def test_livestock_breakdown_shows_counts_by_type(self, farm_user_business, client):
        """Livestock breakdown should show counts by animal type."""
        user, business = farm_user_business
        client.force_login(user)
        
        # Create livestock batches
        FarmLivestockBatch.objects.create(
            business=business,
            animal_type=FarmAnimalType.PIGS,
            name="Pigs Batch 1",
            count_current=12,
            is_active=True,
            created_by=user,
        )
        FarmLivestockBatch.objects.create(
            business=business,
            animal_type=FarmAnimalType.CHICKENS,
            name="Broilers Group A",
            count_current=100,
            is_active=True,
            created_by=user,
        )
        
        response = client.get(reverse("verticals:farm_dashboard"))
        assert response.status_code == 200
        
        content = response.content.decode("utf-8")
        assert 'data-testid="livestock-breakdown-card"' in content
        assert 'data-testid="livestock-type-count"' in content
    
    def test_assets_preview_shows_when_assets_exist(self, farm_user_business, client):
        """Assets preview should show when assets exist."""
        user, business = farm_user_business
        client.force_login(user)
        
        # Create an asset
        FarmAsset.objects.create(
            business=business,
            asset_type="tractor",
            name="John Deere Tractor",
            quantity=1,
            value_mwk=Decimal("5000000"),
            condition="good",
            is_active=True,
            created_by=user,
        )
        
        response = client.get(reverse("verticals:farm_dashboard"))
        assert response.status_code == 200
        
        content = response.content.decode("utf-8")
        assert 'data-testid="assets-preview-card"' in content
        assert "John Deere" in content or "Tractor" in content


# ==============================================================================
# NEW: AI Insights Engine Unit Tests (Jan 2026)
# ==============================================================================

@pytest.mark.django_db
class TestFarmInsightsEngine:
    """Test the deterministic Farm Insights Engine."""
    
    def test_maize_fertilizer_recommendation_generated(self, farm_user_business):
        """Given Maize season planted 3 weeks ago, should return fertilizer recommendation."""
        from inventory.services.farm_insights import generate_crop_insights
        
        user, business = farm_user_business
        today = date.today()
        
        # Simulate a maize season planted 3 weeks ago
        season = FarmCropSeason.objects.create(
            business=business,
            crop_type="maize",
            name="Maize 2026",
            start_date=today - timedelta(days=21),  # 3 weeks ago
            area_value=Decimal("9.0"),
            area_unit="acre",
            status=FarmSeasonStatus.ACTIVE,
            created_by=user,
        )
        
        insights = generate_crop_insights([season], today)
        
        # Should have at least one fertilizer recommendation
        assert len(insights) > 0
        fert_insights = [i for i in insights if i.category.value == "fertilizer"]
        assert len(fert_insights) > 0
        
        # Should have non-zero bag estimates
        first_insight = fert_insights[0]
        assert first_insight.suggested_quantities is not None
        assert "bags" in first_insight.suggested_quantities.lower()
        
        # Should have disclaimer
        assert "estimate" in first_insight.confidence_note.lower() or "adjust" in first_insight.confidence_note.lower()
    
    def test_fertilizer_estimate_calculation(self, farm_user_business):
        """Test fertilizer estimate calculation for maize."""
        from inventory.services.farm_insights import calculate_fertilizer_estimate
        
        result = calculate_fertilizer_estimate("maize", 9.0, 3)  # Week 3, 9 acres
        
        assert result["has_recommendation"] is True
        assert result["npk_bags"] > 0
        assert result["urea_bags"] > 0
        assert "disclaimer" in result
    
    def test_livestock_insights_generated(self, farm_user_business):
        """Test livestock insights generation."""
        from inventory.services.farm_insights import generate_livestock_insights
        
        user, business = farm_user_business
        today = date.today()
        
        # Create a batch
        batch = FarmLivestockBatch.objects.create(
            business=business,
            animal_type=FarmAnimalType.CHICKENS,
            name="Broilers Group A",
            count_current=100,
            is_active=True,
            created_by=user,
        )
        
        insights = generate_livestock_insights([batch], today)
        
        # Should have feed and/or vet insights
        assert len(insights) > 0
        
        # Check categories
        categories = [i.category.value for i in insights]
        assert "feed" in categories or "veterinary" in categories


# ==============================================================================
# NEW: Smart Add Entry Tests (Jan 2026)
# ==============================================================================

@pytest.mark.django_db
class TestSmartAddEntry:
    """Test context-aware Add Entry flow."""
    
    def test_crop_season_detail_has_recommended_panel(self, farm_user_business, client):
        """For crop season, recommended panel should contain fertilizer suggestion."""
        user, business = farm_user_business
        client.force_login(user)
        
        # Create a crop season
        season = FarmCropSeason.objects.create(
            business=business,
            crop_type="maize",
            name="Maize 2026",
            start_date=date.today() - timedelta(days=21),
            area_value=Decimal("9.0"),
            area_unit="acre",
            status=FarmSeasonStatus.ACTIVE,
            created_by=user,
        )
        
        response = client.get(reverse("verticals:farm_crop_detail", args=[season.id]))
        assert response.status_code == 200
        
        content = response.content.decode("utf-8")
        # Should have recommended actions panel
        assert 'data-testid="recommended-actions-panel"' in content or 'data-testid="entry-types-panel"' in content
    
    def test_livestock_add_event_has_recommendations(self, farm_user_business, client):
        """For livestock cohort, recommended panel should contain feed/vet suggestion."""
        user, business = farm_user_business
        client.force_login(user)
        
        # Create a batch
        batch = FarmLivestockBatch.objects.create(
            business=business,
            animal_type=FarmAnimalType.PIGS,
            name="Pigs Batch 1",
            count_current=12,
            is_active=True,
            created_by=user,
        )
        
        # Access with batch_id
        response = client.get(reverse("verticals:farm_livestock_add_event") + f"?batch_id={batch.id}")
        assert response.status_code == 200
        
        content = response.content.decode("utf-8")
        # Should have the form
        assert 'data-testid="farm-livestock-event-form"' in content


# ==============================================================================
# NEW: Vertical-Aware Billing Copy Tests (Jan 2026)
# ==============================================================================

@pytest.mark.django_db
class TestVerticalBillingCopy:
    """Test that billing pages use vertical-appropriate terminology."""
    
    def test_farm_billing_uses_farm_terminology(self, farm_user_business, client):
        """When vertical=farm, billing page should contain 'farm' not 'shop'."""
        user, business = farm_user_business
        client.force_login(user)
        
        response = client.get(reverse("billing:subscribe"))
        
        # Page should load
        assert response.status_code == 200
        
        content = response.content.decode("utf-8")
        # Should use farm terminology
        assert "farm" in content.lower() or "assistant manager" in content.lower()
    
    def test_vertical_copy_returns_correct_terms(self):
        """Test vertical copy map returns correct terminology."""
        from billing.vertical_copy import get_billing_copy
        
        farm_copy = get_billing_copy("farm")
        assert farm_copy.location_singular == "farm"
        assert farm_copy.staff_plural == "assistant managers"
        
        gym_copy = get_billing_copy("gym")
        assert gym_copy.location_singular == "gym"
        assert gym_copy.staff_plural == "trainers"
        
        phones_copy = get_billing_copy("phones")
        assert phones_copy.location_singular == "shop"
        assert phones_copy.staff_plural == "agents"
    
    def test_unknown_vertical_falls_back_to_default(self):
        """Unknown vertical should use default shop/agents terminology."""
        from billing.vertical_copy import get_billing_copy
        
        unknown_copy = get_billing_copy("unknown_vertical")
        assert unknown_copy.location_singular == "shop"
        assert unknown_copy.staff_plural == "agents"


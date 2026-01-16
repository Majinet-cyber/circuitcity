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
"""
import pytest
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from inventory.business_kinds import BusinessKind
from inventory.models_farm import (
    FarmAsset,
    FarmCrop,
    FarmCropSale,
    FarmLedgerEntry,
    FarmLivestockBatch,
    FarmCropCategory,
    FarmEntryType,
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


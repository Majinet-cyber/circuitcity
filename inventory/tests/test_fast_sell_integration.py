# inventory/tests/test_fast_sell_integration.py
"""
Tests for Fast Sell sidebar integration across inventory verticals.
Verifies that Fast Sell pages are accessible and properly configured.

IMPORTANT: Fast Sell is ONLY enabled for pharmacy and clothing.
Phones, liquor, and gym do NOT support Fast Sell (they use dedicated scan/sell flows).
"""
import pytest
from django.urls import reverse
from django.test import Client
from django.urls.exceptions import NoReverseMatch

from tenants.models import Business, Membership
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def create_business_with_manager(db):
    """Create a business with a manager for testing."""

    def _create(business_kind="phones"):
        user = User.objects.create_user(
            username=f"manager_{business_kind}", email=f"manager@{business_kind}.test", password="testpass123"
        )
        business = Business.objects.create(
            name=f"Test {business_kind.title()} Business", business_kind=business_kind, slug=f"test-{business_kind}-biz"
        )
        Membership.objects.create(user=user, business=business, role="MANAGER", status="ACTIVE")
        return user, business

    return _create


@pytest.mark.django_db
class TestPhonesDoesNotSupportFastSell:
    """Test that phones vertical does NOT support Fast Sell (uses dedicated scan/sell flows)."""

    def test_phones_fast_sell_route_does_not_exist(self):
        """Phones Fast Sell route should NOT exist."""
        with pytest.raises(NoReverseMatch):
            reverse("verticals:phones_fast_sell")

    def test_phones_sidebar_does_not_have_fast_sell(self):
        """Phones sidebar should NOT include Fast Sell menu item."""
        from inventory.utils_verticals import get_vertical_sidebar_items

        items = get_vertical_sidebar_items("phones")
        fast_sell_items = [item for item in items if item.get("key") == "fast_sell"]

        assert len(fast_sell_items) == 0, "Phones should NOT have Fast Sell in sidebar"

    def test_vertical_capability_check_phones_no_fast_sell(self):
        """Capability check should return False for phones fast sell support."""
        from inventory.utils_vertical_capabilities import vertical_supports_fast_sell

        assert vertical_supports_fast_sell("phones") is False
        assert vertical_supports_fast_sell("PHONES") is False  # Case insensitive


@pytest.mark.django_db
class TestGymDoesNotSupportFastSell:
    """Test that gym vertical does NOT support Fast Sell (membership-based, not inventory)."""

    def test_gym_fast_sell_route_does_not_exist(self):
        """Gym Fast Sell route should NOT exist."""
        with pytest.raises(NoReverseMatch):
            reverse("verticals:gym_fast_sell")

    def test_gym_sidebar_does_not_have_fast_sell(self):
        """Gym sidebar should NOT include Fast Sell menu item."""
        from inventory.utils_verticals import get_vertical_sidebar_items

        items = get_vertical_sidebar_items("gym")
        fast_sell_items = [item for item in items if item.get("key") == "fast_sell"]

        assert len(fast_sell_items) == 0, "Gym should NOT have Fast Sell in sidebar"

    def test_vertical_capability_check_gym_no_fast_sell(self):
        """Capability check should return False for gym fast sell support."""
        from inventory.utils_vertical_capabilities import vertical_supports_fast_sell

        assert vertical_supports_fast_sell("gym") is False
        assert vertical_supports_fast_sell("GYM") is False  # Case insensitive


@pytest.mark.django_db
class TestLiquorDoesNotSupportFastSell:
    """Test that liquor vertical does NOT support Fast Sell (uses dedicated sell flow with barman attribution)."""

    def test_liquor_fast_sell_route_does_not_exist(self):
        """Liquor Fast Sell route should NOT exist."""
        with pytest.raises(NoReverseMatch):
            reverse("verticals:liquor_fast_sell")

    def test_liquor_sidebar_does_not_have_fast_sell(self):
        """Liquor sidebar should NOT include Fast Sell menu item."""
        from inventory.utils_verticals import get_vertical_sidebar_items

        items = get_vertical_sidebar_items("liquor")
        fast_sell_items = [item for item in items if item.get("key") == "fast_sell"]

        assert len(fast_sell_items) == 0, "Liquor should NOT have Fast Sell in sidebar"

    def test_vertical_capability_check_liquor_no_fast_sell(self):
        """Capability check should return False for liquor fast sell support."""
        from inventory.utils_vertical_capabilities import vertical_supports_fast_sell

        assert vertical_supports_fast_sell("liquor") is False
        assert vertical_supports_fast_sell("LIQUOR") is False  # Case insensitive


@pytest.mark.django_db
class TestFastSellPharmacyIntegration:
    """Test Fast Sell integration for pharmacy vertical."""

    def test_pharmacy_fast_sell_route_exists(self, create_business_with_manager, client: Client):
        """Pharmacy Fast Sell route should be accessible."""
        user, business = create_business_with_manager("pharmacy")
        client.force_login(user)

        session = client.session
        session["active_business_id"] = business.id
        session.save()

        url = reverse("verticals:pharmacy_fast_sell")
        response = client.get(url)

        assert response.status_code == 200
        assert b"Fast Sell" in response.content or b"fast-sell" in response.content


@pytest.mark.django_db
class TestFastSellClothingIntegration:
    """Test Fast Sell integration for clothing vertical."""

    def test_clothing_fast_sell_route_exists(self, create_business_with_manager, client: Client):
        """Clothing Fast Sell route should be accessible."""
        user, business = create_business_with_manager("clothing")
        client.force_login(user)

        session = client.session
        session["active_business_id"] = business.id
        session.save()

        url = reverse("verticals:clothing_fast_sell")
        response = client.get(url)

        assert response.status_code == 200
        assert b"Fast Sell" in response.content or b"fast-sell" in response.content


@pytest.mark.django_db
class TestFastSellSidebarItems:
    """Test that Fast Sell appears in sidebar for pharmacy and clothing ONLY."""

    def test_pharmacy_sidebar_has_fast_sell(self):
        """Pharmacy sidebar should include Fast Sell menu item."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        from inventory.utils_vertical_capabilities import vertical_supports_fast_sell

        assert vertical_supports_fast_sell("pharmacy") is True

        items = get_vertical_sidebar_items("pharmacy")
        fast_sell_items = [item for item in items if item.get("key") == "fast_sell"]

        assert len(fast_sell_items) == 1
        assert fast_sell_items[0]["label"] == "Fast Sell"

    def test_clothing_sidebar_has_fast_sell(self):
        """Clothing sidebar should include Fast Sell menu item."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        from inventory.utils_vertical_capabilities import vertical_supports_fast_sell

        assert vertical_supports_fast_sell("clothing") is True

        items = get_vertical_sidebar_items("clothing")
        fast_sell_items = [item for item in items if item.get("key") == "fast_sell"]

        assert len(fast_sell_items) == 1
        assert fast_sell_items[0]["label"] == "Fast Sell"

# tests/test_vertical_nav_separation.py
"""
Critical tests for vertical navigation separation.
Ensures no phone-specific UI leaks into non-phone verticals.
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from inventory.business_kinds import BusinessKind
from inventory.mobile_nav import get_mobile_nav_items
from inventory.utils_verticals import get_vertical_kind, get_vertical_sidebar_items
from tenants.models import Business, Membership

User = get_user_model()


@pytest.mark.django_db
class TestVerticalNavSeparation(TestCase):
    """
    CRITICAL: Test that phone-specific UI does NOT leak into other verticals.
    This was a regression bug where None/unknown businesses showed phones nav.
    """

    def setUp(self):
        """Create test users and businesses for each vertical"""
        self.user = User.objects.create_user(username="test_user", email="test@test.local", password="test1234")

        # Business with NO business_kind (None)
        self.business_none = Business.objects.create(
            name="No Kind Business", slug="no-kind", business_kind=None, status="ACTIVE"  # CRITICAL: None business_kind
        )
        Membership.objects.create(user=self.user, business=self.business_none, role="Manager")

        # Cement business
        self.business_cement = Business.objects.create(
            name="Cement Store", slug="cement-store", business_kind=BusinessKind.CEMENT, status="ACTIVE"
        )
        Membership.objects.create(user=self.user, business=self.business_cement, role="Manager")

        # Phones business (control group - should have phone terms)
        self.business_phones = Business.objects.create(
            name="Phone Store", slug="phone-store", business_kind=BusinessKind.PHONES, status="ACTIVE"
        )
        Membership.objects.create(user=self.user, business=self.business_phones, role="Manager")

        self.client = Client()
        self.client.login(username="test_user", password="test1234")

    def test_none_business_returns_generic_vertical(self):
        """Test that businesses with business_kind=None return 'generic' not 'phones'"""
        vertical = get_vertical_kind(self.business_none)
        assert vertical == "generic", f"Expected 'generic' but got '{vertical}'"
        assert vertical != "phones", "None business_kind must NOT default to 'phones'"

    def test_none_business_sidebar_has_no_phone_terms(self):
        """Test that None business_kind sidebar has NO phone-specific items"""
        sidebar_items = get_vertical_sidebar_items("generic")

        # Convert all sidebar items to string for easy searching
        sidebar_text = str(sidebar_items).lower()

        # MUST NOT contain phone-specific terms
        phone_terms = [
            "imei",
            "scan in",
            "scan & sell",
            "accessories",
            "phones",
            "scan_in",
            "scan_sold",
        ]

        for term in phone_terms:
            assert term not in sidebar_text, f"Generic sidebar must NOT contain '{term}'. Found in: {sidebar_text}"

        # MUST be minimal (only Home/Dashboard + Settings)
        assert len(sidebar_items) <= 3, f"Generic sidebar should be minimal (≤3 items), got {len(sidebar_items)}"

        # Verify expected items exist
        labels = [item["label"] for item in sidebar_items]
        assert any(
            "home" in label.lower() or "dashboard" in label.lower() for label in labels
        ), "Generic sidebar must have Home or Dashboard"

    def test_cement_sidebar_has_no_phone_terms(self):
        """Test that cement sidebar has NO phone-specific items"""
        sidebar_items = get_vertical_sidebar_items("cement")

        sidebar_text = str(sidebar_items).lower()

        # MUST NOT contain phone-specific terms
        phone_terms = ["imei", "scan in", "accessories", "phones", "scan_in", "scan_sold"]

        for term in phone_terms:
            assert term not in sidebar_text, f"Cement sidebar must NOT contain '{term}'"

        # MUST contain cement-appropriate terms
        cement_labels = [item["label"].lower() for item in sidebar_items]
        assert any("stock" in label for label in cement_labels), "Cement sidebar must have Stock item"
        assert any("sell" in label for label in cement_labels), "Cement sidebar must have Sell item"

    def test_none_business_view_has_no_phone_ui(self):
        """Test that /verticals/none/ page has NO phone-specific UI elements"""
        # Switch to None business
        session = self.client.session
        session["active_business_id"] = self.business_none.id
        session.save()

        response = self.client.get(reverse("verticals:no_business"))
        assert response.status_code == 200

        content = response.content.decode("utf-8").lower()

        # MUST NOT contain phone terms in page content
        phone_terms = [
            "imei",
            "scan imei",
            "scan & sell",
            "accessories",
            "sell accessories",
            "stock in accessories",
        ]

        for term in phone_terms:
            assert term not in content, f"/verticals/none/ must NOT contain '{term}' in page content"

        # SHOULD contain generic/neutral messaging
        assert (
            "select your business type" in content or "business type" in content
        ), "/verticals/none/ should prompt to select business type"

    def test_cement_dashboard_has_no_phone_ui(self):
        """Test that cement dashboard has NO phone-specific UI elements"""
        # Switch to cement business
        session = self.client.session
        session["active_business_id"] = self.business_cement.id
        session.save()

        response = self.client.get(reverse("verticals:cement_dashboard"))
        assert response.status_code == 200

        content = response.content.decode("utf-8").lower()

        # MUST NOT contain phone terms
        phone_terms = [
            "imei",
            "scan imei",
            "accessories",
            "phone",
        ]

        for term in phone_terms:
            assert term not in content, f"Cement dashboard must NOT contain '{term}'"

        # SHOULD contain cement-appropriate terms
        cement_terms = ["cement", "bag", "brand"]
        found_cement_terms = any(term in content for term in cement_terms)
        assert found_cement_terms, f"Cement dashboard should contain cement-appropriate terms: {cement_terms}"

    def test_phones_business_does_have_phone_terms(self):
        """Control test: phones business SHOULD have phone-specific terms"""
        sidebar_items = get_vertical_sidebar_items("phones")
        sidebar_text = str(sidebar_items).lower()

        # Phones vertical SHOULD contain phone terms
        # (This is a control to verify our test logic works)
        phone_items_expected = any(term in sidebar_text for term in ["scan", "stock", "sell"])
        assert phone_items_expected, "Phones sidebar should have scan/stock/sell items (control test)"

    def test_mobile_nav_none_business_no_phone_terms(self):
        """Test that mobile nav for None business has NO phone terms"""
        # Create mock request with None business
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/")
        request.user = self.user
        request.business = self.business_none
        request.session = {}

        nav_items = get_mobile_nav_items(request)

        nav_text = str(nav_items).lower()

        # MUST NOT contain phone terms
        phone_terms = ["imei", "scan", "accessories"]
        for term in phone_terms:
            # Allow "scan" only in context of "scan qr" for cement
            # but not "scan in" or "scan imei"
            if term == "scan":
                assert "scan in" not in nav_text and "scan imei" not in nav_text
            else:
                assert term not in nav_text, f"Mobile nav for None business must NOT contain '{term}'"

    def test_mobile_nav_cement_no_phone_terms(self):
        """Test that mobile nav for cement has NO phone terms"""
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/")
        request.user = self.user
        request.business = self.business_cement
        request.session = {}

        nav_items = get_mobile_nav_items(request)

        nav_text = str(nav_items).lower()

        # MUST NOT contain phone-specific scan terms
        assert "scan imei" not in nav_text
        assert "scan in" not in nav_text or "stock in" in nav_text  # "stock in" is ok for cement
        assert "accessories" not in nav_text


@pytest.mark.django_db
class TestVerticalKindMapping(TestCase):
    """Test that vertical kind detection works correctly"""

    def test_none_business_kind_maps_to_generic(self):
        """Test business_kind=None maps to 'generic'"""
        business = Business.objects.create(name="Test", slug="test-none", business_kind=None, status="ACTIVE")
        assert get_vertical_kind(business) == "generic"

    def test_empty_string_business_kind_maps_to_generic(self):
        """Test business_kind='' maps to 'generic'"""
        business = Business.objects.create(name="Test", slug="test-empty", business_kind="", status="ACTIVE")
        # Empty string gets normalized to generic
        vertical = get_vertical_kind(business)
        assert vertical in ("generic", ""), f"Empty business_kind should map to generic, got {vertical}"

    def test_unknown_business_kind_maps_to_generic(self):
        """Test unknown business_kind maps to 'generic' NOT 'phones'"""
        business = Business.objects.create(
            name="Test", slug="test-unknown", business_kind="unknown_vertical_xyz", status="ACTIVE"  # Invalid vertical
        )
        vertical = get_vertical_kind(business)
        assert vertical == "generic", f"Unknown vertical should map to 'generic', got '{vertical}'"
        assert vertical != "phones", "Unknown vertical must NOT default to 'phones'"

    def test_cement_business_kind_maps_to_cement(self):
        """Test business_kind='cement' maps correctly"""
        business = Business.objects.create(
            name="Test", slug="test-cement", business_kind=BusinessKind.CEMENT, status="ACTIVE"
        )
        assert get_vertical_kind(business) == "cement"


@pytest.mark.django_db
class TestNavRegressionPrevention(TestCase):
    """
    Regression tests to ensure the original bug doesn't come back.

    BUG: Previously, businesses with business_kind=None showed phones nav.
    FIX: Now they show minimal generic nav.
    """

    def test_get_vertical_kind_never_returns_phones_for_none(self):
        """REGRESSION TEST: get_vertical_kind(None) must NOT return 'phones'"""
        business = Business.objects.create(name="Test", slug="test-reg", business_kind=None, status="ACTIVE")

        vertical = get_vertical_kind(business)

        assert vertical != "phones", "REGRESSION: None business_kind returned 'phones' (bug is back!)"
        assert vertical == "generic", f"None business_kind should return 'generic', got '{vertical}'"

    def test_sidebar_items_generic_is_minimal(self):
        """REGRESSION TEST: generic sidebar must be minimal (no phones nav)"""
        items = get_vertical_sidebar_items("generic")

        # Should only have 2-3 items max (Home, Settings, maybe one more)
        assert len(items) <= 3, f"Generic sidebar should be minimal (≤3 items), got {len(items)} items"

        # Verify NO phone-specific items
        all_keys = [item["key"] for item in items]
        phone_keys = ["scan_in", "scan_sold", "accessories", "imei"]

        for phone_key in phone_keys:
            assert phone_key not in all_keys, f"Generic sidebar must NOT contain '{phone_key}' key"

"""
Regression tests for production hardening (April 2026).

Covers three specific fixes:
  1. Pharmacy stock-in 500 error — nullable cost_price in filter arg when engine.debug=True
  2. Gym dashboard dev-comment leakage — section markers must not appear in rendered HTML
  3. Gym dashboard baseline response — authenticated tenant user gets 200

These tests guard against regressions being re-introduced.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from tenants.models import Business, Membership

User = get_user_model()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pharmacy_business():
    from inventory.models import Location as Loc
    biz = Business.objects.create(
        name="Regen Pharmacy",
        slug="regen-pharmacy",
        business_kind="pharmacy",
        status="ACTIVE",
    )
    loc = Loc.objects.create(business=biz, name="Main", is_default=True)
    user = User.objects.create_user(
        username="pharma_mgr@test.com",
        email="pharma_mgr@test.com",
        password="StrongPass1!",
    )
    Membership.objects.create(user=user, business=biz, role="MANAGER")
    return biz, loc, user


def _make_gym_business():
    from inventory.models import Location as Loc
    biz = Business.objects.create(
        name="Iron Temple Gym",
        slug="iron-temple-gym",
        business_kind="gym",
        status="ACTIVE",
    )
    loc = Loc.objects.create(business=biz, name="Main", is_default=True)
    user = User.objects.create_user(
        username="gym_mgr@test.com",
        email="gym_mgr@test.com",
        password="StrongPass1!",
    )
    Membership.objects.create(user=user, business=biz, role="MANAGER")
    return biz, loc, user


def _auth_client(user, biz, loc):
    c = Client()
    c.login(username=user.username, password="StrongPass1!")
    s = c.session
    s["active_business_id"] = biz.id
    s["active_location_id"] = loc.id
    s.save()
    return c


# ---------------------------------------------------------------------------
# 1. Pharmacy stock-in — no 500 when category set but no prefill product
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPharmacyStockInNullableCost(TestCase):
    """
    Guard: stock-in form must render 200 when ?category=<cat> is set but
    no prefill_id is given — i.e., prefill_product=None and
    prefill_last_batch=None — even when template engine.debug=True.
    """

    def setUp(self):
        self.biz, self.loc, self.user = _make_pharmacy_business()
        self.client = _auth_client(self.user, self.biz, self.loc)

    def test_stock_in_no_prefill_body_care_returns_200(self):
        """
        /pharmacy/stock-in/custom/?category=body_care with no prefill_id.
        Both prefill_product and prefill_last_batch are None.
        The view now pre-computes safe scalar context values so the template
        never resolves None.cost_price as a filter argument, eliminating the
        VariableDoesNotExist crash that occurred when engine.debug=True.
        """
        url = reverse("pharmacy:stock_in") + "?category=body_care"
        response = self.client.get(url)
        self.assertEqual(
            response.status_code, 200,
            f"Expected 200 but got {response.status_code}. "
            "Possible VariableDoesNotExist crash on nullable cost_price.",
        )

    def test_stock_in_no_prefill_medicine_returns_200(self):
        """Same check for medicine category."""
        url = reverse("pharmacy:stock_in") + "?category=medicine"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_stock_in_no_category_returns_200(self):
        """Base load with no category — all prefill values absent."""
        url = reverse("pharmacy:stock_in")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_stock_in_invalid_prefill_id_returns_200(self):
        """
        ?prefill_id=999999 refers to a non-existent product.
        prefill_product → None, prefill_last_batch → None.
        Template must not crash.
        """
        url = reverse("pharmacy:stock_in") + "?category=skin_care&prefill_id=999999"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_stock_in_context_has_safe_prefill_values(self):
        """
        View must include safe scalar prefill_cost_price/selling_price/supplier/
        reorder_level in context — never None/missing.
        """
        url = reverse("pharmacy:stock_in") + "?category=body_care"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        self.assertIn("prefill_cost_price", ctx)
        self.assertIn("prefill_selling_price", ctx)
        self.assertIn("prefill_supplier", ctx)
        self.assertIn("prefill_reorder_level", ctx)
        # Must be safe scalars (not None)
        self.assertIsNotNone(ctx["prefill_cost_price"])
        self.assertIsNotNone(ctx["prefill_selling_price"])
        self.assertIsNotNone(ctx["prefill_supplier"])
        self.assertIsNotNone(ctx["prefill_reorder_level"])

    def test_stock_in_prefill_values_populated_from_last_batch(self):
        """
        When a valid prefill_id is given that has an existing batch, the
        context scalar values should reflect the batch's cost/selling price.
        """
        from inventory.models import MerchProduct
        from inventory.models_pharmacy import PharmacyBatch
        from django.utils import timezone

        product = MerchProduct.objects.create(
            business=self.biz,
            name="Test Lotion",
            kind="pharmacy",
            category="body_care",
            cost_price=Decimal("1500.00"),
            selling_price=Decimal("2000.00"),
            is_active=True,
        )
        PharmacyBatch.objects.create(
            business=self.biz,
            merch_product=product,
            batch_number="BT-001",
            expiry_date=timezone.now().date().replace(year=2027),
            quantity=50,
            cost_price=Decimal("1500.00"),
            selling_price=Decimal("2000.00"),
            supplier="Test Supplier",
            reorder_level=5,
        )

        url = (
            reverse("pharmacy:stock_in")
            + f"?category=body_care&prefill_id={product.pk}"
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        self.assertEqual(str(ctx["prefill_cost_price"]), "1500.00")
        self.assertEqual(str(ctx["prefill_selling_price"]), "2000.00")
        self.assertEqual(ctx["prefill_supplier"], "Test Supplier")
        self.assertEqual(ctx["prefill_reorder_level"], 5)


# ---------------------------------------------------------------------------
# 2. Gym dashboard — no dev-comment leakage in rendered HTML
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestGymDashboardNoDevComments(TestCase):
    """
    Guard: the gym dashboard response body must not contain any raw
    developer/scaffolding text that should only live in template comments.
    """

    # Strings that should NEVER appear in rendered HTML (they were
    # section-marker text that leaked in earlier template versions).
    BANNED_STRINGS = [
        "HERO — gradient card",
        "all content server-rendered, no JS dependency",
        "FINANCIAL KPIs",
        "PAYMENT MIX",
        "CHECK-IN STATS",
        "RECENT PAYMENTS",
        "MEMBERSHIP STATUS",
        "Server-rendered widths/colors",
        "zero JS needed, zero CLS",
        "DATE RANGE FILTER",
        "KPI row — always 3 equal columns",
        "Health bar — width set by server via widthratio",
        "Quote lives inside the hero so it never causes",
        "Left: title + blurb",
        "Right: two prominent action cards",
    ]

    def setUp(self):
        self.biz, self.loc, self.user = _make_gym_business()
        self.client = _auth_client(self.user, self.biz, self.loc)

    def _get_dashboard_content(self):
        url = reverse("gym:dashboard")
        response = self.client.get(url)
        self.assertEqual(
            response.status_code, 200,
            f"Gym dashboard returned {response.status_code}",
        )
        return response.content.decode("utf-8")

    def test_no_hero_dev_comment_in_html(self):
        content = self._get_dashboard_content()
        self.assertNotIn(
            "HERO — gradient card",
            content,
            "Dev section marker 'HERO — gradient card' leaked into rendered HTML.",
        )

    def test_no_financial_kpis_dev_comment(self):
        content = self._get_dashboard_content()
        # "Financial Performance" IS a real heading — we check for the raw
        # ALL-CAPS marker string, not the real UI heading.
        self.assertNotIn(
            "FINANCIAL KPIs",
            content,
            "Raw dev marker 'FINANCIAL KPIs' leaked into HTML.",
        )

    def test_no_payment_mix_dev_comment(self):
        content = self._get_dashboard_content()
        # NB: "Payment Mix" (title-case) IS a real UI heading — we only ban
        # the ALL-CAPS raw marker.
        self.assertNotIn(
            "PAYMENT MIX",
            content,
            "Raw dev marker 'PAYMENT MIX' leaked into HTML.",
        )

    def test_no_date_range_filter_dev_comment(self):
        content = self._get_dashboard_content()
        self.assertNotIn(
            "DATE RANGE FILTER",
            content,
            "Raw dev marker 'DATE RANGE FILTER' leaked into HTML.",
        )

    def test_no_implementation_notes_in_html(self):
        """Batch-check all banned strings in one render."""
        content = self._get_dashboard_content()
        leaked = [s for s in self.BANNED_STRINGS if s in content]
        self.assertFalse(
            leaked,
            f"Dev/scaffold text leaked into rendered gym dashboard HTML: {leaked}",
        )


# ---------------------------------------------------------------------------
# 3. Gym dashboard — authenticated tenant user baseline
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestGymDashboardBaselineResponse(TestCase):
    """
    Guard: gym dashboard responds 200 for a valid authenticated tenant user
    across the common date-range filters.
    """

    def setUp(self):
        self.biz, self.loc, self.user = _make_gym_business()
        self.client = _auth_client(self.user, self.biz, self.loc)

    def _assert_200(self, url_suffix=""):
        url = reverse("gym:dashboard") + url_suffix
        response = self.client.get(url)
        self.assertEqual(
            response.status_code, 200,
            f"Gym dashboard returned {response.status_code} for '{url_suffix}'.",
        )
        return response

    def test_dashboard_default_returns_200(self):
        self._assert_200()

    def test_dashboard_today_filter_returns_200(self):
        self._assert_200("?range=today")

    def test_dashboard_last7_filter_returns_200(self):
        self._assert_200("?range=last7")

    def test_dashboard_mtd_filter_returns_200(self):
        self._assert_200("?range=mtd")

    def test_dashboard_all_time_filter_returns_200(self):
        self._assert_200("?range=all_time")

    def test_dashboard_unauthenticated_redirects(self):
        """Unauthenticated request must not return 200 (auth required)."""
        c = Client()
        url = reverse("gym:dashboard")
        response = c.get(url)
        # Should redirect to login, not serve the dashboard
        self.assertNotEqual(response.status_code, 200)
        self.assertIn(response.status_code, [301, 302, 403])

    def test_dashboard_contains_real_ui_headings(self):
        """Key real UI headings must still be present after comment cleanup."""
        response = self._assert_200()
        content = response.content.decode("utf-8")
        # These are real rendered UI strings (NOT dev comments)
        self.assertIn("Financial Performance", content)
        self.assertIn("Filter", content)
        self.assertIn("Check-ins", content)

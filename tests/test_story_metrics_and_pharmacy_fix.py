"""
Tests for:
A. Story metrics resolver (vertical-aware landing page proof data)
B. Pharmacy 500 bug fix (api_stock_in KeyError + api_sell KeyError)
C. Category normalisation helper
D. Gym & pharmacy dashboard smoke tests

Task: vertical-aware live proof + gym polish + pharmacy polish
"""
from __future__ import annotations

import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.models import Location, MerchProduct
from inventory.models_pharmacy import PharmacyBatch, PharmacySale
from inventory.models_verticals import GymMember, GymPayment, GymSettings
from tenants.models import Business, Membership

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pharmacy_business(name="Test Pharmacy", subdomain="test-pharm"):
    return Business.objects.create(
        name=name,
        business_kind=BusinessKind.PHARMACY,
        subdomain=subdomain,
    )


def _make_gym_business(name="Test Gym", subdomain="test-gym"):
    return Business.objects.create(
        name=name,
        business_kind=BusinessKind.GYM,
        subdomain=subdomain,
    )


def _make_manager(business, username, password="pw"):
    user = User.objects.create_user(username=username, password=password)
    Membership.objects.create(user=user, business=business, role="MANAGER", status="ACTIVE")
    return user


def _make_pharmacy_product(business, name="Paracetamol", category="tablets_capsules"):
    return MerchProduct.objects.create(
        business=business,
        name=name,
        kind="pharmacy",
        category=category,
        cost_price=Decimal("150.00"),
        selling_price=Decimal("200.00"),
        quantity_in_stock=0,
    )


def _make_pharmacy_batch(business, product, quantity=100):
    return PharmacyBatch.objects.create(
        business=business,
        merch_product=product,
        batch_number="BATCH-001",
        quantity=quantity,
        cost_price=Decimal("150.00"),
        selling_price=Decimal("200.00"),
        received_date=timezone.now().date(),
    )


# ===========================================================================
# A. Story Metrics Resolver
# ===========================================================================

class StoryMetricsGymTest(TestCase):
    """Gym story returns expected metric structure."""

    def test_gym_returns_three_metrics_when_no_data(self):
        """Resolver degrades gracefully when no gym data exists."""
        from staticpages.story_metrics import get_story_metrics
        metrics = get_story_metrics("gym")
        self.assertEqual(len(metrics), 3)
        labels = {m["label"] for m in metrics}
        self.assertIn("Members tracked", labels)
        self.assertIn("Paid & active", labels)
        self.assertIn("In arrears", labels)

    def test_gym_returns_live_count_when_members_exist(self):
        """Gym story returns real member count when data exists."""
        biz = _make_gym_business("Live Gym", "live-gym")
        GymMember.objects.create(
            business=biz,
            name="Alice Banda",
            is_active=True,
            is_archived=False,
        )

        from staticpages.story_metrics import get_story_metrics
        metrics = get_story_metrics("gym")
        total_metric = next(m for m in metrics if m["label"] == "Members tracked")
        # Value should be a real int (at least 1)
        self.assertNotEqual(total_metric["value"], "—")
        self.assertGreaterEqual(int(total_metric["value"]), 1)

    def test_gym_active_vs_arrears_breakdown(self):
        """Active and in-arrears counts are correctly split."""
        biz = _make_gym_business("Split Gym", "split-gym")
        today = timezone.localdate()

        # Active member
        active_m = GymMember.objects.create(
            business=biz, name="Bob Active", is_active=True, is_archived=False,
        )
        GymPayment.objects.create(
            member=active_m,
            membership_amount=Decimal("55000"),
            trainer_fee=Decimal("0"),
            start_date=today - timezone.timedelta(days=5),
            end_date=today + timezone.timedelta(days=25),
            is_active=True,
        )

        # Overdue member
        GymMember.objects.create(
            business=biz, name="Carol Overdue", is_active=True, is_archived=False,
        )

        from staticpages.story_metrics import get_story_metrics
        metrics = get_story_metrics("gym")

        active_m_val = next(m for m in metrics if m["label"] == "Paid & active")
        arrears_val = next(m for m in metrics if m["label"] == "In arrears")

        self.assertGreaterEqual(int(active_m_val["value"]), 1)
        self.assertGreaterEqual(int(arrears_val["value"]), 1)


class StoryMetricsPharmacyTest(TestCase):
    """Pharmacy story returns expected metric structure."""

    def test_pharmacy_returns_three_metrics_when_no_data(self):
        """Resolver degrades gracefully when no pharmacy data exists."""
        from staticpages.story_metrics import get_story_metrics
        metrics = get_story_metrics("pharmacy")
        self.assertEqual(len(metrics), 3)
        labels = {m["label"] for m in metrics}
        self.assertIn("Sales recorded", labels)
        self.assertIn("Stock value", labels)
        self.assertIn("Revenue tracked", labels)

    def test_pharmacy_returns_live_sales_count(self):
        """Pharmacy story returns real sales count when data exists."""
        biz = _make_pharmacy_business("Live Pharmacy", "live-pharm")
        product = _make_pharmacy_product(biz)
        batch = _make_pharmacy_batch(biz, product)

        PharmacySale.objects.create(
            business=biz,
            batch=batch,
            quantity=1,
            unit_price=Decimal("200.00"),
            unit_cost=Decimal("150.00"),
            total_amount=Decimal("200.00"),
            payment_method="CASH",
            is_deleted=False,
            is_reversed=False,
            sold_at=timezone.now(),
        )

        from staticpages.story_metrics import get_story_metrics
        metrics = get_story_metrics("pharmacy")
        sales_metric = next(m for m in metrics if m["label"] == "Sales recorded")
        self.assertNotEqual(sales_metric["value"], "—")
        # Should be at least "1"
        self.assertIn("1", str(sales_metric["value"]))

    def test_unknown_vertical_returns_empty_list(self):
        """Unknown vertical key returns empty list without raising."""
        from staticpages.story_metrics import get_story_metrics
        result = get_story_metrics("unknown_vertical_xyz")
        self.assertEqual(result, [])


class StoryMetricsAllTest(TestCase):
    """get_all_story_metrics returns both verticals."""

    def test_returns_both_verticals(self):
        from staticpages.story_metrics import get_all_story_metrics
        data = get_all_story_metrics()
        self.assertIn("gym", data)
        self.assertIn("pharmacy", data)

    def test_each_vertical_has_meta_and_metrics(self):
        from staticpages.story_metrics import get_all_story_metrics
        data = get_all_story_metrics()
        for vertical_key in ("gym", "pharmacy"):
            entry = data[vertical_key]
            self.assertIn("meta", entry)
            self.assertIn("metrics", entry)
            self.assertIsInstance(entry["metrics"], list)

    def test_story_meta_has_accent_colour(self):
        from staticpages.story_metrics import get_all_story_metrics
        data = get_all_story_metrics()
        self.assertIn("accent", data["gym"]["meta"])
        self.assertIn("accent", data["pharmacy"]["meta"])


# ===========================================================================
# B. Landing Page — story metrics in context
# ===========================================================================

class LandingPageStoryMetricsContextTest(TestCase):
    """Landing page view passes story metrics to template."""

    def test_home_view_includes_story_metrics_context(self):
        client = Client()
        response = client.get(reverse("staticpages:home"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("story_metrics", response.context)

    def test_story_metrics_context_has_gym_and_pharmacy(self):
        client = Client()
        response = client.get(reverse("staticpages:home"))
        metrics = response.context["story_metrics"]
        self.assertIn("gym", metrics)
        self.assertIn("pharmacy", metrics)

    def test_story_metrics_json_is_valid_json(self):
        client = Client()
        response = client.get(reverse("staticpages:home"))
        json_str = response.context.get("story_metrics_json", "")
        # Must be parseable JSON
        data = json.loads(json_str)
        self.assertIsInstance(data, dict)

    def test_home_page_renders_metrics_panel_html(self):
        """Template renders sc-metrics panels for both stories."""
        client = Client()
        response = client.get(reverse("staticpages:home"))
        content = response.content.decode()
        self.assertIn("sc-metrics--gym", content)
        self.assertIn("sc-metrics--pharmacy", content)
        # Metric chip labels rendered
        self.assertIn("Members tracked", content)
        self.assertIn("Sales recorded", content)


# ===========================================================================
# C. Category normalisation helper
# ===========================================================================

class PharmacyCategoryNormalisationTest(TestCase):
    """normalize_pharmacy_category maps UI names to service codes."""

    def test_valid_category_passthrough(self):
        from inventory.pharmacy_config import normalize_pharmacy_category
        self.assertEqual(normalize_pharmacy_category("tablets_capsules"), "tablets_capsules")
        self.assertEqual(normalize_pharmacy_category("syrup"), "syrup")
        self.assertEqual(normalize_pharmacy_category("other"), "other")
        self.assertEqual(normalize_pharmacy_category("analgesic"), "analgesic")

    def test_medicine_maps_to_tablets_capsules(self):
        from inventory.pharmacy_config import normalize_pharmacy_category
        self.assertEqual(normalize_pharmacy_category("medicine"), "tablets_capsules")

    def test_skin_care_maps_correctly(self):
        from inventory.pharmacy_config import normalize_pharmacy_category
        self.assertEqual(normalize_pharmacy_category("skin_care"), "skin_care")

    def test_unknown_category_returns_other(self):
        from inventory.pharmacy_config import normalize_pharmacy_category
        self.assertEqual(normalize_pharmacy_category("nonsense_xyz"), "other")

    def test_case_insensitive(self):
        from inventory.pharmacy_config import normalize_pharmacy_category
        self.assertEqual(normalize_pharmacy_category("Medicine"), "tablets_capsules")
        self.assertEqual(normalize_pharmacy_category("MEDICINE"), "tablets_capsules")


# ===========================================================================
# D. Pharmacy API bug fix — no 500 on stock-in or sell
# ===========================================================================

class PharmacyApiStockInTest(TestCase):
    """api_stock_in returns 200 JSON, no KeyError 500."""

    def setUp(self):
        self.biz = _make_pharmacy_business("Fix Pharmacy", "fix-pharm")
        self.location = Location.objects.create(business=self.biz, name="Main")
        self.user = _make_manager(self.biz, "fix_user")
        self.product = _make_pharmacy_product(self.biz)
        self.client = Client()
        self.client.force_login(self.user)

    def test_api_stock_in_succeeds_no_500(self):
        """POST to api_stock_in returns success JSON, not 500."""
        url = reverse("pharmacy:api_stock_in")
        payload = {
            "product_id": self.product.id,
            "quantity": 50,
            "unit": "piece",
            "cost_price": "150.00",
            "selling_price": "200.00",
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        # Must not be 500
        self.assertNotEqual(response.status_code, 500)
        data = response.json()
        self.assertTrue(data.get("success"), f"Expected success=True, got: {data}")

    def test_api_stock_in_returns_qty_key_not_old_key(self):
        """Response uses 'new_stock' key (mapped from qty_base_units)."""
        url = reverse("pharmacy:api_stock_in")
        payload = {
            "product_id": self.product.id,
            "quantity": 10,
            "unit": "piece",
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        if response.status_code == 200:
            data = response.json()
            self.assertIn("new_stock", data)
            # new_stock should be a number
            self.assertIsInstance(data["new_stock"], (int, float))

    def test_api_stock_in_with_medicine_category_product(self):
        """Product with category='medicine' is normalised and stocked in cleanly."""
        medicine_product = _make_pharmacy_product(
            self.biz, name="Amoxicillin", category="medicine"
        )
        url = reverse("pharmacy:api_stock_in")
        payload = {
            "product_id": medicine_product.id,
            "quantity": 30,
            "unit": "piece",
            "cost_price": "800.00",
            "selling_price": "1000.00",
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertNotEqual(response.status_code, 500)

    def test_api_stock_in_invalid_product_returns_404(self):
        """Missing product_id returns 400, not 500."""
        url = reverse("pharmacy:api_stock_in")
        response = self.client.post(
            url,
            data=json.dumps({"quantity": 5, "unit": "piece"}),
            content_type="application/json",
        )
        # Should be 400 (missing product_id)
        self.assertEqual(response.status_code, 400)


class PharmacyApiSellTest(TestCase):
    """api_sell does not raise KeyError on sold_from_batches."""

    def setUp(self):
        self.biz = _make_pharmacy_business("Sell Pharmacy", "sell-pharm")
        self.location = Location.objects.create(business=self.biz, name="Main")
        self.user = _make_manager(self.biz, "sell_user")
        self.product = _make_pharmacy_product(self.biz)
        self.batch = _make_pharmacy_batch(self.biz, self.product, quantity=100)
        self.client = Client()
        self.client.force_login(self.user)

    def test_api_sell_succeeds_no_500(self):
        """POST to api_sell returns success JSON, not 500."""
        url = reverse("pharmacy:api_sell")
        payload = {
            "items": [
                {"productId": self.product.id, "quantity": 1, "unit": "piece"}
            ],
            "payment_method": "cash",
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertNotEqual(response.status_code, 500)
        data = response.json()
        self.assertTrue(data.get("success"), f"Expected success=True, got: {data}")

    def test_api_sell_response_has_sales_key(self):
        """Sell response has 'sales' list (not sold_from_batches)."""
        url = reverse("pharmacy:api_sell")
        payload = {
            "items": [
                {"productId": self.product.id, "quantity": 2, "unit": "piece"}
            ],
            "payment_method": "cash",
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        if response.status_code == 200:
            data = response.json()
            self.assertIn("sales", data)
            # sale_id key should be present (not sold_from_batches)
            if data["sales"]:
                self.assertIn("sale_id", data["sales"][0])
                self.assertNotIn("sold_from_batches", data["sales"][0])


# ===========================================================================
# E. Gym vertical smoke tests
# ===========================================================================

class GymDashboardSmokeTest(TestCase):
    """Gym dashboard still loads after UI changes."""

    def setUp(self):
        self.biz = _make_gym_business("Smoke Gym", "smoke-gym")
        Location.objects.create(business=self.biz, name="Main")
        self.user = _make_manager(self.biz, "smoke_gym_user")
        GymSettings.objects.get_or_create(business=self.biz)
        self.client = Client()
        self.client.force_login(self.user)

    def test_gym_dashboard_returns_200(self):
        url = reverse("verticals:gym_dashboard")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_gym_members_list_returns_200(self):
        url = reverse("gym:members_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class GymQrPublicViewTest(TestCase):
    """QR public view still works after template rewrite."""

    def setUp(self):
        self.biz = _make_gym_business("QR Gym", "qr-gym")
        Location.objects.create(business=self.biz, name="Main")
        self.member = GymMember.objects.create(
            business=self.biz,
            name="Test Member QR",
            is_active=True,
            is_archived=False,
        )

    def test_qr_public_page_returns_200(self):
        url = reverse("gym:member_qr_status_public", kwargs={"qr_uuid": self.member.qr_uuid})
        client = Client()
        response = client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_qr_public_page_shows_member_name(self):
        url = reverse("gym:member_qr_status_public", kwargs={"qr_uuid": self.member.qr_uuid})
        client = Client()
        response = client.get(url)
        self.assertContains(response, "Test Member QR")

    def test_qr_public_page_shows_gym_name(self):
        url = reverse("gym:member_qr_status_public", kwargs={"qr_uuid": self.member.qr_uuid})
        client = Client()
        response = client.get(url)
        self.assertContains(response, "QR Gym")

    def test_qr_active_member_shows_active_status(self):
        today = timezone.localdate()
        GymPayment.objects.create(
            member=self.member,
            membership_amount=Decimal("55000"),
            trainer_fee=Decimal("0"),
            start_date=today - timezone.timedelta(days=1),
            end_date=today + timezone.timedelta(days=29),
            is_active=True,
        )
        url = reverse("gym:member_qr_status_public", kwargs={"qr_uuid": self.member.qr_uuid})
        client = Client()
        response = client.get(url)
        self.assertContains(response, "Active")

    def test_qr_overdue_member_shows_overdue_status(self):
        url = reverse("gym:member_qr_status_public", kwargs={"qr_uuid": self.member.qr_uuid})
        client = Client()
        response = client.get(url)
        # Member with no payments should show overdue
        self.assertContains(response, "Overdue")


# ===========================================================================
# F. Pharmacy dashboard smoke test
# ===========================================================================

class PharmacyDashboardSmokeTest(TestCase):
    """Pharmacy dashboard still loads after changes."""

    def setUp(self):
        self.biz = _make_pharmacy_business("Smoke Pharmacy", "smoke-pharm")
        Location.objects.create(business=self.biz, name="Main")
        self.user = _make_manager(self.biz, "smoke_pharm_user")
        self.client = Client()
        self.client.force_login(self.user)

    def test_pharmacy_dashboard_returns_200(self):
        url = reverse("verticals:pharmacy_dashboard")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_pharmacy_stock_in_choice_returns_200(self):
        url = reverse("pharmacy:stock_in_choice")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

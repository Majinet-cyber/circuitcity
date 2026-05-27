"""
Tests for:
1. /edit/ redirect (no 404, no VariableDoesNotExist template spam)
2. Pharmacy stock-in recently-stocked suggestions
"""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import BusinessKind, Location, MerchProduct
from inventory.models_pharmacy import PharmacyBatch
from tenants.models import Business, Membership

User = get_user_model()


# ===========================================================================
# Helpers
# ===========================================================================

def _make_pharmacy_biz(name="Test Pharmacy", subdomain="test-pharm"):
    return Business.objects.create(
        name=name,
        business_kind=BusinessKind.PHARMACY,
        subdomain=subdomain,
    )


def _make_manager(username, business):
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="testpass123",
    )
    Membership.objects.create(user=user, business=business, role="MANAGER", status="ACTIVE")
    return user


def _make_product(business, name, category="medicine"):
    return MerchProduct.objects.create(
        business=business,
        name=name,
        kind="pharmacy",
        category=category,
        is_active=True,
        cost_price=10,
        selling_price=15,
        spec_label="",
    )


def _make_batch(business, product, created_offset_days=0):
    """Create a PharmacyBatch whose created_at is offset_days ago."""
    batch = PharmacyBatch.objects.create(
        merch_product=product,
        business=business,
        quantity=10,
        cost_price=10,
        selling_price=15,
        expiry_date=(timezone.now() + timedelta(days=365)).date(),
    )
    if created_offset_days:
        # Back-date by patching the auto_now_add field directly
        PharmacyBatch.objects.filter(pk=batch.pk).update(
            created_at=timezone.now() - timedelta(days=created_offset_days)
        )
        batch.refresh_from_db()
    return batch


# ===========================================================================
# Issue 1: /edit/ redirect — no 404, no template exception
# ===========================================================================

class EditRedirectTest(TestCase):
    """GET /edit/ should redirect cleanly, not 404 with template exceptions."""

    def test_edit_url_redirects(self):
        response = self.client.get("/edit/")
        # Expect a redirect (302), not a 404
        self.assertIn(response.status_code, (301, 302))

    def test_edit_url_redirect_destination(self):
        response = self.client.get("/edit/", follow=False)
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_edit_url_no_server_error(self):
        """Visiting /edit/ must not raise a 500."""
        response = self.client.get("/edit/")
        self.assertNotEqual(response.status_code, 500)


# ===========================================================================
# Issue 2: Pharmacy stock-in recently stocked suggestions
# ===========================================================================

class PharmacyRecentlyStockedTest(TestCase):
    """Pharmacy /stock-in/custom/ shows recently-stocked products in context."""

    def setUp(self):
        self.business = _make_pharmacy_biz()
        self.location = Location.objects.create(business=self.business, name="Main Store")
        self.user = _make_manager("pharmacist", self.business)
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse("pharmacy:stock_in")

    # ------------------------------------------------------------------
    # Basic: context key exists and returns list
    # ------------------------------------------------------------------

    def test_context_has_recently_stocked(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("recently_stocked", response.context)

    def test_recently_stocked_empty_when_no_batches(self):
        response = self.client.get(self.url)
        recently = list(response.context["recently_stocked"])
        self.assertEqual(recently, [])

    # ------------------------------------------------------------------
    # Ordering: most recently stocked first
    # ------------------------------------------------------------------

    def test_recently_stocked_ordered_by_most_recent(self):
        old_product = _make_product(self.business, "Old Drug", "medicine")
        new_product = _make_product(self.business, "New Drug", "medicine")

        _make_batch(self.business, old_product, created_offset_days=10)  # 10 days ago
        _make_batch(self.business, new_product, created_offset_days=1)   # 1 day ago

        response = self.client.get(self.url)
        recently = list(response.context["recently_stocked"])

        self.assertGreaterEqual(len(recently), 2)
        names = [p.name for p in recently]
        # New Drug should appear BEFORE Old Drug
        self.assertLess(names.index("New Drug"), names.index("Old Drug"))

    # ------------------------------------------------------------------
    # Tenant isolation: another business's products must NOT appear
    # ------------------------------------------------------------------

    def test_other_business_products_excluded(self):
        other_biz = _make_pharmacy_biz(name="Other Pharmacy", subdomain="other-pharm")
        other_product = _make_product(other_biz, "Other Drug", "medicine")
        _make_batch(other_biz, other_product)

        # Our business has no batches
        response = self.client.get(self.url)
        recently = list(response.context["recently_stocked"])
        names = [p.name for p in recently]
        self.assertNotIn("Other Drug", names)

    def test_only_own_business_products_shown(self):
        own_product = _make_product(self.business, "My Drug", "medicine")
        other_biz = _make_pharmacy_biz(name="Other Pharmacy 2", subdomain="other-pharm-2")
        other_product = _make_product(other_biz, "Their Drug", "medicine")

        _make_batch(self.business, own_product)
        _make_batch(other_biz, other_product)

        response = self.client.get(self.url)
        recently = list(response.context["recently_stocked"])
        names = [p.name for p in recently]

        self.assertIn("My Drug", names)
        self.assertNotIn("Their Drug", names)

    # ------------------------------------------------------------------
    # Limit: at most 20 products
    # ------------------------------------------------------------------

    def test_recently_stocked_capped_at_20(self):
        for i in range(25):
            p = _make_product(self.business, f"Drug {i}", "medicine")
            _make_batch(self.business, p)

        response = self.client.get(self.url)
        recently = list(response.context["recently_stocked"])
        self.assertLessEqual(len(recently), 20)

    # ------------------------------------------------------------------
    # Prefill: ?prefill_id= pre-selects product in form
    # ------------------------------------------------------------------

    def test_prefill_id_sets_prefill_product(self):
        product = _make_product(self.business, "Prefilled Drug", "medicine")
        _make_batch(self.business, product)

        url = f"{self.url}?prefill_id={product.id}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context.get("prefill_product"))
        self.assertEqual(response.context["prefill_product"].name, "Prefilled Drug")

    def test_prefill_sets_selected_category_from_product(self):
        product = _make_product(self.business, "Cat Drug", "skin_care")
        _make_batch(self.business, product)

        url = f"{self.url}?prefill_id={product.id}"
        response = self.client.get(url)
        self.assertEqual(response.context["selected_category"], "skin_care")

    def test_prefill_wrong_business_returns_none(self):
        """A prefill_id from another business must not expose that product."""
        other_biz = _make_pharmacy_biz(name="Evil Pharmacy", subdomain="evil-pharm")
        other_product = _make_product(other_biz, "Stolen Drug", "medicine")

        url = f"{self.url}?prefill_id={other_product.id}"
        response = self.client.get(url)
        self.assertIsNone(response.context.get("prefill_product"))

    # ------------------------------------------------------------------
    # Template: recently-stocked section renders when products exist
    # ------------------------------------------------------------------

    def test_recently_stocked_section_in_html(self):
        product = _make_product(self.business, "Paracetamol 500mg", "medicine")
        _make_batch(self.business, product)

        response = self.client.get(self.url)
        self.assertContains(response, "recently-stocked-section")
        self.assertContains(response, "Paracetamol 500mg")

    def test_no_recently_stocked_section_without_batches(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, "recently-stocked-section")

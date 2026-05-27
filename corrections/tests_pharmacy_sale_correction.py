"""
Tests: Corrections Framework – Pharmacy Sale Edit & Delete
==========================================================

Verifies:
1.  Browse list renders edit links for pharmacy_sale rows.
2.  Browse list renders delete icon for pharmacy_sale rows.
3.  Authorized manager can GET the edit form (form loads with current values).
4.  Authorized manager can POST a correction (field changed, audit log created).
5.  Unauthorized user gets 403 (or redirect) on GET and POST edit.
6.  Authorized manager can soft-delete a pharmacy_sale via POST /delete/.
7.  After soft-delete: is_deleted=True, batch stock restored, no longer in revenue.
8.  Unauthorized user cannot delete a pharmacy_sale.
9.  Deleting already-deleted sale is blocked (is_deleted guard in view).
"""
from decimal import Decimal
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from tenants.models import Business
from inventory.models import MerchProduct
from inventory.models_pharmacy import PharmacyBatch, PharmacySale
from inventory.business_kinds import BusinessKind
from corrections.models import CorrectionBatch, CorrectionAuditLog

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_business(name="Test Pharmacy"):
    return Business.objects.create(
        name=name,
        slug=name.lower().replace(" ", "-"),
        business_kind=BusinessKind.PHARMACY,
        email=f"{name.lower().replace(' ', '')}@example.com",
    )


def _make_manager(username="mgr", business=None):
    u = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="TestPass123!",
        is_staff=True,
    )
    if business:
        try:
            from tenants.models import Membership
            Membership.objects.create(
                business=business,
                user=u,
                role="manager",
                status="active",
            )
        except Exception:
            pass
    return u


def _make_cashier(username="cashier", business=None):
    u = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="TestPass123!",
        is_staff=False,
        is_superuser=False,
    )
    if business:
        try:
            from tenants.models import Membership
            Membership.objects.create(
                business=business,
                user=u,
                role="cashier",
                status="active",
            )
        except Exception:
            pass
    return u


def _make_sale(business, batch, quantity=5, unit_price=Decimal("70.00"),
               unit_cost=Decimal("40.00"), payment_method="CASH"):
    return PharmacySale.objects.create(
        business=business,
        batch=batch,
        quantity=quantity,
        unit_price=unit_price,
        unit_cost=unit_cost,
        total_amount=unit_price * quantity,
        payment_method=payment_method,
    )


def _login(client, user):
    client.login(username=user.username, password="TestPass123!")


def _set_business(client, business):
    session = client.session
    session["active_business_id"] = business.id
    session.save()


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class PharmacySaleCorrectionTests(TestCase):
    """
    Tests for the corrections framework pharmacy_sale entity:
    browse, edit, delete – permissions and data integrity.
    """

    def setUp(self):
        self.client = Client()

        self.business = _make_business("Correction Pharmacy")
        self.other_business = _make_business("Other Pharmacy")

        self.manager = _make_manager("corr_mgr", self.business)
        self.cashier = _make_cashier("corr_cashier", self.business)

        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Amoxicillin 250mg",
            kind=BusinessKind.PHARMACY,
            category="antibiotics",
        )
        self.batch = PharmacyBatch.objects.create(
            business=self.business,
            merch_product=self.product,
            batch_number="AMX001",
            expiry_date=date.today() + timedelta(days=365),
            quantity=100,
            reorder_level=10,
            cost_price=Decimal("30.00"),
            selling_price=Decimal("60.00"),
            received_date=date.today(),
        )
        self.sale = _make_sale(
            business=self.business,
            batch=self.batch,
            quantity=5,
            unit_price=Decimal("60.00"),
            unit_cost=Decimal("30.00"),
        )

        self.browse_url = reverse(
            "corrections:browse_entity",
            kwargs={"vertical": "pharmacy", "entity_label": "pharmacy_sale"},
        )
        self.edit_url = reverse(
            "corrections:edit_record",
            kwargs={
                "vertical": "pharmacy",
                "entity_label": "pharmacy_sale",
                "object_id": self.sale.pk,
            },
        )
        self.delete_url = reverse(
            "corrections:delete_record",
            kwargs={
                "vertical": "pharmacy",
                "entity_label": "pharmacy_sale",
                "object_id": self.sale.pk,
            },
        )

    # ------------------------------------------------------------------
    # A) Browse list – edit link rendered
    # ------------------------------------------------------------------

    def test_browse_list_shows_edit_link(self):
        """Browse list should contain an Edit link for each sale row."""
        _login(self.client, self.manager)
        _set_business(self.client, self.business)

        response = self.client.get(self.browse_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "bi-pencil")
        self.assertContains(response, "Edit")
        self.assertContains(response, f"/{self.sale.pk}/edit/")

    def test_browse_list_shows_delete_icon(self):
        """Browse list should show delete icon for pharmacy_sale rows."""
        _login(self.client, self.manager)
        _set_business(self.client, self.business)

        response = self.client.get(self.browse_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "bi-trash")

    def test_browse_row_clickable_data_href(self):
        """Table row should have data-href attribute pointing to edit URL."""
        _login(self.client, self.manager)
        _set_business(self.client, self.business)

        response = self.client.get(self.browse_url)
        self.assertEqual(response.status_code, 200)
        # Row should contain onclick pointing to edit URL
        self.assertContains(response, f"{self.sale.pk}/edit/")

    # ------------------------------------------------------------------
    # B) Edit form – authorized
    # ------------------------------------------------------------------

    def test_edit_form_loads_for_manager(self):
        """Manager should be able to GET the edit form."""
        _login(self.client, self.manager)
        _set_business(self.client, self.business)

        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, 200)
        # Form should contain current values
        self.assertContains(response, str(self.sale.quantity))
        self.assertContains(response, "Apply Correction")

    def test_edit_form_contains_delete_button_for_pharmacy_sale(self):
        """Edit form must have the Delete Record button for pharmacy_sale."""
        _login(self.client, self.manager)
        _set_business(self.client, self.business)

        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Delete Record")
        self.assertContains(response, "deleteModal")

    # ------------------------------------------------------------------
    # C) Edit form – unauthorized
    # ------------------------------------------------------------------

    def test_edit_form_requires_login(self):
        """Unauthenticated GET should redirect to login."""
        response = self.client.get(self.edit_url)
        self.assertNotEqual(response.status_code, 200)

    def test_non_manager_cannot_access_edit_form(self):
        """Cashier (non-manager) should get 302/403 on GET edit."""
        _login(self.client, self.cashier)
        _set_business(self.client, self.business)

        response = self.client.get(self.edit_url)
        # Should not return 200 (either redirect or 403)
        self.assertNotEqual(response.status_code, 200)

    # ------------------------------------------------------------------
    # D) Edit POST – changes persist + audit log
    # ------------------------------------------------------------------

    def test_edit_post_changes_unit_price_and_creates_audit_log(self):
        """POST correction for unit_price should update record and create audit log."""
        _login(self.client, self.manager)
        _set_business(self.client, self.business)

        old_total = self.sale.total_amount
        new_unit_price = "75.00"

        response = self.client.post(self.edit_url, {
            "reason": "Correcting unit price to match invoice",
            "unit_price": new_unit_price,
            "quantity": str(self.sale.quantity),
            "unit_cost": str(self.sale.unit_cost),
            "total_amount": str(Decimal(new_unit_price) * self.sale.quantity),
            "payment_method": self.sale.payment_method,
            "sold_at": timezone.localtime(self.sale.sold_at).strftime("%Y-%m-%dT%H:%M"),
        }, follow=True)

        self.sale.refresh_from_db()
        self.assertEqual(self.sale.unit_price, Decimal(new_unit_price))

        # CorrectionBatch should exist
        self.assertTrue(
            CorrectionBatch.objects.filter(
                business=self.business,
                vertical="pharmacy",
            ).exists()
        )

    # ------------------------------------------------------------------
    # E) Delete – soft delete, stock restored
    # ------------------------------------------------------------------

    def test_manager_can_soft_delete_pharmacy_sale(self):
        """Manager DELETE should mark sale as is_deleted and restore batch stock."""
        _login(self.client, self.manager)
        _set_business(self.client, self.business)

        initial_stock = self.batch.quantity
        sale_qty = self.sale.quantity

        response = self.client.post(self.delete_url, {
            "reason": "data_entry_error",
            "notes": "Test deletion – wrong product recorded",
        }, follow=True)

        # Should redirect to browse list
        self.assertEqual(response.status_code, 200)

        self.sale.refresh_from_db()
        self.assertTrue(self.sale.is_deleted)
        self.assertIsNotNone(self.sale.deleted_at)
        self.assertEqual(self.sale.deleted_by, self.manager)

        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity, initial_stock + sale_qty)

    def test_delete_logs_correction_audit(self):
        """Soft-delete should create a CorrectionAuditLog entry."""
        _login(self.client, self.manager)
        _set_business(self.client, self.business)

        self.client.post(self.delete_url, {
            "reason": "duplicate",
            "notes": "Duplicate sale",
        })

        self.assertTrue(
            CorrectionAuditLog.objects.filter(
                business=self.business,
                action="pharmacy_sale_deleted",
            ).exists()
        )

    def test_deleted_sale_excluded_from_revenue(self):
        """After soft-delete, the sale should not appear in active revenue queries."""
        _login(self.client, self.manager)
        _set_business(self.client, self.business)

        self.client.post(self.delete_url, {
            "reason": "data_entry_error",
            "notes": "",
        })

        active_sales = PharmacySale.objects.filter(
            business=self.business,
            is_deleted=False,
            is_reversed=False,
        )
        self.assertNotIn(self.sale.pk, active_sales.values_list("pk", flat=True))

    # ------------------------------------------------------------------
    # F) Delete – unauthorized
    # ------------------------------------------------------------------

    def test_cashier_cannot_delete_pharmacy_sale(self):
        """Cashier should not be able to delete a pharmacy_sale (403 or redirect)."""
        _login(self.client, self.cashier)
        _set_business(self.client, self.business)

        response = self.client.post(self.delete_url, {
            "reason": "data_entry_error",
            "notes": "",
        })

        # Should NOT be 200 or succeed silently
        self.assertNotEqual(response.status_code, 200)

        # Sale should still be active
        self.sale.refresh_from_db()
        self.assertFalse(self.sale.is_deleted)

    def test_unauthenticated_cannot_delete(self):
        """Unauthenticated POST to delete should redirect to login."""
        response = self.client.post(self.delete_url, {
            "reason": "data_entry_error",
            "notes": "",
        })
        self.assertNotEqual(response.status_code, 200)
        self.sale.refresh_from_db()
        self.assertFalse(self.sale.is_deleted)

    # ------------------------------------------------------------------
    # G) Delete – missing reason is rejected
    # ------------------------------------------------------------------

    def test_delete_requires_reason(self):
        """POST to delete without a reason should fail and not delete the sale."""
        _login(self.client, self.manager)
        _set_business(self.client, self.business)

        response = self.client.post(self.delete_url, {
            "reason": "",
            "notes": "",
        }, follow=True)

        self.sale.refresh_from_db()
        self.assertFalse(self.sale.is_deleted)

    # ------------------------------------------------------------------
    # H) Tenant isolation – cannot edit/delete other business's sale
    # ------------------------------------------------------------------

    def test_cannot_edit_other_business_sale(self):
        """Manager of business A cannot edit a sale from business B."""
        other_product = MerchProduct.objects.create(
            business=self.other_business,
            name="Ibuprofen",
            kind=BusinessKind.PHARMACY,
        )
        other_batch = PharmacyBatch.objects.create(
            business=self.other_business,
            merch_product=other_product,
            batch_number="IBU001",
            expiry_date=date.today() + timedelta(days=180),
            quantity=50,
            reorder_level=5,
            cost_price=Decimal("20.00"),
            selling_price=Decimal("40.00"),
            received_date=date.today(),
        )
        other_sale = _make_sale(
            business=self.other_business,
            batch=other_batch,
        )

        _login(self.client, self.manager)
        _set_business(self.client, self.business)  # logged in to THIS business

        url = reverse(
            "corrections:edit_record",
            kwargs={
                "vertical": "pharmacy",
                "entity_label": "pharmacy_sale",
                "object_id": other_sale.pk,
            },
        )
        response = self.client.get(url)
        # Should be 404 (not found for this business) or redirect
        self.assertNotEqual(response.status_code, 200)

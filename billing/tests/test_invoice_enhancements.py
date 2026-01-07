# billing/tests/test_invoice_enhancements.py
"""
Tests for enhanced Invoice model fields and methods.
"""
from decimal import Decimal

import pytest
from django.utils import timezone

from billing.models import BusinessSubscription, Invoice, InvoiceItem, SubscriptionPlan
from tests.helpers.tenant_setup import make_business, make_user


@pytest.mark.django_db
class TestInvoiceEnhancements:
    """Test new Invoice model fields and methods."""

    @pytest.fixture
    def setup_data(self):
        """Create test user and business."""
        user = make_user(email="test@test.com", password="pass")
        business = make_business(created_by=user, name="Test Biz", slug="test-biz")

        # Create subscription
        plan = SubscriptionPlan.objects.create(
            code="test-plan",
            name="Test Plan",
            amount=Decimal("10000.00"),
            currency="MWK",
        )
        subscription = BusinessSubscription.start_trial(business=business, plan=plan, days=30)

        return {
            "user": user,
            "business": business,
            "subscription": subscription,
        }

    def test_invoice_with_subscription_link(self, setup_data):
        """Test that invoice can be linked to subscription."""
        invoice = Invoice.objects.create(
            business=setup_data["business"],
            subscription=setup_data["subscription"],
            created_by=setup_data["user"],
            currency="MWK",
            total=Decimal("10000.00"),
        )

        assert invoice.subscription == setup_data["subscription"]
        assert invoice.subscription.business == setup_data["business"]

    def test_invoice_with_provider_reference(self, setup_data):
        """Test that invoice can store provider reference."""
        provider_ref = "pc-tx-ref-12345"

        invoice = Invoice.objects.create(
            business=setup_data["business"],
            created_by=setup_data["user"],
            currency="MWK",
            total=Decimal("5000.00"),
            provider_reference=provider_ref,
        )

        assert invoice.provider_reference == provider_ref

        # Test querying by provider_reference (indexed)
        found = Invoice.objects.filter(provider_reference=provider_ref).first()
        assert found.id == invoice.id

    def test_invoice_billing_period_fields(self, setup_data):
        """Test new billing_period_start and billing_period_end fields."""
        start_date = timezone.localdate()
        end_date = start_date + timezone.timedelta(days=30)

        invoice = Invoice.objects.create(
            business=setup_data["business"],
            subscription=setup_data["subscription"],
            created_by=setup_data["user"],
            currency="MWK",
            total=Decimal("10000.00"),
            billing_period_start=start_date,
            billing_period_end=end_date,
        )

        assert invoice.billing_period_start == start_date
        assert invoice.billing_period_end == end_date

    def test_invoice_issued_status_and_timestamp(self, setup_data):
        """Test mark_issued method."""
        invoice = Invoice.objects.create(
            business=setup_data["business"],
            created_by=setup_data["user"],
            currency="MWK",
            total=Decimal("5000.00"),
            status=Invoice.Status.DRAFT,
        )

        assert invoice.status == Invoice.Status.DRAFT
        assert invoice.issued_at is None

        invoice.mark_issued()

        invoice.refresh_from_db()
        assert invoice.status == Invoice.Status.ISSUED
        assert invoice.issued_at is not None

    def test_invoice_void_status(self, setup_data):
        """Test mark_void method."""
        invoice = Invoice.objects.create(
            business=setup_data["business"],
            created_by=setup_data["user"],
            currency="MWK",
            total=Decimal("5000.00"),
            status=Invoice.Status.PAID,
        )

        reason = "Payment refunded"
        invoice.mark_void(reason)

        invoice.refresh_from_db()
        assert invoice.status == Invoice.Status.VOID
        assert invoice.meta.get("void_reason") == reason
        assert "voided_at" in invoice.meta

    def test_invoice_pdf_file_field(self, setup_data):
        """Test that invoice has pdf_file field."""
        invoice = Invoice.objects.create(
            business=setup_data["business"],
            created_by=setup_data["user"],
            currency="MWK",
            total=Decimal("5000.00"),
        )

        assert hasattr(invoice, "pdf_file")
        assert hasattr(invoice, "pdf_generated_at")
        # FileField returns None when no file is set
        assert invoice.pdf_file.name is None or invoice.pdf_file.name == ""
        assert invoice.pdf_generated_at is None

    def test_invoice_tax_field_alias(self, setup_data):
        """Test that invoice has both tax and tax_amount fields."""
        # Test that tax_total property works as alias for tax_amount
        invoice = Invoice.objects.create(
            business=setup_data["business"],
            created_by=setup_data["user"],
            currency="MWK",
            subtotal=Decimal("10000.00"),
            total=Decimal("10000.00"),
        )

        # Invoice.save() calls recalc_totals which may set tax_amount to 0
        # Let's just verify the tax_total property exists and returns tax_amount
        invoice.refresh_from_db()

        # Verify both fields exist
        assert hasattr(invoice, "tax")
        assert hasattr(invoice, "tax_amount")
        assert hasattr(invoice, "tax_total")

        # tax_total should be an alias for tax_amount
        assert invoice.tax_total == invoice.tax_amount

    def test_invoice_due_at_field(self, setup_data):
        """Test new due_at timestamp field."""
        due_datetime = timezone.now() + timezone.timedelta(days=7)

        invoice = Invoice.objects.create(
            business=setup_data["business"],
            created_by=setup_data["user"],
            currency="MWK",
            total=Decimal("5000.00"),
            due_at=due_datetime,
        )

        assert invoice.due_at == due_datetime

    def test_invoice_number_uniqueness(self, setup_data):
        """Test that invoice numbers are unique."""
        invoice1 = Invoice.objects.create(
            business=setup_data["business"],
            created_by=setup_data["user"],
            currency="MWK",
            total=Decimal("5000.00"),
        )

        invoice2 = Invoice.objects.create(
            business=setup_data["business"],
            created_by=setup_data["user"],
            currency="MWK",
            total=Decimal("3000.00"),
        )

        # Invoice numbers should be different
        assert invoice1.number != invoice2.number
        assert invoice1.number.startswith("INV-")
        assert invoice2.number.startswith("INV-")


@pytest.mark.django_db
class TestBusinessSubscriptionEnhancements:
    """Test enhanced BusinessSubscription model."""

    @pytest.fixture
    def setup_data(self):
        """Create test user and business."""
        user = make_user(email="test@test.com", password="pass")
        business = make_business(created_by=user, name="Test Biz", slug="test-biz")

        plan = SubscriptionPlan.objects.create(
            code="test-plan",
            name="Test Plan",
            amount=Decimal("10000.00"),
            currency="MWK",
        )
        subscription = BusinessSubscription.start_trial(business=business, plan=plan, days=30)

        return {
            "user": user,
            "business": business,
            "subscription": subscription,
        }

    def test_subscription_provider_customer_ref(self, setup_data):
        """Test provider_customer_ref field."""
        sub = setup_data["subscription"]
        sub.provider_customer_ref = "cus_paychangu_12345"
        sub.save()

        sub.refresh_from_db()
        assert sub.provider_customer_ref == "cus_paychangu_12345"

    def test_subscription_provider_subscription_ref(self, setup_data):
        """Test provider_subscription_ref field."""
        sub = setup_data["subscription"]
        sub.provider_subscription_ref = "sub_paychangu_67890"
        sub.save()

        sub.refresh_from_db()
        assert sub.provider_subscription_ref == "sub_paychangu_67890"

    def test_subscription_suspended_status(self, setup_data):
        """Test SUSPENDED status."""
        sub = setup_data["subscription"]

        sub.suspend()

        sub.refresh_from_db()
        assert sub.status == BusinessSubscription.Status.SUSPENDED

    def test_subscription_trialing_status_alias(self, setup_data):
        """Test that TRIALING status exists as alias."""
        sub = setup_data["subscription"]

        # TRIALING should be available
        assert hasattr(BusinessSubscription.Status, "TRIALING")

        # Can set to TRIALING
        sub.status = BusinessSubscription.Status.TRIALING
        sub.save()

        sub.refresh_from_db()
        assert sub.status == BusinessSubscription.Status.TRIALING

    def test_subscription_cancelled_status_alias(self, setup_data):
        """Test that CANCELLED status exists as alias."""
        sub = setup_data["subscription"]

        # CANCELLED should be available (British spelling)
        assert hasattr(BusinessSubscription.Status, "CANCELLED")

        # Can set to CANCELLED
        sub.status = BusinessSubscription.Status.CANCELLED
        sub.save()

        sub.refresh_from_db()
        assert sub.status == BusinessSubscription.Status.CANCELLED

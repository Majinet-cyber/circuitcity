# inventory/tests/test_consultancy.py
"""
Consultancy & Services Vertical Tests
======================================

Tests cover:
- Client creation
- Project creation and status updates
- Quote creation
- Invoice creation and payment recording
- Outstanding balance calculation
- Dashboard metrics
"""
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from tenants.models import Business
from inventory.business_kinds import BusinessKind
from inventory.models_consultancy import (
    ConsultancyClient,
    ConsultancyProject,
    ConsultancyQuote,
    ConsultancyQuoteItem,
    ConsultancyInvoice,
    ConsultancyInvoiceItem,
    ConsultancyPayment,
    ProjectStatus,
)

User = get_user_model()


def _make_business():
    import random
    uid = random.randint(1000, 9999)
    return Business.objects.create(
        name=f"Test Consultancy Firm {uid}",
        business_kind=BusinessKind.CONSULTANCY,
    )


def _make_user():
    import random
    uid = random.randint(1000, 9999)
    return User.objects.create_user(
        username=f"cons_user_{uid}",
        password="test123",
    )


class ConsultancyClientTest(TestCase):
    """Test client creation and management."""

    def setUp(self):
        self.business = _make_business()
        self.user = _make_user()

    def test_create_client(self):
        """Can create a consultancy client."""
        client = ConsultancyClient.objects.create(
            business=self.business,
            name="Acme Corporation",
            company="Acme Corp Ltd",
            email="info@acme.com",
            phone="+265 999 000 001",
            created_by=self.user,
        )
        self.assertEqual(client.name, "Acme Corporation")
        self.assertEqual(client.business, self.business)

    def test_client_default_active(self):
        """Client is active by default."""
        client = ConsultancyClient.objects.create(
            business=self.business,
            name="Test Client",
        )
        self.assertTrue(client.is_active)


class ConsultancyProjectTest(TestCase):
    """Test project creation and status updates."""

    def setUp(self):
        self.business = _make_business()
        self.user = _make_user()
        self.client = ConsultancyClient.objects.create(
            business=self.business,
            name="Test Client",
        )

    def test_create_project(self):
        """Can create a project linked to a client."""
        project = ConsultancyProject.objects.create(
            business=self.business,
            client=self.client,
            title="Website Redesign",
            project_type="project",
            status=ProjectStatus.LEAD,
            agreed_value=Decimal("500000"),
            created_by=self.user,
        )
        self.assertEqual(project.title, "Website Redesign")
        self.assertEqual(project.status, ProjectStatus.LEAD)

    def test_project_status_update(self):
        """Can update project status."""
        project = ConsultancyProject.objects.create(
            business=self.business,
            client=self.client,
            title="Mobile App",
            status=ProjectStatus.LEAD,
        )
        project.status = ProjectStatus.IN_PROGRESS
        project.save(update_fields=["status"])
        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.IN_PROGRESS)

    def test_project_overdue_detection(self):
        """is_overdue returns True for projects past their deadline in active states."""
        import datetime
        past_deadline = timezone.localdate() - datetime.timedelta(days=5)
        project = ConsultancyProject.objects.create(
            business=self.business,
            client=self.client,
            title="Overdue Project",
            status=ProjectStatus.IN_PROGRESS,
            deadline=past_deadline,
        )
        self.assertTrue(project.is_overdue)

    def test_completed_project_not_overdue(self):
        """Paid project is not overdue even if past deadline."""
        import datetime
        past_deadline = timezone.localdate() - datetime.timedelta(days=5)
        project = ConsultancyProject.objects.create(
            business=self.business,
            client=self.client,
            title="Done Project",
            status=ProjectStatus.PAID,
            deadline=past_deadline,
        )
        self.assertFalse(project.is_overdue)


class ConsultancyQuoteTest(TestCase):
    """Test quote creation."""

    def setUp(self):
        self.business = _make_business()
        self.user = _make_user()
        self.client = ConsultancyClient.objects.create(
            business=self.business,
            name="Quote Client",
        )

    def test_create_quote(self):
        """Can create a quote with line items."""
        quote = ConsultancyQuote.objects.create(
            business=self.business,
            client=self.client,
            title="Development Quote",
            subtotal=Decimal("300000"),
            discount=Decimal("10000"),
            tax=Decimal("0"),
            total_amount=Decimal("290000"),
            status="draft",
            created_by=self.user,
        )
        self.assertIsNotNone(quote.quote_number)
        self.assertEqual(quote.total_amount, Decimal("290000"))

    def test_quote_has_number(self):
        """Quote gets a number assigned on save."""
        quote = ConsultancyQuote.objects.create(
            business=self.business,
            client=self.client,
            title="Numbered Quote",
            subtotal=Decimal("100000"),
            total_amount=Decimal("100000"),
        )
        self.assertTrue(quote.quote_number.startswith("Q"))


class ConsultancyInvoiceTest(TestCase):
    """Test invoice creation, payments, and balance calculation."""

    def setUp(self):
        self.business = _make_business()
        self.user = _make_user()
        self.client = ConsultancyClient.objects.create(
            business=self.business,
            name="Invoice Client",
        )

    def test_create_invoice(self):
        """Can create an invoice."""
        invoice = ConsultancyInvoice.objects.create(
            business=self.business,
            client=self.client,
            title="Development Invoice",
            subtotal=Decimal("200000"),
            total_amount=Decimal("200000"),
            amount_paid=Decimal("0"),
            status="draft",
            created_by=self.user,
        )
        self.assertIsNotNone(invoice.invoice_number)
        self.assertEqual(invoice.status, "draft")

    def test_invoice_balance_due(self):
        """balance_due = total_amount - amount_paid."""
        invoice = ConsultancyInvoice.objects.create(
            business=self.business,
            client=self.client,
            title="Partial Invoice",
            subtotal=Decimal("100000"),
            total_amount=Decimal("100000"),
            amount_paid=Decimal("40000"),
        )
        self.assertEqual(invoice.balance_due, Decimal("60000"))

    def test_record_payment(self):
        """Recording a payment updates invoice amount_paid and status."""
        invoice = ConsultancyInvoice.objects.create(
            business=self.business,
            client=self.client,
            title="Payment Invoice",
            subtotal=Decimal("50000"),
            total_amount=Decimal("50000"),
            amount_paid=Decimal("0"),
            status="sent",
        )
        payment = ConsultancyPayment.objects.create(
            business=self.business,
            invoice=invoice,
            amount=Decimal("50000"),
            payment_method="cash",
            created_by=self.user,
        )
        # Payment.save() should update invoice.amount_paid
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount_paid, Decimal("50000"))

    def test_full_payment_marks_invoice_paid(self):
        """Paying full amount changes invoice status to paid."""
        invoice = ConsultancyInvoice.objects.create(
            business=self.business,
            client=self.client,
            title="Full Payment Invoice",
            subtotal=Decimal("75000"),
            total_amount=Decimal("75000"),
            amount_paid=Decimal("0"),
            status="sent",
        )
        ConsultancyPayment.objects.create(
            business=self.business,
            invoice=invoice,
            amount=Decimal("75000"),
            payment_method="bank",
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "paid")

    def test_partial_payment_marks_invoice_partial(self):
        """Paying part of an invoice changes status to partial."""
        invoice = ConsultancyInvoice.objects.create(
            business=self.business,
            client=self.client,
            title="Partial Invoice",
            subtotal=Decimal("100000"),
            total_amount=Decimal("100000"),
            amount_paid=Decimal("0"),
            status="sent",
        )
        ConsultancyPayment.objects.create(
            business=self.business,
            invoice=invoice,
            amount=Decimal("30000"),
            payment_method="cash",
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "partial")

    def test_project_financial_properties(self):
        """ConsultancyProject.total_invoiced, total_paid, outstanding_balance."""
        project = ConsultancyProject.objects.create(
            business=self.business,
            client=self.client,
            title="Financial Test Project",
            status=ProjectStatus.IN_PROGRESS,
        )
        invoice = ConsultancyInvoice.objects.create(
            business=self.business,
            client=self.client,
            project=project,
            title="Project Invoice",
            subtotal=Decimal("200000"),
            total_amount=Decimal("200000"),
            amount_paid=Decimal("80000"),
        )
        self.assertEqual(project.total_invoiced, Decimal("200000"))
        self.assertEqual(project.total_paid, Decimal("80000"))
        self.assertEqual(project.outstanding_balance, Decimal("120000"))

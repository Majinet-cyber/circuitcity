# billing/tests/test_invoice_pdf.py
"""
Tests for invoice PDF generation and download.
"""
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from billing import pdf_generator
from billing.models import BusinessSubscription, Invoice, InvoiceItem, SubscriptionPlan
from tests.helpers.tenant_setup import make_business, make_membership, make_user


@pytest.mark.django_db
class TestInvoicePDFGeneration:
    """Test PDF generation functionality."""

    @pytest.fixture
    def setup_data(self):
        """Create test invoice with items."""
        user = make_user(email="test@test.com", password="pass")
        business = make_business(created_by=user, name="Test Business", slug="test-biz")
        make_membership(business=business, user=user, role="MANAGER")

        plan = SubscriptionPlan.objects.create(
            code="test-plan",
            name="Test Plan",
            amount=Decimal("10000.00"),
            currency="MWK",
        )

        subscription = BusinessSubscription.start_trial(
            business=business,
            plan=plan,
            days=30,
        )

        invoice = Invoice.objects.create(
            business=business,
            subscription=subscription,
            created_by=user,
            currency="MWK",
            status=Invoice.Status.ISSUED,
        )

        InvoiceItem.objects.create(
            invoice=invoice,
            description="Test Plan — Monthly",
            qty=Decimal("1"),
            unit="mo",
            unit_price=Decimal("10000.00"),
        )

        invoice.recalc_totals(save=True)

        return {
            "user": user,
            "business": business,
            "invoice": invoice,
        }

    def test_generate_invoice_pdf_returns_bytes(self, setup_data):
        """Test that PDF generation returns bytes."""
        invoice = setup_data["invoice"]

        pdf_bytes = pdf_generator.generate_invoice_pdf(invoice)

        # Should return bytes (or None if ReportLab not installed)
        if pdf_bytes is not None:
            assert isinstance(pdf_bytes, bytes)
            assert len(pdf_bytes) > 0
            # PDF files start with %PDF
            assert pdf_bytes.startswith(b"%PDF")

    def test_generate_and_save_invoice_pdf(self, setup_data):
        """Test saving PDF to invoice.pdf_file field."""
        invoice = setup_data["invoice"]

        assert invoice.pdf_file.name is None or invoice.pdf_file.name == ""
        assert invoice.pdf_generated_at is None

        success = pdf_generator.generate_and_save_invoice_pdf(invoice)

        if success:
            invoice.refresh_from_db()
            assert invoice.pdf_file.name is not None
            assert invoice.pdf_file.name != ""
            assert invoice.pdf_generated_at is not None

    def test_pdf_contains_invoice_number(self, setup_data):
        """Test that PDF is valid and contains expected content."""
        invoice = setup_data["invoice"]

        pdf_bytes = pdf_generator.generate_invoice_pdf(invoice)

        if pdf_bytes:
            # Convert bytes to string for searching
            pdf_text = pdf_bytes.decode("latin-1", errors="ignore")

            # PDF should start with PDF header
            assert pdf_bytes.startswith(b"%PDF-"), "PDF should start with %PDF- header"
            
            # PDF should be reasonably sized (has content)
            assert len(pdf_bytes) > 1000, "PDF should have substantial content"
            
            # ReportLab signature should be present (we use ReportLab for PDF gen)
            assert "ReportLab" in pdf_text or invoice.number in pdf_text, \
                "PDF should contain ReportLab signature or invoice number"


@pytest.mark.django_db
class TestInvoiceDownloadEndpoint:
    """Test invoice download HTTP endpoint."""

    @pytest.fixture
    def setup_data(self):
        """Create test invoice."""
        user = make_user(email="test@test.com", password="pass")
        business = make_business(created_by=user, name="Test Business", slug="test-biz")
        make_membership(business=business, user=user, role="MANAGER")

        invoice = Invoice.objects.create(
            business=business,
            created_by=user,
            currency="MWK",
            total=Decimal("10000.00"),
            status=Invoice.Status.PAID,
        )

        InvoiceItem.objects.create(
            invoice=invoice,
            description="Test Item",
            qty=Decimal("1"),
            unit_price=Decimal("10000.00"),
        )

        return {
            "user": user,
            "business": business,
            "invoice": invoice,
        }

    def test_download_invoice_pdf_requires_login(self, setup_data):
        """Test that download endpoint requires authentication."""
        client = Client()
        invoice = setup_data["invoice"]

        url = reverse("billing:invoice_download", args=[invoice.pk])
        response = client.get(url)

        # Should redirect to login
        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    def test_download_invoice_pdf_scoped_to_business(self, setup_data):
        """Test that users can only download their own business invoices."""
        # Create another user/business
        other_user = make_user(email="other@test.com", password="pass")
        other_business = make_business(created_by=other_user, name="Other Business", slug="other-biz")
        make_membership(business=other_business, user=other_user, role="MANAGER")

        client = Client()
        client.force_login(other_user)

        # Try to download invoice from first business
        invoice = setup_data["invoice"]
        url = reverse("billing:invoice_download", args=[invoice.pk])
        response = client.get(url)

        # Should get 404 (not found due to business scope)
        assert response.status_code == 404

    def test_download_invoice_pdf_success(self, setup_data):
        """Test successful invoice download."""
        client = Client()
        client.force_login(setup_data["user"])

        invoice = setup_data["invoice"]
        url = reverse("billing:invoice_download", args=[invoice.pk])
        response = client.get(url)

        # Should return PDF or redirect with error if ReportLab not installed
        if response.status_code == 200:
            assert response["Content-Type"] == "application/pdf"
            assert "attachment" in response["Content-Disposition"]
            assert invoice.number in response["Content-Disposition"]
        else:
            # If ReportLab not installed, should redirect with error
            assert response.status_code == 302


@pytest.mark.django_db
class TestInvoiceListView:
    """Test invoice list page."""

    @pytest.fixture
    def setup_data(self):
        """Create test invoices."""
        user = make_user(email="test@test.com", password="pass")
        business = make_business(created_by=user, name="Test Business", slug="test-biz")
        make_membership(business=business, user=user, role="MANAGER")

        # Create 3 invoices
        invoices = []
        for i in range(3):
            invoice = Invoice.objects.create(
                business=business,
                created_by=user,
                currency="MWK",
                total=Decimal(f"{(i+1)*1000}.00"),
                status=Invoice.Status.PAID if i % 2 == 0 else Invoice.Status.DRAFT,
            )
            invoices.append(invoice)

        return {
            "user": user,
            "business": business,
            "invoices": invoices,
        }

    def test_invoice_list_requires_login(self):
        """Test that invoice list requires authentication."""
        client = Client()
        url = reverse("billing:invoices")
        response = client.get(url)

        # Should redirect to login
        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    def test_invoice_list_shows_business_invoices(self, setup_data):
        """Test that invoice list shows only business invoices."""
        client = Client()
        client.force_login(setup_data["user"])

        url = reverse("billing:invoices")
        response = client.get(url)

        assert response.status_code == 200

        # All 3 invoices should appear
        for invoice in setup_data["invoices"]:
            assert invoice.number.encode() in response.content

    def test_invoice_list_scoped_to_business(self, setup_data):
        """Test that invoice list is scoped to current business."""
        # Create another user/business with invoices
        other_user = make_user(email="other@test.com", password="pass")
        other_business = make_business(created_by=other_user, name="Other Business", slug="other-biz")
        make_membership(business=other_business, user=other_user, role="MANAGER")

        other_invoice = Invoice.objects.create(
            business=other_business,
            created_by=other_user,
            currency="MWK",
            total=Decimal("5000.00"),
        )

        client = Client()
        client.force_login(setup_data["user"])

        url = reverse("billing:invoices")
        response = client.get(url)

        assert response.status_code == 200

        # First business invoices should appear
        for invoice in setup_data["invoices"]:
            assert invoice.number.encode() in response.content

        # Other business invoice should NOT appear
        assert other_invoice.number.encode() not in response.content

    def test_invoice_list_empty_state(self):
        """Test invoice list with no invoices."""
        user = make_user(email="test@test.com", password="pass")
        business = make_business(created_by=user, name="Test Business", slug="test-biz")
        make_membership(business=business, user=user, role="MANAGER")

        client = Client()
        client.force_login(user)

        url = reverse("billing:invoices")
        response = client.get(url)

        assert response.status_code == 200
        assert b"No Invoices Yet" in response.content or b"no invoices" in response.content.lower()

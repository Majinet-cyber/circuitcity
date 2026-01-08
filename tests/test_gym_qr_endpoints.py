"""
Tests for Gym QR code endpoints - PNG image and PDF card generation.
Validates that both public QR endpoints return 200 and correct content types.
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from inventory.models_verticals import GymMember, PaymentMethod
from tenants.models import Business
from tenants.constants import BusinessKind
from decimal import Decimal

User = get_user_model()


class TestGymQREndpoints(TestCase):
    """Test QR code endpoints for gym members"""

    def setUp(self):
        """Set up test data: business, member with QR UUID"""
        # Create business (uses kind and status, not business_kind and is_active)
        self.business = Business.objects.create(
            name="Test Gym",
            kind=BusinessKind.GYM,
            status="ACTIVE",
        )

        # Create a gym member with QR UUID
        self.member = GymMember.objects.create(
            business=self.business,
            name="John Doe",
            email="john@test.com",
            phone="+265991234567",
            member_number="GYM001",
            is_active=True,
            is_archived=False,
        )

        # Ensure QR UUID is set (should be auto-generated)
        assert self.member.qr_uuid is not None, "Member should have QR UUID"

        self.client = Client()

    def test_qr_png_returns_200(self):
        """Test that QR PNG image endpoint returns 200 and image/png content type"""
        url = reverse("gym:member_qr_png", kwargs={"qr_uuid": self.member.qr_uuid})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200, "QR PNG endpoint should return 200")
        self.assertEqual(response["Content-Type"], "image/png", "Content-Type should be image/png")
        self.assertGreater(len(response.content), 0, "PNG image should have content")

    def test_qr_pdf_returns_200(self):
        """Test that QR PDF card endpoint returns 200 and application/pdf content type"""
        url = reverse("gym:member_qr_card_pdf", kwargs={"qr_uuid": self.member.qr_uuid})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200, "QR PDF endpoint should return 200")
        self.assertIn("application/pdf", response["Content-Type"], "Content-Type should be application/pdf")
        self.assertGreater(len(response.content), 0, "PDF should have content")

        # Check Content-Disposition header for attachment
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(".pdf", response["Content-Disposition"])

    def test_qr_status_public_page_returns_200(self):
        """Test that public QR status page returns 200"""
        url = reverse("gym:member_qr_status_public", kwargs={"qr_uuid": self.member.qr_uuid})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200, "QR status page should return 200")
        self.assertIn(self.member.name, response.content.decode(), "Page should contain member name")

    def test_qr_png_invalid_uuid_returns_404(self):
        """Test that invalid UUID returns 404 for PNG endpoint"""
        invalid_uuid = "00000000-0000-0000-0000-000000000000"
        url = reverse("gym:member_qr_png", kwargs={"qr_uuid": invalid_uuid})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404, "Invalid UUID should return 404")

    def test_qr_pdf_invalid_uuid_returns_404(self):
        """Test that invalid UUID returns 404 for PDF endpoint"""
        invalid_uuid = "00000000-0000-0000-0000-000000000000"
        url = reverse("gym:member_qr_card_pdf", kwargs={"qr_uuid": invalid_uuid})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404, "Invalid UUID should return 404")

    def test_qr_pdf_archived_member_returns_404(self):
        """Test that archived member returns 404 for PDF endpoint"""
        # Archive the member
        self.member.is_archived = True
        self.member.save()

        url = reverse("gym:member_qr_card_pdf", kwargs={"qr_uuid": self.member.qr_uuid})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404, "Archived member should return 404")

    def test_qr_endpoints_bypass_authentication(self):
        """
        Test that QR endpoints are publicly accessible without authentication.
        This validates middleware bypass rules.
        """
        # Test PNG endpoint (no login required)
        url_png = reverse("gym:member_qr_png", kwargs={"qr_uuid": self.member.qr_uuid})
        response_png = self.client.get(url_png)
        self.assertEqual(response_png.status_code, 200, "QR PNG should be accessible without login")

        # Test PDF endpoint (no login required)
        url_pdf = reverse("gym:member_qr_card_pdf", kwargs={"qr_uuid": self.member.qr_uuid})
        response_pdf = self.client.get(url_pdf)
        self.assertEqual(response_pdf.status_code, 200, "QR PDF should be accessible without login")

        # Test status page (no login required)
        url_status = reverse("gym:member_qr_status_public", kwargs={"qr_uuid": self.member.qr_uuid})
        response_status = self.client.get(url_status)
        self.assertEqual(response_status.status_code, 200, "QR status page should be accessible without login")

    def test_qr_pdf_content_starts_with_pdf_header(self):
        """Test that PDF response starts with PDF magic bytes (%PDF)"""
        url = reverse("gym:member_qr_card_pdf", kwargs={"qr_uuid": self.member.qr_uuid})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # PDF files start with %PDF
        self.assertTrue(
            response.content.startswith(b"%PDF"),
            "PDF content should start with %PDF magic bytes"
        )


"""
Tests for gym member QR code functionality.
"""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.models_verticals import GymMember, GymPayment
from inventory.services.gym_status import get_member_status
from tenants.models import Business

User = get_user_model()


@pytest.fixture
def business():
    """Create a test gym business"""
    return Business.objects.create(
        name="Test Gym QR", slug="test-gym-qr", status="ACTIVE", business_kind=BusinessKind.GYM
    )


@pytest.fixture
def gym_member(business):
    """Create a gym member with qr_uuid"""
    member = GymMember.objects.create(business=business, name="QR Test Member", phone="0999888777", email="qr@test.com")
    # Ensure qr_uuid is set (should be auto-generated on save)
    if not member.qr_uuid:
        member.save()  # Trigger save to auto-generate qr_uuid
        member.refresh_from_db()
    return member


@pytest.mark.django_db
class TestGymMemberQR:
    """Test QR code generation and public status page"""

    def test_member_has_qr_uuid(self, gym_member):
        """Test that members have qr_uuid set"""
        assert gym_member.qr_uuid is not None
        assert isinstance(gym_member.qr_uuid, uuid.UUID)

    def test_qr_image_endpoint_returns_png(self, client, gym_member):
        """Test that QR image endpoint returns PNG image"""
        url = reverse("gym:member_qr_png", args=[str(gym_member.qr_uuid)])
        response = client.get(url)

        assert response.status_code == 200
        assert response["Content-Type"] == "image/png"
        assert len(response.content) > 0  # Non-empty image

    def test_public_status_page_accessible(self, client, gym_member):
        """Test that public status page is accessible without authentication"""
        url = reverse("gym:member_qr_status_public", args=[str(gym_member.qr_uuid)])
        response = client.get(url)

        assert response.status_code == 200
        assert gym_member.name in response.content.decode()

    def test_public_status_page_shows_active_status(self, client, business, gym_member):
        """Test that public status page shows ACTIVE when member has valid payment"""
        manager = User.objects.create_user(username="qr_manager", password="pass")

        # Create an active payment
        today = timezone.now().date()
        GymPayment.objects.create(
            member=gym_member,
            membership_amount=Decimal("10000.00"),
            trainer_fee=Decimal("0.00"),
            amount=Decimal("10000.00"),
            start_date=today,
            end_date=today + timedelta(days=30),
            paid_by=manager,
            paid_at=timezone.now(),
            is_active=True,
        )

        url = reverse("gym:member_qr_status_public", args=[str(gym_member.qr_uuid)])
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode()
        assert "Active" in content or "ACTIVE" in content

    def test_public_status_page_shows_overdue_status(self, client, gym_member):
        """Test that public status page shows OVERDUE when member has no active payment"""
        url = reverse("gym:member_qr_status_public", args=[str(gym_member.qr_uuid)])
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode()
        assert "Overdue" in content or "OVERDUE" in content

    def test_qr_print_page_accessible(self, client, gym_member):
        """Test that QR print page is accessible"""
        url = reverse("gym:member_qr_print", args=[str(gym_member.qr_uuid)])
        response = client.get(url)

        assert response.status_code == 200
        assert gym_member.name in response.content.decode()

    def test_invalid_qr_uuid_returns_404(self, client):
        """Test that invalid UUID returns 404"""
        invalid_uuid = uuid.uuid4()
        url = reverse("gym:member_qr_status_public", args=[str(invalid_uuid)])
        response = client.get(url)

        assert response.status_code == 404

    def test_get_member_status_active(self, business, gym_member):
        """Test get_member_status returns ACTIVE for member with valid payment"""
        manager = User.objects.create_user(username="status_manager", password="pass")

        today = timezone.now().date()
        GymPayment.objects.create(
            member=gym_member,
            membership_amount=Decimal("10000.00"),
            trainer_fee=Decimal("0.00"),
            amount=Decimal("10000.00"),
            start_date=today,
            end_date=today + timedelta(days=30),
            paid_by=manager,
            paid_at=timezone.now(),
            is_active=True,
        )

        status_info = get_member_status(gym_member)
        assert status_info["status"] == "ACTIVE"
        assert status_info["next_payment_date"] is not None

    def test_get_member_status_overdue(self, gym_member):
        """Test get_member_status returns OVERDUE for member without active payment"""
        status_info = get_member_status(gym_member)
        assert status_info["status"] == "OVERDUE"
        assert status_info["next_payment_date"] is None

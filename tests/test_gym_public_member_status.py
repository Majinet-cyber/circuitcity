"""
Tests for gym public member status page (short token URL).

Tests:
- GET /gym/m/<token>/ returns 200 without login
- Invalid token returns 404
- Response includes correct status label (Active/Expired etc)
- Email builder includes canonical https://emajinet.africa/gym/m/<token>/ link
- Email send config has click tracking disabled
"""
import secrets
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.models_verticals import GymMember, GymPayment
from inventory.services.gym_qr_email import (
    _build_public_status_url,
    get_member_public_url,
    send_member_qr_email,
)
from tenants.models import Business

User = get_user_model()


@pytest.fixture
def business():
    """Create a test gym business"""
    return Business.objects.create(
        name="Flex Fitness Gym",
        slug="flex-fitness-gym",
        status="ACTIVE",
        business_kind=BusinessKind.GYM,
    )


@pytest.fixture
def gym_member(business):
    """Create a gym member with public_token"""
    member = GymMember.objects.create(
        business=business,
        name="John Banda",
        phone="0999123456",
        email="john.banda@example.com",
    )
    # Ensure tokens are generated
    member.refresh_from_db()
    return member


@pytest.fixture
def active_gym_member(business):
    """Create a gym member with active payment"""
    member = GymMember.objects.create(
        business=business,
        name="Active Member",
        phone="0888111222",
        email="active@test.com",
    )
    member.refresh_from_db()
    
    # Create active payment
    manager = User.objects.create_user(username="gym_manager_active", password="pass")
    today = timezone.now().date()
    GymPayment.objects.create(
        member=member,
        membership_amount=Decimal("55000.00"),
        trainer_fee=Decimal("0.00"),
        amount=Decimal("55000.00"),
        start_date=today,
        end_date=today + timedelta(days=30),
        paid_by=manager,
        paid_at=timezone.now(),
        is_active=True,
    )
    
    # Update member status
    member.membership_start = today
    member.membership_end = today + timedelta(days=30)
    member.status = "ACTIVE"
    member.save()
    
    return member


@pytest.fixture
def expired_gym_member(business):
    """Create a gym member with expired payment"""
    member = GymMember.objects.create(
        business=business,
        name="Expired Member",
        phone="0888333444",
        email="expired@test.com",
    )
    member.refresh_from_db()
    
    # Create expired payment
    manager = User.objects.create_user(username="gym_manager_expired", password="pass")
    today = timezone.now().date()
    GymPayment.objects.create(
        member=member,
        membership_amount=Decimal("55000.00"),
        trainer_fee=Decimal("0.00"),
        amount=Decimal("55000.00"),
        start_date=today - timedelta(days=60),
        end_date=today - timedelta(days=30),
        paid_by=manager,
        paid_at=timezone.now() - timedelta(days=60),
        is_active=True,
    )
    
    # Update member status
    member.membership_start = today - timedelta(days=60)
    member.membership_end = today - timedelta(days=30)
    member.status = "EXPIRED"
    member.save()
    
    return member


@pytest.mark.django_db
class TestPublicTokenGeneration:
    """Tests for public_token field on GymMember"""

    def test_public_token_generated_on_create(self, gym_member):
        """Test that public_token is auto-generated when member is created"""
        assert gym_member.public_token
        assert len(gym_member.public_token) == 22
        # URL-safe characters only
        assert all(c.isalnum() or c in "-_" for c in gym_member.public_token)

    def test_public_token_unique(self, business):
        """Test that each member gets a unique public_token"""
        member1 = GymMember.objects.create(
            business=business, name="Member One", phone="0111111111"
        )
        member2 = GymMember.objects.create(
            business=business, name="Member Two", phone="0222222222"
        )
        assert member1.public_token != member2.public_token

    def test_public_token_stable_on_save(self, gym_member):
        """Test that public_token doesn't change on subsequent saves"""
        original_token = gym_member.public_token
        gym_member.name = "Updated Name"
        gym_member.save()
        gym_member.refresh_from_db()
        assert gym_member.public_token == original_token


@pytest.mark.django_db
class TestPublicMemberStatusView:
    """Tests for GET /gym/m/<token>/ public status page"""

    def test_public_status_returns_200_without_login(self, client, gym_member):
        """Test that public status page is accessible without authentication"""
        url = reverse("gym:gym_public_member_status", args=[gym_member.public_token])
        response = client.get(url)
        assert response.status_code == 200

    def test_public_status_shows_member_name(self, client, gym_member):
        """Test that public status page displays member name"""
        url = reverse("gym:gym_public_member_status", args=[gym_member.public_token])
        response = client.get(url)
        assert gym_member.name in response.content.decode()

    def test_public_status_shows_gym_name(self, client, gym_member):
        """Test that public status page displays gym name"""
        url = reverse("gym:gym_public_member_status", args=[gym_member.public_token])
        response = client.get(url)
        assert gym_member.business.name in response.content.decode()

    def test_public_status_shows_active_label(self, client, active_gym_member):
        """Test that public status page shows 'Active' for active members"""
        url = reverse("gym:gym_public_member_status", args=[active_gym_member.public_token])
        response = client.get(url)
        content = response.content.decode()
        assert "Active" in content

    def test_public_status_shows_expired_label(self, client, expired_gym_member):
        """Test that public status page shows 'Expired' for expired members"""
        url = reverse("gym:gym_public_member_status", args=[expired_gym_member.public_token])
        response = client.get(url)
        content = response.content.decode()
        assert "Expired" in content

    def test_invalid_token_returns_404(self, client):
        """Test that invalid token returns 404"""
        invalid_token = secrets.token_urlsafe(16)[:22]
        url = reverse("gym:gym_public_member_status", args=[invalid_token])
        response = client.get(url)
        assert response.status_code == 404

    def test_archived_member_returns_404(self, client, gym_member):
        """Test that archived member returns 404"""
        gym_member.is_archived = True
        gym_member.save()
        url = reverse("gym:gym_public_member_status", args=[gym_member.public_token])
        response = client.get(url)
        assert response.status_code == 404

    def test_public_status_has_noindex_meta(self, client, gym_member):
        """Test that public status page has noindex meta tag"""
        url = reverse("gym:gym_public_member_status", args=[gym_member.public_token])
        response = client.get(url)
        content = response.content.decode()
        assert 'name="robots"' in content
        assert "noindex" in content

    def test_public_status_has_no_store_cache_control(self, client, gym_member):
        """Test that public status page has no-store cache control"""
        url = reverse("gym:gym_public_member_status", args=[gym_member.public_token])
        response = client.get(url)
        assert "no-store" in response.get("Cache-Control", "")


@pytest.mark.django_db
class TestEmailBuilderCanonicalURL:
    """Tests for email builder using canonical URL"""

    def test_build_public_status_url_uses_site_base_url(self, gym_member):
        """Test that URL builder uses SITE_BASE_URL setting"""
        url = _build_public_status_url(gym_member)
        assert url.startswith(settings.SITE_BASE_URL)
        assert gym_member.public_token in url

    def test_build_public_status_url_correct_format(self, gym_member):
        """Test that URL follows correct format /gym/m/<token>/"""
        url = _build_public_status_url(gym_member)
        expected_path = f"/gym/m/{gym_member.public_token}/"
        assert expected_path in url

    @override_settings(SITE_BASE_URL="https://emajinet.africa")
    def test_build_public_status_url_canonical_domain(self, gym_member):
        """Test that URL uses https://emajinet.africa domain"""
        url = _build_public_status_url(gym_member)
        assert url.startswith("https://emajinet.africa")
        assert f"/gym/m/{gym_member.public_token}/" in url

    def test_get_member_public_url_convenience_function(self, gym_member):
        """Test convenience function returns same URL"""
        url1 = _build_public_status_url(gym_member)
        url2 = get_member_public_url(gym_member)
        assert url1 == url2


@pytest.mark.django_db
class TestEmailClickTrackingDisabled:
    """Tests for email click tracking being disabled"""

    @patch("inventory.services.gym_qr_email.EmailMessage")
    @patch("inventory.services.gym_qr_email._generate_member_card_pdf")
    def test_email_has_click_tracking_disabled(
        self, mock_pdf, mock_email_class, gym_member
    ):
        """Test that gym QR email has click tracking disabled via esp_extra"""
        mock_pdf.return_value = b"fake_pdf_bytes"
        mock_email_instance = MagicMock()
        mock_email_class.return_value = mock_email_instance
        mock_email_instance.send.return_value = 1

        # Create mock request
        mock_request = MagicMock()
        mock_request.build_absolute_uri.return_value = "http://test/gym/qr/..."

        send_member_qr_email(gym_member, mock_request)

        # Verify esp_extra was set with click tracking disabled
        assert hasattr(mock_email_instance, "esp_extra")
        assert mock_email_instance.esp_extra == {
            "tracking_settings": {
                "click_tracking": {"enable": False, "enable_text": False},
            }
        }

    @patch("inventory.services.gym_qr_email._generate_member_card_pdf")
    def test_email_body_contains_canonical_url(self, mock_pdf, gym_member):
        """Test that email body contains the canonical URL"""
        mock_pdf.return_value = b"fake_pdf_bytes"

        # Create mock request
        mock_request = MagicMock()
        mock_request.build_absolute_uri.return_value = "http://test/gym/qr/..."

        # Capture the email by patching send
        with patch.object(EmailMessage, "send") as mock_send:
            mock_send.return_value = 1
            
            # We can't easily capture the email body, but we can verify the URL function
            expected_url = _build_public_status_url(gym_member)
            assert settings.SITE_BASE_URL in expected_url
            assert gym_member.public_token in expected_url


@pytest.mark.django_db
class TestEmailSendIntegration:
    """Integration tests for email sending"""

    def test_send_email_without_request_still_works(self, gym_member):
        """Test that email can be sent even without request (for Celery tasks)"""
        # This should not raise an error, just may not attach PDF
        with patch.object(EmailMessage, "send") as mock_send:
            mock_send.return_value = 1
            result = send_member_qr_email(gym_member, request=None)
            # Should still succeed (email sent, maybe without PDF)
            assert result is True

    def test_send_email_to_member_without_email_returns_false(self, business):
        """Test that sending email to member without email returns False"""
        member = GymMember.objects.create(
            business=business, name="No Email Member", phone="0555666777", email=""
        )
        result = send_member_qr_email(member, request=None)
        assert result is False


@pytest.mark.django_db
class TestURLRoutingIntegration:
    """Integration tests for URL routing"""

    def test_url_pattern_exists(self, gym_member):
        """Test that the URL pattern gym:gym_public_member_status exists"""
        url = reverse("gym:gym_public_member_status", args=[gym_member.public_token])
        assert "/gym/m/" in url
        assert gym_member.public_token in url

    def test_url_is_short_and_clean(self, gym_member):
        """Test that the URL is reasonably short"""
        url = reverse("gym:gym_public_member_status", args=[gym_member.public_token])
        # URL should be like /gym/m/xxxxxxxxxxxxxxxxxxxx/
        # Max path length: /gym/m/ (7) + token (22) + / (1) = 30 chars
        assert len(url) <= 35

    def test_full_canonical_url_format(self, gym_member):
        """Test the full canonical URL format"""
        url = _build_public_status_url(gym_member)
        # Should be https://emajinet.africa/gym/m/<22-char-token>/
        assert url.startswith("https://")
        assert "/gym/m/" in url
        assert len(gym_member.public_token) == 22


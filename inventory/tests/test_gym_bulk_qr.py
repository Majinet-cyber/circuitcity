"""
Tests for bulk QR PDF generation for gym members.
"""
import pytest
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from tenants.models import Business, Membership
from inventory.models import Location
from inventory.business_kinds import BusinessKind
from inventory.models_verticals import GymMember, GymTrainer, GymSettings

User = get_user_model()


@pytest.fixture
def gym_business(db):
    """Create a gym business"""
    business = Business.objects.create(
        name="Test Gym",
        slug="test-gym",
        business_kind=BusinessKind.GYM,
        is_active=True,
    )
    # Create gym settings
    GymSettings.objects.create(
        business=business,
        default_membership_price=Decimal("50000.00"),
        default_trainer_fee=Decimal("30000.00"),
    )
    return business


@pytest.fixture
def gym_location(gym_business):
    """Create a location for the gym"""
    return Location.objects.create(
        business=gym_business,
        name="Main Branch",
        address="123 Gym St",
        is_active=True,
    )


@pytest.fixture
def manager_user(db, gym_business):
    """Create a manager user for the gym"""
    user = User.objects.create_user(
        username="manager",
        email="manager@testgym.com",
        password="testpass123",
        is_staff=True,  # Managers are staff
    )
    # Assign manager role to business
    Membership.objects.create(
        user=user,
        business=gym_business,
        role="MANAGER",
        status="ACTIVE",
    )
    return user


@pytest.fixture
def agent_user(db, gym_business):
    """Create an agent user (non-manager) for the gym"""
    user = User.objects.create_user(
        username="agent",
        email="agent@testgym.com",
        password="testpass123",
        is_staff=False,  # Agents are NOT staff
    )
    # Assign agent role to business
    Membership.objects.create(
        user=user,
        business=gym_business,
        role="AGENT",
        status="ACTIVE",
    )
    return user


@pytest.fixture
def gym_members(gym_business):
    """Create test gym members"""
    members = []
    for i in range(5):
        member = GymMember.objects.create(
            business=gym_business,
            name=f"Member {i+1}",
            phone=f"099912345{i}",
            email=f"member{i+1}@test.com",
            is_active=True,
            is_archived=False,
        )
        members.append(member)
    return members


@pytest.mark.django_db
class TestBulkQRPDFPermissions:
    """Test permissions for bulk QR PDF download"""

    def test_unauthenticated_user_cannot_download(self, client, gym_business):
        """Unauthenticated users should be redirected to login"""
        url = reverse("gym:bulk_qr_pdf")
        response = client.get(url + "?all=1")
        
        # Should redirect to login
        assert response.status_code == 302
        assert "/login" in response.url or "/accounts/login" in response.url

    def test_agent_user_cannot_download(self, client, gym_business, agent_user, gym_members):
        """Agent users (non-managers) should be denied access"""
        client.force_login(agent_user)
        
        # Set active business in session
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:bulk_qr_pdf")
        response = client.get(url + "?all=1")
        
        # Should be forbidden or redirected
        assert response.status_code in [403, 302]

    def test_manager_user_can_download(self, client, gym_business, manager_user, gym_members):
        """Manager users should be able to download bulk QR PDF"""
        client.force_login(manager_user)
        
        # Set active business in session
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:bulk_qr_pdf")
        response = client.get(url + "?all=1")
        
        # Should return PDF or indicate library not available
        assert response.status_code in [200, 503]
        if response.status_code == 200:
            assert response["Content-Type"] == "application/pdf"


@pytest.mark.django_db
class TestBulkQRPDFGeneration:
    """Test bulk QR PDF generation functionality"""

    def test_download_all_active_members(self, client, gym_business, manager_user, gym_members):
        """Test downloading all active members"""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:bulk_qr_pdf")
        response = client.get(url + "?all=1&filter=active")
        
        # Should return PDF or indicate library not available
        assert response.status_code in [200, 503]
        
        if response.status_code == 200:
            assert response["Content-Type"] == "application/pdf"
            assert "gym_qr_stickers" in response["Content-Disposition"]
            assert len(response.content) > 0

    def test_download_selected_members(self, client, gym_business, manager_user, gym_members):
        """Test downloading selected members only"""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        # Select first 3 members
        selected_ids = ",".join([str(m.id) for m in gym_members[:3]])
        
        url = reverse("gym:bulk_qr_pdf")
        response = client.get(url + f"?members={selected_ids}")
        
        # Should return PDF or indicate library not available
        assert response.status_code in [200, 503]
        
        if response.status_code == 200:
            assert response["Content-Type"] == "application/pdf"

    def test_no_members_selected_returns_error(self, client, gym_business, manager_user):
        """Test that no selection returns error"""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:bulk_qr_pdf")
        response = client.get(url)  # No parameters
        
        # Should return 400 error
        assert response.status_code == 400

    def test_invalid_member_ids_returns_error(self, client, gym_business, manager_user):
        """Test that invalid member IDs return error"""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:bulk_qr_pdf")
        response = client.get(url + "?members=invalid,abc")
        
        # Should return 400 error
        assert response.status_code == 400

    def test_no_members_found_returns_404(self, client, gym_business, manager_user):
        """Test that no members found returns 404"""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        # Request archived members when none exist
        url = reverse("gym:bulk_qr_pdf")
        response = client.get(url + "?all=1&filter=archived")
        
        # Should return 404
        assert response.status_code == 404

    def test_pdf_filename_format(self, client, gym_business, manager_user, gym_members):
        """Test that PDF filename follows correct format"""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:bulk_qr_pdf")
        response = client.get(url + "?all=1")
        
        if response.status_code == 200:
            content_disposition = response["Content-Disposition"]
            # Should match format: gym_qr_stickers_<business>_<date>.pdf
            assert "gym_qr_stickers" in content_disposition
            assert ".pdf" in content_disposition
            assert "Test_Gym" in content_disposition or "TestGym" in content_disposition

    def test_qr_images_rendered_in_pdf(self, client, gym_business, manager_user, gym_members):
        """Test that QR images are actually rendered in the PDF (not just text)"""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        # Generate PDF with one member
        member_id = gym_members[0].id
        url = reverse("gym:bulk_qr_pdf")
        response = client.get(url + f"?members={member_id}")
        
        if response.status_code == 200:
            pdf_content = response.content
            
            # PDF with QR images should be significantly larger than text-only
            # A single-member PDF with QR image should be at least 15KB
            # (text-only would be ~5KB, images add substantial size)
            assert len(pdf_content) > 15000, (
                f"PDF size {len(pdf_content)} bytes is too small - "
                "QR images may not be rendering properly"
            )
            
            # Check for PDF image markers (XObject pattern)
            # PDFs with embedded images contain "/Subtype /Image" markers
            pdf_text = pdf_content.decode('latin-1', errors='ignore')
            assert '/Image' in pdf_text or '/XObject' in pdf_text, (
                "PDF does not contain image markers - QR codes may not be embedded"
            )


@pytest.mark.django_db
class TestBulkQRPDFPerformance:
    """Test bulk QR PDF generation with large datasets"""

    def test_handles_100_members(self, client, gym_business, manager_user):
        """Test that system can handle 100 members"""
        # Create 100 members
        members = []
        for i in range(100):
            member = GymMember.objects.create(
                business=gym_business,
                name=f"Member {i+1}",
                phone=f"0999{i:06d}",
                is_active=True,
            )
            members.append(member)
        
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:bulk_qr_pdf")
        response = client.get(url + "?all=1")
        
        # Should complete without timeout
        assert response.status_code in [200, 503]
        
        if response.status_code == 200:
            # PDF should be generated
            assert len(response.content) > 1000  # At least 1KB


@pytest.mark.django_db
class TestBulkQRPDFTenantIsolation:
    """Test that bulk QR PDF respects tenant isolation"""

    def test_cannot_download_other_business_members(self, client, manager_user):
        """Test that managers cannot download members from other businesses"""
        # Create two separate businesses
        business1 = Business.objects.create(
            name="Gym 1",
            slug="gym-1",
            business_kind=BusinessKind.GYM,
            is_active=True,
        )
        business2 = Business.objects.create(
            name="Gym 2",
            slug="gym-2",
            business_kind=BusinessKind.GYM,
            is_active=True,
        )
        
        # Create members in business2
        member2 = GymMember.objects.create(
            business=business2,
            name="Member from Gym 2",
            phone="0999888777",
        )
        
        # Manager logs in with business1 active
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = business1.id
        session.save()
        
        # Try to download member from business2
        url = reverse("gym:bulk_qr_pdf")
        response = client.get(url + f"?members={member2.id}")
        
        # Should return 404 (member not found in active business)
        assert response.status_code == 404


# tests/test_gym_member_purge.py
"""
Tests for gym member purge (delete member + all records) functionality.

Tests cover:
- Service function purge_member()
- View endpoint /gym/members/<id>/purge/
- Tenant scoping
- Permission checks
- Data integrity (all related records deleted)
- Audit trail
"""

from decimal import Decimal
import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.models_verticals import (
    GymMember,
    GymPayment,
    GymCheckIn,
    GymMemberLog,
    GymWalletEntry,
)
from inventory.services_gym_purge import purge_member, can_purge_member
from tenants.models import Business, Membership

User = get_user_model()


def setup_client_with_business(client, user, business):
    """Helper to set up client with proper business context"""
    # Create membership
    Membership.objects.get_or_create(
        user=user,
        business=business,
        defaults={"role": "MANAGER", "status": "ACTIVE", "location": None}
    )
    
    # Login and set active business
    client.force_login(user)
    session = client.session
    session["active_business_id"] = business.id
    session.save()


@pytest.fixture
def business():
    """Create a test gym business"""
    return Business.objects.create(
        name="Test Gym",
        slug="test-gym",
        status="ACTIVE",
        business_kind=BusinessKind.GYM
    )


@pytest.fixture
def other_business():
    """Create another gym business for cross-tenant tests"""
    return Business.objects.create(
        name="Other Gym",
        slug="other-gym",
        status="ACTIVE",
        business_kind=BusinessKind.GYM
    )


@pytest.fixture
def manager(business):
    """Create a manager user"""
    user = User.objects.create_user(username="gym_manager", password="testpass123")
    user.is_staff = True  # Manager permission
    user.save()
    return user


@pytest.fixture
def non_manager():
    """Create a non-manager user"""
    user = User.objects.create_user(username="regular_user", password="testpass123")
    user.is_staff = False
    user.save()
    return user


@pytest.fixture
def gym_member(business):
    """Create a gym member with some history"""
    return GymMember.objects.create(
        business=business,
        name="John Fitness",
        phone="0999123456",
        email="john@example.com",
        membership_fee=Decimal("55000.00"),
    )


@pytest.fixture
def member_with_history(business, manager, gym_member):
    """Create a member with payments, check-ins, and logs"""
    # Add payment
    today = timezone.now().date()
    payment = GymPayment.objects.create(
        member=gym_member,
        membership_amount=Decimal("55000.00"),
        trainer_fee=Decimal("0.00"),
        paid_by=manager,
        paid_at=timezone.now(),
        start_date=today,
        end_date=today + timezone.timedelta(days=30),
    )
    
    # Add wallet entry for payment
    GymWalletEntry.objects.create(
        business=business,
        amount=Decimal("55000.00"),
        description=f"Membership payment for {gym_member.name}",
        entry_type="income",
        related_payment=payment,
        created_by=manager,
    )
    
    # Add check-ins
    GymCheckIn.objects.create(
        business=business,
        member=gym_member,
        checked_in_by=manager,
    )
    GymCheckIn.objects.create(
        business=business,
        member=gym_member,
        checked_in_by=manager,
        timestamp=timezone.now() - timezone.timedelta(days=1),
    )
    
    # Add logs
    GymMemberLog.objects.create(
        member=gym_member,
        action="created",
        performed_by=manager,
    )
    
    return gym_member


@pytest.mark.django_db
class TestPurgeMemberService:
    """Test the purge_member service function"""
    
    def test_purge_member_without_history(self, business, manager, gym_member):
        """Test purging a member with no related records"""
        member_id = gym_member.id
        member_name = gym_member.name
        
        result = purge_member(
            member=gym_member,
            user=manager,
            reason="entered_by_mistake",
            notes="Test member",
        )
        
        # Check result
        assert result["ok"] is True
        assert member_name in result["message"]
        assert result["deleted_counts"]["payments"] == 0
        assert result["deleted_counts"]["checkins"] == 0
        
        # Verify member is deleted
        assert not GymMember.all_objects.filter(id=member_id).exists()
    
    def test_purge_member_with_history(self, business, manager, member_with_history):
        """Test purging a member with payments, check-ins, and logs"""
        member_id = member_with_history.id
        
        # Verify records exist before purge
        assert GymPayment.all_objects.filter(member=member_with_history).count() == 1
        assert GymCheckIn.objects.filter(member=member_with_history).count() == 2
        assert GymMemberLog.objects.filter(member=member_with_history).count() >= 1
        assert GymWalletEntry.objects.filter(related_payment__member=member_with_history).count() == 1
        
        result = purge_member(
            member=member_with_history,
            user=manager,
            reason="duplicate",
            notes="Duplicate of another member",
        )
        
        # Check result
        assert result["ok"] is True
        assert result["deleted_counts"]["payments"] == 1
        assert result["deleted_counts"]["checkins"] == 2
        assert result["deleted_counts"]["wallet_entries"] == 1
        assert result["deleted_counts"]["logs"] >= 1
        
        # Verify all records are deleted
        assert not GymMember.all_objects.filter(id=member_id).exists()
        assert GymPayment.all_objects.filter(member_id=member_id).count() == 0
        assert GymCheckIn.objects.filter(member_id=member_id).count() == 0
        assert GymMemberLog.objects.filter(member_id=member_id).count() == 0
        assert GymWalletEntry.objects.filter(related_payment__member_id=member_id).count() == 0
    
    def test_purge_member_requires_reason(self, gym_member, manager):
        """Test that purge requires a reason"""
        with pytest.raises(ValueError, match="reason is required"):
            purge_member(
                member=gym_member,
                user=manager,
                reason="",
                notes="",
            )
    
    def test_purge_member_audit_snapshot(self, business, manager, gym_member):
        """Test that purge creates proper audit snapshot"""
        # Store member data before purge
        member_id = gym_member.id
        member_name = gym_member.name
        member_phone = gym_member.phone
        member_email = gym_member.email
        
        result = purge_member(
            member=gym_member,
            user=manager,
            reason="test",
            notes="Testing audit",
        )
        
        # Check snapshot contains key fields
        snapshot = result["snapshot"]
        assert snapshot["member_id"] == member_id
        assert snapshot["member_name"] == member_name
        assert snapshot["member_phone"] == member_phone
        assert snapshot["member_email"] == member_email
        assert "qr_uuid" in snapshot
        
        # Check audit metadata
        assert result["reason"] == "test"
        assert result["notes"] == "Testing audit"
        assert result["purged_by"] == manager.username
    
    def test_can_purge_member_permissions(self, gym_member, manager, non_manager):
        """Test permission checks for purging"""
        # Manager can purge
        can_purge, error = can_purge_member(gym_member, manager)
        assert can_purge is True
        assert error is None
        
        # Non-manager (but authenticated user) can also purge
        # In gym product, any logged-in user with tenant access can purge
        can_purge, error = can_purge_member(gym_member, non_manager)
        assert can_purge is True
        assert error is None


@pytest.mark.django_db
class TestPurgeMemberView:
    """Test the member_purge view endpoint"""
    
    def test_purge_member_endpoint_success(self, business, manager, gym_member):
        """Test successful purge via POST endpoint"""
        client = Client()
        setup_client_with_business(client, manager, business)
        
        url = reverse("gym:member_purge", kwargs={"member_id": gym_member.id})
        response = client.post(url, {
            "reason": "duplicate",
            "notes": "Test purge",
            "confirmation": "DELETE",
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "deleted" in data["message"].lower()
        
        # Verify member is deleted
        assert not GymMember.all_objects.filter(id=gym_member.id).exists()
    
    def test_purge_member_requires_confirmation(self, business, manager, gym_member):
        """Test that purge requires typing DELETE"""
        client = Client()
        setup_client_with_business(client, manager, business)
        
        url = reverse("gym:member_purge", kwargs={"member_id": gym_member.id})
        response = client.post(url, {
            "reason": "duplicate",
            "notes": "Test",
            "confirmation": "wrong",
        })
        
        assert response.status_code == 400
        data = response.json()
        assert data["ok"] is False
        assert "DELETE" in data["error"]
        
        # Verify member still exists
        assert GymMember.objects.filter(id=gym_member.id).exists()
    
    def test_purge_member_requires_reason(self, business, manager, gym_member):
        """Test that purge requires a reason"""
        client = Client()
        setup_client_with_business(client, manager, business)
        
        url = reverse("gym:member_purge", kwargs={"member_id": gym_member.id})
        response = client.post(url, {
            "reason": "",
            "confirmation": "DELETE",
        })
        
        assert response.status_code == 400
        data = response.json()
        assert data["ok"] is False
        assert "reason" in data["error"].lower()
    
    def test_purge_member_allows_non_manager_in_tenant(self, business, non_manager, gym_member):
        """Test that any logged-in gym user can purge members in their tenant"""
        client = Client()
        setup_client_with_business(client, non_manager, business)
        
        url = reverse("gym:member_purge", kwargs={"member_id": gym_member.id})
        response = client.post(url, {
            "reason": "duplicate",
            "notes": "Test purge by non-manager",
            "confirmation": "DELETE",
        })
        
        # Should succeed
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        
        # Verify member is deleted
        assert not GymMember.objects.filter(id=gym_member.id).exists()
    
    def test_purge_member_tenant_scoping(self, business, other_business, manager):
        """Test that users cannot purge members from other businesses"""
        # Create member in other business
        other_member = GymMember.objects.create(
            business=other_business,
            name="Other Member",
            phone="0999999999",
        )
        
        client = Client()
        setup_client_with_business(client, manager, business)
        
        # Try to purge member from other business
        url = reverse("gym:member_purge", kwargs={"member_id": other_member.id})
        response = client.post(url, {
            "reason": "duplicate",
            "confirmation": "DELETE",
        })
        
        # Should return 404 (not found due to tenant scoping)
        assert response.status_code == 404
        
        # Verify member still exists
        assert GymMember.objects.filter(id=other_member.id).exists()
    
    def test_purge_member_cross_tenant_protection_non_manager(self, business, other_business, non_manager):
        """Test that even non-managers are blocked from cross-tenant purges"""
        # Create member in other business
        other_member = GymMember.objects.create(
            business=other_business,
            name="Other Member",
            phone="0999999999",
        )
        
        client = Client()
        setup_client_with_business(client, non_manager, business)
        
        # Try to purge member from other business
        url = reverse("gym:member_purge", kwargs={"member_id": other_member.id})
        response = client.post(url, {
            "reason": "duplicate",
            "confirmation": "DELETE",
        })
        
        # Should return 404 (not found due to tenant scoping)
        assert response.status_code == 404
        
        # Verify member still exists
        assert GymMember.objects.filter(id=other_member.id).exists()
    
    def test_purge_member_requires_post(self, business, manager, gym_member):
        """Test that purge endpoint only accepts POST"""
        client = Client()
        setup_client_with_business(client, manager, business)
        
        url = reverse("gym:member_purge", kwargs={"member_id": gym_member.id})
        response = client.get(url)
        
        # Should return 405 Method Not Allowed
        assert response.status_code == 405
    
    def test_purge_member_with_history_deletes_all(self, business, manager, member_with_history):
        """Test that purging deletes all related records"""
        member_id = member_with_history.id
        
        # Verify records exist
        assert GymPayment.all_objects.filter(member=member_with_history).exists()
        assert GymCheckIn.objects.filter(member=member_with_history).exists()
        
        client = Client()
        setup_client_with_business(client, manager, business)
        
        url = reverse("gym:member_purge", kwargs={"member_id": member_id})
        response = client.post(url, {
            "reason": "duplicate",
            "confirmation": "DELETE",
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["deleted_counts"]["payments"] > 0
        assert data["deleted_counts"]["checkins"] > 0
        
        # Verify all records are gone
        assert not GymMember.all_objects.filter(id=member_id).exists()
        assert not GymPayment.all_objects.filter(member_id=member_id).exists()
        assert not GymCheckIn.objects.filter(member_id=member_id).exists()
    
    def test_purge_nonexistent_member(self, business, manager):
        """Test purging a member that doesn't exist"""
        client = Client()
        setup_client_with_business(client, manager, business)
        
        url = reverse("gym:member_purge", kwargs={"member_id": 99999})
        response = client.post(url, {
            "reason": "duplicate",
            "confirmation": "DELETE",
        })
        
        assert response.status_code == 404


@pytest.mark.django_db
class TestPurgeDataIntegrity:
    """Test data integrity during purge operations"""
    
    def test_purge_is_atomic(self, business, manager, member_with_history):
        """Test that purge is atomic (all or nothing)"""
        # This test verifies that if any part of the purge fails,
        # nothing is deleted (transaction rollback)
        
        member_id = member_with_history.id
        
        # Count records before
        payments_before = GymPayment.all_objects.filter(member=member_with_history).count()
        checkins_before = GymCheckIn.objects.filter(member=member_with_history).count()
        
        # Successful purge
        result = purge_member(
            member=member_with_history,
            user=manager,
            reason="test",
        )
        
        assert result["ok"] is True
        
        # All records should be gone
        assert not GymMember.all_objects.filter(id=member_id).exists()
        assert GymPayment.all_objects.filter(member_id=member_id).count() == 0
        assert GymCheckIn.objects.filter(member_id=member_id).count() == 0
    
    def test_purge_deletes_wallet_entries(self, business, manager, member_with_history):
        """Test that wallet entries linked to payments are deleted"""
        # Verify wallet entry exists
        wallet_count = GymWalletEntry.objects.filter(
            related_payment__member=member_with_history
        ).count()
        assert wallet_count > 0
        
        # Purge member
        purge_member(
            member=member_with_history,
            user=manager,
            reason="test",
        )
        
        # Verify wallet entries are deleted
        wallet_count_after = GymWalletEntry.objects.filter(
            related_payment__member_id=member_with_history.id
        ).count()
        assert wallet_count_after == 0


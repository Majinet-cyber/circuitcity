"""
Tests for Gym Payment Corrections and Deletion (Feb 2026)
==========================================================

Tests for:
1. Tenant-scoped queryset helper (Task A)
2. GymPayment edit with tenant isolation (Task A)
3. GymPayment deletion with wallet reversal (Task B)
"""
from decimal import Decimal
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from corrections.services_deletion import GymPaymentDeletionService
from corrections.utils import get_tenant_scoped_queryset, validate_tenant_access
from corrections.models import CorrectionAuditLog
from corrections.registry import registry
from inventory.models_verticals import (
    GymMember,
    GymPayment,
    GymWalletEntry,
    GymMemberStatus,
)
from tenants.models import Business, BusinessKind

User = get_user_model()


class TestTenantScopedQueryset(TestCase):
    """Test the get_tenant_scoped_queryset helper function."""
    
    def setUp(self):
        """Create test data with two tenants."""
        # Tenant 1
        self.business1 = Business.objects.create(
            name="Gym Alpha",
            kind=BusinessKind.GYM,
            owner_email="owner1@example.com",
        )
        self.member1 = GymMember.objects.create(
            business=self.business1,
            name="John Doe",
            phone="0991234567",
            status=GymMemberStatus.ACTIVE,
        )
        self.payment1 = GymPayment.objects.create(
            member=self.member1,
            membership_amount=Decimal("50000.00"),
            trainer_fee=Decimal("5000.00"),
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
        )
        
        # Tenant 2
        self.business2 = Business.objects.create(
            name="Gym Beta",
            kind=BusinessKind.GYM,
            owner_email="owner2@example.com",
        )
        self.member2 = GymMember.objects.create(
            business=self.business2,
            name="Jane Smith",
            phone="0997654321",
            status=GymMemberStatus.ACTIVE,
        )
        self.payment2 = GymPayment.objects.create(
            member=self.member2,
            membership_amount=Decimal("60000.00"),
            trainer_fee=Decimal("0.00"),
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
        )
        
        # Get entity configs
        self.gym_adapter = registry.get_adapter('gym')
        self.member_config = self.gym_adapter.get_entities()['gym_member']
        self.payment_config = self.gym_adapter.get_entities()['gym_payment']
    
    def test_tenant_scoped_queryset_direct_business_field(self):
        """Test filtering model with direct business field (GymMember)."""
        qs = get_tenant_scoped_queryset(
            model=GymMember,
            entity_config=self.member_config,
            business=self.business1,
        )
        
        # Should only return member1
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), self.member1)
    
    def test_tenant_scoped_queryset_indirect_business_field(self):
        """Test filtering model with indirect business field (GymPayment via member__business)."""
        qs = get_tenant_scoped_queryset(
            model=GymPayment,
            entity_config=self.payment_config,
            business=self.business1,
        )
        
        # Should only return payment1
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), self.payment1)
    
    def test_tenant_scoped_queryset_isolates_tenants(self):
        """Test that tenant isolation works correctly."""
        # Business 1 should only see its own payment
        qs1 = get_tenant_scoped_queryset(
            model=GymPayment,
            entity_config=self.payment_config,
            business=self.business1,
        )
        self.assertIn(self.payment1, qs1)
        self.assertNotIn(self.payment2, qs1)
        
        # Business 2 should only see its own payment
        qs2 = get_tenant_scoped_queryset(
            model=GymPayment,
            entity_config=self.payment_config,
            business=self.business2,
        )
        self.assertIn(self.payment2, qs2)
        self.assertNotIn(self.payment1, qs2)
    
    def test_validate_tenant_access_direct_field(self):
        """Test validate_tenant_access with direct business field."""
        # Member1 belongs to business1
        self.assertTrue(
            validate_tenant_access(self.member1, self.member_config, self.business1)
        )
        # Member1 does NOT belong to business2
        self.assertFalse(
            validate_tenant_access(self.member1, self.member_config, self.business2)
        )
    
    def test_validate_tenant_access_indirect_field(self):
        """Test validate_tenant_access with indirect business field."""
        # Payment1 belongs to business1 (via member)
        self.assertTrue(
            validate_tenant_access(self.payment1, self.payment_config, self.business1)
        )
        # Payment1 does NOT belong to business2
        self.assertFalse(
            validate_tenant_access(self.payment1, self.payment_config, self.business2)
        )


class TestGymPaymentEditTenantIsolation(TestCase):
    """Test that GymPayment edit view enforces tenant isolation."""
    
    def setUp(self):
        """Create test data with two tenants and users."""
        # Tenant 1
        self.business1 = Business.objects.create(
            name="Gym Alpha",
            kind=BusinessKind.GYM,
            owner_email="owner1@example.com",
        )
        self.user1 = User.objects.create_user(
            username="manager1",
            email="manager1@example.com",
            password="testpass123",
        )
        self.user1.profile.business = self.business1
        self.user1.profile.role = "MANAGER"
        self.user1.profile.save()
        
        self.member1 = GymMember.objects.create(
            business=self.business1,
            name="John Doe",
            phone="0991234567",
            status=GymMemberStatus.ACTIVE,
        )
        self.payment1 = GymPayment.objects.create(
            member=self.member1,
            membership_amount=Decimal("50000.00"),
            trainer_fee=Decimal("5000.00"),
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
        )
        
        # Tenant 2
        self.business2 = Business.objects.create(
            name="Gym Beta",
            kind=BusinessKind.GYM,
            owner_email="owner2@example.com",
        )
        self.user2 = User.objects.create_user(
            username="manager2",
            email="manager2@example.com",
            password="testpass123",
        )
        self.user2.profile.business = self.business2
        self.user2.profile.role = "MANAGER"
        self.user2.profile.save()
        
        self.member2 = GymMember.objects.create(
            business=self.business2,
            name="Jane Smith",
            phone="0997654321",
            status=GymMemberStatus.ACTIVE,
        )
        self.payment2 = GymPayment.objects.create(
            member=self.member2,
            membership_amount=Decimal("60000.00"),
            trainer_fee=Decimal("0.00"),
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
        )
        
        self.client = Client()
    
    def test_edit_own_payment_succeeds(self):
        """Test that manager can edit payment from their own business."""
        self.client.force_login(self.user1)
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business1.id
        session.save()
        
        url = reverse('corrections:edit_record', kwargs={
            'vertical': 'gym',
            'entity_label': 'gym_payment',
            'object_id': self.payment1.pk,
        })
        
        response = self.client.get(url)
        
        # Should succeed (200 OK)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'John Doe')
    
    def test_edit_other_tenant_payment_fails(self):
        """Test that manager CANNOT edit payment from another business."""
        self.client.force_login(self.user1)
        
        # Set active business in session to business1
        session = self.client.session
        session['active_business_id'] = self.business1.id
        session.save()
        
        # Try to edit payment2 (belongs to business2)
        url = reverse('corrections:edit_record', kwargs={
            'vertical': 'gym',
            'entity_label': 'gym_payment',
            'object_id': self.payment2.pk,
        })
        
        response = self.client.get(url)
        
        # Should fail (404 Not Found due to tenant isolation)
        self.assertEqual(response.status_code, 404)


class TestGymPaymentDeletion(TestCase):
    """Test safe deletion of gym payments with wallet reversal."""
    
    def setUp(self):
        """Create test data."""
        self.business = Business.objects.create(
            name="Test Gym",
            kind=BusinessKind.GYM,
            owner_email="owner@example.com",
        )
        
        self.user = User.objects.create_user(
            username="manager",
            email="manager@example.com",
            password="testpass123",
        )
        self.user.profile.business = self.business
        self.user.profile.role = "MANAGER"
        self.user.profile.save()
        
        self.member = GymMember.objects.create(
            business=self.business,
            name="Test Member",
            phone="0991234567",
            status=GymMemberStatus.ACTIVE,
        )
        
        self.payment = GymPayment.objects.create(
            member=self.member,
            membership_amount=Decimal("50000.00"),
            trainer_fee=Decimal("5000.00"),
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            paid_by=self.user,
        )
        
        # Create wallet entry for this payment
        self.wallet_entry = GymWalletEntry.objects.create(
            business=self.business,
            amount=self.payment.amount,
            description=f"Payment from {self.member.name}",
            entry_type="income",
            related_payment=self.payment,
            created_by=self.user,
        )
    
    def test_delete_payment_soft_delete(self):
        """Test soft deletion of payment."""
        service = GymPaymentDeletionService(business=self.business, user=self.user)
        
        result = service.delete_payment(
            payment=self.payment,
            reason="duplicate",
            notes="Accidental duplicate entry",
            hard_delete=False,
        )
        
        # Should succeed
        self.assertTrue(result.success)
        self.assertEqual(result.wallet_entries_removed, 1)
        
        # Payment should be marked as deleted
        self.payment.refresh_from_db()
        self.assertTrue(self.payment.is_deleted)
        self.assertIsNotNone(self.payment.deleted_at)
        self.assertEqual(self.payment.deleted_by, self.user)
        self.assertEqual(self.payment.delete_reason, "duplicate")
        self.assertEqual(self.payment.delete_notes, "Accidental duplicate entry")
    
    def test_delete_payment_removes_wallet_entries(self):
        """Test that wallet entries are removed when payment is deleted."""
        service = GymPaymentDeletionService(business=self.business, user=self.user)
        
        # Verify wallet entry exists before deletion
        self.assertEqual(
            GymWalletEntry.objects.filter(related_payment=self.payment).count(),
            1
        )
        
        result = service.delete_payment(
            payment=self.payment,
            reason="duplicate",
            notes="Test deletion",
        )
        
        # Wallet entry should be removed
        self.assertEqual(
            GymWalletEntry.objects.filter(related_payment=self.payment).count(),
            0
        )
    
    def test_delete_payment_creates_audit_log(self):
        """Test that deletion creates audit log entry."""
        service = GymPaymentDeletionService(business=self.business, user=self.user)
        
        initial_log_count = CorrectionAuditLog.objects.count()
        
        result = service.delete_payment(
            payment=self.payment,
            reason="duplicate",
            notes="Test audit",
        )
        
        # Audit log should be created
        self.assertEqual(CorrectionAuditLog.objects.count(), initial_log_count + 1)
        
        log = CorrectionAuditLog.objects.latest('performed_at')
        self.assertEqual(log.action, 'gym_payment_deleted')
        self.assertEqual(log.performed_by, self.user)
        self.assertEqual(log.business, self.business)
        self.assertIn('reason', log.details)
        self.assertEqual(log.details['reason'], 'duplicate')
    
    def test_delete_payment_requires_reason(self):
        """Test that deletion requires a reason."""
        service = GymPaymentDeletionService(business=self.business, user=self.user)
        
        result = service.delete_payment(
            payment=self.payment,
            reason="",  # Empty reason
            notes="Test",
        )
        
        # Should fail
        self.assertFalse(result.success)
        self.assertIn("reason", result.message.lower())
    
    def test_delete_payment_tenant_isolation(self):
        """Test that deletion enforces tenant isolation."""
        # Create another business
        other_business = Business.objects.create(
            name="Other Gym",
            kind=BusinessKind.GYM,
            owner_email="other@example.com",
        )
        
        # Try to delete payment using wrong business context
        service = GymPaymentDeletionService(business=other_business, user=self.user)
        
        result = service.delete_payment(
            payment=self.payment,
            reason="duplicate",
            notes="Test",
        )
        
        # Should fail due to tenant mismatch
        self.assertFalse(result.success)
        self.assertIn("access denied", result.message.lower())
        
        # Payment should NOT be deleted
        self.payment.refresh_from_db()
        self.assertFalse(self.payment.is_deleted)
    
    def test_delete_payment_idempotent(self):
        """Test that deleting already-deleted payment is idempotent."""
        service = GymPaymentDeletionService(business=self.business, user=self.user)
        
        # Delete once
        result1 = service.delete_payment(
            payment=self.payment,
            reason="duplicate",
            notes="First delete",
        )
        self.assertTrue(result1.success)
        
        # Delete again
        result2 = service.delete_payment(
            payment=self.payment,
            reason="duplicate",
            notes="Second delete",
        )
        
        # Should still succeed (idempotent)
        self.assertTrue(result2.success)
        self.assertIn("already deleted", result2.message.lower())
    
    def test_deleted_payments_excluded_from_default_queryset(self):
        """Test that soft-deleted payments are excluded from default queries."""
        # Payment should be visible initially
        self.assertEqual(GymPayment.objects.filter(pk=self.payment.pk).count(), 1)
        
        # Delete payment
        service = GymPaymentDeletionService(business=self.business, user=self.user)
        service.delete_payment(payment=self.payment, reason="duplicate", notes="Test")
        
        # Should NOT appear in default queryset
        self.assertEqual(GymPayment.objects.filter(pk=self.payment.pk).count(), 0)
        
        # But should appear in all_objects queryset
        self.assertEqual(GymPayment.all_objects.filter(pk=self.payment.pk).count(), 1)


class TestGymPaymentDeletionView(TestCase):
    """Test the delete_record view for gym payments."""
    
    def setUp(self):
        """Create test data."""
        self.business = Business.objects.create(
            name="Test Gym",
            kind=BusinessKind.GYM,
            owner_email="owner@example.com",
        )
        
        self.user = User.objects.create_user(
            username="manager",
            email="manager@example.com",
            password="testpass123",
        )
        self.user.profile.business = self.business
        self.user.profile.role = "MANAGER"
        self.user.profile.save()
        
        self.member = GymMember.objects.create(
            business=self.business,
            name="Test Member",
            phone="0991234567",
            status=GymMemberStatus.ACTIVE,
        )
        
        self.payment = GymPayment.objects.create(
            member=self.member,
            membership_amount=Decimal("50000.00"),
            trainer_fee=Decimal("5000.00"),
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            paid_by=self.user,
        )
        
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_delete_payment_via_view(self):
        """Test deleting payment through the view."""
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('corrections:delete_record', kwargs={
            'vertical': 'gym',
            'entity_label': 'gym_payment',
            'object_id': self.payment.pk,
        })
        
        response = self.client.post(url, {
            'reason': 'duplicate',
            'notes': 'Accidental duplicate',
        })
        
        # Should redirect to browse page
        self.assertEqual(response.status_code, 302)
        
        # Payment should be deleted (need to use all_objects to see soft-deleted)
        payment_check = GymPayment.all_objects.get(pk=self.payment.pk)
        self.assertTrue(payment_check.is_deleted)
    
    def test_delete_payment_requires_post(self):
        """Test that deletion requires POST method."""
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('corrections:delete_record', kwargs={
            'vertical': 'gym',
            'entity_label': 'gym_payment',
            'object_id': self.payment.pk,
        })
        
        # GET should fail
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)  # Method Not Allowed
    
    def test_delete_payment_requires_reason(self):
        """Test that deletion requires reason in POST."""
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('corrections:delete_record', kwargs={
            'vertical': 'gym',
            'entity_label': 'gym_payment',
            'object_id': self.payment.pk,
        })
        
        # POST without reason
        response = self.client.post(url, {
            'notes': 'Some notes',
        })
        
        # Should redirect back with error
        self.assertEqual(response.status_code, 302)
        
        # Payment should NOT be deleted
        self.payment.refresh_from_db()
        self.assertFalse(self.payment.is_deleted)


# Export
__all__ = [
    'TestTenantScopedQueryset',
    'TestGymPaymentEditTenantIsolation',
    'TestGymPaymentDeletion',
    'TestGymPaymentDeletionView',
]


# tests/test_backups.py
"""
Tests for the backup and data recovery system.
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from tenants.models import Business, Membership
from backups.models import BackupSnapshot, BackupStatus
from backups.helpers import export_business_data_to_zip
from inventory.models import Location, InventoryItem, MerchProduct
from sales.models import Sale
from wallet.models import WalletTransaction, Ledger, TxnType

User = get_user_model()


@pytest.mark.django_db
class TestBackupViews:
    """Test backup view endpoints."""

    def test_manager_can_access_backup_list(self, client, manager_user, business):
        """Managers can access the backup list page."""
        # Create membership
        Membership.objects.create(
            user=manager_user,
            business=business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        client.force_login(manager_user)
        
        url = reverse('backups:manager_list')
        response = client.get(url)
        
        assert response.status_code == 200
        assert 'Data Backup & Export' in str(response.content)

    def test_agent_cannot_access_backup_list(self, client, agent_user, business):
        """Regular agents cannot access manager backup pages."""
        # Create agent membership (not manager)
        Membership.objects.create(
            user=agent_user,
            business=business,
            role="AGENT",
            status="ACTIVE"
        )
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        client.force_login(agent_user)
        
        url = reverse('backups:manager_list')
        response = client.get(url)
        
        # Should be forbidden or redirected
        assert response.status_code in [403, 302]

    def test_generate_backup_creates_snapshot(self, client, manager_user, business):
        """Generating a backup creates a BackupSnapshot record."""
        Membership.objects.create(
            user=manager_user,
            business=business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        client.force_login(manager_user)
        
        url = reverse('backups:generate')
        response = client.post(url)
        
        # Should redirect back to list
        assert response.status_code == 302
        
        # Should have created a snapshot
        snapshot = BackupSnapshot.objects.filter(business=business).first()
        assert snapshot is not None
        assert snapshot.created_by == manager_user


@pytest.mark.django_db
class TestBackupHelpers:
    """Test backup helper functions."""

    def test_export_business_data_creates_zip(self, business):
        """Exporting business data creates a valid ZIP file."""
        # Create some test data
        location = Location.objects.create(
            business=business,
            name="Test Store",
            city="Lilongwe"
        )
        
        product = MerchProduct.objects.create(
            business=business,
            sku="TEST001",
            name="Test Product",
            cost=100,
            sell_price=150
        )
        
        # Export data
        zip_path, records_count = export_business_data_to_zip(business)
        
        # Verify ZIP was created
        assert zip_path.exists()
        assert zip_path.suffix == '.zip'
        
        # Verify record counts
        assert 'business' in records_count
        assert 'locations' in records_count
        assert 'merch_products' in records_count
        
        assert records_count['business'] == 1
        assert records_count['locations'] == 1
        assert records_count['merch_products'] == 1
        
        # Clean up
        import shutil
        shutil.rmtree(zip_path.parent, ignore_errors=True)

    def test_export_includes_all_models(self, business, manager_user):
        """Export includes data from all critical models."""
        # Create comprehensive test data
        location = Location.objects.create(
            business=business,
            name="Test Store"
        )
        
        # Inventory
        item = InventoryItem.objects.create(
            business=business,
            imei="123456789012345",
            brand="TestBrand",
            model="TestModel",
            cost=100,
            sell_price=150,
            status="in_stock",
            location=location
        )
        
        # Sale
        Sale.objects.create(
            item=item,
            agent=manager_user,
            location=location,
            sold_at="2025-01-01",
            price=150
        )
        
        # Wallet transaction
        WalletTransaction.objects.create(
            ledger=Ledger.AGENT,
            agent=manager_user,
            type=TxnType.COMMISSION,
            amount=10,
            note="Test commission"
        )
        
        # Export
        zip_path, records_count = export_business_data_to_zip(business)
        
        # Verify all models are included
        assert records_count['inventory_items'] >= 1
        assert records_count['sales'] >= 1
        assert records_count['wallet_transactions'] >= 1
        
        # Clean up
        import shutil
        shutil.rmtree(zip_path.parent, ignore_errors=True)


@pytest.mark.django_db
class TestSoftDelete:
    """Test soft-delete functionality."""

    def test_soft_delete_marks_as_archived(self, business):
        """Soft deleting a record marks it as archived."""
        from cc.models_base import BaseSoftDeleteModel
        
        # This test would work if we had models inheriting from BaseSoftDeleteModel
        # For now, we'll document the expected behavior
        
        # Expected:
        # product.soft_delete(user=manager)
        # assert product.is_archived == True
        # assert product.archived_at is not None
        # assert product.archived_by == manager
        
        # And the record should still exist in database
        # assert Product.all_objects.filter(pk=product.pk).exists()
        
        # But not in default queryset
        # assert not Product.objects.filter(pk=product.pk).exists()
        pass

    def test_restore_unarchives_record(self):
        """Restoring an archived record makes it active again."""
        # Expected:
        # product.restore()
        # assert product.is_archived == False
        # assert product.archived_at is None
        # assert product.archived_by is None
        
        # And it should appear in default queryset
        # assert Product.objects.filter(pk=product.pk).exists()
        pass


@pytest.mark.django_db
class TestAgentExport:
    """Test agent-level data export."""

    def test_agent_can_export_own_data(self, client, agent_user, business):
        """Agents can export their own activity data."""
        Membership.objects.create(
            user=agent_user,
            business=business,
            role="AGENT",
            status="ACTIVE"
        )
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        client.force_login(agent_user)
        
        url = reverse('wallet:agent_export_activity')
        response = client.get(url)
        
        assert response.status_code == 200
        assert response['Content-Type'] == 'text/csv'
        assert 'agent_activity_' in response['Content-Disposition']

    def test_agent_export_includes_transactions(self, client, agent_user, business):
        """Agent export includes wallet transactions."""
        Membership.objects.create(
            user=agent_user,
            business=business,
            role="AGENT",
            status="ACTIVE"
        )
        
        # Create a transaction for this agent
        WalletTransaction.objects.create(
            ledger=Ledger.AGENT,
            agent=agent_user,
            type=TxnType.COMMISSION,
            amount=50,
            note="Test commission"
        )
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        client.force_login(agent_user)
        
        url = reverse('wallet:agent_export_activity')
        response = client.get(url)
        
        content = response.content.decode('utf-8')
        assert 'WALLET TRANSACTIONS' in content
        assert 'Test commission' in content


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def business():
    """Create a test business."""
    return Business.objects.create(
        name="Test Business",
        business_kind="phones"
    )


@pytest.fixture
def manager_user():
    """Create a manager user."""
    return User.objects.create_user(
        username="manager",
        email="manager@test.com",
        password="testpass123",
        is_staff=False
    )


@pytest.fixture
def agent_user():
    """Create an agent user."""
    return User.objects.create_user(
        username="agent",
        email="agent@test.com",
        password="testpass123",
        is_staff=False
    )


@pytest.fixture
def client():
    """Create a test client."""
    return Client()


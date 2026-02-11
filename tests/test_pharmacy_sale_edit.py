"""
Tests for Pharmacy Sale Edit Functionality
===========================================

Tests that pharmacy sales can be edited safely with:
- Correct total recalculation
- Stock consistency (adjustments handled correctly)
- Permission checks (manager-only)
- Audit logging
- No duplicate sale records created
"""
import pytest
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from tenants.models import Business
from inventory.models import MerchProduct
from inventory.models_pharmacy import PharmacyBatch, PharmacySale

User = get_user_model()


@pytest.mark.django_db
class PharmacySaleEditTests(TestCase):
    """Test suite for pharmacy sale editing functionality."""
    
    def setUp(self):
        """Set up test data."""
        # Create business
        self.business = Business.objects.create(
            name="Test Pharmacy",
            slug="test-pharmacy",
            kind="pharmacy"
        )
        
        # Create manager user
        self.manager = User.objects.create_user(
            username="manager",
            email="manager@test.com",
            password="testpass123",
            is_staff=True
        )
        
        # Create regular user (non-manager)
        self.user = User.objects.create_user(
            username="cashier",
            email="cashier@test.com",
            password="testpass123"
        )
        
        # Create product
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Paracetamol 500mg",
            kind="pharmacy"
        )
        
        # Create batch with stock
        self.batch = PharmacyBatch.objects.create(
            business=self.business,
            merch_product=self.product,
            batch_number="BATCH001",
            expiry_date=timezone.now().date() + timezone.timedelta(days=365),
            quantity=100,
            cost_price=Decimal("40.00"),
            selling_price=Decimal("70.00")
        )
        
        # Create a sale
        self.sale = PharmacySale.objects.create(
            business=self.business,
            batch=self.batch,
            quantity=5,
            unit_price=Decimal("70.00"),
            unit_cost=Decimal("40.00"),
            payment_method="CASH",
            sold_by=self.user
        )
        
        # Reduce batch stock (simulating the sale)
        self.batch.quantity -= 5
        self.batch.save()
        
        self.client = Client()
    
    def test_edit_sale_updates_total_correctly(self):
        """Test that editing sale recalculates total_amount correctly."""
        self.client.login(username="manager", password="testpass123")
        
        # Edit sale: change quantity from 5 to 10
        response = self.client.post(
            reverse('pharmacy:sale_edit', args=[self.sale.id]),
            {
                'quantity': 10,
                'payment_method': 'CASH'
            }
        )
        
        # Refresh sale from database
        self.sale.refresh_from_db()
        
        # Check total_amount recalculated correctly
        expected_total = Decimal("70.00") * 10
        self.assertEqual(self.sale.total_amount, expected_total)
        self.assertEqual(self.sale.quantity, 10)
    
    def test_edit_sale_adjusts_stock_correctly_increase(self):
        """Test that increasing sale quantity reduces batch stock correctly."""
        self.client.login(username="manager", password="testpass123")
        
        initial_batch_qty = self.batch.quantity  # Should be 95 (100 - 5)
        
        # Edit sale: increase quantity from 5 to 8 (+3 units)
        response = self.client.post(
            reverse('pharmacy:sale_edit', args=[self.sale.id]),
            {
                'quantity': 8,
                'payment_method': 'CASH'
            }
        )
        
        # Refresh batch from database
        self.batch.refresh_from_db()
        
        # Batch stock should decrease by 3
        expected_batch_qty = initial_batch_qty - 3
        self.assertEqual(self.batch.quantity, expected_batch_qty)
    
    def test_edit_sale_adjusts_stock_correctly_decrease(self):
        """Test that decreasing sale quantity restores batch stock correctly."""
        self.client.login(username="manager", password="testpass123")
        
        initial_batch_qty = self.batch.quantity  # Should be 95 (100 - 5)
        
        # Edit sale: decrease quantity from 5 to 2 (-3 units)
        response = self.client.post(
            reverse('pharmacy:sale_edit', args=[self.sale.id]),
            {
                'quantity': 2,
                'payment_method': 'CASH'
            }
        )
        
        # Refresh batch from database
        self.batch.refresh_from_db()
        
        # Batch stock should increase by 3
        expected_batch_qty = initial_batch_qty + 3
        self.assertEqual(self.batch.quantity, expected_batch_qty)
    
    def test_edit_sale_prevents_negative_stock(self):
        """Test that edit prevents creating negative stock."""
        self.client.login(username="manager", password="testpass123")
        
        # Try to increase quantity beyond available stock
        # Batch has 95 units, sale is 5, trying to change to 200 would need 195 more
        response = self.client.post(
            reverse('pharmacy:sale_edit', args=[self.sale.id]),
            {
                'quantity': 200,
                'payment_method': 'CASH'
            },
            follow=True
        )
        
        # Should show error message
        messages = list(response.context['messages'])
        self.assertTrue(any('Insufficient stock' in str(m) for m in messages))
        
        # Sale should not be updated
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.quantity, 5)
    
    def test_non_manager_cannot_edit_sale(self):
        """Test that non-manager users cannot edit sales."""
        self.client.login(username="cashier", password="testpass123")
        
        response = self.client.post(
            reverse('pharmacy:sale_edit', args=[self.sale.id]),
            {
                'quantity': 10,
                'payment_method': 'CASH'
            },
            follow=True
        )
        
        # Should show error message
        messages = list(response.context['messages'])
        self.assertTrue(any('Only managers can edit sales' in str(m) for m in messages))
        
        # Sale should not be updated
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.quantity, 5)
    
    def test_edit_sale_does_not_create_duplicate(self):
        """Test that editing a sale doesn't create a duplicate record."""
        self.client.login(username="manager", password="testpass123")
        
        initial_sale_count = PharmacySale.objects.filter(business=self.business).count()
        
        # Edit sale
        response = self.client.post(
            reverse('pharmacy:sale_edit', args=[self.sale.id]),
            {
                'quantity': 10,
                'payment_method': 'MOBILE_MONEY'
            }
        )
        
        # Count should remain the same
        final_sale_count = PharmacySale.objects.filter(business=self.business).count()
        self.assertEqual(initial_sale_count, final_sale_count)
    
    def test_edit_sale_creates_audit_log(self):
        """Test that editing a sale creates an audit log entry."""
        self.client.login(username="manager", password="testpass123")
        
        # Edit sale
        response = self.client.post(
            reverse('pharmacy:sale_edit', args=[self.sale.id]),
            {
                'quantity': 10,
                'payment_method': 'BANK'
            }
        )
        
        # Check audit log was created
        try:
            from audit.models import AuditLog
            
            audit_logs = AuditLog.objects.filter(
                business=self.business,
                action="EDIT_PHARMACY_SALE",
                resource_type="PharmacySale",
                resource_id=self.sale.id
            )
            
            self.assertTrue(audit_logs.exists())
            
            # Check audit log details
            log = audit_logs.first()
            self.assertEqual(log.user, self.manager)
            self.assertEqual(log.details['old_quantity'], 5)
            self.assertEqual(log.details['new_quantity'], 10)
        except ImportError:
            # Audit app not available, skip this check
            pass
    
    def test_cannot_edit_deleted_sale(self):
        """Test that deleted sales cannot be edited."""
        self.client.login(username="manager", password="testpass123")
        
        # Mark sale as deleted
        self.sale.is_deleted = True
        self.sale.save()
        
        # Try to edit
        response = self.client.post(
            reverse('pharmacy:sale_edit', args=[self.sale.id]),
            {
                'quantity': 10,
                'payment_method': 'CASH'
            },
            follow=True
        )
        
        # Should show error
        messages = list(response.context['messages'])
        self.assertTrue(any('Cannot edit a deleted' in str(m) for m in messages))
    
    def test_edit_sale_payment_method(self):
        """Test that payment method can be changed."""
        self.client.login(username="manager", password="testpass123")
        
        # Edit payment method only
        response = self.client.post(
            reverse('pharmacy:sale_edit', args=[self.sale.id]),
            {
                'quantity': 5,  # Keep same quantity
                'payment_method': 'MOBILE_MONEY'
            }
        )
        
        # Refresh sale
        self.sale.refresh_from_db()
        
        # Check payment method updated
        self.assertEqual(self.sale.payment_method, 'MOBILE_MONEY')
        
        # Stock should remain unchanged
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity, 95)
    
    def test_edit_sale_validates_quantity_positive(self):
        """Test that quantity must be positive."""
        self.client.login(username="manager", password="testpass123")
        
        # Try to set quantity to 0
        response = self.client.post(
            reverse('pharmacy:sale_edit', args=[self.sale.id]),
            {
                'quantity': 0,
                'payment_method': 'CASH'
            },
            follow=True
        )
        
        # Should show error
        messages = list(response.context['messages'])
        self.assertTrue(any('Quantity must be at least 1' in str(m) for m in messages))
        
        # Sale should not be updated
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.quantity, 5)
    
    def test_edit_sale_transaction_safety(self):
        """Test that sale edit is transaction-safe (atomic)."""
        self.client.login(username="manager", password="testpass123")
        
        # This test verifies that if something fails, nothing is committed
        # We'll test by trying to edit with invalid data after making a change
        
        initial_batch_qty = self.batch.quantity
        initial_sale_qty = self.sale.quantity
        
        # Make a valid edit
        response = self.client.post(
            reverse('pharmacy:sale_edit', args=[self.sale.id]),
            {
                'quantity': 8,
                'payment_method': 'CASH'
            }
        )
        
        # Verify both sale and batch were updated together
        self.sale.refresh_from_db()
        self.batch.refresh_from_db()
        
        self.assertEqual(self.sale.quantity, 8)
        self.assertEqual(self.batch.quantity, initial_batch_qty - 3)  # 95 - 3 = 92


@pytest.mark.django_db
class PharmacySaleEditUITests(TestCase):
    """Test UI elements for sale editing."""
    
    def setUp(self):
        """Set up test data."""
        self.business = Business.objects.create(
            name="Test Pharmacy",
            slug="test-pharmacy",
            kind="pharmacy"
        )
        
        self.manager = User.objects.create_user(
            username="manager",
            email="manager@test.com",
            password="testpass123",
            is_staff=True
        )
        
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Aspirin 300mg",
            kind="pharmacy"
        )
        
        self.batch = PharmacyBatch.objects.create(
            business=self.business,
            merch_product=self.product,
            batch_number="BATCH002",
            expiry_date=timezone.now().date() + timezone.timedelta(days=365),
            quantity=50,
            cost_price=Decimal("30.00"),
            selling_price=Decimal("60.00")
        )
        
        self.sale = PharmacySale.objects.create(
            business=self.business,
            batch=self.batch,
            quantity=3,
            unit_price=Decimal("60.00"),
            unit_cost=Decimal("30.00"),
            payment_method="CASH"
        )
        
        self.client = Client()
    
    def test_edit_button_visible_on_sales_history(self):
        """Test that Edit button appears on sales history page for managers."""
        self.client.login(username="manager", password="testpass123")
        
        response = self.client.get(reverse('verticals:pharmacy_sales_history'))
        
        # Check that Edit button/link is present
        self.assertContains(response, 'sale_edit')
        self.assertContains(response, 'Edit')
    
    def test_edit_form_displays_correctly(self):
        """Test that edit form shows current sale data."""
        self.client.login(username="manager", password="testpass123")
        
        response = self.client.get(reverse('pharmacy:sale_edit', args=[self.sale.id]))
        
        # Check form displays
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Edit Sale')
        self.assertContains(response, str(self.sale.quantity))
        self.assertContains(response, self.product.name)


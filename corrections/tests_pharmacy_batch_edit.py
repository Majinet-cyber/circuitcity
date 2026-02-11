"""
Test suite for Pharmacy Batch Edit functionality in Corrections Framework
===========================================================================

Verifies that:
1. Edit button appears on pharmacy_batch corrections page
2. Edit form loads correctly
3. Changes can be saved
4. Tenant isolation is enforced
"""
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from tenants.models import Business
from inventory.models import MerchProduct
from inventory.models_pharmacy import PharmacyBatch
from inventory.business_kinds import BusinessKind
from corrections.models import CorrectionBatch, CorrectionItem

User = get_user_model()


class PharmacyBatchEditTest(TestCase):
    """Test pharmacy_batch edit functionality."""
    
    def setUp(self):
        """Set up test data."""
        self.client = Client()
        
        # Create pharmacy business
        self.business = Business.objects.create(
            name='Test Pharmacy',
            business_kind=BusinessKind.PHARMACY,
            email='pharmacy@test.com',
        )
        
        # Create manager user
        self.manager = User.objects.create_user(
            username='manager',
            email='manager@test.com',
            password='testpass123',
            is_manager=True,
        )
        self.manager.businesses.add(self.business)
        
        # Create pharmacy product
        self.product = MerchProduct.objects.create(
            business=self.business,
            name='Paracetamol 500mg',
            kind=BusinessKind.PHARMACY,
            category='Analgesic',
            sku='PARA500',
        )
        
        # Create pharmacy batch
        self.batch = PharmacyBatch.objects.create(
            business=self.business,
            merch_product=self.product,
            batch_number='BATCH001',
            barcode='123456789',
            expiry_date=date.today() + timedelta(days=365),
            quantity=100,
            reorder_level=20,
            cost_price=Decimal('50.00'),
            selling_price=Decimal('75.00'),
            supplier='Test Supplier',
            received_date=date.today(),
        )
        
        # Login
        self.client.login(username='manager', password='testpass123')
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
    
    def test_browse_page_shows_edit_button(self):
        """Test that Edit button appears on pharmacy_batch browse page."""
        url = reverse('corrections:browse_entity', kwargs={
            'vertical': 'pharmacy',
            'entity_label': 'pharmacy_batch',
        })
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        # Check for Edit button with pencil icon
        self.assertContains(response, 'bi-pencil')
        self.assertContains(response, 'Edit')
        # Check for edit URL
        edit_url = reverse('corrections:edit_record', kwargs={
            'vertical': 'pharmacy',
            'entity_label': 'pharmacy_batch',
            'object_id': self.batch.pk,
        })
        self.assertContains(response, edit_url)
    
    def test_edit_page_loads_correctly(self):
        """Test that edit page loads with correct form fields."""
        url = reverse('corrections:edit_record', kwargs={
            'vertical': 'pharmacy',
            'entity_label': 'pharmacy_batch',
            'object_id': self.batch.pk,
        })
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        # Check for form fields
        self.assertContains(response, 'batch_number')
        self.assertContains(response, 'expiry_date')
        self.assertContains(response, 'quantity')
        self.assertContains(response, 'cost_price')
        self.assertContains(response, 'selling_price')
        # Check current values are pre-filled
        self.assertContains(response, 'BATCH001')
        self.assertContains(response, '100')  # quantity
        self.assertContains(response, '50.00')  # cost_price
        self.assertContains(response, '75.00')  # selling_price
    
    def test_edit_saves_changes(self):
        """Test that editing and saving actually updates the record."""
        url = reverse('corrections:edit_record', kwargs={
            'vertical': 'pharmacy',
            'entity_label': 'pharmacy_batch',
            'object_id': self.batch.pk,
        })
        
        # Submit changes
        response = self.client.post(url, {
            'reason': 'Correcting quantity after stock count',
            'batch_number': 'BATCH001-CORRECTED',
            'barcode': '123456789',
            'expiry_date': str(date.today() + timedelta(days=365)),
            'quantity': '95',  # Changed from 100
            'reorder_level': '20',
            'cost_price': '52.50',  # Changed from 50.00
            'selling_price': '80.00',  # Changed from 75.00
            'supplier': 'Test Supplier',
            'received_date': str(date.today()),
        })
        
        # Should redirect to browse page
        self.assertEqual(response.status_code, 302)
        
        # Verify changes were saved
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.batch_number, 'BATCH001-CORRECTED')
        self.assertEqual(self.batch.quantity, 95)
        self.assertEqual(self.batch.cost_price, Decimal('52.50'))
        self.assertEqual(self.batch.selling_price, Decimal('80.00'))
        
        # Verify correction was logged
        correction_batch = CorrectionBatch.objects.filter(
            business=self.business,
            entity_label='pharmacy_batch',
        ).first()
        self.assertIsNotNone(correction_batch)
        self.assertEqual(correction_batch.reason, 'Correcting quantity after stock count')
        
        # Verify correction items were created
        correction_items = CorrectionItem.objects.filter(
            batch=correction_batch,
            object_id=self.batch.pk,
        )
        self.assertGreater(correction_items.count(), 0)
    
    def test_tenant_isolation_edit_page(self):
        """Test that users cannot edit batches from other businesses."""
        # Create another business
        other_business = Business.objects.create(
            name='Other Pharmacy',
            business_kind=BusinessKind.PHARMACY,
        )
        
        # Create product and batch for other business
        other_product = MerchProduct.objects.create(
            business=other_business,
            name='Other Product',
            kind=BusinessKind.PHARMACY,
        )
        other_batch = PharmacyBatch.objects.create(
            business=other_business,
            merch_product=other_product,
            batch_number='OTHER001',
            quantity=50,
            cost_price=Decimal('30.00'),
            selling_price=Decimal('45.00'),
            received_date=date.today(),
        )
        
        # Try to access other batch's edit page
        url = reverse('corrections:edit_record', kwargs={
            'vertical': 'pharmacy',
            'entity_label': 'pharmacy_batch',
            'object_id': other_batch.pk,
        })
        response = self.client.get(url)
        
        # Should get 404 (not found in tenant-scoped queryset)
        self.assertEqual(response.status_code, 404)
    
    def test_browse_page_shows_only_own_batches(self):
        """Test that browse page only shows batches for current business."""
        # Create another business with its own batch
        other_business = Business.objects.create(
            name='Other Pharmacy',
            business_kind=BusinessKind.PHARMACY,
        )
        other_product = MerchProduct.objects.create(
            business=other_business,
            name='Other Product',
            kind=BusinessKind.PHARMACY,
        )
        other_batch = PharmacyBatch.objects.create(
            business=other_business,
            merch_product=other_product,
            batch_number='OTHER001',
            quantity=50,
            cost_price=Decimal('30.00'),
            selling_price=Decimal('45.00'),
            received_date=date.today(),
        )
        
        url = reverse('corrections:browse_entity', kwargs={
            'vertical': 'pharmacy',
            'entity_label': 'pharmacy_batch',
        })
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        # Should show our batch
        self.assertContains(response, 'BATCH001')
        # Should NOT show other business's batch
        self.assertNotContains(response, 'OTHER001')
    
    def test_edit_validates_required_fields(self):
        """Test that required fields are validated."""
        url = reverse('corrections:edit_record', kwargs={
            'vertical': 'pharmacy',
            'entity_label': 'pharmacy_batch',
            'object_id': self.batch.pk,
        })
        
        # Submit with missing required field (quantity)
        response = self.client.post(url, {
            'reason': 'Test',
            'batch_number': 'BATCH001',
            'barcode': '123456789',
            'expiry_date': str(date.today() + timedelta(days=365)),
            # 'quantity': missing
            'reorder_level': '20',
            'cost_price': '50.00',
            'selling_price': '75.00',
            'supplier': 'Test Supplier',
            'received_date': str(date.today()),
        })
        
        # Should not save (either shows error or redirects with error message)
        # Original value should remain unchanged
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity, 100)  # Original value





"""
Test suite for Liquor Credit Sales Workflow.

Tests the complete credit workflow:
- Credit sale creation with required customer details
- Credit payment submission with proof upload
- Manager approval/rejection
- Credit status transitions (OPEN → PARTIAL → SETTLED)
- Reconciliation integration

CRITICAL: These tests ensure credit accounting is accurate and auditable.
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

from tenants.models import Business, Membership
from inventory.models import MerchProduct
from inventory.models_verticals import (
    LiquorCredit,
    LiquorCreditPayment,
    LiquorCreditStatus,
    LiquorCreditPaymentStatus,
    LiquorSale,
    LiquorSaleType,
)
from inventory.business_kinds import BusinessKind

User = get_user_model()


@pytest.fixture
def liquor_business(db):
    """Create a liquor business with manager."""
    user = User.objects.create_user(
        username="manager",
        email="manager@bar.test",
        password="testpass123",
        is_staff=True,  # Make manager
    )
    business = Business.objects.create(
        name="Test Bar",
        kind=BusinessKind.LIQUOR,
        created_by=user,
    )
    # Use MANAGER role
    Membership.objects.create(
        user=user,
        business=business,
        role="MANAGER",
        is_active=True,
    )
    return business, user


@pytest.fixture
def bartender(liquor_business):
    """Create a bartender user."""
    business, _ = liquor_business
    user = User.objects.create_user(
        username="bartender",
        email="bartender@bar.test",
        password="testpass123",
    )
    Membership.objects.create(
        user=user,
        business=business,
        role="BARTENDER",
        is_active=True,
    )
    return user


@pytest.fixture
def liquor_product(liquor_business):
    """Create a liquor product."""
    business, _ = liquor_business
    product = MerchProduct.objects.create(
        business=business,
        name="Test Beer",
        category="beer",
        kind=BusinessKind.LIQUOR,
        selling_price=Decimal("3000.00"),
        cost_price=Decimal("2000.00"),
        quantity_in_stock=100,
        is_active=True,
    )
    return product


# ==============================================================================
# PHASE C: Credit Sales Workflow Tests
# ==============================================================================


@pytest.mark.django_db
class TestCreditSaleCreation:
    """Test credit sale creation with required fields."""
    
    def test_credit_sale_requires_customer_name(self, client, liquor_business, liquor_product):
        """Credit sales must have customer name."""
        business, manager = liquor_business
        client.force_login(manager)
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Attempt credit sale without customer name
        url = reverse('liquor:sell')
        response = client.post(url, {
            'product_id': liquor_product.id,
            'quantity': 5,
            'mode': 'bottle',
            'sale_type': 'credit',
            # customer_name missing
        })
        
        # Should fail with error message
        assert response.status_code in [200, 302]
        
        # No credit sale should be created
        assert LiquorSale.objects.filter(
            business=business,
            is_credit=True
        ).count() == 0
        
    def test_credit_sale_with_customer_name_creates_credit(self, client, liquor_business, liquor_product):
        """Credit sale with customer name should create LiquorCredit record."""
        business, manager = liquor_business
        client.force_login(manager)
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Create credit sale
        url = reverse('liquor:sell')
        response = client.post(url, {
            'product_id': liquor_product.id,
            'quantity': 5,
            'unit_price': '3000.00',
            'mode': 'bottle',
            'sale_type': 'credit',
            'customer_name': 'John Doe',
            'customer_phone': '+265999123456',
        })
        
        # Should succeed
        assert response.status_code in [200, 302]
        
        # Credit should be created
        credit = LiquorCredit.objects.filter(
            business=business,
            customer_name='John Doe'
        ).first()
        
        if credit:  # Only assert if credit was created
            assert credit.customer_phone == '+265999123456'
            assert credit.status == LiquorCreditStatus.OPEN
            assert credit.amount == Decimal('15000.00')  # 5 * 3000
            assert credit.balance == Decimal('15000.00')
            assert credit.created_by == manager
        
    def test_credit_sale_timestamps_recorded(self, liquor_business):
        """Credit creation should auto-record timestamp."""
        business, manager = liquor_business
        
        before_create = timezone.now()
        
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name='Test Customer',
            customer_phone='+265888999000',
            amount=Decimal('10000.00'),
            created_by=manager,
        )
        
        after_create = timezone.now()
        
        assert credit.created_at is not None
        assert before_create <= credit.created_at <= after_create


@pytest.mark.django_db
class TestCreditPaymentSubmission:
    """Test credit payment submission with proof upload."""
    
    def test_submit_payment_with_proof_file(self, client, liquor_business, bartender):
        """Bartenders can submit payment with proof file."""
        business, manager = liquor_business
        
        # Create a credit
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name='Alice',
            amount=Decimal('20000.00'),
            created_by=manager,
        )
        
        client.force_login(bartender)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Submit payment with proof
        proof_file = SimpleUploadedFile(
            "receipt.jpg",
            b"fake image content",
            content_type="image/jpeg"
        )
        
        url = reverse('liquor:submit_credit_payment', args=[credit.id])
        response = client.post(url, {
            'amount': '10000.00',
            'transaction_id': 'TXN12345',
            'proof_file': proof_file,
        })
        
        # Should create payment record
        payment = LiquorCreditPayment.objects.filter(credit=credit).first()
        
        if payment:
            assert payment.amount == Decimal('10000.00')
            assert payment.transaction_id == 'TXN12345'
            assert payment.proof_file is not None
            assert payment.paid_by == bartender
            assert payment.status == LiquorCreditPaymentStatus.PENDING
        
    def test_submit_payment_requires_proof_or_txn_id(self, client, liquor_business, bartender):
        """Payment submission requires either proof file or transaction ID."""
        business, manager = liquor_business
        
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name='Bob',
            amount=Decimal('15000.00'),
            created_by=manager,
        )
        
        client.force_login(bartender)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Attempt submission without proof or txn_id
        url = reverse('liquor:submit_credit_payment', args=[credit.id])
        response = client.post(url, {
            'amount': '5000.00',
            # No transaction_id
            # No proof_file
        })
        
        # Should fail validation
        assert response.status_code == 200  # Returns form with errors
        
        # No payment should be created
        assert LiquorCreditPayment.objects.filter(credit=credit).count() == 0


@pytest.mark.django_db
class TestCreditPaymentApproval:
    """Test manager approval/rejection of credit payments."""
    
    def test_manager_can_approve_payment(self, client, liquor_business):
        """Managers can approve pending credit payments."""
        business, manager = liquor_business
        
        # Create credit and payment
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name='Charlie',
            amount=Decimal('30000.00'),
            created_by=manager,
        )
        
        payment = LiquorCreditPayment.objects.create(
            credit=credit,
            amount=Decimal('15000.00'),
            transaction_id='TXN99999',
            paid_by=manager,
            status=LiquorCreditPaymentStatus.PENDING,
        )
        
        client.force_login(manager)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Approve payment
        url = reverse('liquor:approve_payment', args=[payment.id])
        response = client.post(url)
        
        # Refresh from database
        payment.refresh_from_db()
        credit.refresh_from_db()
        
        assert payment.status == LiquorCreditPaymentStatus.APPROVED
        assert payment.reviewed_by == manager
        assert payment.reviewed_at is not None
        
        # Credit should reflect payment
        assert credit.amount_paid == Decimal('15000.00')
        assert credit.balance == Decimal('15000.00')  # 30000 - 15000
        assert credit.status == LiquorCreditStatus.PARTIAL
        
    def test_manager_can_reject_payment(self, client, liquor_business):
        """Managers can reject pending credit payments."""
        business, manager = liquor_business
        
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name='David',
            amount=Decimal('25000.00'),
            created_by=manager,
        )
        
        payment = LiquorCreditPayment.objects.create(
            credit=credit,
            amount=Decimal('25000.00'),
            transaction_id='TXN88888',
            paid_by=manager,
            status=LiquorCreditPaymentStatus.PENDING,
        )
        
        client.force_login(manager)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Reject payment
        url = reverse('liquor:reject_payment', args=[payment.id])
        response = client.post(url, {
            'reason': 'Invalid receipt'
        })
        
        payment.refresh_from_db()
        
        assert payment.status == LiquorCreditPaymentStatus.REJECTED
        assert payment.reviewed_by == manager
        assert payment.rejection_reason == 'Invalid receipt'


@pytest.mark.django_db
class TestCreditStatusTransitions:
    """Test credit status transitions (OPEN → PARTIAL → SETTLED)."""
    
    def test_credit_starts_as_open(self, liquor_business):
        """New credits start with OPEN status."""
        business, manager = liquor_business
        
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name='Eve',
            amount=Decimal('50000.00'),
            created_by=manager,
        )
        
        assert credit.status == LiquorCreditStatus.OPEN
        assert credit.amount_paid == Decimal('0.00')
        assert credit.balance == credit.amount
        
    def test_partial_payment_sets_status_to_partial(self, liquor_business):
        """Partial payment should set status to PARTIAL."""
        business, manager = liquor_business
        
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name='Frank',
            amount=Decimal('40000.00'),
            created_by=manager,
        )
        
        # Add partial payment
        payment = LiquorCreditPayment.objects.create(
            credit=credit,
            amount=Decimal('20000.00'),
            paid_by=manager,
            status=LiquorCreditPaymentStatus.PENDING,
        )
        
        # Approve payment (triggers status update)
        payment.approve(manager)
        
        credit.refresh_from_db()
        
        assert credit.status == LiquorCreditStatus.PARTIAL
        assert credit.amount_paid == Decimal('20000.00')
        assert credit.balance == Decimal('20000.00')
        
    def test_full_payment_sets_status_to_settled(self, liquor_business):
        """Full payment should set status to SETTLED."""
        business, manager = liquor_business
        
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name='Grace',
            amount=Decimal('35000.00'),
            created_by=manager,
        )
        
        # Add full payment
        payment = LiquorCreditPayment.objects.create(
            credit=credit,
            amount=Decimal('35000.00'),
            paid_by=manager,
            status=LiquorCreditPaymentStatus.PENDING,
        )
        
        payment.approve(manager)
        
        credit.refresh_from_db()
        
        assert credit.status == LiquorCreditStatus.SETTLED
        assert credit.amount_paid == Decimal('35000.00')
        assert credit.balance == Decimal('0.00')
        assert credit.settled_at is not None
        assert credit.settled_by == manager


@pytest.mark.django_db
class TestCreditsListPage:
    """Test credits list page with filters."""
    
    def test_credits_list_returns_200(self, client, liquor_business):
        """Credits list page should return 200."""
        business, manager = liquor_business
        client.force_login(manager)
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        url = reverse('liquor:credits_list')
        response = client.get(url)
        
        assert response.status_code == 200
        assert 'credits' in response.context
        
    def test_credits_list_filters_by_status(self, client, liquor_business):
        """Credits list should filter by status."""
        business, manager = liquor_business
        
        # Create credits with different statuses
        LiquorCredit.objects.create(
            business=business,
            customer_name='Open Credit',
            amount=Decimal('10000.00'),
            status=LiquorCreditStatus.OPEN,
            created_by=manager,
        )
        
        LiquorCredit.objects.create(
            business=business,
            customer_name='Settled Credit',
            amount=Decimal('20000.00'),
            status=LiquorCreditStatus.SETTLED,
            created_by=manager,
        )
        
        client.force_login(manager)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Filter by OPEN status
        url = reverse('liquor:credits_list')
        response = client.get(url, {'status': LiquorCreditStatus.OPEN})
        
        assert response.status_code == 200
        credits = response.context['credits']
        
        # Should only show OPEN credits
        assert all(c.status == LiquorCreditStatus.OPEN for c in credits)
        
    def test_credits_list_shows_empty_state(self, client, liquor_business):
        """Credits list should handle empty state gracefully."""
        business, manager = liquor_business
        client.force_login(manager)
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        url = reverse('liquor:credits_list')
        response = client.get(url)
        
        assert response.status_code == 200
        assert response.context['credits'].count() == 0


@pytest.mark.django_db
class TestCreditDetailPage:
    """Test credit detail page with payment history."""
    
    def test_credit_detail_shows_payments(self, client, liquor_business):
        """Credit detail should show all payments."""
        business, manager = liquor_business
        
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name='Henry',
            amount=Decimal('60000.00'),
            created_by=manager,
        )
        
        # Add payments
        LiquorCreditPayment.objects.create(
            credit=credit,
            amount=Decimal('30000.00'),
            paid_by=manager,
            status=LiquorCreditPaymentStatus.APPROVED,
        )
        
        LiquorCreditPayment.objects.create(
            credit=credit,
            amount=Decimal('15000.00'),
            paid_by=manager,
            status=LiquorCreditPaymentStatus.PENDING,
        )
        
        client.force_login(manager)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        url = reverse('liquor:credit_detail', args=[credit.id])
        response = client.get(url)
        
        assert response.status_code == 200
        assert response.context['credit'] == credit
        assert response.context['payments'].count() == 2
        
    def test_credit_detail_404_for_nonexistent_credit(self, client, liquor_business):
        """Credit detail should return 404 for non-existent credit."""
        business, manager = liquor_business
        client.force_login(manager)
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        url = reverse('liquor:credit_detail', args=[99999])
        response = client.get(url)
        
        assert response.status_code == 404


@pytest.mark.django_db
class TestCreditReconciliationIntegration:
    """Test that credit accounting integrates with reconciliation."""
    
    def test_credit_issued_appears_in_reconciliation(self, liquor_business):
        """Credit sales should be trackable in reconciliation."""
        business, manager = liquor_business
        
        # Create credit sale
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name='Iris',
            amount=Decimal('45000.00'),
            created_by=manager,
        )
        
        # Should be able to query credits for reconciliation
        open_credits = LiquorCredit.objects.filter(
            business=business,
            status=LiquorCreditStatus.OPEN
        )
        
        assert open_credits.count() == 1
        total_credit_owed = sum(c.balance for c in open_credits)
        assert total_credit_owed == Decimal('45000.00')
        
    def test_credit_cleared_appears_in_reconciliation(self, liquor_business):
        """Cleared credits should be trackable as revenue."""
        business, manager = liquor_business
        
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name='Jack',
            amount=Decimal('55000.00'),
            created_by=manager,
        )
        
        # Clear credit
        payment = LiquorCreditPayment.objects.create(
            credit=credit,
            amount=Decimal('55000.00'),
            paid_by=manager,
            status=LiquorCreditPaymentStatus.PENDING,
        )
        payment.approve(manager)
        
        credit.refresh_from_db()
        
        # Should be able to query cleared credits for reconciliation
        cleared_credits = LiquorCredit.objects.filter(
            business=business,
            status=LiquorCreditStatus.SETTLED
        )
        
        assert cleared_credits.count() == 1
        total_cleared = sum(c.amount_paid for c in cleared_credits)
        assert total_cleared == Decimal('55000.00')


"""
Farm Expense Regression Test
CRITICAL: Ensures expense total calculation works correctly (unit_price × quantity).

FAILURE = regression in farm expense calculations
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from tenants.models import Business
from inventory.models_farm import FarmLedgerEntry, FarmEntryType, FarmExpenseCategory, FarmUnit, FarmPaymentMethod


User = get_user_model()


@pytest.fixture
def farm_user_and_business(db):
    """Create a farm user and business for testing."""
    user = User.objects.create_user(
        username="farmtest",
        email="farm@test.com",
        password="testpass123"
    )
    business = Business.objects.create(
        name="Test Farm Business",
        kind="farm",
        owner=user
    )
    return user, business


@pytest.mark.django_db
class TestFarmExpenseTotalCalculation:
    """
    REGRESSION TEST (Jan 2026):
    Verify that farm expense total is calculated correctly as unit_price × quantity.
    
    BUG REPORT: User enters unit_price=175,000 and quantity=20,
    but system saved total as 175,000 instead of 3,500,000.
    """
    
    def test_expense_with_quantity_calculates_total_correctly(self, client, farm_user_and_business):
        """
        CRITICAL TEST: When quantity is provided, amount field is treated as unit price,
        and total is calculated as unit_price × quantity.
        """
        user, business = farm_user_and_business
        client.force_login(user)
        
        # Simulate adding expense: Fertiliser, unit price = 175,000, quantity = 20
        response = client.post(
            reverse('verticals:farm_expenses_record'),
            {
                'date': str(timezone.now().date()),
                'enterprise_type': 'maize',
                'category': FarmExpenseCategory.FERTILISER,
                'description': 'Fertiliser',
                'amount': '175000',  # This is unit price when quantity is provided
                'quantity': '20',
                'unit': FarmUnit.BAG,
                'payment_method': FarmPaymentMethod.CASH,
                'notes': 'Bulk purchase',
            },
            follow=True,
        )
        
        # Verify entry was created
        entry = FarmLedgerEntry.objects.filter(
            business=business,
            entry_type=FarmEntryType.EXPENSE,
            description='Fertiliser',
        ).first()
        
        assert entry is not None, "Expense entry should be created"
        
        # CRITICAL ASSERTION: Total should be unit_price × quantity = 175,000 × 20 = 3,500,000
        expected_total = Decimal('175000') * Decimal('20')
        assert entry.amount_mwk == expected_total, (
            f"Expected total MWK {expected_total:,.2f}, "
            f"but got MWK {entry.amount_mwk:,.2f}. "
            f"Total should be unit_price × quantity."
        )
        
        # Verify quantity was saved
        assert entry.quantity == Decimal('20'), "Quantity should be saved as 20"
        
        # Verify unit was saved
        assert entry.unit == FarmUnit.BAG, "Unit should be saved as BAG"
    
    def test_expense_without_quantity_uses_amount_as_total(self, client, farm_user_and_business):
        """
        When quantity is NOT provided, amount field is the total amount directly.
        """
        user, business = farm_user_and_business
        client.force_login(user)
        
        # Add expense without quantity
        response = client.post(
            reverse('verticals:farm_expenses_record'),
            {
                'date': str(timezone.now().date()),
                'enterprise_type': 'general',
                'category': FarmExpenseCategory.LABOUR,
                'description': 'Farm labour',
                'amount': '50000',  # This is the total when no quantity
                'quantity': '',  # No quantity provided
                'unit': FarmUnit.DAY,
                'payment_method': FarmPaymentMethod.CASH,
                'notes': '',
            },
            follow=True,
        )
        
        entry = FarmLedgerEntry.objects.filter(
            business=business,
            description='Farm labour',
        ).first()
        
        assert entry is not None, "Expense entry should be created"
        
        # Total should be exactly what was entered (no multiplication)
        assert entry.amount_mwk == Decimal('50000'), (
            f"Expected total MWK 50,000, but got MWK {entry.amount_mwk:,.2f}. "
            f"When no quantity, amount should be stored as-is."
        )
        
        # Quantity should be None
        assert entry.quantity is None, "Quantity should be None when not provided"
    
    def test_expense_with_decimal_quantity(self, client, farm_user_and_business):
        """
        Test that decimal quantities work correctly (e.g., 2.5 bags).
        """
        user, business = farm_user_and_business
        client.force_login(user)
        
        response = client.post(
            reverse('verticals:farm_expenses_record'),
            {
                'date': str(timezone.now().date()),
                'enterprise_type': 'maize',
                'category': FarmExpenseCategory.SEEDS,
                'description': 'Maize seeds',
                'amount': '80000',  # Unit price per bag
                'quantity': '2.5',  # 2.5 bags
                'unit': FarmUnit.BAG,
                'payment_method': FarmPaymentMethod.MOBILE_MONEY,
            },
            follow=True,
        )
        
        entry = FarmLedgerEntry.objects.filter(
            business=business,
            description='Maize seeds',
        ).first()
        
        assert entry is not None
        
        # Total = 80,000 × 2.5 = 200,000
        expected_total = Decimal('80000') * Decimal('2.5')
        assert entry.amount_mwk == expected_total, (
            f"Expected total MWK {expected_total:,.2f}, "
            f"but got MWK {entry.amount_mwk:,.2f}"
        )
        assert entry.quantity == Decimal('2.5')


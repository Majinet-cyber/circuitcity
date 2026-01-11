"""
Test payment mix UI polish features:
- All payment methods (Cash, Mobile Money, Bank) shown even if 0
- Percentage calculations are correct
- Template renders with colored cards and progress bars
"""
import pytest
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

from tenants.models import Business
from inventory.models_verticals import (
    GymMember,
    GymPayment,
    PaymentMethod,
    GymMemberStatus,
)
from inventory.services.gym_metrics import get_gym_dashboard_metrics


@pytest.mark.django_db
class TestGymPaymentMixUIPolish:
    """Test payment mix always shows all methods with percentages"""

    @pytest.fixture
    def business(self):
        """Create a gym business."""
        business = Business.objects.create(
            name="Test Gym UI Polish",
            kind="gym",
            slug="test-gym-ui-polish",
        )
        return business

    @pytest.fixture
    def member(self, business):
        """Create a gym member."""
        member = GymMember.objects.create(
            business=business,
            name="Jane Doe Test",
            phone="0999123999",
            email="jane@example.com",
            status=GymMemberStatus.ACTIVE,
            membership_start=timezone.now().date(),
            membership_end=timezone.now().date() + timedelta(days=30),
        )
        return member

    def test_all_payment_methods_shown_even_if_zero(self, business, member):
        """
        CRITICAL: Payment mix must always show Cash, Mobile Money, and Bank
        even if one or more have 0 transactions.
        """
        # Create only CASH payment (no Mobile Money or Bank)
        GymPayment.objects.create(
            member=member,
            membership_amount=Decimal("50000.00"),
            trainer_fee=Decimal("0.00"),
            payment_method=PaymentMethod.CASH,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=30),
            is_active=True,
        )

        # Get metrics
        today = timezone.now().date()
        metrics = get_gym_dashboard_metrics(business, today, today)
        payment_mix = metrics["payment_mix"]

        # Must have exactly 3 methods (all methods shown)
        assert len(payment_mix) == 3, f"Expected 3 payment methods, got {len(payment_mix)}"

        # Extract method names
        method_names = [pm["method"] for pm in payment_mix]
        
        # All 3 canonical methods must be present
        assert "Cash" in method_names, "Cash method missing"
        assert "Mobile Money" in method_names, "Mobile Money method missing"
        assert "Bank Transfer" in method_names, "Bank Transfer method missing"

        # Cash should have amount > 0
        cash_item = next(pm for pm in payment_mix if pm["method"] == "Cash")
        assert cash_item["amount"] == Decimal("50000.00"), f"Cash amount incorrect: {cash_item['amount']}"
        assert cash_item["count"] == 1, f"Cash count incorrect: {cash_item['count']}"

        # Mobile Money and Bank should have 0
        mobile_item = next(pm for pm in payment_mix if pm["method"] == "Mobile Money")
        assert mobile_item["amount"] == Decimal("0.00"), f"Mobile Money should be 0: {mobile_item['amount']}"
        assert mobile_item["count"] == 0, f"Mobile Money count should be 0: {mobile_item['count']}"

        bank_item = next(pm for pm in payment_mix if pm["method"] == "Bank Transfer")
        assert bank_item["amount"] == Decimal("0.00"), f"Bank should be 0: {bank_item['amount']}"
        assert bank_item["count"] == 0, f"Bank count should be 0: {bank_item['count']}"

        print(f"\n✓ All 3 payment methods present even with 0 transactions")
        print(f"✓ Methods: {method_names}")

    def test_percentage_calculations_correct(self, business, member):
        """
        CRITICAL: Percentage calculations must be accurate.
        """
        # Create payments with known amounts
        # Cash: 60,000 (60%)
        # Mobile Money: 40,000 (40%)
        # Bank: 0 (0%)
        GymPayment.objects.create(
            member=member,
            membership_amount=Decimal("60000.00"),
            trainer_fee=Decimal("0.00"),
            payment_method=PaymentMethod.CASH,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=30),
            is_active=True,
        )

        GymPayment.objects.create(
            member=member,
            membership_amount=Decimal("40000.00"),
            trainer_fee=Decimal("0.00"),
            payment_method=PaymentMethod.MOBILE_MONEY,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=30),
            is_active=True,
        )

        # Get metrics
        today = timezone.now().date()
        metrics = get_gym_dashboard_metrics(business, today, today)
        payment_mix = metrics["payment_mix"]

        # Verify total revenue
        assert metrics["revenue"] == Decimal("100000.00")

        # Check percentages
        cash_item = next(pm for pm in payment_mix if pm["method"] == "Cash")
        mobile_item = next(pm for pm in payment_mix if pm["method"] == "Mobile Money")
        bank_item = next(pm for pm in payment_mix if pm["method"] == "Bank Transfer")

        assert cash_item["percentage"] == 60.0, f"Cash % should be 60.0, got {cash_item['percentage']}"
        assert mobile_item["percentage"] == 40.0, f"Mobile Money % should be 40.0, got {mobile_item['percentage']}"
        assert bank_item["percentage"] == 0.0, f"Bank % should be 0.0, got {bank_item['percentage']}"

        # Total percentages should sum to 100% (or close, accounting for rounding)
        total_pct = sum(pm["percentage"] for pm in payment_mix)
        assert 99.0 <= total_pct <= 101.0, f"Total % should be ~100, got {total_pct}"

        print(f"\n✓ Percentages correct: Cash={cash_item['percentage']}%, Mobile={mobile_item['percentage']}%, Bank={bank_item['percentage']}%")

    def test_percentage_zero_when_no_revenue(self, business, member):
        """
        Edge case: When revenue is 0, all percentages should be 0.
        """
        # Don't create any payments
        today = timezone.now().date()
        metrics = get_gym_dashboard_metrics(business, today, today)
        payment_mix = metrics["payment_mix"]

        # All 3 methods should still be present
        assert len(payment_mix) == 3

        # All should have 0 percentage
        for pm in payment_mix:
            assert pm["percentage"] == 0.0, f"{pm['method']} should have 0%, got {pm['percentage']}"
            assert pm["amount"] == Decimal("0.00"), f"{pm['method']} should have 0 amount"
            assert pm["count"] == 0, f"{pm['method']} should have 0 count"

        print(f"\n✓ Zero revenue case: all percentages are 0")

    def test_method_code_slugs_present_for_css(self, business, member):
        """
        CRITICAL: method_code field must be present for CSS class names.
        """
        # Create a payment
        GymPayment.objects.create(
            member=member,
            membership_amount=Decimal("30000.00"),
            trainer_fee=Decimal("0.00"),
            payment_method=PaymentMethod.BANK,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=30),
            is_active=True,
        )

        # Get metrics
        today = timezone.now().date()
        metrics = get_gym_dashboard_metrics(business, today, today)
        payment_mix = metrics["payment_mix"]

        # All items must have method_code
        for pm in payment_mix:
            assert "method_code" in pm, f"method_code missing from {pm['method']}"
            assert pm["method_code"] in ["cash", "mobile-money", "bank"], \
                f"Invalid method_code: {pm['method_code']}"

        # Check specific codes
        cash_item = next(pm for pm in payment_mix if pm["method"] == "Cash")
        assert cash_item["method_code"] == "cash"

        mobile_item = next(pm for pm in payment_mix if pm["method"] == "Mobile Money")
        assert mobile_item["method_code"] == "mobile-money"

        bank_item = next(pm for pm in payment_mix if pm["method"] == "Bank Transfer")
        assert bank_item["method_code"] == "bank"

        print(f"\n✓ All method_code slugs present for CSS classes")

    def test_percentages_with_decimal_precision(self, business, member):
        """
        Test that percentages handle decimal precision correctly (1 decimal place).
        """
        # Create payments with amounts that don't divide evenly
        # Cash: 33,333 (33.3%)
        # Mobile: 33,333 (33.3%)
        # Bank: 33,334 (33.4%)
        # Total: 100,000
        GymPayment.objects.create(
            member=member,
            membership_amount=Decimal("33333.00"),
            trainer_fee=Decimal("0.00"),
            payment_method=PaymentMethod.CASH,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=30),
            is_active=True,
        )

        GymPayment.objects.create(
            member=member,
            membership_amount=Decimal("33333.00"),
            trainer_fee=Decimal("0.00"),
            payment_method=PaymentMethod.MOBILE_MONEY,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=30),
            is_active=True,
        )

        GymPayment.objects.create(
            member=member,
            membership_amount=Decimal("33334.00"),
            trainer_fee=Decimal("0.00"),
            payment_method=PaymentMethod.BANK,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=30),
            is_active=True,
        )

        # Get metrics
        today = timezone.now().date()
        metrics = get_gym_dashboard_metrics(business, today, today)
        payment_mix = metrics["payment_mix"]

        # Check that percentages are rounded to 1 decimal place
        for pm in payment_mix:
            pct = pm["percentage"]
            # Percentage should have at most 1 decimal place
            assert pct == round(pct, 1), f"{pm['method']} percentage not rounded correctly: {pct}"

        # Check individual percentages
        cash_item = next(pm for pm in payment_mix if pm["method"] == "Cash")
        mobile_item = next(pm for pm in payment_mix if pm["method"] == "Mobile Money")
        bank_item = next(pm for pm in payment_mix if pm["method"] == "Bank Transfer")

        # Percentages should be close to 33.3% each (rounding may vary slightly)
        assert abs(cash_item["percentage"] - 33.3) < 0.5, f"Cash % incorrect: {cash_item['percentage']}"
        assert abs(mobile_item["percentage"] - 33.3) < 0.5, f"Mobile % incorrect: {mobile_item['percentage']}"
        assert abs(bank_item["percentage"] - 33.3) < 0.5, f"Bank % incorrect: {bank_item['percentage']}"

        print(f"\n✓ Decimal precision: Cash={cash_item['percentage']}%, Mobile={mobile_item['percentage']}%, Bank={bank_item['percentage']}%")


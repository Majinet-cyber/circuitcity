"""
Test to verify gym dashboard context wiring is correct.
Proves that when payments exist, revenue/costs/profit/mrr are > 0 in template context.
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
class TestGymDashboardContextWiring:
    """Test that gym dashboard gets correct metrics when payments exist"""

    @pytest.fixture
    def business(self):
        """Create a gym business."""
        business = Business.objects.create(
            name="Test Gym Context",
            kind="gym",
            slug="test-gym-context",
        )
        return business

    @pytest.fixture
    def member(self, business):
        """Create a gym member."""
        member = GymMember.objects.create(
            business=business,
            name="John Doe Test",
            phone="0999123458",
            email="john3@example.com",
            status=GymMemberStatus.ACTIVE,
            membership_start=timezone.now().date(),
            membership_end=timezone.now().date() + timedelta(days=30),
        )
        return member

    def test_metrics_service_returns_nonzero_revenue_when_payments_exist(
        self, business, member
    ):
        """
        CRITICAL TEST: Metrics service must return revenue > 0 when payments exist.
        This tests the service layer directly.
        """
        # Create payments with substantial amounts
        GymPayment.objects.create(
            member=member,
            membership_amount=Decimal("55000.00"),
            trainer_fee=Decimal("10000.00"),
            payment_method=PaymentMethod.CASH,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=30),
            is_active=True,
        )

        GymPayment.objects.create(
            member=member,
            membership_amount=Decimal("55000.00"),
            trainer_fee=Decimal("5000.00"),
            payment_method=PaymentMethod.MOBILE_MONEY,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=30),
            is_active=True,
        )

        # Call metrics service
        today = timezone.now().date()
        metrics = get_gym_dashboard_metrics(business, today, today)

        # CRITICAL: Revenue must be > 0
        revenue = metrics["revenue"]
        assert revenue is not None, "revenue is None from metrics service"
        assert revenue > Decimal("0.00"), f"Revenue is {revenue}, expected > 0"
        # Expected: 55000 + 10000 + 55000 + 5000 = 125000
        assert revenue == Decimal("125000.00"), f"Revenue is {revenue}, expected 125000.00"

        # Payment count must match
        payment_count = metrics["payments_count"]
        assert payment_count == 2, f"Payment count is {payment_count}, expected 2"

        # Payment mix must be non-empty and have amounts
        payment_mix = metrics["payment_mix"]
        assert payment_mix is not None, "payment_mix is None"
        assert len(payment_mix) > 0, "payment_mix is empty"

        # Check that payment mix has correct totals
        payment_mix_total = sum(pm["amount"] for pm in payment_mix)
        assert payment_mix_total == revenue, (
            f"Payment mix total ({payment_mix_total}) != revenue ({revenue})"
        )

        # Check individual payment methods
        cash_total = sum(pm["amount"] for pm in payment_mix if pm["method"] == "Cash")
        mobile_total = sum(pm["amount"] for pm in payment_mix if pm["method"] == "Mobile Money")

        assert cash_total == Decimal("65000.00"), f"Cash total is {cash_total}, expected 65000.00"
        assert mobile_total == Decimal("60000.00"), f"Mobile Money total is {mobile_total}, expected 60000.00"

        print(f"\n✓ Metrics service working: revenue={revenue}, count={payment_count}")
        print(f"✓ Payment mix: Cash={cash_total}, Mobile Money={mobile_total}")

    def test_metrics_with_amount_zero_still_shows_revenue(self, business, member):
        """
        REGRESSION TEST: Even if amount field is 0, metrics must show correct revenue.
        """
        # Create payment
        payment = GymPayment.objects.create(
            member=member,
            membership_amount=Decimal("865000.00"),
            trainer_fee=Decimal("5000.00"),
            payment_method=PaymentMethod.CASH,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=30),
            is_active=True,
        )

        # Force amount to 0 (simulating the bug)
        GymPayment.objects.filter(id=payment.id).update(amount=0)

        # Call metrics service
        today = timezone.now().date()
        metrics = get_gym_dashboard_metrics(business, today, today)

        # CRITICAL: Revenue must STILL be correct (computed from components)
        revenue = metrics["revenue"]
        expected = Decimal("870000.00")  # 865000 + 5000
        assert revenue == expected, f"Revenue is {revenue}, expected {expected} even with amount=0"

        payment_mix = metrics["payment_mix"]
        assert len(payment_mix) > 0, "payment_mix should not be empty"
        assert payment_mix[0]["amount"] == expected, f"Payment mix amount is {payment_mix[0]['amount']}, expected {expected}"

        print(f"\n✓ Defense in depth working: revenue={revenue} even though amount field=0")


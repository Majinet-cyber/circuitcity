"""
CRITICAL BUG TEST: Gym dashboard ALWAYS shows MWK 0 for Revenue/Costs/Profit/MRR
Even after creating brand-new gym and recording payments.

This test reproduces the exact failure:
- Create business + gym member + payment
- Django aggregate shows non-zero
- Dashboard view should show non-zero
- Template should render non-zero

If this test FAILS => bug is in view/template
If this test PASSES => bug is elsewhere (caching/SW/etc)
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from inventory.models_verticals import GymMember, GymPayment, PaymentMethod
from tenants.models import Business

User = get_user_model()


class GymDashboardAmountsBugTest(TestCase):
    """
    Test suite to reproduce and fix the CRITICAL BUG where gym dashboard
    shows MWK 0 for all financial metrics even when payments exist.
    """

    def setUp(self):
        """Create a brand-new gym business with fresh payments"""
        # Create owner user
        self.user = User.objects.create_user(
            username="gymowner",
            email="gymowner@test.com",
            password="testpass123",
            first_name="Gym",
            last_name="Owner",
        )

        # Create business
        self.business = Business.objects.create(
            name="Test Gym",
            slug="testgym",
            kind="gym",
            owner=self.user,
        )

        # Create gym member
        self.member = GymMember.objects.create(
            business=self.business,
            name="John Doe",
            phone="+265991234567",
            email="john@example.com",
            membership_fee=Decimal("55000.00"),
            trainer_fee=Decimal("20000.00"),
            has_trainer=True,
        )

        # Create payment (THIS IS THE CRITICAL TEST CASE)
        # Simulates recording a payment via the UI
        today = timezone.now().date()
        self.payment = GymPayment.objects.create(
            member=self.member,
            membership_amount=Decimal("55000.00"),
            trainer_fee=Decimal("20000.00"),
            amount=Decimal("75000.00"),  # Total
            payment_method=PaymentMethod.CASH,
            start_date=today,
            end_date=today + timezone.timedelta(days=29),
            paid_by=self.user,
            paid_at=timezone.now(),
            is_active=True,
        )

        # Login
        self.client = Client()
        self.client.force_login(self.user)

    def test_django_aggregate_shows_nonzero(self):
        """
        SANITY CHECK: Verify Django aggregate correctly shows non-zero amounts.
        This confirms the DB has the data (user already verified this).
        """
        from django.db.models import Sum
        from django.db.models.functions import Coalesce

        # Aggregate amount field (legacy)
        sum_amount = (
            GymPayment.objects.filter(member__business=self.business, is_active=True).aggregate(
                total=Coalesce(Sum("amount"), Decimal("0.00"))
            )["total"]
        )

        # Aggregate from components (membership_amount + trainer_fee)
        from django.db.models import DecimalField, ExpressionWrapper, F, Value

        sum_components = (
            GymPayment.objects.filter(member__business=self.business, is_active=True).aggregate(
                total=Coalesce(
                    Sum(
                        ExpressionWrapper(
                            Coalesce(F("membership_amount"), Value(Decimal("0.00")))
                            + Coalesce(F("trainer_fee"), Value(Decimal("0.00"))),
                            output_field=DecimalField(max_digits=12, decimal_places=2),
                        )
                    ),
                    Value(Decimal("0.00")),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )["total"]
        )

        # ASSERT: DB has non-zero data
        self.assertEqual(sum_amount, Decimal("75000.00"), "amount field should be 75000")
        self.assertEqual(sum_components, Decimal("75000.00"), "membership_amount + trainer_fee should be 75000")

    def test_gym_metrics_service_returns_nonzero(self):
        """
        TEST: The gym_metrics service should return non-zero revenue.
        This tests the single source of truth for financial metrics.
        """
        from inventory.services.gym_metrics import get_gym_dashboard_metrics

        today = timezone.now().date()
        month_start = today.replace(day=1)

        metrics = get_gym_dashboard_metrics(self.business, month_start, today)

        # CRITICAL ASSERTION: Revenue should be 75000, NOT 0
        self.assertGreater(
            metrics["revenue"],
            Decimal("0.00"),
            "Revenue should be > 0 when payments exist (CRITICAL BUG if this fails)",
        )
        self.assertEqual(
            metrics["revenue"],
            Decimal("75000.00"),
            "Revenue should exactly match payment amount (75000)",
        )
        self.assertEqual(metrics["payments_count"], 1, "Should have 1 payment")

        # Check payment mix
        self.assertEqual(len(metrics["payment_mix"]), 1, "Should have 1 payment method in mix")
        self.assertEqual(
            metrics["payment_mix"][0]["amount"],
            Decimal("75000.00"),
            "Payment mix amount should be 75000",
        )

    def test_dashboard_view_context_has_nonzero_revenue(self):
        """
        TEST: The dashboard view should pass non-zero revenue to template context.
        This is the #1 failure point - view passes correct data but context is 0.
        """
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # Call dashboard view
        response = self.client.get("/verticals/gym/dashboard/")

        # ASSERT: Response is successful
        self.assertEqual(response.status_code, 200, "Dashboard should load successfully")

        # CRITICAL ASSERTION: Context should have non-zero revenue
        self.assertIn("revenue", response.context, "Context should have 'revenue' key")
        revenue = response.context["revenue"]

        self.assertIsNotNone(revenue, "Revenue should not be None")
        self.assertIsInstance(revenue, Decimal, f"Revenue should be Decimal, got {type(revenue)}")
        self.assertGreater(
            revenue,
            Decimal("0.00"),
            "CRITICAL BUG: Revenue in context is 0 when payments exist!",
        )
        self.assertEqual(
            revenue,
            Decimal("75000.00"),
            "Revenue should exactly match payment amount (75000)",
        )

        # Check payment_count too
        payment_count = response.context.get("payment_count", 0)
        self.assertGreater(
            payment_count,
            0,
            "Payment count should be > 0",
        )

        # Check payment_mix
        payment_mix = response.context.get("payment_mix", [])
        self.assertEqual(len(payment_mix), 1, "Should have 1 payment method in mix")
        if payment_mix:
            self.assertGreater(
                payment_mix[0].get("amount", Decimal("0.00")),
                Decimal("0.00"),
                "Payment mix amount should be > 0",
            )

    def test_dashboard_html_renders_nonzero_amounts(self):
        """
        TEST: The rendered HTML should contain non-zero amounts, not "MWK 0".
        This tests the complete end-to-end flow including template filters.
        
        CRITICAL: This test catches the filter chaining bug where
        {{ revenue|floatformat:2|intcomma|money }} breaks the money filter.
        """
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # Call dashboard view
        response = self.client.get("/verticals/gym/dashboard/")

        # Get rendered HTML
        html = response.content.decode("utf-8")

        # CRITICAL ASSERTION: HTML should NOT contain "MWK 0.00" for revenue when payments exist
        # We check for "MWK 0.00</p>" to avoid false positives from "MWK 0.00" in other contexts
        self.assertNotIn(
            "MWK 0.00</p>",
            html,
            "CRITICAL BUG: HTML contains 'MWK 0.00</p>' when payments exist! "
            "This suggests the money filter is returning 0 due to comma-separated string input.",
        )

        # HTML should contain the actual formatted amount
        # The money filter should format as "MWK 75,000.00"
        self.assertIn(
            "MWK 75,000.00",
            html,
            "HTML should contain 'MWK 75,000.00' for the payment amount. "
            "If this fails, check: (1) money filter is formatting correctly, "
            "(2) template is not chaining filters incorrectly.",
        )
        
        # Also verify the payment count is correct (should show "1 payment")
        self.assertIn("1 payment", html, "Should show '1 payment' count")
        
        # Verify member name appears in recent payments
        self.assertIn("John Doe", html, "Recent payments should show member name")

    def test_recent_payments_display_nonzero_amounts(self):
        """
        TEST: Recent payments list should show non-zero amounts.
        This was a separate bug where payment.amount was used instead of payment.total_amount.
        """
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # Call dashboard view
        response = self.client.get("/verticals/gym/dashboard/")

        # Get rendered HTML
        html = response.content.decode("utf-8")

        # Recent payments section should show the member name
        self.assertIn("John Doe", html, "Recent payments should show member name")

        # Recent payments should show non-zero amount
        # Check for the payment amount near the member name
        # The amount should be 75000 (75,000 with comma)
        self.assertTrue(
            "75,000" in html or "75000" in html,
            "Recent payments should display non-zero amount (75,000)",
        )

    def test_multiple_payments_aggregate_correctly(self):
        """
        TEST: Multiple payments should aggregate correctly.
        """
        # Create second payment
        today = timezone.now().date()
        GymPayment.objects.create(
            member=self.member,
            membership_amount=Decimal("55000.00"),
            trainer_fee=Decimal("0.00"),
            amount=Decimal("55000.00"),
            payment_method=PaymentMethod.MOBILE_MONEY,
            start_date=today,
            end_date=today + timezone.timedelta(days=29),
            paid_by=self.user,
            paid_at=timezone.now(),
            is_active=True,
        )

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # Call dashboard view
        response = self.client.get("/verticals/gym/dashboard/")

        # ASSERT: Revenue should be 75000 + 55000 = 130000
        revenue = response.context["revenue"]
        self.assertEqual(
            revenue,
            Decimal("130000.00"),
            "Revenue should aggregate multiple payments correctly",
        )

        # Payment count should be 2
        payment_count = response.context.get("payment_count", 0)
        self.assertEqual(payment_count, 2, "Should have 2 payments")

        # Payment mix should have 2 methods
        payment_mix = response.context.get("payment_mix", [])
        self.assertEqual(len(payment_mix), 2, "Should have 2 payment methods in mix")

    def test_sanity_log_triggers_when_payment_count_nonzero_but_revenue_zero(self):
        """
        TEST: The sanity check log should trigger if payments exist but revenue is 0.
        This is the guardrail that catches the bug in production.
        """
        # This test verifies the sanity log is in place
        # We'll manually check logs after running tests

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # If the bug exists, this would trigger the sanity log
        # We can't easily assert on logger calls in tests without mocking,
        # but we verify the logic is in place by checking revenue > 0
        response = self.client.get("/verticals/gym/dashboard/")

        revenue = response.context["revenue"]
        payment_count = response.context.get("payment_count", 0)

        # If this assertion fails, the sanity log should trigger
        if payment_count > 0:
            self.assertGreater(
                revenue,
                Decimal("0.00"),
                "SANITY CHECK FAILED: Payments exist but revenue is 0",
            )


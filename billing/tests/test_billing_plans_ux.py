"""
Tests for billing plans UX bug fix:
Trial users should NOT see "CURRENT" on any plan until they complete payment.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from billing.models import BusinessSubscription, SubscriptionPlan
from tenants.models import Business, Membership

User = get_user_model()


class BillingPlansTrialUXTest(TestCase):
    """Test billing plans page shows correct status for trial vs active subscriptions"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        self.business = Business.objects.create(name="Test Business", slug="test-business")
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER")
        
        # Get or create starter plan (may already exist from migrations)
        self.starter_plan, _ = SubscriptionPlan.objects.get_or_create(
            code="starter",
            defaults={
                "name": "Starter", 
                "amount": Decimal("10000.00"), 
                "currency": "MWK", 
                "interval": "month", 
                "is_active": True
            }
        )

    def test_trial_user_does_not_see_current_badge(self):
        """
        Trial users should NOT see CURRENT badge on any plan (even if plan is assigned).
        This is the critical bug fix.
        """
        # Create trial subscription with Starter plan assigned (this is how trials work)
        sub = BusinessSubscription.start_trial(business=self.business, plan=self.starter_plan, days=30)

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("billing:plans"))

        # Should show trial banner
        self.assertContains(response, "You're on a free trial")
        # Should NOT show CURRENT badge anywhere (critical fix)
        self.assertNotContains(response, "CURRENT")
        # Should NOT show "Current Plan" disabled button
        self.assertNotContains(response, "Current Plan")

    def test_trial_user_sees_choose_plan_buttons(self):
        """Trial users should see 'Choose [Plan]' buttons for all plans"""
        # Create multiple plans (use unique codes to avoid conflicts)
        growth_plan = SubscriptionPlan.objects.create(
            code="growth_ux_test", 
            name="Growth", 
            amount=Decimal("20000.00"), 
            currency="MWK", 
            interval="month", 
            is_active=True
        )
        pro_plan = SubscriptionPlan.objects.create(
            code="pro_ux_test", 
            name="Pro", 
            amount=Decimal("30000.00"), 
            currency="MWK", 
            interval="month", 
            is_active=True
        )

        # Create trial subscription with Starter plan
        sub = BusinessSubscription.start_trial(business=self.business, plan=self.starter_plan, days=30)

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("billing:plans"))

        # Should see "Choose" buttons for all plans (including the one assigned to trial)
        self.assertContains(response, "Choose Starter")
        self.assertContains(response, "Choose Growth")
        self.assertContains(response, "Choose Pro")

    def test_trialing_status_also_works(self):
        """Test that 'trialing' status (not just 'trial') works correctly"""
        # Create subscription with 'trialing' status
        sub = BusinessSubscription.objects.create(
            business=self.business, 
            plan=self.starter_plan, 
            status=BusinessSubscription.Status.TRIALING
        )

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("billing:plans"))

        # Should show trial banner
        self.assertContains(response, "You're on a free trial")
        # Should NOT show CURRENT badge
        self.assertNotContains(response, "CURRENT")

    def test_active_user_sees_current_badge_on_paid_plan(self):
        """Active (paid) users should see CURRENT badge on their plan"""
        # Create active subscription
        sub = BusinessSubscription.objects.create(
            business=self.business, 
            plan=self.starter_plan, 
            status=BusinessSubscription.Status.ACTIVE
        )

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("billing:plans"))

        # Should show CURRENT badge on Starter plan
        self.assertContains(response, "CURRENT")
        # Should show disabled "Current Plan" button
        self.assertContains(response, "Current Plan")
        # Should show active subscription banner
        self.assertContains(response, "You are subscribed")

    def test_active_user_can_upgrade_to_higher_tier(self):
        """Active users should see upgrade option for higher tier plans"""
        # Create growth plan (higher tier, use unique code)
        growth_plan = SubscriptionPlan.objects.create(
            code="growth_upgrade_test", 
            name="Growth", 
            amount=Decimal("20000.00"), 
            currency="MWK", 
            interval="month", 
            is_active=True
        )

        # Create active subscription on Starter
        sub = BusinessSubscription.objects.create(
            business=self.business, 
            plan=self.starter_plan, 
            status=BusinessSubscription.Status.ACTIVE
        )

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("billing:plans"))

        # Should show CURRENT on Starter
        self.assertContains(response, "CURRENT")
        # Should show Upgrade button for Growth
        self.assertContains(response, "Upgrade to Growth")


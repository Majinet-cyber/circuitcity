from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from billing.models import BusinessSubscription, SubscriptionPlan
from tenants.models import Business, Membership

User = get_user_model()


class BillingPlansViewTest(TestCase):
    """Test billing plans page shows correct subscription status"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        self.business = Business.objects.create(name="Test Business", slug="test-business")
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER")
        self.plan = SubscriptionPlan.objects.create(
            code="starter", name="Starter", amount=Decimal("10000.00"), currency="MWK", interval="month", is_active=True
        )

    def test_plans_page_shows_active_subscription_not_trial(self):
        """When subscription is active, plans page should show 'Active' not 'Trial'"""
        # Create active subscription
        sub = BusinessSubscription.objects.create(
            business=self.business, plan=self.plan, status=BusinessSubscription.Status.ACTIVE
        )

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("billing:plans"))

        # Should show active subscription banner
        self.assertContains(response, "You are subscribed")
        self.assertContains(response, "Active")
        # Should NOT show trial banner
        self.assertNotContains(response, "You're on a free trial")
        self.assertNotContains(response, "Trial ends on")

    def test_plans_page_shows_trial_when_trial(self):
        """When subscription is trial, plans page should show 'Trial'"""
        # Create trial subscription
        sub = BusinessSubscription.start_trial(business=self.business, plan=self.plan, days=30)

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("billing:plans"))

        # Should show trial banner
        self.assertContains(response, "You're on a free trial")
        self.assertContains(response, "Trial ends on")
        # Should NOT show active banner
        self.assertNotContains(response, "You are subscribed")

    def test_plans_page_shows_past_due_when_past_due(self):
        """When subscription is past due, plans page should show warning"""
        sub = BusinessSubscription.objects.create(
            business=self.business, plan=self.plan, status=BusinessSubscription.Status.PAST_DUE
        )

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("billing:plans"))

        # Should show past due banner
        self.assertContains(response, "Payment Required")
        self.assertContains(response, "Pay Now")

    def test_plans_page_shows_manage_subscription_for_trial(self):
        """Trial subscriptions should show 'Manage Subscription' button"""
        # Create trial subscription
        sub = BusinessSubscription.start_trial(business=self.business, plan=self.plan, days=30)

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("billing:plans"))

        # Should show trial banner with Manage Subscription button
        self.assertContains(response, "You're on a free trial")
        self.assertContains(response, "Manage Subscription")
        self.assertContains(response, reverse("billing:manage"))

    def test_plans_page_shows_manage_subscription_for_active(self):
        """Active subscriptions should show 'Manage Subscription' button"""
        # Create active subscription
        sub = BusinessSubscription.objects.create(
            business=self.business, plan=self.plan, status=BusinessSubscription.Status.ACTIVE
        )

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("billing:plans"))

        # Should show active banner with Manage Subscription button
        self.assertContains(response, "You are subscribed")
        self.assertContains(response, "Manage Subscription")
        self.assertContains(response, reverse("billing:manage"))

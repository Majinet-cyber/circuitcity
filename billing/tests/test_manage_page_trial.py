"""
Tests for /billing/manage page - trial vs active subscription display
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from billing.models import BusinessSubscription, Invoice, SubscriptionPlan
from tenants.models import Business, Membership

User = get_user_model()


class ManagePageTrialTest(TestCase):
    """Test /billing/manage page correctly shows trial vs active subscription state"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        self.business = Business.objects.create(name="Test Business", slug="test-business", status="ACTIVE")
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER", status="ACTIVE")
        
        # Get or create starter plan
        self.starter_plan, _ = SubscriptionPlan.objects.get_or_create(
            code="starter",
            defaults={
                "name": "Starter", 
                "amount": Decimal("20000.00"), 
                "currency": "MWK", 
                "interval": "month", 
                "is_active": True
            }
        )

    def test_trial_user_does_not_see_paid_plan_details(self):
        """Trial users should NOT see 'Current Plan: Starter MWK 20,000/month'"""
        # Create trial subscription
        sub = BusinessSubscription.start_trial(business=self.business, plan=self.starter_plan, days=30)

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("billing:manage"))

        # Should show trial info
        self.assertContains(response, "Free Trial")
        # Should NOT show "Current Plan" section with pricing
        self.assertNotContains(response, "Current Plan</h2>")
        # Should NOT show MWK 20,000 / month
        self.assertNotContains(response, "20,000 / month")

    def test_trial_user_does_not_see_draft_invoices(self):
        """Trial users should NOT see draft invoices in the manage page"""
        # Create trial subscription
        sub = BusinessSubscription.start_trial(business=self.business, plan=self.starter_plan, days=30)
        
        # Create a draft invoice (simulating what happens when user clicks "Choose Plan")
        invoice = Invoice.objects.create(
            business=self.business,
            total=Decimal("20000.00"),
            currency="MWK",
            status=Invoice.Status.DRAFT,
            number="INV-TEST-001"
        )

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("billing:manage"))

        # Should NOT show the draft invoice
        self.assertNotContains(response, "INV-TEST-001")

    def test_active_user_sees_current_plan_details(self):
        """Active (paid) users should see 'Current Plan' with pricing and details"""
        # Create ACTIVE subscription
        sub = BusinessSubscription.objects.create(
            business=self.business,
            plan=self.starter_plan,
            status=BusinessSubscription.Status.ACTIVE
        )

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("billing:manage"))

        # Should show "Current Plan" section
        self.assertContains(response, "Current Plan</h2>")
        # Should show plan name
        self.assertContains(response, "Starter")
        # Should show pricing
        self.assertContains(response, "20,000")

    def test_active_user_sees_paid_invoices(self):
        """Active users should see paid invoices"""
        # Create ACTIVE subscription
        sub = BusinessSubscription.objects.create(
            business=self.business,
            plan=self.starter_plan,
            status=BusinessSubscription.Status.ACTIVE
        )
        
        # Create a paid invoice
        invoice = Invoice.objects.create(
            business=self.business,
            total=Decimal("20000.00"),
            currency="MWK",
            status=Invoice.Status.PAID,
            number="INV-PAID-001"
        )

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("billing:manage"))

        # Should show the paid invoice
        self.assertContains(response, "INV-PAID-001")


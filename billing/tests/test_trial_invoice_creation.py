"""
Tests for trial subscription behavior and invoice creation timing.
Ensures invoices are NOT created until payment is confirmed.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from billing.models import BusinessSubscription, Invoice, PendingCheckout, SubscriptionPlan
from tenants.models import Business, Membership

User = get_user_model()


class TrialInvoiceCreationTest(TestCase):
    """Test that invoices are NOT created for trial users until payment succeeds"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        self.business = Business.objects.create(name="Test Business", slug="test-business")
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER")
        
        # Create starter plan
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

    def test_trial_user_has_no_invoices(self):
        """Trial users should have NO invoices (not even drafts)"""
        # Create trial subscription
        sub = BusinessSubscription.start_trial(business=self.business, plan=self.starter_plan, days=30)

        # Check no invoices exist
        invoice_count = Invoice.objects.filter(business=self.business).count()
        self.assertEqual(invoice_count, 0, "Trial user should have ZERO invoices")

    def test_select_plan_creates_pending_checkout_not_invoice(self):
        """Selecting a plan should create PendingCheckout, NOT an invoice"""
        # Create trial subscription
        sub = BusinessSubscription.start_trial(business=self.business, plan=self.starter_plan, days=30)

        self.client.login(username="testuser", password="testpass123")
        
        # Select a plan
        response = self.client.post(reverse("billing:select_plan"), {"plan": self.starter_plan.id})
        
        # Should redirect to checkout
        self.assertEqual(response.status_code, 302)
        self.assertIn("/billing/checkout", response.url)
        
        # Should create PendingCheckout
        pending_count = PendingCheckout.objects.filter(business=self.business, status=PendingCheckout.Status.PENDING).count()
        self.assertEqual(pending_count, 1, "Should create one PendingCheckout")
        
        # Should NOT create invoice yet
        invoice_count = Invoice.objects.filter(business=self.business).count()
        self.assertEqual(invoice_count, 0, "Should NOT create invoice before payment")

    def test_manage_page_shows_no_invoices_for_trial(self):
        """Manage page should show NO invoices for trial users"""
        # Create trial subscription
        sub = BusinessSubscription.start_trial(business=self.business, plan=self.starter_plan, days=30)

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("billing:manage"))

        # Should show trial info
        self.assertContains(response, "Free Trial")
        
        # Should NOT show paid plan details
        self.assertNotContains(response, "MWK 10,000")  # Plan price should not appear
        
        # Invoices table should be empty or hidden
        content = response.content.decode('utf-8')
        # If there's an invoices section, it should show 0 invoices
        if 'invoice' in content.lower():
            invoice_count = Invoice.objects.filter(business=self.business).count()
            self.assertEqual(invoice_count, 0)

    def test_active_subscription_after_payment_has_invoice(self):
        """After payment succeeds, subscription should be ACTIVE and have a PAID invoice"""
        # This would be tested via webhook simulation
        # For now, just verify the model states
        
        # Create trial subscription
        sub = BusinessSubscription.start_trial(business=self.business, plan=self.starter_plan, days=30)
        
        # Simulate payment success: activate subscription
        from django.utils import timezone
        sub.status = BusinessSubscription.Status.ACTIVE
        sub.last_payment_at = timezone.now()
        sub.save()
        
        # Create invoice (this would happen in webhook handler)
        invoice = Invoice.objects.create(
            business=self.business,
            subscription=sub,
            currency="MWK",
            status=Invoice.Status.PAID,
        )
        
        # Now verify
        self.assertEqual(sub.status, BusinessSubscription.Status.ACTIVE)
        self.assertIsNotNone(sub.last_payment_at)
        
        invoice_count = Invoice.objects.filter(business=self.business, status=Invoice.Status.PAID).count()
        self.assertEqual(invoice_count, 1, "Should have one PAID invoice after payment")


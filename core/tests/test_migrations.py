# core/tests/test_migrations.py
"""
Tests to ensure migrations are consistent and all fields exist.
"""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase


class MigrationConsistencyTest(TestCase):
    """Test that migrations are consistent and all required fields exist."""

    def test_no_missing_migrations(self):
        """Test that there are no missing migrations."""
        out = StringIO()
        try:
            call_command("makemigrations", "--check", "--dry-run", stdout=out, stderr=out)
        except Exception as e:
            self.fail(f"Missing migrations detected: {e}\nRun: python manage.py makemigrations")

    def test_business_has_hq_notified_signup_at(self):
        """Test that Business model has hq_notified_signup_at field."""
        from tenants.models import Business

        # Check field exists
        self.assertTrue(
            hasattr(Business, "hq_notified_signup_at"), "Business model missing hq_notified_signup_at field"
        )

        # Check field is nullable
        field = Business._meta.get_field("hq_notified_signup_at")
        self.assertTrue(field.null, "hq_notified_signup_at should be nullable")
        self.assertTrue(field.blank, "hq_notified_signup_at should be blank=True")

    def test_subscription_has_hq_notification_fields(self):
        """Test that BusinessSubscription has all HQ notification fields."""
        from billing.models import BusinessSubscription

        required_fields = [
            "cancel_requested_at",
            "hq_notified_cancel_requested_at",
            "hq_notified_canceled_at",
            "hq_notified_suspended_at",
        ]

        for field_name in required_fields:
            self.assertTrue(
                hasattr(BusinessSubscription, field_name), f"BusinessSubscription missing {field_name} field"
            )

            field = BusinessSubscription._meta.get_field(field_name)
            self.assertTrue(field.null, f"{field_name} should be nullable")
            self.assertTrue(field.blank, f"{field_name} should be blank=True")

    def test_invoice_has_hq_notified_paid_at(self):
        """Test that Invoice model has hq_notified_paid_at field."""
        from billing.models import Invoice

        self.assertTrue(hasattr(Invoice, "hq_notified_paid_at"), "Invoice model missing hq_notified_paid_at field")

        field = Invoice._meta.get_field("hq_notified_paid_at")
        self.assertTrue(field.null, "hq_notified_paid_at should be nullable")
        self.assertTrue(field.blank, "hq_notified_paid_at should be blank=True")

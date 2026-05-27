# notifications/management/commands/email_smoke_test.py
"""
Management command to smoke test email notifications.
Tests both welcome email and OTP reset email flows.

Usage: python manage.py email_smoke_test you@email.com
"""
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from notifications.services import emit_event
from notifications.models import NotificationEvent
from circuitcity.accounts.models import EmailOTP
from circuitcity.accounts.services.email_otp import request_email_otp

User = get_user_model()


class Command(BaseCommand):
    help = "Smoke test email notifications (welcome + OTP reset)"

    def add_arguments(self, parser):
        parser.add_argument(
            "email",
            type=str,
            help="Email address to test with (user will be created if missing)",
        )

    def handle(self, *args, **options):
        email = options["email"].strip().lower()

        self.stdout.write(self.style.SUCCESS("=== Email Smoke Test ==="))
        self.stdout.write("")

        # Print email backend status
        self.stdout.write(f"EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
        use_console = os.getenv("USE_CONSOLE_EMAIL")
        has_sendgrid = bool(os.getenv("SENDGRID_API_KEY"))
        self.stdout.write(f"USE_CONSOLE_EMAIL: {use_console}")
        self.stdout.write(f"HAS SENDGRID_API_KEY: {has_sendgrid}")
        self.stdout.write("")

        # Ensure test user exists
        user, created = User.objects.get_or_create(
            email__iexact=email,
            defaults={
                "username": email,
                "email": email,
                "first_name": "Test",
                "last_name": "User",
            },
        )
        if created:
            user.set_password("test_password_123")
            user.save()
            self.stdout.write(self.style.SUCCESS(f"✓ Created test user: {email}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"✓ Using existing user: {email}"))
        self.stdout.write("")

        # Get or create a business for the user (needed for welcome email)
        business = None
        try:
            from tenants.models import Business, Membership

            # Try to get user's first business
            membership = Membership.objects.filter(user=user, status="ACTIVE").first()
            if membership:
                business = membership.business
            else:
                # Create a test business if none exists
                business, _ = Business.objects.get_or_create(
                    slug="test-business",
                    defaults={
                        "name": "Test Business",
                        "status": "ACTIVE",
                    },
                )
                Membership.objects.get_or_create(
                    user=user, business=business, defaults={"role": "MANAGER", "status": "ACTIVE"}
                )
                self.stdout.write(self.style.SUCCESS(f"✓ Created test business: {business.name}"))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠ Could not get/create business: {e}"))

        self.stdout.write("")
        self.stdout.write("--- Testing Welcome Email ---")

        # Test 1: Welcome email
        try:
            emit_event(
                event_type="WELCOME_MANAGER",
                recipients=[email],
                dedupe_key=f"WELCOME_MANAGER:SMOKE_TEST:{user.id}",
                payload={
                    "manager_name": user.get_full_name() or user.username,
                    "business_name": business.name if business else "Test Business",
                    "login_url": "https://emajinet.africa/dashboard/",
                    "support_url": "https://emajinet.africa/support",
                    "next_steps": [
                        "Scan In - Add products to your inventory",
                        "Scan & Sell - Process sales quickly",
                    ],
                },
                business=business,
                user=user,
            )
            self.stdout.write(self.style.SUCCESS("✓ Welcome email event created"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Failed to create welcome email event: {e}"))

        self.stdout.write("")
        self.stdout.write("--- Testing OTP Reset Email ---")

        # Test 2: OTP reset email
        try:
            # Create OTP record first
            otp_count_before = EmailOTP.objects.filter(email__iexact=email, purpose="reset").count()

            # Use the service function which creates EmailOTP and sends via emit_event
            request_email_otp(email, "reset", user=user, request=None)

            otp_count_after = EmailOTP.objects.filter(email__iexact=email, purpose="reset").count()
            if otp_count_after > otp_count_before:
                self.stdout.write(self.style.SUCCESS(f"✓ OTP record created (count: {otp_count_after})"))
            else:
                self.stdout.write(self.style.WARNING("⚠ OTP record count did not increase (may be rate-limited)"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Failed to create OTP reset: {e}"))

        # Wait a moment for async processing
        import time

        self.stdout.write("")
        self.stdout.write("Waiting 2 seconds for async processing...")
        time.sleep(2)

        # Print last 10 NotificationEvent rows
        self.stdout.write("")
        self.stdout.write("--- Last 10 NotificationEvent Rows ---")
        events = NotificationEvent.objects.order_by("-created_at")[:10]

        if not events:
            self.stdout.write(self.style.WARNING("⚠ No NotificationEvent rows found"))
        else:
            for event in events:
                status_style = {
                    "SENT": self.style.SUCCESS,
                    "FAILED": self.style.ERROR,
                    "SKIPPED": self.style.WARNING,
                    "PENDING": self.style.WARNING,
                }.get(event.status, self.style.NOTICE)

                self.stdout.write(
                    f"{status_style(event.status)} | "
                    f"{event.event_type} | "
                    f"{event.recipient_email} | "
                    f'{event.created_at.strftime("%Y-%m-%d %H:%M:%S")}'
                )
                if event.last_error:
                    self.stdout.write(f"  Error: {event.last_error[:100]}")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Smoke Test Complete ==="))
        self.stdout.write("")
        self.stdout.write("Check your email inbox for:")
        self.stdout.write(f"  1. Welcome email to {email}")
        self.stdout.write(f"  2. OTP reset code email to {email}")
        self.stdout.write("")
        if "console" in settings.EMAIL_BACKEND.lower():
            self.stdout.write(self.style.WARNING("⚠ Using console backend - check terminal output above for emails"))

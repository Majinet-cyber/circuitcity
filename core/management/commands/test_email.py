# core/management/commands/test_email.py
"""
Management command to test SendGrid email sending via Django send_mail.
Usage: python manage.py test_email someone@email.com
"""
from django.core.management.base import BaseCommand, CommandError
from django.core.mail import send_mail
from django.conf import settings


class Command(BaseCommand):
    help = "Test email sending to a specified email address using Django send_mail"

    def add_arguments(self, parser):
        parser.add_argument("email", type=str, help="Email address to send test email to")

    def handle(self, *args, **options):
        email = options["email"]

        if "@" not in email:
            raise CommandError(f"Invalid email address: {email}")

        self.stdout.write(f"Sending test email to {email}...")
        self.stdout.write(f"Using backend: {settings.EMAIL_BACKEND}")

        # Warn if using console backend
        if "console" in settings.EMAIL_BACKEND.lower():
            self.stdout.write(
                self.style.WARNING(
                    "⚠ WARNING: Using console backend. No real email will be sent - "
                    "email content will be printed to terminal instead."
                )
            )

        try:
            result = send_mail(
                subject="Test Email from Emajinet",
                message="Test Email\n\nThis is a test email from the Emajinet system.\n\nIf you received this, your email configuration is working correctly!",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )

            if result:
                self.stdout.write(self.style.SUCCESS(f"✓ Test email sent successfully to {email}"))
            else:
                self.stdout.write(self.style.ERROR(f"✗ Failed to send test email to {email}"))

        except Exception as e:
            raise CommandError(f"Error sending email: {e}")

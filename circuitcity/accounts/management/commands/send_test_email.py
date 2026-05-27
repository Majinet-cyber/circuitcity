"""
Management command to send a test email via SendGrid.
Usage: python manage.py send_test_email you@gmail.com
"""
from django.core.management.base import BaseCommand, CommandError
from django.core.mail import send_mail
from django.conf import settings


class Command(BaseCommand):
    help = "Send a test email to verify SendGrid configuration"

    def add_arguments(self, parser):
        parser.add_argument(
            "email",
            type=str,
            help="Email address to send the test email to",
        )

    def handle(self, *args, **options):
        email = options["email"].strip()

        if not email or "@" not in email:
            raise CommandError("Please provide a valid email address")

        subject = "Test Email from Emajinet"
        message = (
            "This is a test email sent from the Emajinet/CircuitCity application.\n\n"
            "If you received this email, your SendGrid configuration is working correctly!"
        )
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@emajinet.africa")

        try:
            send_mail(subject, message, from_email, [email], fail_silently=False)
            self.stdout.write(self.style.SUCCESS(f"✓ Test email sent successfully to {email}"))
        except Exception as e:
            raise CommandError(f"Failed to send email: {e}")

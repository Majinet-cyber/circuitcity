# notifications/management/commands/email_debug.py
"""
Management command to debug email configuration.
Prints email backend settings, SendGrid config, and environment variables.
Usage: python manage.py email_debug
"""
from django.core.management.base import BaseCommand
from django.conf import settings
import os


class Command(BaseCommand):
    help = 'Debug email configuration (backend, SendGrid, environment variables)'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("Email Configuration Debug"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write("")
        
        # Email backend
        email_backend = getattr(settings, "EMAIL_BACKEND", "Not set")
        self.stdout.write(f"EMAIL_BACKEND: {email_backend}")
        self.stdout.write("")
        
        # USE_CONSOLE_EMAIL
        use_console_email = getattr(settings, "USE_CONSOLE_EMAIL", None)
        env_use_console = os.environ.get("USE_CONSOLE_EMAIL", "Not set")
        self.stdout.write(f"settings.USE_CONSOLE_EMAIL: {use_console_email}")
        self.stdout.write(f"env USE_CONSOLE_EMAIL: {env_use_console}")
        self.stdout.write("")
        
        # SendGrid API Key
        sendgrid_key = os.environ.get("SENDGRID_API_KEY", "")
        has_sendgrid = bool(sendgrid_key)
        self.stdout.write(f"HAS SENDGRID_API_KEY: {has_sendgrid}")
        if has_sendgrid:
            # Show first 8 chars and last 4 chars for verification (not full key)
            masked = f"{sendgrid_key[:8]}...{sendgrid_key[-4:]}" if len(sendgrid_key) > 12 else "***"
            self.stdout.write(f"  (masked: {masked})")
        else:
            self.stdout.write(self.style.WARNING("  ⚠ SENDGRID_API_KEY not set"))
        self.stdout.write("")
        
        # ANYMAIL config
        anymail_config = getattr(settings, "ANYMAIL", None)
        has_anymail = bool(anymail_config)
        self.stdout.write(f"ANYMAIL config present: {has_anymail}")
        if has_anymail:
            anymail_keys = list(anymail_config.keys()) if isinstance(anymail_config, dict) else []
            self.stdout.write(f"  ANYMAIL keys: {', '.join(anymail_keys)}")
        self.stdout.write("")
        
        # DEFAULT_FROM_EMAIL
        default_from = getattr(settings, "DEFAULT_FROM_EMAIL", "Not set")
        self.stdout.write(f"DEFAULT_FROM_EMAIL: {default_from}")
        self.stdout.write("")
        
        # Summary
        self.stdout.write(self.style.SUCCESS("=" * 60))
        if use_console_email:
            self.stdout.write(self.style.WARNING("⚠ Using console backend - emails will print to terminal"))
        elif has_sendgrid:
            self.stdout.write(self.style.SUCCESS("✓ SendGrid configured - emails will be sent via SendGrid"))
        else:
            self.stdout.write(self.style.ERROR("✗ SendGrid not configured - email sending may fail"))
        self.stdout.write(self.style.SUCCESS("=" * 60))


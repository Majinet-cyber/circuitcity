# core/management/commands/email_debug.py
"""
Management command to debug email backend configuration.
Prints current email settings without exposing sensitive keys.
Usage: python manage.py email_debug
"""
import os
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Debug email backend configuration (no secrets printed)'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== Email Configuration Debug ==='))
        self.stdout.write('')
        
        # Email backend
        self.stdout.write(f'EMAIL_BACKEND: {settings.EMAIL_BACKEND}')
        self.stdout.write('')
        
        # Environment variables (never print API key value)
        use_console_email = os.getenv("USE_CONSOLE_EMAIL")
        self.stdout.write(f'USE_CONSOLE_EMAIL env: {use_console_email}')
        
        sendgrid_key = os.getenv("SENDGRID_API_KEY")
        has_key = bool(sendgrid_key)
        self.stdout.write(f'HAS SENDGRID_API_KEY: {has_key} (value hidden)')
        
        default_from = os.getenv("DEFAULT_FROM_EMAIL")
        self.stdout.write(f'DEFAULT_FROM_EMAIL env: {default_from}')
        self.stdout.write('')
        
        # Settings values
        self.stdout.write('--- Settings Values ---')
        self.stdout.write(f'settings.DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}')
        self.stdout.write(f'settings.SERVER_EMAIL: {getattr(settings, "SERVER_EMAIL", "NOT SET")}')
        self.stdout.write('')
        
        # Anymail config (if set)
        if hasattr(settings, 'ANYMAIL'):
            anymail_config = settings.ANYMAIL
            self.stdout.write('ANYMAIL config present: YES')
            if 'SENDGRID_API_KEY' in anymail_config:
                key_length = len(str(anymail_config.get('SENDGRID_API_KEY', '')))
                self.stdout.write(f'  SENDGRID_API_KEY length: {key_length} chars (value hidden)')
        else:
            self.stdout.write('ANYMAIL config present: NO')
        self.stdout.write('')
        
        # Status
        if "console" in settings.EMAIL_BACKEND.lower():
            self.stdout.write(self.style.WARNING('⚠ Using console backend - emails will print to terminal'))
        else:
            self.stdout.write(self.style.SUCCESS('✓ Using production backend - emails will be sent'))


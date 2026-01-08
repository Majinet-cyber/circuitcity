# cc/models_email.py
"""
SSOT Email Delivery Log Model
Tracks all email sending attempts for reliability and visibility.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class EmailDeliveryLog(models.Model):
    """
    Centralized email delivery log for all outgoing emails.
    Provides audit trail, retry tracking, and failure visibility.
    """
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('retrying', 'Retrying'),
    ]
    
    EVENT_CHOICES = [
        ('SALE_OCCURRED', 'Sale Occurred'),
        ('USER_SIGNUP', 'User Signup'),
        ('OTP_REQUEST', 'OTP Request'),
        ('SUBSCRIPTION_SUCCESS', 'Subscription Success'),
        ('SUBSCRIPTION_CANCELLED', 'Subscription Cancelled'),
        ('AGENT_COMMISSION', 'Agent Commission'),
        ('DAILY_SUMMARY', 'Daily Summary'),
        ('WEEKLY_DIGEST', 'Weekly Digest'),
        ('IMPORTANT_ALERT', 'Important Alert'),
        ('CUSTOM', 'Custom'),
    ]
    
    # Event metadata
    event = models.CharField(
        max_length=50,
        choices=EVENT_CHOICES,
        help_text="Type of email event being sent"
    )
    
    # Recipients
    to = models.EmailField(help_text="Primary recipient email")
    cc = models.TextField(blank=True, default='', help_text="CC recipients (comma-separated)")
    bcc = models.TextField(blank=True, default='', help_text="BCC recipients (comma-separated)")
    
    # Email content
    subject = models.CharField(max_length=255, help_text="Email subject line")
    template_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Template used (if applicable)"
    )
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True
    )
    attempts = models.IntegerField(
        default=0,
        help_text="Number of send attempts"
    )
    last_error = models.TextField(
        blank=True,
        default='',
        help_text="Last error message if failed"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When email was successfully sent"
    )
    
    # Optional relations
    business = models.ForeignKey(
        'tenants.Business',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='email_logs',
        help_text="Business this email relates to (if applicable)"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='email_logs',
        help_text="User this email relates to (if applicable)"
    )
    
    # Metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional context (sale_id, subscription_id, etc.)"
    )
    
    class Meta:
        verbose_name = "Email Delivery Log"
        verbose_name_plural = "Email Delivery Logs"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['event', 'created_at']),
            models.Index(fields=['to', 'created_at']),
            models.Index(fields=['business', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.event} to {self.to} - {self.status}"
    
    def mark_sent(self):
        """Mark email as successfully sent."""
        self.status = 'sent'
        self.sent_at = timezone.now()
        self.save(update_fields=['status', 'sent_at', 'updated_at'])
    
    def mark_failed(self, error_message: str):
        """Mark email as failed with error message."""
        self.status = 'failed'
        self.last_error = error_message
        self.save(update_fields=['status', 'last_error', 'updated_at'])
    
    def increment_attempts(self):
        """Increment attempt counter."""
        self.attempts += 1
        if self.attempts > 1:
            self.status = 'retrying'
        self.save(update_fields=['attempts', 'status', 'updated_at'])


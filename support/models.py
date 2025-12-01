# support/models.py
"""
Ticket system for manager-HQ communication and issue tracking.
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.urls import reverse
from tenants.models import Business


class Ticket(models.Model):
    """
    Support ticket created by managers, handled by HQ staff.
    """
    STATUS_CHOICES = [
        ('OPEN', 'Open'),
        ('IN_PROGRESS', 'In Progress'),
        ('RESOLVED', 'Resolved'),
        ('CLOSED', 'Closed'),
    ]
    
    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('URGENT', 'Urgent'),
    ]
    
    # Reference number (e.g., EMA-2025-000123)
    reference = models.CharField(max_length=50, unique=True, db_index=True, editable=False)
    
    # Relations
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='tickets')
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='tickets_created')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets_assigned')
    
    # Content
    subject = models.CharField(max_length=200)
    description = models.TextField()
    
    # Status & Priority
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OPEN', db_index=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='MEDIUM')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tickets_resolved'
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['business', 'status']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['reference']),
        ]
    
    def __str__(self):
        return f"{self.reference}: {self.subject}"
    
    def save(self, *args, **kwargs):
        # Generate reference number if not set
        if not self.reference:
            # Format: EMA-YYYY-NNNNNN
            year = timezone.now().year
            # Count tickets this year
            count = Ticket.objects.filter(
                created_at__year=year
            ).count() + 1
            self.reference = f"EMA-{year}-{count:06d}"
        
        # Set resolved_at when status changes to RESOLVED or CLOSED
        if self.status in ['RESOLVED', 'CLOSED'] and not self.resolved_at:
            self.resolved_at = timezone.now()
        
        super().save(*args, **kwargs)
    
    def get_absolute_url(self):
        return reverse('support:ticket_detail', kwargs={'pk': self.pk})


class TicketComment(models.Model):
    """
    Comments/updates on a ticket.
    """
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    comment = models.TextField()
    is_internal = models.BooleanField(
        default=False,
        help_text="Internal notes only visible to HQ staff"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"Comment on {self.ticket.reference} by {self.author}"


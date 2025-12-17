# hq/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal


class HQPaymentMark(models.Model):
    """
    Track manual payment confirmations from HQ for subscription periods.
    Idempotent: one mark per business per period.
    """
    business = models.ForeignKey(
        "tenants.Business",
        on_delete=models.CASCADE,
        related_name="payment_marks"
    )
    period_start = models.DateField(help_text="Start of billing period")
    period_end = models.DateField(help_text="End of billing period")
    plan_code = models.CharField(max_length=50, blank=True, default="", help_text="Plan code at time of marking")
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), help_text="Amount marked paid")
    
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+"
    )
    marked_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True, default="")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["-period_start"]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "period_start", "period_end"],
                name="unique_payment_mark_per_period"
            )
        ]
        indexes = [
            models.Index(fields=["business", "period_start"]),
            models.Index(fields=["marked_at"]),
        ]
    
    def __str__(self):
        return f"{self.business.name} - {self.period_start} to {self.period_end} - Marked Paid"


class AgentMilestone(models.Model):
    """
    Track agent performance milestones and achievements for gamification.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="agent_milestones")
    business = models.ForeignKey("tenants.Business", on_delete=models.CASCADE, null=True, blank=True)
    milestone_type = models.CharField(max_length=50, help_text="Type of milestone (e.g., first_sale, 100_sales, top_seller)")
    achieved_at = models.DateTimeField(default=timezone.now)
    metadata = models.JSONField(default=dict, blank=True, help_text="Additional milestone data")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-achieved_at"]
        indexes = [
            models.Index(fields=["user", "milestone_type"]),
            models.Index(fields=["business", "achieved_at"]),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.milestone_type}"


# Support models (already exist based on imports, defining schema for completeness)
class SupportTicket(models.Model):
    """Support ticket tracking."""
    STATUS_CHOICES = [
        ("open", "Open"),
        ("in_progress", "In Progress"),
        ("resolved", "Resolved"),
        ("closed", "Closed"),
    ]
    
    business = models.ForeignKey("tenants.Business", on_delete=models.CASCADE, related_name="support_tickets")
    title = models.CharField(max_length=255)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")
    priority = models.CharField(max_length=20, default="medium")
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]
    
    def __str__(self):
        return f"Ticket #{self.id}: {self.title}"


class SupportActionLog(models.Model):
    """Log of support actions taken by HQ staff."""
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, null=True, blank=True, related_name="action_logs")
    business = models.ForeignKey("tenants.Business", on_delete=models.CASCADE, null=True, blank=True)
    
    action_type = models.CharField(max_length=50)
    description = models.TextField()
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    metadata = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "created_at"]),
            models.Index(fields=["ticket", "created_at"]),
        ]
    
    def __str__(self):
        return f"{self.action_type} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"


# Contract models (for HQ contract management)
class MerchantContract(models.Model):
    """Business contract storage and management."""
    business = models.ForeignKey("tenants.Business", on_delete=models.CASCADE, related_name="contracts")
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to="contracts/", null=True, blank=True)
    contract_type = models.CharField(max_length=50, default="standard")
    
    signed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "contract_type"]),
        ]
    
    def __str__(self):
        return f"{self.business.name} - {self.title}"

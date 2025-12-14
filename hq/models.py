# hq/models.py
"""
HQ Admin support models for multi-tenant overwatch console.
Provides support tickets, notes, and comprehensive audit logging.
"""
from __future__ import annotations

import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


# ======================================================================
# Support Action Log (Immutable Audit Trail for HQ Actions)
# ======================================================================
class SupportActionType(models.TextChoices):
    """All possible HQ support actions that need auditing."""
    # Subscription actions
    EXTEND_SUBSCRIPTION = "EXTEND_SUBSCRIPTION", "Extended Subscription"
    REVOKE_SUBSCRIPTION = "REVOKE_SUBSCRIPTION", "Revoked Subscription"
    SUSPEND_SUBSCRIPTION = "SUSPEND_SUBSCRIPTION", "Suspended Subscription"
    ACTIVATE_SUBSCRIPTION = "ACTIVATE_SUBSCRIPTION", "Activated Subscription"
    CHANGE_PLAN = "CHANGE_PLAN", "Changed Plan"
    ADD_GRACE_DAYS = "ADD_GRACE_DAYS", "Added Grace Days"
    
    # Account/Login actions
    FORCE_LOGOUT = "FORCE_LOGOUT", "Force Logout"
    RESET_PASSWORD = "RESET_PASSWORD", "Reset Password"
    UNLOCK_ACCOUNT = "UNLOCK_ACCOUNT", "Unlocked Account"
    RESEND_OTP = "RESEND_OTP", "Resent OTP"
    VERIFY_EMAIL = "VERIFY_EMAIL", "Verified Email"
    IMPERSONATE_USER = "IMPERSONATE_USER", "Impersonated User"
    END_IMPERSONATION = "END_IMPERSONATION", "Ended Impersonation"
    
    # Data/Inventory actions
    RESTORE_STOCK = "RESTORE_STOCK", "Restored Stock"
    ARCHIVE_STOCK = "ARCHIVE_STOCK", "Archived Stock"
    REVERSE_TRANSACTION = "REVERSE_TRANSACTION", "Reversed Transaction"
    FIX_DUPLICATE = "FIX_DUPLICATE", "Fixed Duplicate Entry"
    HARD_DELETE = "HARD_DELETE", "Hard Delete"
    
    # Payment actions
    RECORD_MANUAL_PAYMENT = "RECORD_MANUAL_PAYMENT", "Recorded Manual Payment"
    APPLY_CREDIT = "APPLY_CREDIT", "Applied Credit"
    APPLY_DISCOUNT = "APPLY_DISCOUNT", "Applied Discount"
    REFUND_PAYMENT = "REFUND_PAYMENT", "Refunded Payment"
    RESEND_RECEIPT = "RESEND_RECEIPT", "Resent Receipt"
    
    # Viewing actions
    VIEW_BUSINESS = "VIEW_BUSINESS", "Viewed Business"
    VIEW_DASHBOARD = "VIEW_DASHBOARD", "Viewed Dashboard"
    EXPORT_DATA = "EXPORT_DATA", "Exported Data"
    
    # Other
    CREATE_TICKET = "CREATE_TICKET", "Created Support Ticket"
    UPDATE_TICKET = "UPDATE_TICKET", "Updated Support Ticket"
    ADD_NOTE = "ADD_NOTE", "Added Note"
    OTHER = "OTHER", "Other Action"


class SupportActionLog(models.Model):
    """
    Immutable audit trail of all HQ admin actions.
    Every destructive or sensitive HQ operation MUST create an entry here.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Who performed the action
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="support_actions",
        help_text="HQ staff member who performed this action"
    )
    
    # Which business was affected
    business = models.ForeignKey(
        "tenants.Business",
        on_delete=models.CASCADE,
        related_name="support_actions",
        help_text="Business this action affected",
        db_index=True
    )
    
    # What was done
    action_type = models.CharField(
        max_length=32,
        choices=SupportActionType.choices,
        db_index=True,
        help_text="Type of action performed"
    )
    
    # Why it was done
    reason = models.TextField(
        help_text="Required explanation/justification for this action"
    )
    
    # Before/after state
    payload_before = models.JSONField(
        default=dict,
        blank=True,
        help_text="State before the action (for reversibility)"
    )
    payload_after = models.JSONField(
        default=dict,
        blank=True,
        help_text="State after the action"
    )
    
    # Additional context
    entity_type = models.CharField(
        max_length=64,
        blank=True,
        help_text="Type of entity affected (Subscription, User, Stock, etc.)"
    )
    entity_id = models.CharField(
        max_length=64,
        blank=True,
        help_text="ID of the affected entity"
    )
    
    # Request metadata
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the actor"
    )
    user_agent = models.TextField(
        blank=True,
        help_text="User agent of the actor"
    )
    
    # Immutable timestamp
    created_at = models.DateTimeField(
        default=timezone.now,
        editable=False,
        db_index=True
    )
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "-created_at"]),
            models.Index(fields=["actor", "-created_at"]),
            models.Index(fields=["action_type", "-created_at"]),
            models.Index(fields=["business", "action_type", "-created_at"]),
        ]
        verbose_name = "Support Action Log"
        verbose_name_plural = "Support Action Logs"
    
    def __str__(self) -> str:
        return f"{self.action_type} by {self.actor} on {self.business.name} at {self.created_at:%Y-%m-%d %H:%M}"
    
    def save(self, *args, **kwargs):
        # Ensure immutability: only allow creation, not updates
        if self.pk:
            raise ValueError("SupportActionLog entries are immutable and cannot be updated")
        super().save(*args, **kwargs)


# ======================================================================
# Support Tickets & Notes
# ======================================================================
class SupportTicketCategory(models.TextChoices):
    """Categories for support tickets."""
    LOGIN = "login", "Login/Access Issue"
    PAYMENT = "payment", "Payment/Billing Issue"
    DATA = "data", "Data/Inventory Issue"
    BUG = "bug", "Bug Report"
    FEATURE = "feature", "Feature Request"
    PERFORMANCE = "performance", "Performance Issue"
    OTHER = "other", "Other"


class SupportTicketPriority(models.TextChoices):
    """Priority levels for tickets."""
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    URGENT = "urgent", "Urgent"


class SupportTicketStatus(models.TextChoices):
    """Status for support tickets."""
    OPEN = "open", "Open"
    IN_PROGRESS = "in_progress", "In Progress"
    WAITING_CUSTOMER = "waiting_customer", "Waiting on Customer"
    RESOLVED = "resolved", "Resolved"
    CLOSED = "closed", "Closed"


class SupportTicket(models.Model):
    """
    Support ticket for tracking customer issues and HQ interventions.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Ticket identification
    ticket_number = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        help_text="Human-readable ticket number (e.g., HQ-2025-001234)"
    )
    
    # Which business
    business = models.ForeignKey(
        "tenants.Business",
        on_delete=models.CASCADE,
        related_name="support_tickets",
        db_index=True
    )
    
    # Who requested (optional - might be created by HQ proactively)
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_tickets_requested",
        help_text="User who requested support (if applicable)"
    )
    requester_email = models.EmailField(
        blank=True,
        help_text="Contact email if requester not in system"
    )
    
    # Ticket details
    category = models.CharField(
        max_length=20,
        choices=SupportTicketCategory.choices,
        default=SupportTicketCategory.OTHER,
        db_index=True
    )
    priority = models.CharField(
        max_length=10,
        choices=SupportTicketPriority.choices,
        default=SupportTicketPriority.MEDIUM,
        db_index=True
    )
    status = models.CharField(
        max_length=20,
        choices=SupportTicketStatus.choices,
        default=SupportTicketStatus.OPEN,
        db_index=True
    )
    
    # Content
    title = models.CharField(
        max_length=255,
        help_text="Short description of the issue"
    )
    description = models.TextField(
        help_text="Detailed description of the issue"
    )
    
    # Assignment
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_tickets_assigned",
        help_text="HQ staff member assigned to this ticket"
    )
    
    # Metadata
    meta = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metadata (e.g., error logs, screenshots)"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "status", "-created_at"]),
            models.Index(fields=["assigned_to", "status", "-created_at"]),
            models.Index(fields=["category", "status", "-created_at"]),
            models.Index(fields=["priority", "status", "-created_at"]),
        ]
        verbose_name = "Support Ticket"
        verbose_name_plural = "Support Tickets"
    
    def __str__(self) -> str:
        return f"{self.ticket_number}: {self.title} ({self.get_status_display()})"
    
    def save(self, *args, **kwargs):
        # Auto-generate ticket number if not set
        if not self.ticket_number:
            from django.utils.timezone import now
            today = now().date()
            # Count tickets created today
            count = SupportTicket.objects.filter(
                created_at__date=today
            ).count() + 1
            self.ticket_number = f"HQ-{today:%Y%m%d}-{count:04d}"
        
        # Auto-set resolved_at when status changes to resolved
        if self.status == SupportTicketStatus.RESOLVED and not self.resolved_at:
            self.resolved_at = timezone.now()
        
        # Auto-set closed_at when status changes to closed
        if self.status == SupportTicketStatus.CLOSED and not self.closed_at:
            self.closed_at = timezone.now()
        
        super().save(*args, **kwargs)


class SupportNote(models.Model):
    """
    Timeline entry for a support ticket (comments, status changes, actions taken).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name="notes"
    )
    
    # Who added the note
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="support_notes_authored",
        help_text="User who added this note"
    )
    
    # Note content
    note_type = models.CharField(
        max_length=20,
        choices=[
            ("comment", "Comment"),
            ("status_change", "Status Change"),
            ("action", "Action Taken"),
            ("system", "System Note"),
        ],
        default="comment"
    )
    content = models.TextField(
        help_text="Note content"
    )
    
    # Is this note internal (hidden from customer)?
    is_internal = models.BooleanField(
        default=False,
        help_text="If True, only visible to HQ staff"
    )
    
    # Metadata
    meta = models.JSONField(
        default=dict,
        blank=True
    )
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["ticket", "created_at"]),
        ]
        verbose_name = "Support Note"
        verbose_name_plural = "Support Notes"
    
    def __str__(self) -> str:
        return f"Note on {self.ticket.ticket_number} by {self.author} at {self.created_at:%Y-%m-%d %H:%M}"


class BusinessNote(models.Model):
    """
    Pinned notes for a business (e.g., special billing arrangements, quirks, support history).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    business = models.ForeignKey(
        "tenants.Business",
        on_delete=models.CASCADE,
        related_name="pinned_notes"
    )
    
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="business_notes_authored"
    )
    
    title = models.CharField(
        max_length=255,
        help_text="Short title for quick reference"
    )
    content = models.TextField(
        help_text="Detailed note content"
    )
    
    is_pinned = models.BooleanField(
        default=True,
        help_text="If True, shown prominently on business detail page"
    )
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["-is_pinned", "-created_at"]
        indexes = [
            models.Index(fields=["business", "is_pinned", "-created_at"]),
        ]
        verbose_name = "Business Note"
        verbose_name_plural = "Business Notes"
    
    def __str__(self) -> str:
        return f"Note on {self.business.name}: {self.title}"

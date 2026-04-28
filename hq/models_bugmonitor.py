# hq/models_bugmonitor.py
"""
Bug Monitor models: SystemIssue, SystemIssueOccurrence, AdminAuditLog.

Design:
  SystemIssue      – one row per unique bug (fingerprinted).
  SystemIssueOccurrence – one row per hit (child of SystemIssue).
  AdminAuditLog    – immutable trail of every HQ admin action.
"""
from __future__ import annotations

import hashlib
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

class IssueStatus(models.TextChoices):
    NEW          = "new",          "New"
    INVESTIGATING = "investigating", "Investigating"
    CLEARED      = "cleared",      "Cleared"
    IGNORED      = "ignored",      "Ignored"


class IssueSeverity(models.TextChoices):
    LOW      = "low",      "Low"
    MEDIUM   = "medium",   "Medium"
    HIGH     = "high",     "High"
    CRITICAL = "critical", "Critical"


# ---------------------------------------------------------------------------
# SystemIssue – grouped / de-duplicated bug
# ---------------------------------------------------------------------------

class SystemIssue(models.Model):
    """
    One row per unique bug fingerprint.

    Recurring errors increment occurrence_count and update last_seen_at
    rather than creating endless duplicate rows.
    """

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fingerprint = models.CharField(max_length=64, unique=True, db_index=True)

    # Classification
    title       = models.CharField(max_length=512, default="Unhandled exception")
    error_type  = models.CharField(max_length=255, blank=True, default="")
    message     = models.TextField(blank=True, default="")
    status_code = models.SmallIntegerField(null=True, blank=True, db_index=True)
    severity    = models.CharField(
        max_length=16, choices=IssueSeverity.choices,
        default=IssueSeverity.HIGH, db_index=True,
    )
    status      = models.CharField(
        max_length=20, choices=IssueStatus.choices,
        default=IssueStatus.NEW, db_index=True,
    )

    # Request context (from first occurrence)
    path        = models.CharField(max_length=2048, blank=True, default="")
    method      = models.CharField(max_length=16, blank=True, default="")
    view_name   = models.CharField(max_length=255, blank=True, default="")
    app_label   = models.CharField(max_length=100, blank=True, default="")

    # Actor context (from first occurrence)
    user        = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="system_issues",
    )
    business    = models.ForeignKey(
        "tenants.Business", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="system_issues",
    )

    # Device / browser (from first occurrence)
    user_agent     = models.TextField(blank=True, default="")
    device_family  = models.CharField(max_length=128, blank=True, default="")
    browser_family = models.CharField(max_length=128, blank=True, default="")
    os_family      = models.CharField(max_length=128, blank=True, default="")
    ip_address     = models.GenericIPAddressField(null=True, blank=True)

    # Safe-sanitized payload snapshots (from last occurrence)
    sanitized_get_params  = models.JSONField(default=dict, blank=True)
    sanitized_post_data   = models.JSONField(default=dict, blank=True)
    sanitized_payload     = models.JSONField(default=dict, blank=True)

    # Technical details (stack trace visible to superadmin / permissioned staff only)
    stack_trace = models.TextField(blank=True, default="")

    # Environment
    environment     = models.CharField(max_length=64, blank=True, default="")
    release_version = models.CharField(max_length=128, blank=True, default="")

    # Recurrence tracking
    occurrence_count = models.PositiveIntegerField(default=1)
    first_seen_at    = models.DateTimeField(default=timezone.now, db_index=True)
    last_seen_at     = models.DateTimeField(default=timezone.now, db_index=True)

    # Resolution workflow
    assigned_to      = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="assigned_issues",
        db_index=True,
    )
    notes            = models.TextField(blank=True, default="")
    resolution_notes = models.TextField(blank=True, default="")
    cleared_by       = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="cleared_issues",
    )
    cleared_at       = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_seen_at"]
        verbose_name = "System Issue"
        verbose_name_plural = "System Issues"
        permissions = [
            ("can_view_hq_admin",       "Can view HQ admin"),
            ("can_view_bug_monitor",    "Can view Bug Monitor"),
            ("can_view_stack_traces",   "Can view stack traces"),
            ("can_manage_bug_status",   "Can manage bug status"),
            ("can_assign_bugs",         "Can assign bugs"),
            ("can_view_audit_logs",     "Can view audit logs"),
            ("can_manage_admin_roles",  "Can manage admin roles"),
            ("can_view_business_data",  "Can view business data"),
            ("can_manage_integrations", "Can manage integrations"),
            ("can_view_webhooks",       "Can view webhooks"),
        ]
        indexes = [
            models.Index(fields=["fingerprint"]),
            models.Index(fields=["status", "severity"]),
            models.Index(fields=["status_code"]),
            models.Index(fields=["last_seen_at"]),
            models.Index(fields=["assigned_to"]),
        ]

    def __str__(self):
        return f"[{self.status_code or '?'}] {self.title[:80]}"

    @property
    def is_recurring(self) -> bool:
        return self.occurrence_count > 1

    @property
    def is_open(self) -> bool:
        return self.status in (IssueStatus.NEW, IssueStatus.INVESTIGATING)

    def mark_cleared(self, actor, notes: str = "") -> None:
        self.status = IssueStatus.CLEARED
        self.cleared_by = actor
        self.cleared_at = timezone.now()
        if notes:
            self.resolution_notes = notes
        self.save(update_fields=["status", "cleared_by", "cleared_at", "resolution_notes", "updated_at"])

    @staticmethod
    def build_fingerprint(
        error_type: str,
        status_code: int | None,
        path: str,
        view_name: str,
        top_frame: str,
    ) -> str:
        """
        Deterministic fingerprint for de-duplication.
        Normalize path to collapse numeric/UUID segments.
        """
        from hq.sanitizer import normalize_path_for_fingerprint
        norm_path = normalize_path_for_fingerprint(path or "")
        raw = "|".join([
            (error_type or ""),
            str(status_code or ""),
            norm_path,
            (view_name or ""),
            (top_frame or "")[:200],
        ])
        return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()


# ---------------------------------------------------------------------------
# SystemIssueOccurrence – one row per individual hit
# ---------------------------------------------------------------------------

class SystemIssueOccurrence(models.Model):
    """
    Individual occurrence of a SystemIssue.
    Keeps the history of every hit without bloating the parent row.
    """

    id    = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    issue = models.ForeignKey(
        SystemIssue, on_delete=models.CASCADE,
        related_name="occurrences", db_index=True,
    )

    # Snapshot of request context at time of occurrence
    path        = models.CharField(max_length=2048, blank=True, default="")
    method      = models.CharField(max_length=16, blank=True, default="")
    user        = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    business    = models.ForeignKey(
        "tenants.Business", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    user_agent  = models.TextField(blank=True, default="")
    ip_address  = models.GenericIPAddressField(null=True, blank=True)
    stack_trace = models.TextField(blank=True, default="")

    sanitized_get_params = models.JSONField(default=dict, blank=True)
    sanitized_post_data  = models.JSONField(default=dict, blank=True)
    sanitized_payload    = models.JSONField(default=dict, blank=True)

    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at"]
        verbose_name = "Issue Occurrence"
        verbose_name_plural = "Issue Occurrences"
        indexes = [
            models.Index(fields=["issue", "occurred_at"]),
        ]

    def __str__(self):
        return f"Occurrence of {self.issue_id} at {self.occurred_at}"


# ---------------------------------------------------------------------------
# AdminAuditLog – immutable HQ admin action trail
# ---------------------------------------------------------------------------

class AdminAuditLog(models.Model):
    """
    Immutable audit trail for all HQ admin actions.

    Separate from audit.AuditLog (which tracks business-level data changes).
    This tracks HQ staff operations: role changes, bug triaging, etc.
    """

    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor          = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="admin_audit_logs",
    )
    action         = models.CharField(max_length=100, db_index=True)

    # Target object (polymorphic — store model name + pk)
    target_model   = models.CharField(max_length=100, blank=True, default="")
    target_id      = models.CharField(max_length=100, blank=True, default="")
    target_repr    = models.CharField(max_length=512, blank=True, default="")

    # Change snapshots (safe: never store passwords/tokens)
    before         = models.JSONField(null=True, blank=True)
    after          = models.JSONField(null=True, blank=True)
    metadata       = models.JSONField(default=dict, blank=True)

    # Request context
    ip_address     = models.GenericIPAddressField(null=True, blank=True)
    user_agent     = models.TextField(blank=True, default="")

    created_at     = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Admin Audit Log"
        verbose_name_plural = "Admin Audit Logs"
        indexes = [
            models.Index(fields=["actor", "created_at"]),
            models.Index(fields=["action"]),
            models.Index(fields=["target_model", "target_id"]),
        ]

    def __str__(self):
        actor_name = self.actor.username if self.actor else "system"
        return f"{actor_name} → {self.action} [{self.created_at.strftime('%Y-%m-%d %H:%M')}]"

    @classmethod
    def record(
        cls,
        actor,
        action: str,
        *,
        target=None,
        target_model: str = "",
        target_id: str = "",
        target_repr: str = "",
        before: dict | None = None,
        after: dict | None = None,
        metadata: dict | None = None,
        request=None,
    ) -> "AdminAuditLog":
        """
        Convenience factory. Never raises — logs errors and returns None on failure.
        """
        try:
            ip = None
            ua = ""
            if request:
                ip = _get_client_ip(request)
                ua = request.META.get("HTTP_USER_AGENT", "")[:1000]

            if target is not None and not target_model:
                target_model = type(target).__name__
                target_id = str(getattr(target, "pk", "") or "")
                target_repr = str(target)[:512]

            return cls.objects.create(
                actor=actor if (actor and getattr(actor, "is_authenticated", False)) else None,
                action=action,
                target_model=target_model,
                target_id=target_id,
                target_repr=target_repr,
                before=before,
                after=after,
                metadata=metadata or {},
                ip_address=ip,
                user_agent=ua,
            )
        except Exception:
            import logging
            logging.getLogger("hq.audit").exception("Failed to write AdminAuditLog")
            return None


def _get_client_ip(request) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")

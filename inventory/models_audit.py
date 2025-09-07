# inventory/models_audit.py
from __future__ import annotations

import hashlib
import json
from typing import Dict, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils import timezone

User = get_user_model()


class AuditLog(models.Model):
    """
    Tamper-evident audit trail with hash chaining.
    Stores CREATE/UPDATE/DELETE events and relevant context.
    """

    ACTION_CHOICES = (
        ("CREATE", "Create"),
        ("UPDATE", "Update"),
        ("DELETE", "Delete"),
    )

    # Who / when / where
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    actor = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs"
    )
    ip = models.GenericIPAddressField(null=True, blank=True)
    ua = models.TextField(blank=True, default="")  # user-agent string

    # What was affected
    entity = models.CharField(max_length=100, db_index=True)
    entity_id = models.CharField(max_length=100, db_index=True)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    payload = models.JSONField(default=dict, blank=True)

    # Tamper-proofing: each row’s hash depends on the previous row’s hash + payload
    prev_hash = models.CharField(max_length=64, blank=True, default="")
    hash = models.CharField(max_length=64, unique=True, editable=False)

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["entity"]),
            models.Index(fields=["entity_id"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"[{self.action}] {self.entity}:{self.entity_id} by {self.actor or 'SYSTEM'}"

    # ---------- Hash Chain ----------

    def compute_payload(self, prev: str) -> Dict:
        """Exactly what goes into the hash computation."""
        return {
            "prev": prev,
            "actor": getattr(self.actor, "pk", None),
            "ip": self.ip,
            "ua": self.ua,
            "entity": self.entity,
            "entity_id": self.entity_id,
            "action": self.action,
            "payload": self.payload,
        }

    def compute_hash(self, prev: str) -> str:
        packed = json.dumps(self.compute_payload(prev), sort_keys=True).encode()
        return hashlib.sha256(packed).hexdigest()

    def save(self, *args, **kwargs):
        """Override save to automatically chain hashes."""
        if not self.prev_hash:
            last = AuditLog.objects.order_by("-id").first()
            self.prev_hash = last.hash if last else ""
        self.hash = self.compute_hash(self.prev_hash)
        super().save(*args, **kwargs)


# ---------- Signal helpers ----------

def _get_request_meta(request) -> Dict:
    return {
        "ip": request.META.get("REMOTE_ADDR"),
        "ua": request.META.get("HTTP_USER_AGENT", ""),
    }


def log_audit(
    *,
    actor: Optional[User],
    entity: str,
    entity_id: str,
    action: str,
    payload: Optional[Dict] = None,
    request=None,
) -> AuditLog:
    """
    Helper for creating audit rows anywhere in code.
    Example usage:
        log_audit(
            actor=request.user,
            entity="Stock",
            entity_id=str(stock.pk),
            action="UPDATE",
            payload={"before": {...}, "after": {...}},
            request=request,
        )
    """
    meta = _get_request_meta(request) if request else {}
    return AuditLog.objects.create(
        actor=actor,
        ip=meta.get("ip"),
        ua=meta.get("ua"),
        entity=entity,
        entity_id=str(entity_id),
        action=action.upper(),
        payload=payload or {},
    )


# ---------- Auto-log deletes via signals (optional) ----------

@receiver(pre_save)
def auto_log_delete_or_update(sender, instance, **kwargs):
    """
    For models we want to track automatically, we can hook in here later.
    Right now this is a placeholder — we won't automatically log unless explicitly hooked.
    """
    tracked = getattr(settings, "AUDIT_LOG_SETTINGS", {}).get("ENABLED", False)
    if not tracked:
        return
    # Example: we could auto-track certain models like Inventory, Stock, etc.
    return

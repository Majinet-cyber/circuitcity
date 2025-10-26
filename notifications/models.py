# notifications/models.py
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class Notification(models.Model):
    LEVELS = (
        ("info", "Info"),
        ("success", "Success"),
        ("warning", "Warning"),
        ("error", "Error"),
    )
    AUDIENCE = (
        ("ADMIN", "Admin"),
        ("AGENT", "Agent"),
    )

    audience = models.CharField(max_length=10, choices=AUDIENCE)
    # For agent notifications, target user (nullable for admin-wide notices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    message = models.TextField()
    level = models.CharField(max_length=10, choices=LEVELS, default="info")
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["audience", "created_at"]),
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["read_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        who = self.user or self.audience
        return f"[{self.audience}] {who}: {self.message[:60]}"

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    def mark_read(self):
        if not self.read_at:
            self.read_at = timezone.now()
            self.save(update_fields=["read_at"])



# cc/models_base.py
"""
Base models for soft-delete and audit trail functionality.
Provides a foundation for the "never lost" data promise.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class SoftDeleteManager(models.Manager):
    """Manager that excludes archived records by default."""

    def get_queryset(self):
        return super().get_queryset().filter(is_archived=False)

    def archived(self):
        """Get only archived records."""
        return super().get_queryset().filter(is_archived=True)

    def with_archived(self):
        """Get all records, including archived."""
        return super().get_queryset()


class BaseSoftDeleteModel(models.Model):
    """
    Base model that provides soft-delete functionality.

    Instead of permanently deleting records, they are marked as archived
    with a timestamp and the user who performed the action.

    This ensures critical business data is never truly lost.
    """

    is_archived = models.BooleanField(
        default=False, db_index=True, help_text="If True, this record has been 'deleted' (soft delete)."
    )
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True, help_text="When this record was archived.")
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_archived",
        help_text="User who archived this record.",
    )

    # Default manager excludes archived records
    objects = SoftDeleteManager()

    # Unscoped manager includes everything
    all_objects = models.Manager()

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["is_archived", "archived_at"]),
        ]

    def soft_delete(self, user=None):
        """
        Soft delete this record by marking it as archived.

        Args:
            user: The user performing the delete (optional)
        """
        self.is_archived = True
        self.archived_at = timezone.now()
        if user:
            self.archived_by = user
        self.save(update_fields=["is_archived", "archived_at", "archived_by"])

    def restore(self):
        """Restore an archived record."""
        self.is_archived = False
        self.archived_at = None
        self.archived_by = None
        self.save(update_fields=["is_archived", "archived_at", "archived_by"])

    def delete(self, *args, **kwargs):
        """
        Override delete to prevent accidental hard deletes.

        For safety, this raises an error. Use soft_delete() instead.
        If you really need to hard delete (e.g., for tests or admin cleanup),
        use force_delete().
        """
        raise ValueError(
            f"Cannot hard-delete {self.__class__.__name__}. "
            f"Use .soft_delete(user) to archive, or .force_delete() "
            f"if you absolutely must permanently delete."
        )

    def force_delete(self):
        """Permanently delete this record (bypasses soft delete)."""
        super().delete()


class AuditMixin(models.Model):
    """
    Mixin that adds created/updated tracking fields.
    Useful for audit trails alongside soft delete.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_created",
        help_text="User who created this record.",
    )

    class Meta:
        abstract = True

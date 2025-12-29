# backups/models.py
"""
Models for per-business backup and export functionality.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from tenants.models import Business


class BackupStatus(models.TextChoices):
    """Status of a backup snapshot."""
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"


class BackupSnapshot(models.Model):
    """
    Represents a full data export/backup for a specific business.
    
    Each snapshot is a complete, self-contained backup that includes:
    - Inventory data
    - Sales records
    - Wallet transactions
    - Timelogs
    - Layby contracts
    - Vertical-specific data (liquor, gym, clothing, pharmacy)
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="backup_snapshots",
        db_index=True,
        help_text="Business this backup belongs to."
    )
    
    created_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="When this backup was initiated."
    )
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="backups_created",
        help_text="User who requested this backup (usually a manager)."
    )
    
    status = models.CharField(
        max_length=20,
        choices=BackupStatus.choices,
        default=BackupStatus.PENDING,
        db_index=True,
        help_text="Current status of the backup."
    )
    
    file = models.FileField(
        upload_to="backups/%Y/%m/",
        null=True,
        blank=True,
        help_text="ZIP file containing the backup data."
    )
    
    file_size = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Size of the backup file in bytes."
    )
    
    error_message = models.TextField(
        blank=True,
        default="",
        help_text="Error message if backup failed."
    )
    
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this backup completed (success or failure)."
    )
    
    # Metadata about what was included
    records_count = models.JSONField(
        default=dict,
        blank=True,
        help_text="Count of records per model type included in this backup."
    )
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "-created_at"]),
            models.Index(fields=["business", "status"]),
            models.Index(fields=["status", "-created_at"]),
        ]
        verbose_name = "Backup Snapshot"
        verbose_name_plural = "Backup Snapshots"
    
    def __str__(self):
        return f"Backup for {self.business.name} at {self.created_at:%Y-%m-%d %H:%M}"
    
    @property
    def file_size_mb(self):
        """File size in megabytes."""
        if self.file_size:
            return round(self.file_size / (1024 * 1024), 2)
        return 0
    
    @property
    def size_display(self):
        """
        Human-readable file size display.
        
        Returns:
            - "xxx B" if < 1024 bytes
            - "xxx KB" if < 1 MB
            - "x.x MB" if >= 1 MB
            - "—" if file_size is None or 0
        """
        if not self.file_size or self.file_size == 0:
            return "—"
        
        bytes_val = self.file_size
        
        # Less than 1 KB
        if bytes_val < 1024:
            return f"{bytes_val} B"
        
        # Less than 1 MB
        if bytes_val < 1024 * 1024:
            kb = bytes_val / 1024
            return f"{kb:.1f} KB"
        
        # 1 MB or more
        mb = bytes_val / (1024 * 1024)
        return f"{mb:.1f} MB"
    
    @property
    def is_complete(self):
        """Whether this backup is finished (success or failed)."""
        return self.status in (BackupStatus.SUCCESS, BackupStatus.FAILED)
    
    @property
    def duration_seconds(self):
        """How long the backup took to complete."""
        if self.completed_at and self.created_at:
            return (self.completed_at - self.created_at).total_seconds()
        return None


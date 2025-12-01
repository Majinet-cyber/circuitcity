# timelogs/models.py
"""
Agent Work Log models for tracking on-site time, idle time, and presence.
This is the SINGLE SOURCE OF TRUTH for agent presence tracking.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.db import models
from django.db.models import Sum, F, ExpressionWrapper, DurationField
from django.utils import timezone


User = settings.AUTH_USER_MODEL


class WorkingHours(models.Model):
    """
    Working hours configuration per business (or per location).
    If location is NULL, this is the business-wide default.
    """
    business = models.ForeignKey(
        "tenants.Business",
        on_delete=models.CASCADE,
        related_name="working_hours",
    )
    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="working_hours",
        help_text="If null, this is the business-wide default.",
    )
    
    # Day of week (0=Monday, 6=Sunday) - NULL means applies to all days
    day_of_week = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        choices=[
            (0, "Monday"),
            (1, "Tuesday"),
            (2, "Wednesday"),
            (3, "Thursday"),
            (4, "Friday"),
            (5, "Saturday"),
            (6, "Sunday"),
        ],
        help_text="Leave blank for all days.",
    )
    
    scheduled_start = models.TimeField(
        default="08:00",
        help_text="Expected start time (e.g., 08:00).",
    )
    scheduled_end = models.TimeField(
        default="17:00",
        help_text="Expected end time (e.g., 17:00).",
    )
    
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = [("business", "location", "day_of_week")]
        ordering = ["business", "location", "day_of_week"]
        verbose_name = "Working Hours"
        verbose_name_plural = "Working Hours"
    
    def __str__(self):
        day = self.get_day_of_week_display() if self.day_of_week is not None else "All days"
        loc = self.location.name if self.location else "All locations"
        return f"{self.business.name} · {loc} · {day}: {self.scheduled_start}-{self.scheduled_end}"
    
    @classmethod
    def get_for_date(cls, business, location=None, date=None) -> Optional["WorkingHours"]:
        """
        Get the applicable working hours for a given date.
        Priority: location+day > location+all > business+day > business+all
        """
        if date is None:
            date = timezone.localdate()
        dow = date.weekday()
        
        qs = cls.objects.filter(business=business, is_active=True)
        
        # Try location-specific first
        if location:
            # location + specific day
            wh = qs.filter(location=location, day_of_week=dow).first()
            if wh:
                return wh
            # location + all days
            wh = qs.filter(location=location, day_of_week__isnull=True).first()
            if wh:
                return wh
        
        # Business-wide
        # business + specific day
        wh = qs.filter(location__isnull=True, day_of_week=dow).first()
        if wh:
            return wh
        # business + all days
        wh = qs.filter(location__isnull=True, day_of_week__isnull=True).first()
        return wh


class AgentWorkLog(models.Model):
    """
    Daily work log for an agent. ONE row per agent per work_date.
    Tracks: first seen, last seen, total on-site, total idle, scheduled hours.
    """
    agent = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="work_logs",
    )
    business = models.ForeignKey(
        "tenants.Business",
        on_delete=models.CASCADE,
        related_name="work_logs",
    )
    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_logs",
    )
    
    work_date = models.DateField(default=timezone.localdate, db_index=True)
    
    # Actual presence times
    first_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="First ping inside the geofence radius.",
    )
    last_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Most recent ping inside the geofence radius.",
    )
    
    # Computed totals (updated by ping endpoint or cron)
    total_on_site_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Total minutes spent inside the geofence.",
    )
    total_idle_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Total minutes away from the store during working hours.",
    )
    
    # Scheduled working hours for this day (copied from WorkingHours for reference)
    scheduled_start = models.TimeField(null=True, blank=True)
    scheduled_end = models.TimeField(null=True, blank=True)
    
    # Derived metrics for bonuses/penalties
    arrived_early_minutes = models.IntegerField(
        default=0,
        help_text="Minutes arrived before scheduled_start (positive = early).",
    )
    left_late_minutes = models.IntegerField(
        default=0,
        help_text="Minutes stayed after scheduled_end (positive = late).",
    )
    arrived_late_minutes = models.IntegerField(
        default=0,
        help_text="Minutes arrived after scheduled_start (positive = late).",
    )
    
    # Timestamp tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = [("agent", "business", "work_date")]
        ordering = ["-work_date", "-first_seen_at"]
        indexes = [
            models.Index(fields=["business", "work_date"]),
            models.Index(fields=["agent", "work_date"]),
            models.Index(fields=["location", "work_date"]),
        ]
    
    def __str__(self):
        return f"{self.agent} @ {self.business.name} on {self.work_date}"
    
    def populate_scheduled_hours(self) -> None:
        """Copy scheduled hours from WorkingHours config if not set."""
        if self.scheduled_start and self.scheduled_end:
            return
        wh = WorkingHours.get_for_date(self.business, self.location, self.work_date)
        if wh:
            self.scheduled_start = wh.scheduled_start
            self.scheduled_end = wh.scheduled_end
    
    def compute_early_late(self) -> None:
        """
        Compute early/late arrival and departure metrics.
        Call this after updating first_seen_at / last_seen_at.
        """
        if not self.scheduled_start or not self.scheduled_end:
            return
        
        if self.first_seen_at:
            sched_start_dt = timezone.make_aware(
                timezone.datetime.combine(self.work_date, self.scheduled_start)
            )
            diff = (sched_start_dt - self.first_seen_at).total_seconds() / 60
            if diff > 0:
                self.arrived_early_minutes = int(diff)
                self.arrived_late_minutes = 0
            else:
                self.arrived_early_minutes = 0
                self.arrived_late_minutes = int(abs(diff))
        
        if self.last_seen_at:
            sched_end_dt = timezone.make_aware(
                timezone.datetime.combine(self.work_date, self.scheduled_end)
            )
            diff = (self.last_seen_at - sched_end_dt).total_seconds() / 60
            if diff > 0:
                self.left_late_minutes = int(diff)
            else:
                self.left_late_minutes = 0
    
    @property
    def effective_work_minutes(self) -> int:
        """Total minutes from first_seen to last_seen minus idle."""
        if not self.first_seen_at or not self.last_seen_at:
            return 0
        total = (self.last_seen_at - self.first_seen_at).total_seconds() / 60
        return max(0, int(total) - self.total_idle_minutes)
    
    @property
    def early_bonus_blocks(self) -> int:
        """Number of 30-minute blocks arrived early (for bonus calculation)."""
        return max(0, self.arrived_early_minutes // 30)
    
    @property
    def late_penalty_blocks(self) -> int:
        """Number of 30-minute blocks arrived late (for penalty calculation)."""
        return max(0, self.arrived_late_minutes // 30)
    
    def save(self, *args, **kwargs):
        self.populate_scheduled_hours()
        self.compute_early_late()
        super().save(*args, **kwargs)


class LocationPing(models.Model):
    """
    Individual GPS ping from an agent. Used to compute on-site/idle time.
    Lightweight model - can be purged after daily aggregation.
    """
    work_log = models.ForeignKey(
        AgentWorkLog,
        on_delete=models.CASCADE,
        related_name="pings",
    )
    
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    
    is_inside_geofence = models.BooleanField(
        default=False,
        help_text="True if this ping was within the location's geofence radius.",
    )
    
    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["work_log", "timestamp"]),
        ]
    
    def __str__(self):
        status = "inside" if self.is_inside_geofence else "outside"
        return f"Ping {self.timestamp:%H:%M:%S} ({status})"


# =========================================================================
# Legacy compatibility - keep old TimeLog/TimeLogSegment for migration
# =========================================================================

class TimeLog(models.Model):
    """
    Legacy model - One shift/session per agent per day.
    Kept for backwards compatibility; new code should use AgentWorkLog.
    """
    agent = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="timelogs",
        help_text="The agent user for this time log.",
    )
    business = models.ForeignKey(
        "tenants.Business",
        on_delete=models.CASCADE,
        related_name="timelogs",
    )
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    note = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["-started_at"]

    @property
    def work_minutes(self):
        secs = self.segments.filter(in_range=True, ended_at__isnull=False).aggregate(
            s=Sum(ExpressionWrapper(F("ended_at") - F("started_at"), output_field=DurationField()))
        )["s"]
        return (secs.total_seconds() // 60) if secs else 0

    @property
    def out_minutes(self):
        secs = self.segments.filter(in_range=False, ended_at__isnull=False).aggregate(
            s=Sum(ExpressionWrapper(F("ended_at") - F("started_at"), output_field=DurationField()))
        )["s"]
        return (secs.total_seconds() // 60) if secs else 0

    def __str__(self):
        return f"TimeLog {self.id} - {self.agent} @ {self.business}"


class TimeLogSegment(models.Model):
    """
    Legacy model - Pieces that flip between in-range (work) and out-of-range (paused).
    """
    timelog = models.ForeignKey(TimeLog, on_delete=models.CASCADE, related_name="segments")
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    in_range = models.BooleanField(default=False)
    source = models.CharField(max_length=16, default="gps")  # gps/manual

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Segment {self.id} - {'IN' if self.in_range else 'OUT'}"

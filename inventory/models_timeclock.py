# inventory/models_timeclock.py
from __future__ import annotations
from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL

class TimeGeofence(models.Model):
    """Manager defines a store perimeter once (radius in meters)."""
    business = models.ForeignKey("tenants.Business", on_delete=models.CASCADE, related_name="geofences")
    name = models.CharField(max_length=120)
    lat = models.FloatField()
    lon = models.FloatField()
    radius_m = models.PositiveIntegerField(default=80)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("business", "name")]
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} Â· {self.radius_m}m"


class TimeSession(models.Model):
    """Single source of truth per user per geofence per day."""
    class State(models.TextChoices):
        ONSITE = "onsite", "On site"
        OFFSITE = "offsite", "Off site"
        CLOSED = "closed", "Closed"

    business = models.ForeignKey("tenants.Business", on_delete=models.CASCADE, related_name="time_sessions")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="time_sessions")
    geofence = models.ForeignKey(TimeGeofence, on_delete=models.PROTECT, related_name="sessions")
    day = models.DateField()  # local/tenant day (store time)
    arrival_at = models.DateTimeField(null=True, blank=True)
    departure_at = models.DateTimeField(null=True, blank=True)

    # Running totals (seconds)
    work_s = models.IntegerField(default=0)
    offsite_s = models.IntegerField(default=0)

    # Last known state + when that state began
    state = models.CharField(max_length=12, choices=State.choices, default=State.OFFSITE)
    state_since = models.DateTimeField(default=timezone.now)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["business", "user", "day"]),
            models.Index(fields=["business", "state"]),
        ]
        unique_together = [("business", "user", "geofence", "day")]

    def accumulate_until(self, now: timezone.datetime):
        """Accumulate time from state_since until now into work/offsite."""
        if self.state == self.State.CLOSED:
            return
        seconds = int((now - self.state_since).total_seconds())
        if seconds <= 0:
            return
        if self.state == self.State.ONSITE:
            self.work_s += seconds
        else:
            self.offsite_s += seconds
        self.state_since = now

    @property
    def net_work_hours(self) -> float:
        return round(self.work_s / 3600.0, 2)

    @property
    def off_hours(self) -> float:
        return round(self.offsite_s / 3600.0, 2)


class TimeEvent(models.Model):
    """Immutable audit of transitions / pings."""
    class Kind(models.TextChoices):
        PING = "ping", "Ping"
        ARRIVE = "arrive", "Arrive"
        DEPART = "depart", "Depart"
        ONSITE = "onsite", "On site"
        OFFSITE = "offsite", "Off site"
        CLOSE = "close", "Close"

    session = models.ForeignKey(TimeSession, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    at = models.DateTimeField(default=timezone.now)
    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)
    accuracy_m = models.FloatField(null=True, blank=True)
    note = models.CharField(max_length=240, blank=True, default="")

    class Meta:
        ordering = ["-at"]

    def __str__(self):
        return f"{self.kind}@{self.at:%H:%M}"



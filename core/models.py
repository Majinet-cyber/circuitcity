# core/models.py
from __future__ import annotations

import math
from datetime import timedelta
from typing import Optional, Tuple

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

User = get_user_model()

# -----------------------------------------------------------------------------
# Optional cross-app imports (guarded so this app can migrate independently)
# -----------------------------------------------------------------------------
try:
    # Your project already references these in hq/ and billing/
    from tenants.models import Business, Location  # type: ignore
except Exception:  # pragma: no cover - keep app bootstrappable
    class Business(models.Model):  # type: ignore
        name = models.CharField(max_length=255)
        def __str__(self) -> str:  # pragma: no cover
            return getattr(self, "name", f"Business#{self.pk}")

    class Location(models.Model):  # type: ignore
        business = models.ForeignKey("Business", on_delete=models.CASCADE, related_name="locations", null=True, blank=True)
        name = models.CharField(max_length=255)
        # Optional coordinates (store managers can set these)
        latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
        longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
        geofence_radius_m = models.PositiveIntegerField(default=75, help_text="Radius in meters for presence checks")
        def __str__(self) -> str:  # pragma: no cover
            return getattr(self, "name", f"Location#{self.pk}")


# -----------------------------------------------------------------------------
# Mixins
# -----------------------------------------------------------------------------
class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        abstract = True


# -----------------------------------------------------------------------------
# User Profile (lightweight; avoids touching auth_user table)
# -----------------------------------------------------------------------------
class Profile(TimeStampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    # Basic contact
    phone = models.CharField(max_length=32, blank=True, default="")
    whatsapp = models.CharField(max_length=32, blank=True, default="")
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)

    # Roles (complements is_staff / is_superuser)
    is_manager = models.BooleanField(default=False, help_text="Store/branch manager")

    # UX
    timezone = models.CharField(max_length=64, blank=True, default="")
    greeting_last_at = models.DateTimeField(null=True, blank=True, help_text="Last time we showed the daily greeting")

    # Product metrics (for light gamification nudges)
    last_month_sales = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    last_month_profit = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    def __str__(self) -> str:  # pragma: no cover
        return f"Profile({self.user_id})"


# -----------------------------------------------------------------------------
# Lightweight notification feed (for â€œDid you knowâ€¦â€, nudges, greetings)
# -----------------------------------------------------------------------------
class Notification(TimeStampedModel):
    class Kind(models.TextChoices):
        INFO = "INFO", "Info"
        SUCCESS = "SUCCESS", "Success"
        WARNING = "WARNING", "Warning"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.INFO)
    title = models.CharField(max_length=140, blank=True, default="")
    message = models.TextField()
    seen_at = models.DateTimeField(null=True, blank=True)

    # Optional business context
    business = models.ForeignKey(Business, null=True, blank=True, on_delete=models.SET_NULL, related_name="notifications")

    def mark_seen(self) -> None:
        self.seen_at = timezone.now()
        self.save(update_fields=["seen_at", "updated_at"])

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.kind}: {self.title or self.message[:24]}"


# -----------------------------------------------------------------------------
# Time tracking with geofence pause (arrival â†’ live counter; out-of-range â†’ pause)
# Managers can set coordinates on Location; the system uses them to validate presence.
# -----------------------------------------------------------------------------
class TimeLog(TimeStampedModel, SoftDeleteModel):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        PAUSED = "PAUSED", "Paused (Out of range)"
        CLOSED = "CLOSED", "Closed"

    # Scope
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="time_logs")
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name="time_logs")
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name="time_logs")

    # Session timeline
    started_at = models.DateTimeField(help_text="When the agent tapped Arrival / started the shift")
    paused_at = models.DateTimeField(null=True, blank=True, help_text="When we detected out-of-range and paused")
    ended_at = models.DateTimeField(null=True, blank=True, help_text="When the agent tapped Exit / end shift")

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN, db_index=True)

    # Live counters (kept denormalized for fast manager views)
    minutes_worked = models.PositiveIntegerField(default=0)
    minutes_out_of_range = models.PositiveIntegerField(default=0)

    # Device telemetry (last heartbeat)
    device_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    device_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    device_accuracy_m = models.PositiveIntegerField(null=True, blank=True)

    # Geofence override (if set, takes precedence over Location.geofence_radius_m)
    geofence_radius_m = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="0 = use Location radius; otherwise use this value",
    )

    note = models.CharField(max_length=240, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["business", "agent", "status"]),
            models.Index(fields=["created_at"]),
        ]
        ordering = ["-created_at"]

    # ----------------------------- Computation helpers -------------------------
    @staticmethod
    def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Distance in meters between two lat/lng points."""
        R = 6371000.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = phi2 - phi1
        dl = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    def _current_geofence(self) -> Optional[Tuple[float, float, int]]:
        """Return (lat, lng, radius_m) if we can check range."""
        loc = self.location
        if not loc or loc.latitude is None or loc.longitude is None:
            return None
        radius = int(self.geofence_radius_m or getattr(loc, "geofence_radius_m", 0) or 0)
        if radius <= 0:
            radius = 75  # sensible default if nothing set
        return float(loc.latitude), float(loc.longitude), radius

    def _is_in_range(self, lat: float, lng: float) -> Optional[bool]:
        """True=in-range, False=out, None=unknown (no geofence set)."""
        geo = self._current_geofence()
        if not geo:
            return None
        glat, glng, radius = geo
        dist = self._haversine_m(glat, glng, float(lat), float(lng))
        return dist <= radius

    # ----------------------------- State transitions --------------------------
    @classmethod
    def start(cls, *, business: Business, agent: User, location: Optional[Location] = None,
              lat: Optional[float] = None, lng: Optional[float] = None,
              accuracy_m: Optional[int] = None, note: str = "") -> "TimeLog":
        """Agent taps Arrival â€” start a new OPEN log and begin counting."""
        now = timezone.now()
        log = cls.objects.create(
            business=business,
            agent=agent,
            location=location,
            started_at=now,
            status=cls.Status.OPEN,
            device_lat=lat,
            device_lng=lng,
            device_accuracy_m=accuracy_m,
            note=note[:240] if note else "",
        )
        # If we can evaluate geofence and they are out-of-range immediately, mark paused
        if lat is not None and lng is not None:
            in_range = log._is_in_range(lat, lng)
            if in_range is False:
                log.status = cls.Status.PAUSED
                log.paused_at = now
                log.save(update_fields=["status", "paused_at", "updated_at"])
        return log

    def heartbeat(self, *, lat: Optional[float], lng: Optional[float], accuracy_m: Optional[int] = None) -> None:
        """
        Device pings location. We:
          - Accrue worked or out-of-range minutes since the last state change
          - Transition between OPEN<->PAUSED when crossing the geofence
        """
        now = timezone.now()

        # 1) Accrue time since last tick
        self._accrue_until(now)

        # 2) Update telemetry
        fields = ["updated_at"]
        if lat is not None:
            self.device_lat = lat; fields.append("device_lat")
        if lng is not None:
            self.device_lng = lng; fields.append("device_lng")
        if accuracy_m is not None:
            self.device_accuracy_m = int(accuracy_m); fields.append("device_accuracy_m")

        # 3) Range evaluation (if we have enough data)
        if lat is not None and lng is not None:
            in_range = self._is_in_range(lat, lng)
            if in_range is False and self.status == self.Status.OPEN:
                # Transition to PAUSED
                self.status = self.Status.PAUSED
                self.paused_at = now
                fields += ["status", "paused_at"]
            elif in_range is True and self.status == self.Status.PAUSED:
                # Resume to OPEN
                self.status = self.Status.OPEN
                self.paused_at = None
                fields += ["status", "paused_at"]

        self.save(update_fields=fields)

    def end(self, *, note: Optional[str] = None) -> None:
        """Agent taps Exit â€” finalize counts and close the log."""
        if self.status == self.Status.CLOSED:
            return
        now = timezone.now()
        self._accrue_until(now)
        self.ended_at = now
        self.status = self.Status.CLOSED
        if note:
            self.note = (self.note + " " + note).strip()[:240]
        self.save(update_fields=["minutes_worked", "minutes_out_of_range", "ended_at", "status", "note", "updated_at"])

    # ----------------------------- Accrual core -------------------------------
    def _accrue_until(self, ts: timezone.datetime) -> None:
        """
        Add minutes since the last state boundary to the appropriate counter.
        Rules:
          - OPEN accrues into minutes_worked
          - PAUSED accrues into minutes_out_of_range
        We measure from max(last boundary, created/started) to `ts`.
        """
        last = max(filter(None, [self.started_at, self.paused_at, self.created_at]))
        if ts <= last:
            return

        delta_min = int((ts - last).total_seconds() // 60)
        if delta_min <= 0:
            return

        if self.status == self.Status.OPEN:
            self.minutes_worked += delta_min
            self.save(update_fields=["minutes_worked", "updated_at"])
        elif self.status == self.Status.PAUSED:
            self.minutes_out_of_range += delta_min
            self.save(update_fields=["minutes_out_of_range", "updated_at"])
        # CLOSED state accrual isn't expected; guard by early return in end()

    # ----------------------------- Convenience --------------------------------
    @property
    def total_minutes(self) -> int:
        """Total minutes including out-of-range time (for full session length)."""
        end = self.ended_at or timezone.now()
        return int(max(0, (end - self.started_at).total_seconds() // 60))

    @property
    def worked_td(self) -> timedelta:
        return timedelta(minutes=self.minutes_worked)

    @property
    def out_of_range_td(self) -> timedelta:
        return timedelta(minutes=self.minutes_out_of_range)

    def __str__(self) -> str:  # pragma: no cover
        return f"TimeLog#{self.pk} {self.agent_id} {self.status}"


# -----------------------------------------------------------------------------
# Signals â€” create Profile automatically for new users
# -----------------------------------------------------------------------------
def _create_profile(sender, instance: User, created: bool, **kwargs) -> None:  # pragma: no cover
    if created:
        Profile.objects.create(user=instance)


try:  # pragma: no cover - avoid import errors at migration time
    from django.db.models.signals import post_save
    from django.dispatch import receiver

    @receiver(post_save, sender=User)
    def _auto_profile(sender, instance, created, **kwargs):
        _create_profile(sender, instance, created, **kwargs)

except Exception:
    # If signals can't be connected (during early migrations), that's fine.
    pass



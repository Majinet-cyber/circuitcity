# circuitcity/inventory/models_attendance.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model

from tenants.models import Business
from .models import Location  # your existing Location model

User = get_user_model()

# ---------------------------------------------------------------------
# Core enums / helpers
# ---------------------------------------------------------------------
CHECKIN_TYPES = (
    ("ARRIVAL", "Arrival"),
    ("DEPARTURE", "Departure"),
)

def _mwk(n: int) -> Decimal:
    return Decimal(n)

# ---------------------------------------------------------------------
# TimeLog — canonical attendance event
# ---------------------------------------------------------------------
class TimeLog(models.Model):
    """
    Raw events when an agent taps 'Check-in now' (Arrival/Departure).
    Keep 'business' nullable initially to avoid one-off default prompts;
    you can backfill from location.business then tighten later.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="time_logs",
        db_index=True,
        null=True, blank=True,   # <-- keep nullable for smooth migration
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="time_logs",
        db_index=True,
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="time_logs",
    )
    kind = models.CharField(
        max_length=10,
        choices=CHECKIN_TYPES,
        default="ARRIVAL",
        db_index=True,
    )
    ts = models.DateTimeField(default=timezone.now, db_index=True)

    # optional geo snapshot at check-in (renamed fields)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lon = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    class Meta:
        ordering = ("-ts",)
        indexes = [
            models.Index(fields=["business", "ts"], name="timelog_biz_ts_idx"),
            models.Index(fields=["user", "ts"], name="timelog_user_ts_idx"),
            models.Index(fields=["location", "ts"], name="timelog_loc_ts_idx"),
        ]

    def __str__(self):
        return f"{self.ts:%Y-%m-%d %H:%M} {self.user} {self.kind}"

# ---------------------------------------------------------------------
# Attendance policy (defaults)
# ---------------------------------------------------------------------
DEFAULT_OPENING_HOUR = time(8, 0, 0)  # 08:00
LATE_DEDUCT_PER_30  = _mwk(3000)
EARLY_BONUS_PER_30  = _mwk(5000)
WEEKEND_BONUS       = _mwk(10000)

@dataclass
class AttendanceOutcome:
    minutes_late: int = 0
    minutes_early: int = 0
    weekend_bonus: Decimal = Decimal(0)
    late_deduction: Decimal = Decimal(0)
    early_bonus: Decimal = Decimal(0)

    @property
    def net_adjustment(self) -> Decimal:
        return self.early_bonus + self.weekend_bonus - self.late_deduction

def compute_attendance_outcome(at_ts: datetime, kind: str) -> AttendanceOutcome:
    """
    Compute rewards/penalties for a given ARRIVAL log timestamp.
    Only ARRIVAL generates adjustments.
    """
    if kind != "ARRIVAL":
        return AttendanceOutcome()

    local = timezone.localtime(at_ts)
    opening = local.replace(
        hour=DEFAULT_OPENING_HOUR.hour,
        minute=DEFAULT_OPENING_HOUR.minute,
        second=0,
        microsecond=0,
    )

    # Weekend?
    is_weekend = local.weekday() >= 5  # 5=Sat, 6=Sun
    outcome = AttendanceOutcome()

    if is_weekend:
        outcome.weekend_bonus = WEEKEND_BONUS
        return outcome

    delta = local - opening
    if delta.total_seconds() > 0:
        # Late: charge per started 30-min block
        mins = int((delta.total_seconds() + 59) // 60)     # ceil to minute
        blocks = (mins + 29) // 30                         # ceil to 30-min blocks
        outcome.minutes_late = mins
        outcome.late_deduction = LATE_DEDUCT_PER_30 * blocks
    else:
        # Early: reward per started 30-min block
        mins = int((-delta.total_seconds() + 59) // 60)
        blocks = (mins + 29) // 30
        outcome.minutes_early = mins
        outcome.early_bonus = EARLY_BONUS_PER_30 * blocks

    return outcome

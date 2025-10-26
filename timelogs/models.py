# timelogs/models.py
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.db.models import Sum, F, ExpressionWrapper, DurationField

class Location(models.Model):
    business = models.ForeignKey("tenants.Business", on_delete=models.CASCADE)
    name = models.CharField(max_length=120, default="Main")
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)
    radius_m = models.PositiveIntegerField(default=60)  # editable by MANAGER
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

class TimeLog(models.Model):
    """One shift/session per agent per day (or per arrivalâ†’leave)."""
    agent = models.ForeignKey("agents.Agent", on_delete=models.CASCADE)
    business = models.ForeignKey("tenants.Business", on_delete=models.CASCADE)
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    note = models.CharField(max_length=240, blank=True)

    @property
    def work_minutes(self):
        secs = self.segments.filter(in_range=True, ended_at__isnull=False)\
               .aggregate(s=Sum(ExpressionWrapper(F("ended_at")-F("started_at"), output_field=DurationField())))["s"]
        return (secs.total_seconds() // 60) if secs else 0

    @property
    def out_minutes(self):
        secs = self.segments.filter(in_range=False, ended_at__isnull=False)\
               .aggregate(s=Sum(ExpressionWrapper(F("ended_at")-F("started_at"), output_field=DurationField())))["s"]
        return (secs.total_seconds() // 60) if secs else 0

class TimeLogSegment(models.Model):
    """Pieces that flip between in-range (work) and out-of-range (paused)."""
    timelog = models.ForeignKey(TimeLog, on_delete=models.CASCADE, related_name="segments")
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    in_range = models.BooleanField(default=False)
    source = models.CharField(max_length=16, default="gps")  # gps/manual



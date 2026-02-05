from django.db import models
from django.conf import settings


class Business(models.Model):
    """Business model - imported from tenants.models for compatibility."""
    name = models.CharField(max_length=255)
    business_kind = models.CharField(max_length=50, default='retail')
    
    class Meta:
        managed = False
        db_table = 'tenants_business'


class Store(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    geofence_radius_m = models.PositiveIntegerField(default=60)  # managers set


class AgentAssignment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    store = models.ForeignKey(Store, on_delete=models.CASCADE)
    active = models.BooleanField(default=True)

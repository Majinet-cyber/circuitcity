# audit/models.py
from django.db import models

class AuditLog(models.Model):
    business = models.ForeignKey("tenants.Business", on_delete=models.CASCADE, db_index=True)
    user = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL)
    entity = models.CharField(max_length=64)       # e.g. "InventoryItem"
    entity_id = models.CharField(max_length=64)    # pk/identifier
    action = models.CharField(max_length=64)       # e.g. INVENTORY_CREATE
    message = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    ua = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["business", "entity", "entity_id", "action"])]
        ordering = ["-created_at"]

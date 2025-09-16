# tenants/tenant.py
from threading import local
from django.db import models
from django.conf import settings

_local = local()

def set_current_business_id(biz_id: int | None):
    _local.biz_id = biz_id

def get_current_business_id():
    return getattr(_local, "biz_id", None)

class TenantQuerySet(models.QuerySet):
    def for_current_business(self):
      biz_id = get_current_business_id()
      if biz_id:
          return self.filter(business_id=biz_id)
      # If no business is set, return empty queryset to avoid leaks.
      return self.none()

class TenantManager(models.Manager):
    def get_queryset(self):
        qs = super().get_queryset()
        biz_id = get_current_business_id()
        return qs.filter(business_id=biz_id) if biz_id else qs.none()

class BusinessScopedModel(models.Model):
    """
    Base for all tenant-scoped tables.
    """
    business = models.ForeignKey("tenants.Business", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s")

    objects = TenantManager()         # always scoped
    all_objects = models.Manager()    # only use in admin tasks/migrations

    class Meta:
        abstract = True
        indexes = [models.Index(fields=["business"])]

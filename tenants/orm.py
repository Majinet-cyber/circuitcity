# tenants/orm.py
from django.db import models
from tenants.locals import get_current_business

class TenantQuerySet(models.QuerySet):
    def for_current(self):
        biz = get_current_business()
        return self.filter(business=biz) if biz else self.none()

class TenantManager(models.Manager):
    def get_queryset(self):
        qs = super().get_queryset()
        biz = get_current_business()
        return qs.filter(business=biz) if biz else qs.none()

class TenantOwned(models.Model):
    business = models.ForeignKey("tenants.Business", on_delete=models.CASCADE, db_index=True)
    objects = TenantManager.from_queryset(TenantQuerySet)()

    class Meta:
        abstract = True



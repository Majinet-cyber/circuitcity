from decimal import Decimal

from django.db import models


class BusinessSetting(models.Model):
    merchant_commission_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("1.00"),
    )
    manager_commission_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("3.00"),
    )
    loan_multiplier = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("2.50"),
    )
    spin_enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Business setting"
        verbose_name_plural = "Business settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "TengaSale business settings"

from django.db import models
from django.conf import settings

class Forecast(models.Model):
    product = models.ForeignKey("inventory.Product", on_delete=models.CASCADE, null=True, blank=True)
    date = models.DateField()
    predicted_units = models.IntegerField()
    predicted_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("product", "date")
        ordering = ["date"]

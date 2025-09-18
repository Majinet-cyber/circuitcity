# inventory/models.py
class InventoryRebalancePlan(models.Model):
    created_at   = models.DateTimeField(auto_now_add=True)
    created_by   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    sku          = models.ForeignKey('Product', on_delete=models.PROTECT)
    from_business= models.ForeignKey('tenants.Business', related_name='+', on_delete=models.PROTECT)
    to_business  = models.ForeignKey('tenants.Business', related_name='+', on_delete=models.PROTECT)
    quantity     = models.PositiveIntegerField()
    status       = models.CharField(max_length=20, default='draft')  # draft|approved|in_transit|done|cancelled

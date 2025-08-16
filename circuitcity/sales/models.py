# sales/models.py
from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from inventory.models import InventoryItem, Location

User = get_user_model()


class Sale(models.Model):
    """
    Created when an InventoryItem is sold on credit.
    """
    item            = models.OneToOneField(InventoryItem, on_delete=models.PROTECT, related_name="sale")
    agent           = models.ForeignKey(User, on_delete=models.PROTECT, related_name="sales")
    location        = models.ForeignKey(Location, on_delete=models.PROTECT)
    sold_at         = models.DateField()
    price           = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    commission_pct  = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                          validators=[MinValueValidator(0), MaxValueValidator(100)])
    # Phase 5: index for fast dashboards / recents
    created_at      = models.DateTimeField(default=timezone.now, db_index=True, editable=False)

    class Meta:
        indexes = [
            models.Index(fields=["created_at"], name="sale_created_at_idx"),
            models.Index(fields=["sold_at"], name="sale_sold_at_idx"),
            models.Index(fields=["location", "created_at"], name="sale_loc_created_idx"),
            models.Index(fields=["agent", "created_at"], name="sale_agent_created_idx"),
        ]
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(check=models.Q(price__gte=0), name="sale_price_nonneg"),
            models.CheckConstraint(check=models.Q(commission_pct__gte=0) & models.Q(commission_pct__lte=100),
                                   name="sale_commission_pct_0_100"),
        ]

    @property
    def commission_amount(self):
        return (self.price * self.commission_pct) / 100

    def __str__(self):
        return f"Sale #{self.pk} - item {self.item_id}"

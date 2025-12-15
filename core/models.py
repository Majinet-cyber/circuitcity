# core/models.py
from __future__ import annotations

from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models

if TYPE_CHECKING:
    from tenants.models import Business
    from inventory.models import Location

User = get_user_model()

# -----------------------------------------------------------------------------
# Cross-app imports: Use string FKs to avoid import-time dependencies
# -----------------------------------------------------------------------------
# Business and Location are referenced via string foreign keys:
# - Business: "tenants.Business"
# - Location: "inventory.Location"


# -----------------------------------------------------------------------------
# Mixins
# -----------------------------------------------------------------------------
class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        abstract = True


# -----------------------------------------------------------------------------
# Exchange Rate (for MWK <-> USD conversion)
# -----------------------------------------------------------------------------
class ExchangeRate(TimeStampedModel):
    """
    Singleton model storing the global MWK→USD exchange rate.
    Only one row should exist (enforced by unique_together on base/quote).
    Rate represents: 1 USD = mwk_per_usd MWK (e.g., if 1 USD = 1750 MWK, mwk_per_usd = 1750.00)
    """
    base = models.CharField(max_length=3, default="MWK", help_text="Base currency (locked to MWK)")
    quote = models.CharField(max_length=3, default="USD", help_text="Quote currency (locked to USD)")
    mwk_per_usd = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Exchange rate: 1 USD = mwk_per_usd MWK (e.g., 1750.00 means 1 USD = 1750 MWK)"
    )
    updated_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="exchange_rate_updates",
        help_text="User who last updated this rate"
    )

    class Meta:
        db_table = "core_exchangerate"
        unique_together = [["base", "quote"]]
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"1 {self.quote} = {self.mwk_per_usd} {self.base}"

    @classmethod
    def get_current_rate(cls) -> Optional["ExchangeRate"]:
        """Get the current exchange rate (singleton)."""
        return cls.objects.filter(base="MWK", quote="USD").first()

    @classmethod
    def get_rate_value(cls) -> Optional[Decimal]:
        """Get the current mwk_per_usd value as Decimal, or None if no rate is set."""
        rate_obj = cls.get_current_rate()
        return rate_obj.mwk_per_usd if rate_obj else None

    def save(self, *args, **kwargs):
        """Ensure base and quote are always MWK and USD."""
        self.base = "MWK"
        self.quote = "USD"
        super().save(*args, **kwargs)

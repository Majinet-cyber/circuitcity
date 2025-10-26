from django.db import models
from django.conf import settings

# ============================
# Phase 4 â€” Data & Forecasting
# ============================

class DailyKPI(models.Model):
    """
    Per (store_id, product, day) aggregates used as a lightweight feature store.
    store_id is kept as a plain integer to avoid coupling to a specific Store model.
    """
    store_id = models.IntegerField(db_index=True, null=True, blank=True)
    product = models.ForeignKey("inventory.Product", on_delete=models.CASCADE)
    d = models.DateField()
    units = models.FloatField(default=0)
    revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    profit = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["store_id", "product", "d"], name="uniq_dkpi_storeid_product_day")
        ]
        indexes = [
            models.Index(fields=["store_id", "product"]),
            models.Index(fields=["d"]),
        ]

    def __str__(self):
        return f"DailyKPI(store_id={self.store_id}, product={self.product_id}, d={self.d}, units={self.units})"


class ForecastRun(models.Model):
    """
    A run groups forecast items (e.g., one nightly run).
    """
    created_at = models.DateTimeField(auto_now_add=True)
    algo = models.CharField(max_length=30, default="ema_weekday")
    horizon_days = models.PositiveSmallIntegerField(default=14)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"ForecastRun(id={self.id}, algo={self.algo}, horizon={self.horizon_days}, at={self.created_at:%Y-%m-%d})"


class ForecastItem(models.Model):
    """
    Per (store_id, product, date) forecast values for the coming horizon.
    """
    run = models.ForeignKey(ForecastRun, on_delete=models.CASCADE, related_name="items")
    store_id = models.IntegerField(db_index=True, null=True, blank=True)
    product = models.ForeignKey("inventory.Product", on_delete=models.CASCADE)
    date = models.DateField()
    yhat = models.FloatField()               # point forecast (units)
    ylo  = models.FloatField(null=True, blank=True)  # P20 (or similar) bound
    yhi  = models.FloatField(null=True, blank=True)  # P80 (or similar) bound
    mape = models.FloatField(null=True, blank=True)  # backtest quality if available

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["run", "store_id", "product", "date"], name="uniq_forecastitem_run_scope_day")
        ]
        indexes = [
            models.Index(fields=["store_id", "product"]),
            models.Index(fields=["date"]),
        ]
        ordering = ["date"]

    def __str__(self):
        return f"ForecastItem(store_id={self.store_id}, product={self.product_id}, date={self.date}, yhat={self.yhat})"


class InventoryPolicy(models.Model):
    """
    Policy parameters per (store_id, product) used to compute ROP, safety stock, etc.
    """
    store_id = models.IntegerField(db_index=True, null=True, blank=True)
    product = models.ForeignKey("inventory.Product", on_delete=models.CASCADE)
    lead_time_days = models.FloatField(default=7)
    service_level_z = models.FloatField(default=1.28)  # ~90%
    safety_factor = models.FloatField(default=1.0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["store_id", "product"], name="uniq_invpolicy_storeid_product")
        ]
        indexes = [
            models.Index(fields=["store_id", "product"]),
        ]

    def __str__(self):
        return f"InventoryPolicy(store_id={self.store_id}, product={self.product_id}, L={self.lead_time_days})"


class ReorderAdvice(models.Model):
    """
    Snapshot advice row produced by the nightly forecast/policy engine.
    """
    store_id = models.IntegerField(db_index=True, null=True, blank=True)
    product = models.ForeignKey("inventory.Product", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    reorder_point = models.FloatField()
    recommend_qty = models.FloatField()
    reason = models.CharField(max_length=120, default="cover_lead_time_plus_buffer")

    class Meta:
        indexes = [
            models.Index(fields=["store_id", "product"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return (f"ReorderAdvice(store_id={self.store_id}, product={self.product_id}, "
                f"ROP={self.reorder_point}, qty={self.recommend_qty})")


# ==================================
# Phase 4.2 â€” Notifications & Emails
# ==================================

class Notification(models.Model):
    """
    In-app (and optionally emailed) notifications for users.
    """
    KIND_CHOICES = (
        ("low_stock", "Low Stock"),
        ("nudge", "Nudge"),
        ("report", "Report"),
    )
    SEVERITY_CHOICES = (
        ("info", "info"),
        ("warn", "warn"),
        ("crit", "crit"),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    kind = models.CharField(max_length=40, choices=KIND_CHOICES)
    title = models.CharField(max_length=140)
    body = models.TextField()
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default="info")
    meta = models.JSONField(default=dict, blank=True)
    sent_via = models.JSONField(default=list)  # e.g. ["inapp","email"]
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["kind"]),
            models.Index(fields=["severity"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Notification(user={self.user_id}, kind={self.kind}, title={self.title[:24]!r})"


class EmailReportLog(models.Model):
    """
    Audit trail for weekly (or other) email reports.
    """
    report_key = models.CharField(max_length=40)  # e.g., "weekly-2025W35-store3"
    sent_to = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["report_key"]),
            models.Index(fields=["-created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"EmailReportLog({self.report_key} -> {self.sent_to})"


# =======================
# Phase 5 â€” Gamification
# =======================

class Badge(models.Model):
    """
    Static badge catalog (seeded via management command).
    """
    code = models.SlugField(primary_key=True)
    name = models.CharField(max_length=60)
    emoji = models.CharField(max_length=8, default="ðŸ…")
    description = models.CharField(max_length=200)
    rule = models.JSONField()  # e.g., {"metric":"units","window":"week","gte":30}

    def __str__(self):
        return f"{self.emoji} {self.name} ({self.code})"


class AgentBadge(models.Model):
    """
    Awarded badges for an agent (map to your AUTH_USER instead of inventory.Agent).
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE)
    awarded_at = models.DateTimeField(auto_now_add=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "badge"], name="uniq_user_badge_once")
        ]
        indexes = [
            models.Index(fields=["user", "-awarded_at"]),
        ]
        ordering = ["-awarded_at"]

    def __str__(self):
        return f"AgentBadge(user={self.user_id}, badge={self.badge_id})"


class LeaderboardSnapshot(models.Model):
    """
    Snapshot of leaderboard standings for a period & metric.
    """
    period_start = models.DateField()
    period_end   = models.DateField()
    scope = models.CharField(max_length=12, choices=[("week", "week"), ("month", "month")])
    metric = models.CharField(max_length=12, choices=[("units", "units"), ("revenue", "revenue"), ("profit", "profit")])
    data = models.JSONField()  # [{user_id, name, units, revenue, profit, rank}]
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["scope", "metric"]),
            models.Index(fields=["-created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"LeaderboardSnapshot({self.scope} {self.metric} {self.period_start}â€“{self.period_end})"


# ==================================================
# Legacy/Simple Forecast table (kept for compatibility)
# ==================================================

class Forecast(models.Model):
    """
    Simple flat forecast table you already had: one row per (product, date).
    Kept as-is for compatibility; new features use ForecastRun/ForecastItem.
    """
    product = models.ForeignKey("inventory.Product", on_delete=models.CASCADE, null=True, blank=True)
    date = models.DateField()
    predicted_units = models.IntegerField()
    predicted_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product", "date"], name="uniq_forecast_product_date")
        ]
        ordering = ["date"]
        indexes = [
            models.Index(fields=["product", "date"]),
        ]

    def __str__(self):
        return f"Forecast(product={self.product_id}, date={self.date}, units={self.predicted_units})"


# =====================================================
# Currency Setting (singleton) â€” for display & FX rates
# =====================================================

class CurrencySetting(models.Model):
    """
    Singleton for currency config and cached FX rates.

    - base_currency: currency your DB amounts are stored in (default MWK)
    - display_currency: what to show in UI (admin can change)
    - rates: mapping where value is how many DISPLAY units one BASE unit buys, e.g.
             if base=MWK and display=USD, rates["USD"] = 0.00059
    """
    base_currency = models.CharField(max_length=8, default="MWK")
    display_currency = models.CharField(max_length=8, default="MWK")
    rates = models.JSONField(default=dict, blank=True)  # {"USD": 0.00059, "ZAR": 0.0103, ...}
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Currency Setting"
        verbose_name_plural = "Currency Setting"

    def __str__(self):
        return f"Currency(base={self.base_currency}, display={self.display_currency})"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj



from __future__ import annotations

from decimal import Decimal

from django.db import models


class BusinessHealthCheck(models.Model):
    class Status(models.TextChoices):
        NOT_ENOUGH_DATA = "not_enough_data", "Not enough data"
        BALANCED = "balanced", "Books Balanced"
        WINNING = "winning", "You Are Winning"
        WARNING_MISSING_MONEY = "warning_missing_money", "Warning: Missing Money"
        WARNING_COSTS = "warning_costs", "Warning: Costs Not Recorded"
        WARNING_RECEIVABLES = "warning_receivables", "Warning: Receivables Too High"
        DANGER = "danger", "Books Not Balanced"

    business = models.ForeignKey(
        "tenants.Business",
        on_delete=models.CASCADE,
        related_name="business_health_checks",
    )
    date = models.DateField(db_index=True)

    opening_cash = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    opening_stock_value = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    opening_receivables = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    current_cash = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    current_stock_value = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    current_receivables = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    sales_revenue = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    cost_of_goods_sold = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    recorded_expenses = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    capital_injection = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    owner_withdrawals = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    loans_received = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    loan_repayments = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    expected_value = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    actual_value = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    variance = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    tolerance = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("1000.00"))

    score = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.NOT_ENOUGH_DATA,
        db_index=True,
    )
    recommendation = models.TextField(blank=True, default="")
    badges = models.JSONField(default=list, blank=True)
    actions = models.JSONField(default=list, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("business", "date")]
        ordering = ["-date", "-updated_at"]
        indexes = [
            models.Index(fields=["business", "date"]),
            models.Index(fields=["business", "status", "date"]),
        ]

    def __str__(self) -> str:
        return f"{self.business_id} {self.date} {self.status} {self.variance}"

    @property
    def variance_abs(self) -> Decimal:
        return abs(self.variance or Decimal("0.00"))

    @property
    def status_color(self) -> str:
        if self.status in {self.Status.BALANCED, self.Status.WINNING}:
            return "green"
        if self.status in {
            self.Status.WARNING_MISSING_MONEY,
            self.Status.WARNING_COSTS,
            self.Status.WARNING_RECEIVABLES,
        }:
            return "amber"
        if self.status == self.Status.DANGER:
            return "red"
        return "slate"

    @property
    def status_label(self) -> str:
        labels = {
            self.Status.NOT_ENOUGH_DATA: "Not enough data to reconcile yet",
            self.Status.BALANCED: "Books Balanced",
            self.Status.WINNING: "You Are Winning",
            self.Status.WARNING_MISSING_MONEY: "Warning: Missing Money",
            self.Status.WARNING_COSTS: "Warning: Costs Not Recorded",
            self.Status.WARNING_RECEIVABLES: "Warning: Receivables Too High",
            self.Status.DANGER: "Books Not Balanced",
        }
        return labels.get(self.status, self.get_status_display())

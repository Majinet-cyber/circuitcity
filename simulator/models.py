# simulator/models.py
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class Scenario(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="scenarios",
    )
    name = models.CharField(max_length=120)

    # --- Core business knobs (match forms & logic.py) ---
    baseline_monthly_units = models.PositiveIntegerField(default=0)   # demand per month
    avg_unit_price = models.FloatField(default=0.0)                   # price per unit (MWK)
    variable_cost_pct = models.FloatField(default=0.0)                # % of price (0..100)
    monthly_fixed_costs = models.FloatField(default=0.0)              # fixed opex per month (MWK)
    monthly_growth_pct = models.FloatField(default=0.0)               # % demand growth per month (0..100)
    months = models.PositiveIntegerField(default=12)                  # months to simulate (1..60 rec.)

    # --- Optional finance knobs (used by logic.py if present) ---
    tax_rate_pct = models.FloatField(default=0.0)                     # % of positive operating profit
    opening_cash = models.FloatField(default=0.0)                     # starting cash balance (MWK)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["owner", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.name}"


class SimulationRun(models.Model):
    scenario = models.ForeignKey(
        Scenario,
        on_delete=models.CASCADE,
        related_name="runs",
    )
    created_at = models.DateTimeField(default=timezone.now)

    # New canonical field used by views/helpers
    results_json = models.JSONField(default=dict, blank=True, null=True)

    # Legacy field kept for backward compatibility (read fallback)
    # _get_results_json() in views will read this if results_json is empty.
    result_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["scenario", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"Run #{self.id} â€” {self.scenario.name}"



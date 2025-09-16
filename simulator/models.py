from django.conf import settings
from django.db import models
from django.utils import timezone

class Scenario(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="scenarios")
    name = models.CharField(max_length=120)

    # Demand / pricing
    demand_growth_pct = models.FloatField(default=0)     # % per day (compound)
    price_change_pct = models.FloatField(default=0)      # % applied to base_price once at t0
    base_price = models.FloatField(default=100.0)        # NEW: baseline selling price per unit
    unit_cost = models.FloatField(default=60.0)          # NEW: COGS per unit

    # Inventory policy
    lead_time_days = models.PositiveIntegerField(default=7)
    reorder_point = models.PositiveIntegerField(default=10)
    initial_stock = models.PositiveIntegerField(default=50)
    horizon_days = models.PositiveIntegerField(default=30)

    # P&L & cash flow knobs
    op_ex_pct_of_revenue = models.FloatField(default=10.0)  # NEW: % of revenue as operating expense
    tax_rate_pct = models.FloatField(default=25.0)          # NEW: corporate tax on positive operating profit
    ar_days = models.PositiveIntegerField(default=7)         # NEW: AR collection lag
    ap_days = models.PositiveIntegerField(default=7)         # NEW: AP payment lag
    opening_cash = models.FloatField(default=0.0)            # NEW: opening cash balance

    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.name

class SimulationRun(models.Model):
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name="runs")
    created_at = models.DateTimeField(default=timezone.now)
    result_json = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"Run #{self.id} — {self.scenario.name}"

"""
PHASE 6: Liquor Agent Stock Assignment Models
Enables managers to assign bottles to specific agents and track individual agent performance.
"""
from __future__ import annotations

from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class LiquorStockAssignment(models.Model):
    """
    Assigns specific bottles/products to agents for selling.
    Managers use this to distribute stock among sales agents.
    """

    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("SOLD_OUT", "Sold Out"),
        ("RETURNED", "Returned to Stock"),
        ("RECONCILED", "Reconciled"),
    ]

    business = models.ForeignKey("tenants.Business", on_delete=models.CASCADE, related_name="liquor_stock_assignments")
    agent = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="liquor_stock_assigned",
        help_text="Agent who is assigned this stock",
    )
    product = models.ForeignKey("inventory.MerchProduct", on_delete=models.PROTECT, related_name="liquor_assignments")

    # Assignment details
    bottles_assigned = models.PositiveIntegerField(default=0, help_text="Number of bottles assigned to agent")
    bottles_sold = models.PositiveIntegerField(default=0, help_text="Number of bottles sold by agent")
    bottles_returned = models.PositiveIntegerField(default=0, help_text="Number of bottles returned unsold")

    # Pricing (for reporting)
    unit_cost_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"), help_text="Cost price per bottle at assignment time"
    )
    unit_sell_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"), help_text="Expected selling price per bottle"
    )

    # Status
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="ACTIVE", db_index=True)

    # Timestamps
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="liquor_assignments_made",
        help_text="Manager who made this assignment",
    )
    reconciled_at = models.DateTimeField(null=True, blank=True, help_text="When this assignment was reconciled")
    reconciled_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="liquor_assignments_reconciled"
    )

    # Notes
    notes = models.TextField(blank=True, default="", help_text="Optional notes about this assignment")

    class Meta:
        ordering = ["-assigned_at"]
        indexes = [
            models.Index(fields=["business", "agent", "-assigned_at"]),
            models.Index(fields=["business", "status"]),
            models.Index(fields=["agent", "status", "-assigned_at"]),
        ]

    def __str__(self):
        return f"{self.agent.username} - {self.product.name} ({self.bottles_assigned} bottles)"

    @property
    def bottles_remaining(self):
        """Calculate how many bottles are still with the agent"""
        return self.bottles_assigned - self.bottles_sold - self.bottles_returned

    @property
    def total_cost(self):
        """Total cost of assigned bottles"""
        return self.unit_cost_price * Decimal(str(self.bottles_assigned))

    @property
    def total_expected_revenue(self):
        """Expected revenue if all bottles are sold"""
        return self.unit_sell_price * Decimal(str(self.bottles_assigned))

    @property
    def actual_revenue(self):
        """Actual revenue from sold bottles"""
        return self.unit_sell_price * Decimal(str(self.bottles_sold))

    @property
    def expected_profit(self):
        """Expected profit from sold bottles"""
        return self.actual_revenue - (self.unit_cost_price * Decimal(str(self.bottles_sold)))


class LiquorDailyReconciliation(models.Model):
    """
    Daily reconciliation report for an agent.
    Tracks all assignments, sales, and returns for a specific day.
    """

    business = models.ForeignKey("tenants.Business", on_delete=models.CASCADE, related_name="liquor_reconciliations")
    agent = models.ForeignKey(User, on_delete=models.PROTECT, related_name="liquor_reconciliations")
    date = models.DateField(default=timezone.now, db_index=True)

    # Metrics
    total_bottles_assigned = models.PositiveIntegerField(default=0, help_text="Total bottles assigned today")
    total_bottles_sold = models.PositiveIntegerField(default=0, help_text="Total bottles sold today")
    total_bottles_returned = models.PositiveIntegerField(default=0, help_text="Total bottles returned today")
    total_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_profit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    # Reconciliation status
    is_reconciled = models.BooleanField(default=False, db_index=True)
    reconciled_at = models.DateTimeField(null=True, blank=True)
    reconciled_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="liquor_daily_reconciliations_done"
    )

    # Notes
    notes = models.TextField(blank=True, default="")

    class Meta:
        unique_together = ("business", "agent", "date")
        ordering = ["-date", "agent"]
        indexes = [
            models.Index(fields=["business", "-date"]),
            models.Index(fields=["agent", "-date"]),
            models.Index(fields=["business", "date", "is_reconciled"]),
        ]

    def __str__(self):
        return f"{self.agent.username} - {self.date} ({'Reconciled' if self.is_reconciled else 'Pending'})"

    @property
    def sell_through_rate(self):
        """Percentage of assigned bottles that were sold"""
        if self.total_bottles_assigned == 0:
            return Decimal("0.00")
        return (Decimal(str(self.total_bottles_sold)) / Decimal(str(self.total_bottles_assigned))) * Decimal("100.00")


class LiquorAgentTarget(models.Model):
    """
    Monthly sales targets for liquor agents.
    Managers can set targets to motivate agents.
    """

    business = models.ForeignKey("tenants.Business", on_delete=models.CASCADE, related_name="liquor_agent_targets")
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name="liquor_targets")

    # Target period
    month = models.DateField(help_text="First day of the target month")

    # Targets
    target_revenue = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Target revenue for the month",
    )
    target_bottles = models.PositiveIntegerField(default=0, help_text="Target number of bottles to sell")

    # Actual performance (computed periodically)
    actual_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    actual_bottles = models.PositiveIntegerField(default=0)

    # Metadata
    set_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="liquor_targets_set"
    )
    set_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("business", "agent", "month")
        ordering = ["-month", "agent"]
        indexes = [
            models.Index(fields=["business", "-month"]),
            models.Index(fields=["agent", "-month"]),
        ]

    def __str__(self):
        return f"{self.agent.username} - {self.month.strftime('%B %Y')}"

    @property
    def revenue_progress_pct(self):
        """Percentage of revenue target achieved"""
        if self.target_revenue == 0:
            return Decimal("0.00")
        return (self.actual_revenue / self.target_revenue) * Decimal("100.00")

    @property
    def bottles_progress_pct(self):
        """Percentage of bottles target achieved"""
        if self.target_bottles == 0:
            return Decimal("0.00")
        return (Decimal(str(self.actual_bottles)) / Decimal(str(self.target_bottles))) * Decimal("100.00")

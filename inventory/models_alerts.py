# inventory/models_alerts.py
"""
Alert system models for real-time notifications.
"""
from django.db import models
from django.utils import timezone
from tenants.models import Business
from inventory.models import Location


class Alert(models.Model):
    """
    Alert/notification for business events.
    Types: out_of_stock, low_stock, top_agent, payment_received, etc.
    """

    ALERT_TYPE_CHOICES = [
        ("out_of_stock", "Out of Stock"),
        ("low_stock", "Low Stock"),
        ("top_agent", "Top Agent"),
        ("high_sales", "High Sales Day"),
        ("payment_received", "Payment Received"),
        ("new_customer", "New Customer"),
        ("system", "System Alert"),
    ]

    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("urgent", "Urgent"),
    ]

    business = models.ForeignKey(
        "tenants.Business",
        on_delete=models.CASCADE,
        related_name="alerts",
    )

    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alerts",
    )

    alert_type = models.CharField(
        max_length=30,
        choices=ALERT_TYPE_CHOICES,
        db_index=True,
    )

    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default="medium",
    )

    title = models.CharField(max_length=200)
    message = models.TextField()

    # Optional metadata (JSON)
    meta = models.JSONField(default=dict, blank=True)

    # Link to related object
    related_object_id = models.IntegerField(null=True, blank=True)
    related_object_type = models.CharField(max_length=50, blank=True)  # e.g., 'product', 'agent', 'sale'

    # Status
    is_read = models.BooleanField(default=False, db_index=True)
    is_dismissed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "is_read", "-created_at"]),
            models.Index(fields=["business", "alert_type", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.get_alert_type_display()}: {self.title}"

    def mark_as_read(self):
        """Mark this alert as read."""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])

    @classmethod
    def create_out_of_stock_alert(cls, business, product_name, location=None):
        """Create an out of stock alert."""
        return cls.objects.create(
            business=business,
            location=location,
            alert_type="out_of_stock",
            priority="high",
            title=f"{product_name} is out of stock",
            message=f"The product '{product_name}' has run out of stock and needs restocking.",
            meta={"product_name": product_name},
        )

    @classmethod
    def create_low_stock_alert(cls, business, product_name, quantity, threshold, location=None):
        """Create a low stock alert."""
        return cls.objects.create(
            business=business,
            location=location,
            alert_type="low_stock",
            priority="medium",
            title=f"Low stock: {product_name}",
            message=f"The product '{product_name}' has only {quantity} units left (threshold: {threshold}).",
            meta={"product_name": product_name, "quantity": quantity, "threshold": threshold},
        )

    @classmethod
    def create_top_agent_alert(cls, business, agent_name, period="week", sales_count=0, revenue=0):
        """Create a top agent alert."""
        return cls.objects.create(
            business=business,
            alert_type="top_agent",
            priority="low",
            title=f"🏆 {agent_name} is the top agent this {period}!",
            message=f"{agent_name} has made {sales_count} sales totaling {revenue:,.0f} this {period}.",
            meta={"agent_name": agent_name, "period": period, "sales_count": sales_count, "revenue": float(revenue)},
        )

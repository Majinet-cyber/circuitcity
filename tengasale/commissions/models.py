from django.conf import settings
from django.db import models


class Commission(models.Model):
    ROLE_MERCHANT = "merchant"
    ROLE_MANAGER = "manager"

    ROLE_CHOICES = [
        (ROLE_MERCHANT, "Merchant"),
        (ROLE_MANAGER, "Manager"),
    ]

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_PAID = "paid"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_PAID, "Paid"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="commissions")
    application = models.ForeignKey(
        "applications.FinancingApplication",
        on_delete=models.CASCADE,
        related_name="commissions",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    commission_percent = models.DecimalField(max_digits=5, decimal_places=2)
    sale_amount = models.DecimalField(max_digits=14, decimal_places=2)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["application", "user", "role"],
                name="unique_commission_per_application_user_role",
            ),
        ]

    def __str__(self):
        return f"{self.user} {self.role} commission for {self.application}"

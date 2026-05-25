from decimal import Decimal

from django.conf import settings
from django.db import models


def default_small_rewards():
    return [100, 500, 1000, 2500, 5000, 10000]


class SpinWallet(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="spin_wallet")
    available_spins = models.PositiveIntegerField(default=0)
    total_spins_earned = models.PositiveIntegerField(default=0)
    total_spins_used = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.user.username} spin wallet"


class SpinGrant(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="spin_grants")
    application = models.ForeignKey(
        "applications.FinancingApplication",
        on_delete=models.CASCADE,
        related_name="spin_grants",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["application", "user"], name="unique_spin_grant_per_application_user"),
        ]

    def __str__(self):
        return f"{self.user.username} spin for {self.application}"


class SpinReward(models.Model):
    TIER_SMALL = "small"
    TIER_MEDIUM = "medium"
    TIER_JACKPOT = "jackpot"

    TIER_CHOICES = [
        (TIER_SMALL, "Small"),
        (TIER_MEDIUM, "Medium"),
        (TIER_JACKPOT, "Jackpot"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="spin_rewards")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    spin_date = models.DateTimeField()
    reward_tier = models.CharField(max_length=20, choices=TIER_CHOICES)
    application = models.ForeignKey(
        "applications.FinancingApplication",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="spin_rewards",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-spin_date"]

    def __str__(self):
        return f"{self.user.username} won {self.amount}"


class SpinConfig(models.Model):
    is_enabled = models.BooleanField(default=True)
    small_rewards = models.JSONField(default=default_small_rewards)
    jackpot_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("50000.00"))
    jackpot_limit_per_week = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Spin config"
        verbose_name_plural = "Spin config"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "Spin & Win config"

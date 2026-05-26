from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    ROLE_MERCHANT = "merchant"
    ROLE_UNDERWRITER = "underwriter"
    ROLE_HQ = "hq"

    ROLE_CHOICES = [
        (ROLE_MERCHANT, "Merchant"),
        (ROLE_UNDERWRITER, "Underwriter"),
        (ROLE_HQ, "HQ"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, blank=True, null=True)
    phone_number = models.CharField(max_length=30, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.role or 'No role'}"

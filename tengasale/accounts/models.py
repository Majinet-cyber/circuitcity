from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ("", "No role assigned"),
        ("merchant", "Merchant"),
        ("underwriter", "Underwriter"),
        ("hq", "HQ"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, blank=True, default="")
    phone_number = models.CharField(max_length=30, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.role}"

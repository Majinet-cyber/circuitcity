from django.conf import settings
from django.db import models
from django.utils import timezone


def avatar_upload_to(instance, filename):
    return f"avatars/{instance.pk}/{filename}"


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    avatar = models.ImageField(upload_to=avatar_upload_to, blank=True, null=True)

    def __str__(self):
        return f"{self.user.get_username()} profile"


class PasswordResetCode(models.Model):
    """
    One-time password (OTP) for password reset.
    We store only a hash of the code; never the raw value.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="password_reset_codes",
    )
    code_hash = models.CharField(max_length=256)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    used = models.BooleanField(default=False)
    requester_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "expires_at", "used"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        status = "used" if self.used else "active"
        return f"ResetCode<{self.user_id}:{status} @ {self.created_at:%Y-%m-%d %H:%M:%S}>"

    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

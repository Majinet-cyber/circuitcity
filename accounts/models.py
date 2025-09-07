# accounts/models.py
from __future__ import annotations

from datetime import timedelta
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password
from django.db.models.signals import post_save
from django.dispatch import receiver


# -----------------------------
# Profile (avatar + settings)
# -----------------------------
def avatar_upload_to(instance: "Profile", filename: str) -> str:
    return f"avatars/{instance.user_id}/{filename}"


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    # Visual identity
    avatar = models.ImageField(upload_to=avatar_upload_to, blank=True, null=True)

    # Settings shown on the Settings · Profile page
    display_name = models.CharField(max_length=120, blank=True, default="")
    country      = models.CharField(max_length=80,  blank=True, default="")
    language     = models.CharField(max_length=80,  blank=True, default="English - United States")
    timezone     = models.CharField(max_length=80,  blank=True, default=settings.TIME_ZONE)

    class Meta:
        db_table = "accounts_profile"
        indexes = [
            models.Index(fields=["user"]),
        ]

    def __str__(self) -> str:
        return f"{self.user.get_username()} profile"

    @property
    def initials(self) -> str:
        """
        Initials fallback when no avatar is uploaded.
        """
        name = (self.display_name or self.user.get_full_name() or self.user.get_username() or "").strip()
        if not name:
            return ""
        parts = [p for p in name.replace("_", " ").split() if p]
        if not parts:
            return name[:2].upper()
        first = parts[0][0]
        second = parts[1][0] if len(parts) > 1 else ""
        return (first + second).upper()


# -------------------------------------
# Password reset one-time code (hashed)
# -------------------------------------
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
        db_table = "accounts_passwordresetcode"
        indexes = [
            models.Index(fields=["user", "expires_at", "used"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        status = "used" if self.used else "active"
        return f"ResetCode<{self.user_id}:{status} @ {self.created_at:%Y-%m-%d %H:%M:%S}>"

    # ---- Helpers ----
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def set_raw_code(self, raw_code: str) -> None:
        """Hash and store the raw OTP (do NOT store plaintext)."""
        self.code_hash = make_password(raw_code)

    def matches(self, raw_code: str) -> bool:
        """Constant-time check of provided code against stored hash."""
        return check_password(raw_code, self.code_hash)


# ------------------------------------
# Email OTP (login/verify/reset/2FA)
# ------------------------------------
class EmailOTP(models.Model):
    """
    Email-based OTP for actions like login/verify email/2FA.
    We store only a hash of the code; never the raw value.
    """
    email = models.EmailField(db_index=True)
    purpose = models.CharField(max_length=32, default="login", db_index=True)  # e.g. 'reset', 'verify', 'login'
    code_hash = models.CharField(max_length=256)  # compatible with Django's password hashers
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    requester_ip = models.GenericIPAddressField(null=True, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "accounts_emailotp"
        indexes = [
            models.Index(fields=["email", "purpose", "expires_at"]),
            models.Index(fields=["email", "purpose", "consumed_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        state = "used" if self.is_used else ("expired" if self.is_expired else "active")
        return f"EmailOTP<{self.email}:{self.purpose}:{state} @ {self.created_at:%Y-%m-%d %H:%M:%S}>"

    # ---- Helpers ----
    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_used(self) -> bool:
        return self.consumed_at is not None

    def set_raw_code(self, raw_code: str) -> None:
        """Hash and store the raw OTP (do NOT store plaintext)."""
        self.code_hash = make_password(raw_code)

    def matches(self, raw_code: str) -> bool:
        """Constant-time check of provided code against stored hash."""
        return check_password(raw_code, self.code_hash)


# ---------------------------------------------------------
# LoginSecurity: staged lockouts for brute force protection
# ---------------------------------------------------------
class LoginSecurity(models.Model):
    """
    Tracks staged lockouts to slow down credential stuffing/brute force.

    Policy implemented by callers via note_failure()/note_success():
      - Stage 0: after 3 failures -> lock for 5 minutes, advance to Stage 1
      - Stage 1: after 2 failures -> lock for 45 minutes, advance to Stage 2
      - Stage 2: after 2 failures -> hard_blocked (admin must unblock)

    Call .is_locked() to check current temporary lock or hard block.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="login_sec",
    )
    # 0 -> first tier, 1 -> second tier, 2 -> final tier
    stage = models.PositiveSmallIntegerField(default=0)
    fail_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    hard_blocked = models.BooleanField(default=False)

    class Meta:
        db_table = "accounts_loginsecurity"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["locked_until"]),
            models.Index(fields=["hard_blocked"]),
        ]

    def __str__(self) -> str:
        if self.hard_blocked:
            state = "HARD-BLOCKED"
        elif self.locked_until and self.locked_until > timezone.now():
            state = f"LOCKED until {self.locked_until:%Y-%m-%d %H:%M:%S}"
        else:
            state = "OK"
        return f"LoginSecurity<{self.user_id} stage={self.stage} fails={self.fail_count} {state}>"

    # ---- Lock/Fail logic ----
    def is_locked(self) -> bool:
        if self.hard_blocked:
            return True
        return bool(self.locked_until and self.locked_until > timezone.now())

    def note_failure(self) -> None:
        """
        Increment failure counters and apply staged lockouts.
        - Stage 0: 3 fails -> lock 5 min, move to Stage 1, reset counter
        - Stage 1: 2 fails -> lock 45 min, move to Stage 2, reset counter
        - Stage 2: 2 fails -> hard block
        """
        now = timezone.now()

        # If already in a locked or blocked state, don't mutate further
        if self.hard_blocked or (self.locked_until and self.locked_until > now):
            return

        self.fail_count += 1

        if self.stage == 0 and self.fail_count >= 3:
            self.locked_until = now + timedelta(minutes=5)
            self.stage = 1
            self.fail_count = 0
        elif self.stage == 1 and self.fail_count >= 2:
            self.locked_until = now + timedelta(minutes=45)
            self.stage = 2
            self.fail_count = 0
        elif self.stage == 2 and self.fail_count >= 2:
            self.hard_blocked = True

        self.save(update_fields=["fail_count", "locked_until", "stage", "hard_blocked"])

    def note_success(self) -> None:
        """
        Reset counters and locks on successful authentication (or after an admin reset).
        """
        self.stage = 0
        self.fail_count = 0
        self.locked_until = None
        self.hard_blocked = False
        self.save(update_fields=["stage", "fail_count", "locked_until", "hard_blocked"])


# ---------------------------------------------------
# Signals: auto-provision Profile & LoginSecurity
# ---------------------------------------------------
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def _ensure_user_sidecars(sender, instance, created, **kwargs):
    """
    Automatically create Profile and LoginSecurity records for new users.
    Safe to call multiple times; uses get_or_create.
    """
    if not instance:
        return
    Profile.objects.get_or_create(user=instance)
    LoginSecurity.objects.get_or_create(user=instance)

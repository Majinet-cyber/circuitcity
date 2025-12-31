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
# Profile (avatar + settings + role)
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

    # Settings shown on the Settings Â· Profile page
    display_name = models.CharField(max_length=120, blank=True, default="")
    country      = models.CharField(max_length=80,  blank=True, default="")
    language     = models.CharField(max_length=80,  blank=True, default="English - United States")
    timezone     = models.CharField(max_length=80,  blank=True, default=settings.TIME_ZONE)
    
    # Currency display preference
    display_currency = models.CharField(
        max_length=3,
        choices=[("MWK", "MWK"), ("USD", "USD")],
        default="MWK",
        help_text="Currency to display amounts in (MWK is base currency, USD is converted)"
    )

    # ---- Role flag (no need to replace AUTH_USER_MODEL) ----
    # Mark â€œmanagerâ€ users who can access CFO/approvals/etc.
    # Admins remain those with user.is_staff=True.
    is_manager   = models.BooleanField(default=False)
    
    # ---- Force password change (for temp passwords) ----
    force_password_change = models.BooleanField(
        default=False,
        help_text="If True, user must change password on next login.",
    )
    
    # ---- Email verification ----
    email_verified = models.BooleanField(
        default=False,
        help_text="If True, user's email address has been verified via OTP.",
    )

    class Meta:
        db_table = "accounts_profile"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["is_manager"]),
        ]

    def __str__(self) -> str:
        return f"{self.user.get_username()} profile"

    # ----- Convenience helpers -----
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

    @property
    def is_admin(self) -> bool:
        """Admins = Django staff/superusers."""
        u = getattr(self, "user", None)
        return bool(u and u.is_authenticated and u.is_staff)

    @property
    def is_agent(self) -> bool:
        """
        Agent = not admin and not manager.
        Use this to keep the agent UI clean (no CFO/Approvals/etc).
        """
        return not self.is_admin and not self.is_manager


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
    PURPOSE_CHOICES = [
        ("signup", "Signup"),
        ("login", "Login"),
        ("reset", "Password Reset"),
        ("2fa", "Two-Factor Authentication"),
    ]
    
    email = models.EmailField(db_index=True, help_text="Normalized lowercase email")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="email_otps",
        help_text="Optional user reference (for signup, user may not exist yet)",
    )
    purpose = models.CharField(
        max_length=32,
        choices=PURPOSE_CHOICES,
        default="login",
        db_index=True,
        help_text="Purpose of this OTP (signup, login, reset, 2fa)",
    )
    code_hash = models.CharField(max_length=256, help_text="Hashed OTP code (never store plaintext)")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0, help_text="Number of verification attempts")
    requester_ip = models.GenericIPAddressField(null=True, blank=True, help_text="IP address of requester")
    user_agent = models.TextField(null=True, blank=True, help_text="User agent string")
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "accounts_emailotp"
        indexes = [
            models.Index(fields=["email", "purpose", "-created_at"]),
            models.Index(fields=["email", "purpose", "consumed_at"]),
            models.Index(fields=["user", "purpose", "-created_at"]),
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


# -----------------------------
# Onboarding Profile (wizard goals & completion)
# -----------------------------
class OnboardingProfile(models.Model):
    """
    Tracks user goals selected during the signup wizard.
    Helps personalize the dashboard and track onboarding progress.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="onboarding_profile",
    )
    
    # Goals selected in Step 4
    goal_stop_theft = models.BooleanField(default=False, help_text="Stop theft and missing stock")
    goal_see_profit = models.BooleanField(default=False, help_text="See profit and losses clearly")
    goal_track_performance = models.BooleanField(default=False, help_text="Track agent performance and rankings")
    goal_move_off_notebooks = models.BooleanField(default=False, help_text="Move off hardcover notebooks")
    
    # Wizard completion tracking
    completed_at = models.DateTimeField(null=True, blank=True)
    wizard_version = models.CharField(max_length=20, default="v1", help_text="Wizard version for A/B testing")
    
    # Business context captured during onboarding
    first_business_name = models.CharField(max_length=200, blank=True, default="")
    first_location_name = models.CharField(max_length=200, blank=True, default="")
    chosen_vertical = models.CharField(max_length=50, blank=True, default="")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = "accounts_onboarding_profile"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["completed_at"]),
        ]
    
    def __str__(self) -> str:
        return f"Onboarding: {self.user.get_username()}"
    
    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None
    
    @property
    def selected_goals(self) -> list[str]:
        """Returns a list of selected goal descriptions."""
        goals = []
        if self.goal_stop_theft:
            goals.append("Stop theft and missing stock")
        if self.goal_see_profit:
            goals.append("See profit and losses clearly")
        if self.goal_track_performance:
            goals.append("Track agent performance and rankings")
        if self.goal_move_off_notebooks:
            goals.append("Move off hardcover notebooks")
        return goals


# ---------------------------------------------------
# Two-Factor Authentication (SMS OTP via Twilio Verify)
# ---------------------------------------------------
class UserTwoFactor(models.Model):
    """
    SMS-based 2FA settings per user.
    Stores phone number and whether SMS 2FA is enabled.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="twofactor",
    )
    sms_enabled = models.BooleanField(
        default=False,
        help_text="Whether SMS 2FA is enabled for this user"
    )
    phone_e164 = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Phone number in E.164 format (e.g. +265991234567)"
    )
    phone_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the phone number was last verified"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_usertwofa"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["sms_enabled"]),
        ]

    def __str__(self) -> str:
        status = "enabled" if self.sms_enabled else "disabled"
        return f"2FA<{self.user.get_username()}:{status}>"


# ----- Two-Factor Helper Functions -----
def get_or_create_twofactor(user):
    """
    Get or create UserTwoFactor record for a user.
    Safe to call multiple times.
    """
    if not user or not user.is_authenticated:
        return None
    tf, _ = UserTwoFactor.objects.get_or_create(user=user)
    return tf


def is_twofa_enabled(user) -> bool:
    """
    Check if SMS 2FA is enabled for the given user.
    """
    if not user or not user.is_authenticated:
        return False
    try:
        tf = user.twofactor
        return tf.sms_enabled
    except UserTwoFactor.DoesNotExist:
        return False


def mask_phone(phone_e164: str) -> str:
    """
    Mask a phone number for display: +265******456
    Shows country code + first digit + last 3 digits.
    """
    if not phone_e164 or len(phone_e164) < 7:
        return phone_e164
    
    # E.164: +[country][number]
    # Example: +265991234567 -> +265******567
    if phone_e164.startswith("+"):
        # Keep + and country code (typically 1-3 digits)
        # Show last 3 digits
        visible_start = phone_e164[:5] if len(phone_e164) > 8 else phone_e164[:4]
        visible_end = phone_e164[-3:]
        masked_middle = "*" * (len(phone_e164) - len(visible_start) - len(visible_end))
        return f"{visible_start}{masked_middle}{visible_end}"
    
    return phone_e164


def is_twofa_recent(request, max_age_seconds: int = 1800) -> bool:
    """
    Check if user has recently passed 2FA challenge (within max_age_seconds).
    Used for step-up authentication on sensitive actions.
    
    Args:
        request: HttpRequest object with session
        max_age_seconds: Maximum age in seconds (default 30 minutes)
    
    Returns:
        True if 2FA was passed recently, False otherwise
    """
    if not request or not hasattr(request, 'session'):
        return False
    
    passed_at = request.session.get("twofa_passed_at")
    if not passed_at:
        return False
    
    try:
        from django.utils import timezone
        import datetime
        
        # Convert to datetime if it's a timestamp
        if isinstance(passed_at, (int, float)):
            passed_dt = datetime.datetime.fromtimestamp(passed_at, tz=timezone.utc)
        elif isinstance(passed_at, str):
            passed_dt = datetime.datetime.fromisoformat(passed_at)
        else:
            passed_dt = passed_at
        
        age = (timezone.now() - passed_dt).total_seconds()
        return age <= max_age_seconds
    except Exception:
        return False




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



# accounts/forms.py
from __future__ import annotations

import re
from typing import Optional

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from .validators import (
    validate_file_size,
    validate_mime,
    validate_strong_password,   # <-- strong password policy
)
from .utils.images import process_avatar
from .models import Profile

# ============================================================
# Helpers
# ============================================================
CODE_RE = re.compile(r"^\d{6}$")
User = get_user_model()


def _normalize_identifier(value: str) -> str:
    """
    Lowercase emails; leave usernames as-is.
    """
    value = (value or "").strip()
    return value.lower() if "@" in value else value


def _validate_passwords(p1: str | None, p2: str | None, *, user: object | None = None) -> str:
    """
    Common enforcement: both provided, must match, and pass validators.
    Returns the validated password (p1).

    Order:
      1) Quick presence & match checks
      2) Our strong policy (≥10 chars + letter + number + special; block weak patterns)
      3) Django's global validators (AUTH_PASSWORD_VALIDATORS)
    """
    if not p1 or not p2:
        raise forms.ValidationError("Enter your password twice.")
    if p1 != p2:
        raise forms.ValidationError("Passwords do not match.")

    # Enforce your custom policy first (clear, concise error)
    validate_strong_password(p1)
    # Then Django's standard validators (e.g., similarity, min length, etc.)
    validate_password(p1, user=user)
    return p1


# ============================================================
# Country / Language / Time zone choice sources
# ============================================================

# Defaults (what shows preselected in the form)
DEFAULT_COUNTRY = "MW"              # Malawi
DEFAULT_LANGUAGE = "en-us"          # English (United States)
DEFAULT_TIMEZONE = "Africa/Blantyre"

# ---- Countries (use django-countries if available; else pycountry; else tiny list) ----
try:
    from django_countries import countries as _countries_source
    COUNTRY_CHOICES = list(_countries_source)  # -> [("MW", "Malawi"), ...]
except Exception:
    try:
        import pycountry  # type: ignore
        COUNTRY_CHOICES = sorted(
            [(c.alpha_2, c.name) for c in pycountry.countries],
            key=lambda x: x[1],
        )
    except Exception:
        COUNTRY_CHOICES = [
            ("MW", "Malawi"),
            ("US", "United States"),
            ("GB", "United Kingdom"),
            ("ZA", "South Africa"),
        ]

# ---- Languages from Django settings (fallback to a small set) ----
LANG_CHOICES = list(
    getattr(
        settings,
        "LANGUAGES",
        [
            ("en-us", "English (United States)"),
            ("en-gb", "English (United Kingdom)"),
            ("en", "English"),
            ("ny", "Chichewa"),
            ("sw", "Swahili"),
            ("fr", "French"),
        ],
    )
)

# ---- Time zones (zoneinfo preferred; pytz fallback; tiny fallback) ----
try:
    from zoneinfo import available_timezones  # Python 3.9+
    TZ_CHOICES = sorted([(tz, tz) for tz in available_timezones()], key=lambda x: x[0])
except Exception:
    try:
        import pytz  # type: ignore
        TZ_CHOICES = sorted([(tz, tz) for tz in pytz.all_timezones], key=lambda x: x[0])
    except Exception:
        TZ_CHOICES = [
            ("Africa/Blantyre", "Africa/Blantyre"),
            ("UTC", "UTC"),
            ("Africa/Johannesburg", "Africa/Johannesburg"),
            ("Europe/London", "Europe/London"),
            ("America/New_York", "America/New_York"),
        ]


# ============================================================
# Avatar upload (standalone endpoint)
# ============================================================
class AvatarForm(forms.Form):
    avatar = forms.ImageField(required=True)

    def clean_avatar(self):
        f = self.cleaned_data["avatar"]
        validate_file_size(f)

        # Use browser-provided content_type as a hint (not authoritative)
        ctype = getattr(f, "content_type", "")
        if ctype:
            validate_mime(ctype)

        # Deep validation + re-encode to safe format/size
        try:
            processed = process_avatar(f)
        except Exception:
            raise forms.ValidationError("Could not process image. Use a valid JPEG/PNG/WEBP.")
        return processed


# ============================================================
# Settings: Profile (ModelForm)
# ============================================================
class ProfileForm(forms.ModelForm):
    """
    Used on Settings → Profile.
    Renders select dropdowns for Country / Language / Time zone with sensible defaults.
    """
    # Force these to ChoiceFields so templates render <select> controls
    country = forms.ChoiceField(choices=COUNTRY_CHOICES, required=False)
    language = forms.ChoiceField(choices=LANG_CHOICES, required=False)
    timezone = forms.ChoiceField(choices=TZ_CHOICES, required=False)

    class Meta:
        model = Profile
        fields = ["display_name", "country", "language", "timezone", "avatar"]
        widgets = {
            "display_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Display name"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Set initial defaults if instance doesn't already have values
        self.fields["country"].initial = getattr(self.instance, "country", None) or DEFAULT_COUNTRY
        self.fields["language"].initial = getattr(self.instance, "language", None) or DEFAULT_LANGUAGE
        self.fields["timezone"].initial = getattr(self.instance, "timezone", None) or DEFAULT_TIMEZONE

        # Bootstrap styles
        self.fields["country"].widget.attrs.update({"class": "form-select"})
        self.fields["language"].widget.attrs.update({"class": "form-select"})
        self.fields["timezone"].widget.attrs.update({"class": "form-select"})
        if "avatar" in self.fields:
            self.fields["avatar"].widget.attrs.update({"class": "form-control"})

    def clean_avatar(self):
        """
        Avatar is optional here; if provided, validate + re-encode.
        """
        f = self.cleaned_data.get("avatar")
        if not f:
            return f
        validate_file_size(f)
        ctype = getattr(f, "content_type", "")
        if ctype:
            validate_mime(ctype)
        try:
            return process_avatar(f)
        except Exception:
            raise forms.ValidationError("Could not process image. Use a valid JPEG/PNG/WEBP.")

    # Optional: keep country code uppercased for ISO-3166 consistency
    def clean_country(self):
        val = (self.cleaned_data.get("country") or "").strip()
        return val.upper()


# ============================================================
# Settings: Security → Password change (simple form)
# ============================================================
class PasswordChangeSimpleForm(forms.Form):
    old_password = forms.CharField(
        label="Current password",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "class": "form-control"}),
    )
    new_password1 = forms.CharField(
        label="New password",
        help_text="At least 10 characters and include a letter, a number, and a special character.",
        widget=forms.PasswordInput(attrs={
            "autocomplete": "new-password",
            "class": "form-control",
            "id": "id_password1",
            "pattern": r"(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z0-9]).{10,}",
            "title": "At least 10 characters and include a letter, a number, and a special character."
        }),
    )
    new_password2 = forms.CharField(
        label="Confirm new password",
        widget=forms.PasswordInput(attrs={
            "autocomplete": "new-password",
            "class": "form-control",
            "id": "id_password2",
        }),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user  # Optional: views can pass request.user for validators
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        _validate_passwords(cleaned.get("new_password1"), cleaned.get("new_password2"), user=self.user)
        return cleaned


# ============================================================
# Login forms (choose one; LoginForm alias points to IdentifierLoginForm)
# ============================================================
class EmailLoginForm(forms.Form):
    """
    Use this if your login page asks specifically for 'Email' + 'Password'.
    """
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={
            "placeholder": "you@example.com",
            "autocomplete": "username email",
            "autofocus": "autofocus",
        }),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def clean_email(self):
        return _normalize_identifier(self.cleaned_data["email"])


class IdentifierLoginForm(forms.Form):
    """
    Use this if you prefer a single 'Email or Username' field on the login page.
    """
    identifier = forms.CharField(
        label="Email or Username",
        max_length=254,
        widget=forms.TextInput(attrs={
            "placeholder": "Email or Username",
            "autocomplete": "username email",
            "autofocus": "autofocus",
        }),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def clean_identifier(self):
        return _normalize_identifier(self.cleaned_data["identifier"])


# Convenience alias so views can `from accounts.forms import LoginForm`
class LoginForm(IdentifierLoginForm):
    pass


# ============================================================
# Forgot password (request code)
# ============================================================
class ForgotPasswordRequestForm(forms.Form):
    identifier = forms.CharField(
        label="Email or Username",
        max_length=254,
        widget=forms.TextInput(attrs={
            "placeholder": "Email or Username",
            "autocomplete": "username email",
        }),
    )

    def clean_identifier(self):
        return _normalize_identifier(self.cleaned_data["identifier"])


# ============================================================
# Verify code + set new password
# ============================================================
class VerifyCodeResetForm(forms.Form):
    """
    Step 2 form: email/username + 6-digit code + new password (twice).
    Optionally pass `user=<User>` to __init__ so password validators
    (AUTH_PASSWORD_VALIDATORS) can use user context.
    """
    identifier = forms.CharField(
        label="Email or Username",
        max_length=254,
        widget=forms.TextInput(attrs={
            "placeholder": "Email or Username",
            "autocomplete": "username email",
        }),
    )
    code = forms.CharField(
        label="Reset code",
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            "placeholder": "6-digit code",
            "inputmode": "numeric",
            "autocomplete": "one-time-code",
        }),
        error_messages={"invalid": "Enter the 6-digit code we emailed."},
    )
    new_password1 = forms.CharField(
        label="New password",
        help_text="At least 10 characters and include a letter, a number, and a special character.",
        widget=forms.PasswordInput(attrs={
            "autocomplete": "new-password",
            "id": "id_password1",
            "pattern": r"(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z0-9]).{10,}",
            "title": "At least 10 characters and include a letter, a number, and a special character."
        }),
    )
    new_password2 = forms.CharField(
        label="Confirm new password",
        widget=forms.PasswordInput(attrs={
            "autocomplete": "new-password",
            "id": "id_password2",
        }),
    )

    def __init__(self, *args, user: Optional[object] = None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_identifier(self):
        return _normalize_identifier(self.cleaned_data["identifier"])

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip()
        if not CODE_RE.match(code):
            raise forms.ValidationError("Enter the 6-digit code we emailed.")
        return code

    def clean(self):
        cleaned = super().clean()
        _validate_passwords(cleaned.get("new_password1"), cleaned.get("new_password2"), user=self.user)
        return cleaned


# ============================================================
# Manager sign-up (creates first manager + seeds Business via view)
# ============================================================
class ManagerSignUpForm(forms.Form):
    """
    Minimal manager sign-up form used by views.signup_manager.
    The view will create the User and Business, add user to 'Manager' group,
    and optionally set profile flags.

    Fields:
      - full_name: Free text, split into first/last if available on User model.
      - email: Used as username; must be unique (case-insensitive).
      - business_name: Name of the store/business to create.
      - subdomain (optional): render-friendly; store/ignore in view as you like.
      - password1/password2: With validators (custom + Django).
    """
    full_name = forms.CharField(
        max_length=150,
        label="Full name",
        widget=forms.TextInput(attrs={"placeholder": "Your full name"}),
    )
    email = forms.EmailField(
        label="Work email",
        widget=forms.EmailInput(attrs={"placeholder": "you@store.co"}),
    )
    business_name = forms.CharField(
        max_length=200,
        label="Store / Business name",
        widget=forms.TextInput(attrs={"placeholder": "e.g., Circuit City Area 25"}),
    )
    subdomain = forms.CharField(
        max_length=40,
        required=False,
        label="Subdomain (optional)",
        widget=forms.TextInput(attrs={"placeholder": "e.g. circuitcity"}),
        help_text="Optional short URL label. You can set this later.",
    )
    password1 = forms.CharField(
        label="Password",
        help_text="At least 10 characters and include a letter, a number, and a special character.",
        widget=forms.PasswordInput(attrs={
            "autocomplete": "new-password",
            "id": "id_password1",
            "pattern": r"(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z0-9]).{10,}",
            "title": "At least 10 characters and include a letter, a number, and a special character."
        }),
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "id": "id_password2"}),
    )

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        # We use email as username; block duplicates in either field.
        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        data = super().clean()
        # Validate match + strength using a dummy user for context
        dummy_user = User(username=(data.get("email") or "").strip().lower())
        try:
            _validate_passwords(data.get("password1"), data.get("password2"), user=dummy_user)
        except forms.ValidationError as e:
            # Attach to password2 for nicer UX on the form
            self.add_error("password2", e)
        # Ensure business name provided
        if not (data.get("business_name") or "").strip():
            self.add_error("business_name", "Enter your store name.")
        return data

# accounts/forms.py
from __future__ import annotations

import re
from typing import Optional

from django import forms
from django.contrib.auth.password_validation import validate_password

from .validators import validate_file_size, validate_mime
from .utils.images import process_avatar
from .models import Profile


# ============================================================
# Helpers
# ============================================================
CODE_RE = re.compile(r"^\d{6}$")


def _normalize_identifier(value: str) -> str:
    """
    Lowercase emails; leave usernames as-is.
    """
    value = (value or "").strip()
    return value.lower() if "@" in value else value


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
    Reuses process_avatar to sanitize uploads; shows initials fallback when empty.
    """
    class Meta:
        model = Profile
        fields = ["display_name", "country", "language", "timezone", "avatar"]
        widgets = {
            "display_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Display name"}),
            "country": forms.TextInput(attrs={"class": "form-control", "placeholder": "Country/Region"}),
            "language": forms.TextInput(attrs={"class": "form-control", "placeholder": "Language"}),
            "timezone": forms.TextInput(attrs={"class": "form-control", "placeholder": "Time zone"}),
        }

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
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "class": "form-control"}),
    )
    new_password2 = forms.CharField(
        label="Confirm new password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "class": "form-control"}),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user  # Optional: views can pass request.user for validators
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("new_password1")
        p2 = cleaned.get("new_password2")

        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("New passwords do not match.")

        if p1:
            # Apply Django's password validators (with optional user context)
            validate_password(p1, user=self.user)

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
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    new_password2 = forms.CharField(
        label="Confirm new password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
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
        p1 = cleaned.get("new_password1")
        p2 = cleaned.get("new_password2")

        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Passwords do not match.")

        if p1:
            # Apply Django's password validators with optional user context
            validate_password(p1, user=getattr(self, "user", None))

        return cleaned

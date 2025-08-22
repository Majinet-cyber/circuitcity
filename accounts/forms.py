# accounts/forms.py
from django import forms
from django.contrib.auth.password_validation import validate_password

from .validators import validate_file_size, validate_mime
from .utils.images import process_avatar


class AvatarForm(forms.Form):
    avatar = forms.ImageField(required=True)

    def clean_avatar(self):
        f = self.cleaned_data["avatar"]
        validate_file_size(f)

        # Use browser-provided content_type as a hint (not authoritative)
        ctype = getattr(f, "content_type", "")
        if ctype:
            validate_mime(ctype)

        # Deep validation + re-encode
        try:
            processed = process_avatar(f)
        except Exception:
            raise forms.ValidationError("Could not process image. Use a valid JPEG/PNG/WEBP.")
        return processed


class ForgotPasswordRequestForm(forms.Form):
    identifier = forms.CharField(
        label="Email or Username",
        max_length=254,
        widget=forms.TextInput(attrs={
            "placeholder": "Email or Username",
            "autocomplete": "username email",
        }),
    )


class VerifyCodeResetForm(forms.Form):
    identifier = forms.CharField(
        label="Email or Username",
        max_length=254,
        widget=forms.TextInput(attrs={
            "placeholder": "Email or Username",
            "autocomplete": "username email",
        }),
    )
    code = forms.RegexField(
        label="Reset code",
        regex=r"^\d{6}$",
        min_length=6,
        max_length=6,
        error_messages={"invalid": "Enter the 6-digit code we emailed."},
        widget=forms.TextInput(attrs={
            "placeholder": "6-digit code",
            "inputmode": "numeric",
            "autocomplete": "one-time-code",
        }),
    )
    new_password1 = forms.CharField(
        label="New password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    new_password2 = forms.CharField(
        label="Confirm new password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("new_password1")
        p2 = cleaned.get("new_password2")

        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Passwords do not match.")

        if p1:
            # Apply Django's password validators (AUTH_PASSWORD_VALIDATORS)
            validate_password(p1)

        return cleaned

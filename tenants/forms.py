# tenants/forms.py
from __future__ import annotations

from django import forms
from django.utils.text import slugify
from django.core.exceptions import ValidationError

from .models import Business


class CreateBusinessForm(forms.ModelForm):
    """
    Minimal manager-onboarding form.
    - Only asks for 'name'
    - Derives a unique slug automatically
    """
    class Meta:
        model = Business
        fields = ["name"]  # add "subdomain" here if you want to collect it at create time

    def clean(self):
        cleaned = super().clean()
        name = (cleaned.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Please provide a business/store name.")
        # provide slug for views to use
        cleaned["slug"] = slugify(name)
        return cleaned


class JoinAsAgentForm(forms.Form):
    """
    Simple join flow: agent types the exact business name to request access.
    Your view resolves Business and attaches it to cleaned_data['business'].
    """
    business_name = forms.CharField(
        max_length=120,
        help_text="Enter the exact business name your manager created."
    )

    def clean(self):
        from .models import Business  # local import avoids early import surprises
        cleaned = super().clean()
        name = (cleaned.get("business_name") or "").strip()
        if not name:
            raise forms.ValidationError("Please enter a business name.")

        try:
            biz = Business.objects.get(name__iexact=name, status="ACTIVE")
        except Business.DoesNotExist:
            raise forms.ValidationError("No active business with that name.")

        cleaned["business"] = biz
        return cleaned


class InviteAgentForm(forms.Form):
    """
    Used by managers to invite agents.

    Behavior:
      - 'invited_name' is optional
      - 'email' and 'phone' are BOTH optional
      - optional 'message' field is included for convenience
    """
    invited_name = forms.CharField(
        max_length=120,
        required=False,
        label="Invited name (optional)",
    )
    email = forms.EmailField(required=False)
    phone = forms.CharField(required=False, help_text="Optional. WhatsApp/phone number")
    message = forms.CharField(required=False, max_length=240)

    def clean(self):
        cleaned = super().clean()

        # Normalize whitespace on free-text fields
        for key in ("invited_name", "email", "phone", "message"):
            if key in cleaned and isinstance(cleaned.get(key), str):
                cleaned[key] = cleaned[key].strip()

        # NOTE: We intentionally do NOT require email or phone.
        # The manager can copy/share the generated link directly.
        return cleaned


# === New: Accept-invite signup form (used on /tenants/invites/accept/<token>/) ===

class AgentInviteAcceptForm(forms.Form):
    """
    Form shown to invitees after clicking the invite link.
    - Email is prefilled from the invite and locked (disabled) so the token
      cannot be used to create a different account.
    - User selects a password and confirms it.

    Usage in view:
        form = AgentInviteAcceptForm(initial_email=invite.email, data=request.POST or None)
    """
    email = forms.EmailField(disabled=True, required=False, label="Email")
    password1 = forms.CharField(
        widget=forms.PasswordInput,
        min_length=8,
        label="Password",
        help_text="At least 8 characters."
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput,
        min_length=8,
        label="Confirm password"
    )

    def __init__(self, *args, initial_email: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        # Prefill and lock the email the invite was sent to (may be blank if link-only)
        if initial_email:
            self.fields["email"].initial = initial_email

    def clean_password1(self):
        pw = self.cleaned_data.get("password1") or ""
        # Basic strength nudges (kept simple to avoid surprises)
        if len(pw) < 8:
            raise ValidationError("Password must be at least 8 characters.")
        return pw

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            raise ValidationError("Passwords do not match.")
        return cleaned

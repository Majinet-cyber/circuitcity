# tenants/forms.py
from __future__ import annotations

from django import forms
from django.utils.text import slugify

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

    New behavior to match the updated template:
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

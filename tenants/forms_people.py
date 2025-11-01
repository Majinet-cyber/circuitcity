# tenants/forms_people.py
from __future__ import annotations

from typing import Any

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from .models_invite import AgentInvite, ROLE_CHOICES
from inventory.models import Location

User = get_user_model()


class InviteAgentForm(forms.ModelForm):
    """
    Manager invites an Agent/Staff member.
    Requires at least one contact method (email or phone).
    """

    class Meta:
        model = AgentInvite
        fields = ["full_name", "email", "phone", "role", "locations"]
        widgets = {
            "locations": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Normalize choices & labels defensively
        try:
            self.fields["role"].choices = list(ROLE_CHOICES)
        except Exception:
            # Fallback: keep whatever the model provides
            pass

        # Locations queryset (ordered for nicer UX)
        try:
            self.fields["locations"].queryset = Location.objects.all().order_by("name")
        except Exception:
            # If Location has no 'name' field, drop ordering but keep queryset
            self.fields["locations"].queryset = Location.objects.all()

        # Optional: nicer labels/placeholders
        self.fields["full_name"].label = "Full name"
        if "email" in self.fields:
            self.fields["email"].widget.attrs.setdefault("placeholder", "name@example.com")
        if "phone" in self.fields:
            self.fields["phone"].widget.attrs.setdefault("placeholder", "+265 …")

    def clean(self) -> dict[str, Any]:
        data = super().clean()
        email = (data.get("email") or "").strip()
        phone = (data.get("phone") or "").strip()

        if not email and not phone:
            raise forms.ValidationError("Provide at least an email or a phone number.")

        # Normalize email to lowercase
        if email:
            data["email"] = email.lower()

        # Basic phone trim; leave heavy validation to model/validators if any
        if phone:
            data["phone"] = phone

        return data


class AcceptInviteForm(forms.Form):
    """
    Invitee completes acceptance: provides full name and sets a password.
    """
    full_name = forms.CharField(max_length=120)
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    def clean(self) -> dict[str, Any]:
        data = super().clean()
        pwd1 = data.get("password1") or ""
        pwd2 = data.get("password2") or ""

        if pwd1 != pwd2:
            raise forms.ValidationError("Passwords do not match.")

        # Run Django's password validators
        validate_password(pwd1)
        return data


class LocationForm(forms.ModelForm):
    """
    Minimal Location editor. Adjust fields if your model differs.
    """
    class Meta:
        model = Location
        fields = ["name", "city", "latitude", "longitude"]  # adjust to your actual fields


class PasswordResetTriggerForm(forms.Form):
    """
    Small admin/manager helper form to trigger a reset flow for a user.
    """
    user_id = forms.IntegerField(widget=forms.HiddenInput)

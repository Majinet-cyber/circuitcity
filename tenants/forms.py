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
    - (Optionally) allows subdomain if you uncomment the Meta fields
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

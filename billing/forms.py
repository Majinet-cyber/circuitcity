# billing/forms.py
from __future__ import annotations

from datetime import date
from typing import Iterable

from django import forms
from django.core.exceptions import ValidationError

from .models import SubscriptionPlan, Payment


# ---------------------------
# Helpers
# ---------------------------
def _active_plans_qs() -> Iterable[SubscriptionPlan]:
    return SubscriptionPlan.objects.filter(is_active=True).order_by("amount", "name")


def _luhn_ok(num: str) -> bool:
    """
    Basic Luhn check for PAN validation (non-PCI demo only).
    """
    digits = [int(ch) for ch in num if ch.isdigit()]
    if len(digits) < 12:  # keep it loose for test cards
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _normalize_msisdn(raw: str) -> str:
    """
    Normalize phone numbers: strip spaces/dashes, keep leading + if present.
    If starts with '0', keep as-is for local usage; if '265' missing, the backend
    can decide. We only ensure it is digits/+ and reasonable length.
    """
    cleaned = "".join(ch for ch in raw.strip() if ch.isdigit() or ch == "+")
    # collapse leading 00 -> +
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    return cleaned


# ---------------------------
# Forms
# ---------------------------
class ChoosePlanForm(forms.Form):
    plan = forms.ModelChoiceField(
        queryset=_active_plans_qs(),
        label="Choose your plan",
        widget=forms.Select(attrs={"class": "input", "hx-target": "closest form"}),
        empty_label=None,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Improve labels like: "Starter â€” MWK 20,000 / monthly"
        qs = _active_plans_qs()
        choices = []
        for p in qs:
            label = f"{p.name} â€” {p.currency} {p.amount} / {p.get_interval_display().lower()}"
            choices.append((p.id, label))
        self.fields["plan"].choices = choices


class AirtelForm(forms.Form):
    msisdn = forms.CharField(
        label="Airtel Money number",
        help_text="e.g., +265 999 12 34 56 or 0999 123 456",
        widget=forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel", "class": "input"}),
    )

    def clean_msisdn(self) -> str:
        msisdn = _normalize_msisdn(self.cleaned_data["msisdn"])
        digits = [d for d in msisdn if d.isdigit()]
        if len(digits) < 9 or len(digits) > 15:
            raise ValidationError("Enter a valid phone number.")
        return msisdn


class BankProofForm(forms.Form):
    reference = forms.CharField(
        label="Bank reference / narration",
        widget=forms.TextInput(attrs={"class": "input"}),
    )
    proof_file = forms.FileField(
        label="Attach proof (optional)",
        required=False,
        widget=forms.ClearableFileInput(attrs={"class": "file-input"}),
    )


class CardForm(forms.Form):
    number = forms.CharField(
        label="Card number",
        widget=forms.TextInput(attrs={"autocomplete": "cc-number", "inputmode": "numeric", "class": "input"}),
    )
    exp_month = forms.IntegerField(
        label="Exp. month",
        min_value=1,
        max_value=12,
        widget=forms.NumberInput(attrs={"class": "input", "style": "max-width:120px"}),
    )
    exp_year = forms.IntegerField(
        label="Exp. year",
        min_value=date.today().year,
        max_value=date.today().year + 15,
        widget=forms.NumberInput(attrs={"class": "input", "style": "max-width:140px"}),
    )
    cvv = forms.CharField(
        label="CVV",
        min_length=3,
        max_length=4,
        widget=forms.PasswordInput(attrs={"autocomplete": "cc-csc", "inputmode": "numeric", "class": "input", "style": "max-width:120px"}),
    )

    def clean_number(self) -> str:
        raw = self.cleaned_data["number"]
        num = "".join(ch for ch in raw if ch.isdigit())
        if not _luhn_ok(num):
            raise ValidationError("Card number appears invalid.")
        return num

    def clean(self):
        cleaned = super().clean()
        # Basic expiry check
        month = cleaned.get("exp_month")
        year = cleaned.get("exp_year")
        if month and year:
            today = date.today()
            if year < today.year or (year == today.year and month < today.month):
                raise ValidationError("Card is expired.")
        return cleaned



# billing/forms.py
from __future__ import annotations
from django import forms
from .models import Plan

class ChoosePlanForm(forms.Form):
    plan = forms.ModelChoiceField(queryset=Plan.objects.filter(is_active=True), empty_label=None)

class AirtelForm(forms.Form):
    msisdn = forms.CharField(max_length=20, label="Airtel Money number")

class BankProofForm(forms.Form):
    reference = forms.CharField(max_length=64, label="Standard Bank reference / proof code")

class CardForm(forms.Form):
    # We DO NOT store raw card; your JS should tokenize and put the token in this hidden field
    token = forms.CharField(widget=forms.HiddenInput)
    brand = forms.CharField(max_length=20)
    last4 = forms.CharField(max_length=4)
    exp_month = forms.IntegerField(min_value=1, max_value=12)
    exp_year = forms.IntegerField(min_value=2024, max_value=2040)

from __future__ import annotations
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from .models_invite import AgentInvite, ROLE_CHOICES
from inventory.models import Location


User = get_user_model()


class InviteAgentForm(forms.ModelForm):
class Meta:
model = AgentInvite
fields = ["full_name", "email", "phone", "role", "locations"]
widgets = {
"locations": forms.CheckboxSelectMultiple,
}


def clean(self):
data = super().clean()
if not data.get("email") and not data.get("phone"):
raise forms.ValidationError("Provide at least an email or a phone number.")
return data


class AcceptInviteForm(forms.Form):
full_name = forms.CharField(max_length=120)
password1 = forms.CharField(widget=forms.PasswordInput)
password2 = forms.CharField(widget=forms.PasswordInput)


def clean(self):
data = super().clean()
if data.get("password1") != data.get("password2"):
raise forms.ValidationError("Passwords do not match.")
validate_password(data.get("password1"))
return data


class LocationForm(forms.ModelForm):
class Meta:
model = Location
fields = ["name", "city", "latitude", "longitude"] # adjust to your actual fields


class PasswordResetTriggerForm(forms.Form):
user_id = forms.IntegerField(widget=forms.HiddenInput)


# support/forms.py
from django import forms
from .models import Ticket, TicketComment


class TicketCreateForm(forms.ModelForm):
    """Form for managers to create tickets."""

    class Meta:
        model = Ticket
        fields = ["subject", "description", "priority"]
        widgets = {
            "subject": forms.TextInput(attrs={"class": "form-control", "placeholder": "Brief summary of the issue"}),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": "Detailed description of your issue or request",
                }
            ),
            "priority": forms.Select(attrs={"class": "form-control"}),
        }


class TicketUpdateForm(forms.ModelForm):
    """Form for HQ to update ticket status."""

    class Meta:
        model = Ticket
        fields = ["status", "priority", "assigned_to"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-control"}),
            "priority": forms.Select(attrs={"class": "form-control"}),
            "assigned_to": forms.Select(attrs={"class": "form-control"}),
        }


class TicketCommentForm(forms.ModelForm):
    """Form for adding comments to tickets."""

    class Meta:
        model = TicketComment
        fields = ["comment", "is_internal"]
        widgets = {
            "comment": forms.Textarea(
                attrs={"class": "form-control", "rows": 3, "placeholder": "Add a comment or update..."}
            ),
            "is_internal": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

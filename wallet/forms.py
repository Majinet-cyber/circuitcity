# wallet/forms.py
from __future__ import annotations
from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

class IssuePayslipForm(forms.Form):
    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).order_by("username"),
        widget=forms.SelectMultiple(attrs={"size": 12, "class": "form-select"})
    )
    period_start = forms.DateField(widget=forms.DateInput(attrs={"type":"date"}))
    period_end   = forms.DateField(widget=forms.DateInput(attrs={"type":"date"}))
    send_now     = forms.BooleanField(initial=True, required=False)

    # Optional quick scheduler
    schedule_monthly = forms.BooleanField(initial=False, required=False)
    schedule_day     = forms.IntegerField(min_value=1, max_value=31, initial=28, required=False)
    schedule_hour    = forms.IntegerField(min_value=0, max_value=23, initial=9, required=False)

    def clean(self):
        c = super().clean()
        if c.get("period_end") and c.get("period_start") and c["period_end"] < c["period_start"]:
            self.add_error("period_end", "End date must be after start date.")
        if c.get("schedule_monthly"):
            if not c.get("schedule_day") and not c.get("schedule_hour"):
                self.add_error("schedule_day", "Choose a day and hour for monthly auto-send.")
        return c

    @classmethod
    def initial_previous_month(cls):
        today = timezone.localdate()
        first_this = today.replace(day=1)
        last_prev = first_this - timezone.timedelta(days=1)
        start_prev = last_prev.replace(day=1)
        return {"period_start": start_prev, "period_end": last_prev}

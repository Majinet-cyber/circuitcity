from django import forms
from django.contrib.auth import get_user_model

from .utils import assign_role, profile_role


ROLE_CHOICES = [
    ("merchant", "Merchant"),
    ("underwriter", "Underwriter"),
    ("hq", "HQ"),
]


class HQUserForm(forms.ModelForm):
    full_name = forms.CharField(max_length=150, required=False)
    role = forms.ChoiceField(choices=ROLE_CHOICES)
    password = forms.CharField(widget=forms.PasswordInput, required=False)

    class Meta:
        model = get_user_model()
        fields = ["username", "email", "full_name", "password", "role", "is_active"]

    def __init__(self, *args, **kwargs):
        self.creating = kwargs.pop("creating", False)
        super().__init__(*args, **kwargs)
        if self.creating:
            self.fields["password"].required = True
        if self.instance.pk:
            self.fields["full_name"].initial = self.instance.get_full_name()
            role = profile_role(self.instance)
            if role in {"merchant", "underwriter", "hq"}:
                self.fields["role"].initial = role
            elif self.instance.groups.filter(name="HQ").exists():
                self.fields["role"].initial = "hq"
            elif self.instance.groups.filter(name="Underwriter").exists():
                self.fields["role"].initial = "underwriter"
            elif self.instance.groups.filter(name="Merchant").exists():
                self.fields["role"].initial = "merchant"

    def save(self, commit=True):
        user = super().save(commit=False)
        full_name = self.cleaned_data.get("full_name", "").strip()
        if full_name:
            parts = full_name.split(" ", 1)
            user.first_name = parts[0]
            user.last_name = parts[1] if len(parts) > 1 else ""
        else:
            user.first_name = ""
            user.last_name = ""

        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)

        if commit:
            user.save()
            assign_role(user, self.cleaned_data["role"])
        return user

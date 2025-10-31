# tenants/forms.py
from __future__ import annotations

from django import forms
from django.utils.text import slugify
from django.core.exceptions import ValidationError

from .models import Business

try:
    from .models import Location  # optional; used to populate location choices
except Exception:  # pragma: no cover
    Location = None  # type: ignore


class CreateBusinessForm(forms.ModelForm):
    """
    Minimal manager-onboarding form.
    - Only asks for 'name'
    - Derives a unique slug automatically (appends -2, -3, ... if needed)
    """
    class Meta:
        model = Business
        fields = ["name"]  # add "subdomain" here if you want to collect it at create time

    def _unique_slug(self, base: str) -> str:
        """
        Ensure the slug is unique without racing: best-effort check here;
        database unique constraints should still enforce final uniqueness.
        """
        base = (base or "").strip("-")
        if not base:
            base = "shop"
        slug = base
        # Try a few numeric suffixes (cheap, avoids heavy queries)
        for i in range(1, 999):
            try:
                exists = Business.objects.filter(slug=slug).exists()
            except Exception:
                # If model lacks slug or DB unavailable at this moment, just return
                exists = False
            if not exists:
                return slug
            slug = f"{base}-{i+1}"
        return slug  # fallback (DB should still reject duplicates)

    def clean(self):
        cleaned = super().clean()
        name = (cleaned.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Please provide a business/store name.")

        # Provide a unique slug for views to use (only if model has slug)
        try:
            field_names = {f.name for f in Business._meta.fields}
        except Exception:
            field_names = set()

        if "slug" in field_names:
            base = slugify(name) or "shop"
            cleaned_slug = self._unique_slug(base)
            cleaned["slug"] = cleaned_slug
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

        # If Business has a 'status' field, require ACTIVE; otherwise match by name only.
        try:
            field_names = {f.name for f in Business._meta.fields}
        except Exception:
            field_names = set()

        try:
            if "status" in field_names:
                biz = Business.objects.get(name__iexact=name, status="ACTIVE")
            else:
                biz = Business.objects.get(name__iexact=name)
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
      - optional 'ttl_days' (default 7; 1..30 allowed)
      - optional 'location_id' (choices populated when form initialized with business=...)
    """
    invited_name = forms.CharField(
        max_length=120,
        required=False,
        label="Invited name (optional)",
    )
    email = forms.EmailField(required=False)
    phone = forms.CharField(required=False, help_text="Optional. WhatsApp/phone number")
    message = forms.CharField(required=False, max_length=240)

    ttl_days = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=30,
        initial=7,
        help_text="Optional. Expiry in days for the invite link (1–30). Default is 7."
    )

    location_id = forms.ChoiceField(
        required=False,
        choices=(),  # populated in __init__ when a business is provided
        label="Location (optional)",
    )

    def __init__(self, *args, business: Business | None = None, **kwargs):
        """
        Pass `business` if you want to populate the location dropdown.
        Example:
            form = InviteAgentForm(request.POST or None, business=request.business)
        """
        super().__init__(*args, **kwargs)
        # Populate location choices if Location model is available and business provided
        choices = [("", "— No specific location —")]
        try:
            if business and Location is not None:
                qs = Location.objects.filter(business=business).order_by("name")  # type: ignore
                choices += [(str(loc.id), loc.name or f"Location #{loc.id}") for loc in qs]
        except Exception:
            # Keep the default single "no location" choice if anything goes wrong
            pass
        self.fields["location_id"].choices = choices

    def clean(self):
        cleaned = super().clean()

        # Normalize whitespace on free-text fields
        for key in ("invited_name", "email", "phone", "message"):
            if key in cleaned and isinstance(cleaned.get(key), str):
                cleaned[key] = cleaned[key].strip()

        # Phone: light sanity check (allow empty)
        phone = cleaned.get("phone")
        if phone:
            raw_digits = "".join(ch for ch in phone if ch.isdigit())
            if len(raw_digits) < 7:
                raise forms.ValidationError("Please enter a valid phone or leave it blank.")

        # ttl_days: default to 7 if empty/invalid (bounds already enforced by field)
        ttl = cleaned.get("ttl_days")
        if not ttl:
            cleaned["ttl_days"] = 7

        # NOTE: We intentionally do NOT require email or phone.
        # The manager can copy/share the generated link directly.
        return cleaned


# === Accept-invite signup form (used on /tenants/invites/accept/<token>/) ===

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
        # Keep an internal copy so clean() can persist the email even though the field is disabled
        self._initial_email = initial_email or ""

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

        # Ensure email survives (disabled fields are not posted)
        email_val = (self.fields.get("email").initial  # type: ignore[assignment]
                     if self.fields.get("email") else None)
        cleaned["email"] = email_val or self._initial_email or ""
        return cleaned

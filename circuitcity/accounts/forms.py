# accounts/forms.py
from __future__ import annotations

import re
from typing import Optional

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import Profile
from .utils.images import process_avatar
from .validators import validate_strong_password  # <-- strong password policy
from .validators import validate_file_size, validate_mime

try:
    from inventory.business_kinds import BusinessKind
except Exception:  # pragma: no cover

    class BusinessKind:
        PHONES = "phones"
        LIQUOR = "liquor"
        GROCERY = "grocery"
        PHARMACY = "pharmacy"
        CLOTHING = "clothing"
        GYM = "gym"
        choices = [
            (PHONES, "Phones & Electronics"),
            (LIQUOR, "Liquor / Bar"),
            (GROCERY, "Grocery / General"),
            (PHARMACY, "Pharmacy"),
            (CLOTHING, "Clothing"),
            (GYM, "Gym / Fitness"),
        ]


# ============================================================
# Helpers
# ============================================================
CODE_RE = re.compile(r"^\d{6}$")
User = get_user_model()


def _normalize_identifier(value: str) -> str:
    """
    Lowercase emails; leave usernames as-is.
    """
    value = (value or "").strip()
    return value.lower() if "@" in value else value


def _validate_passwords(p1: str | None, p2: str | None, *, user: object | None = None) -> str:
    """
    Common enforcement: both provided, must match, and pass validators.
    Returns the validated password (p1).

    Order:
      1) Quick presence & match checks
      2) Our strong policy (â‰¥10 chars + letter + number + special; block weak patterns)
      3) Django's global validators (AUTH_PASSWORD_VALIDATORS)
    """
    if not p1 or not p2:
        raise forms.ValidationError("Enter your password twice.")
    if p1 != p2:
        raise forms.ValidationError("Passwords do not match.")

    # Enforce your custom policy first (clear, concise error)
    validate_strong_password(p1)
    # Then Django's standard validators (e.g., similarity, min length, etc.)
    validate_password(p1, user=user)
    return p1


# ============================================================
# Country / Language / Time zone choice sources
# ============================================================

# Defaults (what shows preselected in the form)
DEFAULT_COUNTRY = "MW"  # Malawi
DEFAULT_LANGUAGE = "en-us"  # English (United States)
DEFAULT_TIMEZONE = "Africa/Blantyre"
DEFAULT_CITY = "Lilongwe"  # Malawi capital

# ---- Countries (use django-countries if available; else pycountry; else tiny list) ----
try:
    from django_countries import countries as _countries_source

    COUNTRY_CHOICES = list(_countries_source)  # -> [("MW", "Malawi"), ...]
except Exception:
    try:
        import pycountry  # type: ignore

        COUNTRY_CHOICES = sorted(
            [(c.alpha_2, c.name) for c in pycountry.countries],
            key=lambda x: x[1],
        )
    except Exception:
        COUNTRY_CHOICES = [
            ("MW", "Malawi"),
            ("US", "United States"),
            ("GB", "United Kingdom"),
            ("ZA", "South Africa"),
        ]

# ---- Languages from Django settings (fallback to a small set) ----
LANG_CHOICES = list(
    getattr(
        settings,
        "LANGUAGES",
        [
            ("en-us", "English (United States)"),
            ("en-gb", "English (United Kingdom)"),
            ("en", "English"),
            ("ny", "Chichewa"),
            ("sw", "Swahili"),
            ("fr", "French"),
        ],
    )
)

# ---- Time zones (zoneinfo preferred; pytz fallback; tiny fallback) ----
try:
    from zoneinfo import available_timezones  # Python 3.9+

    TZ_CHOICES = sorted([(tz, tz) for tz in available_timezones()], key=lambda x: x[0])
except Exception:
    try:
        import pytz  # type: ignore

        TZ_CHOICES = sorted([(tz, tz) for tz in pytz.all_timezones], key=lambda x: x[0])
    except Exception:
        TZ_CHOICES = [
            ("Africa/Blantyre", "Africa/Blantyre"),
            ("UTC", "UTC"),
            ("Africa/Johannesburg", "Africa/Johannesburg"),
            ("Europe/London", "Europe/London"),
            ("America/New_York", "America/New_York"),
        ]


# ============================================================
# Avatar upload (standalone endpoint)
# ============================================================
class AvatarForm(forms.Form):
    avatar = forms.ImageField(required=True)

    def clean_avatar(self):
        f = self.cleaned_data["avatar"]
        validate_file_size(f)

        # Use browser-provided content_type as a hint (not authoritative)
        ctype = getattr(f, "content_type", "")
        if ctype:
            validate_mime(ctype)

        # Deep validation + re-encode to safe format/size
        try:
            processed = process_avatar(f)
        except Exception:
            raise forms.ValidationError("Could not process image. Use a valid JPEG/PNG/WEBP.")
        return processed


# ============================================================
# Settings: Profile (ModelForm)
# ============================================================
class ProfileForm(forms.ModelForm):
    """
    Used on Settings â†’ Profile.
    Renders select dropdowns for Country / Language / Time zone with sensible defaults.
    """

    # Force these to ChoiceFields so templates render <select> controls
    country = forms.ChoiceField(choices=COUNTRY_CHOICES, required=False)
    language = forms.ChoiceField(choices=LANG_CHOICES, required=False)
    timezone = forms.ChoiceField(choices=TZ_CHOICES, required=False)
    display_currency = forms.ChoiceField(
        choices=[("MWK", "MWK"), ("USD", "USD")], required=False, help_text="Currency to display amounts in"
    )

    class Meta:
        model = Profile
        fields = ["display_name", "country", "language", "timezone", "city", "display_currency", "avatar"]
        widgets = {
            "display_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Display name"}),
            "city": forms.TextInput(attrs={"class": "form-control", "placeholder": "City"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Set initial defaults if instance doesn't already have values
        self.fields["country"].initial = getattr(self.instance, "country", None) or DEFAULT_COUNTRY
        self.fields["language"].initial = getattr(self.instance, "language", None) or DEFAULT_LANGUAGE
        self.fields["timezone"].initial = getattr(self.instance, "timezone", None) or DEFAULT_TIMEZONE
        if "city" in self.fields:
            self.fields["city"].initial = getattr(self.instance, "city", None) or DEFAULT_CITY

        # Bootstrap styles
        self.fields["country"].widget.attrs.update({"class": "form-select"})
        self.fields["language"].widget.attrs.update({"class": "form-select"})
        self.fields["display_currency"].widget.attrs.update({"class": "form-select"})
        self.fields["timezone"].widget.attrs.update({"class": "form-select"})
        if "avatar" in self.fields:
            self.fields["avatar"].widget.attrs.update({"class": "form-control"})

    def clean_avatar(self):
        """
        Avatar is optional here; if provided, validate + re-encode.
        """
        f = self.cleaned_data.get("avatar")
        if not f:
            return f
        validate_file_size(f)
        ctype = getattr(f, "content_type", "")
        if ctype:
            validate_mime(ctype)
        try:
            return process_avatar(f)
        except Exception:
            raise forms.ValidationError("Could not process image. Use a valid JPEG/PNG/WEBP.")

    # Optional: keep country code uppercased for ISO-3166 consistency
    def clean_country(self):
        val = (self.cleaned_data.get("country") or "").strip()
        return val.upper()


# ============================================================
# Settings: Security â†’ Password change (simple form)
# ============================================================
class PasswordChangeSimpleForm(forms.Form):
    old_password = forms.CharField(
        label="Current password",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "class": "form-control"}),
    )
    new_password1 = forms.CharField(
        label="New password",
        help_text="At least 10 characters and include a letter, a number, and a special character.",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "class": "form-control",
                "id": "id_password1",
                "pattern": r"(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z0-9]).{10,}",
                "title": "At least 10 characters and include a letter, a number, and a special character.",
            }
        ),
    )
    new_password2 = forms.CharField(
        label="Confirm new password",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "class": "form-control",
                "id": "id_password2",
            }
        ),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user  # Optional: views can pass request.user for validators
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        _validate_passwords(cleaned.get("new_password1"), cleaned.get("new_password2"), user=self.user)
        return cleaned


# ============================================================
# Login forms (choose one; LoginForm alias points to IdentifierLoginForm)
# ============================================================
class EmailLoginForm(forms.Form):
    """
    Use this if your login page asks specifically for 'Email' + 'Password'.
    """

    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "placeholder": "you@example.com",
                "autocomplete": "username email",
                "autofocus": "autofocus",
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def clean_email(self):
        return _normalize_identifier(self.cleaned_data["email"])


class IdentifierLoginForm(forms.Form):
    """
    Use this if you prefer a single 'Email or Username' field on the login page.
    """

    identifier = forms.CharField(
        label="Email or Username",
        max_length=254,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Email or Username",
                "autocomplete": "username email",
                "autofocus": "autofocus",
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def clean_identifier(self):
        return _normalize_identifier(self.cleaned_data["identifier"])


# Convenience alias so views can `from accounts.forms import LoginForm`
class LoginForm(IdentifierLoginForm):
    pass


# ============================================================
# Forgot password (request code)
# ============================================================
class ForgotPasswordRequestForm(forms.Form):
    identifier = forms.CharField(
        label="Email or Username",
        max_length=254,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Email or Username",
                "autocomplete": "username email",
            }
        ),
    )

    def clean_identifier(self):
        return _normalize_identifier(self.cleaned_data["identifier"])


# ============================================================
# Verify code + set new password
# ============================================================
class VerifyCodeResetForm(forms.Form):
    """
    Step 2 form: email/username + 6-digit code + new password (twice).
    Optionally pass `user=<User>` to __init__ so password validators
    (AUTH_PASSWORD_VALIDATORS) can use user context.
    """

    identifier = forms.CharField(
        label="Email or Username",
        max_length=254,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Email or Username",
                "autocomplete": "username email",
            }
        ),
    )
    code = forms.CharField(
        label="Reset code",
        max_length=6,
        min_length=6,
        widget=forms.TextInput(
            attrs={
                "placeholder": "6-digit code",
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
            }
        ),
        error_messages={"invalid": "Enter the 6-digit code we emailed."},
    )
    new_password1 = forms.CharField(
        label="New password",
        help_text="At least 10 characters and include a letter, a number, and a special character.",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "id": "id_password1",
                "pattern": r"(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z0-9]).{10,}",
                "title": "At least 10 characters and include a letter, a number, and a special character.",
            }
        ),
    )
    new_password2 = forms.CharField(
        label="Confirm new password",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "id": "id_password2",
            }
        ),
    )

    def __init__(self, *args, user: Optional[object] = None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_identifier(self):
        return _normalize_identifier(self.cleaned_data["identifier"])

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip()
        if not CODE_RE.match(code):
            raise forms.ValidationError("Enter the 6-digit code we emailed.")
        return code

    def clean(self):
        cleaned = super().clean()
        _validate_passwords(cleaned.get("new_password1"), cleaned.get("new_password2"), user=self.user)
        return cleaned


# ============================================================
# Manager sign-up (creates first manager + seeds Business via view)
# ============================================================
class ManagerSignUpForm(forms.Form):
    """
    Minimal manager sign-up form used by views.signup_manager.
    The view will create the User and Business, add user to 'Manager' group,
    and optionally set profile flags.

    Fields:
      - full_name: Free text, split into first/last if available on User model.
      - email: Used as username; must be unique (case-insensitive).
      - business_name: Name of the store/business to create.
      - subdomain (optional): render-friendly; store/ignore in view as you like.
      - password1/password2: With validators (custom + Django).
    """

    full_name = forms.CharField(
        max_length=150,
        label="Full name",
        widget=forms.TextInput(attrs={"placeholder": "Your full name"}),
    )
    email = forms.EmailField(
        label="Work email",
        widget=forms.EmailInput(attrs={"placeholder": "you@store.co"}),
    )
    business_name = forms.CharField(
        max_length=200,
        label="Store / Business name",
        widget=forms.TextInput(attrs={"placeholder": "e.g., Circuit City Area 25"}),
    )
    business_kind = forms.ChoiceField(
        label="Business type",
        choices=BusinessKind.choices,
        widget=forms.Select(attrs={"autocomplete": "off"}),
    )
    subdomain = forms.CharField(
        max_length=40,
        required=False,
        label="Subdomain (optional)",
        widget=forms.TextInput(attrs={"placeholder": "e.g. circuitcity"}),
        help_text="Optional short URL label. You can set this later.",
    )
    password1 = forms.CharField(
        label="Password",
        help_text="At least 8 characters – more is stronger.",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "id": "id_password1",
                "minlength": "8",
                "pattern": r".{8,}",
                "title": "At least 8 characters. Use a mix of letters, numbers, and symbols for better security.",
            }
        ),
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "id": "id_password2",
                "minlength": "8",
            }
        ),
    )

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        # We use email as username; block duplicates in either field.
        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError("You already have an account with this email. Please log in instead.")
        return email

    def clean(self):
        data = super().clean()
        # Validate match + strength using a dummy user for context
        dummy_user = User(username=(data.get("email") or "").strip().lower())
        try:
            _validate_passwords(data.get("password1"), data.get("password2"), user=dummy_user)
        except forms.ValidationError as e:
            # Attach to password2 for nicer UX on the form
            self.add_error("password2", e)
        # Ensure business name provided
        if not (data.get("business_name") or "").strip():
            self.add_error("business_name", "Enter your store name.")
        return data


# ================================================================
# Multi-step Signup Wizard Forms
# ================================================================


class WizardStep1Form(forms.Form):
    """Step 1: Your Account - collect user credentials"""

    full_name = forms.CharField(
        max_length=150,
        label="Full name",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Your full name",
                "class": "wizard-input",
                "autocomplete": "name",
            }
        ),
    )
    email = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(
            attrs={
                "placeholder": "you@company.com",
                "class": "wizard-input",
                "autocomplete": "email",
            }
        ),
    )
    password1 = forms.CharField(
        label="Password",
        help_text="At least 8 characters – more is stronger.",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "class": "wizard-input",
                "minlength": "8",
                "placeholder": "Create a strong password",
            }
        ),
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "class": "wizard-input",
                "minlength": "8",
                "placeholder": "Type your password again",
            }
        ),
    )

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError("You already have an account with this email. Please sign in instead.")
        return email

    def clean(self):
        data = super().clean()
        dummy_user = User(username=(data.get("email") or "").strip().lower())
        try:
            _validate_passwords(data.get("password1"), data.get("password2"), user=dummy_user)
        except forms.ValidationError as e:
            self.add_error("password2", e)
        return data


class WizardStep2Form(forms.Form):
    """Step 2: Your Business - collect business details"""

    business_name = forms.CharField(
        max_length=200,
        label="Business name",
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g., Circuit City Area 25",
                "class": "wizard-input",
            }
        ),
    )
    country = forms.CharField(
        max_length=100,
        required=False,
        label="Country",
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g., Zambia",
                "class": "wizard-input",
                "autocomplete": "country",
            }
        ),
    )
    currency = forms.ChoiceField(
        label="Currency",
        choices=[
            ("ZMW", "ZMW - Zambian Kwacha"),
            ("USD", "USD - US Dollar"),
            ("GBP", "GBP - British Pound"),
            ("EUR", "EUR - Euro"),
            ("ZAR", "ZAR - South African Rand"),
            ("KES", "KES - Kenyan Shilling"),
            ("TZS", "TZS - Tanzanian Shilling"),
            ("UGX", "UGX - Ugandan Shilling"),
            ("MWK", "MWK - Malawian Kwacha"),
        ],
        initial="ZMW",
        widget=forms.Select(attrs={"class": "wizard-select"}),
    )
    business_kind = forms.ChoiceField(
        label="Main vertical / business type",
        choices=[("", "Select your business type...")] + list(BusinessKind.choices),
        widget=forms.Select(attrs={"class": "wizard-select"}),
        required=True,
    )

    def clean_business_kind(self):
        """Validate business_kind is a valid choice and not empty."""
        kind = self.cleaned_data.get("business_kind", "").strip()
        if not kind:
            raise forms.ValidationError("Please select your business type.")

        # Verify it's a valid BusinessKind choice
        valid_kinds = [choice[0] for choice in BusinessKind.choices]
        if kind not in valid_kinds:
            raise forms.ValidationError(f"Invalid business type: {kind}. Please select a valid option.")

        return kind

    def clean_business_name(self):
        name = (self.cleaned_data.get("business_name") or "").strip()
        if not name:
            raise forms.ValidationError("Enter your business name.")

        # Import validators
        from tenants.models import Business
        from tenants.validators import validate_business_name, validate_business_name_not_numeric

        # Check not numeric-only
        try:
            validate_business_name_not_numeric(name)
        except forms.ValidationError as e:
            raise forms.ValidationError(e.messages)

        # Check uniqueness (case-insensitive)
        if Business.objects.filter(name__iexact=name).exists():
            raise forms.ValidationError(
                "That store name is already in use. Please pick another name or "
                "contact support if you believe this is an error."
            )

        # Apply basic business name validation
        try:
            validate_business_name(name)
        except forms.ValidationError as e:
            raise forms.ValidationError(e.messages)

        return name


class WizardStep3Form(forms.Form):
    """Step 3: First Location / Shop"""

    location_name = forms.CharField(
        max_length=200,
        label="Location / Shop name",
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g., Main Store or Area 25 Branch",
                "class": "wizard-input",
            }
        ),
    )
    city = forms.CharField(
        max_length=100,
        required=False,
        label="City",
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g., Lusaka",
                "class": "wizard-input",
                "autocomplete": "address-level2",
            }
        ),
    )
    staff_count = forms.IntegerField(
        required=False,
        label="Number of staff / agents (optional)",
        widget=forms.NumberInput(
            attrs={
                "placeholder": "e.g., 5",
                "class": "wizard-input",
                "min": "1",
                "max": "1000",
            }
        ),
    )

    def clean_location_name(self):
        name = (self.cleaned_data.get("location_name") or "").strip()
        if not name:
            raise forms.ValidationError("Enter your location name.")
        return name


class WizardStep4Form(forms.Form):
    """Step 4: Goals & Finish - collect user goals"""

    goal_stop_theft = forms.BooleanField(
        required=False,
        label="Stop theft and missing stock",
    )
    goal_see_profit = forms.BooleanField(
        required=False,
        label="See profit and losses clearly",
    )
    goal_track_performance = forms.BooleanField(
        required=False,
        label="Track agent performance and rankings",
    )
    goal_move_off_notebooks = forms.BooleanField(
        required=False,
        label="Move off hardcover notebooks",
    )


# ================================================================
# Manager Signup Wizard Forms (4 steps for /accounts/signup/manager/)
# ================================================================


class ManagerWizardStep1Form(forms.Form):
    """Manager Signup Step 1: Account credentials"""

    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "placeholder": "you@company.com",
                "autocomplete": "email",
            }
        ),
    )
    full_name = forms.CharField(
        max_length=150,
        label="Your full name",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Jane Doe",
                "autocomplete": "name",
            }
        ),
    )
    password1 = forms.CharField(
        label="Password",
        help_text="Use at least 12 characters (letters, numbers, symbol).",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "minlength": "12",
                "placeholder": "Create a strong password",
            }
        ),
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "minlength": "12",
                "placeholder": "Repeat your password",
            }
        ),
    )

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError("You already have an account with this email. Please sign in instead.")
        return email

    def clean(self):
        data = super().clean()
        dummy_user = User(username=(data.get("email") or "").strip().lower())
        try:
            _validate_passwords(data.get("password1"), data.get("password2"), user=dummy_user)
        except forms.ValidationError as e:
            self.add_error("password2", e)
        return data


class ManagerWizardStep2Form(forms.Form):
    """Manager Signup Step 2: Store basics"""

    business_name = forms.CharField(
        max_length=200,
        label="Store name",
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. Circuitly",
            }
        ),
    )
    business_kind = forms.ChoiceField(
        label="Business type",
        choices=BusinessKind.choices,
        widget=forms.Select(attrs={"autocomplete": "off"}),
    )
    subdomain = forms.CharField(
        max_length=40,
        required=False,
        label="Subdomain (optional)",
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. circuitly",
                "inputmode": "lowercase",
            }
        ),
        help_text="yourstore.emajinet.africa",
    )

    def clean_business_name(self):
        name = (self.cleaned_data.get("business_name") or "").strip()
        if not name:
            raise forms.ValidationError("Enter your store name.")

        # Import validators
        from tenants.models import Business
        from tenants.validators import validate_business_name, validate_business_name_not_numeric

        # Check not numeric-only
        try:
            validate_business_name_not_numeric(name)
        except forms.ValidationError as e:
            raise forms.ValidationError(e.messages)

        # Check uniqueness (case-insensitive)
        if Business.objects.filter(name__iexact=name).exists():
            raise forms.ValidationError(
                "That store name is already in use. Please pick another name or "
                "contact support if you believe this is an error."
            )

        # Apply basic business name validation
        try:
            validate_business_name(name)
        except forms.ValidationError as e:
            raise forms.ValidationError(e.messages)

        return name


class ManagerWizardStep3Form(forms.Form):
    """Manager Signup Step 3: Brand (logo upload)"""

    logo = forms.ImageField(
        required=False,
        label="Logo (optional)",
        widget=forms.FileInput(attrs={"accept": "image/*"}),
    )

    def clean_logo(self):
        f = self.cleaned_data.get("logo")
        if not f:
            return f
        validate_file_size(f)
        ctype = getattr(f, "content_type", "")
        if ctype:
            validate_mime(ctype)
        try:
            return process_avatar(f)
        except Exception:
            raise forms.ValidationError("Could not process image. Use a valid JPEG/PNG/WEBP.")


class ManagerWizardStep4Form(forms.Form):
    """Manager Signup Step 4: Review & Create (no additional fields, just confirmation)"""

    agree = forms.BooleanField(
        required=True,
        label="I agree to the Terms and confirm that I'm creating a store for my business.",
    )

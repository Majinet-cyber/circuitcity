# tenants/validators.py
from __future__ import annotations

import re
from typing import Callable, Iterable, Optional, Tuple, Type

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db.models import Model
from django.utils.deconstruct import deconstructible
from django.utils.text import slugify


__all__ = [
    "clean_whitespace",
    "digits",
    "validate_business_name",
    "validate_subdomain",
    "validate_slug_simple",
    "unique_ci_validator",
    "soft_email_validator",
    "validate_email_soft",
    "normalize_msisdn",
    "validate_msisdn",
]


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------

def clean_whitespace(value: str | None) -> str:
    """Collapse internal whitespace and strip ends. Safe for None."""
    if value is None:
        return ""
    # Replace any runs of whitespace with a single space
    return re.sub(r"\s+", " ", value).strip()


def digits(value: str | None) -> str:
    """Return only the digits from a string."""
    return re.sub(r"\D+", "", value or "")


# ---------------------------------------------------------------------------
# Business name
# ---------------------------------------------------------------------------

BUSINESS_NAME_MAX = 80
BUSINESS_NAME_MIN = 2
# Allow letters, digits, basic punctuation that appears in shop names.
BUSINESS_NAME_ALLOWED_RE = re.compile(r"^[\w\s&/.,'’()\-+|#]*$", re.UNICODE)


def validate_business_name(value: str) -> None:
    """
    Basic sanity checks for a business/store name.
    - Length 2..80
    - Restrict to a conservative safe set of characters
    """
    v = clean_whitespace(value)
    if not (BUSINESS_NAME_MIN <= len(v) <= BUSINESS_NAME_MAX):
        raise ValidationError(
            f"Business name must be between {BUSINESS_NAME_MIN} and {BUSINESS_NAME_MAX} characters."
        )
    if not BUSINESS_NAME_ALLOWED_RE.match(v):
        raise ValidationError(
            "Business name contains invalid characters. "
            "Use letters, numbers, spaces, and simple punctuation like & / . , ' ( ) - + | #"
        )


# ---------------------------------------------------------------------------
# Subdomain / Slug validators
# ---------------------------------------------------------------------------

# RFC-1035-ish: letters, digits, hyphen; no leading/trailing hyphen; 3-30 chars.
SUBDOMAIN_RE = re.compile(r"^(?!-)[a-z0-9-]{3,30}(?<!-)$")
# Avoid known reserved words you likely use in your app / infra.
RESERVED_SUBDOMAINS = {
    "www", "app", "admin", "api", "static", "media", "assets",
    "dashboard", "hq", "staff", "help", "support", "cdn",
    "mail", "smtp", "imap", "pop", "mx", "gateway",
}


def validate_subdomain(value: str) -> None:
    """
    Validate a tenant subdomain label:
    - Lowercase a–z, 0–9, hyphen
    - 3..30 chars
    - Not leading/trailing hyphen
    - Not in a reserved words set
    """
    v = (value or "").strip().lower()
    if not SUBDOMAIN_RE.match(v):
        raise ValidationError(
            "Subdomain must be 3–30 chars of lowercase letters, digits, or hyphens, "
            "and cannot start or end with a hyphen."
        )
    if "--" in v:
        # Optional: disallow double hyphen to keep it neat
        raise ValidationError("Subdomain cannot contain consecutive hyphens.")
    if v in RESERVED_SUBDOMAINS:
        raise ValidationError("That subdomain is reserved. Please choose another.")


def validate_slug_simple(value: str) -> None:
    """
    Conservative slug validator suitable for URL parts:
    - Lowercase letters, digits, hyphens only
    - 1..64 chars
    """
    v = (value or "").strip().lower()
    if not 1 <= len(v) <= 64:
        raise ValidationError("Slug must be between 1 and 64 characters.")
    if not re.fullmatch(r"[a-z0-9-]+", v):
        raise ValidationError("Slug may contain only lowercase letters, digits, and hyphens.")
    if v.startswith("-") or v.endswith("-") or "--" in v:
        raise ValidationError("Slug cannot start/end with a hyphen or contain consecutive hyphens.")


def unique_ci_validator(
    model: Type[Model],
    field_name: str,
    *,
    normalize: Callable[[str], str] | None = None,
    message: str | None = None,
) -> Callable[[str], None]:
    """
    Factory: return a validator that checks the given field is unique (case-insensitive).
    Example:
        slug = models.SlugField(validators=[validate_slug_simple, unique_ci_validator(Business, "slug")])
    """
    def _validator(value: str) -> None:
        val = value or ""
        if normalize:
            val = normalize(val)
        try:
            exists = model.objects.filter(**{f"{field_name}__iexact": val}).exists()
        except Exception:
            # If DB not available here (e.g., migrations), do not block form save;
            # rely on DB unique constraints later.
            exists = False
        if exists:
            raise ValidationError(message or "This value is already in use. Please choose another.")
    return _validator


# ---------------------------------------------------------------------------
# Email (soft)
# ---------------------------------------------------------------------------

soft_email_validator = EmailValidator(
    message="Enter a valid email address."
)

def validate_email_soft(value: str) -> None:
    """
    A forgiving email validator (uses Django's EmailValidator).
    Accepts empty values—use required=True on the form/field if needed.
    """
    v = (value or "").strip()
    if not v:
        return
    soft_email_validator(v)


# ---------------------------------------------------------------------------
# Phone / MSISDN helpers (Malawi-friendly defaults, but generic enough)
# ---------------------------------------------------------------------------

# Malawi: country code 265. National numbers are typically 9 digits.
_DEFAULT_CC = "265"

# Common local patterns we want to accept and normalize:
#  - "+265 991 23 45 67"
#  - "0991 234 567"
#  - "991234567"
# We are intentionally lenient: if it looks like 9–12 digits, we'll produce E.164 (+CC + NSN).
_MSISDN_CLEAN_RE = re.compile(r"[^\d+]+")


def _strip_plus(s: str) -> str:
    return s[1:] if s.startswith("+") else s


def normalize_msisdn(
    raw: str | None,
    *,
    default_cc: str = _DEFAULT_CC,
) -> str:
    """
    Normalize a phone number into E.164 where possible.
    - If `raw` starts with '+', keep the country code.
    - If it starts with '0', drop the leading zero and prepend default_cc.
    - If it has 9–10 digits without CC, assume default_cc.
    Returns: "+<countrycode><number>" or "" if input is empty/unusable.
    """
    if not raw:
        return ""

    s = _MSISDN_CLEAN_RE.sub("", raw)
    if not s:
        return ""

    # Already +<digits>
    if s.startswith("+"):
        # Keep only first leading '+', strip others, and remove spaces
        s = "+" + digits(_strip_plus(s))
        return s

    # Leading zero => local format
    if s.startswith("0"):
        nsn = digits(s.lstrip("0"))
        if not nsn:
            return ""
        return f"+{default_cc}{nsn}"

    # Bare digits; decide if it's local
    just_digits = digits(s)
    if not just_digits:
        return ""

    # Heuristic: 9–10 digits => assume local to default_cc
    if 9 <= len(just_digits) <= 10:
        return f"+{default_cc}{just_digits}"

    # If it looks like CC+NSN without leading '+'
    if len(just_digits) >= 11:
        return f"+{just_digits}"

    # Fallback: cannot normalize confidently
    return f"+{just_digits}"  # still return a plus form to be consistent


def validate_msisdn(value: str) -> None:
    """
    Validate a phone number in a practical, user-friendly way:
    - Accept empty → no error (make field required=True if needed).
    - Normalize to E.164 and then sanity-check length (min 10, max 16 digits excluding '+').
    - Very lenient about local formats; we normalize then check.
    """
    if not value:
        return
    e164 = normalize_msisdn(value)
    if not e164 or not e164.startswith("+") or not digits(e164):
        raise ValidationError("Enter a valid phone number.")
    total = len(digits(e164))
    if total < 10 or total > 16:
        raise ValidationError("Enter a valid phone number (10–16 digits including country code).")


# ---------------------------------------------------------------------------
# Optional: deconstructible validator classes (play nicely with migrations)
# ---------------------------------------------------------------------------

@deconstructible
class UniqueCaseInsensitive:
    """
    A deconstructible version of unique_ci_validator for use directly on model fields.
    Example:
        slug = models.SlugField(validators=[validate_slug_simple, UniqueCaseInsensitive(Business, "slug")])
    """
    def __init__(self, model: Type[Model], field_name: str, message: str | None = None):
        self.model = model
        self.field_name = field_name
        self.message = message or "This value is already in use. Please choose another."

    def __call__(self, value: str) -> None:
        try:
            exists = self.model.objects.filter(**{f"{self.field_name}__iexact": (value or "")}).exists()
        except Exception:
            exists = False
        if exists:
            raise ValidationError(self.message)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model.__name__}, field_name={self.field_name!r})"

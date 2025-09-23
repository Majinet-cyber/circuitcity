# accounts/validators.py
from __future__ import annotations

import re
from typing import Any, Optional

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# ---------- Image/Avatar constraints ----------
ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}  # block svg/gif
MAX_AVATAR_BYTES = 5 * 1024 * 1024  # 5 MB


def _bytes_human(n: int) -> str:
    """Return a human-readable bytes string (e.g., '5 MB')."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n / (1024 ** ('BKBMBGB'.index(unit)//2)):.0f} {unit}"
        n /= 1024
    return f"{n:.0f} B"


def validate_file_size(f: Any) -> None:
    """
    Ensure uploaded file is within MAX_AVATAR_BYTES.
    Accepts a Django UploadedFile or any object with a `.size` attribute.
    """
    size = getattr(f, "size", None)
    if size is None:
        # If we can't read size, fail safe.
        raise ValidationError(_("Unable to read file size."))
    if size > MAX_AVATAR_BYTES:
        raise ValidationError(
            _("File too large (max %(max)s)."),
            params={"max": _bytes_human(MAX_AVATAR_BYTES)},
        )


def validate_mime(mime_or_file: Any) -> None:
    """
    Validate MIME type is allowed (JPEG/PNG/WEBP).
    Accepts either a MIME string or an object with `.content_type`.
    """
    if isinstance(mime_or_file, str):
        mime = mime_or_file
    else:
        mime = getattr(mime_or_file, "content_type", None)
    if not mime:
        raise ValidationError(_("Unable to determine file type."))
    if mime not in ALLOWED_IMAGE_MIME:
        raise ValidationError(_("Unsupported image type. Use JPEG, PNG, or WEBP."))


def validate_avatar(f: Any) -> None:
    """
    Convenience validator for avatar uploads: size + MIME.
    Usage in a form/model field:  validators=[validate_avatar]
    """
    validate_file_size(f)
    validate_mime(f)


# ---------- Strong password constraints ----------
# At least 10 chars, include a letter, a digit, and a special (non-alnum) character.
PASSWORD_REGEX = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z0-9]).{10,}$")

# A few extremely common/weak patterns to block even if regex passes.
COMMON_WEAK_SUBSTRINGS = {
    "password",
    "passw0rd",
    "qwerty",
    "welcome",
    "letmein",
    "admin",
    "imajinet",
    "imajin",
    "majin",
}


def validate_strong_password(value: Optional[str]) -> None:
    """
    Enforce a strong password policy.

    Rules:
      • ≥ 10 characters
      • Contains at least one letter, one number, and one special character
      • Rejects very common patterns/words and simple numeric sequences

    Raise ValidationError with a clear, user-facing message if invalid.
    """
    pwd = value or ""

    if not PASSWORD_REGEX.match(pwd):
        raise ValidationError(
            _(
                "Password must be at least 10 characters and include: "
                "a letter, a number, and a special character."
            )
        )

    lower = pwd.lower()
    if any(w in lower for w in COMMON_WEAK_SUBSTRINGS):
        raise ValidationError(_("Password is too easy to guess. Avoid common words or brand names."))

    # Obvious sequences (e.g., 0123, 1234, 2345)
    if re.search(r"(0123|1234|2345|3456|4567|5678|6789)", pwd):
        raise ValidationError(_("Avoid obvious numeric sequences like 1234."))

    # Repeated same character 3+ times
    if re.search(r"(.)\1{2,}", pwd):
        raise ValidationError(_("Avoid repeating the same character three or more times."))


__all__ = [
    "ALLOWED_IMAGE_MIME",
    "MAX_AVATAR_BYTES",
    "validate_file_size",
    "validate_mime",
    "validate_avatar",
    "PASSWORD_REGEX",
    "validate_strong_password",
]

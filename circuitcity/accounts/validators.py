# accounts/validators.py
from django.core.exceptions import ValidationError

ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}  # block svg/gif
MAX_AVATAR_BYTES = 5 * 1024 * 1024  # 5 MB

def validate_file_size(f):
    if f.size > MAX_AVATAR_BYTES:
        raise ValidationError("File too large (max 5MB).")

def validate_mime(mime: str):
    if mime not in ALLOWED_IMAGE_MIME:
        raise ValidationError("Unsupported image type. Use JPEG, PNG, or WEBP.")

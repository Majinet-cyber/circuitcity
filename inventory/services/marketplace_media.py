from __future__ import annotations

import os

from inventory.services.media_safety import safe_field_url


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov"}
SUPPORTED_MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS


def placeholder_icon(vertical: str | None) -> str:
    return {
        "phones": "📱",
        "car_dealer": "🏎️",
        "car_hire": "🚗",
        "clothing": "👕",
        "farm": "🌾",
        "gym": "🏋️",
        "pharmacy": "💊",
        "hardware": "🔧",
        "liquor": "🍺",
    }.get(vertical or "", "📦")


def _field_url(field_file):
    return safe_field_url(field_file)


def _media_kind(name: str, fallback_is_image: bool = False) -> str:
    ext = os.path.splitext(name or "")[1].lower()
    if ext in IMAGE_EXTENSIONS or fallback_is_image:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    return "placeholder"


def normalize_marketplace_media_name(name: str | None) -> str:
    """
    Normalize legacy file-field names to storage-relative media paths.

    Some old rows may carry absolute local paths or values prefixed with
    /media/. FileField.url needs a storage-relative name; this keeps the real
    marketplace path where one can be safely inferred and otherwise returns "".
    """
    raw = (name or "").strip().replace("\\", "/")
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if "/media/" in raw:
        raw = raw.split("/media/", 1)[1]
    raw = raw.lstrip("/")
    if "marketplace/" in raw:
        raw = raw[raw.index("marketplace/") :]
    return raw


def is_supported_media_name(name: str | None, *, image_only: bool = False) -> bool:
    normalized = normalize_marketplace_media_name(name)
    if not normalized or normalized.startswith(("http://", "https://")):
        return False
    ext = os.path.splitext(normalized)[1].lower()
    if image_only:
        return ext in IMAGE_EXTENSIONS
    return ext in SUPPORTED_MEDIA_EXTENSIONS


def media_file_is_usable(field_file, *, image_only: bool = False) -> bool:
    if not field_file or not getattr(field_file, "name", ""):
        return False
    if not is_supported_media_name(field_file.name, image_only=image_only):
        return False
    return bool(_field_url(field_file))


def marketplace_image_url(image_obj) -> str:
    image_field = getattr(image_obj, "image", None)
    url = _field_url(image_field)
    if not url:
        return ""
    if _media_kind(getattr(image_field, "name", ""), fallback_is_image=True) != "image":
        return ""
    return url


def _media_file_candidate(listing) -> dict[str, str] | None:
    media_file = getattr(listing, "media_file", None)
    media_url = _field_url(media_file)
    if not media_url:
        return None

    media_kind = _media_kind(getattr(media_file, "name", ""))
    if media_kind == "placeholder":
        # Primary uploaded media wins whenever storage can generate a URL.
        # Some production upload paths can be extensionless or otherwise hard
        # to classify, but browsers can still render them correctly.
        media_kind = "image"
    return {
        "kind": media_kind,
        "url": media_url,
        "alt": getattr(listing, "title", "Marketplace listing"),
        "source": "primary",
    }


def _related_image_candidate(listing) -> dict[str, str] | None:
    primary = getattr(listing, "primary_image", None)
    primary_url = marketplace_image_url(primary) if primary else ""
    if not primary_url:
        return None
    return {
        "kind": "image",
        "url": primary_url,
        "alt": getattr(listing, "title", "Marketplace listing"),
        "source": "gallery",
    }


def listing_media(listing) -> dict[str, str]:
    icon = placeholder_icon(getattr(listing, "vertical", ""))
    media = _media_file_candidate(listing) or _related_image_candidate(listing)
    if media:
        media["placeholder_icon"] = icon
        return media

    return {
        "kind": "placeholder",
        "url": "",
        "placeholder_icon": icon,
        "alt": getattr(listing, "title", "Marketplace listing"),
    }

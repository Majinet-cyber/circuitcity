from __future__ import annotations

import os


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov"}


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
    if not field_file or not getattr(field_file, "name", ""):
        return ""
    try:
        storage = field_file.storage
        if storage and not storage.exists(field_file.name):
            return ""
    except Exception:
        pass
    try:
        return field_file.url
    except Exception:
        return ""


def _media_kind(name: str, fallback_is_image: bool = False) -> str:
    ext = os.path.splitext(name or "")[1].lower()
    if ext in IMAGE_EXTENSIONS or fallback_is_image:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    return "placeholder"


def marketplace_image_url(image_obj) -> str:
    return _field_url(getattr(image_obj, "image", None))


def listing_media(listing) -> dict[str, str]:
    icon = placeholder_icon(getattr(listing, "vertical", ""))
    primary = getattr(listing, "primary_image", None)
    primary_url = marketplace_image_url(primary) if primary else ""
    if primary_url:
        return {
            "kind": "image",
            "url": primary_url,
            "placeholder_icon": icon,
            "alt": getattr(listing, "title", "Marketplace listing"),
        }

    media_file = getattr(listing, "media_file", None)
    media_url = _field_url(media_file)
    if media_url:
        return {
            "kind": _media_kind(getattr(media_file, "name", "")),
            "url": media_url,
            "placeholder_icon": icon,
            "alt": getattr(listing, "title", "Marketplace listing"),
        }

    return {
        "kind": "placeholder",
        "url": "",
        "placeholder_icon": icon,
        "alt": getattr(listing, "title", "Marketplace listing"),
    }

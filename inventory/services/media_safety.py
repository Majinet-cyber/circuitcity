from __future__ import annotations

from django.core.files.storage import FileSystemStorage


def storage_is_local(storage) -> bool:
    return isinstance(storage, FileSystemStorage)


def field_file_exists(field_file) -> bool:
    if not field_file or not getattr(field_file, "name", ""):
        return False
    storage = getattr(field_file, "storage", None)
    if storage is None:
        return False
    if not storage_is_local(storage):
        return True
    try:
        return bool(storage.exists(field_file.name))
    except Exception:
        return False


def safe_field_url(field_file) -> str:
    if not field_file or not getattr(field_file, "name", ""):
        return ""
    try:
        url = field_file.url
    except Exception:
        return ""
    if not url:
        return ""

    storage = getattr(field_file, "storage", None)
    if storage is not None and storage_is_local(storage):
        return url if field_file_exists(field_file) else ""

    if url.startswith(("http://", "https://")):
        return url
    if not field_file_exists(field_file):
        return ""
    return url


def object_image_url(obj, attr: str = "image") -> str:
    return safe_field_url(getattr(obj, attr, None))

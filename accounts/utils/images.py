# accounts/utils/images.py
from io import BytesIO
from PIL import Image, UnidentifiedImageError
from django.core.files.uploadedfile import InMemoryUploadedFile
import os

# Final output format and max dimensions
TARGET_FORMAT = "WEBP"  # compact + strips EXIF; could use "JPEG"
MAX_W, MAX_H = 512, 512  # avatars rarely need to be larger
QUALITY = 85

def process_avatar(file) -> InMemoryUploadedFile:
    """
    Open, verify, resize to fit box, convert to RGB, re-encode to WEBP/JPEG.
    Returns a new InMemoryUploadedFile suitable for saving.
    Raises if not a real image.
    """
    try:
        img = Image.open(file)
        img.verify()  # quick integrity check
    except UnidentifiedImageError:
        raise ValueError("Invalid image file.")
    file.seek(0)  # must re-open after verify

    img = Image.open(file)
    # Normalize mode (strip alpha if necessary)
    if img.mode not in ("RGB", "L", "P"):
        img = img.convert("RGB")
    else:
        img = img.convert("RGB")

    # Resize to fit within MAX_W x MAX_H
    img.thumbnail((MAX_W, MAX_H))

    # Re-encode
    buf = BytesIO()
    img.save(buf, format=TARGET_FORMAT, quality=QUALITY, optimize=True)
    buf.seek(0)

    # Build a safe filename (ignore original)
    base = "avatar"
    ext = ".webp" if TARGET_FORMAT.upper() == "WEBP" else ".jpg"
    fname = base + ext

    # Wrap back into InMemoryUploadedFile
    return InMemoryUploadedFile(
        buf,               # file
        field_name=None,   # not bound to a form field here
        name=fname,
        content_type="image/webp" if ext == ".webp" else "image/jpeg",
        size=buf.getbuffer().nbytes,
        charset=None
    )

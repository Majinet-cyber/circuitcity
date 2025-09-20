from __future__ import annotations

from io import BytesIO
from django.core.files.base import ContentFile

try:
    from PIL import Image  # optional; if missing we just pass through
except Exception:
    Image = None


def process_avatar(uploaded_file, max_px: int = 512):
    """
    Best-effort avatar processor:
      - If Pillow is available: convert to RGB JPEG, max side <= max_px.
      - If anything fails (or Pillow not installed), return the original file.
    """
    if Image is None:
        return uploaded_file

    try:
        img = Image.open(uploaded_file)
        img = img.convert("RGB")
        img.thumbnail((max_px, max_px))

        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        data = buf.getvalue()

        out = ContentFile(data)
        base = uploaded_file.name.rsplit(".", 1)[0]
        out.name = f"{base}.jpg"
        return out
    except Exception:
        # Safety first: never block the flow because of image processing.
        return uploaded_file

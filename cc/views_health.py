# cc/views_health.py
from __future__ import annotations

from django.http import JsonResponse, HttpRequest


def health(request: HttpRequest) -> JsonResponse:
    """
    Public health endpoint (no authentication required).
    Returns {"ok": true} for Render parity CI checks.
    """
    return JsonResponse({"ok": True})


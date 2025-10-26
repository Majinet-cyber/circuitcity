# circuitcity/notifications/views.py
from __future__ import annotations

from typing import Optional

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpRequest, HttpResponseBadRequest
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError

# Try to import the model, but allow the app to run even if migrations aren't applied yet.
try:
    from .models import Notification  # type: ignore
except Exception:  # app not ready / import error
    Notification = None  # type: ignore


# ---------------------------
# Helpers
# ---------------------------
def _table_exists(model) -> bool:
    try:
        if not model:
            return False
        return model._meta.db_table in connection.introspection.table_names()
    except Exception:
        return False


def _base_qs_for_user(request) -> Optional["Notification"].__class__:
    """
    Returns a queryset filtered for the current user's audience,
    or None if the table/model is unavailable.
    """
    if not (Notification and _table_exists(Notification)):
        return None
    if request.user.is_staff:
        return Notification.objects.filter(audience="ADMIN")
    return Notification.objects.filter(audience="AGENT", user=request.user)


# ---------------------------
# Views
# ---------------------------
@login_required
def feed(request: HttpRequest):
    """
    Returns latest notifications for the current user.
    Admins: ADMIN audience
    Agents: AGENT audience for self
    Optional:
      - ?since=<iso8601>
      - ?limit=<int> (default 50, max 200)
    """
    qs_all = _base_qs_for_user(request)
    now_iso = timezone.now().isoformat()

    # If notifications aren't ready, return an empty feed gracefully.
    if qs_all is None:
        return JsonResponse({"items": [], "unread": 0, "now": now_iso})

    # Parse optional filters & limits (do NOT slice before computing unread)
    since_s = request.GET.get("since")
    since = parse_datetime(since_s) if since_s else None
    try:
        limit = max(1, min(int(request.GET.get("limit", "50")), 200))
    except (TypeError, ValueError):
        limit = 50

    filtered = qs_all
    if since:
        filtered = filtered.filter(created_at__gt=since)

    # Compute unread BEFORE any slicing to avoid the sliceâ†’filter error
    unread = filtered.filter(read_at__isnull=True).count()

    # Now fetch the page of items
    items_qs = filtered.order_by("-created_at")[:limit]

    data = [
        {
            "id": n.id,
            "message": n.message,
            "level": n.level,
            "created_at": n.created_at.isoformat(),
            "read": n.is_read,
        }
        for n in items_qs
    ]

    return JsonResponse({"items": data, "unread": unread, "now": now_iso})


@login_required
def mark_read(request: HttpRequest):
    """
    POST:
      - id=<int>  mark one
      - all=1     mark visible set as read
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    qs = _base_qs_for_user(request)

    # If notifications aren't ready, succeed as a no-op so UI doesn't break.
    if qs is None:
        return JsonResponse({"ok": True, "noop": True})

    n_now = timezone.now()

    if request.POST.get("all") == "1":
        try:
            qs.filter(read_at__isnull=True).update(read_at=n_now)
            return JsonResponse({"ok": True})
        except (OperationalError, ProgrammingError):
            # Table might be mid-migrationâ€”treat as no-op.
            return JsonResponse({"ok": True, "noop": True})

    try:
        nid = int(request.POST.get("id", "0"))
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Invalid id")

    try:
        updated = qs.filter(pk=nid, read_at__isnull=True).update(read_at=n_now)
        return JsonResponse({"ok": bool(updated)})
    except (OperationalError, ProgrammingError):
        return JsonResponse({"ok": True, "noop": True})



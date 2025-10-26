# inventory/views_audit.py
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from typing import Dict, Optional, Tuple

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse, Http404
from django.shortcuts import get_object_or_404, render

from .models_audit import AuditLog


# ---------- Helpers ----------

def _digest(prev_hash: str, data: Dict) -> str:
    """Compute the row digest in the exact shape used when appending to the chain."""
    packed = json.dumps(data, sort_keys=True).encode()
    return hashlib.sha256(packed).hexdigest()


def _row_payload_for_hash(prev: str, row: AuditLog) -> Dict:
    """Rebuild the payload the writer used so recomputation matches exactly."""
    return {
        "prev": prev,
        "actor": getattr(row.actor, "pk", None),
        "ip": row.ip,
        "ua": row.ua,
        "entity": row.entity,
        "entity_id": row.entity_id,
        "action": row.action,
        "payload": row.payload,
    }


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    # Accept ISO-ish inputs like "2025-09-07" or "2025-09-07 13:20"
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _is_staff(user) -> bool:
    return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))


# ---------- Views ----------

@login_required
def verify_chain(request: HttpRequest):
    """
    Walk the entire AuditLog chain in ascending id order, recompute hashes,
    and detect the first break. Returns HTML by default, JSON if ?format=json.
    """
    ok = True
    broken_at: Optional[int] = None
    checked = 0

    prev = ""
    # Use iterator() to limit memory for long chains
    for row in AuditLog.objects.order_by("id").iterator():
        payload = _row_payload_for_hash(prev, row)
        recomputed = _digest(prev, payload)
        if recomputed != row.hash:
            ok = False
            broken_at = row.id
            break
        prev = row.hash
        checked += 1

    if request.GET.get("format") == "json":
        return JsonResponse({"ok": ok, "broken_at": broken_at, "checked": checked})

    return render(
        request,
        "inventory/audit_verify.html",
        {"ok": ok, "broken_at": broken_at, "checked": checked},
    )


@login_required
def audit_list(request: HttpRequest):
    """
    Paginated list with basic filters:
      - q: free-text over entity, entity_id, action, ip, ua
      - entity: exact match
      - actor: user id
      - action: CREATE|UPDATE|DELETE
      - start, end: datetimes (YYYY-MM-DD or YYYY-MM-DD HH:MM)
    """
    qs = AuditLog.objects.select_related("actor").order_by("-id")

    q = request.GET.get("q", "").strip()
    entity = request.GET.get("entity", "").strip()
    actor = request.GET.get("actor", "").strip()
    action = request.GET.get("action", "").strip().upper()
    start = _parse_date(request.GET.get("start"))
    end = _parse_date(request.GET.get("end"))

    if q:
        qs = qs.filter(
            Q(entity__icontains=q)
            | Q(entity_id__icontains=q)
            | Q(action__icontains=q)
            | Q(ip__icontains=q)
            | Q(ua__icontains=q)
        )

    if entity:
        qs = qs.filter(entity=entity)

    if actor:
        try:
            qs = qs.filter(actor_id=int(actor))
        except ValueError:
            pass

    if action in {"CREATE", "UPDATE", "DELETE"}:
        qs = qs.filter(action=action)

    if start:
        qs = qs.filter(created_at__gte=start)
    if end:
        qs = qs.filter(created_at__lte=end)

    page = max(int(request.GET.get("page", "1") or 1), 1)
    per_page = min(max(int(request.GET.get("per", "25") or 25), 1), 200)

    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(page)

    # Optional JSON for API consumers
    if request.GET.get("format") == "json":
        data = [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat(),
                "actor_id": getattr(r.actor, "pk", None),
                "actor": getattr(r.actor, "get_username", lambda: None)(),
                "ip": r.ip,
                "ua": r.ua,
                "entity": r.entity,
                "entity_id": r.entity_id,
                "action": r.action,
                "payload": r.payload,
                "prev_hash": r.prev_hash,
                "hash": r.hash,
            }
            for r in page_obj.object_list
        ]
        return JsonResponse(
            {
                "count": paginator.count,
                "num_pages": paginator.num_pages,
                "page": page_obj.number,
                "results": data,
            }
        )

    return render(
        request,
        "inventory/audit_list.html",
        {
            "page_obj": page_obj,
            "paginator": paginator,
            "filters": {
                "q": q,
                "entity": entity,
                "actor": actor,
                "action": action,
                "start": request.GET.get("start", ""),
                "end": request.GET.get("end", ""),
            },
        },
    )


@login_required
def audit_detail(request: HttpRequest, pk: int):
    """
    Show a single audit row and verify its local linkage with prev hash.
    """
    row = get_object_or_404(AuditLog.objects.select_related("actor"), pk=pk)

    # Recompute this row's digest given its prev_hash
    payload = _row_payload_for_hash(row.prev_hash or "", row)
    recomputed = _digest(row.prev_hash or "", payload)
    valid = (recomputed == row.hash)

    # Neighbor peek (for template convenience)
    prev_row = AuditLog.objects.filter(id__lt=row.id).order_by("-id").first()
    next_row = AuditLog.objects.filter(id__gt=row.id).order_by("id").first()

    if request.GET.get("format") == "json":
        return JsonResponse(
            {
                "id": row.id,
                "valid": valid,
                "recomputed": recomputed,
                "stored": row.hash,
                "prev_id": getattr(prev_row, "id", None),
                "next_id": getattr(next_row, "id", None),
            }
        )

    return render(
        request,
        "inventory/audit_detail.html",
        {
            "row": row,
            "valid": valid,
            "recomputed": recomputed,
            "prev_row": prev_row,
            "next_row": next_row,
        },
    )


@user_passes_test(_is_staff)
def audit_export_csv(request: HttpRequest) -> HttpResponse:
    """
    Staff-only CSV export honoring the same filters as audit_list.
    (Caps at 100k rows for safety unless ?limit=â€¦ provided up to 500k.)
    """
    qs = AuditLog.objects.select_related("actor").order_by("id")

    q = request.GET.get("q", "").strip()
    entity = request.GET.get("entity", "").strip()
    actor = request.GET.get("actor", "").strip()
    action = request.GET.get("action", "").strip().upper()
    start = _parse_date(request.GET.get("start"))
    end = _parse_date(request.GET.get("end"))
    limit = max(1, min(int(request.GET.get("limit", "100000") or 100000), 500000))

    if q:
        qs = qs.filter(
            Q(entity__icontains=q)
            | Q(entity_id__icontains=q)
            | Q(action__icontains=q)
            | Q(ip__icontains=q)
            | Q(ua__icontains=q)
        )
    if entity:
        qs = qs.filter(entity=entity)
    if actor:
        try:
            qs = qs.filter(actor_id=int(actor))
        except ValueError:
            pass
    if action in {"CREATE", "UPDATE", "DELETE"}:
        qs = qs.filter(action=action)
    if start:
        qs = qs.filter(created_at__gte=start)
    if end:
        qs = qs.filter(created_at__lte=end)

    # Stream CSV
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="audit_log.csv"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "id",
            "created_at",
            "actor_id",
            "actor_username",
            "ip",
            "ua",
            "entity",
            "entity_id",
            "action",
            "payload_json",
            "prev_hash",
            "hash",
        ]
    )

    count = 0
    for r in qs.iterator(chunk_size=2000):
        if count >= limit:
            break
        writer.writerow(
            [
                r.id,
                r.created_at.isoformat(),
                getattr(r.actor, "pk", None),
                getattr(r.actor, "get_username", lambda: None)(),
                r.ip,
                r.ua,
                r.entity,
                r.entity_id,
                r.action,
                json.dumps(r.payload, ensure_ascii=False),
                r.prev_hash,
                r.hash,
            ]
        )
        count += 1

    return response



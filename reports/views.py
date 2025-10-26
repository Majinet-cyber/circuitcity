# reports/views.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional, Any, Dict

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.template.loader import get_template
from django.utils import timezone

# These imports are fine to keep; we won't assume field names that could break.
from sales.models import Sale  # noqa
from inventory.models import InventoryItem  # noqa


# -------------------------------
# Auth helpers
# -------------------------------
def _is_staff_or_auditor(user) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    return user.groups.filter(name__in=["Admin", "Manager", "Auditor", "Auditors"]).exists()


# -------------------------------
# Filters
# -------------------------------
@dataclass
class ReportFilters:
    date_from: Optional[datetime]
    date_to: Optional[datetime]
    agent_id: Optional[int]
    model_q: Optional[str]
    channel: Optional[str]
    ads: Optional[str]  # "with", "without", or None

    @classmethod
    def from_request(cls, request: HttpRequest) -> "ReportFilters":
        g = request.GET

        def _make_aware(dt: Optional[datetime]) -> Optional[datetime]:
            if not dt:
                return None
            tz = timezone.get_current_timezone()
            return timezone.make_aware(dt, tz) if timezone.is_naive(dt) else dt.astimezone(tz)

        def parse_iso_date_or_datetime(val: str, *, end_of_day: bool = False) -> Optional[datetime]:
            """
            Accepts 'YYYY-MM-DD' or full ISO 'YYYY-MM-DDTHH:MM[:SS[.ffffff]]'.
            Returns timezone-aware datetime (local tz). For date-only:
            - start_of_day at 00:00:00
            - end_of_day at 23:59:59.999999 if end_of_day=True
            """
            val = (val or "").strip()
            if not val:
                return None
            try:
                # If only a date was provided, add a time component.
                if "T" not in val and " " not in val and len(val) == 10:
                    if end_of_day:
                        dt = datetime.fromisoformat(val)  # naive date -> midnight
                        dt = datetime.combine(dt.date(), time(23, 59, 59, 999999))
                    else:
                        dt = datetime.fromisoformat(val)  # naive date -> midnight
                        dt = datetime.combine(dt.date(), time(0, 0, 0, 0))
                else:
                    dt = datetime.fromisoformat(val)
            except Exception:
                return None
            return _make_aware(dt)

        date_from = parse_iso_date_or_datetime(g.get("date_from", ""), end_of_day=False)
        date_to = parse_iso_date_or_datetime(g.get("date_to", ""), end_of_day=True)

        # Normalize ordering if user swapped them
        if date_from and date_to and date_from > date_to:
            date_from, date_to = date_to, date_from

        return cls(
            date_from=date_from,
            date_to=date_to,
            agent_id=int(g.get("agent") or 0) or None,
            model_q=(g.get("model") or "").strip() or None,
            channel=(g.get("channel") or "").strip() or None,
            ads=(g.get("ads") or "").strip() or None,
        )


# -------------------------------
# Template resolving / rendering
# -------------------------------
def _resolve_template(candidates: list[str]) -> tuple[str, str]:
    """
    Returns (template_name, origin_path). Tries candidates in order.
    """
    last_error: Optional[Exception] = None
    for tpl in candidates:
        try:
            t = get_template(tpl)
            origin = getattr(getattr(t, "origin", None), "name", "(unknown origin)")
            # Print to console for fast feedback
            print(f">> REPORTS USING TEMPLATE {tpl}: {origin}")
            return tpl, origin
        except Exception as e:
            last_error = e
            continue
    # Nothing resolved; raise the last error to surface the issue.
    raise last_error or RuntimeError("No reports template could be resolved.")


def _render(request: HttpRequest, context: Dict[str, Any]) -> HttpResponse:
    """
    Renders the best-guess Reports template and attaches X-Template-Origin.
    Prefers 'ccreports/home.html' (new module), falls back to 'reports/home.html' (legacy).
    """
    tpl_name, origin = _resolve_template(["ccreports/home.html", "reports/home.html"])
    resp = render(request, tpl_name, context)
    resp["X-Template-Origin"] = origin
    resp["X-Template-Name"] = tpl_name
    return resp


# -------------------------------
# View
# -------------------------------
@login_required
@user_passes_test(_is_staff_or_auditor)
def reports_home(request: HttpRequest) -> HttpResponse:
    filters = ReportFilters.from_request(request)

    # Keep context minimal & safe. Add more metrics later if/when fields are confirmed.
    context: Dict[str, Any] = {
        "title": "Reports",
        "subtitle": "Overview",
        "filters": filters,
    }
    return _render(request, context)



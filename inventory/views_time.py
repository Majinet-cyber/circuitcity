from __future__ import annotations
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone

from tenants.utils import get_active_business, require_business
from tenants.models import Membership
from .models import Location
from .models_attendance import TimeLog, compute_attendance_outcome

def _agent_default_location(request) -> Location | None:
    # tie agent to the location they joined (you can store this on Membership if you like)
    _, biz_id = get_active_business(request)
    if not biz_id:
        return None

    # If Membership has a preferred location, use it; else first location / default
    mem = Membership.objects.filter(user=request.user, business_id=biz_id).first()
    if mem and hasattr(mem, "location") and mem.location_id:
        return mem.location

    # Fallback: prefer location with is_default if you added that, else first()
    qs = Location.objects.filter(business_id=biz_id)
    loc = qs.filter(name__icontains="store").first() or qs.first()
    return loc

@login_required
@require_http_methods(["GET", "POST"])
def time_checkin(request):
    gate = require_business(request)
    if gate:
        return gate

    _, biz_id = get_active_business(request)
    location = _agent_default_location(request)

    if request.method == "POST":
        kind = request.POST.get("kind", "ARRIVAL").upper()
        lat = request.POST.get("lat") or None
        lon = request.POST.get("lon") or None

        tl = TimeLog.objects.create(
            business_id=biz_id,
            user=request.user,
            location=location,
            kind=kind,
            lat=lat, lon=lon,
        )

        # Rewards/penalties (only on ARRIVAL)
        outcome = compute_attendance_outcome(tl.ts, kind)
        if outcome.net_adjustment:
            # You already have wallets/earnings; record there if desired.
            # For now, we attach a flash message + show on logs tables.
            if outcome.net_adjustment > 0:
                messages.success(request, f"+MWK {outcome.net_adjustment:,} attendance bonus applied.")
            else:
                messages.warning(request, f"âˆ’MWK {abs(outcome.net_adjustment):,} late deduction applied.")

        messages.info(request, f"{kind.title()} recorded.")
        return redirect("inventory:my_time_logs")

    return render(request, "inventory/time_checkin.html", {
        "location": location,
    })

@login_required
def my_time_logs(request):
    gate = require_business(request)
    if gate:
        return gate
    _, biz_id = get_active_business(request)

    logs = TimeLog.objects.filter(business_id=biz_id, user=request.user).select_related("location")[:200]
    return render(request, "inventory/time_logs.html", {"logs": logs})



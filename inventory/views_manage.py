from __future__ import annotations
from datetime import timedelta
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_http_methods
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Count, Sum
from django.utils import timezone

from tenants.utils import require_role, get_active_business
from .models_attendance import TimeLog, compute_attendance_outcome
from .models import Location
from accounts.models import User  # adjust if your User path differs
from .models_inventory import InventoryItem  # if you have it split; else from .models import InventoryItem
from .models_sales import Sale  # adjust to your project

def _is_manager(user):
    # reuse your role checks; fallback:
    return getattr(user, "is_staff", False) or user.groups.filter(name__iexact="manager").exists()

@login_required
def manage_time_logs(request):
    # managers only
    if not _is_manager(request.user):
        messages.error(request, "Managers only.")
        return redirect("/")

    _, biz_id = get_active_business(request)
    since = timezone.now() - timedelta(days=14)
    logs = TimeLog.objects.filter(business_id=biz_id, ts__gte=since).select_related("user", "location")

    # annotate computed adjustments for display
    enriched = []
    for tl in logs:
        outcome = compute_attendance_outcome(tl.ts, tl.kind)
        enriched.append((tl, outcome))

    return render(request, "inventory/manage_time_logs.html", {"logs": enriched})

@login_required
@require_http_methods(["GET","POST"])
def location_geofence(request, pk: int):
    if not _is_manager(request.user):
        messages.error(request, "Managers only.")
        return redirect("/")

    loc = get_object_or_404(Location, pk=pk)
    if request.method == "POST":
        loc.latitude = request.POST.get("latitude") or None
        loc.longitude = request.POST.get("longitude") or None
        loc.geofence_radius_m = int(request.POST.get("radius") or 150)
        loc.save(update_fields=["latitude","longitude","geofence_radius_m"])
        messages.success(request, "Location GPS saved.")
        return redirect("inventory:location_geofence", pk=loc.pk)

    return render(request, "inventory/location_geofence.html", {"loc": loc})

@login_required
def toggle_geofence_launch(request, pk: int):
    if not _is_manager(request.user):
        messages.error(request, "Managers only.")
        return redirect("/")

    loc = get_object_or_404(Location, pk=pk)
    loc.geofence_enabled = not loc.geofence_enabled
    loc.save(update_fields=["geofence_enabled"])
    messages.success(request, f"Geofence {'LAUNCHED' if loc.geofence_enabled else 'paused'} for {loc.name}.")
    return redirect("inventory:location_geofence", pk=pk)

@login_required
def manager_agents(request):
    if not _is_manager(request.user):
        messages.error(request, "Managers only.")
        return redirect("/")

    _, biz_id = get_active_business(request)
    # â€œActive agentsâ€ = users with recent logs or sales
    recent = timezone.now() - timedelta(days=7)
    user_ids = set(TimeLog.objects.filter(business_id=biz_id, ts__gte=recent).values_list("user_id", flat=True))
    # fallback to all business members if needed
    agents = User.objects.filter(id__in=user_ids).order_by("first_name","last_name")
    return render(request, "inventory/manager_agents.html", {"agents": agents})

@login_required
def manager_agent_detail(request, user_id: int):
    if not _is_manager(request.user):
        messages.error(request, "Managers only.")
        return redirect("/")

    _, biz_id = get_active_business(request)
    agent = get_object_or_404(User, pk=user_id)
    logs = TimeLog.objects.filter(business_id=biz_id, user=agent).select_related("location").order_by("-ts")[:200]

    # Example aggregates (adapt to your models)
    stock_count = InventoryItem.objects.filter(business_id=biz_id, owner=agent, is_active=True).count()
    sales_qs = Sale.objects.filter(business_id=biz_id, seller=agent)
    total_sales = sales_qs.count()
    total_earnings = sales_qs.aggregate(s=Sum("profit"))["s"] or 0

    # Compute attendance net total for display
    net = 0
    enriched = []
    for tl in logs:
        oc = compute_attendance_outcome(tl.ts, tl.kind)
        net += int(oc.net_adjustment)
        enriched.append((tl, oc))

    return render(request, "inventory/manager_agent_detail.html", {
        "agent": agent,
        "stock_count": stock_count,
        "total_sales": total_sales,
        "total_earnings": total_earnings,
        "logs": enriched,
        "attendance_net": net,
    })



# inventory/verticals/farm_locations.py
"""
Farm Locations view for managing farm fields, plots, and areas.
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.models import Location
from tenants.utils import require_business
from inventory.verticals import base


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def locations_list(request: HttpRequest) -> HttpResponse:
    """
    Farm Locations list page.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    locations = Location.objects.filter(business=business).order_by("name")
    
    ctx.update({
        "active_tab": "locations",
        "hero_title": "Farm Locations",
        "hero_blurb": "Manage your farm fields, plots, and areas",
        "locations": locations,
    })
    
    return render(request, "verticals/farm/locations_list.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
@require_http_methods(["GET", "POST"])
def locations_create(request: HttpRequest) -> HttpResponse:
    """Create a new farm location."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    if request.method == "POST":
        try:
            location = Location.objects.create(
                business=business,
                name=request.POST.get("name", ""),
                address=request.POST.get("address", ""),
                notes=request.POST.get("notes", ""),
            )
            messages.success(request, f"Location '{location.name}' created successfully.")
            return redirect("verticals:farm_locations")
        except Exception as e:
            messages.error(request, f"Error creating location: {e}")
    
    ctx.update({
        "active_tab": "locations",
        "hero_title": "Add Location",
    })
    
    return render(request, "verticals/farm/locations_form.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
@require_http_methods(["GET", "POST"])
def locations_edit(request: HttpRequest, location_id: int) -> HttpResponse:
    """Edit an existing farm location."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    location = get_object_or_404(Location, id=location_id, business=business)
    
    if request.method == "POST":
        try:
            location.name = request.POST.get("name", location.name)
            location.address = request.POST.get("address", location.address)
            location.notes = request.POST.get("notes", location.notes)
            location.save()
            messages.success(request, f"Location '{location.name}' updated successfully.")
            return redirect("verticals:farm_locations")
        except Exception as e:
            messages.error(request, f"Error updating location: {e}")
    
    ctx.update({
        "active_tab": "locations",
        "hero_title": f"Edit Location: {location.name}",
        "location": location,
    })
    
    return render(request, "verticals/farm/locations_form.html", ctx)

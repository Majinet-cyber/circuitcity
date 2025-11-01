# tenants/views_people.py
from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

# Your project’s decorator helpers (fallback to no-ops if missing)
try:
    from tenants.utils import require_business, require_role  # type: ignore
except Exception:  # pragma: no cover
    def require_business(view_func):  # type: ignore
        return view_func

    def require_role(_role: str):  # type: ignore
        def _wrap(view_func):
            return view_func
        return _wrap

from inventory.models import Location
from .forms_people import LocationForm


@login_required
@require_business
@require_role("MANAGER")
def location_create(request: HttpRequest) -> HttpResponse:
    """
    Create a Location scoped to the current business on the request.
    """
    if request.method == "POST":
        form = LocationForm(request.POST)
        if form.is_valid():
            loc = form.save(commit=False)
            # Ensure business scoping is enforced server-side
            if hasattr(loc, "business"):
                loc.business = getattr(request, "business", None)
            loc.save()
            messages.success(request, "Location created.")
            return redirect("tenants:locations_index")
    else:
        form = LocationForm()

    return render(
        request,
        "tenants/location_form.html",
        {"form": form, "mode": "create"},
    )


@login_required
@require_business
@require_role("MANAGER")
def location_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Edit a Location that belongs to the current business.
    """
    loc = get_object_or_404(Location, business=request.business, pk=pk)

    if request.method == "POST":
        form = LocationForm(request.POST, instance=loc)
        if form.is_valid():
            form.save()
            messages.success(request, "Location updated.")
            return redirect("tenants:locations_index")
    else:
        form = LocationForm(instance=loc)

    return render(
        request,
        "tenants/location_form.html",
        {"form": form, "mode": "edit", "loc": loc},
    )


@login_required
@require_business
@require_role("MANAGER")
def location_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Delete a Location that belongs to the current business.
    """
    loc = get_object_or_404(Location, business=request.business, pk=pk)

    if request.method == "POST":
        name = getattr(loc, "name", "Location")
        loc.delete()
        messages.success(request, f"Location '{name}' deleted.")
        return redirect("tenants:locations_index")

    return render(
        request,
        "tenants/location_delete_confirm.html",
        {"loc": loc},
    )


@login_required
@require_business
@require_role("MANAGER")
def location_set_default(request: HttpRequest, pk: int) -> HttpResponse:
    """
    If your Location model supports an `is_default` boolean, mark this one as default
    and clear the default flag from others in the same business.
    """
    loc = get_object_or_404(Location, business=request.business, pk=pk)

    if not hasattr(loc, "is_default"):
        messages.error(request, "Default flag is not supported on the Location model.")
        return redirect("tenants:locations_index")

    # Clear others then set this one
    Location.objects.filter(business=request.business).update(is_default=False)
    loc.is_default = True
    loc.save(update_fields=["is_default"])
    messages.success(request, f"'{loc.name}' set as default.")
    return redirect("tenants:locations_index")

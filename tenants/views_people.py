from __future__ import annotations
return redirect("tenants:locations_index")
else:
form = LocationForm()
return render(request, "tenants/location_form.html", {"form": form, "mode": "create"})


@login_required
@require_business
@require_role("MANAGER")
def location_edit(request: HttpRequest, pk: int) -> HttpResponse:
loc = get_object_or_404(Location, business=request.business, pk=pk)
if request.method == "POST":
form = LocationForm(request.POST, instance=loc)
if form.is_valid():
form.save()
messages.success(request, "Location updated.")
return redirect("tenants:locations_index")
else:
form = LocationForm(instance=loc)
return render(request, "tenants/location_form.html", {"form": form, "mode": "edit", "loc": loc})


@login_required
@require_business
@require_role("MANAGER")
def location_delete(request: HttpRequest, pk: int) -> HttpResponse:
loc = get_object_or_404(Location, business=request.business, pk=pk)
if request.method == "POST":
name = loc.name
loc.delete()
messages.success(request, f"Location â€˜{name}â€™ deleted.")
return redirect("tenants:locations_index")
return render(request, "tenants/location_delete_confirm.html", {"loc": loc})


@login_required
@require_business
@require_role("MANAGER")
def location_set_default(request: HttpRequest, pk: int) -> HttpResponse:
"""If your Location model has is_default, toggle it here."""
loc = get_object_or_404(Location, business=request.business, pk=pk)
if not hasattr(loc, "is_default"):
messages.error(request, "Default flag not supported on Location model.")
return redirect("tenants:locations_index")
# Clear others then set this one
Location.objects.filter(business=request.business).update(is_default=False)
loc.is_default = True
loc.save(update_fields=["is_default"])
messages.success(request, f"â€˜{loc.name}â€™ set as default.")
return redirect("tenants:locations_index")


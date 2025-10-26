# hq/views_locations.py  (manager scope)
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect
from timelogs.models import Location

@login_required
def store_locations(request):
    biz = request.user.profile.active_business  # manager's business
    if request.method == "POST":
        Location.objects.update_or_create(
            business=biz, name=request.POST.get("name","Main"),
            defaults=dict(lat=request.POST["lat"], lng=request.POST["lng"], radius_m=request.POST.get("radius_m",60), created_by=request.user)
        )
        return redirect("hq:store_locations")
    return render(request, "hq/locations.html", {"locations": Location.objects.filter(business=biz)})



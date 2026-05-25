from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import DeviceDeal


@login_required
def all_deals(request):
    deals = DeviceDeal.objects.filter(is_active=True).order_by("brand__name", "model_name")
    return render(request, "deals/all_deals.html", {"deals": deals})
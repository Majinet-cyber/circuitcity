from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from applications.models import FinancingApplication


@login_required
def home(request):
    active_count = FinancingApplication.objects.filter(
        created_by=request.user,
        status__in=[
            "started",
            "customer_details",
            "device_selection",
            "kyc",
            "kyc_capture",
            "location_details",
            "work_details",
            "signature",
            "correction_requested",
            "imei_required",
            "submitted",
            "under_review",
        ],
    ).count()

    context = {
        "active_count": active_count,
    }
    return render(request, "dashboard/home.html", context)

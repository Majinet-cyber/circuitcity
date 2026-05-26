from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render
from applications.models import FinancingApplication
from commissions.models import Commission
from rewards.models import SpinWallet


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
    earnings_total = (
        Commission.objects.filter(user=request.user)
        .exclude(status=Commission.STATUS_CANCELLED)
        .aggregate(total=Sum("amount"))["total"]
        or 0
    )
    spin_wallet, _ = SpinWallet.objects.get_or_create(user=request.user)

    context = {
        "active_count": active_count,
        "earnings_total": earnings_total,
        "spin_wallet": spin_wallet,
    }
    return render(request, "dashboard/home.html", context)

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.views import redirect_to_login
from django.db.models import Sum
from django.shortcuts import redirect, render
from accounts.decorators import hq_required, merchant_required
from accounts.utils import role_redirect_url
from applications.models import FinancingApplication
from commissions.models import Commission
from contracts.models import Contract
from rewards.models import SpinWallet


def home(request):
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    return redirect(role_redirect_url(request.user))


@merchant_required
def merchant_dashboard(request):
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


@hq_required
def hq_dashboard(request):
    User = get_user_model()
    underwriter_group_ids = Group.objects.filter(name__in=["Underwriter", "Manager"]).values_list("id", flat=True)
    merchant_group = Group.objects.filter(name="Merchant").first()

    total_merchants = User.objects.filter(groups=merchant_group).distinct().count() if merchant_group else 0
    total_underwriters = (
        User.objects.filter(groups__id__in=underwriter_group_ids).distinct().count()
        + User.objects.filter(is_staff=True, is_superuser=False).exclude(groups__id__in=underwriter_group_ids).count()
    )
    total_commissions = (
        Commission.objects.exclude(status=Commission.STATUS_CANCELLED).aggregate(total=Sum("amount"))["total"]
        or 0
    )

    context = {
        "total_merchants": total_merchants,
        "total_underwriters": total_underwriters,
        "pending_review_count": FinancingApplication.objects.filter(status="pending_review").count(),
        "under_review_count": FinancingApplication.objects.filter(status="under_review").count(),
        "approved_count": FinancingApplication.objects.filter(status="approved").count(),
        "completed_contracts_count": Contract.objects.filter(status=Contract.STATUS_COMPLETE).count(),
        "total_commissions": total_commissions,
    }
    return render(request, "dashboard/hq.html", context)

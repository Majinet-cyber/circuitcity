from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.views import redirect_to_login
from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from accounts.decorators import hq_required, merchant_required
from accounts.forms import HQUserForm
from accounts.utils import primary_role, role_redirect_url
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
    underwriter_group_ids = Group.objects.filter(name="Underwriter").values_list("id", flat=True)
    merchant_group = Group.objects.filter(name="Merchant").first()

    total_merchants = User.objects.filter(groups=merchant_group).distinct().count() if merchant_group else 0
    total_underwriters = User.objects.filter(groups__id__in=underwriter_group_ids).distinct().count()
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


@hq_required
def hq_users(request):
    User = get_user_model()
    if request.method == "POST":
        form = HQUserForm(request.POST, creating=True)
        if form.is_valid():
            form.save()
            messages.success(request, "User created.")
            return redirect("hq_users")
    else:
        form = HQUserForm(creating=True)

    users = User.objects.select_related("userprofile").prefetch_related("groups").order_by("username")
    rows = [{"user": user, "role": primary_role(user) or "unassigned"} for user in users]
    return render(request, "dashboard/hq_users.html", {"form": form, "rows": rows})


@hq_required
def hq_user_edit(request, user_id):
    User = get_user_model()
    user_obj = get_object_or_404(User.objects.select_related("userprofile").prefetch_related("groups"), id=user_id)
    if request.method == "POST":
        form = HQUserForm(request.POST, instance=user_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "User updated.")
            return redirect("hq_users")
    else:
        form = HQUserForm(instance=user_obj)
    return render(request, "dashboard/hq_user_edit.html", {"form": form, "user_obj": user_obj})


@hq_required
def hq_deals(request):
    return render(request, "dashboard/hq_section.html", {"title": "Deals", "body": "Use Django Admin for detailed deal management."})


@hq_required
def hq_applications(request):
    apps = FinancingApplication.objects.select_related("created_by", "claimed_by").order_by("-created_at")[:50]
    return render(request, "dashboard/hq_applications.html", {"apps": apps})


@hq_required
def hq_commissions(request):
    commissions = Commission.objects.select_related("user", "application").order_by("-created_at")[:50]
    return render(request, "dashboard/hq_commissions.html", {"commissions": commissions})

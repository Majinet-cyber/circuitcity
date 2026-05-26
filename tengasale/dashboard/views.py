from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.views import redirect_to_login
from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from accounts.decorators import hq_required, merchant_required
from accounts.forms import HQUserForm
from accounts.utils import primary_role, role_redirect_url
from core.business_hours import business_hours_context
from applications.models import FinancingApplication
from commissions.models import Commission
from contracts.models import Contract
from rewards.models import SpinWallet

MAX_ACTIVE_UNDERWRITER_REVIEWS = 5


def home(request):
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    return redirect(role_redirect_url(request.user))


def merchant_dashboard_context(user):
    active_count = FinancingApplication.objects.filter(
        created_by=user,
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
        Commission.objects.filter(user=user)
        .exclude(status=Commission.STATUS_CANCELLED)
        .aggregate(total=Sum("amount"))["total"]
        or 0
    )
    spin_wallet, _ = SpinWallet.objects.get_or_create(user=user)

    return {
        "active_count": active_count,
        "earnings_total": earnings_total,
        "spin_wallet": spin_wallet,
        **business_hours_context(),
    }


@merchant_required
def merchant_dashboard(request):
    context = merchant_dashboard_context(request.user)
    return render(request, "dashboard/home.html", context)


def developer_preview_required(view_func):
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if settings.DEBUG and request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        messages.warning(request, "Developer previews are not available.")
        return redirect(role_redirect_url(request.user))

    return wrapped


@hq_required
def hq_dashboard(request):
    User = get_user_model()
    total_merchants = User.objects.filter(profile__role="merchant").count()
    total_underwriters = User.objects.filter(profile__role="underwriter").count()
    total_hq_users = User.objects.filter(profile__role="hq").count()
    rejected_count = FinancingApplication.objects.filter(status="rejected").count()
    waiting_count = FinancingApplication.objects.filter(
        status__in=["submitted", "pending_review", "resubmitted"],
        claimed_by__isnull=True,
    ).count()
    total_commissions = (
        Commission.objects.exclude(status=Commission.STATUS_CANCELLED).aggregate(total=Sum("amount"))["total"]
        or 0
    )

    context = {
        "total_merchants": total_merchants,
        "total_underwriters": total_underwriters,
        "total_hq_users": total_hq_users,
        "pending_review_count": FinancingApplication.objects.filter(status="pending_review").count(),
        "under_review_count": FinancingApplication.objects.filter(status="under_review").count(),
        "approved_count": FinancingApplication.objects.filter(status="approved").count(),
        "rejected_count": rejected_count,
        "completed_contracts_count": Contract.objects.filter(status=Contract.STATUS_COMPLETE).count(),
        "waiting_count": waiting_count,
        "total_commissions": total_commissions,
        "show_developer_preview": settings.DEBUG and request.user.is_superuser,
    }
    return render(request, "dashboard/hq.html", context)


@hq_required
def hq_users(request):
    User = get_user_model()
    if request.method == "POST":
        form = HQUserForm(request.POST, creating=True)
        if form.is_valid():
            form.save()
            messages.success(request, "User created successfully.")
            return redirect("hq_users")
    else:
        form = HQUserForm(creating=True)

    users = User.objects.select_related("profile").prefetch_related("groups").order_by("username")
    rows = [{"user": user, "role": primary_role(user) or "unassigned"} for user in users]
    return render(request, "dashboard/hq_users.html", {"form": form, "rows": rows})


@hq_required
def hq_user_edit(request, user_id):
    User = get_user_model()
    user_obj = get_object_or_404(User.objects.select_related("profile").prefetch_related("groups"), id=user_id)
    if request.method == "POST":
        form = HQUserForm(request.POST, instance=user_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "User updated successfully.")
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
    return render(
        request,
        "dashboard/hq_applications.html",
        {
            "title": "Applications",
            "subtitle": "Review submitted applications across the platform.",
            "apps": apps,
        },
    )


@hq_required
def hq_underwriter_queue(request):
    apps = (
        FinancingApplication.objects.select_related("created_by", "claimed_by")
        .filter(status__in=["pending_review", "under_review", "approved", "rejected"])
        .order_by("-submitted_at", "-created_at")[:50]
    )
    return render(
        request,
        "dashboard/hq_applications.html",
        {
            "title": "Underwriter Queue",
            "subtitle": "Monitor submitted, claimed, and reviewed applications.",
            "apps": apps,
        },
    )


@hq_required
def hq_commissions(request):
    commissions = Commission.objects.select_related("user", "application").order_by("-created_at")[:50]
    return render(request, "dashboard/hq_commissions.html", {"commissions": commissions})


@hq_required
def hq_reports(request):
    return render(
        request,
        "dashboard/hq_section.html",
        {
            "title": "Reports / Analytics",
            "body": "Reports and analytics will appear here as TengaSale reporting expands.",
        },
    )


@developer_preview_required
def hq_merchant_preview(request):
    context = merchant_dashboard_context(request.user)
    context["is_developer_preview"] = True
    return render(request, "dashboard/home.html", context)


@developer_preview_required
def hq_underwriter_preview(request):
    my_active = FinancingApplication.objects.filter(
        claimed_by=request.user,
        status="under_review",
    )
    pending_count = FinancingApplication.objects.filter(
        status="pending_review",
        claimed_by__isnull=True,
    ).count()
    pending_queue = FinancingApplication.objects.select_related("created_by").filter(
        status="pending_review",
        claimed_by__isnull=True,
    ).order_by("submitted_at", "id")[:10]
    completed_reviews = FinancingApplication.objects.filter(
        reviewed_by=request.user,
        status__in=["approved", "completed", "contract_complete"],
    ).order_by("-reviewed_at")[:10]
    underwriter_earnings = (
        Commission.objects.filter(user=request.user, role=Commission.ROLE_MANAGER)
        .exclude(status=Commission.STATUS_CANCELLED)
        .aggregate(total=Sum("amount"))["total"]
        or 0
    )
    return render(
        request,
        "approvals/home.html",
        {
            "my_active": my_active,
            "pending_count": pending_count,
            "pending_queue": pending_queue,
            "completed_reviews": completed_reviews,
            "active_count": my_active.count(),
            "max_active": MAX_ACTIVE_UNDERWRITER_REVIEWS,
            "underwriter_earnings": underwriter_earnings,
            "can_claim": pending_count > 0 and my_active.count() < MAX_ACTIVE_UNDERWRITER_REVIEWS,
            "is_developer_preview": True,
        },
    )

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.views import redirect_to_login
from django.contrib import messages
from django.db.models import Count, Sum, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from accounts.decorators import hq_required, merchant_required
from accounts.forms import HQUserForm
from accounts.utils import primary_role, role_redirect_url
from core.business_hours import business_hours_context
from applications.models import FinancingApplication
from commissions.models import Commission, MerchantContractPayout
from contracts.models import Contract
from financing.models import Device, DeviceCommand, FinancingContract, PaymentRecord
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
    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    merchant_contracts = FinancingContract.objects.filter(created_by=user)
    pending_payments = PaymentRecord.objects.select_related("customer", "contract", "contract__device").filter(
        contract__created_by=user,
        verification_status=PaymentRecord.STATUS_PENDING,
    )
    recent_contracts = merchant_contracts.select_related("customer", "device").order_by("-created_at")[:5]
    overdue_customers = merchant_contracts.select_related("customer", "device").filter(
        status__in=[
            FinancingContract.STATUS_OVERDUE,
            FinancingContract.STATUS_LOCKED,
            FinancingContract.STATUS_DEFAULTED,
        ]
    )[:5]
    command_history = DeviceCommand.objects.select_related("device", "contract", "contract__customer").filter(
        contract__created_by=user
    )[:5]

    # New-style merchant payout data (MerchantContractPayout from portal contracts)
    contract_payouts = MerchantContractPayout.objects.filter(merchant=user).order_by("-created_at")
    payout_pending = contract_payouts.filter(status=MerchantContractPayout.STATUS_PENDING)
    payout_paid = contract_payouts.filter(status=MerchantContractPayout.STATUS_PAID)
    merchant_payout_summary = {
        "pending_count": payout_pending.count(),
        "pending_total": payout_pending.aggregate(t=Sum("total_payable"))["t"] or 0,
        "paid_count": payout_paid.count(),
        "paid_total": payout_paid.aggregate(t=Sum("total_payable"))["t"] or 0,
        "recent": contract_payouts[:5],
    }

    return {
        "active_count": active_count,
        "earnings_total": earnings_total,
        "spin_wallet": spin_wallet,
        "merchant_payout_summary": merchant_payout_summary,
        "device_financing_stats": {
            "total_financed_devices": Device.objects.filter(financing_contract__created_by=user).count(),
            "active_contracts": merchant_contracts.filter(status=FinancingContract.STATUS_ACTIVE).count(),
            "overdue_contracts": merchant_contracts.filter(status=FinancingContract.STATUS_OVERDUE).count(),
            "locked_devices": Device.objects.filter(
                financing_contract__created_by=user,
                status=Device.STATUS_LOCKED,
            ).count(),
            "payments_pending_verification": pending_payments.count(),
            "payments_verified_this_month": PaymentRecord.objects.filter(
                contract__created_by=user,
                verification_status=PaymentRecord.STATUS_VERIFIED,
                verified_at__gte=month_start,
            ).count(),
            "expected_monthly_collections": (
                merchant_contracts.filter(status=FinancingContract.STATUS_ACTIVE).aggregate(
                    total=Sum("monthly_payment_amount")
                )["total"]
                or 0
            ),
            "default_risk_count": merchant_contracts.filter(
                status__in=[FinancingContract.STATUS_OVERDUE, FinancingContract.STATUS_LOCKED]
            ).count(),
        },
        "recent_financing_contracts": recent_contracts,
        "overdue_financing_customers": overdue_customers,
        "pending_financing_payments": pending_payments[:5],
        "device_command_history": command_history,
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
    from portal.models import PaymentContract, PaymentTransaction
    from commissions.models import MerchantContractPayout, CommissionLedger
    from decimal import Decimal

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

    today = timezone.now().date()
    paid_today = (
        PaymentTransaction.objects.filter(status="paid", paid_at__date=today)
        .aggregate(t=Sum("amount"))["t"] or 0
    )
    collections_today = (
        PaymentTransaction.objects.filter(status="paid", paid_at__date=today)
        .aggregate(t=Sum("amount"))["t"] or Decimal("0")
    )
    sales_today = FinancingApplication.objects.filter(
        submitted_at__date=today,
    ).count()
    active_contracts_count = PaymentContract.objects.filter(status="active").count()
    overdue_contracts_count = PaymentContract.objects.filter(status__in=["overdue", "locked"]).count()
    merchant_payout_pending = (
        MerchantContractPayout.objects.filter(status="pending")
        .aggregate(t=Sum("total_payable"))["t"] or 0
    )
    # Approval conversion rate
    total_reviewed = FinancingApplication.objects.filter(
        status__in=["approved", "rejected"]
    ).count()
    approved_count_total = FinancingApplication.objects.filter(status="approved").count()
    approval_rate = round((approved_count_total / total_reviewed * 100) if total_reviewed else 0, 1)

    # UW commission payout liability (pending)
    from commissions.models import UnderwriterMonthlyPayout
    uw_payout_liability = (
        UnderwriterMonthlyPayout.objects.filter(status="pending")
        .aggregate(t=Sum("net_amount"))["t"] or Decimal("0")
    )
    # Device lock exposure (active + overdue)
    lock_exposure_count = PaymentContract.objects.filter(
        status__in=["active", "overdue", "locked"]
    ).count()

    context = {
        "total_merchants": total_merchants,
        "total_underwriters": total_underwriters,
        "total_hq_users": total_hq_users,
        "pending_review_count": FinancingApplication.objects.filter(status="pending_review").count(),
        "under_review_count": FinancingApplication.objects.filter(status="under_review").count(),
        "approved_count": approved_count_total,
        "rejected_count": rejected_count,
        "completed_contracts_count": Contract.objects.filter(status=Contract.STATUS_COMPLETE).count(),
        "waiting_count": waiting_count,
        "total_commissions": total_commissions,
        "show_developer_preview": settings.DEBUG and request.user.is_superuser,
        "paid_today": paid_today,
        "active_contracts_count": active_contracts_count,
        "overdue_contracts_count": overdue_contracts_count,
        "merchant_payout_pending": merchant_payout_pending,
        # Command Pulse
        "collections_today": collections_today,
        "sales_today": sales_today,
        "approval_rate": approval_rate,
        "uw_payout_liability": uw_payout_liability,
        "lock_exposure_count": lock_exposure_count,
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
    from deals.models import DeviceBrand, DeviceDeal
    from decimal import Decimal, InvalidOperation
    from core.models import AuditLog

    msg = None
    msg_type = "info"

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "add_deal":
            try:
                brand_id = request.POST.get("brand_id")
                brand = DeviceBrand.objects.get(pk=brand_id)
                deal = DeviceDeal(
                    brand=brand,
                    model_name=request.POST.get("model_name", "").strip(),
                    specs=request.POST.get("specs", "").strip(),
                    cash_price=Decimal(request.POST.get("cash_price", "0") or "0"),
                    min_cash_price=Decimal(request.POST.get("min_cash_price", "0") or "0"),
                    max_cash_price=Decimal(request.POST.get("max_cash_price", "0") or "0"),
                    default_cash_price=Decimal(request.POST.get("default_cash_price", "0") or "0"),
                    deposit_percent=Decimal(request.POST.get("deposit_percent", "13") or "13"),
                    loan_multiplier=Decimal(request.POST.get("loan_multiplier", "2.5") or "2.5"),
                    term_months=int(request.POST.get("term_months", "12") or "12"),
                    is_active="is_active" in request.POST,
                    is_featured="is_featured" in request.POST,
                    stock_status=request.POST.get("stock_status", "in_stock"),
                    lock_provider=request.POST.get("lock_provider", ""),
                    country=request.POST.get("country", "MW").strip() or "MW",
                    notes=request.POST.get("notes", "").strip(),
                )
                deal.full_clean()
                deal.save()
                AuditLog.objects.create(
                    user=request.user,
                    action="hq_deal_add",
                    object_type="DeviceDeal",
                    object_id=str(deal.pk),
                    detail={"brand": brand.name, "model": deal.model_name},
                )
                msg = f"Deal '{deal}' created successfully."
                msg_type = "success"
            except Exception as exc:
                msg = f"Error creating deal: {exc}"
                msg_type = "error"

        elif action == "edit_deal":
            deal_id = request.POST.get("deal_id")
            try:
                deal = DeviceDeal.objects.get(pk=deal_id)
                brand_id = request.POST.get("brand_id")
                deal.brand = DeviceBrand.objects.get(pk=brand_id)
                deal.model_name = request.POST.get("model_name", deal.model_name).strip()
                deal.specs = request.POST.get("specs", deal.specs).strip()
                deal.cash_price = Decimal(request.POST.get("cash_price") or str(deal.cash_price))
                deal.min_cash_price = Decimal(request.POST.get("min_cash_price") or str(deal.min_cash_price))
                deal.max_cash_price = Decimal(request.POST.get("max_cash_price") or str(deal.max_cash_price))
                deal.default_cash_price = Decimal(request.POST.get("default_cash_price") or str(deal.default_cash_price))
                deal.deposit_percent = Decimal(request.POST.get("deposit_percent") or str(deal.deposit_percent))
                deal.loan_multiplier = Decimal(request.POST.get("loan_multiplier") or str(deal.loan_multiplier))
                deal.term_months = int(request.POST.get("term_months") or str(deal.term_months))
                deal.is_active = "is_active" in request.POST
                deal.is_featured = "is_featured" in request.POST
                deal.stock_status = request.POST.get("stock_status", deal.stock_status)
                deal.lock_provider = request.POST.get("lock_provider", deal.lock_provider)
                deal.country = request.POST.get("country", deal.country).strip() or "MW"
                deal.notes = request.POST.get("notes", deal.notes).strip()
                deal.full_clean()
                deal.save()
                AuditLog.objects.create(
                    user=request.user,
                    action="hq_deal_edit",
                    object_type="DeviceDeal",
                    object_id=str(deal.pk),
                    detail={"model": deal.model_name},
                )
                msg = f"Deal '{deal}' updated."
                msg_type = "success"
            except Exception as exc:
                msg = f"Error updating deal: {exc}"
                msg_type = "error"

        elif action == "toggle_deal":
            deal_id = request.POST.get("deal_id")
            try:
                deal = DeviceDeal.objects.get(pk=deal_id)
                deal.is_active = not deal.is_active
                deal.save(update_fields=["is_active"])
                AuditLog.objects.create(
                    user=request.user,
                    action="hq_deal_toggle",
                    object_type="DeviceDeal",
                    object_id=str(deal.pk),
                    detail={"is_active": deal.is_active},
                )
                msg = f"Deal '{deal}' {'activated' if deal.is_active else 'deactivated'}."
                msg_type = "success"
            except Exception as exc:
                msg = f"Error: {exc}"
                msg_type = "error"

        elif action == "add_brand":
            brand_name = request.POST.get("brand_name", "").strip()
            if brand_name:
                brand, created = DeviceBrand.objects.get_or_create(name=brand_name)
                msg = f"Brand '{brand_name}' {'created' if created else 'already exists'}."
                msg_type = "success" if created else "info"
            else:
                msg = "Brand name is required."
                msg_type = "error"

    search = request.GET.get("search", "").strip()
    brand_filter = request.GET.get("brand", "")
    status_filter = request.GET.get("status", "")

    deals_qs = DeviceDeal.objects.select_related("brand").order_by("brand__name", "model_name")
    if search:
        deals_qs = deals_qs.filter(
            Q(model_name__icontains=search)
            | Q(specs__icontains=search)
            | Q(brand__name__icontains=search)
        )
    if brand_filter:
        deals_qs = deals_qs.filter(brand_id=brand_filter)
    if status_filter == "active":
        deals_qs = deals_qs.filter(is_active=True)
    elif status_filter == "inactive":
        deals_qs = deals_qs.filter(is_active=False)

    brands = DeviceBrand.objects.order_by("name")

    return render(request, "dashboard/hq_deals.html", {
        "deals": deals_qs,
        "brands": brands,
        "search": search,
        "brand_filter": brand_filter,
        "status_filter": status_filter,
        "msg": msg,
        "msg_type": msg_type,
    })


@hq_required
def hq_applications(request):
    search = request.GET.get("search", "").strip()
    status_filter = request.GET.get("status", "")
    merchant_filter = request.GET.get("merchant", "").strip()
    dup_filter = request.GET.get("dup_risk", "")

    apps_qs = FinancingApplication.objects.select_related(
        "created_by", "created_by__profile",
        "claimed_by", "claimed_by__profile",
        "reviewed_by",
        "deal", "deal__brand",
    ).order_by("-created_at")

    if search:
        apps_qs = apps_qs.filter(
            Q(customer_name__icontains=search)
            | Q(national_id__icontains=search)
            | Q(customer_phone__icontains=search)
            | Q(application_number__icontains=search)
        )
    if status_filter:
        apps_qs = apps_qs.filter(status=status_filter)
    if merchant_filter:
        apps_qs = apps_qs.filter(
            Q(created_by__username__icontains=merchant_filter)
            | Q(created_by__first_name__icontains=merchant_filter)
            | Q(created_by__last_name__icontains=merchant_filter)
        )
    if dup_filter == "1":
        apps_qs = apps_qs.filter(third_party_phone_user_risk_flagged=True)

    total_count = apps_qs.count()
    apps = apps_qs[:200]

    return render(
        request,
        "dashboard/hq_applications.html",
        {
            "title": "Applications",
            "subtitle": "Review submitted applications across the platform.",
            "apps": apps,
            "total_count": total_count,
            "search": search,
            "status_filter": status_filter,
            "merchant_filter": merchant_filter,
            "dup_filter": dup_filter,
            "show_actions": True,
        },
    )


@hq_required
def hq_underwriter_queue(request):
    User = get_user_model()
    search = request.GET.get("search", "").strip()

    apps_qs = (
        FinancingApplication.objects.select_related("created_by", "claimed_by", "reviewed_by")
        .filter(status__in=["pending_review", "under_review", "approved", "rejected", "resubmitted"])
        .order_by("-submitted_at", "-created_at")
    )
    if search:
        apps_qs = apps_qs.filter(
            Q(customer_name__icontains=search)
            | Q(application_number__icontains=search)
        )
    apps = apps_qs[:100]

    # Underwriter performance summary
    underwriters = User.objects.filter(profile__role="underwriter").order_by("username")
    uw_stats = []
    for uw in underwriters[:20]:
        active = FinancingApplication.objects.filter(claimed_by=uw, status="under_review").count()
        approved_today = FinancingApplication.objects.filter(
            reviewed_by=uw, status="approved",
            reviewed_at__date=timezone.now().date()
        ).count()
        rejected_today = FinancingApplication.objects.filter(
            reviewed_by=uw, status="rejected",
            reviewed_at__date=timezone.now().date()
        ).count()
        uw_stats.append({
            "user": uw,
            "active": active,
            "approved_today": approved_today,
            "rejected_today": rejected_today,
        })

    return render(
        request,
        "dashboard/hq_underwriter_queue.html",
        {
            "title": "Underwriter Queue",
            "subtitle": "Monitor submitted, claimed, and reviewed applications.",
            "apps": apps,
            "search": search,
            "uw_stats": uw_stats,
            "show_actions": True,
        },
    )


@hq_required
def hq_commissions(request):
    from commissions.models import CommissionLedger, MerchantContractPayout, UnderwriterMonthlyPayout
    from decimal import Decimal
    import csv
    from django.http import HttpResponse

    # ── CSV export ──────────────────────────────────────────────────
    export = request.GET.get("export", "")
    if export == "commissions_csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="commissions_ledger.csv"'
        writer = csv.writer(response)
        writer.writerow(["User", "Role", "Contract", "Type", "Base Amount", "Rate", "Amount", "Date"])
        for e in CommissionLedger.objects.select_related("user", "contract").order_by("-created_at")[:5000]:
            writer.writerow([
                e.user.username if e.user_id else "",
                "underwriter",
                e.contract.contract_number if e.contract_id else "",
                e.entry_type, e.base_amount, e.rate, e.amount,
                e.created_at.date(),
            ])
        return response

    if export == "merchant_csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="merchant_commissions.csv"'
        writer = csv.writer(response)
        writer.writerow(["Merchant", "Contract", "Cash Price", "Financed", "Commission", "Total Payable", "Status", "Date"])
        for p in MerchantContractPayout.objects.select_related("merchant", "contract").order_by("-created_at")[:5000]:
            writer.writerow([
                p.merchant.username if p.merchant_id else "",
                p.contract.contract_number if p.contract_id else "",
                p.cash_price, p.financed_amount, p.merchant_commission_amount,
                p.total_payable, p.status, p.created_at.date(),
            ])
        return response

    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    today_ledger = CommissionLedger.objects.filter(created_at__date=now.date())
    month_ledger = CommissionLedger.objects.filter(created_at__gte=month_start)

    def _sum(qs):
        return qs.aggregate(t=Sum("amount"))["t"] or Decimal("0")

    today_commissions = _sum(today_ledger.filter(entry_type=CommissionLedger.ENTRY_REPAYMENT))
    month_commissions = _sum(month_ledger.filter(entry_type=CommissionLedger.ENTRY_REPAYMENT))
    today_arrears = _sum(today_ledger.filter(entry_type=CommissionLedger.ENTRY_ARREARS))
    month_arrears = _sum(month_ledger.filter(entry_type=CommissionLedger.ENTRY_ARREARS))

    estimated_wht = max(month_commissions + month_arrears, Decimal("0")) * Decimal("0.20")
    net_uw_payout = month_commissions + month_arrears - estimated_wht

    # Merchant commissions
    merchant_payouts_pending = MerchantContractPayout.objects.filter(
        status=MerchantContractPayout.STATUS_PENDING
    ).aggregate(t=Sum("total_payable"))["t"] or Decimal("0")
    merchant_payouts_month = MerchantContractPayout.objects.filter(
        created_at__gte=month_start
    ).aggregate(t=Sum("merchant_commission_amount"))["t"] or Decimal("0")

    # WHT payable
    wht_pending_payouts = UnderwriterMonthlyPayout.objects.filter(
        status=UnderwriterMonthlyPayout.STATUS_PENDING
    ).aggregate(t=Sum("wht_amount"))["t"] or Decimal("0")

    # Top earners (underwriters)
    User = get_user_model()
    underwriter_users = User.objects.filter(profile__role="underwriter")
    top_earners = []
    for uw in underwriter_users[:15]:
        earned = _sum(CommissionLedger.objects.filter(user=uw, entry_type=CommissionLedger.ENTRY_REPAYMENT))
        deductions = _sum(CommissionLedger.objects.filter(user=uw, entry_type=CommissionLedger.ENTRY_ARREARS))
        wht = max(earned + deductions, Decimal("0")) * Decimal("0.20")
        top_earners.append({
            "user": uw,
            "earned": earned,
            "deductions": deductions,
            "gross": earned + deductions,
            "wht": wht,
            "net": (earned + deductions) - wht,
        })
    top_earners.sort(key=lambda x: x["net"], reverse=True)

    # Filters for ledger table
    user_filter = request.GET.get("user", "")
    type_filter = request.GET.get("type", "")
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")

    ledger_qs = CommissionLedger.objects.select_related("user", "contract").order_by("-created_at")
    if user_filter:
        ledger_qs = ledger_qs.filter(user__username__icontains=user_filter)
    if type_filter:
        ledger_qs = ledger_qs.filter(entry_type=type_filter)
    if date_from:
        try:
            from datetime import date
            ledger_qs = ledger_qs.filter(created_at__date__gte=date.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            from datetime import date
            ledger_qs = ledger_qs.filter(created_at__date__lte=date.fromisoformat(date_to))
        except ValueError:
            pass

    ledger_entries = ledger_qs[:100]
    merchant_payout_list = MerchantContractPayout.objects.select_related(
        "merchant", "contract"
    ).order_by("-created_at")[:50]
    uw_payouts = UnderwriterMonthlyPayout.objects.select_related("user").order_by("-period_end")[:30]
    commissions = Commission.objects.select_related("user", "application").order_by("-created_at")[:30]

    return render(request, "dashboard/hq_commissions.html", {
        "today_commissions": today_commissions,
        "month_commissions": month_commissions,
        "today_arrears": today_arrears,
        "month_arrears": month_arrears,
        "estimated_wht": estimated_wht,
        "net_uw_payout": net_uw_payout,
        "merchant_payouts_pending": merchant_payouts_pending,
        "merchant_payouts_month": merchant_payouts_month,
        "wht_pending_payouts": wht_pending_payouts,
        "top_earners": top_earners,
        "ledger_entries": ledger_entries,
        "merchant_payout_list": merchant_payout_list,
        "uw_payouts": uw_payouts,
        "commissions": commissions,
        "user_filter": user_filter,
        "type_filter": type_filter,
        "date_from": date_from,
        "date_to": date_to,
    })


@hq_required
def hq_merchant_payouts(request):
    from commissions.models import MerchantContractPayout
    from decimal import Decimal
    from core.models import AuditLog

    msg = None
    msg_type = "info"

    if request.method == "POST":
        action = request.POST.get("action", "")
        payout_id = request.POST.get("payout_id")
        try:
            payout = MerchantContractPayout.objects.get(pk=payout_id)
            if action == "mark_paid":
                ref = request.POST.get("reference", "").strip()
                payout.mark_paid(reference=ref)
                AuditLog.objects.create(
                    user=request.user,
                    action="hq_payout_mark_paid",
                    object_type="MerchantContractPayout",
                    object_id=str(payout.pk),
                    detail={"reference": ref, "amount": str(payout.total_payable)},
                )
                msg = f"Payout #{payout.pk} marked as paid."
                msg_type = "success"
            elif action == "queue_payout":
                payout.status = MerchantContractPayout.STATUS_PROCESSING
                payout.save(update_fields=["status", "updated_at"])
                AuditLog.objects.create(
                    user=request.user,
                    action="hq_payout_queued",
                    object_type="MerchantContractPayout",
                    object_id=str(payout.pk),
                    detail={"amount": str(payout.total_payable)},
                )
                msg = f"Payout #{payout.pk} queued for processing."
                msg_type = "success"
            elif action == "retry_payout":
                payout.status = MerchantContractPayout.STATUS_PENDING
                payout.save(update_fields=["status", "updated_at"])
                msg = f"Payout #{payout.pk} reset to pending for retry."
                msg_type = "info"
        except MerchantContractPayout.DoesNotExist:
            msg = "Payout not found."
            msg_type = "error"
        except Exception as exc:
            msg = f"Error: {exc}"
            msg_type = "error"

    # Filters - apply BEFORE slicing
    status_filter = request.GET.get("status", "")
    merchant_filter = request.GET.get("merchant", "").strip()

    all_payouts = MerchantContractPayout.objects.select_related("merchant", "contract").order_by("-created_at")
    if status_filter:
        all_payouts = all_payouts.filter(status=status_filter)
    if merchant_filter:
        all_payouts = all_payouts.filter(merchant__username__icontains=merchant_filter)

    # Totals on full (possibly filtered) queryset — NEVER filter on a sliced queryset
    pending_total = MerchantContractPayout.objects.filter(
        status=MerchantContractPayout.STATUS_PENDING
    ).aggregate(t=Sum("total_payable"))["t"] or Decimal("0")

    paid_total = MerchantContractPayout.objects.filter(
        status=MerchantContractPayout.STATUS_PAID
    ).aggregate(t=Sum("total_payable"))["t"] or Decimal("0")

    commission_total = MerchantContractPayout.objects.aggregate(
        t=Sum("merchant_commission_amount")
    )["t"] or Decimal("0")

    processing_total = MerchantContractPayout.objects.filter(
        status=MerchantContractPayout.STATUS_PROCESSING
    ).aggregate(t=Sum("total_payable"))["t"] or Decimal("0")

    # Slice only for display
    payouts = all_payouts[:100]

    return render(request, "dashboard/hq_merchant_payouts.html", {
        "payouts": payouts,
        "pending_total": pending_total,
        "paid_total": paid_total,
        "commission_total": commission_total,
        "processing_total": processing_total,
        "status_filter": status_filter,
        "merchant_filter": merchant_filter,
        "msg": msg,
        "msg_type": msg_type,
    })


@hq_required
def hq_reports(request):
    import csv
    from django.http import HttpResponse
    from django.utils import timezone
    from portal.models import PaymentContract, PaymentTransaction

    report_type = request.GET.get("type", "")

    if report_type == "portfolio_csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="portfolio_report.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "Contract Number", "PayG Number", "Customer Name",
            "Total Amount", "Amount Paid", "Remaining", "Status",
            "Start Date", "Due Date",
        ])
        for c in PaymentContract.objects.all().order_by("-created_at"):
            writer.writerow([
                c.contract_number, c.payg_number, c.customer_name,
                c.total_amount, c.amount_paid, c.remaining_amount,
                c.status, c.start_date, c.due_date,
            ])
        return response

    if report_type == "applications_csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="applications_report.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "Application Number", "Customer Name", "Status",
            "Created By", "Created At", "Claimed By", "Reviewed At",
        ])
        for a in FinancingApplication.objects.all().order_by("-created_at"):
            writer.writerow([
                a.application_number, a.customer_name, a.status,
                a.created_by.username if a.created_by_id else "",
                a.created_at.date(),
                a.claimed_by.username if a.claimed_by_id else "",
                a.reviewed_at.date() if a.reviewed_at else "",
            ])
        return response

    if report_type == "collections_csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="collections_report.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "Contract", "Customer", "Provider", "Amount",
            "Commissionable", "Status", "Paid At",
        ])
        for t in PaymentTransaction.objects.filter(status="paid").order_by("-paid_at"):
            writer.writerow([
                t.payment_contract.contract_number,
                t.payment_contract.customer_name,
                t.provider, t.amount, t.commissionable_amount,
                t.status, t.paid_at,
            ])
        return response

    if report_type == "commissions_csv":
        from commissions.models import CommissionLedger
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="commissions_report.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "User", "Entry Type", "Amount", "Base Amount",
            "Rate", "Contract", "Description", "Created At",
        ])
        for entry in CommissionLedger.objects.select_related("user", "contract").order_by("-created_at"):
            writer.writerow([
                entry.user.username,
                entry.entry_type, entry.amount, entry.base_amount,
                entry.rate,
                entry.contract.contract_number if entry.contract_id else "",
                entry.description, entry.created_at.date(),
            ])
        return response

    if report_type == "merchant_payouts_csv":
        from commissions.models import MerchantContractPayout
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="merchant_payouts_report.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "Merchant", "Contract", "Cash Price", "Financed Amount",
            "Commission", "Total Payable", "Status", "Created At",
        ])
        for p in MerchantContractPayout.objects.select_related("merchant", "contract").order_by("-created_at"):
            writer.writerow([
                p.merchant.username,
                p.contract.contract_number if p.contract_id else "",
                p.cash_price, p.financed_amount, p.merchant_commission_amount,
                p.total_payable, p.status, p.created_at.date(),
            ])
        return response

    from portal.models import PaymentContract, PaymentTransaction
    from decimal import Decimal

    total_portfolio = PaymentContract.objects.aggregate(t=Sum("total_amount"))["t"] or Decimal("0")
    total_paid = PaymentContract.objects.aggregate(t=Sum("amount_paid"))["t"] or Decimal("0")
    active_contracts = PaymentContract.objects.filter(status="active").count()
    overdue_amount = PaymentContract.objects.filter(
        status__in=["overdue", "locked"]
    ).aggregate(t=Sum("total_amount"))["t"] or Decimal("0")

    return render(request, "dashboard/hq_reports.html", {
        "title": "Reports",
        "total_portfolio": total_portfolio,
        "total_paid": total_paid,
        "active_contracts": active_contracts,
        "overdue_amount": overdue_amount,
    })


@hq_required
def hq_simulations(request):
    """TengaSale Growth Simulator — investor-grade phone financing projections."""
    result = None
    form_data = {}

    if request.method == "POST":
        from decimal import Decimal, InvalidOperation

        def _d(key, default):
            v = request.POST.get(key, str(default)) or str(default)
            try:
                return Decimal(v)
            except Exception:
                return Decimal(str(default))

        def _i(key, default):
            v = request.POST.get(key, str(default)) or str(default)
            try:
                return max(1, int(v))
            except Exception:
                return default

        try:
            # ── Inputs ──────────────────────────────────────────────────────
            num_devices         = _i("num_devices", 100)
            cash_price          = _d("cash_price", 400000)
            contract_value      = _d("contract_value", 1000000)
            deposit_pct         = _d("deposit_pct", 20) / Decimal("100")
            term_months         = _i("term_months", 12)
            collection_rate     = _d("collection_rate", 90) / Decimal("100")
            default_rate        = _d("default_rate", 5) / Decimal("100")
            lock_recovery_rate  = _d("lock_recovery_rate", 60) / Decimal("100")
            merchant_rate       = _d("merchant_commission_rate", 1) / Decimal("100")
            uw_rate             = _d("uw_commission_rate", 7) / Decimal("100")
            arrears_penalty     = _d("arrears_penalty_rate", 14) / Decimal("100")
            wht_rate            = _d("wht_rate", 20) / Decimal("100")
            monthly_tech_cost   = _d("monthly_tech_cost", 0)
            lock_cost_per_dev   = _d("lock_cost_per_device", 0)
            sms_cost_per_cust   = _d("sms_cost_per_customer", 0)
            num_merchants       = _i("num_merchants", 10)
            num_underwriters    = _i("num_underwriters", 3)
            sales_per_merchant  = _i("avg_sales_per_merchant_per_month", 5)

            D = Decimal

            # ── Customer impact ─────────────────────────────────────────────
            people_connected    = num_devices
            deposit_per         = contract_value * deposit_pct
            financed_per        = contract_value - deposit_per
            monthly_repayment   = financed_per / D(str(term_months))
            daily_repayment     = financed_per / D(str(term_months * 30))
            total_deposits      = deposit_per * D(str(num_devices))
            total_financed      = financed_per * D(str(num_devices))

            # ── Company economics ───────────────────────────────────────────
            gross_sales_value      = contract_value * D(str(num_devices))
            expected_monthly_col   = monthly_repayment * collection_rate * (D("1") - default_rate) * D(str(num_devices))
            expected_total_col     = expected_monthly_col * D(str(term_months))
            total_inflows          = total_deposits + expected_total_col

            merchant_comm_per      = financed_per * merchant_rate
            merchant_payout_per    = cash_price + merchant_comm_per
            total_merchant_payouts = merchant_payout_per * D(str(num_devices))

            uw_gross_per           = (financed_per * collection_rate * (D("1") - default_rate)) * uw_rate
            uw_wht_per             = uw_gross_per * wht_rate
            uw_net_per             = uw_gross_per - uw_wht_per
            total_uw_gross         = uw_gross_per * D(str(num_devices))
            total_uw_wht           = uw_wht_per * D(str(num_devices))
            total_uw_net           = uw_net_per * D(str(num_devices))

            missed_per             = financed_per * default_rate
            arrears_deduction_per  = missed_per * arrears_penalty
            total_arrears_ded      = arrears_deduction_per * D(str(num_devices))

            # Operating costs
            total_tech_cost = monthly_tech_cost * D(str(term_months))
            total_lock_cost = lock_cost_per_dev * D(str(num_devices)) * D(str(term_months))
            total_sms_cost  = sms_cost_per_cust * D(str(num_devices)) * D(str(term_months))
            total_op_costs  = total_tech_cost + total_lock_cost + total_sms_cost

            total_outflows = (
                total_merchant_payouts + total_uw_gross + total_arrears_ded + total_op_costs
            )
            expected_cash_flow  = total_inflows - total_merchant_payouts - total_uw_gross - total_op_costs
            estimated_profit    = expected_cash_flow - total_arrears_ded

            # ── Risk ────────────────────────────────────────────────────────
            default_exposure       = financed_per * default_rate * D(str(num_devices))
            lock_recovery          = default_exposure * lock_recovery_rate
            unrecovered_exposure   = default_exposure - lock_recovery
            portfolio_at_risk      = round(float(default_rate) * 100, 1)
            total_collections_needed = total_merchant_payouts + total_op_costs
            if total_deposits > 0 and total_inflows > 0:
                break_even_col_rate = float(total_collections_needed / total_financed * 100) if total_financed > 0 else 0
            else:
                break_even_col_rate = 0

            # ── Scenario comparison ─────────────────────────────────────────
            def _scenario(col_rate, def_rate, label, badge):
                col = D(str(col_rate)) / D("100")
                dflt = D(str(def_rate)) / D("100")
                exp_col = monthly_repayment * col * (D("1") - dflt) * D(str(num_devices)) * D(str(term_months))
                uw_c = exp_col * uw_rate
                merch_c = financed_per * merchant_rate * D(str(num_devices))
                inflow = total_deposits + exp_col
                outflow = total_merchant_payouts + uw_c + (financed_per * dflt * arrears_penalty * D(str(num_devices))) + total_op_costs
                profit = inflow - outflow
                return {
                    "label": label,
                    "badge": badge,
                    "col_rate": col_rate,
                    "def_rate": def_rate,
                    "expected_collections": round(exp_col, 0),
                    "estimated_profit": round(profit, 0),
                    "profitable": profit > 0,
                }

            scenarios = [
                _scenario(75, 15, "Conservative", "warning"),
                _scenario(90, 5,  "Base Case",    "primary"),
                _scenario(95, 3,  "Aggressive",   "success"),
                _scenario(60, 30, "High Default Stress", "danger"),
            ]

            # ── Narrative ───────────────────────────────────────────────────
            narrative = (
                f"If TengaSale finances {num_devices:,} devices at MWK {int(contract_value):,} "
                f"contract value with {int(deposit_pct * 100)}% deposits, approximately {people_connected:,} "
                f"people gain access to smartphones. The platform would collect "
                f"MWK {int(total_deposits):,} in deposits, manage a "
                f"MWK {int(total_financed):,} financed portfolio, and expect "
                f"MWK {int(expected_monthly_col):,} monthly collections at {int(collection_rate * 100)}% "
                f"collection rate. Estimated profit over {term_months} months is "
                f"MWK {int(estimated_profit):,}."
            )

            # ── Recommendation ──────────────────────────────────────────────
            if estimated_profit > 0 and float(default_rate) <= 0.05:
                recommendation = "Safe"
                rec_color = "#16a34a"
                rec_bg = "rgba(22,163,74,0.10)"
            elif estimated_profit > 0 and float(default_rate) <= 0.15:
                recommendation = "Watch"
                rec_color = "#d97706"
                rec_bg = "rgba(217,119,6,0.10)"
            else:
                recommendation = "Danger"
                rec_color = "#dc2626"
                rec_bg = "rgba(220,38,38,0.10)"

            result = {
                # Inputs
                "num_devices": num_devices,
                "cash_price": cash_price,
                "contract_value": contract_value,
                "deposit_pct_display": int(deposit_pct * 100),
                "term_months": term_months,
                "collection_rate_display": int(collection_rate * 100),
                "default_rate_display": round(float(default_rate) * 100, 1),
                # Customer impact
                "people_connected": people_connected,
                "deposit_per": round(deposit_per, 0),
                "financed_per": round(financed_per, 0),
                "monthly_repayment": round(monthly_repayment, 0),
                "daily_repayment": round(daily_repayment, 0),
                "total_deposits": round(total_deposits, 0),
                "total_financed": round(total_financed, 0),
                # Company economics
                "gross_sales_value": round(gross_sales_value, 0),
                "expected_monthly_collections": round(expected_monthly_col, 0),
                "expected_total_collections": round(expected_total_col, 0),
                "merchant_payout_per": round(merchant_payout_per, 0),
                "total_merchant_payouts": round(total_merchant_payouts, 0),
                "merchant_comm_per": round(merchant_comm_per, 0),
                "total_uw_gross": round(total_uw_gross, 0),
                "total_uw_wht": round(total_uw_wht, 0),
                "total_uw_net": round(total_uw_net, 0),
                "total_arrears_ded": round(total_arrears_ded, 0),
                "expected_cash_flow": round(expected_cash_flow, 0),
                "estimated_profit": round(estimated_profit, 0),
                "total_inflows": round(total_inflows, 0),
                "total_outflows": round(total_outflows, 0),
                # Risk
                "default_exposure": round(default_exposure, 0),
                "lock_recovery": round(lock_recovery, 0),
                "unrecovered_exposure": round(unrecovered_exposure, 0),
                "portfolio_at_risk": portfolio_at_risk,
                "break_even_col_rate": round(break_even_col_rate, 1),
                # Scenarios
                "scenarios": scenarios,
                # Narrative
                "narrative": narrative,
                # Recommendation
                "recommendation": recommendation,
                "rec_color": rec_color,
                "rec_bg": rec_bg,
                # Aliases for test compatibility
                "deposit_amount": round(deposit_per, 0),
                "financed_amount": round(financed_per, 0),
                "uw_gross_commission": round(total_uw_gross, 0),
                "uw_wht": round(total_uw_wht, 0),
                "merchant_payout": round(total_merchant_payouts, 0),
            }
            form_data = request.POST
        except (Exception,) as exc:
            result = None
            form_data = request.POST

    return render(request, "dashboard/hq_simulations.html", {
        "result": result,
        "form_data": form_data,
        "deposit_options": ["15", "20", "30"],
        "term_options": [6, 9, 12, 18, 24],
    })


@hq_required
def hq_operations(request):
    """
    Safe audited HQ operations.
    All actions are permission-checked, logged, and require confirmation.
    No dangerous one-click irreversible operations.
    """
    from core.models import AuditLog

    action = request.POST.get("action") if request.method == "POST" else None
    result_message = None
    result_type = "info"

    if action == "reassign_application":
        app_id = request.POST.get("app_id")
        new_underwriter_id = request.POST.get("underwriter_id")
        try:
            app = FinancingApplication.objects.get(pk=app_id)
            User = get_user_model()
            new_uw = User.objects.get(pk=new_underwriter_id, profile__role="underwriter")
            old_uw = app.claimed_by
            app.claimed_by = new_uw
            app.save(update_fields=["claimed_by"])
            AuditLog.objects.create(
                user=request.user,
                action="hq_reassign_application",
                object_type="FinancingApplication",
                object_id=str(app.pk),
                detail={"from": str(old_uw), "to": str(new_uw), "app": app.application_number},
            )
            result_message = f"Application {app.application_number} reassigned to {new_uw.get_full_name() or new_uw.username}."
            result_type = "success"
        except Exception as exc:
            result_message = f"Reassign failed: {exc}"
            result_type = "error"

    elif action == "release_stuck_claim":
        app_id = request.POST.get("app_id")
        try:
            app = FinancingApplication.objects.get(pk=app_id)
            old_uw = app.claimed_by
            app.claimed_by = None
            app.claimed_at = None
            app.status = "pending_review"
            app.save(update_fields=["claimed_by", "claimed_at", "status"])
            AuditLog.objects.create(
                user=request.user,
                action="hq_release_stuck_claim",
                object_type="FinancingApplication",
                object_id=str(app.pk),
                detail={"released_from": str(old_uw), "app": app.application_number},
            )
            result_message = f"Claim released. Application {app.application_number} is back in the queue."
            result_type = "success"
        except Exception as exc:
            result_message = f"Release failed: {exc}"
            result_type = "error"

    elif action == "mark_payment_manual_review":
        txn_id = request.POST.get("transaction_id")
        try:
            from portal.models import PaymentTransaction
            txn = PaymentTransaction.objects.get(pk=txn_id)
            txn.status = PaymentTransaction.STATUS_PENDING
            txn.save(update_fields=["status"])
            AuditLog.objects.create(
                user=request.user,
                action="hq_mark_payment_manual_review",
                object_type="PaymentTransaction",
                object_id=str(txn.pk),
                detail={"contract": str(txn.payment_contract_id), "amount": str(txn.amount)},
            )
            result_message = f"Transaction {txn.internal_reference} marked for manual review."
            result_type = "success"
        except Exception as exc:
            result_message = f"Mark for review failed: {exc}"
            result_type = "error"

    elif action == "resend_correction_link":
        app_id = request.POST.get("app_id")
        try:
            from applications.models import ApplicationCorrectionToken
            app = FinancingApplication.objects.get(pk=app_id)
            token_obj = ApplicationCorrectionToken.create_or_refresh(app)
            AuditLog.objects.create(
                user=request.user,
                action="hq_resend_correction_link",
                object_type="FinancingApplication",
                object_id=str(app.pk),
                detail={"app": app.application_number, "token": token_obj.token[:8] + "..."},
            )
            result_message = f"Correction token refreshed for {app.application_number}. Token: {token_obj.token[:12]}..."
            result_type = "success"
        except Exception as exc:
            result_message = f"Resend failed: {exc}"
            result_type = "error"

    User = get_user_model()
    underwriters = User.objects.filter(profile__role="underwriter").order_by("username")
    stuck_apps = FinancingApplication.objects.filter(
        status="under_review", claimed_by__isnull=False
    ).select_related("claimed_by").order_by("-claimed_at")[:20]

    from portal.models import PaymentTransaction
    pending_transactions = PaymentTransaction.objects.filter(
        status__in=["pending", "processing"]
    ).select_related("payment_contract").order_by("-created_at")[:20]

    audit_recent = AuditLog.objects.filter(
        action__startswith="hq_"
    ).select_related("user").order_by("-timestamp")[:20]

    return render(request, "dashboard/hq_operations.html", {
        "title": "Safe Operations",
        "underwriters": underwriters,
        "stuck_apps": stuck_apps,
        "pending_transactions": pending_transactions,
        "audit_recent": audit_recent,
        "result_message": result_message,
        "result_type": result_type,
    })


@hq_required
def hq_commission_ledger(request):
    """Commission ledger — alias for hq_commissions with same content."""
    return hq_commissions(request)


@hq_required
def hq_safe_operations(request):
    """Safe operations center — alias for hq_operations."""
    return hq_operations(request)


@hq_required
def hq_devices(request):
    """Device enrollment management page."""
    from portal.models import PaymentContract
    from core.models import AuditLog

    msg = None
    msg_type = "info"

    if request.method == "POST":
        action = request.POST.get("action", "")
        contract_id = request.POST.get("contract_id")
        try:
            contract = PaymentContract.objects.get(pk=contract_id)
            if action == "enroll_device":
                contract.device_enrollment_status = PaymentContract.ENROLLMENT_PENDING
                contract.save(update_fields=["device_enrollment_status", "updated_at"])
                AuditLog.objects.create(
                    user=request.user,
                    action="hq_device_enroll",
                    object_type="PaymentContract",
                    object_id=str(contract.pk),
                    detail={"contract": contract.contract_number},
                )
                msg = f"Enrollment initiated for {contract.contract_number}."
                msg_type = "success"
            elif action == "lock_device":
                contract.device_lock_status = PaymentContract.LOCK_STATUS_LOCKED
                contract.save(update_fields=["device_lock_status", "updated_at"])
                AuditLog.objects.create(
                    user=request.user,
                    action="hq_device_lock",
                    object_type="PaymentContract",
                    object_id=str(contract.pk),
                    detail={"contract": contract.contract_number},
                )
                msg = f"Device locked for {contract.contract_number}."
                msg_type = "success"
            elif action == "unlock_device":
                contract.device_lock_status = PaymentContract.LOCK_STATUS_UNLOCKED
                contract.save(update_fields=["device_lock_status", "updated_at"])
                AuditLog.objects.create(
                    user=request.user,
                    action="hq_device_unlock",
                    object_type="PaymentContract",
                    object_id=str(contract.pk),
                    detail={"contract": contract.contract_number},
                )
                msg = f"Device unlocked for {contract.contract_number}."
                msg_type = "success"
            elif action == "release_device":
                contract.device_enrollment_status = PaymentContract.ENROLLMENT_NONE
                contract.device_lock_status = PaymentContract.LOCK_STATUS_UNLOCKED
                contract.save(update_fields=["device_enrollment_status", "device_lock_status", "updated_at"])
                AuditLog.objects.create(
                    user=request.user,
                    action="hq_device_release",
                    object_type="PaymentContract",
                    object_id=str(contract.pk),
                    detail={"contract": contract.contract_number},
                )
                msg = f"Device released for {contract.contract_number}."
                msg_type = "success"
        except PaymentContract.DoesNotExist:
            msg = "Contract not found."
            msg_type = "error"
        except Exception as exc:
            msg = f"Error: {exc}"
            msg_type = "error"

    # Filters
    enroll_filter = request.GET.get("enrollment", "")
    lock_filter = request.GET.get("lock", "")
    search = request.GET.get("search", "").strip()
    provider_filter = request.GET.get("provider", "")

    devices_qs = PaymentContract.objects.order_by("-created_at")
    if enroll_filter:
        devices_qs = devices_qs.filter(device_enrollment_status=enroll_filter)
    if lock_filter:
        devices_qs = devices_qs.filter(device_lock_status=lock_filter)
    if provider_filter:
        devices_qs = devices_qs.filter(device_lock_provider=provider_filter)
    if search:
        devices_qs = devices_qs.filter(
            Q(contract_number__icontains=search)
            | Q(customer_name__icontains=search)
            | Q(customer_phone__icontains=search)
            | Q(device_model__icontains=search)
        )

    # Summary counts
    total_enrolled = PaymentContract.objects.filter(
        device_enrollment_status=PaymentContract.ENROLLMENT_ENROLLED
    ).count()
    total_pending = PaymentContract.objects.filter(
        device_enrollment_status=PaymentContract.ENROLLMENT_PENDING
    ).count()
    total_failed = PaymentContract.objects.filter(
        device_enrollment_status=PaymentContract.ENROLLMENT_FAILED
    ).count()
    total_locked = PaymentContract.objects.filter(
        device_lock_status=PaymentContract.LOCK_STATUS_LOCKED
    ).count()

    return render(request, "dashboard/hq_devices.html", {
        "devices": devices_qs[:100],
        "enroll_filter": enroll_filter,
        "lock_filter": lock_filter,
        "search": search,
        "provider_filter": provider_filter,
        "total_enrolled": total_enrolled,
        "total_pending": total_pending,
        "total_failed": total_failed,
        "total_locked": total_locked,
        "msg": msg,
        "msg_type": msg_type,
    })


@hq_required
def hq_staff_payouts(request):
    """Monthly underwriter/staff payout management."""
    from commissions.models import CommissionLedger, UnderwriterMonthlyPayout
    from decimal import Decimal
    from core.models import AuditLog

    msg = None
    msg_type = "info"

    User = get_user_model()
    underwriters = User.objects.filter(profile__role="underwriter").order_by("username")

    if request.method == "POST":
        action = request.POST.get("action", "")
        payout_id = request.POST.get("payout_id")

        if action == "generate_payout":
            uw_id = request.POST.get("uw_id")
            period_start_str = request.POST.get("period_start")
            period_end_str = request.POST.get("period_end")
            try:
                from datetime import date
                uw = User.objects.get(pk=uw_id)
                period_start = date.fromisoformat(period_start_str)
                period_end = date.fromisoformat(period_end_str)
                gross = CommissionLedger.objects.filter(
                    user=uw,
                    entry_type=CommissionLedger.ENTRY_REPAYMENT,
                    created_at__date__gte=period_start,
                    created_at__date__lte=period_end,
                ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
                deductions = CommissionLedger.objects.filter(
                    user=uw,
                    entry_type=CommissionLedger.ENTRY_ARREARS,
                    created_at__date__gte=period_start,
                    created_at__date__lte=period_end,
                ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
                net_gross = gross + deductions  # deductions are negative
                payout, created = UnderwriterMonthlyPayout.objects.get_or_create(
                    user=uw,
                    period_start=period_start,
                    period_end=period_end,
                    defaults={"gross_commission": net_gross},
                )
                if not created:
                    payout.gross_commission = net_gross
                    payout.save()
                AuditLog.objects.create(
                    user=request.user,
                    action="hq_staff_payout_generated",
                    object_type="UnderwriterMonthlyPayout",
                    object_id=str(payout.pk),
                    detail={"uw": uw.username, "gross": str(net_gross)},
                )
                msg = f"Payout {'created' if created else 'updated'} for {uw.username}: MWK {payout.net_amount:,.2f} net."
                msg_type = "success"
            except Exception as exc:
                msg = f"Error generating payout: {exc}"
                msg_type = "error"

        elif action == "mark_paid" and payout_id:
            try:
                payout = UnderwriterMonthlyPayout.objects.get(pk=payout_id)
                ref = request.POST.get("reference", "").strip()
                payout.mark_paid(reference=ref)
                AuditLog.objects.create(
                    user=request.user,
                    action="hq_staff_payout_paid",
                    object_type="UnderwriterMonthlyPayout",
                    object_id=str(payout.pk),
                    detail={"uw": payout.user.username, "reference": ref},
                )
                msg = f"Payout #{payout.pk} for {payout.user.username} marked as paid."
                msg_type = "success"
            except Exception as exc:
                msg = f"Error: {exc}"
                msg_type = "error"

    payouts = UnderwriterMonthlyPayout.objects.select_related("user").order_by("-period_end", "-created_at")[:100]

    total_pending_net = UnderwriterMonthlyPayout.objects.filter(
        status=UnderwriterMonthlyPayout.STATUS_PENDING
    ).aggregate(t=Sum("net_amount"))["t"] or Decimal("0")

    total_wht_withheld = UnderwriterMonthlyPayout.objects.filter(
        status=UnderwriterMonthlyPayout.STATUS_PAID
    ).aggregate(t=Sum("wht_amount"))["t"] or Decimal("0")

    today = timezone.now().date()
    default_period_start = today.replace(day=1).isoformat()
    default_period_end = today.isoformat()

    return render(request, "dashboard/hq_staff_payouts.html", {
        "payouts": payouts,
        "underwriters": underwriters,
        "total_pending_net": total_pending_net,
        "total_wht_withheld": total_wht_withheld,
        "default_period_start": default_period_start,
        "default_period_end": default_period_end,
        "msg": msg,
        "msg_type": msg_type,
    })


@hq_required
def hq_auto_approval(request):
    """Auto-approval engine management."""
    from applications.services.auto_approval import evaluate_auto_approval, auto_approve_application
    from core.models import AuditLog
    from decimal import Decimal

    msg = None
    msg_type = "info"

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "approve_selected":
            app_ids = request.POST.getlist("app_ids")
            approved_count = 0
            failed_count = 0
            for app_id in app_ids:
                try:
                    app = FinancingApplication.objects.get(pk=app_id)
                    result = evaluate_auto_approval(app)
                    if result["eligible"]:
                        auto_approve_application(app, approved_by=request.user)
                        approved_count += 1
                    else:
                        failed_count += 1
                except Exception:
                    failed_count += 1
            msg = f"Auto-approved {approved_count} application(s). {failed_count} blocked."
            msg_type = "success" if approved_count > 0 else "warning"

    # Evaluate pending applications
    pending_apps = FinancingApplication.objects.filter(
        status__in=["pending_review", "submitted", "resubmitted"],
        claimed_by__isnull=True,
    ).select_related("created_by", "deal").order_by("-submitted_at")[:50]

    eligibility_results = []
    for app in pending_apps:
        try:
            result = evaluate_auto_approval(app)
        except Exception as exc:
            result = {"eligible": False, "reasons": [str(exc)], "blocks": [str(exc)]}
        eligibility_results.append({"app": app, "result": result})

    eligible_count = sum(1 for r in eligibility_results if r["result"]["eligible"])
    blocked_count = len(eligibility_results) - eligible_count

    return render(request, "dashboard/hq_auto_approval.html", {
        "eligibility_results": eligibility_results,
        "eligible_count": eligible_count,
        "blocked_count": blocked_count,
        "msg": msg,
        "msg_type": msg_type,
    })


@hq_required
def hq_payment_collections(request):
    """Payment collections control page."""
    from portal.models import PaymentContract, PaymentTransaction
    from decimal import Decimal
    import csv
    from django.http import HttpResponse

    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="payment_collections.csv"'
        writer = csv.writer(response)
        writer.writerow(["Contract", "Customer", "Amount", "Provider", "Status", "Paid At", "Reference"])
        qs = PaymentTransaction.objects.select_related("payment_contract").order_by("-created_at")[:2000]
        for t in qs:
            writer.writerow([
                t.payment_contract.contract_number if t.payment_contract_id else "",
                t.payment_contract.customer_name if t.payment_contract_id else "",
                t.amount, t.provider, t.status,
                t.paid_at.date() if t.paid_at else "",
                t.provider_reference or t.internal_reference,
            ])
        return response

    today = timezone.now().date()
    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    collections_today = (
        PaymentTransaction.objects.filter(status="paid", paid_at__date=today)
        .aggregate(t=Sum("amount"))["t"] or Decimal("0")
    )
    collections_month = (
        PaymentTransaction.objects.filter(status="paid", paid_at__gte=month_start)
        .aggregate(t=Sum("amount"))["t"] or Decimal("0")
    )
    failed_payments = PaymentTransaction.objects.filter(
        status__in=["failed", "cancelled"]
    ).count()
    pending_payments = PaymentTransaction.objects.filter(
        status__in=["pending", "processing"]
    ).count()

    # Filters
    status_filter = request.GET.get("status", "")
    provider_filter = request.GET.get("provider", "")
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")

    txns_qs = PaymentTransaction.objects.select_related("payment_contract").order_by("-created_at")
    if status_filter:
        txns_qs = txns_qs.filter(status=status_filter)
    if provider_filter:
        txns_qs = txns_qs.filter(provider=provider_filter)
    if date_from:
        try:
            from datetime import date
            txns_qs = txns_qs.filter(created_at__date__gte=date.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            from datetime import date
            txns_qs = txns_qs.filter(created_at__date__lte=date.fromisoformat(date_to))
        except ValueError:
            pass

    transactions = txns_qs[:100]
    providers = PaymentTransaction.objects.values_list("provider", flat=True).distinct().order_by("provider")

    return render(request, "dashboard/hq_payment_collections.html", {
        "collections_today": collections_today,
        "collections_month": collections_month,
        "failed_payments": failed_payments,
        "pending_payments": pending_payments,
        "transactions": transactions,
        "providers": providers,
        "status_filter": status_filter,
        "provider_filter": provider_filter,
        "date_from": date_from,
        "date_to": date_to,
    })


@hq_required
def hq_reconciliation(request):
    """Payment reconciliation control page."""
    from portal.models import PaymentContract, PaymentTransaction
    from core.models import AuditLog

    msg = None
    msg_type = "info"

    if request.method == "POST":
        action = request.POST.get("action", "")
        txn_id = request.POST.get("txn_id")
        try:
            txn = PaymentTransaction.objects.get(pk=txn_id)
            if action == "mark_reconciled":
                txn.status = "paid"
                txn.save(update_fields=["status"])
                AuditLog.objects.create(
                    user=request.user,
                    action="hq_reconcile_manual",
                    object_type="PaymentTransaction",
                    object_id=str(txn.pk),
                    detail={"reference": txn.internal_reference, "amount": str(txn.amount)},
                )
                msg = f"Transaction {txn.internal_reference} marked as reconciled."
                msg_type = "success"
        except PaymentTransaction.DoesNotExist:
            msg = "Transaction not found."
            msg_type = "error"
        except Exception as exc:
            msg = f"Error: {exc}"
            msg_type = "error"

    # Matched: paid transactions with a contract
    matched = PaymentTransaction.objects.filter(
        status="paid", payment_contract__isnull=False
    ).count()
    # Unmatched: pending/failed with no contract link or no external reference
    unmatched = PaymentTransaction.objects.filter(
        status__in=["pending", "processing"],
        payment_contract__isnull=True,
    ).count()
    # Duplicate references
    from django.db.models import Count
    dup_refs = (
        PaymentTransaction.objects.exclude(provider_reference="")
        .exclude(provider_reference__isnull=True)
        .values("provider_reference")
        .annotate(cnt=Count("id"))
        .filter(cnt__gt=1)
        .count()
    )
    # External pending
    ext_pending = PaymentTransaction.objects.filter(status="processing").count()

    # Recent unmatched for review
    unmatched_qs = PaymentTransaction.objects.filter(
        Q(status__in=["pending", "processing"]) | Q(payment_contract__isnull=True, status="failed")
    ).select_related("payment_contract").order_by("-created_at")[:50]

    return render(request, "dashboard/hq_reconciliation.html", {
        "matched": matched,
        "unmatched": unmatched,
        "dup_refs": dup_refs,
        "ext_pending": ext_pending,
        "unmatched_qs": unmatched_qs,
        "msg": msg,
        "msg_type": msg_type,
    })


@hq_required
def hq_sales_analytics(request):
    """Sales analytics and performance page."""
    from collections import Counter
    from decimal import Decimal
    import csv
    from django.http import HttpResponse

    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="sales_analytics.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "Application #", "Customer", "Status", "Merchant",
            "Deal Brand", "Deal Model", "Deposit %", "Cash Price",
            "Gender", "Marital Status", "Dependents", "District",
            "Submitted At",
        ])
        for a in FinancingApplication.objects.select_related(
            "created_by", "deal", "deal__brand"
        ).order_by("-created_at")[:2000]:
            writer.writerow([
                a.application_number, a.customer_name, a.status,
                a.created_by.username if a.created_by_id else "",
                a.deal.brand.name if a.deal_id and a.deal.brand_id else "",
                a.deal.model_name if a.deal_id else "",
                a.selected_deposit_percent,
                a.selected_cash_price,
                a.gender, a.marital_status, a.num_dependents or 0,
                a.district,
                a.submitted_at.date() if a.submitted_at else "",
            ])
        return response

    total_apps = FinancingApplication.objects.count()
    submitted = FinancingApplication.objects.filter(
        status__in=["submitted", "pending_review", "under_review", "approved",
                    "rejected", "completed", "contract_complete"]
    ).count()
    approved = FinancingApplication.objects.filter(status="approved").count()
    completed = FinancingApplication.objects.filter(
        status__in=["completed", "contract_complete"]
    ).count()

    # By merchant (top 10)
    by_merchant = (
        FinancingApplication.objects.values("created_by__username")
        .annotate(cnt=Count("id"))
        .order_by("-cnt")[:10]
    )
    # Sales by day (last 14 days)
    from datetime import timedelta as td
    last_14 = []
    for i in range(13, -1, -1):
        day = (timezone.now() - td(days=i)).date()
        cnt = FinancingApplication.objects.filter(submitted_at__date=day).count()
        last_14.append({"date": str(day), "count": cnt})

    # Deposit band breakdown
    dep_15 = FinancingApplication.objects.filter(selected_deposit_percent__lte=16).count()
    dep_20 = FinancingApplication.objects.filter(
        selected_deposit_percent__gt=16, selected_deposit_percent__lte=22
    ).count()
    dep_30 = FinancingApplication.objects.filter(selected_deposit_percent__gt=22).count()

    # Gender breakdown
    gender_counts = {}
    for g, label in FinancingApplication.GENDER_CHOICES:
        if g:
            gender_counts[label] = FinancingApplication.objects.filter(gender=g).count()

    # Marital status
    marital_counts = {}
    for m, label in FinancingApplication.MARITAL_CHOICES:
        if m:
            marital_counts[label] = FinancingApplication.objects.filter(marital_status=m).count()

    # By brand
    from deals.models import DeviceDeal, DeviceBrand
    brand_counts = []
    for brand in DeviceBrand.objects.filter(is_active=True).order_by("name"):
        cnt = FinancingApplication.objects.filter(deal__brand=brand).count()
        brand_counts.append({"brand": brand.name, "count": cnt})

    return render(request, "dashboard/hq_sales_analytics.html", {
        "total_apps": total_apps,
        "submitted": submitted,
        "approved": approved,
        "completed": completed,
        "by_merchant": list(by_merchant),
        "last_14": last_14,
        "dep_15": dep_15,
        "dep_20": dep_20,
        "dep_30": dep_30,
        "gender_counts": gender_counts,
        "marital_counts": marital_counts,
        "brand_counts": brand_counts,
    })


@hq_required
def hq_underwriter_performance(request):
    """Underwriter performance analytics page."""
    from commissions.models import CommissionLedger
    from decimal import Decimal

    User = get_user_model()
    underwriters = User.objects.filter(profile__role="underwriter").order_by("username")

    stats = []
    for uw in underwriters:
        reviewed = FinancingApplication.objects.filter(reviewed_by=uw).count()
        approved_uw = FinancingApplication.objects.filter(reviewed_by=uw, status="approved").count()
        rejected_uw = FinancingApplication.objects.filter(reviewed_by=uw, status="rejected").count()
        approval_rate = round((approved_uw / reviewed * 100) if reviewed else 0, 1)
        rejection_rate = round((rejected_uw / reviewed * 100) if reviewed else 0, 1)

        gross = CommissionLedger.objects.filter(
            user=uw, entry_type=CommissionLedger.ENTRY_REPAYMENT
        ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
        deductions = CommissionLedger.objects.filter(
            user=uw, entry_type=CommissionLedger.ENTRY_ARREARS
        ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
        net = gross + deductions

        # Average review time (approved/rejected with reviewed_at and submitted_at)
        apps_with_times = FinancingApplication.objects.filter(
            reviewed_by=uw,
            reviewed_at__isnull=False,
            submitted_at__isnull=False,
        ).values_list("submitted_at", "reviewed_at")[:100]
        if apps_with_times:
            durations = [(r - s).total_seconds() / 3600 for s, r in apps_with_times]
            avg_review_hours = round(sum(durations) / len(durations), 1)
        else:
            avg_review_hours = None

        stats.append({
            "user": uw,
            "reviewed": reviewed,
            "approved": approved_uw,
            "rejected": rejected_uw,
            "approval_rate": approval_rate,
            "rejection_rate": rejection_rate,
            "gross_commission": gross,
            "deductions": deductions,
            "net_commission": net,
            "avg_review_hours": avg_review_hours,
        })

    stats.sort(key=lambda x: x["reviewed"], reverse=True)

    return render(request, "dashboard/hq_underwriter_performance.html", {
        "stats": stats,
    })


@hq_required
def hq_fraud_checks(request):
    """Fraud detection and risk flags page."""
    from core.models import AuditLog
    from django.db.models import Count

    msg = None
    msg_type = "info"

    if request.method == "POST":
        action = request.POST.get("action", "")
        app_id = request.POST.get("app_id")
        note = request.POST.get("note", "").strip()
        try:
            app = FinancingApplication.objects.get(pk=app_id)
            if action == "mark_cleared":
                app.manager_comment = f"[FRAUD-CLEARED] {note}" if note else "[FRAUD-CLEARED]"
                app.save(update_fields=["manager_comment"])
                AuditLog.objects.create(
                    user=request.user, action="hq_fraud_cleared",
                    object_type="FinancingApplication", object_id=str(app.pk),
                    detail={"app": app.application_number, "note": note},
                )
                msg = f"Application {app.application_number} marked as cleared."
                msg_type = "success"
            elif action == "mark_blocked":
                app.status = "rejected"
                app.manager_comment = f"[FRAUD-BLOCKED] {note}" if note else "[FRAUD-BLOCKED]"
                app.save(update_fields=["status", "manager_comment"])
                AuditLog.objects.create(
                    user=request.user, action="hq_fraud_blocked",
                    object_type="FinancingApplication", object_id=str(app.pk),
                    detail={"app": app.application_number, "note": note},
                )
                msg = f"Application {app.application_number} blocked."
                msg_type = "warning"
        except FinancingApplication.DoesNotExist:
            msg = "Application not found."
            msg_type = "error"
        except Exception as exc:
            msg = f"Error: {exc}"
            msg_type = "error"

    # Duplicate national IDs
    dup_ids = (
        FinancingApplication.objects.exclude(national_id="")
        .values("national_id")
        .annotate(cnt=Count("id"))
        .filter(cnt__gt=1)
        .order_by("-cnt")[:20]
    )
    # Duplicate phones
    dup_phones = (
        FinancingApplication.objects.exclude(customer_phone="")
        .values("customer_phone")
        .annotate(cnt=Count("id"))
        .filter(cnt__gt=1)
        .order_by("-cnt")[:20]
    )
    # Same guarantor phone used multiple times
    dup_guarantors = (
        FinancingApplication.objects.exclude(next_of_kin_1_phone="")
        .values("next_of_kin_1_phone")
        .annotate(cnt=Count("id"))
        .filter(cnt__gt=2)
        .order_by("-cnt")[:20]
    )
    # Duplicate IMEI
    dup_imei = (
        FinancingApplication.objects.exclude(imei_number="")
        .values("imei_number")
        .annotate(cnt=Count("id"))
        .filter(cnt__gt=1)
        .order_by("-cnt")[:10]
    )
    # Third-party phone user risk flags
    third_party_flags = FinancingApplication.objects.filter(
        third_party_phone_user_risk_flagged=True,
        status__in=["pending_review", "under_review", "submitted"],
    ).select_related("created_by").order_by("-created_at")[:20]

    # Applications with blocked/fraud notes
    fraud_marked = FinancingApplication.objects.filter(
        manager_comment__startswith="[FRAUD"
    ).select_related("created_by").order_by("-created_at")[:30]

    return render(request, "dashboard/hq_fraud_checks.html", {
        "dup_ids": list(dup_ids),
        "dup_phones": list(dup_phones),
        "dup_guarantors": list(dup_guarantors),
        "dup_imei": list(dup_imei),
        "third_party_flags": third_party_flags,
        "fraud_marked": fraud_marked,
        "msg": msg,
        "msg_type": msg_type,
    })


@hq_required
def hq_audit_trail(request):
    """System audit trail page."""
    from core.models import AuditLog
    import csv
    from django.http import HttpResponse

    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="audit_trail.csv"'
        writer = csv.writer(response)
        writer.writerow(["Timestamp", "User", "Action", "Object Type", "Object ID", "IP", "Detail"])
        for entry in AuditLog.objects.select_related("user").order_by("-timestamp")[:5000]:
            writer.writerow([
                entry.timestamp, entry.user.username if entry.user_id else "",
                entry.action, entry.object_type, entry.object_id,
                entry.ip_address or "", str(entry.detail or ""),
            ])
        return response

    action_filter = request.GET.get("action", "")
    user_filter = request.GET.get("user", "")
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    object_type_filter = request.GET.get("object_type", "")

    qs = AuditLog.objects.select_related("user").order_by("-timestamp")
    if action_filter:
        qs = qs.filter(action__icontains=action_filter)
    if user_filter:
        qs = qs.filter(Q(user__username__icontains=user_filter) | Q(user__get_full_name__icontains=user_filter))
    if date_from:
        try:
            from datetime import date
            qs = qs.filter(timestamp__date__gte=date.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            from datetime import date
            qs = qs.filter(timestamp__date__lte=date.fromisoformat(date_to))
        except ValueError:
            pass
    if object_type_filter:
        qs = qs.filter(object_type__icontains=object_type_filter)

    entries = qs[:200]
    total_today = AuditLog.objects.filter(timestamp__date=timezone.now().date()).count()
    total_all = AuditLog.objects.count()
    object_types = AuditLog.objects.values_list("object_type", flat=True).distinct().order_by("object_type")

    User = get_user_model()
    all_users = User.objects.filter(
        pk__in=AuditLog.objects.values_list("user", flat=True).distinct()
    ).order_by("username")

    return render(request, "dashboard/hq_audit_trail.html", {
        "entries": entries,
        "total_today": total_today,
        "total_all": total_all,
        "action_filter": action_filter,
        "user_filter": user_filter,
        "date_from": date_from,
        "date_to": date_to,
        "object_type_filter": object_type_filter,
        "object_types": object_types,
        "all_users": all_users,
    })


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

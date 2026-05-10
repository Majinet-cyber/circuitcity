# wallet/views.py
from __future__ import annotations

import csv
import io
import json
from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Tuple, Any

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.mail import send_mail
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q, Sum, QuerySet
from django.http import HttpRequest, JsonResponse, HttpResponseBadRequest, HttpResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import ListView, TemplateView

# ---- OTP alias: requires OTP when ENABLE_2FA=1; otherwise behaves like login_required
try:
    if getattr(settings, "ENABLE_2FA", False):
        from django_otp.decorators import otp_required  # type: ignore
    else:
        raise ImportError
except Exception:  # pragma: no cover
    from django.contrib.auth.decorators import login_required as otp_required  # type: ignore

# Optional tenant helper (don't hard-fail if tenants app is unavailable)
try:
    from tenants.utils import get_active_business  # type: ignore
except Exception:  # pragma: no cover
    def get_active_business(_request):  # type: ignore
        return None

# IDOR-safe scoping helper
try:
    from tenants.scoping import scoped_get_object_or_404  # type: ignore
except ImportError:  # pragma: no cover
    # Fallback to unsafe get_object_or_404 if scoping not available
    scoped_get_object_or_404 = None  # type: ignore

from .models import (
    AdminPurchaseOrder,
    AdminPurchaseOrderItem,
    BudgetRequest,
    Ledger,
    Payment,
    PaymentMethod,
    Payslip,
    PayslipStatus,
    PayoutSchedule,
    PurchaseOrderStatus,
    TxnType,
    WalletTransaction,
)
from .money import q2
from .services import add_txn, agent_wallet_summary, ranking

# Optional: PO forms come from inventory.forms if available
try:
    from inventory.forms import PurchaseOrderHeaderForm, PurchaseOrderItemForm
except Exception:  # pragma: no cover
    PurchaseOrderHeaderForm = None
    PurchaseOrderItemForm = None


# ---------------------------------------------------------------------
# Helpers / guards
# ---------------------------------------------------------------------
def _staff(user) -> bool:
    """
    Manager-like users can access admin views:
    - Admins: user.is_staff
    - Managers: user.profile.is_manager  (if profile exists)
    """
    try:
        return bool(user.is_authenticated and (user.is_staff or user.profile.is_manager))
    except Exception:
        return bool(user.is_authenticated and user.is_staff)


def _month_bounds(year: int, month: int) -> Tuple[date, date]:
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    return first, last


def _sum(qs, **filters) -> Decimal:
    return qs.filter(**filters).aggregate(s=Sum("amount"))["s"] or Decimal("0")


def _maybe_scope_to_business(qs, business):
    """
    Legacy helper: if model has a 'business' field, add business filter;
    otherwise return qs unchanged. (Kept for backward compat.)
    """
    if not business:
        return qs
    try:
        if "business" in [f.name for f in qs.model._meta.get_fields()]:
            return qs.filter(business=business)
    except Exception:
        pass
    return qs


# -------- New: robust scoping to active business (works via multiple relations) --------
from django.contrib.auth import get_user_model
from django.db.models import QuerySet
from typing import Any

def business_users_qs(business):
    """
    Best-effort queryset of users that belong to the given business.
    Tries common relations; returns an empty queryset if we can't match.
    """
    U = get_user_model()
    if not business:
        return U.objects.none()

    try:
        from tenants.models import Membership
        member_ids = (
            Membership.objects.filter(business=business, status="ACTIVE", user__is_active=True)
            .values_list("user_id", flat=True)
            .distinct()
        )
        qs = U.objects.filter(id__in=list(member_ids), is_active=True).order_by("first_name", "last_name", "username")
        if qs.exists():
            return qs
    except Exception:
        pass

    # Try the most likely relations first
    candidates = (
        {"profile__business": business},
        {"business": business},
        {"store__business": business},
        {"memberships__business": business},  # if you have a membership/through model
    )

    # Prefer a path that yields rows; otherwise fall back to the first valid path
    for filt in candidates:
        try:
            qs = U.objects.filter(is_active=True, **filt)
            if qs.exists():
                return qs
        except Exception:
            continue
    for filt in candidates:
        try:
            return U.objects.filter(is_active=True, **filt)
        except Exception:
            continue
    return U.objects.none()


def scope_qs_to_user(qs: QuerySet, request: Any) -> QuerySet:
    """
    Superusers: full queryset.
    Others: restrict to active business via (in order):
      1) direct FKs: business / business_id
      2) via store: store__business / store__business_id
      3) via agent FKs: agent__business / agent__profile__business
      4) FALLBACK: if model has an 'agent' field, filter agent__in users of the business
    If we can't determine a safe path, return qs.none() for non-superusers.
    """
    user = getattr(request, "user", None)
    if getattr(user, "is_superuser", False):
        return qs

    biz = get_active_business(request)
    biz_id = getattr(biz, "id", None)
    if not biz_id:
        return qs.none()

    # 1â€“3: try common relational paths (validate lookups; ignore FieldError)
    for path in (
        {"business_id": biz_id},
        {"business": biz},
        {"store__business_id": biz_id},
        {"store__business": biz},
        {"agent__business_id": biz_id},
        {"agent__business": biz},
        {"agent__profile__business_id": biz_id},
        {"agent__profile__business": biz},
    ):
        try:
            qs.filter(**path)[:0]  # validate lookup
            return qs.filter(**path)
        except Exception:
            continue

    # 4) Fallback by agent membership (works for WalletTransaction with agent FK)
    try:
        field_names = {f.name for f in qs.model._meta.get_fields()}
    except Exception:
        field_names = set()

    if "agent" in field_names or "agent_id" in field_names:
        try:
            users_in_biz = business_users_qs(biz)
            return qs.filter(agent__in=users_in_biz)
        except Exception:
            pass

    return qs.none()


def _staff_options_for_request(request: HttpRequest):
    biz = get_active_business(request)
    qs = business_users_qs(biz)
    if getattr(request.user, "is_superuser", False) and not qs.exists():
        qs = get_user_model().objects.filter(is_active=True).order_by("first_name", "last_name", "username")[:200]
    rows = []
    for user in qs:
        try:
            membership = user.memberships.filter(business=biz, status="ACTIVE").first() if biz else None
        except Exception:
            membership = None
        role = getattr(membership, "role", "") or getattr(getattr(user, "profile", None), "role", "") or ""
        phone = (
            getattr(getattr(user, "profile", None), "phone", "")
            or getattr(getattr(user, "agent_profile", None), "phone", "")
            or ""
        )
        name = user.get_full_name() or user.get_username()
        rows.append(
            {
                "id": user.id,
                "name": name,
                "role": role,
                "email": user.email or "",
                "phone": phone,
                "identifier": str(user.id),
                "label": f"{name} ({role})" if role else name,
            }
        )
    return rows

def _agent_belongs_to_business(agent: Any, business: Any) -> bool:
    """
    Try a few attributes to determine if the agent belongs to the active business.
    If we can't determine cleanly (missing relations), allow superusers only.
    """
    if business is None:
        return False
    try:
        if getattr(agent, "business_id", None) == business.id:
            return True
        prof = getattr(agent, "profile", None)
        if prof and getattr(prof, "business_id", None) == business.id:
            return True
        # If agent has store with business
        store = getattr(agent, "store", None)
        if store and getattr(store, "business_id", None) == business.id:
            return True
    except Exception:
        pass
    return False


def _compute_breakdown(agent, first: date, last: date) -> dict:
    """
    Returns a dict with positive/negative totals and simple type splits
    for the agent's ledger within [first, last].
    """
    qs = WalletTransaction.objects.filter(
        ledger=Ledger.AGENT,
        agent=agent,
        effective_date__gte=first,
        effective_date__lte=last,
    )

    pos_total = _sum(qs, amount__gt=0)
    neg_total = _sum(qs, amount__lt=0)  # negative number or 0

    # Split out common types (only counting positives where it makes sense)
    commission = _sum(qs, type=TxnType.COMMISSION, amount__gt=0)
    bonus = _sum(qs, type=TxnType.BONUS, amount__gt=0)
    advances = -_sum(qs, type=TxnType.ADVANCE, amount__lt=0)  # to positive
    penalties = -_sum(qs, type=TxnType.PENALTY, amount__lt=0)

    return {
        "pos_total": pos_total,
        "neg_total": neg_total,
        "commission": commission,
        "bonus": bonus,
        "advances": advances,
        "penalties": penalties,
    }


def _send_payslip_email(p: Payslip) -> bool:
    """
    Minimal email sender; attach numbers in body.
    Returns True if we think it went out successfully.
    """
    if not getattr(p, "email_to", ""):
        return False

    subject = f"Payslip Â· {p.year}-{p.month:02d} Â· {getattr(settings, 'APP_NAME', 'Emajinet')}"
    body = (
        f"Hello,\n\n"
        f"Here is your payslip for {p.year}-{p.month:02d}.\n\n"
        f"Base salary: MWK {p.base_salary:,.0f}\n"
        f"Commission:  MWK {p.commission:,.0f}\n"
        f"Bonuses/Fee: MWK {p.bonuses_fees:,.0f}\n"
        f"Deductions:  MWK {p.deductions:,.0f}\n"
        f"----------------------------------\n"
        f"Gross:       MWK {p.gross:,.0f}\n"
        f"Net:         MWK {p.net:,.0f}\n\n"
        f"Ref: {p.reference}\n"
        f"-- {getattr(settings, 'APP_NAME', 'Emajinet')}"
    )
    sent = send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [p.email_to], fail_silently=True)
    return bool(sent)


def _json_requested(request: HttpRequest) -> bool:
    """
    True if the client clearly asked for JSON.
    """
    accept = (request.headers.get("Accept") or "").lower()
    return accept.startswith("application/json") or request.GET.get("format") == "json"


def _csv_http_response(rows, filename: str) -> HttpResponse:
    """
    Simple CSV exporter (UTF-8, no BOM). `rows` is an iterable of lists/tuples.
    """
    buf = io.StringIO()
    w = csv.writer(buf)
    for r in rows:
        w.writerow(r)
    data = buf.getvalue().encode("utf-8")
    resp = HttpResponse(data, content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


# =====================================================================
# JSON APIs used by the wallet page
# =====================================================================

@login_required
@require_GET
def api_txn_types(request: HttpRequest):
    """Return available transaction types for the Reason dropdown."""
    return JsonResponse({
        "ok": True,
        "types": [{"value": v, "label": lbl} for v, lbl in TxnType.choices],
    })


@login_required
@require_GET
def api_summary(request: HttpRequest):
    """Return the current user's wallet summary (balance, etc.)."""
    s = agent_wallet_summary(request.user)

    def ser(val):
        return float(val) if isinstance(val, Decimal) else val

    if isinstance(s, dict):
        s = {k: ser(v) for k, v in s.items()}

    return JsonResponse({"ok": True, "summary": s})


@login_required
@require_POST
def api_add_txn(request: HttpRequest):
    """
    Add a transaction to the current user's agent wallet.
    Accepts JSON or form-encoded data.
    """
    if request.content_type and "application/json" in request.content_type.lower():
        try:
            data = json.loads(request.body.decode() or "{}")
        except Exception:
            data = {}
    else:
        data = request.POST

    # Parse fields
    try:
        amount = Decimal(str(data.get("amount", "0") or "0"))
    except (InvalidOperation, TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Invalid amount."}, status=400)

    ttype = (data.get("type") or data.get("reason") or "").strip()
    note = (data.get("note") or data.get("memo") or "").strip()

    if ttype not in TxnType.values:
        return JsonResponse({"ok": False, "error": "Invalid reason/type."}, status=400)

    # Post to the AGENT ledger (services.add_txn handles sign/validation)
    add_txn(
        agent=request.user,
        amount=amount,
        type=ttype,
        note=note,
        created_by=request.user,
        ledger=Ledger.AGENT,
    )
    return JsonResponse({"ok": True})


def _decimal_post(request: HttpRequest, key: str) -> Decimal | None:
    if key not in request.POST:
        return None
    raw = request.POST.get(key)
    if raw in (None, ""):
        return Decimal("0.00")
    return q2(raw)


def _invalid_decimal_fields(request: HttpRequest, keys: tuple[str, ...]) -> list[str]:
    invalid: list[str] = []
    for key in keys:
        raw = request.POST.get(key)
        if raw in (None, ""):
            continue
        try:
            Decimal(str(raw).replace(",", "").strip())
        except (InvalidOperation, ValueError, TypeError):
            invalid.append(key.replace("_", " "))
    return invalid


def _payslip_components_from_post(request: HttpRequest) -> dict[str, Decimal]:
    keys = ("base_salary", "allowances", "bonuses", "commission", "other_earnings", "advances", "penalties", "other_deductions")
    components: dict[str, Decimal] = {}
    for key in keys:
        value = _decimal_post(request, key)
        if value is not None:
            components[key] = value
    return components


def _employee_snapshot_from_post(request: HttpRequest, agent=None) -> dict[str, str]:
    full_name = (request.POST.get("employee_name") or "").strip()
    role = (request.POST.get("employee_role") or "").strip()
    email = (request.POST.get("employee_email") or "").strip()
    phone = (request.POST.get("employee_phone") or "").strip()
    identifier = (request.POST.get("employee_identifier") or "").strip()
    if agent is not None:
        full_name = full_name or agent.get_full_name() or agent.get_username()
        email = email or getattr(agent, "email", "") or ""
        identifier = identifier or str(agent.id)
        if not role:
            try:
                biz = get_active_business(request)
                membership = agent.memberships.filter(business=biz, status="ACTIVE").first() if biz else None
                role = getattr(membership, "role", "") or ""
            except Exception:
                role = ""
    return {
        "employee_name": full_name,
        "employee_role": role,
        "employee_email": email,
        "employee_phone": phone,
        "employee_identifier": identifier,
    }


def _period_from_post(request: HttpRequest, year: int, month: int) -> tuple[date, date]:
    first, last = _month_bounds(year, month)
    start_raw = request.POST.get("period_start") or ""
    end_raw = request.POST.get("period_end") or ""
    try:
        start = datetime.strptime(start_raw, "%Y-%m-%d").date() if start_raw else first
    except ValueError:
        start = first
    try:
        end = datetime.strptime(end_raw, "%Y-%m-%d").date() if end_raw else last
    except ValueError:
        end = last
    return start, end


def _attendance_summary_for_payslip(agent, business, year: int, month: int) -> dict[str, Any]:
    if agent is None:
        return {}
    try:
        from inventory.models_attendance import TimeLog
        from inventory.views_time import _pair_work_seconds
    except Exception:
        return {}
    first, last = _month_bounds(year, month)
    start = timezone.make_aware(datetime.combine(first, datetime.min.time()))
    end = timezone.make_aware(datetime.combine(last + timedelta(days=1), datetime.min.time()))
    qs = TimeLog.objects.filter(user=agent, ts__gte=start, ts__lt=end).order_by("ts", "id")
    if business is not None:
        qs = qs.filter(business=business)
    events = list(qs)
    if not events:
        return {"days_worked": 0, "hours_worked": "0.00", "open_shifts": 0}
    grouped: dict[date, list[Any]] = {}
    for event in events:
        grouped.setdefault(timezone.localtime(event.ts).date(), []).append(event)
    total_seconds = 0
    open_shifts = 0
    for day_events in grouped.values():
        worked, open_shift, _ = _pair_work_seconds(day_events, timezone.now())
        total_seconds += int(worked or 0)
        open_shifts += 1 if open_shift else 0
    return {
        "days_worked": len(grouped),
        "hours_worked": str(q2(Decimal(total_seconds) / Decimal("3600"))),
        "open_shifts": open_shifts,
    }


# ---------------------------------------------------------------------
# Payslip builder (helper)
# ---------------------------------------------------------------------
def _create_or_update_payslip_and_txn(
    *,
    agent=None,
    year: int,
    month: int,
    created_by,
    send_now: bool = False,
    payment_method: str | None = None,
    components: dict[str, Decimal] | None = None,
    business=None,
    employee_snapshot: dict[str, str] | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> Payslip:
    """
    Compute totals -> create/update Payslip -> post wallet/company mirror txns (for net)
    -> optionally send email now. Returns the Payslip.
    """
    first, last = _month_bounds(year, month)
    breakdown = _compute_breakdown(agent, first, last) if agent is not None else {
        "pos_total": Decimal("0"),
        "neg_total": Decimal("0"),
        "commission": Decimal("0"),
        "bonus": Decimal("0"),
        "advances": Decimal("0"),
        "penalties": Decimal("0"),
    }

    components = components or {}
    # Components - base salary is computed from wallet transactions unless explicitly supplied
    # For Phones agents, this will include the MWK 50,000 base salary transaction
    # For others, falls back to settings default
    from .utils_salary import get_base_salary_for_month
    from tenants.utils import get_active_business
    
    # Try to get business from agent's profile/membership
    try:
        from tenants.models import Membership
        membership = Membership.objects.filter(user=agent, status="ACTIVE").first() if agent is not None else None
        biz = business or (membership.business if membership else None)
    except Exception:
        biz = business
    
    base_salary = get_base_salary_for_month(biz, agent, year, month) if biz and agent is not None else Decimal("0")
    
    if "base_salary" in components:
        base_salary = components["base_salary"]
    # Fallback to settings default if no base salary transaction exists
    elif base_salary == Decimal("0"):
        base_salary = Decimal(getattr(settings, "WALLET_BASE_SALARY", "40000") or "0")
    
    commission = components.get("commission", breakdown["commission"])
    allowances = components.get("allowances", Decimal("0"))
    bonuses = components.get("bonuses", breakdown["bonus"])
    other_earnings = components.get("other_earnings", Decimal("0"))
    advances = components.get("advances", breakdown["advances"])
    penalties = components.get("penalties", breakdown["penalties"])
    other_deductions = components.get("other_deductions", Decimal("0"))
    bonuses_fees = allowances + bonuses
    deductions = advances + penalties + other_deductions

    gross = base_salary + commission + bonuses_fees + other_earnings
    net = gross - deductions
    attendance = _attendance_summary_for_payslip(agent, biz, year, month)
    employee_snapshot = employee_snapshot or {}
    period_start = period_start or first
    period_end = period_end or last

    # Create / update payslip record
    defaults = dict(
            business=biz,
            base_salary=base_salary,
            commission=commission,
            bonuses_fees=bonuses_fees,
            other_earnings=other_earnings,
            deductions=deductions,
            gross=gross,
            net=net,
            created_by=created_by,
            email_to=employee_snapshot.get("employee_email") or getattr(agent, "email", "") if agent is not None else employee_snapshot.get("employee_email", ""),
            period_start=period_start,
            period_end=period_end,
            payment_method_label=payment_method or "",
            **employee_snapshot,
            meta={
                "calc": {
                    "pos_total": str(breakdown["pos_total"]),
                    "neg_total": str(breakdown["neg_total"]),
                    "advances": str(breakdown["advances"]),
                    "penalties": str(breakdown["penalties"]),
                    "allowances": str(allowances),
                    "bonuses": str(bonuses),
                    "commission": str(commission),
                    "other_earnings": str(other_earnings),
                    "other_deductions": str(other_deductions),
                },
                "attendance": attendance,
            },
    )
    if agent is not None:
        p, created = Payslip.objects.get_or_create(
            agent=agent,
            year=year,
            month=month,
            defaults=defaults,
        )
    else:
        p = Payslip.objects.create(agent=None, year=year, month=month, **defaults)
        created = True
    if not created:
        p.business = biz or p.business
        p.period_start = period_start
        p.period_end = period_end
        for key, value in employee_snapshot.items():
            if value:
                setattr(p, key, value)
        p.base_salary = base_salary
        p.commission = commission
        p.bonuses_fees = bonuses_fees
        p.other_earnings = other_earnings
        p.deductions = deductions
        p.gross = gross
        p.net = net
        p.payment_method_label = payment_method or p.payment_method_label
        meta = dict(p.meta or {})
        meta["calc"] = {
            "pos_total": str(breakdown["pos_total"]),
            "neg_total": str(breakdown["neg_total"]),
            "advances": str(advances),
            "penalties": str(penalties),
            "allowances": str(allowances),
            "bonuses": str(bonuses),
            "commission": str(commission),
            "other_earnings": str(other_earnings),
            "other_deductions": str(other_deductions),
        }
        meta["attendance"] = attendance
        p.meta = meta
        if employee_snapshot.get("employee_email"):
            p.email_to = employee_snapshot["employee_email"]
        if not getattr(p, "email_to", "") and agent is not None:
            p.email_to = getattr(agent, "email", "") or ""
        if not getattr(p, "created_by", None):
            p.created_by = created_by
        p.save()

    # Post wallet/company transactions only when net != 0 (avoid noise)
    existing_payout = WalletTransaction.objects.filter(
        type=TxnType.PAYSLIP,
        agent=agent,
        effective_date__gte=first,
        effective_date__lte=last,
        meta__payslip_id=p.id,
    ).exists()
    if agent is not None and net != 0 and not existing_payout:
        # Agent wallet reduces by net (payment out)
        add_txn(
            agent=agent,
            amount=-net,
            type=TxnType.PAYSLIP,
            note=f"Payslip {year}-{month:02d}",
            created_by=created_by,
            meta={"gross": str(gross), "deductions": str(deductions), "payslip_id": p.id},
        )
        # Company mirror increases by net (payout made)
        WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            agent=agent,
            amount=net,
            type=TxnType.PAYSLIP,
            note=f"[Agent {agent.id}] Payslip {year}-{month:02d}",
            created_by=created_by,
            meta={"payslip_id": p.id},
        )

    # Optional: record a Payment row (future integrations)
    if payment_method:
        Payment.objects.create(
            payslip=p,
            method=payment_method if payment_method in PaymentMethod.values else PaymentMethod.MANUAL,
            amount=p.net,
            status="PENDING",
            processed_by=created_by,
            meta={"auto_created": True},
        )

    # Optional: send email now
    if send_now:
        ok = _send_payslip_email(p)
        if ok:
            p.sent_to_email = True
            p.sent_at = timezone.now()
            p.status = "SENT"
            p.save(update_fields=["sent_to_email", "sent_at", "status"])

    return p


# ---------------------------------------------------------------------
# Agent wallet views (login-only; read/own-wallet)
# ---------------------------------------------------------------------
@method_decorator(ensure_csrf_cookie, name="dispatch")
class AgentWalletView(LoginRequiredMixin, TemplateView):
    """
    Agent self wallet page.

    ensure_csrf_cookie -> guarantees a CSRF cookie on first GET so that any
    subsequent fetch/POST from the page has a token (prevents 403 HTML pages
    that used to surface as â€œUnexpected token '<'â€ in the UI).
    """
    template_name = "wallet/agent_wallet.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        u = self.request.user
        biz = get_active_business(self.request)

        # Ensure base salary for Phones agents (idempotent)
        from .utils_salary import ensure_monthly_base_salary_for_agent
        ensure_monthly_base_salary_for_agent(biz, u)

        # Parse date range from query params for filtered earnings view
        from datetime import datetime, timedelta
        
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        range_param = self.request.GET.get('range', 'month').lower()
        
        if range_param == 'today':
            filter_start = today_start
            filter_end = now
            range_label = 'Today'
        elif range_param == '7d':
            filter_start = today_start - timedelta(days=7)
            filter_end = now
            range_label = 'Last 7 Days'
        elif range_param == 'custom':
            start_str = self.request.GET.get('start', '')
            end_str = self.request.GET.get('end', '')
            try:
                start_d = datetime.strptime(start_str, '%Y-%m-%d').date()
                end_d = datetime.strptime(end_str, '%Y-%m-%d').date()
                filter_start = timezone.make_aware(datetime.combine(start_d, datetime.min.time()))
                filter_end = timezone.make_aware(datetime.combine(end_d, datetime.max.time()))
                range_label = f"{start_d.strftime('%b %d')} – {end_d.strftime('%b %d, %Y')}"
            except (ValueError, TypeError):
                # Fallback to this month
                month_start = today_start.replace(day=1)
                filter_start = month_start
                filter_end = now
                range_label = 'This Month'
        else:
            # Default: this month
            month_start = today_start.replace(day=1)
            filter_start = month_start
            filter_end = now
            range_label = 'This Month'
        
        # Get agent's earnings for the filtered period
        try:
            from inventory.services.agent_earnings import get_agent_earnings
            
            earnings_data = get_agent_earnings(
                business=biz,
                start_date=filter_start.date() if hasattr(filter_start, 'date') else filter_start,
                end_date=filter_end.date() if hasattr(filter_end, 'date') else filter_end,
                agent_id=u.id,
            )
            
            # Extract this agent's data
            my_earnings = earnings_data[0] if earnings_data else None
        except Exception:
            my_earnings = None

        # Summary is already per-user; txns also per-user
        txns = WalletTransaction.objects.filter(ledger=Ledger.AGENT, agent=u)
        ctx["agent_summary"] = agent_wallet_summary(u)
        ctx["txns"] = txns.order_by("-effective_date", "-id")[:50]
        
        # Add filtered earnings data
        ctx["my_earnings"] = my_earnings
        ctx["range_key"] = range_param
        ctx["range_label"] = range_label
        ctx["filter_start"] = filter_start.date() if hasattr(filter_start, 'date') else filter_start
        ctx["filter_end"] = filter_end.date() if hasattr(filter_end, 'date') else filter_end

        # Check if commissions are enabled
        commissions_enabled = True
        try:
            from sales.models import CommissionConfig
            config = CommissionConfig.get_active(biz)
            if config:
                commissions_enabled = config.commissions_enabled
        except Exception:
            pass
        ctx["commissions_enabled"] = commissions_enabled

        # Scope tenant-aware lists where possible
        bqs = BudgetRequest.objects.filter(agent=u).order_by("-created_at")
        ctx["budgets"] = bqs[:5]
        
        # Compute dynamic payslips from wallet transactions (so they update immediately)
        # This provides real-time visibility into earnings without waiting for manager to issue payslip
        from datetime import datetime
        from collections import defaultdict
        
        # Get all positive transactions (commissions + bonuses including base salary) grouped by month
        earning_txns = WalletTransaction.objects.filter(
            ledger=Ledger.AGENT,
            agent=u,
            type__in=[TxnType.COMMISSION, TxnType.BONUS],
            amount__gt=0
        ).order_by('-effective_date')[:200]  # Last 200 transactions
        
        # Get all deductions
        deduction_txns = WalletTransaction.objects.filter(
            ledger=Ledger.AGENT,
            agent=u,
            amount__lt=0
        ).order_by('-effective_date')[:100]  # Last 100 deductions
        
        # Group by year-month
        monthly_earnings = defaultdict(lambda: {'gross': Decimal('0'), 'deductions': Decimal('0'), 'count': 0})
        
        for txn in earning_txns:
            year_month = (txn.effective_date.year, txn.effective_date.month)
            monthly_earnings[year_month]['gross'] += txn.amount
            monthly_earnings[year_month]['count'] += 1
        
        for txn in deduction_txns:
            year_month = (txn.effective_date.year, txn.effective_date.month)
            monthly_earnings[year_month]['deductions'] += abs(txn.amount)
        
        # Also check for formal Payslip records (manager-issued)
        formal_payslips = Payslip.objects.filter(agent=u).order_by("-year", "-month")[:5]
        
        # Build unified payslip list
        payslip_list = []
        
        # Add formal payslips first
        formal_months = set()
        for p in formal_payslips:
            payslip_list.append(p)
            formal_months.add((p.year, p.month))
        
        # Add dynamic computed payslips for months without formal payslips
        for (year, month), data in sorted(monthly_earnings.items(), reverse=True)[:5]:
            if (year, month) not in formal_months:
                # Create a temporary payslip-like object
                class DynamicPayslip:
                    def __init__(self, year, month, gross, deductions, count):
                        self.year = year
                        self.month = month
                        self.gross = gross
                        self.deductions = deductions
                        self.net = gross - deductions
                        self.pdf = None
                        self.is_dynamic = True
                        self.txn_count = count
                
                payslip_list.append(DynamicPayslip(year, month, data['gross'], data['deductions'], data['count']))
        
        # Sort by year/month descending and limit to 5
        payslip_list.sort(key=lambda p: (p.year, p.month), reverse=True)
        ctx["payslips"] = payslip_list[:5]

        # For ranking chart on the wallet page, prefer tenant scope if supported by service
        try:
            ctx["ranking_period"] = "month"
            ctx["ranking_rows"] = ranking("month", business=biz)  # type: ignore[arg-type]
        except TypeError:
            # If your ranking(service) doesn't accept business, fall back gracefully
            ctx["ranking_period"] = "month"
            ctx["ranking_rows"] = ranking("month")
        return ctx


class AgentTxnListView(LoginRequiredMixin, ListView):
    template_name = "wallet/agent_txns.html"
    paginate_by = 50

    def get_queryset(self):
        return (
            WalletTransaction.objects.filter(ledger=Ledger.AGENT, agent=self.request.user)
            .order_by("-effective_date", "-id")
        )


@login_required
def api_ranking(request: HttpRequest):
    """
    API endpoint for agent earnings rankings.
    Returns top agents by commission for the specified period.
    """
    period = request.GET.get("period", "month")
    biz = get_active_business(request)
    
    if not biz:
        return JsonResponse({"period": period, "rows": []})
    
    # Use the agent_earnings service for consistent ranking
    try:
        from inventory.services.agent_earnings import get_agent_earnings
        from datetime import date, timedelta
        from django.utils import timezone
        
        today = timezone.localdate()
        
        if period == "all":
            start_date = None
            end_date = today
        else:  # month
            start_date = today.replace(day=1)
            end_date = today
        
        # Get earnings data
        earnings_data = get_agent_earnings(
            business=biz,
            start_date=start_date,
            end_date=end_date,
        )
        
        # Convert to format expected by frontend
        rows = []
        for earning in earnings_data[:20]:  # Top 20
            rows.append({
                "agent__id": earning.agent_id,
                "agent__first_name": earning.agent_name.split()[0] if " " in earning.agent_name else earning.agent_name,
                "agent__last_name": " ".join(earning.agent_name.split()[1:]) if " " in earning.agent_name else "",
                "total": float(earning.total_commission),
            })
        
        return JsonResponse({"period": period, "rows": rows})
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in api_ranking: {e}")
        
        # Fallback to old ranking function
        try:
            rows = ranking(period, business=biz)  # type: ignore[arg-type]
        except TypeError:
            rows = ranking(period)
        return JsonResponse({"rows": rows})


# ---------------------------------------------------------------------
# Agent extras expected by urls.py
# ---------------------------------------------------------------------
@login_required
def entry_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Transaction drill-down. Agents can see their own; staff can see their business's.
    
    SECURITY: Always scoped to active business to prevent IDOR.
    """
    business = get_active_business(request)
    
    if _staff(request.user):
        # Staff can see any transaction within their business
        if business:
            entry = get_object_or_404(WalletTransaction, pk=pk, business=business)
        else:
            # Superuser with no business context can see any
            entry = get_object_or_404(WalletTransaction, pk=pk)
    else:
        # Agents can only see their own transactions
        if business:
            entry = get_object_or_404(
                WalletTransaction, pk=pk, agent=request.user, ledger=Ledger.AGENT, business=business
            )
        else:
            entry = get_object_or_404(WalletTransaction, pk=pk, agent=request.user, ledger=Ledger.AGENT)
    return render(request, "wallet/entry_detail.html", {"entry": entry})


@login_required
def payslip_download(request: HttpRequest, year: int, month: int) -> HttpResponse:
    """
    Lightweight HTML "PDF" fallback for an agent's payslip for a period.
    (No external PDF dependency; downloads as HTML if PDF lib isnâ€™t present.)
    """
    p = get_object_or_404(Payslip, agent=request.user, year=year, month=month)
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Payslip {p.year}-{p.month:02d}</title>
<style>body{{font-family:system-ui,Segoe UI,Arial,sans-serif}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #eee;padding:6px;text-align:right}}th:first-child,td:first-child{{text-align:left}}</style>
</head><body>
<h2>Payslip â€” {p.year}-{p.month:02d}</h2>
<p><strong>Agent:</strong> {getattr(request.user, "get_full_name", lambda: request.user.username)()}</p>
<table>
<tr><th>Base Salary</th><td>{p.base_salary:.2f}</td></tr>
<tr><th>Commission</th><td>{p.commission:.2f}</td></tr>
<tr><th>Bonuses/Fees</th><td>{p.bonuses_fees:.2f}</td></tr>
<tr><th>Deductions</th><td>{p.deductions:.2f}</td></tr>
<tr><th>Gross</th><td>{p.gross:.2f}</td></tr>
<tr><th>Net</th><td><strong>{p.net:.2f}</strong></td></tr>
</table>
<p>Reference: {p.reference}</p>
</body></html>"""
    resp = HttpResponse(html)
    resp["Content-Disposition"] = f'attachment; filename="payslip-{p.year}-{p.month:02d}.html"'
    return resp


def _render_payslip_pdf(p: Payslip, requester) -> HttpResponse:
    attendance = (p.meta or {}).get("attendance") or {}
    calc = (p.meta or {}).get("calc") or {}
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception:
        html = render(requester, "wallet/payslip_pdf.html", {"payslip": p, "p": p, "attendance": attendance})
        html["Content-Disposition"] = f'attachment; filename="payslip-{p.reference or p.id}.html"'
        return html

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=40, rightMargin=40, topMargin=38, bottomMargin=32)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("PayslipTitle", parent=styles["Heading1"], fontSize=18, textColor=colors.HexColor("#065f46"))
    employee_name = p.display_employee_name
    business_name = getattr(p.business, "name", "") or getattr(get_active_business(requester), "name", "") or "Emajinet"
    period = (
        f"{p.period_start:%Y-%m-%d} to {p.period_end:%Y-%m-%d}"
        if p.period_start and p.period_end
        else f"{p.year}-{p.month:02d}"
    )
    rows = [
        ["Business", business_name],
        ["Employee", employee_name],
        ["Role / position", p.employee_role or ""],
        ["Employee ID", p.employee_identifier or ""],
        ["Pay period", period],
        ["Issue date", timezone.localtime(p.issued_at).strftime("%Y-%m-%d") if p.issued_at else ""],
        ["Days worked", attendance.get("days_worked", "")],
        ["Hours worked", attendance.get("hours_worked", "")],
        ["Payment method", p.payment_method_label or "Manual"],
        ["Prepared by", getattr(p.created_by, "get_username", lambda: "")() if p.created_by_id else ""],
        ["Status", p.get_status_display()],
    ]
    earnings_rows = [
        ["Earnings", "Amount"],
        ["Basic salary", f"MWK {p.base_salary:,.2f}"],
        ["Commission", f"MWK {p.commission:,.2f}"],
        ["Allowances", f"MWK {Decimal(str(calc.get('allowances') or 0)):,.2f}"],
        ["Bonuses", f"MWK {Decimal(str(calc.get('bonuses') or 0)):,.2f}"],
        ["Other earnings", f"MWK {p.other_earnings:,.2f}"],
        ["Gross pay", f"MWK {p.gross:,.2f}"],
    ]
    deduction_rows = [
        ["Deductions", "Amount"],
        ["Advances", f"MWK {Decimal(str(calc.get('advances') or 0)):,.2f}"],
        ["Penalties", f"MWK {Decimal(str(calc.get('penalties') or 0)):,.2f}"],
        ["Other deductions", f"MWK {Decimal(str(calc.get('other_deductions') or 0)):,.2f}"],
        ["Total deductions", f"MWK {p.deductions:,.2f}"],
        ["Net pay", f"MWK {p.net:,.2f}"],
    ]
    table = Table(rows, colWidths=[150, 330])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dcfce7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#064e3b")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1fae5")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("PADDING", (0, 0), (-1, -1), 7),
    ]))
    earnings = Table(earnings_rows, colWidths=[230, 250])
    deductions_table = Table(deduction_rows, colWidths=[230, 250])
    for t in (earnings, deductions_table):
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ecfdf5")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1fae5")),
            ("PADDING", (0, 0), (-1, -1), 7),
        ]))
    doc.build([
        Paragraph("Payslip", title_style),
        Paragraph(f"{business_name} | Reference: {p.reference}", styles["Normal"]),
        Spacer(1, 14),
        table,
        Spacer(1, 14),
        earnings,
        Spacer(1, 14),
        deductions_table,
        Spacer(1, 28),
        Paragraph("Prepared by: ____________________    Employee signature: ____________________", styles["Normal"]),
    ])
    resp = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="payslip-{p.reference or p.id}.pdf"'
    return resp


@login_required
def payslip_download_by_id(request: HttpRequest, pk: int) -> HttpResponse:
    p = get_object_or_404(Payslip.objects.select_related("agent", "created_by", "business"), pk=pk)
    if not (_staff(request.user) or p.agent_id == request.user.id):
        return HttpResponse("Not allowed", status=403)
    if _staff(request.user) and not request.user.is_superuser:
        biz = get_active_business(request)
        same_business = bool(biz and getattr(p, "business_id", None) == getattr(biz, "id", None))
        if not same_business and (not p.agent_id or not _agent_belongs_to_business(p.agent, biz)):
            return HttpResponse("Not allowed", status=403)
    return _render_payslip_pdf(p, request)


@otp_required
@require_POST
def payslip_set_status(request: HttpRequest, pk: int, action: str) -> HttpResponse:
    if not _staff(request.user):
        return redirect("wallet:agent_wallet")
    p = get_object_or_404(Payslip.objects.select_related("agent", "business"), pk=pk)
    biz = get_active_business(request)
    same_business = bool(biz and getattr(p, "business_id", None) == getattr(biz, "id", None))
    if not request.user.is_superuser and not same_business and (not p.agent_id or not _agent_belongs_to_business(p.agent, biz)):
        return HttpResponse("Not allowed", status=403)
    if action == "issued":
        p.status = PayslipStatus.SENT
        p.sent_at = p.sent_at or timezone.now()
    elif action == "paid":
        p.status = PayslipStatus.PAID
    else:
        messages.error(request, "Invalid payslip action.")
        return redirect("wallet:admin_agent", agent_id=p.agent_id) if p.agent_id else redirect("wallet:admin_payslips")
    p.save(update_fields=["status", "sent_at"] if action == "issued" else ["status"])
    messages.success(request, f"Payslip marked as {p.get_status_display()}.")
    return redirect("wallet:admin_agent", agent_id=p.agent_id) if p.agent_id else redirect("wallet:admin_payslips")


@login_required
def budget_new(request: HttpRequest) -> HttpResponse:
    """
    Simple agent budget request creator (POST title, amount, reason).
    """
    if request.method == "POST":
        title = (request.POST.get("title") or "").strip() or "Budget Request"
        reason = (request.POST.get("reason") or "").strip()
        try:
            amount = Decimal(str(request.POST.get("amount") or "0"))
        except (InvalidOperation, ValueError, TypeError):
            messages.error(request, "Invalid amount.")
            return redirect("wallet:agent_wallet")

        BudgetRequest.objects.create(
            agent=request.user,
            title=title,
            amount=amount,
            reason=reason,
        )
        messages.success(request, "Budget request submitted.")
        return redirect("wallet:agent_wallet")

    # GET â†’ minimal form (fallback if you don't have a template)
    return render(request, "wallet/budget_new.html", {})


# ---------------------------------------------------------------------
# Admin wallet views (OTP-required)
# ---------------------------------------------------------------------
@method_decorator([otp_required, ensure_csrf_cookie], name="dispatch")
class AdminWalletHome(LoginRequiredMixin, TemplateView):
    template_name = "wallet/admin_home.html"

    def dispatch(self, request, *args, **kwargs):
        if not _staff(request.user):
            return redirect("wallet:agent_wallet")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Scope company ledger to user (superuser sees all; managers see their business)
        qs = WalletTransaction.objects.filter(ledger=Ledger.COMPANY)
        qs = scope_qs_to_user(qs, self.request)

        ctx["company_spend"] = qs.aggregate(s=Sum("amount"))["s"] or Decimal("0")
        ctx["recent"] = qs.select_related("agent").order_by("-created_at")[:30]

        pending = scope_qs_to_user(BudgetRequest.objects.all(), self.request)
        ctx["budgets_pending"] = pending.filter(status=BudgetRequest.Status.PENDING).count()
        
        # Get commission configuration
        business = get_active_business(self.request)
        if business:
            try:
                from tenants.utils_commission import get_phone_commission_pct
                commission_fraction = get_phone_commission_pct(business)
                ctx["commission_pct"] = commission_fraction * 100  # Convert to percentage for display
            except Exception:
                ctx["commission_pct"] = Decimal("10.00")  # Default
        else:
            ctx["commission_pct"] = Decimal("10.00")
        
        # Get cost summary for current month
        if business:
            try:
                from .services_costs import get_business_costs_for_period
                cost_summary = get_business_costs_for_period(business, period='month')
                ctx["total_costs_this_month"] = cost_summary['overall_costs_total']
                ctx["recurring_monthly_costs"] = cost_summary['recurring_costs']
            except Exception:
                ctx["total_costs_this_month"] = Decimal("0.00")
                ctx["recurring_monthly_costs"] = Decimal("0.00")
        else:
            ctx["total_costs_this_month"] = Decimal("0.00")
            ctx["recurring_monthly_costs"] = Decimal("0.00")
        
        # Compute Business Spend Trend (costs + commissions) for recent days
        ctx["business_spend_trend"] = self._compute_spend_trend(business)
        
        # Set active_tab to prevent template errors
        ctx["active_tab"] = "overview"
        return ctx
    
    def _compute_spend_trend(self, business):
        """
        Compute spend trend data (costs + commissions) for the last 14 days.
        Returns JSON string with daily aggregates.
        """
        today = timezone.localdate()
        days_back = 14
        start_date = today - timedelta(days=days_back)
        
        # Get costs (WalletTransaction with type in COST_ONCE_OFF, COST_RECURRING)
        cost_qs = WalletTransaction.objects.filter(
            ledger=Ledger.COMPANY,
            type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING],
            effective_date__gte=start_date,
            effective_date__lte=today,
        )
        if business:
            cost_qs = cost_qs.filter(business=business)
        
        cost_by_date = cost_qs.values('effective_date').annotate(total=Sum('amount'))
        
        # Get commissions (SaleCommission)
        try:
            from sales.models import SaleCommission
            commission_qs = SaleCommission.objects.filter(
                created_at__date__gte=start_date,
                created_at__date__lte=today,
            )
            if business:
                commission_qs = commission_qs.filter(business=business)
            
            commission_by_date = commission_qs.extra(
                select={'date': 'DATE(created_at)'}
            ).values('date').annotate(total=Sum('net_amount'))
        except Exception:
            # If SaleCommission model is not available or error occurs
            commission_by_date = []
        
        # Build a dictionary keyed by date
        trend_map = {}
        
        for row in cost_by_date:
            d = row['effective_date']
            if d not in trend_map:
                trend_map[d] = {'date': d, 'costs': 0, 'commissions': 0}
            # Costs are stored as negative, convert to positive for display
            trend_map[d]['costs'] += abs(float(row['total'] or 0))
        
        for row in commission_by_date:
            # Handle both dict key formats
            d = row.get('date') or row.get('created_at__date')
            if isinstance(d, str):
                d = date.fromisoformat(d)
            if d not in trend_map:
                trend_map[d] = {'date': d, 'costs': 0, 'commissions': 0}
            trend_map[d]['commissions'] += float(row['total'] or 0)
        
        # Convert to sorted list
        trend_data = sorted(trend_map.values(), key=lambda x: x['date'])
        
        # Convert to JSON
        return json.dumps(trend_data, cls=DjangoJSONEncoder)


@method_decorator([otp_required, ensure_csrf_cookie], name="dispatch")
class AdminAgentWallet(LoginRequiredMixin, TemplateView):
    template_name = "wallet/admin_agent.html"

    def dispatch(self, request, *args, **kwargs):
        if not _staff(request.user):
            return redirect("wallet:agent_wallet")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, agent_id, **kwargs):
        U = get_user_model()
        agent = get_object_or_404(U, id=agent_id)
        ctx = super().get_context_data(**kwargs)
        biz = get_active_business(self.request)

        # Non-superusers may only access agents in their active business
        if not self.request.user.is_superuser and not _agent_belongs_to_business(agent, biz):
            raise Http404("Agent not found")

        ctx["agent"] = agent
        ctx["summary"] = agent_wallet_summary(agent)

        tx = WalletTransaction.objects.filter(ledger=Ledger.AGENT, agent=agent)
        ctx["txns"] = tx.order_by("-effective_date", "-id")[:100]

        bqs = scope_qs_to_user(BudgetRequest.objects.filter(agent=agent), self.request)
        pqs = scope_qs_to_user(Payslip.objects.filter(agent=agent), self.request)

        ctx["budgets"] = bqs.order_by("-created_at")
        ctx["payslips"] = pqs.order_by("-year", "-month")
        return ctx


@method_decorator([otp_required, ensure_csrf_cookie], name="dispatch")
class AdminIssueTxnView(LoginRequiredMixin, TemplateView):
    template_name = "wallet/admin_issue.html"

    def dispatch(self, request, *args, **kwargs):
        if not _staff(request.user):
            return redirect("wallet:agent_wallet")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        U = get_user_model()
        agent = get_object_or_404(U, id=request.POST.get("agent_id"))
        # Ensure manager can only issue to agents in their business
        if not request.user.is_superuser and not _agent_belongs_to_business(agent, get_active_business(request)):
            return HttpResponse("Not allowed for this agent.", status=403)

        amount = Decimal(request.POST.get("amount", "0"))
        ttype = request.POST.get("type")
        note = request.POST.get("note", "")

        # Agent wallet (signed amount)
        add_txn(
            agent=agent,
            amount=amount,
            type=ttype,
            note=note,
            created_by=request.user,
            ledger=Ledger.AGENT,
        )

        # Mirror to company ledger for a full business trail
        WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            agent=agent,
            amount=-amount,
            type=ttype,
            note=f"[Agent {agent.id}] {note}",
            created_by=request.user,
        )
        return redirect("wallet:admin_agent", agent_id=agent.id)


@method_decorator([otp_required, ensure_csrf_cookie], name="dispatch")
class AdminBudgetsView(LoginRequiredMixin, TemplateView):
    template_name = "wallet/admin_budgets.html"

    def dispatch(self, request, *args, **kwargs):
        if not _staff(request.user):
            return redirect("wallet:agent_wallet")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        pending = scope_qs_to_user(BudgetRequest.objects.all(), self.request).filter(
            status=BudgetRequest.Status.PENDING
        ).select_related("agent")
        approved = scope_qs_to_user(BudgetRequest.objects.all(), self.request).filter(
            status=BudgetRequest.Status.APPROVED
        ).select_related("agent")
        paid = scope_qs_to_user(BudgetRequest.objects.all(), self.request).filter(
            status=BudgetRequest.Status.PAID
        ).select_related("agent")

        ctx["pending"] = pending
        ctx["approved"] = approved
        ctx["paid"] = paid
        return ctx

    def post(self, request):
        bid = int(request.POST["budget_id"])
        action = request.POST["action"]  # approve / reject / pay
        
        # SECURITY: Scope to business BEFORE fetching to prevent IDOR
        biz = get_active_business(request)
        if request.user.is_superuser and not biz:
            # Superuser without business context can access any
            b = get_object_or_404(BudgetRequest, id=bid)
        else:
            # Scope via agent membership - only get budgets from agents in our business
            from tenants.models import Membership
            agent_ids = Membership.objects.filter(
                business=biz, status="ACTIVE"
            ).values_list("user_id", flat=True)
            b = get_object_or_404(BudgetRequest, id=bid, agent_id__in=list(agent_ids))

        if action == "approve":
            b.status = BudgetRequest.Status.APPROVED
        elif action == "reject":
            b.status = BudgetRequest.Status.REJECTED
        elif action == "pay":
            b.status = BudgetRequest.Status.PAID
            add_txn(
                agent=b.agent,
                amount=Decimal(b.amount),
                type=TxnType.BUDGET,
                note=f"Budget: {getattr(b, 'title', 'Approved budget')}",
                created_by=request.user,
            )
            WalletTransaction.objects.create(
                ledger=Ledger.COMPANY,
                agent=b.agent,
                amount=-Decimal(b.amount),
                type=TxnType.BUDGET,
                note=f"[Agent {b.agent_id}] {getattr(b, 'title', 'Approved budget')}",
                created_by=request.user,
            )

        b.decided_by = request.user
        b.decided_at = timezone.now()
        b.save()
        return redirect("wallet:admin_budgets")


# ---------------------------------------------------------------------
# Admin extras (for urls.py additive routes)
# ---------------------------------------------------------------------
@otp_required
def admin_budget_list(request: HttpRequest) -> HttpResponse:
    if not _staff(request.user):
        return redirect("wallet:agent_wallet")

    qs = scope_qs_to_user(BudgetRequest.objects.all().select_related("agent"), request)
    status = request.GET.get("status")
    if status and status.lower() in {s for s, _ in BudgetRequest.Status.choices}:
        qs = qs.filter(status=status.lower())
    rows = qs.order_by("-created_at")[:200]
    return render(request, "wallet/admin_budget_list.html", {"rows": rows, "business": get_active_business(request)})


@otp_required
def admin_budget_set_status(request: HttpRequest, pk: int, action: str) -> HttpResponse:
    if not _staff(request.user):
        return redirect("wallet:agent_wallet")

    # SECURITY: Scope to business BEFORE fetching to prevent IDOR
    biz = get_active_business(request)
    if request.user.is_superuser and not biz:
        # Superuser without business context can access any
        b = get_object_or_404(BudgetRequest, pk=pk)
    else:
        # Scope via agent membership - only get budgets from agents in our business
        from tenants.models import Membership
        agent_ids = Membership.objects.filter(
            business=biz, status="ACTIVE"
        ).values_list("user_id", flat=True)
        try:
            b = BudgetRequest.objects.get(pk=pk, agent_id__in=list(agent_ids))
        except BudgetRequest.DoesNotExist:
            raise Http404("Budget request not found")

    action = (action or "").lower()
    if action == "approve":
        b.status = BudgetRequest.Status.APPROVED
    elif action == "reject":
        b.status = BudgetRequest.Status.REJECTED
    elif action == "paid" or action == "pay":
        b.status = BudgetRequest.Status.PAID
    else:
        messages.error(request, "Invalid action.")
        return redirect("wallet:admin_budget_list")
    b.decided_by = request.user
    b.decided_at = timezone.now()
    b.save(update_fields=["status", "decided_by", "decided_at"])
    messages.success(request, f"Budget set to {b.status}.")
    return redirect("wallet:admin_budget_list")


@otp_required
def admin_entries_export_csv(request: HttpRequest) -> HttpResponse:
    if not _staff(request.user):
        return redirect("wallet:agent_wallet")

    qs = scope_qs_to_user(WalletTransaction.objects.all().select_related("agent"), request)

    # Optional filters
    agent_id = request.GET.get("agent_id")
    if agent_id:
        qs = qs.filter(agent_id=agent_id)
    year = request.GET.get("year")
    month = request.GET.get("month")
    if year and month:
        y, m = int(year), int(month)
        first, last = _month_bounds(y, m)
        qs = qs.filter(effective_date__gte=first, effective_date__lte=last)

    rows = [
        ["created_at", "effective_date", "ledger", "agent_id", "type", "amount", "note", "reference"]
    ]
    for t in qs.order_by("effective_date", "agent_id", "created_at", "id").iterator():
        rows.append([
            t.created_at.isoformat(timespec="seconds"),
            t.effective_date.isoformat(),
            t.ledger,
            t.agent_id or "",
            t.type,
            f"{t.amount:.2f}",
            t.note or "",
            t.reference or "",
        ])
    return _csv_http_response(rows, "wallet_transactions.csv")


# ---------------------------------------------------------------------
# Payslips (single + bulk + schedules) â€” OTP-required
# ---------------------------------------------------------------------
@otp_required
def issue_payslip(request, agent_id: int, year: int, month: int):
    """
    Legacy single-agent endpoint. Now delegates to the bulk-capable helper.
    Returns JSON if explicitly requested.
    """
    if not _staff(request.user):
        return redirect("wallet:agent_wallet")

    U = get_user_model()
    agent = get_object_or_404(U, id=agent_id)

    # Enforce manager scope for target agent
    if not request.user.is_superuser and not _agent_belongs_to_business(agent, get_active_business(request)):
        return HttpResponse("Not allowed for this agent.", status=403)

    p = _create_or_update_payslip_and_txn(
        agent=agent,
        year=year,
        month=month,
        created_by=request.user,
        send_now=bool(request.GET.get("send") == "1" or request.POST.get("send_now")),
        payment_method=request.POST.get("method") if request.method == "POST" else None,
        components=_payslip_components_from_post(request) if request.method == "POST" else None,
    )
    if _json_requested(request):
        return JsonResponse(
            {"ok": True, "agent": agent.id, "reference": p.reference, "net": float(p.net)}
        )
    return redirect("wallet:admin_agent", agent_id=agent.id)


@method_decorator([otp_required, ensure_csrf_cookie], name="dispatch")
class AdminIssuePayslipView(LoginRequiredMixin, TemplateView):
    """
    Issue a SINGLE payslip via form (agent, year, month, send_now, method).
    """
    template_name = "wallet/admin_issue_payslip.html"

    def dispatch(self, request, *args, **kwargs):
        if not _staff(request.user):
            return redirect("wallet:agent_wallet")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        staff_options = _staff_options_for_request(self.request)
        ctx["staff_options"] = staff_options
        ctx["agents"] = [row["id"] for row in staff_options]
        today = timezone.localdate()
        ctx["year"] = int(self.request.GET.get("year", today.year))
        ctx["month"] = int(self.request.GET.get("month", today.month))
        return ctx

    def post(self, request: HttpRequest):
        U = get_user_model()
        agent_id = (request.POST.get("agent_id") or "").strip()
        agent = get_object_or_404(U, id=agent_id) if agent_id else None
        # Enforce manager scope
        if agent is not None and not request.user.is_superuser and not _agent_belongs_to_business(agent, get_active_business(request)):
            return HttpResponse("Not allowed for this agent.", status=403)

        try:
            year = int(request.POST.get("year"))
            month = int(request.POST.get("month"))
            if month < 1 or month > 12:
                raise ValueError
        except (TypeError, ValueError):
            messages.error(request, "Choose a valid payslip month and year.")
            return redirect("wallet:admin_issue_payslip")
        send_now = request.POST.get("send_now") in ("1", "true", "on", "yes")
        method = request.POST.get("method")  # optional
        invalid_money = _invalid_decimal_fields(
            request,
            ("base_salary", "allowances", "bonuses", "commission", "other_earnings", "advances", "penalties", "other_deductions"),
        )
        if invalid_money:
            messages.error(request, f"Enter valid money values for: {', '.join(invalid_money)}.")
            return redirect("wallet:admin_issue_payslip")
        components = _payslip_components_from_post(request)
        employee_snapshot = _employee_snapshot_from_post(request, agent)
        if not employee_snapshot.get("employee_name"):
            messages.error(request, "Employee name is required. Select staff or enter employee details manually.")
            return redirect("wallet:admin_issue_payslip")
        provided_earnings = sum(
            components.get(key, Decimal("0"))
            for key in ("base_salary", "allowances", "bonuses", "commission", "other_earnings")
        )
        if agent is None and provided_earnings <= 0:
            messages.error(request, "Enter basic salary or another earnings amount before issuing.")
            return redirect("wallet:admin_issue_payslip")
        period_start, period_end = _period_from_post(request, year, month)
        action = (request.POST.get("action") or "issue").lower()

        if action == "preview":
            preview = Payslip(
                business=get_active_business(request),
                agent=agent,
                year=year,
                month=month,
                period_start=period_start,
                period_end=period_end,
                base_salary=components.get("base_salary", Decimal("0")),
                commission=components.get("commission", Decimal("0")),
                bonuses_fees=components.get("allowances", Decimal("0")) + components.get("bonuses", Decimal("0")),
                other_earnings=components.get("other_earnings", Decimal("0")),
                deductions=components.get("advances", Decimal("0")) + components.get("penalties", Decimal("0")) + components.get("other_deductions", Decimal("0")),
                payment_method_label=method or "Manual",
                created_by=request.user,
                meta={"calc": {k: str(v) for k, v in components.items()}},
                **employee_snapshot,
            )
            preview.save = lambda *args, **kwargs: None  # type: ignore[method-assign]
            preview.gross = q2(preview.base_salary + preview.commission + preview.bonuses_fees + preview.other_earnings)
            preview.net = q2(preview.gross - preview.deductions)
            ctx = self.get_context_data()
            ctx.update({"preview_payslip": preview, "preview_calc": components})
            return render(request, self.template_name, ctx)

        p = _create_or_update_payslip_and_txn(
            agent=agent,
            year=year,
            month=month,
            created_by=request.user,
            send_now=send_now,
            payment_method=method,
            components=components,
            business=get_active_business(request),
            employee_snapshot=employee_snapshot,
            period_start=period_start,
            period_end=period_end,
        )
        if action == "issue" and p.status != PayslipStatus.SENT:
            p.status = PayslipStatus.SENT
            p.sent_at = p.sent_at or timezone.now()
            p.save(update_fields=["status", "sent_at"])
        if action in {"generate_pdf", "download_pdf"}:
            return _render_payslip_pdf(p, request)
        if _json_requested(request):
            return JsonResponse(
                {"ok": True, "agent": getattr(agent, "id", None), "reference": p.reference, "net": float(p.net)}
            )
        messages.success(request, f"Payslip {p.reference} issued for {p.display_employee_name}.")
        return redirect("wallet:admin_agent", agent_id=agent.id) if agent is not None else redirect("wallet:admin_payslips")


@method_decorator([otp_required, ensure_csrf_cookie], name="dispatch")
class AdminPayslipBulkView(LoginRequiredMixin, TemplateView):
    """
    GET  -> form to pick agents + period + send_now flag
    POST -> issue payslips for selected agents (and optionally email)
    """
    template_name = "wallet/admin_payslips.html"

    def dispatch(self, request, *args, **kwargs):
        if not _staff(request.user):
            return redirect("wallet:agent_wallet")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        staff_options = _staff_options_for_request(self.request)
        ctx["staff_options"] = staff_options
        ctx["agents"] = [row["id"] for row in staff_options]
        today = timezone.localdate()
        ctx["year"] = int(self.request.GET.get("year", today.year))
        ctx["month"] = int(self.request.GET.get("month", today.month))
        recent = Payslip.objects.select_related("agent", "created_by", "business")
        biz = get_active_business(self.request)
        if biz is not None:
            recent = recent.filter(Q(business=biz) | Q(agent__in=business_users_qs(biz)))
        elif not self.request.user.is_superuser:
            recent = recent.none()
        ctx["recent_payslips"] = recent.order_by("-issued_at")[:50]
        return ctx

    def post(self, request: HttpRequest):
        U = get_user_model()
        # Accept multiple forms: agent_ids=1&agent_ids=2 or comma string
        raw = request.POST.getlist("agent_ids") or request.POST.get("agent_ids", "")
        if isinstance(raw, str):
            agent_ids = [x for x in (y.strip() for y in raw.split(",")) if x]
        else:
            agent_ids = raw

        if not agent_ids and _json_requested(request):
            return JsonResponse({"ok": False, "error": "No agents selected."}, status=400)
        if not agent_ids:
            messages.error(request, "Select at least one active staff member, or use the single payslip form for manual entry.")
            return redirect("wallet:admin_payslips")

        try:
            year = int(request.POST.get("year"))
            month = int(request.POST.get("month"))
            if month < 1 or month > 12:
                raise ValueError
        except (TypeError, ValueError):
            messages.error(request, "Choose a valid payslip month and year.")
            return redirect("wallet:admin_payslips")
        send_now = request.POST.get("send_now") in ("1", "true", "on", "yes")
        method = request.POST.get("method")  # optional
        invalid_money = _invalid_decimal_fields(
            request,
            ("base_salary", "allowances", "bonuses", "commission", "other_earnings", "advances", "penalties", "other_deductions"),
        )
        if invalid_money:
            messages.error(request, f"Enter valid money values for: {', '.join(invalid_money)}.")
            return redirect("wallet:admin_payslips")

        agents = list(U.objects.filter(id__in=agent_ids, is_active=True))
        # Enforce scope: managers can only act on their business agents
        if not request.user.is_superuser:
            biz = get_active_business(request)
            agents = [a for a in agents if _agent_belongs_to_business(a, biz)]

        results = []
        components = _payslip_components_from_post(request)
        period_start, period_end = _period_from_post(request, year, month)
        for a in agents:
            employee_snapshot = _employee_snapshot_from_post(request, a)
            p = _create_or_update_payslip_and_txn(
                agent=a,
                year=year,
                month=month,
                created_by=request.user,
                send_now=send_now,
                payment_method=method,
                components=components,
                business=get_active_business(request),
                employee_snapshot=employee_snapshot,
                period_start=period_start,
                period_end=period_end,
            )
            if p.status != PayslipStatus.SENT:
                p.status = PayslipStatus.SENT
                p.sent_at = p.sent_at or timezone.now()
                p.save(update_fields=["status", "sent_at"])
            results.append({"agent": a.id, "net": float(p.net), "reference": p.reference, "sent": p.sent_to_email})

        # JSON if requested; otherwise go home
        if _json_requested(request):
            return JsonResponse({"ok": True, "count": len(results), "results": results})
        messages.success(request, f"Issued {len(results)} payslip{'' if len(results) == 1 else 's'}.")
        return redirect("wallet:admin_home")


@method_decorator([otp_required, ensure_csrf_cookie], name="dispatch")
class AdminPayoutSchedulesView(LoginRequiredMixin, TemplateView):
    """
    Minimal view to create/update monthly auto-send schedules.
    You will still need a Celery beat job to call the runner daily/hourly.
    """
    template_name = "wallet/admin_schedules.html"

    def dispatch(self, request, *args, **kwargs):
        if not _staff(request.user):
            return redirect("wallet:agent_wallet")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        U = get_user_model()
        # Superusers see all schedules; managers only those for their business (best effort)
        qs = PayoutSchedule.objects.all().prefetch_related("users")
        if not self.request.user.is_superuser:
            biz = get_active_business(self.request)
            try:
                qs = qs.filter(users__profile__business=biz).distinct()
            except Exception:
                try:
                    qs = qs.filter(users__business=biz).distinct()
                except Exception:
                    qs = qs.none()
        ctx["schedules"] = qs

        agents_qs = U.objects.filter(is_active=True).order_by("first_name", "last_name", "username")
        if not self.request.user.is_superuser:
            biz = get_active_business(self.request)
            try:
                agents_qs = agents_qs.filter(profile__business=biz)
            except Exception:
                try:
                    agents_qs = agents_qs.filter(business=biz)
                except Exception:
                    agents_qs = agents_qs.none()
        ctx["agents"] = agents_qs
        return ctx

    def post(self, request: HttpRequest):
        name = request.POST.get("name") or "Monthly Payouts"
        day = int(request.POST.get("day_of_month", 28))
        hour = int(request.POST.get("at_hour", 9))
        active = request.POST.get("active") in ("1", "true", "on", "yes")
        user_ids = request.POST.getlist("user_ids")

        sch = PayoutSchedule.objects.create(
            name=name,
            day_of_month=day,
            at_hour=hour,
            active=active,
            created_by=request.user,
        )
        if user_ids:
            sch.users.add(*user_ids)

        if _json_requested(request):
            return JsonResponse({"ok": True, "id": sch.id})
        return redirect("wallet:admin_schedules")


@otp_required
def run_payout_schedule(request: HttpRequest, schedule_id: int):
    """
    Manual trigger: issues payslips for all users on the schedule for
    the previous month. Useful for testing before wiring Celery.
    
    SECURITY: PayoutSchedule is a global entity scoped by created_by.
    """
    if not _staff(request.user):
        return redirect("wallet:agent_wallet")

    # SECURITY: Only allow schedules created by users in the same business
    biz = get_active_business(request)
    if request.user.is_superuser and not biz:
        sch = get_object_or_404(PayoutSchedule, id=schedule_id, active=True)
    else:
        # Scope to schedules created by users in this business
        from tenants.models import Membership
        user_ids = Membership.objects.filter(
            business=biz, status="ACTIVE"
        ).values_list("user_id", flat=True)
        sch = get_object_or_404(PayoutSchedule, id=schedule_id, active=True, created_by_id__in=list(user_ids))
    today = timezone.localdate()
    prev_year = today.year if today.month > 1 else (today.year - 1)
    prev_month = today.month - 1 if today.month > 1 else 12

    results = []
    for u in sch.users.all():
        # Managers: skip users outside their business
        if not request.user.is_superuser and not _agent_belongs_to_business(u, get_active_business(request)):
            continue
        p = _create_or_update_payslip_and_txn(
            agent=u,
            year=prev_year,
            month=prev_month,
            created_by=request.user,
            send_now=True,  # schedules send email
        )
        results.append({"agent": u.id, "reference": p.reference, "net": float(p.net)})

    sch.last_run_at = timezone.now()
    sch.save(update_fields=["last_run_at"])

    return JsonResponse({"ok": True, "schedule": sch.id, "count": len(results), "results": results})


# ---------------------------------------------------------------------
# Admin Purchase Orders (simple views) â€” OTP-required
# ---------------------------------------------------------------------
@method_decorator([otp_required, ensure_csrf_cookie], name="dispatch")
class AdminPOListView(LoginRequiredMixin, TemplateView):
    """
    Lists Admin Purchase Orders with simple filters. (Wire in wallet/urls.py)
    """
    template_name = "wallet/admin_pos.html"

    def dispatch(self, request, *args, **kwargs):
        if not _staff(request.user):
            return redirect("wallet:agent_wallet")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        status = self.request.GET.get("status")
        qs = AdminPurchaseOrder.objects.all().order_by("-created_at")
        # (Optional) scope POs if your model has business/store relations
        qs = scope_qs_to_user(qs, self.request)
        if status in (
            PurchaseOrderStatus.DRAFT,
            PurchaseOrderStatus.SENT,
            PurchaseOrderStatus.COMPLETED,
            PurchaseOrderStatus.CANCELLED,
        ):
            qs = qs.filter(status=status)
        ctx["orders"] = qs
        ctx["status"] = status or "all"
        return ctx


@otp_required
def admin_po_new(request: HttpRequest):
    """
    Create a new PO header then redirect to detail page to add items.
    """
    if not _staff(request.user):
        return redirect("wallet:agent_wallet")

    if PurchaseOrderHeaderForm is None:
        return HttpResponseBadRequest("PurchaseOrderHeaderForm not available.")

    if request.method == "POST":
        form = PurchaseOrderHeaderForm(request.POST)
        if form.is_valid():
            po = form.save(commit=False)
            if hasattr(po, "business"):
                po.business = get_active_business(request)
            po.created_by = request.user
            po.status = PurchaseOrderStatus.DRAFT
            po.save()
            return redirect("wallet:admin_po_detail", po_id=po.id)
    else:
        form = PurchaseOrderHeaderForm()

    return render(request, "wallet/admin_po_new.html", {"form": form})


@otp_required
def admin_po_detail(request: HttpRequest, po_id: int):
    """
    View/edit a PO: add items, recompute totals, and move simple statuses.
    
    SECURITY: Scoped by created_by membership to prevent cross-tenant access.
    """
    if not _staff(request.user):
        return redirect("wallet:agent_wallet")

    # SECURITY: Scope to POs created by users in the same business
    biz = get_active_business(request)
    if request.user.is_superuser and not biz:
        po = get_object_or_404(AdminPurchaseOrder, id=po_id)
    else:
        from tenants.models import Membership
        user_ids = Membership.objects.filter(
            business=biz, status="ACTIVE"
        ).values_list("user_id", flat=True)
        po = get_object_or_404(AdminPurchaseOrder, id=po_id, created_by_id__in=list(user_ids))

    ItemForm = PurchaseOrderItemForm  # alias
    if ItemForm is None:
        return HttpResponseBadRequest("PurchaseOrderItemForm not available.")

    if request.method == "POST":
        action = request.POST.get("action") or "add_item"

        if action == "add_item":
            form = ItemForm(request.POST, business=biz)
            if form.is_valid():
                AdminPurchaseOrderItem.objects.create(po=po, **form.to_model_kwargs())
                po.recompute_totals(save=True)
                return redirect("wallet:admin_po_detail", po_id=po.id)
        elif action == "delete_item":
            item_id = request.POST.get("item_id")
            if item_id:
                it = get_object_or_404(AdminPurchaseOrderItem, id=item_id, po=po)
                it.delete()
                po.recompute_totals(save=True)
                return redirect("wallet:admin_po_detail", po_id=po.id)
        elif action == "recompute":
            po.recompute_totals(save=True)
            return redirect("wallet:admin_po_detail", po_id=po.id)
        elif action == "set_status":
            new_status = request.POST.get("status")
            if new_status in PurchaseOrderStatus.values:
                po.status = new_status
                po.save(update_fields=["status"])
            return redirect("wallet:admin_po_detail", po_id=po.id)

    # GET or invalid POST -> render page
    form = ItemForm(business=biz)
    items = po.items.select_related("product").all().order_by("id")
    product_catalog = []
    try:
        for product in form.fields["product"].queryset:
            product_catalog.append(
                {
                    "id": product.id,
                    "code": getattr(product, "code", "") or "",
                    "model": getattr(product, "model", "") or getattr(product, "name", "") or str(product),
                    "cost_price": str(q2(getattr(product, "cost_price", Decimal("0.00")))),
                    "sale_price": str(q2(getattr(product, "sale_price", Decimal("0.00")))),
                }
            )
    except Exception:
        product_catalog = []
    return render(
        request,
        "wallet/admin_po_detail.html",
        {
            "po": po,
            "form": form,
            "items": items,
            "status_choices": PurchaseOrderStatus.choices,
            "product_catalog_json": json.dumps(product_catalog, cls=DjangoJSONEncoder),
        },
    )


@otp_required
def admin_po_pdf(request: HttpRequest, po_id: int):
    if not _staff(request.user):
        return redirect("wallet:agent_wallet")
    biz = get_active_business(request)
    qs = AdminPurchaseOrder.objects.all()
    if biz is not None and hasattr(AdminPurchaseOrder, "business"):
        qs = qs.filter(business=biz)
    elif not request.user.is_superuser:
        from tenants.models import Membership
        user_ids = Membership.objects.filter(business=biz, status="ACTIVE").values_list("user_id", flat=True)
        qs = qs.filter(created_by_id__in=list(user_ids))
    po = get_object_or_404(qs.select_related("created_by", "business"), id=po_id)
    po.recompute_totals(save=True)
    items = list(po.items.select_related("product").all().order_by("id"))

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception:
        return render(request, "wallet/admin_po_pdf.html", {"po": po, "items": items})

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=38, rightMargin=38, topMargin=36, bottomMargin=30)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("POTitle", parent=styles["Heading1"], textColor=colors.HexColor("#065f46"), fontSize=18)
    business_name = getattr(getattr(po, "business", None), "name", None) or getattr(biz, "name", None) or "Emajinet"
    header = [
        Paragraph("Purchase Order", title_style),
        Paragraph(f"{business_name} | PO-{po.id:05d} | {timezone.localtime(po.created_at):%Y-%m-%d}", styles["Normal"]),
        Spacer(1, 12),
        Table(
            [
                ["Supplier", po.supplier_name or "Not specified"],
                ["Contact", " | ".join([v for v in [po.supplier_email, po.supplier_phone] if v]) or "Not specified"],
                ["Expected delivery", po.expected_delivery_date or "Not specified"],
                ["Payment terms", po.payment_terms or "Not specified"],
                ["Prepared by", getattr(po.created_by, "get_username", lambda: "")() if po.created_by_id else ""],
            ],
            colWidths=[140, 360],
            style=[
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1fae5")),
                ("PADDING", (0, 0), (-1, -1), 6),
            ],
        ),
        Spacer(1, 14),
    ]
    rows = [["Item", "Qty", "Unit Cost", "Line Total"]]
    for item in items:
        rows.append([
            str(item.product),
            item.quantity,
            f"{po.currency} {item.unit_price:,.2f}",
            f"{po.currency} {item.line_total:,.2f}",
        ])
    rows.extend([["", "", "Subtotal", f"{po.currency} {po.subtotal:,.2f}"], ["", "", "Tax", f"{po.currency} {po.tax:,.2f}"], ["", "", "Total", f"{po.currency} {po.total:,.2f}"]])
    table = Table(rows, repeatRows=1, colWidths=[230, 55, 100, 115])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#065f46")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -4), [colors.white, colors.HexColor("#f8fafc")]),
        ("FONTNAME", (2, -3), (-1, -1), "Helvetica-Bold"),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    footer = Paragraph("Signature: ____________________________    Date: __________________", styles["Normal"])
    doc.build(header + [table, Spacer(1, 18), Paragraph(po.notes or "", styles["Normal"]), Spacer(1, 18), footer])
    resp = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="purchase-order-{po.id:05d}.pdf"'
    return resp


# ---------------------------------------------------------------------
# ---------------------------------------------------------------------
# Agent Earnings View
# ---------------------------------------------------------------------
@login_required
def agent_earnings(request: HttpRequest) -> HttpResponse:
    """
    GET /wallet/earnings/
    
    Polished "My Earnings" dashboard for agents showing:
    - Yesterday, last 30 days, lifetime earnings
    - Unpaid balance
    - Chart: earnings per day for last 30 days
    - Table: recent transactions
    """
    u = request.user
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    thirty_days_ago = today - timedelta(days=30)
    
    # Build querysets
    qs_all = WalletTransaction.objects.filter(ledger=Ledger.AGENT, agent=u)
    qs_yesterday = qs_all.filter(effective_date=yesterday)
    qs_last_30 = qs_all.filter(effective_date__gte=thirty_days_ago, effective_date__lte=today)
    
    def total(qs):
        return qs.aggregate(s=Sum("amount"))["s"] or Decimal("0")
    
    # Check if commissions are enabled for this business
    commissions_enabled = True
    try:
        from tenants.utils import get_active_business
        biz = get_active_business(request)
        if biz:
            from sales.models import CommissionConfig
            config = CommissionConfig.get_active(biz)
            if config:
                commissions_enabled = config.commissions_enabled
    except Exception:
        pass
    
    # Summary stats
    summary = {
        "yesterday": total(qs_yesterday.filter(amount__gt=0)),
        "yesterday_txns": qs_yesterday.count(),
        "last_30_days": total(qs_last_30.filter(amount__gt=0)),
        "last_30_txns": qs_last_30.filter(amount__gt=0).count(),
        "lifetime": total(qs_all.filter(amount__gt=0)),
        "balance": total(qs_all),  # current wallet balance
        
        # Bonus/Penalty breakdown (last 30 days)
        "bonuses_30d": total(qs_last_30.filter(type=TxnType.BONUS, amount__gt=0)),
        "penalties_30d": -total(qs_last_30.filter(type=TxnType.PENALTY, amount__lt=0)),
        "commissions_30d": total(qs_last_30.filter(type=TxnType.COMMISSION, amount__gt=0)),
    }
    
    # Chart data: daily earnings for last 30 days
    chart_labels = []
    chart_data = []
    for i in range(30, -1, -1):
        day = today - timedelta(days=i)
        chart_labels.append(day.strftime("%b %d"))
        daily_earnings = total(qs_all.filter(effective_date=day, amount__gt=0))
        chart_data.append(float(daily_earnings))
    
    # Recent transactions (all types, last 50)
    txns = qs_all.order_by("-effective_date", "-id")[:50]
    
    import json
    return render(request, "wallet/agent_earnings.html", {
        "summary": summary,
        "chart_labels": json.dumps(chart_labels),
        "chart_data": json.dumps(chart_data),
        "txns": txns,
        "commissions_enabled": commissions_enabled,
    })


# ---------------------------------------------------------------------
# URL-callable views (expose .as_view() for urls.py)
# ---------------------------------------------------------------------
# Agent area
agent_wallet = AgentWalletView.as_view()
agent_txns = AgentTxnListView.as_view()

# Admin area
admin_home = AdminWalletHome.as_view()
admin_agent = AdminAgentWallet.as_view()
admin_issue = AdminIssueTxnView.as_view()
admin_budgets = AdminBudgetsView.as_view()
admin_issue_payslip = AdminIssuePayslipView.as_view()
admin_payslips = AdminPayslipBulkView.as_view()
admin_schedules = AdminPayoutSchedulesView.as_view()
admin_po_list = AdminPOListView.as_view()


# ---------------------------------------------------------------------
# Admin Cost Management
# ---------------------------------------------------------------------
@method_decorator([otp_required, ensure_csrf_cookie], name="dispatch")
class AdminCostListView(LoginRequiredMixin, TemplateView):
    """
    List and manage admin costs (once-off and recurring) for the active business.
    Business and location aware with cost KPI aggregations.
    """
    template_name = "wallet/admin_costs.html"

    def dispatch(self, request, *args, **kwargs):
        if not _staff(request.user):
            messages.error(request, "Access denied.")
            return redirect("wallet:agent_wallet")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        from datetime import timedelta
        ctx = super().get_context_data(**kwargs)
        
        # Get business and location from request
        biz = get_active_business(self.request)
        location = getattr(self.request, "active_location", None)
        
        # Get all cost transactions for this business
        costs_qs = WalletTransaction.objects.filter(
            ledger=Ledger.COMPANY,
            type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING],
        )
        costs_qs = _maybe_scope_to_business(costs_qs, biz)
        
        # Note: WalletTransaction doesn't have location FK, so we only filter by business
        # If location tracking is needed, it can be added to WalletTransaction model in future
        
        # Calculate cost aggregations for KPI cards
        period_days = 30
        period_start = timezone.now() - timedelta(days=period_days)
        
        # Fixed monthly costs (sum of all recurring costs)
        fixed_monthly = costs_qs.filter(is_recurring=True).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0.00")
        # Costs are stored as negative, so take absolute value
        fixed_monthly = abs(fixed_monthly)
        
        # Once-off costs in last 30 days
        once_off_30d = costs_qs.filter(
            is_recurring=False,
            created_at__gte=period_start,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        once_off_30d = abs(once_off_30d)
        
        # Total costs (30 days)
        total_costs_30d = fixed_monthly + once_off_30d
        
        # Separate once-off and recurring for table display
        once_off = costs_qs.filter(is_recurring=False).order_by("-effective_date")
        recurring = costs_qs.filter(is_recurring=True).order_by("-effective_from")
        
        ctx.update({
            "once_off_costs": once_off,
            "recurring_costs": recurring,
            "business": biz,
            "location": location,
            "fixed_monthly": fixed_monthly,
            "once_off_30d": once_off_30d,
            "total_costs_30d": total_costs_30d,
            "period_days": period_days,
        })
        return ctx


@otp_required
def admin_cost_create(request: HttpRequest):
    """
    Create a new cost transaction (once-off or recurring).
    """
    if not _staff(request.user):
        messages.error(request, "Access denied.")
        return redirect("wallet:agent_wallet")
    
    biz = get_active_business(request)
    
    if request.method == "POST":
        from .forms import AdminCostForm
        form = AdminCostForm(request.POST, business=biz)
        if form.is_valid():
            cost = form.save(commit=False)
            cost.created_by = request.user
            if biz:
                cost.business = biz
            cost.save()
            
            cost_type = "recurring" if cost.is_recurring else "once-off"
            messages.success(request, f"{cost_type.title()} cost added successfully.")
            return redirect("wallet:admin_costs")
        else:
            # Return form with errors
            ctx = {"form": form, "business": biz}
            return render(request, "wallet/admin_cost_form.html", ctx)
    else:
        from .forms import AdminCostForm
        form = AdminCostForm(business=biz)
        ctx = {"form": form, "business": biz}
        return render(request, "wallet/admin_cost_form.html", ctx)


@otp_required
def admin_cost_edit(request: HttpRequest, cost_id: int):
    """
    Edit an existing cost transaction.
    
    SECURITY: Scoped to business BEFORE fetch to prevent IDOR.
    """
    if not _staff(request.user):
        messages.error(request, "Access denied.")
        return redirect("wallet:agent_wallet")
    
    biz = get_active_business(request)
    
    # SECURITY: Scope to business BEFORE fetching to prevent IDOR
    if biz:
        cost = get_object_or_404(WalletTransaction, id=cost_id, business=biz)
    else:
        # Superuser without business context
        cost = get_object_or_404(WalletTransaction, id=cost_id)
    
    if request.method == "POST":
        from .forms import AdminCostForm
        # Note: amount needs to be positive in the form
        initial_data = {
            'type': cost.type,
            'amount': abs(cost.amount),  # Convert negative to positive for editing
            'note': cost.note,
            'effective_date': cost.effective_date,
            'is_recurring': cost.is_recurring,
            'recurrence': cost.recurrence,
            'effective_from': cost.effective_from,
        }
        form = AdminCostForm(request.POST, instance=cost, business=biz)
        if form.is_valid():
            updated_cost = form.save(commit=False)
            updated_cost.created_by = request.user  # Track who last modified
            updated_cost.save()
            
            messages.success(request, "Cost updated successfully.")
            return redirect("wallet:admin_costs")
        else:
            ctx = {"form": form, "cost": cost, "business": biz}
            return render(request, "wallet/admin_cost_form.html", ctx)
    else:
        from .forms import AdminCostForm
        # Pre-populate form with existing data (convert amount to positive)
        initial_data = {
            'type': cost.type,
            'amount': abs(cost.amount),
            'note': cost.note,
            'effective_date': cost.effective_date,
            'is_recurring': cost.is_recurring,
            'recurrence': cost.recurrence,
            'effective_from': cost.effective_from,
        }
        form = AdminCostForm(instance=cost, initial=initial_data, business=biz)
        ctx = {"form": form, "cost": cost, "business": biz, "editing": True}
        return render(request, "wallet/admin_cost_form.html", ctx)


@otp_required
@require_POST
def admin_cost_delete(request: HttpRequest, cost_id: int):
    """
    Delete a cost transaction.
    
    SECURITY: Scoped to business BEFORE fetch to prevent IDOR.
    """
    if not _staff(request.user):
        messages.error(request, "Access denied.")
        return redirect("wallet:agent_wallet")
    
    biz = get_active_business(request)
    
    # SECURITY: Scope to business BEFORE fetching to prevent IDOR
    if biz:
        cost = get_object_or_404(WalletTransaction, id=cost_id, business=biz)
    else:
        # Superuser without business context
        cost = get_object_or_404(WalletTransaction, id=cost_id)
    
    # Only allow deletion of cost transactions
    if cost.type not in [TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING]:
        messages.error(request, "You can only delete cost transactions.")
        return redirect("wallet:admin_costs")
    
    cost.delete()
    messages.success(request, "Cost deleted successfully.")
    return redirect("wallet:admin_costs")


# ---------------------------------------------------------------------
# Agent Wallet Adjustment (Manual)
# ---------------------------------------------------------------------
@otp_required
def wallet_adjust_agent(request: HttpRequest, membership_id: int):
    """
    Admin/manager view to manually adjust an agent's wallet balance.
    
    Can add money (credit) or deduct money (debit) with a required reason.
    All adjustments are logged for audit trail.
    """
    if not _staff(request.user):
        messages.error(request, "Access denied. Only managers/admins can adjust agent wallets.")
        return redirect("dashboard:agent_dashboard")
    
    # SECURITY: Scope membership to business BEFORE fetching to prevent IDOR
    biz = get_active_business(request)
    
    try:
        from tenants.models import Membership
        if request.user.is_superuser and not biz:
            # Superuser without business context can access any
            membership = get_object_or_404(Membership, pk=membership_id)
        elif biz:
            # Scope to this business
            membership = get_object_or_404(Membership, pk=membership_id, business=biz)
        else:
            raise Http404("Membership not found")
    except ImportError:
        messages.error(request, "Tenants app not available.")
        return redirect("dashboard:admin_dashboard")
    
    # Get agent's current wallet
    from wallet.agent_models import get_or_create_agent_wallet
    wallet = get_or_create_agent_wallet(membership)
    
    if request.method == "POST":
        from .forms import AgentWalletAdjustmentForm
        form = AgentWalletAdjustmentForm(request.POST)
        
        if form.is_valid():
            amount = form.cleaned_data['amount']
            is_deduction = form.cleaned_data['is_deduction']
            reason = form.cleaned_data['reason']
            
            try:
                from wallet.agent_models import add_manual_adjustment
                
                # Perform the adjustment
                txn = add_manual_adjustment(
                    membership=membership,
                    amount=amount,
                    is_debit=is_deduction,
                    reason=reason,
                    created_by=request.user,
                )
                
                action = "deducted from" if is_deduction else "added to"
                messages.success(
                    request,
                    f"Successfully {action} {membership.user.get_username()}'s wallet: "
                    f"MK {amount:,.2f}. New balance: MK {wallet.balance:,.2f}"
                )
                
                # Redirect to agent detail or back to list
                try:
                    from django.urls import reverse
                    return redirect(reverse('dashboard:admin_agent_detail', args=[membership.user.id]))
                except Exception:
                    return redirect("dashboard:admin_dashboard")
                    
            except Exception as e:
                messages.error(request, f"Error processing adjustment: {e}")
                ctx = {
                    "form": form,
                    "membership": membership,
                    "wallet": wallet,
                    "business": biz,
                }
                return render(request, "wallet/agent_adjustment_form.html", ctx)
        else:
            # Form has errors, re-render with errors
            ctx = {
                "form": form,
                "membership": membership,
                "wallet": wallet,
                "business": biz,
            }
            return render(request, "wallet/agent_adjustment_form.html", ctx)
    else:
        # GET request - show form
        from .forms import AgentWalletAdjustmentForm
        form = AgentWalletAdjustmentForm(initial={'membership': membership_id})
        
        ctx = {
            "form": form,
            "membership": membership,
            "wallet": wallet,
            "business": biz,
        }
        return render(request, "wallet/agent_adjustment_form.html", ctx)


# View aliases for urls.py
admin_costs = AdminCostListView.as_view()



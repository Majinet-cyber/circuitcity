# circuitcity/hq/views_subscriptions.py
from __future__ import annotations

import json
from datetime import datetime as dt, timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Q, Sum, Value, DecimalField
from django.db.models.functions import TruncMonth, Coalesce
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import select_template
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from hq.permissions import hq_admin_required
from tenants.models import Business
from billing.models import Subscription, Invoice

# Optional Plan model
try:
    from billing.models import Plan  # type: ignore
except Exception:  # pragma: no cover
    Plan = None  # type: ignore

# ---- Import helpers & catalog from hq.views to keep a single source of truth ----
from .views import (
    PLAN_CATALOG,
    _field,
    _range_filter,
    _date_range_from_request,
    _render_safe,
    _plan_info_from_subscription,
    _back_to,
)

# ---------------------------
# Small local helpers
# ---------------------------
def _json_body(request):
    try:
        return json.loads(request.body.decode("utf-8"))
    except Exception:
        return {}


# ============================================================
# Subscriptions list
# ============================================================
@hq_admin_required
def subscriptions(request):
    """
    HQ Subscriptions table with search, status filter, and range filter.
    Renders hq/subscriptions.html if present, else billing/hq_subscriptions.html.
    """
    start, end, rng = _date_range_from_request(request)
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()

    qs = Subscription.objects.select_related("business", "plan")

    if q:
        qs = qs.filter(
            Q(business__name__icontains=q)
            | Q(business__slug__icontains=q)
            | Q(plan__name__icontains=q)
            | Q(plan__code__icontains=q)
        )
    if status:
        qs = qs.filter(status__iexact=status)

    if start and end and _field(Subscription, "created_at"):
        qs = _range_filter(qs, Subscription, "created_at", start, end)

    order_field = "-created_at" if _field(Subscription, "created_at") else "-id"
    qs = qs.order_by(order_field)

    page = Paginator(qs, 25).get_page(request.GET.get("page") or 1)

    ctx = {
        "subscriptions": page,
        "subscriptions_qs": qs,
        "subs": page,
        "rows": page.object_list,
        "object_list": page.object_list,
        "items": page.object_list,
        "page_obj": page,
        "count": qs.count(),
        "total": qs.count(),
        "q": q,
        "status": status,
        "range": rng,
        "start": start,
        "end": end,
        "plan_catalog": PLAN_CATALOG,
    }

    tpl = select_template(["hq/subscriptions.html", "billing/hq_subscriptions.html"])
    return HttpResponse(tpl.render(ctx, request))


# ============================================================
# Subscription actions (GET = redirect w/ flash, POST = JSON)
# ============================================================
@hq_admin_required
@require_http_methods(["GET", "POST"])
def sub_adjust_trial(request, pk: int):
    """
    Adjust trial by ?days=Â±N or set ?trial_end=YYYY-MM-DD.
    GET -> perform + redirect back with flash
    POST -> JSON
    """
    sub = get_object_or_404(Subscription, pk=pk)
    data = _json_body(request) if request.method == "POST" else request.GET

    # Guard if any paid invoices exist for the business
    if Invoice.objects.filter(business=sub.business, status__in=["PAID", "SETTLED", "paid"]).exists():
        if request.method == "GET":
            messages.error(request, "Cannot adjust: subscription is locked by payment activity.")
            return _back_to(request)
        return JsonResponse({"ok": False, "error": "locked_by_payment"}, status=409)

    # +/- days
    days = data.get("days")
    try:
        days = int(days) if days is not None else None
    except Exception:
        days = None

    if isinstance(days, int) and days != 0:
        if hasattr(sub, "extend_trial"):
            sub.extend_trial(days, save=True)
        else:
            if not getattr(sub, "trial_end", None):
                if request.method == "GET":
                    messages.error(request, "No trial_end field on subscription.")
                    return _back_to(request)
                return JsonResponse({"ok": False, "error": "no_trial_field"}, status=409)
            sub.trial_end = (sub.trial_end or timezone.now()) + timedelta(days=days)
            if _field(Subscription, "current_period_end"):
                sub.current_period_end = sub.trial_end
            sub.save(update_fields=[f for f in ["trial_end", "current_period_end"] if _field(Subscription, f)])
        if request.method == "GET":
            messages.success(request, f"Trial adjusted by {days} day(s).")
            return _back_to(request)
        return JsonResponse({"ok": True, "trial_end": sub.trial_end.isoformat()})

    # Set to specific date
    new_date = data.get("trial_end")
    if new_date:
        try:
            d = dt.strptime(new_date, "%Y-%m-%d").date()
            new_dt = timezone.make_aware(dt(d.year, d.month, d.day, 23, 59, 59))
            sub.trial_end = new_dt
            if _field(Subscription, "current_period_end"):
                sub.current_period_end = new_dt
            sub.save(update_fields=[f for f in ["trial_end", "current_period_end"] if _field(Subscription, f)])
            if request.method == "GET":
                messages.success(request, f"Trial end set to {d.isoformat()}.")
                return _back_to(request)
            return JsonResponse({"ok": True, "trial_end": sub.trial_end.isoformat()})
        except Exception:
            if request.method == "GET":
                messages.error(request, "Invalid date format. Use YYYY-MM-DD.")
                return _back_to(request)
            return JsonResponse({"ok": False, "error": "bad_date"}, status=400)

    if request.method == "GET":
        messages.info(request, "No trial change requested.")
        return _back_to(request)
    return JsonResponse({"ok": False, "error": "no_action"}, status=400)


@hq_admin_required
@require_http_methods(["GET", "POST"])
def sub_cancel(request, pk: int):
    sub = get_object_or_404(Subscription, pk=pk)
    try:
        if _field(Subscription, "cancel_at_period_end"):
            sub.cancel_at_period_end = True
            sub.save(update_fields=["cancel_at_period_end"])
        else:
            sub.status = "CANCELED"
            sub.save(update_fields=["status"])
        if request.method == "GET":
            messages.success(request, "Subscription will cancel at period end.")
            return _back_to(request)
        return JsonResponse({"ok": True})
    except Exception:
        if request.method == "GET":
            messages.error(request, "Could not cancel subscription.")
            return _back_to(request)
        return JsonResponse({"ok": False}, status=400)


@hq_admin_required
@require_http_methods(["GET", "POST"])
def sub_extend(request, pk: int):
    """
    Extend trial to a specific date (?trial_end=YYYY-MM-DD) OR by ?days=Â±N.
    """
    sub = get_object_or_404(Subscription, pk=pk)
    data = _json_body(request) if request.method == "POST" else request.GET

    if Invoice.objects.filter(business=sub.business, status__in=["PAID", "SETTLED", "paid"]).exists():
        if request.method == "GET":
            messages.error(request, "Cannot extend: subscription is locked by payment activity.")
            return _back_to(request)
        return JsonResponse({"ok": False, "error": "locked_by_payment"}, status=409)

    # Exact date wins if provided
    if data.get("trial_end"):
        try:
            d = dt.strptime(data["trial_end"], "%Y-%m-%d").date()
            new_dt = timezone.make_aware(dt(d.year, d.month, d.day, 23, 59, 59))
            sub.trial_end = new_dt
            if hasattr(sub, "Status"):
                sub.status = sub.Status.TRIAL  # enum style
            else:
                sub.status = "trial"
            if _field(Subscription, "current_period_end"):
                sub.current_period_end = new_dt
            if _field(Subscription, "next_billing_date"):
                sub.next_billing_date = new_dt
            sub.save(update_fields=[f for f in ["trial_end", "status", "current_period_end", "next_billing_date", "updated_at"] if _field(Subscription, f)])
            if request.method == "GET":
                messages.success(request, f"Trial extended to {d.isoformat()}.")
                return _back_to(request)
            return JsonResponse({"ok": True, "trial_end": sub.trial_end.isoformat()})
        except Exception:
            if request.method == "GET":
                messages.error(request, "Invalid date format. Use YYYY-MM-DD.")
                return _back_to(request)
            return JsonResponse({"ok": False, "error": "bad_date"}, status=400)

    # days fallback
    days = data.get("days")
    try:
        days = int(days) if days is not None else None
    except Exception:
        days = None

    if isinstance(days, int) and days != 0:
        if hasattr(sub, "extend_trial"):
            sub.extend_trial(days, save=True)
        else:
            sub.trial_end = (sub.trial_end or timezone.now()) + timedelta(days=days)
            if _field(Subscription, "current_period_end"):
                sub.current_period_end = sub.trial_end
            sub.status = "trial"
            sub.save(update_fields=[f for f in ["trial_end", "current_period_end", "status"] if _field(Subscription, f)])
        if request.method == "GET":
            messages.success(request, f"Trial adjusted by {days} day(s).")
            return _back_to(request)
        return JsonResponse({"ok": True, "trial_end": sub.trial_end.isoformat()})

    if request.method == "GET":
        messages.info(request, "No change requested.")
        return _back_to(request)
    return JsonResponse({"ok": False}, status=400)


@hq_admin_required
@require_http_methods(["GET", "POST"])
def sub_revoke_trial(request, pk: int):
    sub = get_object_or_404(Subscription, pk=pk)
    try:
        if hasattr(sub, "end_trial_now"):
            sub.end_trial_now(to_grace=True, save=True)
        else:
            sub.trial_end = timezone.now()
            if hasattr(sub, "enter_grace"):
                sub.enter_grace(save=True)
            else:
                sub.status = "canceled"
                sub.save(update_fields=["trial_end", "status", "updated_at"])
        if request.method == "GET":
            messages.success(request, "Trial revoked.")
            return _back_to(request)
        return JsonResponse({"ok": True})
    except Exception:
        if request.method == "GET":
            messages.error(request, "Could not revoke trial.")
            return _back_to(request)
        return JsonResponse({"ok": False}, status=400)


@hq_admin_required
@require_http_methods(["GET", "POST"])
def sub_activate_now(request, pk: int):
    sub = get_object_or_404(Subscription, pk=pk)
    try:
        # Your model likely defines activate_now(period_days=...)
        sub.activate_now(period_days=30)
        if request.method == "GET":
            messages.success(request, "Subscription activated.")
            return _back_to(request)
        return JsonResponse({"ok": True})
    except Exception:
        if request.method == "GET":
            messages.error(request, "Could not activate subscription.")
            return _back_to(request)
        return JsonResponse({"ok": False}, status=400)


@hq_admin_required
@require_http_methods(["GET", "POST"])
def sub_set_plan(request, pk: int):
    """
    Change the plan to ?plan_code=starter|pro|promax (GET) or {"plan_code": "..."} (POST).
    """
    sub = get_object_or_404(Subscription, pk=pk)
    data = _json_body(request) if request.method == "POST" else request.GET
    code = (data.get("plan_code") or "").lower().strip()
    if code not in PLAN_CATALOG:
        if request.method == "GET":
            messages.error(request, "Unknown plan.")
            return _back_to(request)
        return JsonResponse({"ok": False, "error": "unknown_plan"}, status=400)

    catalog = PLAN_CATALOG[code]
    try:
        # If a Plan model exists, attach or create the plan
        if _field(Subscription, "plan") and Plan:
            kwargs = {}
            if _field(Plan, "code"):
                kwargs["code"] = catalog["code"]
            if _field(Plan, "name"):
                kwargs["name"] = catalog["name"]
            if _field(Plan, "amount"):
                kwargs["amount"] = catalog["amount"]
            if _field(Plan, "interval"):
                kwargs["interval"] = "month"

            plan_obj = (
                Plan.objects.filter(
                    Q(code=kwargs.get("code", None)) | Q(name__iexact=catalog["name"])
                ).order_by("-id").first()
            )
            if not plan_obj:
                plan_obj = Plan.objects.create(**kwargs)

            sub.plan = plan_obj
            update_fields = ["plan"]
            if _field(Subscription, "plan_code"):
                sub.plan_code = catalog["code"]; update_fields.append("plan_code")
            if _field(Subscription, "amount"):
                sub.amount = catalog["amount"]; update_fields.append("amount")
            if _field(Subscription, "updated_at"):
                update_fields.append("updated_at")
            sub.save(update_fields=update_fields)
        else:
            # No Plan model: store amount and optional plan_code directly on subscription
            update_fields = []
            if _field(Subscription, "amount"):
                sub.amount = catalog["amount"]; update_fields.append("amount")
            if _field(Subscription, "plan_code"):
                sub.plan_code = catalog["code"]; update_fields.append("plan_code")
            if _field(Subscription, "updated_at"):
                update_fields.append("updated_at")
            sub.save(update_fields=update_fields)

        if request.method == "GET":
            messages.success(request, f"Plan set to {catalog['name']}.")
            return _back_to(request)
        return JsonResponse({"ok": True, "plan": catalog["name"], "amount": str(catalog["amount"])})
    except Exception:
        if request.method == "GET":
            messages.error(request, "Could not change plan.")
            return _back_to(request)
        return JsonResponse({"ok": False}, status=400)



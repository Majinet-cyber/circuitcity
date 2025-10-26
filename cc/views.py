# cc/views.py
from __future__ import annotations
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, Any

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import connection
from django.db.models import Sum
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_protect

from inventory.models import InventoryItem, TimeLog, WalletTxn
from sales.models import Sale

User = get_user_model()

# Compensation knobs
BASE_SALARY = Decimal("40000")          # MK40,000
EARLY_BIRD_BONUS = Decimal("5000")      # before 08:00
LATE_STEP_PENALTY = Decimal("5000")     # every 30 min after 08:00
SUNDAY_BONUS = Decimal("15000")         # any time on Sunday


# ==============================================================================
# Single Source of Truth: error rendering helper
# ==============================================================================
def _render_error(request: HttpRequest, template: str, status: int, context: Dict[str, Any] | None = None) -> HttpResponse:
    """
    Centralized renderer for error pages so all errors:
      - Share the same template look/feel
      - Automatically include request_id if middleware set it
      - Are easy to call from multiple handlers/views
    """
    ctx = dict(context or {})
    # Expose request_id for the template (set by your RequestIDMiddleware)
    ctx.setdefault("request_id", getattr(request, "request_id", None))
    return render(request, template, ctx, status=status)


# ==============================================================================
# Health & utility
# ==============================================================================
def healthz(_request: HttpRequest) -> JsonResponse:
    """
    Lightweight liveness/readiness probe:
      - Confirms DB connectivity with a simple SELECT 1
    Returns 200 if OK, else 500.
    """
    db_ok = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        db_ok = False

    status = 200 if db_ok else 500
    return JsonResponse({"ok": db_ok}, status=status)


def temporary_ok(_request: HttpRequest) -> HttpResponse:
    """Tiny page to verify URLConf & server are wired correctly."""
    return HttpResponse(
        "<h3 style='margin:1rem;padding:.75rem;border-radius:8px;"
        "background:#e7f7ec;border:1px solid #b7e5c4'>"
        "It works! URLConf and server are OK.</h3>"
        "<p style='margin:1rem;color:#334155'>If your normal pages still 500, "
        "the error is in a specific view/template path.</p>",
        content_type="text/html",
    )


def user_in_group(user: User, group_name: str) -> bool:
    return user.is_authenticated and user.groups.filter(name=group_name).exists()


def is_admin(user: User) -> bool:
    return user.is_staff or user_in_group(user, "Admin")


@login_required
@ensure_csrf_cookie  # ensure csrftoken cookie is set on first GET
def home(request: HttpRequest) -> HttpResponse:
    """
    Route users to the correct dashboard using the NEW (namespaced) routes.
    Staff/Admin  -> dashboard:dashboard
    Manager      -> manager_dashboard
    Agent        -> dashboard:agent_dashboard
    """
    u = request.user
    if is_admin(u):
        return redirect("dashboard:dashboard")
    if user_in_group(u, "Manager"):
        return redirect("manager_dashboard")
    return redirect("dashboard:agent_dashboard")


@require_http_methods(["GET", "POST"])
def logout_now(request: HttpRequest) -> HttpResponse:
    """
    Log the user out on GET or POST and redirect to login.
    Accepting GET avoids 405 errors when using a simple <a href="...">Logout</a>.
    """
    if request.user.is_authenticated:
        logout(request)
    next_target = getattr(settings, "LOGOUT_REDIRECT_URL", "accounts:login") or "accounts:login"
    # redirect() accepts a URL pattern name, so passing "accounts:login" is fine.
    return redirect(next_target)


# Back-compat alias (if any code imports logout_view)
logout_view = logout_now


def _totals_for_user(user: User, scope: str = "all") -> Dict[str, Any]:
    if is_admin(user) or scope == "all":
        items = InventoryItem.objects.all()
        sales = Sale.objects.all()
    elif user_in_group(user, "Manager"):
        items = InventoryItem.objects.all()
        sales = Sale.objects.all()
    else:
        items = InventoryItem.objects.filter(assigned_agent=user)
        sales = Sale.objects.filter(agent=user)

    # Decimal-safe aggregation
    sales_value = sales.aggregate(total=Sum("price"))["total"] or Decimal("0")
    commission_total = sum((s.commission_amount for s in sales), Decimal("0"))

    return {
        "in_stock": items.filter(status="IN_STOCK").count(),
        "sold": items.filter(status="SOLD").count(),
        "sales_value": sales_value,
        "commission_total": commission_total,
    }


# ==============================================================================
# Back-compat alias for old name
# ==============================================================================
@login_required
@user_passes_test(is_admin)
def admin_dashboard(_request: HttpRequest) -> HttpResponse:
    """Old route name â†’ redirect to the new namespaced admin dashboard."""
    return redirect("dashboard:dashboard")


# ==============================================================================
# Admin â†’ per-agent detail + record advance
# ==============================================================================
@login_required
@user_passes_test(is_admin)
@ensure_csrf_cookie         # set cookie on GET
@csrf_protect               # enforce token on POST
def admin_agent_detail(request: HttpRequest, user_id: int) -> HttpResponse:
    agent = get_object_or_404(User, pk=user_id)

    now = timezone.localtime()
    today = now.date()
    month_start = today.replace(day=1)

    # Record advance/adjustment
    if request.method == "POST":
        raw_amount = (request.POST.get("amount", "0") or "0").replace(",", "").strip()
        try:
            amount = Decimal(raw_amount)
        except Exception:
            amount = Decimal("0")
        memo = (request.POST.get("memo", "") or "").strip()

        if amount != 0:
            WalletTxn.objects.create(
                user=agent,
                amount=-abs(amount),  # advance = deduction
                reason="ADVANCE",
                memo=memo or "Advance payment",
            )
            messages.success(request, f"Advance of MK{amount:,} recorded for {agent.get_username()}.")
        else:
            messages.error(request, "Enter a non-zero amount.")
        return redirect("admin_agent_detail", user_id=agent.id)

    # Stats
    in_stock = InventoryItem.objects.filter(assigned_agent=agent, status="IN_STOCK").count()
    total_sales = Sale.objects.filter(agent=agent).count()

    sales_all = Sale.objects.filter(agent=agent)
    sales_month = sales_all.filter(sold_at__gte=month_start)

    month_commission = sum((s.commission_amount for s in sales_month), Decimal("0"))
    lifetime_commission = sum((s.commission_amount for s in sales_all), Decimal("0"))

    month_txn_total = WalletTxn.objects.filter(
        user=agent, created_at__date__gte=month_start
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    lifetime_txn_total = WalletTxn.objects.filter(user=agent).aggregate(
        t=Sum("amount")
    )["t"] or Decimal("0")

    month_deductions = WalletTxn.objects.filter(
        user=agent, created_at__date__gte=month_start, amount__lt=0
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")

    total_monthly_earnings = BASE_SALARY + month_commission + month_txn_total
    lifetime_earnings = lifetime_commission + lifetime_txn_total

    ctx = {
        "agent": agent,
        "date_joined": agent.date_joined,
        "in_stock": in_stock,
        "total_sales": total_sales,
        "month_commission": month_commission,
        "month_txn_total": month_txn_total,
        "month_deductions": month_deductions,
        "total_monthly_earnings": total_monthly_earnings,
        "lifetime_earnings": lifetime_earnings,
        "last_logs": TimeLog.objects.filter(user=agent).order_by("-logged_at")[:10],
        "wallet_txns": WalletTxn.objects.filter(user=agent).order_by("-created_at")[:20],
        "BASE_SALARY": BASE_SALARY,
        "today": today,
    }
    return render(request, "dash/admin_agent_detail.html", ctx)


# ==============================================================================
# Manager dashboard (placeholder)
# ==============================================================================
@login_required
@ensure_csrf_cookie
def manager_dashboard(request: HttpRequest) -> HttpResponse:
    ctx = _totals_for_user(request.user)
    return render(request, "dash/manager_dashboard.html", ctx)


# ==============================================================================
# Agent dashboard (enhanced)
# ==============================================================================
@login_required
@ensure_csrf_cookie  # set csrftoken cookie for JS/phone before any POST
@csrf_protect        # enforce token on POST
def agent_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Agent dashboard:
      - Time logging (POST)
      - Wallet view (base salary + monthly earnings/deductions + lifetime)
      - Agent battery (max 20)
    """
    user = request.user
    now = timezone.localtime()
    today = now.date()
    month_start = today.replace(day=1)

    # --- Handle time log POST ---
    if request.method == "POST" and request.POST.get("action") == "log_time":
        when = now
        raw_dt = request.POST.get("logged_at")  # "YYYY-MM-DDTHH:MM"
        if raw_dt:
            try:
                naive = datetime.fromisoformat(raw_dt)  # local naive
                when = timezone.make_aware(naive, timezone.get_current_timezone())
            except Exception:
                when = now

        TimeLog.objects.create(user=user, logged_at=when, note=request.POST.get("note", "")[:200])

        # Rewards/penalties using LOCAL time
        local_when = timezone.localtime(when)

        if local_when.weekday() == 6:  # Sunday
            WalletTxn.objects.create(
                user=user,
                amount=SUNDAY_BONUS,
                reason="SUNDAY_BONUS",
                memo="Sunday work bonus",
            )
            messages.success(request, "ðŸŽ‰ Sunday bonus MK15,000 added to your wallet!")
        else:
            eight_am = local_when.replace(hour=8, minute=0, second=0, microsecond=0)
            if local_when <= eight_am:
                WalletTxn.objects.create(
                    user=user,
                    amount=EARLY_BIRD_BONUS,
                    reason="EARLY_BIRD",
                    memo="Early-bird before 8am",
                )
                messages.success(request, "ðŸ˜Š Early-bird bonus MK5,000 added to your wallet!")
            else:
                secs_after = (local_when - eight_am).total_seconds()
                blocks = int((secs_after + 1799) // 1800)  # 30-min blocks, rounded up
                penalty = LATE_STEP_PENALTY * blocks
                if penalty > 0:
                    WalletTxn.objects.create(
                        user=user,
                        amount=-penalty,
                        reason="LATE_PENALTY",
                        memo=f"Late by ~{blocks*30} minutes",
                    )
                    messages.error(request, f"ðŸ˜¢ Late penalty âˆ’MK{penalty:,} applied.")

        # Stay on this (cc) agent dashboard
        return redirect("agent_dashboard")

    # --- Stock for battery (agent-specific rules; max=20) ---
    agent_in_stock = InventoryItem.objects.filter(
        assigned_agent=user, status="IN_STOCK"
    ).count()
    battery_max = 20
    battery_pct = min(100, int(round((agent_in_stock / battery_max) * 100))) if agent_in_stock > 0 else 0
    if agent_in_stock < 10:
        battery_color = "red"
        battery_label = "Critical"
    elif agent_in_stock < 12:
        battery_color = "yellow"
        battery_label = "Low"
    else:
        battery_color = "green"
        battery_label = "Stable"

    # --- Wallet & earnings ---
    my_sales_all = Sale.objects.filter(agent=user)
    my_sales_month = my_sales_all.filter(sold_at__gte=month_start)

    month_commission = sum((s.commission_amount for s in my_sales_month), Decimal("0"))
    lifetime_commission = sum((s.commission_amount for s in my_sales_all), Decimal("0"))

    month_txn_total = WalletTxn.objects.filter(
        user=user, created_at__date__gte=month_start
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    lifetime_txn_total = WalletTxn.objects.filter(user=user).aggregate(
        t=Sum("amount")
    )["t"] or Decimal("0")

    month_deductions = WalletTxn.objects.filter(
        user=user, created_at__date__gte=month_start, amount__lt=0
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")

    total_monthly_earnings = BASE_SALARY + month_commission + month_txn_total
    lifetime_earnings = lifetime_commission + lifetime_txn_total

    # --- Quick headline tiles (reuse helper) ---
    tiles = _totals_for_user(user)

    ctx = {
        **tiles,
        "today": today,
        "now": now,
        # Battery
        "battery_count": agent_in_stock,
        "battery_pct": battery_pct,
        "battery_color": battery_color,
        "battery_label": battery_label,
        "battery_max": battery_max,
        # Wallet
        "base_salary": BASE_SALARY,
        "month_commission": month_commission,
        "month_txn_total": month_txn_total,
        "month_deductions": month_deductions,  # negative number
        "total_monthly_earnings": total_monthly_earnings,
        "lifetime_earnings": lifetime_earnings,
        # Time logs (last few)
        "last_logs": TimeLog.objects.filter(user=user).order_by("-logged_at")[:5],
    }
    return render(request, "dash/agent_dashboard.html", ctx)


# ==============================================================================
# API: lightweight AI recommendations for dashboard
# ==============================================================================
@login_required
@require_GET
def api_recommendations(request: HttpRequest) -> JsonResponse:
    """
    Small, safe recommendations endpoint for local/dev.
    Returns: {"success": true, "items": [...]}

    - Suggest restock if agent has < 10 IN_STOCK items.
    - Flag no recent sales (last 14 days).
    """
    user = request.user
    now = timezone.localtime()

    items: list[dict[str, Any]] = []

    # Stock-based nudge
    in_stock = InventoryItem.objects.filter(assigned_agent=user, status="IN_STOCK").count()
    if in_stock < 10:
        items.append({
            "type": "restock",
            "message": f"Low stock: only {in_stock} items available. Consider restocking to at least 12.",
            "confidence": 0.82,
        })

    # Recent sales nudge
    recent_sales = Sale.objects.filter(agent=user, sold_at__gte=now - timedelta(days=14)).count()
    if recent_sales == 0:
        items.append({
            "type": "marketing",
            "message": "No sales in the last 14 days. Try a small discount or a WhatsApp broadcast.",
            "confidence": 0.61,
        })

    return JsonResponse({"success": True, "items": items})


# ==============================================================================
# Friendly error views (used by handler404/handler500 and for 501 fallback)
# ==============================================================================
def page_not_found(request: HttpRequest, exception, *args, **kwargs) -> HttpResponse:
    """
    Global 404 renderer. Django calls this when DEBUG=False and a route isn't found.
    """
    return _render_error(
        request,
        template="errors/404.html",
        status=404,
        context={"path": request.get_full_path()},
    )


def server_error(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    """
    Global 500 renderer. Django calls this when DEBUG=False, or our FriendlyErrorsMiddleware
    decides to render a user-safe page.
    """
    return _render_error(request, template="errors/500.html", status=500)


def feature_unavailable(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    """
    Show a clean 501 'Under Development' page for endpoints we want to expose safely
    before the real implementation lands.
    """
    return _render_error(request, template="errors/501.html", status=501)






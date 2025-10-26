# cc/views.py
from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from typing import Dict, Any

from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import connection
from django.db.models import Sum
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone

from inventory.models import InventoryItem, TimeLog, WalletTxn
from sales.models import Sale

User = get_user_model()

BASE_SALARY = Decimal("40000")          # MK40,000
EARLY_BIRD_BONUS = Decimal("5000")      # before 08:00
LATE_STEP_PENALTY = Decimal("5000")     # every 30 min after 08:00
SUNDAY_BONUS = Decimal("15000")         # any time on Sunday


# -------------------------
# Health & utility
# -------------------------
def healthz(request: HttpRequest) -> JsonResponse:
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


def user_in_group(user: User, group_name: str) -> bool:
    return user.is_authenticated and user.groups.filter(name=group_name).exists()


def is_admin(user: User) -> bool:
    return user.is_staff or user_in_group(user, "Admin")


@login_required
def home(request: HttpRequest) -> HttpResponse:
    """
    Route users to the correct dashboard using the NEW (namespaced) routes.
    Staff/Admin  -> dashboard:dashboard
    Manager      -> manager_dashboard (legacy view in cc)
    Agent        -> dashboard:agent_dashboard
    """
    u = request.user
    if is_admin(u):
        return redirect("dashboard:dashboard")
    if user_in_group(u, "Manager"):
        return redirect("manager_dashboard")
    return redirect("dashboard:agent_dashboard")


def logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect("login")


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

    # Use Decimal-safe aggregation
    sales_value = sales.aggregate(total=Sum("price"))["total"] or Decimal("0")
    commission_total = sum((s.commission_amount for s in sales), Decimal("0"))

    return {
        "in_stock": items.filter(status="IN_STOCK").count(),
        "sold": items.filter(status="SOLD").count(),
        "sales_value": sales_value,
        "commission_total": commission_total,
    }


# -------------------------
# Back-compat alias for old name
# -------------------------
@login_required
@user_passes_test(is_admin)
def admin_dashboard(request: HttpRequest) -> HttpResponse:
    """Old route name â†’ redirect to the new namespaced admin dashboard."""
    return redirect("dashboard:dashboard")


# -------------------------
# Admin â†’ per-agent detail + record advance
# -------------------------
@login_required
@user_passes_test(is_admin)
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


# -------------------------
# Manager dashboard (placeholder)
# -------------------------
@login_required
def manager_dashboard(request: HttpRequest) -> HttpResponse:
    ctx = _totals_for_user(request.user)
    return render(request, "dash/manager_dashboard.html", ctx)


# -------------------------
# Agent dashboard (enhanced)
# -------------------------
@login_required
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
            WalletTxn.objects.create(user=user, amount=SUNDAY_BONUS, reason="SUNDAY_BONUS",
                                     memo="Sunday work bonus")
            messages.success(request, "ðŸŽ‰ Sunday bonus MK15,000 added to your wallet!")
        else:
            eight_am = local_when.replace(hour=8, minute=0, second=0, microsecond=0)
            if local_when <= eight_am:
                WalletTxn.objects.create(user=user, amount=EARLY_BIRD_BONUS, reason="EARLY_BIRD",
                                         memo="Early-bird before 8am")
                messages.success(request, "ðŸ˜Š Early-bird bonus MK5,000 added to your wallet!")
            else:
                secs_after = (local_when - eight_am).total_seconds()
                blocks = int((secs_after + 1799) // 1800)  # 30-min blocks, rounded up
                penalty = LATE_STEP_PENALTY * blocks
                if penalty > 0:
                    WalletTxn.objects.create(user=user, amount=-penalty, reason="LATE_PENALTY",
                                             memo=f"Late by ~{blocks*30} minutes")
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

    month_txn_total = WalletTxn.objects.filter(user=user, created_at__date__gte=month_start).aggregate(
        t=Sum("amount")
    )["t"] or Decimal("0")
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





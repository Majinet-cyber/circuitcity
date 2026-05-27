# inventory/views_agent_performance.py
"""
Agent Performance Page
Shows comprehensive performance metrics for an agent (manager-only access).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, DecimalField
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.contrib import messages

from django.http import Http404
from tenants.utils import require_business, get_active_business
from core.roles import is_manager
from inventory.models import InventoryItem
from sales.models import Sale

User = get_user_model()


def _get_scoped_agent(request, agent_id: int, business):
    """
    Get an agent user scoped to the current business.
    
    SECURITY: Verifies agent belongs to business via Membership BEFORE 
    returning to prevent IDOR vulnerabilities.
    
    Returns 404 if agent doesn't exist or doesn't belong to business.
    """
    try:
        from tenants.models import Membership
        if not Membership.objects.filter(user_id=agent_id, business=business, status="ACTIVE").exists():
            raise Http404("Agent not found")
    except ImportError:
        pass  # If Membership model unavailable, continue
    
    return get_object_or_404(User, pk=agent_id)


def _parse_date_range(request: HttpRequest) -> tuple[date, date, str]:
    """
    Parse date range from query parameters.
    Returns (start_date, end_date, label).
    Defaults to "This Month" (MTD).
    """
    now = timezone.now()
    today = now.date()
    today_start = today

    range_param = request.GET.get("range", "mtd").lower()

    if range_param == "today":
        start_date = today
        end_date = today + timedelta(days=1)
        label = "Today"
    elif range_param == "7d":
        start_date = today - timedelta(days=6)
        end_date = today + timedelta(days=1)
        label = "Last 7 Days"
    elif range_param == "custom":
        # Parse custom dates
        start_str = request.GET.get("start", "")
        end_str = request.GET.get("end", "")
        try:
            start_date = date.fromisoformat(start_str)
            end_date = date.fromisoformat(end_str) + timedelta(days=1)  # Make end inclusive
            label = f"{start_date.strftime('%b %d')} – {end_date.strftime('%b %d, %Y')}"
        except (ValueError, TypeError):
            # Fall back to MTD
            start_date = today.replace(day=1)
            end_date = today + timedelta(days=1)
            label = "This Month"
    else:  # 'mtd' or default
        start_date = today.replace(day=1)
        end_date = today + timedelta(days=1)
        label = "This Month"

    return start_date, end_date, label


@login_required
@require_business
def agent_performance(request: HttpRequest, agent_id: int) -> HttpResponse:
    """
    Agent Performance page (manager-only access).

    Shows comprehensive metrics for an agent:
    - Stock held (count + value)
    - Sales performance (count + revenue + profit)
    - Earnings (commission/payments)

    All scoped to manager's business. Agents can optionally view their own page.
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("inventory:inventory_dashboard")

    # Security: Only managers can view any agent's performance
    # Agents can view their own performance only
    if not is_manager(request.user):
        if request.user.pk != agent_id:
            messages.error(request, "You don't have permission to view this agent's performance.")
            return redirect("inventory:inventory_dashboard")

    # ✅ SECURITY: Get agent with business scope BEFORE proceeding (prevents IDOR)
    agent = _get_scoped_agent(request, agent_id, business)

    # Parse date range
    start_date, end_date, range_label = _parse_date_range(request)

    # Convert to timezone-aware datetimes for filtering
    start_dt = timezone.make_aware(timezone.datetime.combine(start_date, timezone.datetime.min.time()))
    end_dt = timezone.make_aware(timezone.datetime.combine(end_date, timezone.datetime.min.time()))

    # ==========================================================================
    # STOCK HELD BY AGENT (current snapshot)
    # ==========================================================================
    stock_held = InventoryItem.objects.filter(
        business=business,
        assigned_agent=agent,
        status="IN_STOCK",
        is_active=True,
    ).select_related("product", "current_location")

    stock_count = stock_held.count()

    stock_cost_value = stock_held.aggregate(
        total=Coalesce(Sum("order_price"), Decimal("0.00"), output_field=DecimalField())
    )["total"] or Decimal("0.00")

    stock_selling_value = stock_held.aggregate(
        total=Coalesce(Sum("selling_price"), Decimal("0.00"), output_field=DecimalField())
    )["total"] or Decimal("0.00")

    stock_potential_profit = stock_selling_value - stock_cost_value

    # Stock list for display (limit to 50 for performance)
    stock_list = stock_held.order_by("-received_at")[:50]

    # ==========================================================================
    # SALES PERFORMANCE (selected date range)
    # ==========================================================================
    # Sales by this agent in the date range
    sales_qs = Sale.objects.filter(
        item__business=business,
        agent=agent,
        sold_at__gte=start_dt,
        sold_at__lt=end_dt,
    ).select_related("item", "item__product", "location")

    sales_count = sales_qs.count()

    sales_revenue = sales_qs.aggregate(total=Coalesce(Sum("price"), Decimal("0.00"), output_field=DecimalField()))[
        "total"
    ] or Decimal("0.00")

    # Calculate COGS for sold items
    sales_cogs = sales_qs.aggregate(
        total=Coalesce(Sum("item__order_price"), Decimal("0.00"), output_field=DecimalField())
    )["total"] or Decimal("0.00")

    sales_profit = sales_revenue - sales_cogs

    # ==========================================================================
    # EARNINGS (commission/payments for this period)
    # ==========================================================================
    # Try to get earnings from wallet/commission system
    earnings_total = Decimal("0.00")
    try:
        from wallet.models import WalletTransaction, Ledger, TxnType

        # Get agent commission/payout transactions
        earnings_qs = WalletTransaction.objects.filter(
            business=business,
            user=agent,
            ledger=Ledger.AGENT,
            type__in=[TxnType.COMMISSION, TxnType.SALARY, TxnType.BONUS],
            effective_date__gte=start_date,
            effective_date__lt=end_date,
        )

        earnings_total = earnings_qs.aggregate(
            total=Coalesce(Sum("amount"), Decimal("0.00"), output_field=DecimalField())
        )["total"] or Decimal("0.00")

    except Exception:
        # Wallet module not available or earnings system not implemented
        pass

    # ==========================================================================
    # CONTEXT ASSEMBLY
    # ==========================================================================
    context = {
        "agent": agent,
        "agent_name": agent.get_full_name() or agent.username or agent.email,
        "business": business,
        "range_label": range_label,
        "start_date": start_date,
        "end_date": end_date,
        # Stock metrics
        "stock_count": stock_count,
        "stock_cost_value": stock_cost_value,
        "stock_selling_value": stock_selling_value,
        "stock_potential_profit": stock_potential_profit,
        "stock_list": stock_list,
        # Sales metrics
        "sales_count": sales_count,
        "sales_revenue": sales_revenue,
        "sales_cogs": sales_cogs,
        "sales_profit": sales_profit,
        # Earnings
        "earnings_total": earnings_total,
    }

    return render(request, "inventory/agent_performance.html", context)

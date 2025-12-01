# tenants/views_agent_detail.py
"""
Agent detail view with earnings panel and date filters.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Avg, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from inventory.models import InventoryItem
from sales.models import Sale
from tenants.utils import require_business, require_role

User = get_user_model()


@login_required
@require_business
@require_role(["Manager", "Admin"])
def agent_detail(request: HttpRequest, agent_id: int) -> HttpResponse:
    """
    Detail view for an agent showing:
    - Stock assigned to them
    - Earnings panel with filters (Today, Last 7 days, Last 30 days, Custom range)
    - Sales metrics
    """
    business = request.business
    agent = get_object_or_404(User, pk=agent_id)
    
    # Check that agent belongs to this business
    from tenants.models import Membership
    membership = Membership.objects.filter(
        user=agent,
        business=business,
        role="AGENT",
        status="ACTIVE"
    ).first()
    
    if not membership:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Agent not found in this business.")
    
    # Parse date filters
    filter_type = request.GET.get("filter", "last_30_days")
    today = timezone.now().date()
    
    if filter_type == "today":
        start_date = today
        end_date = today
        period_label = "Today"
    elif filter_type == "last_7_days":
        start_date = today - timedelta(days=7)
        end_date = today
        period_label = "Last 7 Days"
    elif filter_type == "last_30_days":
        start_date = today - timedelta(days=30)
        end_date = today
        period_label = "Last 30 Days"
    elif filter_type == "custom":
        # Custom date range from query params
        start_str = request.GET.get("start_date", "")
        end_str = request.GET.get("end_date", "")
        try:
            start_date = date.fromisoformat(start_str) if start_str else today - timedelta(days=30)
            end_date = date.fromisoformat(end_str) if end_str else today
        except (ValueError, TypeError):
            start_date = today - timedelta(days=30)
            end_date = today
        period_label = f"{start_date} to {end_date}"
    else:
        # Default to last 30 days
        start_date = today - timedelta(days=30)
        end_date = today
        period_label = "Last 30 Days"
    
    # Stock assigned to agent
    agent_stock_qs = InventoryItem.objects.filter(
        business=business,
        assigned_agent=agent,
        is_active=True
    )
    stock_in_stock = agent_stock_qs.filter(status="IN_STOCK").count()
    stock_sold = agent_stock_qs.filter(status="SOLD").count()
    stock_total = agent_stock_qs.count()
    
    # Sales by agent in the selected period
    sales_qs = Sale.objects.filter(
        agent=agent,
        location__business=business,
        sold_at__gte=start_date,
        sold_at__lte=end_date
    )
    
    # Earnings metrics
    sales_count = sales_qs.count()
    total_sales_amount = sales_qs.aggregate(total=Sum("price"))["total"] or Decimal("0")
    avg_selling_price = sales_qs.aggregate(avg=Avg("price"))["avg"] or Decimal("0")
    
    # Commission (if commission tracking exists)
    try:
        from sales.models import SaleCommission
        commissions_qs = SaleCommission.objects.filter(
            agent=agent,
            business=business,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )
        total_commission = commissions_qs.aggregate(total=Sum("net_amount"))["total"] or Decimal("0")
        commission_breakdown = {
            "base": commissions_qs.aggregate(total=Sum("base_commission"))["total"] or Decimal("0"),
            "bonus": commissions_qs.aggregate(total=Sum("early_bonus"))["total"] or Decimal("0"),
            "penalty": commissions_qs.aggregate(total=Sum("late_penalty"))["total"] or Decimal("0"),
        }
    except ImportError:
        total_commission = Decimal("0")
        commission_breakdown = None
    
    # Sales list (last 20 in period)
    recent_sales = list(sales_qs.select_related("item", "item__product", "location").order_by("-sold_at")[:20])
    
    ctx = {
        "agent": agent,
        "membership": membership,
        "stock_in_stock": stock_in_stock,
        "stock_sold": stock_sold,
        "stock_total": stock_total,
        "filter_type": filter_type,
        "start_date": start_date,
        "end_date": end_date,
        "period_label": period_label,
        "sales_count": sales_count,
        "total_sales_amount": total_sales_amount,
        "avg_selling_price": avg_selling_price,
        "total_commission": total_commission,
        "commission_breakdown": commission_breakdown,
        "recent_sales": recent_sales,
    }
    
    return render(request, "tenants/agent_detail.html", ctx)


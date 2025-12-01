# tenants/views_location_detail.py
"""
Location detail view showing stock and agent performance.
"""
from __future__ import annotations

from typing import Any, Dict

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from inventory.models import Location, InventoryItem
from sales.models import Sale
from tenants.utils import require_business, require_role


@login_required
@require_business
@require_role(["Manager", "Admin"])
def location_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Detail view for a location showing:
    - Stock at this location
    - Agents at this location with their sales and stock counts
    """
    business = request.business
    location = get_object_or_404(Location, business=business, pk=pk)
    
    # Stock at this location
    stock_qs = InventoryItem.objects.filter(
        business=business,
        current_location=location,
        is_active=True
    )
    
    stock_in_stock = stock_qs.filter(status="IN_STOCK")
    stock_sold = stock_qs.filter(status="SOLD")
    
    stock_list = list(stock_in_stock.select_related("product", "assigned_agent")[:100])
    
    # Sales at this location
    sales_qs = Sale.objects.filter(location=location)
    sales_count = sales_qs.count()
    sales_amount = sales_qs.aggregate(total=Sum("price"))["total"] or 0
    
    # Agents at this location
    from tenants.models import Membership
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    # Get agents assigned to this location
    agent_memberships = Membership.objects.filter(
        business=business,
        location=location,
        role="AGENT",
        status="ACTIVE"
    ).select_related("user")
    
    agent_stats = []
    for membership in agent_memberships:
        agent = membership.user
        
        # Stock assigned to this agent at this location
        agent_stock_count = stock_in_stock.filter(assigned_agent=agent).count()
        
        # Sales by this agent at this location
        agent_sales_qs = sales_qs.filter(agent=agent)
        agent_sales_count = agent_sales_qs.count()
        agent_sales_amount = agent_sales_qs.aggregate(total=Sum("price"))["total"] or 0
        
        agent_stats.append({
            "agent": agent,
            "stock_count": agent_stock_count,
            "sales_count": agent_sales_count,
            "sales_amount": agent_sales_amount,
        })
    
    # Sort by sales amount descending
    agent_stats.sort(key=lambda x: x["sales_amount"], reverse=True)
    
    ctx = {
        "location": location,
        "stock_in_stock_count": stock_in_stock.count(),
        "stock_sold_count": stock_sold.count(),
        "stock_total": stock_qs.count(),
        "stock_list": stock_list,
        "sales_count": sales_count,
        "sales_amount": sales_amount,
        "agent_stats": agent_stats,
    }
    
    return render(request, "tenants/location_detail.html", ctx)


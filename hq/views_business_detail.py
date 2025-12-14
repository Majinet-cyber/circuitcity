# hq/views_business_detail.py
"""
Business Detail Command Center - Comprehensive tabbed view for business management.
Tabs: Overview, Subscription, Users, Data, Sales, Health, Tickets, Audit.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
import json
from django.contrib import messages
from django.db.models import Count, Sum, Q
from django.db.models.functions import TruncDate
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from hq.permissions import hq_admin_required
from tenants.models import Business, Membership
from billing.models import BusinessSubscription as Subscription, Invoice
from billing.models_extensions import get_subscription_state
from wallet.models import WalletTransaction
from sales.models import Sale

try:
    from hq.models import SupportActionLog, SupportTicket, BusinessNote
    from inventory.models import InventoryItem
except ImportError:
    SupportActionLog = None
    SupportTicket = None
    BusinessNote = None
    InventoryItem = None


@hq_admin_required
def business_command_center(request: HttpRequest, business_id: int) -> HttpResponse:
    """
    Premium command center for a single business with tabbed interface.
    """
    business = get_object_or_404(Business, id=business_id)
    active_tab = request.GET.get("tab", "overview")
    
    # ===================================================================
    # Common Data (All Tabs)
    # ===================================================================
    try:
        subscription = business.subscription
        sub_state = get_subscription_state(subscription)
    except Exception:
        subscription = None
        sub_state = {"status": "none", "is_active": False}
    
    # Memberships
    memberships = Membership.objects.filter(business=business).select_related("user").order_by("-role")
    
    # ===================================================================
    # Tab-Specific Data
    # ===================================================================
    context = {
        "business": business,
        "subscription": subscription,
        "sub_state": sub_state,
        "memberships": memberships,
        "active_tab": active_tab,
    }
    
    if active_tab == "overview":
        context.update(_get_overview_data(business, subscription))
    
    elif active_tab == "subscription":
        context.update(_get_subscription_data(business, subscription))
    
    elif active_tab == "users":
        context.update(_get_users_data(business))
    
    elif active_tab == "data":
        context.update(_get_data_inventory_data(business))
    
    elif active_tab == "sales":
        context.update(_get_sales_wallet_data(business))
    
    elif active_tab == "health":
        context.update(_get_health_logs_data(business))
    
    elif active_tab == "tickets":
        context.update(_get_tickets_data(business))
    
    elif active_tab == "audit":
        context.update(_get_audit_data(business))
    
    # ===================================================================
    # Chart Data (for all tabs that need it)
    # ===================================================================
    chart_data = _get_chart_data(business)
    context["chart_data"] = json.dumps(chart_data)
    
    return render(request, "hq/business_command_center.html", context)


def _get_overview_data(business: Business, subscription: Subscription | None) -> dict:
    """Get overview tab data."""
    # Financial summary
    invoices = Invoice.objects.filter(business=business)
    total_invoices = invoices.count()
    paid_total = invoices.filter(status="PAID").aggregate(
        total=Sum("total")
    )["total"] or Decimal("0")
    open_total = invoices.filter(status__in=["PENDING", "OPEN"]).aggregate(
        total=Sum("total")
    )["total"] or Decimal("0")
    
    # Sales summary (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    if Sale:
        sales_30d = Sale.objects.filter(
            business=business,
            created_at__gte=thirty_days_ago
        ).aggregate(
            count=Count("id"),
            total=Sum("amount")
        )
        sales_count_30d = sales_30d["count"] or 0
        sales_total_30d = sales_30d["total"] or Decimal("0")
    else:
        sales_count_30d = 0
        sales_total_30d = Decimal("0")
    
    # Agents
    agents_count = Membership.objects.filter(
        business=business,
        role__in=["AGENT", "MANAGER"]
    ).count()
    
    # Stock summary (if applicable)
    if InventoryItem:
        stock_count = InventoryItem.objects.filter(business=business, archived=False).count()
        stock_in_7d = InventoryItem.objects.filter(
            business=business,
            created_at__gte=timezone.now() - timedelta(days=7)
        ).count()
    else:
        stock_count = 0
        stock_in_7d = 0
    
    # Pinned notes
    notes = []
    if BusinessNote:
        notes = BusinessNote.objects.filter(business=business, is_pinned=True)[:5]
    
    return {
        "total_invoices": total_invoices,
        "paid_total": paid_total,
        "open_total": open_total,
        "sales_count_30d": sales_count_30d,
        "sales_total_30d": sales_total_30d,
        "agents_count": agents_count,
        "stock_count": stock_count,
        "stock_in_7d": stock_in_7d,
        "pinned_notes": notes,
    }


def _get_subscription_data(business: Business, subscription: Subscription | None) -> dict:
    """Get subscription tab data."""
    if not subscription:
        return {"subscription_history": []}
    
    # Payment history
    invoices = Invoice.objects.filter(business=business).order_by("-created_at")[:20]
    
    # Subscription change history (if SupportActionLog exists)
    history = []
    if SupportActionLog:
        history = SupportActionLog.objects.filter(
            business=business,
            action_type__in=[
                "EXTEND_SUBSCRIPTION",
                "REVOKE_SUBSCRIPTION",
                "ACTIVATE_SUBSCRIPTION",
                "SUSPEND_SUBSCRIPTION",
                "CHANGE_PLAN",
            ]
        ).select_related("actor").order_by("-created_at")[:20]
    
    return {
        "invoices": invoices,
        "subscription_history": history,
    }


def _get_users_data(business: Business) -> dict:
    """Get users tab data."""
    from circuitcity.accounts.models import LoginSecurity
    
    users_with_sec = []
    for m in Membership.objects.filter(business=business).select_related("user"):
        user = m.user
        login_sec = None
        try:
            login_sec = LoginSecurity.objects.get(user=user)
        except Exception:
            pass
        
        users_with_sec.append({
            "membership": m,
            "user": user,
            "login_sec": login_sec,
            "is_locked": login_sec.is_locked() if login_sec else False,
        })
    
    return {"users_with_sec": users_with_sec}


def _get_data_inventory_data(business: Business) -> dict:
    """Get data & inventory tab data."""
    if not InventoryItem:
        return {"stock_items": [], "archived_count": 0}
    
    # Recent stock
    stock_items = InventoryItem.objects.filter(
        business=business,
        archived=False
    ).order_by("-created_at")[:20]
    
    archived_count = InventoryItem.objects.filter(
        business=business,
        archived=True
    ).count()
    
    return {
        "stock_items": stock_items,
        "archived_count": archived_count,
    }


def _get_sales_wallet_data(business: Business) -> dict:
    """Get sales & wallet tab data."""
    # Sales (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    if Sale:
        recent_sales = Sale.objects.filter(
            business=business,
            created_at__gte=thirty_days_ago
        ).order_by("-created_at")[:20]
    else:
        recent_sales = []
    
    # Wallet transactions
    wallet_txns = WalletTransaction.objects.filter(
        business=business
    ).order_by("-created_at")[:20]
    
    # Summary
    wallet_summary = WalletTransaction.objects.filter(
        business=business
    ).aggregate(
        total_income=Sum("amount", filter=Q(amount__gt=0)),
        total_expense=Sum("amount", filter=Q(amount__lt=0))
    )
    
    return {
        "recent_sales": recent_sales,
        "wallet_txns": wallet_txns,
        "wallet_total_income": wallet_summary["total_income"] or Decimal("0"),
        "wallet_total_expense": abs(wallet_summary["total_expense"] or Decimal("0")),
    }


def _get_health_logs_data(business: Business) -> dict:
    """Get health & logs tab data."""
    # System health indicators
    # - Recent errors (if you have error tracking)
    # - Performance metrics
    # - API usage
    
    # For now, just placeholder
    return {
        "health_status": "healthy",
        "last_activity": timezone.now(),
    }


def _get_tickets_data(business: Business) -> dict:
    """Get support tickets tab data."""
    if not SupportTicket:
        return {"tickets": [], "open_tickets_count": 0}
    
    tickets = SupportTicket.objects.filter(business=business).order_by("-created_at")[:20]
    open_tickets_count = SupportTicket.objects.filter(
        business=business,
        status__in=["open", "in_progress"]
    ).count()
    
    return {
        "tickets": tickets,
        "open_tickets_count": open_tickets_count,
    }


def _get_audit_data(business: Business) -> dict:
    """Get audit trail tab data."""
    if not SupportActionLog:
        return {"audit_logs": []}
    
    audit_logs = SupportActionLog.objects.filter(
        business=business
    ).select_related("actor").order_by("-created_at")[:50]
    
    return {"audit_logs": audit_logs}


# ======================================================================
# Quick Actions
# ======================================================================
@hq_admin_required
@require_POST
def add_business_note(request: HttpRequest, business_id: int) -> HttpResponse:
    """Add a pinned note to a business."""
    if not BusinessNote:
        messages.error(request, "BusinessNote model not available")
        return redirect("hq:business_command_center", business_id=business_id)
    
    business = get_object_or_404(Business, id=business_id)
    
    title = request.POST.get("title", "").strip()
    content = request.POST.get("content", "").strip()
    
    if not title or not content:
        messages.error(request, "Title and content are required")
        return redirect("hq:business_command_center", business_id=business_id)
    
    BusinessNote.objects.create(
        business=business,
        author=request.user,
        title=title,
        content=content,
        is_pinned=True
    )
    
    messages.success(request, "Note added successfully")
    return redirect("hq:business_command_center", business_id=business_id)


def _get_chart_data(business: Business) -> dict:
    """Generate chart data for business command center."""
    thirty_days_ago = timezone.now() - timedelta(days=30)
    ninety_days_ago = timezone.now() - timedelta(days=90)
    
    # Sales revenue trend (last 30 days)
    sales_trend_labels = []
    sales_trend_data = []
    
    if Sale:
        sales_by_day = Sale.objects.filter(
            business=business,
            created_at__gte=thirty_days_ago
        ).annotate(
            date=TruncDate("created_at")
        ).values("date").annotate(
            total=Sum("amount")
        ).order_by("date")
        
        for item in sales_by_day:
            sales_trend_labels.append(item["date"].strftime("%b %d"))
            sales_trend_data.append(float(item["total"]) if item["total"] else 0)
    
    # Transactions by type (wallet)
    txn_types = WalletTransaction.objects.filter(
        business=business
    ).values("transaction_type").annotate(
        count=Count("id")
    ).order_by("-count")
    
    transactions_by_type = {}
    for item in txn_types:
        txn_type = item["transaction_type"] or "Other"
        transactions_by_type[txn_type.replace("_", " ").title()] = item["count"]
    
    # Sale amounts distribution (histogram)
    sale_amounts = []
    if Sale:
        recent_sales = Sale.objects.filter(
            business=business,
            created_at__gte=thirty_days_ago
        ).values_list("amount", flat=True)
        sale_amounts = [float(amt) for amt in recent_sales if amt]
    
    # Create bins for histogram
    sale_distribution = {
        "0-1000": 0,
        "1000-5000": 0,
        "5000-10000": 0,
        "10000-50000": 0,
        "50000+": 0
    }
    
    for amount in sale_amounts:
        if amount <= 1000:
            sale_distribution["0-1000"] += 1
        elif amount <= 5000:
            sale_distribution["1000-5000"] += 1
        elif amount <= 10000:
            sale_distribution["5000-10000"] += 1
        elif amount <= 50000:
            sale_distribution["10000-50000"] += 1
        else:
            sale_distribution["50000+"] += 1
    
    # Tickets trend (if available)
    tickets_opened = 0
    tickets_closed = 0
    
    if SupportTicket:
        tickets_opened = SupportTicket.objects.filter(
            business=business,
            created_at__gte=thirty_days_ago
        ).count()
        
        tickets_closed = SupportTicket.objects.filter(
            business=business,
            status__in=["resolved", "closed"],
            resolved_at__gte=thirty_days_ago
        ).count()
    
    return {
        "sales_trend": {
            "labels": sales_trend_labels or ["No data"],
            "data": sales_trend_data or [0]
        },
        "transactions_by_type": transactions_by_type,
        "sale_distribution": sale_distribution,
        "tickets": {
            "opened": tickets_opened,
            "closed": tickets_closed
        }
    }


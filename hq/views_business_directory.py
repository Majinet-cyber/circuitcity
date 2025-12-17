# hq/views_business_directory.py
"""
Enhanced HQ Business Directory - Global search, KPIs, alerts, and management.
Premium Overwatch-style business monitoring and control.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
import json
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum, F
from django.db.models.functions import TruncDate
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from hq.permissions import hq_admin_required
from tenants.models import Business, Membership
from billing.models import BusinessSubscription as Subscription, Invoice
from billing.models_extensions import get_subscription_state

try:
    from hq.models import SupportActionLog, SupportTicket
except ImportError:
    SupportActionLog = None
    SupportTicket = None

# Check if contracts module is available
try:
    from hq import views_contracts
    CONTRACTS_ENABLED = True
except ImportError:
    CONTRACTS_ENABLED = False


@hq_admin_required
def business_directory(request: HttpRequest) -> HttpResponse:
    """
    Premium business directory with global KPIs, alerts, search, and filters.
    """
    # ===================================================================
    # Global KPIs
    # ===================================================================
    total_businesses = Business.objects.count()
    active_businesses = Business.objects.filter(status="ACTIVE").count()
    
    subs = Subscription.objects.select_related("business")
    trial_count = subs.filter(status="trial").count()
    active_subs = subs.filter(status="active").count()
    suspended_count = subs.filter(status="canceled").count()
    expired_count = subs.filter(status="expired").count()
    
    # Expiring soon (within 7 days)
    soon = timezone.now() + timedelta(days=7)
    expiring_soon = subs.filter(
        status__in=["trial", "active"],
        current_period_end__lte=soon,
        current_period_end__gt=timezone.now()
    ).count()
    
    # ===================================================================
    # Alerts
    # ===================================================================
    alerts = []
    
    # Failed payments (last 7 days)
    week_ago = timezone.now() - timedelta(days=7)
    failed_invoices = Invoice.objects.filter(
        status__in=["FAILED", "DECLINED"],
        created_at__gte=week_ago
    ).values("business__name").distinct().count()
    
    if failed_invoices > 0:
        alerts.append({
            "type": "danger",
            "icon": "💳",
            "title": "Failed Payments",
            "message": f"{failed_invoices} businesses with failed payment attempts in the last 7 days",
            "count": failed_invoices
        })
    
    # Expiring soon
    if expiring_soon > 0:
        alerts.append({
            "type": "warning",
            "icon": "⏰",
            "title": "Expiring Soon",
            "message": f"{expiring_soon} subscriptions expiring within 7 days",
            "count": expiring_soon
        })
    
    # Suspended businesses
    if suspended_count > 0:
        alerts.append({
            "type": "info",
            "icon": "🚫",
            "title": "Suspended",
            "message": f"{suspended_count} businesses currently suspended",
            "count": suspended_count
        })
    
    # Open support tickets (if model exists)
    if SupportTicket:
        open_tickets = SupportTicket.objects.filter(status__in=["open", "in_progress"]).count()
        if open_tickets > 0:
            alerts.append({
                "type": "info",
                "icon": "🎫",
                "title": "Open Tickets",
                "message": f"{open_tickets} support tickets require attention",
                "count": open_tickets
            })
    
    # ===================================================================
    # Business List with Filters & Search
    # ===================================================================
    businesses = Business.objects.select_related().prefetch_related("subscription")
    
    # Search
    search_query = request.GET.get("q", "").strip()
    if search_query:
        businesses = businesses.filter(
            Q(name__icontains=search_query) |
            Q(slug__icontains=search_query) |
            Q(created_by__email__icontains=search_query) |
            Q(created_by__first_name__icontains=search_query) |
            Q(created_by__last_name__icontains=search_query)
        )
    
    # Status filter
    status_filter = request.GET.get("status", "").upper()
    if status_filter in ["ACTIVE", "PENDING", "SUSPENDED"]:
        businesses = businesses.filter(status=status_filter)
    
    # Subscription status filter
    sub_status_filter = request.GET.get("sub_status", "")
    if sub_status_filter:
        businesses = businesses.filter(subscription__status=sub_status_filter)
    
    # Vertical filter
    vertical_filter = request.GET.get("vertical", "")
    if vertical_filter:
        businesses = businesses.filter(business_kind=vertical_filter)
    
    # Expiring filter
    if request.GET.get("expiring") == "true":
        businesses = businesses.filter(
            subscription__status__in=["trial", "active"],
            subscription__current_period_end__lte=soon,
            subscription__current_period_end__gt=timezone.now()
        )
    
    # Sort
    sort_by = request.GET.get("sort", "-created_at")
    valid_sorts = ["name", "-name", "created_at", "-created_at"]
    if sort_by in valid_sorts:
        businesses = businesses.order_by(sort_by)
    else:
        businesses = businesses.order_by("-created_at")
    
    # Pagination
    paginator = Paginator(businesses, 25)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)
    
    # Enrich with subscription state - normalize to prevent template errors
    def normalize_sub_state(d):
        """Ensure all expected keys exist with safe defaults."""
        d = d or {}
        return {
            "status": d.get("status") or "none",
            "is_active": bool(d.get("is_active")),
            "days_remaining": d.get("days_remaining") or None,
            "plan_name": d.get("plan_name") or d.get("plan") or None,
            "expires_at": d.get("expires_at") or d.get("expiry_date") or None,
            "renews_on": d.get("renews_on") or None,
            "started_on": d.get("started_on") or None,
            "is_expired": bool(d.get("is_expired")),
            "is_in_grace": bool(d.get("is_in_grace")),
            "needs_payment": bool(d.get("needs_payment")),
            "trial_ends_at": d.get("trial_ends_at") or None,
            "period_ends_at": d.get("period_ends_at") or None,
        }
    
    for biz in page_obj:
        try:
            sub = biz.subscription
            biz.sub_state = normalize_sub_state(get_subscription_state(sub))
        except Exception:
            # Ensure all keys are present for template safety
            biz.sub_state = normalize_sub_state({})
    
    # ===================================================================
    # Chart Data Generation
    # ===================================================================
    
    # Active businesses trend (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    active_trend = Business.objects.filter(
        status="ACTIVE",
        created_at__gte=thirty_days_ago
    ).annotate(
        date=TruncDate("created_at")
    ).values("date").annotate(
        count=Count("id")
    ).order_by("date")
    
    trend_labels = []
    trend_data = []
    for item in active_trend:
        trend_labels.append(item["date"].strftime("%b %d"))
        trend_data.append(item["count"])
    
    # Businesses by vertical
    vertical_counts = Business.objects.values("business_kind").annotate(
        count=Count("id")
    ).order_by("-count")
    
    businesses_by_vertical = {}
    for item in vertical_counts:
        vertical = item["business_kind"] or "General"
        businesses_by_vertical[vertical.replace("_", " ").title()] = item["count"]
    
    # Days remaining distribution
    now = timezone.now()
    all_subs = Subscription.objects.filter(
        status__in=["trial", "active"]
    ).select_related("business")
    
    days_distribution = {
        "0-7": 0,
        "8-30": 0,
        "31-90": 0,
        "91-180": 0,
        "181+": 0
    }
    
    for sub in all_subs:
        if sub.current_period_end:
            days_left = (sub.current_period_end - now).days
            if days_left < 0:
                continue
            elif days_left <= 7:
                days_distribution["0-7"] += 1
            elif days_left <= 30:
                days_distribution["8-30"] += 1
            elif days_left <= 90:
                days_distribution["31-90"] += 1
            elif days_left <= 180:
                days_distribution["91-180"] += 1
            else:
                days_distribution["181+"] += 1
    
    # Calculate support health score
    open_tickets_count = 0
    if SupportTicket:
        open_tickets_count = SupportTicket.objects.filter(status__in=["open", "in_progress"]).count()
    
    # Simple weighted formula (higher is better)
    support_health_score = 100
    support_health_score -= min(open_tickets_count * 5, 30)  # Up to -30 for tickets
    support_health_score -= min(expiring_soon * 2, 20)  # Up to -20 for expiring
    support_health_score -= min(failed_invoices * 3, 20)  # Up to -20 for failed payments
    support_health_score = max(0, support_health_score)  # Floor at 0
    
    # Chart data bundle
    chart_data = {
        "active_businesses_trend": {
            "labels": trend_labels or ["No data"],
            "data": trend_data or [0]
        },
        "businesses_by_vertical": businesses_by_vertical,
        "days_remaining_distribution": days_distribution,
        "subscription_status_distribution": {
            "Active": active_subs,
            "Trial": trial_count,
            "Suspended": suspended_count,
            "Expired": expired_count
        }
    }
    
    # ===================================================================
    # Context
    # ===================================================================
    context = {
        "page_title": "Business Directory",
        "active_tab": "directory",  # For template navigation consistency
        "total_businesses": total_businesses,
        "active_businesses": active_businesses,
        "trial_count": trial_count,
        "active_subs": active_subs,
        "suspended_count": suspended_count,
        "expired_count": expired_count,
        "expiring_soon": expiring_soon,
        "alerts": alerts,
        "businesses": page_obj,
        "search_query": search_query,
        "status_filter": status_filter,
        "sub_status_filter": sub_status_filter,
        "vertical_filter": vertical_filter,
        "sort_by": sort_by,
        "page_obj": page_obj,
        # Use real BusinessKind choices from database (no hardcoded fake verticals)
        "verticals": [
            (choice[0], choice[1]) for choice in Business._meta.get_field('business_kind').choices
        ] if hasattr(Business._meta.get_field('business_kind'), 'choices') else [],
        "chart_data": json.dumps(chart_data),
        "support_health_score": support_health_score,
        "failed_payments_count": failed_invoices,
        "contracts_enabled": CONTRACTS_ENABLED,
    }
    
    return render(request, "hq/business_directory.html", context)


@hq_admin_required
@require_http_methods(["GET"])
def business_search_api(request: HttpRequest) -> JsonResponse:
    """
    AJAX endpoint for global business search (autocomplete).
    Searches: business name, owner email, phone.
    """
    query = request.GET.get("q", "").strip()
    if len(query) < 2:
        return JsonResponse({"results": []})
    
    businesses = Business.objects.filter(
        Q(name__icontains=query) |
        Q(slug__icontains=query) |
        Q(created_by__email__icontains=query) |
        Q(created_by__first_name__icontains=query) |
        Q(created_by__last_name__icontains=query)
    ).select_related("created_by", "subscription")[:10]
    
    results = []
    for biz in businesses:
        try:
            sub = biz.subscription
            sub_status = sub.get_status_display() if sub else "No Subscription"
            sub_color = _status_badge_color(sub.status if sub else "none")
        except Exception:
            sub_status = "No Subscription"
            sub_color = "#6b7280"
        
        results.append({
            "id": biz.id,
            "name": biz.name,
            "slug": biz.slug,
            "status": biz.status,
            "vertical": biz.business_kind or "general",
            "owner_email": biz.created_by.email if biz.created_by else "",
            "sub_status": sub_status,
            "sub_color": sub_color,
            "url": f"/hq/businesses/{biz.id}/"
        })
    
    return JsonResponse({"results": results})


def _status_badge_color(status: str) -> str:
    """Get badge color for subscription status."""
    colors = {
        "trial": "#06b6d4",  # cyan
        "active": "#16a34a",  # green
        "grace": "#f59e0b",  # amber
        "past_due": "#ef4444",  # red
        "canceled": "#ef4444",  # red
        "expired": "#6b7280",  # gray
        "none": "#6b7280",
    }
    return colors.get(status, "#6b7280")


@hq_admin_required
@require_http_methods(["POST"])
def quick_action(request: HttpRequest, business_id: int) -> HttpResponse:
    """
    Quick actions from business directory (extend, suspend, etc.).
    """
    business = get_object_or_404(Business, id=business_id)
    action = request.POST.get("action", "")
    
    if action == "extend_30":
        try:
            from billing.models_extensions import extend_subscription_days
            sub = business.subscription
            extend_subscription_days(
                sub,
                days=30,
                reason="Quick extend from directory (HQ)",
                actor=request.user
            )
            messages.success(request, f"Extended {business.name} by 30 days")
        except Exception as e:
            messages.error(request, f"Failed to extend: {e}")
    
    elif action == "suspend":
        try:
            from billing.models_extensions import suspend_subscription
            sub = business.subscription
            suspend_subscription(
                sub,
                reason="Quick suspend from directory (HQ)",
                actor=request.user
            )
            messages.success(request, f"Suspended {business.name}")
        except Exception as e:
            messages.error(request, f"Failed to suspend: {e}")
    
    elif action == "activate":
        try:
            from billing.models_extensions import activate_subscription
            sub = business.subscription
            activate_subscription(
                sub,
                days=30,
                reason="Quick activate from directory (HQ)",
                actor=request.user
            )
            messages.success(request, f"Activated {business.name} for 30 days")
        except Exception as e:
            messages.error(request, f"Failed to activate: {e}")
    
    else:
        messages.error(request, "Unknown action")
    
    return redirect("hq:business_directory")


@hq_admin_required
def business_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """
    URL target for the directory 'View' link.
    Redirects to the business command center for the given business ID.
    """
    return redirect("hq:business_command_center", business_id=pk)

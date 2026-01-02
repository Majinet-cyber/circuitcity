# audit/views.py
"""
Views for audit log management (HQ only).
"""
import csv
from datetime import datetime, timedelta
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db.models import Q
from django.core.paginator import Paginator
from django.utils import timezone
from .models import AuditLog
from tenants.decorators import hq_only


@login_required
@hq_only
def audit_log_list(request):
    """
    HQ view: List and filter audit logs.

    STAFF-ONLY SCOPE: This page shows platform staff/superuser activity only,
    not merchant/tenant activity. Purpose: prove we don't snoop merchant data
    unless we're fixing something.
    """
    # Base queryset: ONLY staff/superuser activity (HQ transparency requirement)
    logs = AuditLog.objects.filter(Q(user__is_staff=True) | Q(user__is_superuser=True)).select_related(
        "business", "user"
    )

    # Date range filter
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            logs = logs.filter(created_at__gte=start_dt)
        except ValueError:
            pass

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            # Include the entire end date
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
            logs = logs.filter(created_at__lte=end_dt)
        except ValueError:
            pass

    # Business filter
    business_id = request.GET.get("business")
    if business_id:
        logs = logs.filter(business_id=business_id)

    # User filter
    user_id = request.GET.get("user")
    if user_id:
        logs = logs.filter(user_id=user_id)

    # Action filter
    action = request.GET.get("action")
    if action:
        logs = logs.filter(action__icontains=action)

    # Search
    search = request.GET.get("search")
    if search:
        logs = logs.filter(Q(message__icontains=search) | Q(entity__icontains=search) | Q(entity_id__icontains=search))

    # Export to CSV if requested
    if request.GET.get("export") == "csv":
        return export_audit_logs_csv(logs, start_date, end_date)

    # Pagination
    paginator = Paginator(logs, 50)
    page = request.GET.get("page", 1)
    logs_page = paginator.get_page(page)

    # Get filter options
    from tenants.models import Business
    from django.contrib.auth import get_user_model

    User = get_user_model()

    businesses = Business.objects.filter(status="ACTIVE").order_by("name")
    # Only show staff/superuser in filter dropdown (consistent with queryset)
    users = User.objects.filter(Q(is_staff=True) | Q(is_superuser=True), is_active=True).order_by("username")[:100]

    # Common actions
    common_actions = ["VIEW", "EXPORT", "UPDATE", "DELETE", "CREATE"]

    return render(
        request,
        "audit/audit_log_list.html",
        {
            "logs": logs_page,
            "businesses": businesses,
            "users": users,
            "common_actions": common_actions,
            "filters": {
                "start_date": start_date,
                "end_date": end_date,
                "business": business_id,
                "user": user_id,
                "action": action,
                "search": search,
            },
        },
    )


def export_audit_logs_csv(queryset, start_date=None, end_date=None):
    """Export audit logs to CSV."""
    filename = f"audit_logs_{start_date or 'all'}_{end_date or 'all'}.csv"

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(["Date/Time", "Business", "User", "Action", "Entity", "Entity ID", "Message", "IP Address"])

    for log in queryset.iterator():
        writer.writerow(
            [
                log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                log.business.name if log.business else "",
                log.user.username if log.user else "Anonymous",
                log.action,
                log.entity,
                log.entity_id,
                log.message,
                log.ip or "",
            ]
        )

    return response


@login_required
@hq_only
def audit_log_stats(request):
    """HQ view: Audit log statistics and insights (staff activity only)."""
    # Last 30 days, staff/superuser only
    thirty_days_ago = timezone.now() - timedelta(days=30)
    recent_logs = AuditLog.objects.filter(
        Q(user__is_staff=True) | Q(user__is_superuser=True), created_at__gte=thirty_days_ago
    )

    stats = {
        "total_recent": recent_logs.count(),
        "by_action": {},
        "by_business": {},
        "top_users": [],
    }

    # Group by action
    from django.db.models import Count

    action_counts = recent_logs.values("action").annotate(count=Count("id")).order_by("-count")[:10]
    for item in action_counts:
        stats["by_action"][item["action"]] = item["count"]

    # Group by business
    business_counts = recent_logs.values("business__name").annotate(count=Count("id")).order_by("-count")[:10]
    for item in business_counts:
        stats["by_business"][item["business__name"]] = item["count"]

    # Top users
    user_counts = recent_logs.values("user__username").annotate(count=Count("id")).order_by("-count")[:10]
    stats["top_users"] = [{"username": item["user__username"], "count": item["count"]} for item in user_counts]

    return render(
        request,
        "audit/audit_log_stats.html",
        {
            "stats": stats,
        },
    )

from __future__ import annotations

from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.db.models import QuerySet
from django.utils import timezone

from tenants.models import Membership
from tenants.utils_roles import is_manager

from .models import AgentWorkLog


def parse_iso_timestamp(value):
    if not value:
        return timezone.now()
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed)
    return parsed.astimezone(timezone.get_current_timezone())


def parse_date(value, default: date | None = None) -> date:
    if isinstance(value, date):
        return value
    if not value:
        return default or timezone.localdate()
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return default or timezone.localdate()


def user_can_manage_timelogs(user, business) -> bool:
    return user.is_superuser or user.is_staff or is_manager(user, business)


def available_business_agents(business):
    return (
        Membership.objects.filter(business=business, status="ACTIVE")
        .select_related("user")
        .order_by("user__first_name", "user__last_name", "user__username")
    )


def resolve_selected_agent(request, business):
    selected_agent_id = request.GET.get("agent")
    if user_can_manage_timelogs(request.user, business):
        if selected_agent_id and selected_agent_id != "all":
            User = get_user_model()
            return User.objects.filter(
                id=selected_agent_id,
                memberships__business=business,
                memberships__status="ACTIVE",
            ).first()
        return None
    return request.user


def latest_ping(work_log: AgentWorkLog):
    return work_log.pings.order_by("-timestamp").first() if work_log else None


def geofence_status(work_log: AgentWorkLog) -> str:
    ping = latest_ping(work_log)
    if not ping:
        return "unknown"
    return "inside" if ping.is_inside_geofence else "outside"


def lateness_status(work_log: AgentWorkLog) -> str:
    if not work_log:
        return "not_checked_in"
    if work_log.arrived_late_minutes > 0:
        return "late"
    if work_log.arrived_early_minutes > 0:
        return "early"
    if work_log.first_seen_at:
        return "on_time"
    return "not_checked_in"


def reliability_score(work_log: AgentWorkLog | None) -> int:
    if not work_log or not work_log.first_seen_at:
        return 0

    score = 100
    score -= min(40, work_log.arrived_late_minutes)

    total_tracked = work_log.total_on_site_minutes + work_log.total_idle_minutes
    if total_tracked:
        idle_ratio = work_log.total_idle_minutes / total_tracked
        score -= int(min(30, idle_ratio * 30))

    if geofence_status(work_log) == "outside":
        score -= 15

    return max(0, min(100, score))


def presence_summary(work_log: AgentWorkLog | None) -> dict:
    status = geofence_status(work_log) if work_log else "unknown"
    checked_in = bool(work_log and work_log.first_seen_at)
    completed_day = bool(work_log and work_log.work_date < timezone.localdate())
    checked_out = bool(
        checked_in
        and work_log.last_seen_at
        and (status == "outside" or completed_day)
    )
    return {
        "checked_in": checked_in,
        "checked_out": checked_out,
        "check_in_at": work_log.first_seen_at if work_log else None,
        "check_out_at": work_log.last_seen_at if checked_out else None,
        "geofence_status": status,
        "lateness_status": lateness_status(work_log),
        "reliability_score": reliability_score(work_log),
    }


def attach_presence_summaries(work_logs) -> list[AgentWorkLog]:
    logs = list(work_logs)
    for work_log in logs:
        work_log.presence = presence_summary(work_log)
    return logs


def dashboard_kpis(work_logs) -> dict:
    logs = list(work_logs)
    present = [log for log in logs if log.first_seen_at]
    scores = [reliability_score(log) for log in present]
    inside_count = sum(1 for log in present if geofence_status(log) == "inside")
    late_count = sum(1 for log in present if log.arrived_late_minutes > 0)
    return {
        "present_count": len(present),
        "late_count": late_count,
        "inside_count": inside_count,
        "total_on_site_minutes": sum(log.total_on_site_minutes for log in logs),
        "total_idle_minutes": sum(log.total_idle_minutes for log in logs),
        "average_reliability_score": int(sum(scores) / len(scores)) if scores else 0,
    }


def permitted_work_logs_for_export(request, business, from_date: date, to_date: date) -> QuerySet:
    selected_agent_id = request.GET.get("agent")
    qs = AgentWorkLog.objects.filter(
        business=business,
        work_date__gte=from_date,
        work_date__lte=to_date,
    ).select_related("agent", "location")

    if user_can_manage_timelogs(request.user, business):
        if selected_agent_id and selected_agent_id != "all":
            qs = qs.filter(agent_id=selected_agent_id)
        return qs.order_by("work_date", "agent__username")

    return qs.filter(agent=request.user).order_by("work_date")

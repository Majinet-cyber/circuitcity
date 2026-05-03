from __future__ import annotations

from datetime import date, datetime, time

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


def _display_name(user) -> str:
    return user.get_full_name() or user.username


def _minutes_between(start, end) -> int:
    if not start or not end:
        return 0
    return max(0, int((end - start).total_seconds() // 60))


def format_minutes(minutes: int | None) -> str:
    minutes = int(minutes or 0)
    hours, remainder = divmod(minutes, 60)
    if hours and remainder:
        return f"{hours}h {remainder}m"
    if hours:
        return f"{hours}h"
    return f"{remainder}m"


def _default_scheduled_start(work_log: AgentWorkLog | None) -> time:
    return work_log.scheduled_start if work_log and work_log.scheduled_start else time(8, 0)


def _late_minutes(work_log: AgentWorkLog | None, grace_minutes: int = 15) -> int:
    if not work_log or not work_log.first_seen_at:
        return 0

    scheduled_start = _default_scheduled_start(work_log)
    scheduled_dt = timezone.make_aware(datetime.combine(work_log.work_date, scheduled_start))
    grace_dt = scheduled_dt + timezone.timedelta(minutes=grace_minutes)
    check_in = timezone.localtime(work_log.first_seen_at)
    if check_in <= grace_dt:
        return 0
    return int((check_in - grace_dt).total_seconds() // 60)


def inferred_check_out_at(work_log: AgentWorkLog | None, selected_date: date | None = None):
    if not work_log or not work_log.first_seen_at or not work_log.last_seen_at:
        return None

    selected_date = selected_date or work_log.work_date
    ping = latest_ping(work_log)
    if selected_date < timezone.localdate():
        return work_log.last_seen_at
    if ping and not ping.is_inside_geofence:
        return work_log.last_seen_at
    return None


def attendance_row(agent, work_log: AgentWorkLog | None, selected_date: date) -> dict:
    check_in_at = work_log.first_seen_at if work_log else None
    check_out_at = inferred_check_out_at(work_log, selected_date)
    late_minutes = _late_minutes(work_log)
    ping = latest_ping(work_log) if work_log else None

    if not check_in_at:
        shift_status = "not_checked_in"
        shift_label = "No Checkout"
    elif check_out_at:
        shift_status = "checked_out"
        shift_label = "Checked Out"
    elif selected_date == timezone.localdate():
        shift_status = "active"
        shift_label = "Active"
    else:
        shift_status = "no_checkout"
        shift_label = "No Checkout"

    if not ping:
        geo_status = "unknown"
        geo_label = "No GPS"
    elif ping.is_inside_geofence:
        geo_status = "inside"
        geo_label = "Inside Zone"
    else:
        geo_status = "outside"
        geo_label = "Outside Zone"

    span_minutes = _minutes_between(check_in_at, check_out_at or (work_log.last_seen_at if work_log else None))
    worked_minutes = work_log.effective_work_minutes if work_log and work_log.effective_work_minutes else span_minutes
    if work_log and work_log.total_on_site_minutes:
        worked_minutes = max(worked_minutes, work_log.total_on_site_minutes)

    return {
        "agent": agent,
        "agent_name": _display_name(agent),
        "work_log": work_log,
        "check_in_at": check_in_at,
        "check_out_at": check_out_at,
        "worked_minutes": worked_minutes,
        "worked_label": format_minutes(worked_minutes),
        "idle_minutes": work_log.total_idle_minutes if work_log else 0,
        "idle_label": format_minutes(work_log.total_idle_minutes if work_log else 0),
        "shift_status": shift_status,
        "shift_label": shift_label,
        "late_minutes": late_minutes,
        "late_status": "late" if late_minutes > 0 else ("on_time" if check_in_at else "not_checked_in"),
        "late_label": f"Late {late_minutes}m" if late_minutes > 0 else ("On Time" if check_in_at else "-"),
        "geo_status": geo_status,
        "geo_label": geo_label,
        "location_label": work_log.location.name if work_log and work_log.location else "-",
        "reliability_score": reliability_score(work_log),
        "notes": "No GPS captured" if not ping and check_in_at else "",
    }


def attendance_rows_for_agents(agents, work_logs, selected_date: date) -> list[dict]:
    logs_by_agent = {log.agent_id: log for log in work_logs}
    return [attendance_row(agent, logs_by_agent.get(agent.id), selected_date) for agent in agents]


def attendance_kpis(rows: list[dict]) -> dict:
    present = [row for row in rows if row["check_in_at"]]
    return {
        "present_count": len(present),
        "late_count": sum(1 for row in rows if row["late_status"] == "late"),
        "active_count": sum(1 for row in rows if row["shift_status"] == "active"),
        "completed_count": sum(1 for row in rows if row["shift_status"] == "checked_out"),
        "total_worked_minutes": sum(row["worked_minutes"] for row in rows),
        "total_worked_label": format_minutes(sum(row["worked_minutes"] for row in rows)),
        "total_idle_minutes": sum(row["idle_minutes"] for row in rows),
        "total_idle_label": format_minutes(sum(row["idle_minutes"] for row in rows)),
        "average_reliability_score": int(sum(row["reliability_score"] for row in present) / len(present)) if present else 0,
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

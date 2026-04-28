# hq/views_bugmonitor.py
"""
Bug Monitor views for HQ Admin.
All views require HQ admin access. Stack traces additionally require can_view_stack_traces.
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from hq.models_bugmonitor import AdminAuditLog, IssueStatus, IssueSeverity, SystemIssue, SystemIssueOccurrence
from hq.permissions import hq_admin_required

User = get_user_model()


def _can_view_stack_traces(user) -> bool:
    return user.is_superuser or user.has_perm("hq.can_view_stack_traces")


def _can_manage_bugs(user) -> bool:
    return user.is_superuser or user.has_perm("hq.can_manage_bug_status")


def _can_assign_bugs(user) -> bool:
    return user.is_superuser or user.has_perm("hq.can_assign_bugs")


# ---------------------------------------------------------------------------
# Bug list
# ---------------------------------------------------------------------------

@hq_admin_required
def bugs_list(request):
    qs = SystemIssue.objects.select_related("user", "business", "assigned_to", "cleared_by")

    # --- Filters ---
    status_filter   = request.GET.get("status", "")
    severity_filter = request.GET.get("severity", "")
    code_filter     = request.GET.get("status_code", "")
    path_filter     = request.GET.get("path", "")
    recurring_only  = request.GET.get("recurring", "")
    date_from       = request.GET.get("date_from", "")
    date_to         = request.GET.get("date_to", "")

    if status_filter:
        qs = qs.filter(status=status_filter)
    else:
        # Default: hide ignored
        qs = qs.exclude(status=IssueStatus.IGNORED)

    if severity_filter:
        qs = qs.filter(severity=severity_filter)
    if code_filter:
        try:
            qs = qs.filter(status_code=int(code_filter))
        except ValueError:
            pass
    if path_filter:
        qs = qs.filter(path__icontains=path_filter)
    if recurring_only:
        qs = qs.filter(occurrence_count__gt=1)
    if date_from:
        try:
            from datetime import datetime
            qs = qs.filter(last_seen_at__date__gte=datetime.fromisoformat(date_from).date())
        except Exception:
            pass
    if date_to:
        try:
            from datetime import datetime
            qs = qs.filter(last_seen_at__date__lte=datetime.fromisoformat(date_to).date())
        except Exception:
            pass

    # Summary counts for cards
    today = timezone.now().date()
    open_count     = SystemIssue.objects.filter(status__in=[IssueStatus.NEW, IssueStatus.INVESTIGATING]).count()
    critical_count = SystemIssue.objects.filter(severity=IssueSeverity.CRITICAL, status__in=[IssueStatus.NEW, IssueStatus.INVESTIGATING]).count()
    new_today      = SystemIssue.objects.filter(first_seen_at__date=today).count()
    recurring_count = SystemIssue.objects.filter(occurrence_count__gt=1, status__in=[IssueStatus.NEW, IssueStatus.INVESTIGATING]).count()
    errors_500_today = SystemIssue.objects.filter(status_code=500, last_seen_at__date=today).count()

    from datetime import timedelta
    week_start = today - timedelta(days=7)
    cleared_week = SystemIssue.objects.filter(status=IssueStatus.CLEARED, cleared_at__date__gte=week_start).count()

    context = {
        "issues": qs[:200],
        "status_choices": IssueStatus.choices,
        "severity_choices": IssueSeverity.choices,
        # Filter state
        "status_filter":   status_filter,
        "severity_filter": severity_filter,
        "code_filter":     code_filter,
        "path_filter":     path_filter,
        "recurring_only":  recurring_only,
        "date_from":       date_from,
        "date_to":         date_to,
        # Cards
        "open_count":      open_count,
        "critical_count":  critical_count,
        "new_today":       new_today,
        "recurring_count": recurring_count,
        "errors_500_today": errors_500_today,
        "cleared_week":    cleared_week,
        # Permissions
        "can_manage_bugs": _can_manage_bugs(request.user),
        "can_assign_bugs": _can_assign_bugs(request.user),
    }
    return render(request, "hq/bugs_list.html", context)


# ---------------------------------------------------------------------------
# Bug detail
# ---------------------------------------------------------------------------

@hq_admin_required
def bug_detail(request, pk):
    issue = get_object_or_404(
        SystemIssue.objects.select_related("user", "business", "assigned_to", "cleared_by"),
        pk=pk,
    )
    occurrences = issue.occurrences.select_related("user", "business").order_by("-occurred_at")[:50]
    audit_entries = AdminAuditLog.objects.filter(
        target_model="SystemIssue", target_id=str(pk)
    ).select_related("actor").order_by("-created_at")[:50]

    can_view_trace = _can_view_stack_traces(request.user)

    # Admins for assignment dropdown
    admin_users = User.objects.filter(
        is_staff=True
    ).order_by("username")[:100]

    context = {
        "issue":         issue,
        "occurrences":   occurrences,
        "audit_entries": audit_entries,
        "can_view_stack_traces": can_view_trace,
        "can_manage_bugs": _can_manage_bugs(request.user),
        "can_assign_bugs": _can_assign_bugs(request.user),
        "admin_users":   admin_users,
        "status_choices": IssueStatus.choices,
        "severity_choices": IssueSeverity.choices,
    }
    return render(request, "hq/bug_detail.html", context)


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

@hq_admin_required
@require_POST
def bug_action(request, pk):
    """Handle bulk actions: mark_investigating, mark_cleared, mark_ignored, assign, escalate, add_note."""
    if not _can_manage_bugs(request.user):
        messages.error(request, "You don't have permission to manage bug status.")
        return redirect("hq:bug_detail", pk=pk)

    issue = get_object_or_404(SystemIssue, pk=pk)
    action = request.POST.get("action", "")

    if action == "mark_investigating":
        old_status = issue.status
        issue.status = IssueStatus.INVESTIGATING
        issue.save(update_fields=["status", "updated_at"])
        AdminAuditLog.record(
            request.user, "bug_status_changed",
            target=issue, before={"status": old_status}, after={"status": issue.status}, request=request,
        )
        messages.success(request, "Issue marked as Investigating.")

    elif action == "mark_cleared":
        notes = request.POST.get("resolution_notes", "")
        old_status = issue.status
        issue.mark_cleared(request.user, notes=notes)
        AdminAuditLog.record(
            request.user, "bug_cleared",
            target=issue, before={"status": old_status}, after={"status": IssueStatus.CLEARED}, request=request,
        )
        messages.success(request, "Issue marked as Cleared.")

    elif action == "mark_ignored":
        old_status = issue.status
        issue.status = IssueStatus.IGNORED
        issue.save(update_fields=["status", "updated_at"])
        AdminAuditLog.record(
            request.user, "bug_status_changed",
            target=issue, before={"status": old_status}, after={"status": IssueStatus.IGNORED}, request=request,
        )
        messages.success(request, "Issue ignored.")

    elif action == "assign":
        if not _can_assign_bugs(request.user):
            messages.error(request, "You don't have permission to assign bugs.")
            return redirect("hq:bug_detail", pk=pk)
        assignee_id = request.POST.get("assignee_id")
        old_assignee = str(issue.assigned_to_id or "")
        if assignee_id:
            try:
                assignee = User.objects.get(pk=assignee_id, is_staff=True)
                issue.assigned_to = assignee
                issue.save(update_fields=["assigned_to", "updated_at"])
                AdminAuditLog.record(
                    request.user, "bug_assigned",
                    target=issue, before={"assigned_to": old_assignee},
                    after={"assigned_to": str(assignee.pk)}, request=request,
                )
                messages.success(request, f"Issue assigned to {assignee.username}.")
            except User.DoesNotExist:
                messages.error(request, "Assignee not found.")
        else:
            issue.assigned_to = None
            issue.save(update_fields=["assigned_to", "updated_at"])
            messages.success(request, "Assignment cleared.")

    elif action == "assign_to_me":
        if not _can_assign_bugs(request.user):
            messages.error(request, "You don't have permission to assign bugs.")
            return redirect("hq:bug_detail", pk=pk)
        old_assignee = str(issue.assigned_to_id or "")
        issue.assigned_to = request.user
        issue.save(update_fields=["assigned_to", "updated_at"])
        AdminAuditLog.record(
            request.user, "bug_assigned",
            target=issue, before={"assigned_to": old_assignee},
            after={"assigned_to": str(request.user.pk)}, request=request,
        )
        messages.success(request, "Assigned to you.")

    elif action == "escalate":
        sev_order = [IssueSeverity.LOW, IssueSeverity.MEDIUM, IssueSeverity.HIGH, IssueSeverity.CRITICAL]
        old_sev = issue.severity
        try:
            idx = sev_order.index(issue.severity)
            if idx < len(sev_order) - 1:
                issue.severity = sev_order[idx + 1]
                issue.save(update_fields=["severity", "updated_at"])
                AdminAuditLog.record(
                    request.user, "severity_changed",
                    target=issue, before={"severity": old_sev}, after={"severity": issue.severity}, request=request,
                )
                messages.success(request, f"Severity escalated to {issue.get_severity_display()}.")
            else:
                messages.info(request, "Already at Critical severity.")
        except ValueError:
            pass

    elif action == "add_note":
        note = request.POST.get("note", "").strip()
        if note:
            issue.notes = (issue.notes + "\n\n" + note).strip()
            issue.save(update_fields=["notes", "updated_at"])
            AdminAuditLog.record(
                request.user, "bug_note_added", target=issue,
                after={"note": note[:500]}, request=request,
            )
            messages.success(request, "Note added.")

    return redirect("hq:bug_detail", pk=pk)


# ---------------------------------------------------------------------------
# Bulk actions (from list)
# ---------------------------------------------------------------------------

@hq_admin_required
@require_POST
def bug_bulk_action(request):
    if not _can_manage_bugs(request.user):
        messages.error(request, "You don't have permission to manage bugs.")
        return redirect("hq:bugs_list")

    action = request.POST.get("action", "")
    ids = request.POST.getlist("issue_ids")
    if not ids:
        messages.warning(request, "No issues selected.")
        return redirect("hq:bugs_list")

    issues = SystemIssue.objects.filter(pk__in=ids)

    if action == "mark_cleared":
        for issue in issues:
            if issue.status != IssueStatus.CLEARED:
                issue.mark_cleared(request.user)
        messages.success(request, f"{issues.count()} issues marked cleared.")

    elif action == "mark_ignored":
        issues.update(status=IssueStatus.IGNORED)
        messages.success(request, f"Issues ignored.")

    elif action == "mark_investigating":
        issues.update(status=IssueStatus.INVESTIGATING)
        messages.success(request, f"Issues marked as Investigating.")

    return redirect("hq:bugs_list")


# ---------------------------------------------------------------------------
# Audit log list
# ---------------------------------------------------------------------------

@hq_admin_required
def audit_log(request):
    if not (request.user.is_superuser or request.user.has_perm("hq.can_view_audit_logs")):
        messages.error(request, "You don't have permission to view audit logs.")
        return redirect("hq:dashboard")

    qs = AdminAuditLog.objects.select_related("actor").order_by("-created_at")

    action_filter = request.GET.get("action", "")
    actor_filter  = request.GET.get("actor", "")
    date_from     = request.GET.get("date_from", "")

    if action_filter:
        qs = qs.filter(action__icontains=action_filter)
    if actor_filter:
        qs = qs.filter(actor__username__icontains=actor_filter)
    if date_from:
        try:
            from datetime import datetime
            qs = qs.filter(created_at__date__gte=datetime.fromisoformat(date_from).date())
        except Exception:
            pass

    context = {
        "entries":       qs[:500],
        "action_filter": action_filter,
        "actor_filter":  actor_filter,
        "date_from":     date_from,
    }
    return render(request, "hq/audit_log.html", context)

# hq/views_accounts.py
"""
HQ Admin Accounts management: view, assign roles, activate/deactivate accounts.
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from hq.models_bugmonitor import AdminAuditLog
from hq.permissions import hq_admin_required

User = get_user_model()

_ROLE_CHANGE_ACTIONS = ["role_assigned", "account_activated", "account_deactivated", "admin_role_changed"]


def _can_manage_roles(user) -> bool:
    return user.is_superuser or user.has_perm("hq.can_manage_admin_roles")


# ---------------------------------------------------------------------------
# Account list
# ---------------------------------------------------------------------------

@hq_admin_required
def accounts_list(request):
    qs = User.objects.filter(is_staff=True).prefetch_related("groups").order_by("username")

    q = request.GET.get("q", "")
    group_filter = request.GET.get("group", "")

    if q:
        qs = qs.filter(username__icontains=q) | User.objects.filter(email__icontains=q, is_staff=True)
    if group_filter:
        qs = qs.filter(groups__name=group_filter)

    groups = Group.objects.all().order_by("name")
    context = {
        "accounts":       qs.distinct()[:200],
        "groups":         groups,
        "q":              q,
        "group_filter":   group_filter,
        "can_manage_roles": _can_manage_roles(request.user),
    }
    return render(request, "hq/accounts.html", context)


# ---------------------------------------------------------------------------
# Account detail / role assignment
# ---------------------------------------------------------------------------

@hq_admin_required
def account_detail(request, user_id):
    account = get_object_or_404(User, pk=user_id, is_staff=True)
    groups = Group.objects.all().order_by("name")
    audit_entries = AdminAuditLog.objects.filter(
        target_model="User", target_id=str(user_id)
    ).select_related("actor").order_by("-created_at")[:50]

    context = {
        "account":        account,
        "groups":         groups,
        "audit_entries":  audit_entries,
        "can_manage_roles": _can_manage_roles(request.user),
    }
    return render(request, "hq/account_detail.html", context)


# ---------------------------------------------------------------------------
# Role assignment action
# ---------------------------------------------------------------------------

@hq_admin_required
@require_POST
def account_assign_groups(request, user_id):
    if not _can_manage_roles(request.user):
        messages.error(request, "You don't have permission to manage roles.")
        return redirect("hq:accounts_list")

    account = get_object_or_404(User, pk=user_id, is_staff=True)

    # Safety: prevent self-demotion for non-superusers
    if account == request.user and not request.user.is_superuser:
        messages.error(request, "You cannot change your own roles.")
        return redirect("hq:account_detail", user_id=user_id)

    # Prevent privilege escalation: only superuser can grant superuser rights
    make_superuser = request.POST.get("is_superuser") == "1"
    if make_superuser and not request.user.is_superuser:
        messages.error(request, "Only superusers can grant superuser status.")
        return redirect("hq:account_detail", user_id=user_id)

    old_groups = list(account.groups.values_list("name", flat=True))
    new_group_ids = request.POST.getlist("groups")
    new_groups = Group.objects.filter(pk__in=new_group_ids)

    account.groups.set(new_groups)

    if make_superuser and not account.is_superuser:
        account.is_superuser = True
        account.save(update_fields=["is_superuser"])
    elif not make_superuser and account.is_superuser and request.user.is_superuser:
        account.is_superuser = False
        account.save(update_fields=["is_superuser"])

    new_group_names = list(account.groups.values_list("name", flat=True))

    AdminAuditLog.record(
        request.user, "admin_role_changed",
        target=account,
        before={"groups": old_groups},
        after={"groups": new_group_names},
        request=request,
    )
    messages.success(request, f"Roles updated for {account.username}.")
    return redirect("hq:account_detail", user_id=user_id)


# ---------------------------------------------------------------------------
# Activate / deactivate account
# ---------------------------------------------------------------------------

@hq_admin_required
@require_POST
def account_toggle_active(request, user_id):
    if not _can_manage_roles(request.user):
        messages.error(request, "You don't have permission to manage accounts.")
        return redirect("hq:accounts_list")

    account = get_object_or_404(User, pk=user_id)

    if account == request.user:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect("hq:account_detail", user_id=user_id)

    old_state = account.is_active
    account.is_active = not account.is_active
    account.save(update_fields=["is_active"])

    action = "account_activated" if account.is_active else "account_deactivated"
    AdminAuditLog.record(
        request.user, action,
        target=account,
        before={"is_active": old_state},
        after={"is_active": account.is_active},
        request=request,
    )
    state_label = "activated" if account.is_active else "deactivated"
    messages.success(request, f"Account {account.username} {state_label}.")
    return redirect("hq:account_detail", user_id=user_id)

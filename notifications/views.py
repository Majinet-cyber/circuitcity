# notifications/views.py
"""
Views for managing user notifications.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_POST

from .models import (
    BusinessEmailRecipient,
    DailySummarySettings,
    Notification,
)


@login_required
def notification_list(request):
    """Full page listing all notifications for the current user."""
    notifications = Notification.objects.filter(user=request.user)

    # Filter by read/unread
    filter_type = request.GET.get("filter", "all")
    if filter_type == "unread":
        notifications = notifications.filter(read_at__isnull=True)
    elif filter_type == "read":
        notifications = notifications.filter(read_at__isnull=False)

    paginator = Paginator(notifications, 20)
    page = request.GET.get("page", 1)
    notifications_page = paginator.get_page(page)

    return render(
        request,
        "notifications/notification_list.html",
        {
            "notifications": notifications_page,
            "filter_type": filter_type,
        },
    )


@login_required
def notification_dropdown(request):
    """API endpoint for the notification dropdown (latest 10)."""
    notifications = Notification.objects.filter(user=request.user)[:10]
    unread_count = Notification.objects.filter(user=request.user, read_at__isnull=True).count()

    data = {
        "unread_count": unread_count,
        "notifications": [
            {
                "id": n.id,
                "message": n.message,
                "level": n.level,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat(),
                "meta": n.meta,
            }
            for n in notifications
        ],
    }

    return JsonResponse(data)


@login_required
def mark_as_read(request, pk):
    """Mark a single notification as read."""
    try:
        notification = Notification.objects.get(pk=pk, user=request.user)
        notification.mark_read()
    except Notification.DoesNotExist:
        pass

    return redirect(request.META.get("HTTP_REFERER", "notifications:list"))


@login_required
def mark_all_as_read(request):
    """Mark all user's notifications as read."""
    from django.utils import timezone

    Notification.objects.filter(user=request.user, read_at__isnull=True).update(read_at=timezone.now())

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"success": True})

    return redirect("notifications:list")


@login_required
def mark_read_and_redirect(request, pk):
    """
    Mark a notification as read and redirect to its deep link or dashboard.
    Used for notification bell dropdown clicks.
    """
    try:
        notification = Notification.objects.get(pk=pk, user=request.user)
        notification.mark_read()

        # Check if notification has a deep link in meta
        deep_link = notification.meta.get("link") if notification.meta else None
        if deep_link:
            return redirect(deep_link)
    except Notification.DoesNotExist:
        pass

    # Default: redirect to dashboard
    try:
        from django.urls import reverse

        return redirect(reverse("dashboard:home"))
    except Exception:
        return redirect("/")


# ==============================================================================
# Daily Summary Settings UI
# ==============================================================================

def _get_manager_business(request: HttpRequest):
    """
    Return the active Business for the request, or None if not found.
    Uses the same resolution chain as other views in this project.
    """
    from tenants.utils import get_active_business
    return get_active_business(request)


def _is_manager_of(request: HttpRequest, business) -> bool:
    """
    Return True if the current user holds a MANAGER membership for ``business``.
    Also returns True if the user is staff (Django admin).
    """
    if not business:
        return False
    if request.user.is_staff:
        return True
    from tenants.models import Membership
    return Membership.objects.filter(
        user=request.user,
        business=business,
        role="MANAGER",
        status="ACTIVE",
    ).exists()


@login_required
def daily_summary_settings(request: HttpRequest) -> HttpResponse:
    """
    Manager-facing page to configure the daily summary email.

    Handles three POST actions via a hidden ``action`` field:
      - ``save_settings``    — update is_enabled / send_hour / timezone
      - ``add_recipient``    — add a new BusinessEmailRecipient
    """
    business = _get_manager_business(request)
    if not business or not _is_manager_of(request, business):
        messages.error(request, "You do not have permission to manage daily summary settings.")
        return redirect("/")

    ds = DailySummarySettings.for_business(business)
    recipients = BusinessEmailRecipient.objects.filter(business=business).order_by("email")

    if request.method == "POST":
        action = request.POST.get("action", "save_settings")

        if action == "save_settings":
            ds.is_enabled = request.POST.get("is_enabled") == "on"
            send_hour_raw = request.POST.get("send_hour", "7")
            try:
                ds.send_hour = max(0, min(23, int(send_hour_raw)))
            except (ValueError, TypeError):
                ds.send_hour = 7
            tz = request.POST.get("timezone", "Africa/Blantyre").strip()
            valid_tz_values = [t[0] for t in DailySummarySettings._meta.get_field("timezone").choices]
            if tz in valid_tz_values:
                ds.timezone = tz
            ds.save()
            messages.success(request, "Daily summary settings saved.")

        elif action == "add_recipient":
            email = request.POST.get("email", "").strip().lower()
            name = request.POST.get("name", "").strip()
            if email:
                obj, created = BusinessEmailRecipient.objects.get_or_create(
                    business=business,
                    email=email,
                    defaults={"name": name, "is_active": True},
                )
                if not created:
                    obj.is_active = True
                    obj.name = name or obj.name
                    obj.save(update_fields=["is_active", "name"])
                messages.success(request, f"Recipient {email} added.")
            else:
                messages.error(request, "Please enter a valid email address.")

        return redirect("notifications:daily_summary_settings")

    return render(
        request,
        "notifications/daily_summary_settings.html",
        {
            "ds": ds,
            "recipients": recipients,
            "business": business,
            "send_hour_choices": list(DailySummarySettings._meta.get_field("send_hour").choices),
            "timezone_choices": list(DailySummarySettings._meta.get_field("timezone").choices),
        },
    )


@login_required
@require_POST
def daily_summary_recipient_remove(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Deactivate (soft-remove) a daily summary recipient for the current business.
    Uses is_active=False so the row is preserved in history but skipped on send.
    """
    business = _get_manager_business(request)
    if not business or not _is_manager_of(request, business):
        messages.error(request, "Permission denied.")
        return redirect("/")

    recipient = get_object_or_404(BusinessEmailRecipient, pk=pk, business=business)
    recipient.is_active = False
    recipient.save(update_fields=["is_active"])
    messages.success(request, f"{recipient.email} removed from daily summary recipients.")
    return redirect("notifications:daily_summary_settings")

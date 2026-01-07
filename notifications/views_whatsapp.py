# notifications/views_whatsapp.py
"""
Views for managing WhatsApp notification preferences.
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST

from .models import WhatsAppPreference
from . import whatsapp_service


@login_required
def whatsapp_settings(request: HttpRequest) -> HttpResponse:
    """
    Manage WhatsApp notification preferences.
    """
    user = request.user

    # Get or create preference
    try:
        pref = WhatsAppPreference.objects.get(user=user)
    except WhatsAppPreference.DoesNotExist:
        pref = WhatsAppPreference(user=user, phone_number="", is_enabled=False)

    if request.method == "POST":
        # Update preferences
        phone = request.POST.get("phone_number", "").strip()
        is_enabled = request.POST.get("is_enabled") == "on"
        receive_sale_alerts = request.POST.get("receive_sale_alerts") == "on"
        receive_profit_milestones = request.POST.get("receive_profit_milestones") == "on"
        receive_low_stock_alerts = request.POST.get("receive_low_stock_alerts") == "on"
        receive_commission_alerts = request.POST.get("receive_commission_alerts") == "on"

        # Normalize phone number
        if phone and is_enabled:
            phone = whatsapp_service.normalize_phone_number(phone)

        # Update or create
        pref.phone_number = phone
        pref.is_enabled = is_enabled
        pref.receive_sale_alerts = receive_sale_alerts
        pref.receive_profit_milestones = receive_profit_milestones
        pref.receive_low_stock_alerts = receive_low_stock_alerts
        pref.receive_commission_alerts = receive_commission_alerts

        pref.save()

        messages.success(request, "WhatsApp notification preferences updated.")
        return redirect(request.path)

    return render(
        request,
        "notifications/whatsapp_settings.html",
        {
            "pref": pref,
            "whatsapp_configured": whatsapp_service.is_whatsapp_configured(),
        },
    )


@login_required
@require_POST
def whatsapp_test(request: HttpRequest) -> HttpResponse:
    """
    Send a test WhatsApp message.
    """
    user = request.user

    try:
        pref = WhatsAppPreference.objects.get(user=user, is_enabled=True)
    except WhatsAppPreference.DoesNotExist:
        messages.error(request, "WhatsApp notifications are not enabled.")
        return redirect("notifications:whatsapp_settings")

    # Send test message
    success = whatsapp_service.send_whatsapp_message(
        pref.phone_number,
        f"✅ Test message from Emajinet\n\nHello {user.first_name or user.username}! WhatsApp notifications are working correctly.",
    )

    if success:
        messages.success(request, "Test message sent! Check your WhatsApp.")
    else:
        messages.error(request, "Failed to send test message. Check your phone number and try again.")

    return redirect("notifications:whatsapp_settings")

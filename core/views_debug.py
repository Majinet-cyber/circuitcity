"""
Debug views for internal testing and diagnostics.

These views are restricted to staff/superuser only and should not be
accessible to regular users.
"""
from __future__ import annotations

import json
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


def app_version_view(request: HttpRequest) -> JsonResponse:
    """
    Return the current app version as JSON.
    Public endpoint - no authentication required.
    """
    return JsonResponse({"version": getattr(settings, "APP_VERSION", "1.1.0")})


@login_required
@require_http_methods(["GET", "POST"])
def whatsapp_test(request: HttpRequest) -> HttpResponse:
    """
    Debug view to test sending WhatsApp messages.
    
    Restricted to staff/superuser only.
    """
    # Restrict to staff/superuser
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponse("Access denied: staff only", status=403)
    
    # Get env vars for display (safely)
    import os
    whatsapp_token = os.environ.get("WHATSAPP_TOKEN", "")
    whatsapp_phone_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
    
    context = {
        "success": False,
        "error": None,
        "response_data": None,
        "to_number": getattr(settings, "DEBUG_WHATSAPP_TO_NUMBER", ""),
        "WHATSAPP_TOKEN": whatsapp_token,
        "WHATSAPP_PHONE_NUMBER_ID": whatsapp_phone_id,
    }
    
    if request.method == "POST":
        to_number = request.POST.get("to_number", "").strip()
        
        if not to_number:
            context["error"] = "Phone number is required"
        else:
            try:
                # Import here to avoid import errors if module doesn't exist
                from notifications.whatsapp import send_whatsapp_text
                
                # Send test message
                response = send_whatsapp_text(
                    to_number,
                    "Emajinet test: your WhatsApp integration is live ✅"
                )
                
                context["success"] = True
                context["response_data"] = json.dumps(response, indent=2)
                logger.info(f"WhatsApp test message sent to {to_number}")
                
            except ImportError as e:
                context["error"] = f"WhatsApp module not found: {e}"
                logger.error(f"WhatsApp module import error: {e}")
            except Exception as e:
                context["error"] = str(e)
                logger.error(f"WhatsApp test error: {e}")
            
            context["to_number"] = to_number
    
    return render(request, "core/debug_whatsapp_test.html", context)


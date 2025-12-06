# wallet/views_admin.py
"""
Admin-specific wallet views for commission and cost management.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

try:
    from tenants.utils import get_active_business
except ImportError:
    def get_active_business(request):
        return None

try:
    from accounts.decorators import otp_required
except ImportError:
    def otp_required(func):
        return func


def _is_manager(user) -> bool:
    """Check if user is manager/staff."""
    try:
        return bool(user.is_authenticated and (user.is_staff or user.profile.is_manager))
    except Exception:
        return bool(user.is_authenticated and user.is_staff)


@otp_required
@require_POST
@login_required
def update_commission_config(request: HttpRequest):
    """
    Update the phone commission percentage for the active business.
    
    POST params:
        - commission_pct: Decimal value between 0-100
        
    Returns:
        JSON response with success/error
    """
    if not _is_manager(request.user):
        return JsonResponse({
            "ok": False,
            "error": "Access denied. Only managers can update commission config."
        }, status=403)
    
    business = get_active_business(request)
    if not business:
        return JsonResponse({
            "ok": False,
            "error": "No active business selected."
        }, status=400)
    
    try:
        commission_pct_str = request.POST.get("commission_pct", "").strip()
        if not commission_pct_str:
            return JsonResponse({
                "ok": False,
                "error": "Commission percentage is required."
            }, status=400)
        
        commission_pct = Decimal(commission_pct_str)
        
        if not (0 <= commission_pct <= 100):
            return JsonResponse({
                "ok": False,
                "error": "Commission percentage must be between 0 and 100."
            }, status=400)
        
        # Update commission config
        from tenants.utils_commission import update_commission_percentage
        
        success = update_commission_percentage(
            business=business,
            new_pct=commission_pct,
            updated_by=request.user
        )
        
        if success:
            messages.success(
                request,
                f"Commission percentage updated to {commission_pct}% for {business.name}."
            )
            return JsonResponse({
                "ok": True,
                "commission_pct": float(commission_pct),
                "message": f"Commission updated to {commission_pct}%"
            })
        else:
            return JsonResponse({
                "ok": False,
                "error": "Failed to update commission percentage."
            }, status=500)
            
    except (InvalidOperation, ValueError) as e:
        return JsonResponse({
            "ok": False,
            "error": f"Invalid commission percentage: {e}"
        }, status=400)
    except Exception as e:
        return JsonResponse({
            "ok": False,
            "error": f"Error updating commission: {e}"
        }, status=500)


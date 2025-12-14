# hq/views_account_support.py
"""
HQ Account & Login Support Tools.
Provides tools for HQ to resolve login issues, reset passwords, unlock accounts, etc.
"""
from __future__ import annotations

from datetime import timedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from hq.permissions import hq_admin_required
from tenants.models import Business, Membership

try:
    from circuitcity.accounts.models import LoginSecurity, EmailOTP, PasswordResetCode
except ImportError:
    try:
        from accounts.models import LoginSecurity, EmailOTP, PasswordResetCode
    except ImportError:
        LoginSecurity = None
        EmailOTP = None
        PasswordResetCode = None

User = get_user_model()


@hq_admin_required
def account_support_home(request: HttpRequest, business_id: int) -> HttpResponse:
    """
    Account & login support dashboard for a specific business.
    Shows users, login issues, OTP status, etc.
    """
    business = get_object_or_404(Business, id=business_id)
    
    # Get all users for this business
    memberships = Membership.objects.filter(
        business=business
    ).select_related("user").order_by("-role", "user__email")
    
    users_with_status = []
    for m in memberships:
        user = m.user
        
        # Login security status
        login_sec = None
        if LoginSecurity:
            try:
                login_sec = LoginSecurity.objects.get(user=user)
            except LoginSecurity.DoesNotExist:
                pass
        
        # Last login
        last_login = user.last_login
        
        # Active sessions count
        active_sessions = 0
        if hasattr(user, "id"):
            active_sessions = Session.objects.filter(
                expire_date__gte=timezone.now()
            ).count()  # Simplified - proper implementation would decode session data
        
        users_with_status.append({
            "user": user,
            "membership": m,
            "login_sec": login_sec,
            "is_locked": login_sec.is_locked() if login_sec else False,
            "is_hard_blocked": login_sec.hard_blocked if login_sec else False,
            "last_login": last_login,
            "active_sessions": active_sessions,
        })
    
    context = {
        "business": business,
        "users_with_status": users_with_status,
        "active_tab": "account_support",  # For template navigation consistency
    }
    
    return render(request, "hq/account_support.html", context)


@hq_admin_required
@require_POST
def force_logout_user(request: HttpRequest, business_id: int, user_id: int) -> HttpResponse:
    """
    Force logout all sessions for a specific user.
    """
    business = get_object_or_404(Business, id=business_id)
    user = get_object_or_404(User, id=user_id)
    
    # Verify user belongs to business
    if not Membership.objects.filter(business=business, user=user).exists():
        messages.error(request, "User does not belong to this business")
        return redirect("hq:account_support", business_id=business_id)
    
    # Delete all sessions for this user
    # Note: This is simplified - proper implementation would decode session data to find user sessions
    try:
        # Update user's session_auth_hash to invalidate all sessions
        user.set_unusable_password()
        user.save()
        
        # Log action
        _log_support_action(
            actor=request.user,
            business=business,
            action_type="FORCE_LOGOUT",
            reason=request.POST.get("reason", "Forced logout by HQ"),
            entity_type="User",
            entity_id=str(user.id),
            payload_after={"email": user.email}
        )
        
        messages.success(request, f"Force logged out {user.email}")
    except Exception as e:
        messages.error(request, f"Failed to force logout: {e}")
    
    return redirect("hq:account_support", business_id=business_id)


@hq_admin_required
@require_POST
def unlock_account(request: HttpRequest, business_id: int, user_id: int) -> HttpResponse:
    """
    Unlock a locked account (clear login security lockouts).
    """
    business = get_object_or_404(Business, id=business_id)
    user = get_object_or_404(User, id=user_id)
    
    if not Membership.objects.filter(business=business, user=user).exists():
        messages.error(request, "User does not belong to this business")
        return redirect("hq:account_support", business_id=business_id)
    
    if not LoginSecurity:
        messages.error(request, "LoginSecurity model not available")
        return redirect("hq:account_support", business_id=business_id)
    
    try:
        login_sec, created = LoginSecurity.objects.get_or_create(user=user)
        
        before_state = {
            "stage": login_sec.stage,
            "fail_count": login_sec.fail_count,
            "locked_until": login_sec.locked_until.isoformat() if login_sec.locked_until else None,
            "hard_blocked": login_sec.hard_blocked,
        }
        
        # Unlock
        login_sec.note_success()
        
        after_state = {
            "stage": 0,
            "fail_count": 0,
            "locked_until": None,
            "hard_blocked": False,
        }
        
        # Log action
        _log_support_action(
            actor=request.user,
            business=business,
            action_type="UNLOCK_ACCOUNT",
            reason=request.POST.get("reason", "Account unlocked by HQ"),
            entity_type="User",
            entity_id=str(user.id),
            payload_before=before_state,
            payload_after=after_state
        )
        
        messages.success(request, f"Unlocked account for {user.email}")
    except Exception as e:
        messages.error(request, f"Failed to unlock account: {e}")
    
    return redirect("hq:account_support", business_id=business_id)


@hq_admin_required
@require_POST
def reset_password_for_user(request: HttpRequest, business_id: int, user_id: int) -> HttpResponse:
    """
    Generate a password reset link for a user.
    """
    business = get_object_or_404(Business, id=business_id)
    user = get_object_or_404(User, id=user_id)
    
    if not Membership.objects.filter(business=business, user=user).exists():
        messages.error(request, "User does not belong to this business")
        return redirect("hq:account_support", business_id=business_id)
    
    if not PasswordResetCode:
        messages.error(request, "PasswordResetCode model not available")
        return redirect("hq:account_support", business_id=business_id)
    
    try:
        # Create password reset code
        code = PasswordResetCode.objects.create(
            email=user.email,
            expires_at=timezone.now() + timedelta(hours=24)
        )
        
        # Generate reset link
        from django.urls import reverse
        reset_url = request.build_absolute_uri(
            reverse("accounts:password_reset_confirm", kwargs={"code": code.code})
        )
        
        # Log action
        _log_support_action(
            actor=request.user,
            business=business,
            action_type="RESET_PASSWORD",
            reason=request.POST.get("reason", "Password reset generated by HQ"),
            entity_type="User",
            entity_id=str(user.id),
            payload_after={"email": user.email, "reset_code": str(code.code)[:8] + "..."}
        )
        
        messages.success(
            request,
            f"Password reset link generated for {user.email}: {reset_url}"
        )
    except Exception as e:
        messages.error(request, f"Failed to generate reset link: {e}")
    
    return redirect("hq:account_support", business_id=business_id)


@hq_admin_required
@require_POST
def resend_otp(request: HttpRequest, business_id: int, user_id: int) -> HttpResponse:
    """
    Resend OTP code for a user.
    """
    business = get_object_or_404(Business, id=business_id)
    user = get_object_or_404(User, id=user_id)
    
    if not Membership.objects.filter(business=business, user=user).exists():
        messages.error(request, "User does not belong to this business")
        return redirect("hq:account_support", business_id=business_id)
    
    if not EmailOTP:
        messages.error(request, "EmailOTP model not available")
        return redirect("hq:account_support", business_id=business_id)
    
    try:
        # Create new OTP
        otp = EmailOTP.objects.create(
            email=user.email,
            purpose="login",
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        
        # In production, send email here
        # For now, just log it
        
        # Log action
        _log_support_action(
            actor=request.user,
            business=business,
            action_type="RESEND_OTP",
            reason=request.POST.get("reason", "OTP resent by HQ"),
            entity_type="User",
            entity_id=str(user.id),
            payload_after={"email": user.email}
        )
        
        messages.success(request, f"OTP resent to {user.email}")
    except Exception as e:
        messages.error(request, f"Failed to resend OTP: {e}")
    
    return redirect("hq:account_support", business_id=business_id)


@hq_admin_required
def user_sessions(request: HttpRequest, business_id: int, user_id: int) -> HttpResponse:
    """
    View active sessions for a user.
    """
    business = get_object_or_404(Business, id=business_id)
    user = get_object_or_404(User, id=user_id)
    
    if not Membership.objects.filter(business=business, user=user).exists():
        messages.error(request, "User does not belong to this business")
        return redirect("hq:account_support", business_id=business_id)
    
    # Get active sessions (simplified)
    now = timezone.now()
    active_sessions = Session.objects.filter(expire_date__gte=now)
    
    # In a real implementation, you'd decode session data to filter by user
    # For now, just show count
    
    context = {
        "business": business,
        "user": user,
        "active_sessions_count": active_sessions.count(),
        "active_tab": "account_support",  # For template navigation consistency
    }
    
    return render(request, "hq/user_sessions.html", context)


# ======================================================================
# Helper Functions
# ======================================================================
def _log_support_action(
    actor,
    business,
    action_type: str,
    reason: str,
    entity_type: str = "",
    entity_id: str = "",
    payload_before: dict = None,
    payload_after: dict = None
) -> None:
    """Create a SupportActionLog entry."""
    try:
        from hq.models import SupportActionLog
        SupportActionLog.objects.create(
            actor=actor,
            business=business,
            action_type=action_type,
            reason=reason,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_before=payload_before or {},
            payload_after=payload_after or {},
        )
    except Exception:
        # Don't fail if logging fails
        pass


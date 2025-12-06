# wallet/views_admin.py
"""
Admin-specific wallet views for commission and cost management.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.views.decorators.http import require_POST, require_http_methods
from django.db import transaction

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


# ==============================================================================
# Admin Cost Management Views
# ==============================================================================

@login_required
def admin_costs_list(request: HttpRequest):
    """
    List and manage admin costs for current business.
    Shows cost transactions with CRUD operations.
    """
    if not _is_manager(request.user):
        messages.error(request, "Access denied. Only managers can manage costs.")
        return redirect('dashboard:home')
    
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect('tenants:activate_mine')
    
    from wallet.models import WalletTransaction, Ledger, TxnType
    
    # Get all cost transactions for this business
    costs = WalletTransaction.objects.filter(
        business=business,
        ledger=Ledger.COMPANY,
        type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING]
    ).order_by('-created_at')
    
    return render(request, 'wallet/admin_costs.html', {
        'costs': costs,
        'business': business,
    })


@login_required
@require_http_methods(["POST"])
def admin_costs_create(request: HttpRequest):
    """
    Create a new admin cost.
    
    POST params:
        - name: Cost name/description
        - amount: Cost amount (positive number)
        - is_recurring: Boolean (1 if recurring, 0 if once-off)
    """
    if not _is_manager(request.user):
        messages.error(request, "Access denied. Only managers can create costs.")
        return redirect('dashboard:home')
    
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect('tenants:activate_mine')
    
    try:
        from wallet.models import WalletTransaction, Ledger, TxnType
        
        name = request.POST.get('name', '').strip()
        amount_str = request.POST.get('amount', '').strip()
        is_recurring = request.POST.get('is_recurring') == '1'
        
        if not name:
            messages.error(request, "Cost name is required.")
            return redirect('wallet:admin_costs_list')
        
        if not amount_str:
            messages.error(request, "Cost amount is required.")
            return redirect('wallet:admin_costs_list')
        
        try:
            amount = Decimal(amount_str)
            if amount <= 0:
                raise ValueError("Amount must be positive")
        except (ValueError, InvalidOperation) as e:
            messages.error(request, f"Invalid amount: {e}")
            return redirect('wallet:admin_costs_list')
        
        # Create cost transaction (negative for expense)
        cost_type = TxnType.COST_RECURRING if is_recurring else TxnType.COST_ONCE_OFF
        
        WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            type=cost_type,
            amount=-abs(amount),  # Negative for expense
            note=name,
            business=business,
            created_by=request.user,
            is_recurring=is_recurring,
        )
        
        messages.success(
            request,
            f"Cost '{name}' created successfully ({cost_type.label})."
        )
        
    except Exception as e:
        messages.error(request, f"Error creating cost: {e}")
    
    return redirect('wallet:admin_costs_list')


@login_required
@require_http_methods(["POST"])
def admin_costs_update(request: HttpRequest, pk: int):
    """
    Update an existing admin cost.
    
    POST params:
        - name: Updated cost name
        - amount: Updated amount
        - is_recurring: Boolean
    """
    if not _is_manager(request.user):
        messages.error(request, "Access denied. Only managers can edit costs.")
        return redirect('dashboard:home')
    
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect('tenants:activate_mine')
    
    try:
        from wallet.models import WalletTransaction, Ledger, TxnType
        
        cost = get_object_or_404(
            WalletTransaction,
            pk=pk,
            business=business,
            ledger=Ledger.COMPANY,
            type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING]
        )
        
        name = request.POST.get('name', '').strip()
        amount_str = request.POST.get('amount', '').strip()
        is_recurring = request.POST.get('is_recurring') == '1'
        
        if name:
            cost.note = name
        
        if amount_str:
            try:
                amount = Decimal(amount_str)
                if amount <= 0:
                    raise ValueError("Amount must be positive")
                cost.amount = -abs(amount)
            except (ValueError, InvalidOperation) as e:
                messages.error(request, f"Invalid amount: {e}")
                return redirect('wallet:admin_costs_list')
        
        # Update type and recurring flag
        cost.is_recurring = is_recurring
        cost.type = TxnType.COST_RECURRING if is_recurring else TxnType.COST_ONCE_OFF
        
        cost.save()
        
        messages.success(request, f"Cost '{cost.note}' updated successfully.")
        
    except Exception as e:
        messages.error(request, f"Error updating cost: {e}")
    
    return redirect('wallet:admin_costs_list')


@login_required
@require_http_methods(["POST"])
def admin_costs_delete(request: HttpRequest, pk: int):
    """
    Delete an admin cost.
    """
    if not _is_manager(request.user):
        messages.error(request, "Access denied. Only managers can delete costs.")
        return redirect('dashboard:home')
    
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect('tenants:activate_mine')
    
    try:
        from wallet.models import WalletTransaction, Ledger, TxnType
        
        cost = get_object_or_404(
            WalletTransaction,
            pk=pk,
            business=business,
            ledger=Ledger.COMPANY,
            type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING]
        )
        
        cost_name = cost.note
        cost.delete()
        
        messages.success(request, f"Cost '{cost_name}' deleted successfully.")
        
    except Exception as e:
        messages.error(request, f"Error deleting cost: {e}")
    
    return redirect('wallet:admin_costs_list')


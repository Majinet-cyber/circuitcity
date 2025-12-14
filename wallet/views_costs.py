# wallet/views_costs.py
"""
Admin cost management views.
Managers can create, view, edit, and delete business costs (fixed/variable, recurring/once-off).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import WalletTransaction, TxnType, Ledger
from .services_costs import (
    get_business_costs_for_period,
    add_business_cost,
    get_cost_breakdown_by_category
)
from .utils_costs import ensure_monthly_recurring_costs

try:
    from tenants.utils import get_active_business
except ImportError:
    def get_active_business(request):
        return getattr(request, 'business', None) or getattr(request, 'active_business', None)

try:
    from core.decorators import manager_required
except ImportError:
    def manager_required(view_func):
        """Fallback decorator"""
        from functools import wraps
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not (request.user.is_staff or getattr(request.user, 'is_superuser', False)):
                raise PermissionDenied("Manager access required")
            return view_func(request, *args, **kwargs)
        return _wrapped


def _is_manager(user, business=None) -> bool:
    """Check if user is a manager."""
    if not user or not user.is_authenticated:
        return False
    
    if user.is_staff or user.is_superuser:
        return True
    
    try:
        if hasattr(user, 'profile') and getattr(user.profile, 'is_manager', False):
            return True
    except Exception:
        pass
    
    if business:
        try:
            from tenants.models import Membership
            membership = Membership.objects.filter(
                user=user,
                business=business,
                role='MANAGER',
                status='ACTIVE'
            ).first()
            if membership:
                return True
        except Exception:
            pass
    
    return False


@login_required
@require_http_methods(["GET"])
def admin_cost_list(request: HttpRequest) -> HttpResponse:
    """
    List all costs for the active business.
    Shows fixed vs variable costs, recurring vs once-off.
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected")
        return redirect("wallet:admin_home")
    
    if not _is_manager(request.user, business):
        messages.error(request, "Manager access required")
        return redirect("wallet:admin_home")
    
    # Ensure recurring costs are created for current month (idempotent)
    try:
        from datetime import date
        today = timezone.now().date()
        month_start = date(today.year, today.month, 1)
        ensure_monthly_recurring_costs(business, month_start)
    except Exception as e:
        # Don't break the page if auto-creation fails, just log it
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to auto-create recurring costs: {e}")
    
    # Get period from query params (default to current month)
    period = request.GET.get('period', 'month')
    
    # Get cost summary for the period
    cost_summary = get_business_costs_for_period(business, period=period)
    
    # Get detailed breakdown with defensive handling
    breakdown = get_cost_breakdown_by_category(
        business,
        cost_summary['period_start'],
        cost_summary['period_end']
    )
    # Defensive: ensure breakdown has expected keys
    breakdown = breakdown or {}
    
    # Get all costs as WalletTransaction objects for templates that expect direct model access
    # Defensive: use .none() if no business (though we already checked above)
    if business:
        all_costs_qs = WalletTransaction.objects.filter(
            business=business,
            ledger=Ledger.COMPANY,
            type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING]
        ).order_by('-created_at')
    else:
        all_costs_qs = WalletTransaction.objects.none()
    
    # Get subscription safely (may not exist)
    subscription = None
    try:
        subscription = business.subscription
    except Exception:
        subscription = None
    
    # Get membership safely (may not exist)
    membership = None
    try:
        from tenants.models import Membership
        membership = Membership.objects.filter(
            user=request.user,
            business=business,
            status='ACTIVE'
        ).first()
    except Exception:
        membership = None
    
    context = {
        'business': business,
        'period': period,
        'cost_summary': cost_summary,
        'fixed_costs': breakdown.get('fixed') or [],
        'variable_costs': breakdown.get('variable') or [],
        'fixed_total': breakdown.get('fixed_total') or Decimal('0'),
        'variable_total': breakdown.get('variable_total') or Decimal('0'),
        'costs': all_costs_qs,  # For templates that expect a 'costs' variable
        'show_search': False,  # Don't show global search bar on this page
        'subscription': subscription,  # Safe default for base template
        'membership': membership,  # Safe default for base template
    }
    
    # Explicitly render the app-specific template to avoid ambiguity
    return render(request, 'wallet/admin_costs.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def admin_cost_create(request: HttpRequest) -> HttpResponse:
    """
    Create a new business cost.
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected")
        return redirect("wallet:admin_home")
    
    if not _is_manager(request.user, business):
        messages.error(request, "Manager access required")
        return redirect("wallet:admin_home")
    
    if request.method == "POST":
        try:
            # Get form data
            name = request.POST.get('name', '').strip()
            amount_str = request.POST.get('amount', '0').strip()
            cost_category = request.POST.get('cost_category', 'variable')
            is_recurring = request.POST.get('is_recurring') == 'on'
            effective_date_str = request.POST.get('effective_date', '')
            note = request.POST.get('note', '').strip()
            
            # Validate
            if not name:
                messages.error(request, "Cost name is required")
                return render(request, 'wallet/admin_cost_form.html', {
                    'business': business,
                    'form_data': request.POST,
                })
            
            try:
                amount = Decimal(amount_str)
                if amount <= 0:
                    raise InvalidOperation("Amount must be positive")
            except (InvalidOperation, ValueError):
                messages.error(request, "Invalid amount")
                return render(request, 'wallet/admin_cost_form.html', {
                    'business': business,
                    'form_data': request.POST,
                })
            
            # Parse effective date
            if effective_date_str:
                try:
                    effective_date = date.fromisoformat(effective_date_str)
                except ValueError:
                    effective_date = timezone.localdate()
            else:
                effective_date = timezone.localdate()
            
            # Create cost
            add_business_cost(
                business=business,
                name=name,
                amount=amount,
                cost_category=cost_category,
                is_recurring=is_recurring,
                effective_date=effective_date,
                created_by=request.user,
                note=note
            )
            
            messages.success(
                request,
                f"Cost '{name}' added successfully"
            )
            return redirect("wallet:admin_cost_list")
            
        except Exception as e:
            messages.error(request, f"Error creating cost: {str(e)}")
            return render(request, 'wallet/admin_cost_form.html', {
                'business': business,
                'form_data': request.POST,
            })
    
    # GET request - show form
    return render(request, 'wallet/admin_cost_form.html', {
        'business': business,
        'today': timezone.localdate().isoformat(),
    })


@login_required
@require_http_methods(["GET", "POST"])
def admin_cost_edit(request: HttpRequest, cost_id: int) -> HttpResponse:
    """
    Edit an existing cost.
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected")
        return redirect("wallet:admin_home")
    
    if not _is_manager(request.user, business):
        messages.error(request, "Manager access required")
        return redirect("wallet:admin_home")
    
    try:
        cost = WalletTransaction.objects.get(
            pk=cost_id,
            business=business,
            ledger=Ledger.COMPANY,
            type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING]
        )
    except WalletTransaction.DoesNotExist:
        messages.error(request, "Cost not found")
        return redirect("wallet:admin_cost_list")
    
    if request.method == "POST":
        try:
            # Get form data
            name = request.POST.get('name', '').strip()
            amount_str = request.POST.get('amount', '0').strip()
            cost_category = request.POST.get('cost_category', 'variable')
            is_recurring = request.POST.get('is_recurring') == 'on'
            effective_date_str = request.POST.get('effective_date', '')
            note = request.POST.get('note', '').strip()
            
            # Validate
            if not name:
                messages.error(request, "Cost name is required")
                return render(request, 'wallet/admin_cost_form.html', {
                    'business': business,
                    'cost': cost,
                    'form_data': request.POST,
                    'is_edit': True,
                })
            
            try:
                amount = Decimal(amount_str)
                if amount <= 0:
                    raise InvalidOperation("Amount must be positive")
            except (InvalidOperation, ValueError):
                messages.error(request, "Invalid amount")
                return render(request, 'wallet/admin_cost_form.html', {
                    'business': business,
                    'cost': cost,
                    'form_data': request.POST,
                    'is_edit': True,
                })
            
            # Parse effective date
            if effective_date_str:
                try:
                    effective_date = date.fromisoformat(effective_date_str)
                except ValueError:
                    effective_date = cost.effective_date
            else:
                effective_date = cost.effective_date
            
            # Update cost
            cost.amount = -abs(amount)  # Store as negative
            cost.note = f"{name}" + (f" - {note}" if note else "")
            cost.effective_date = effective_date
            cost.is_recurring = is_recurring
            cost.type = TxnType.COST_RECURRING if is_recurring else TxnType.COST_ONCE_OFF
            cost.effective_from = effective_date if is_recurring else None
            
            # Update metadata
            meta = cost.meta or {}
            meta['cost_category'] = cost_category
            meta['cost_name'] = name
            cost.meta = meta
            
            cost.save()
            
            messages.success(request, f"Cost '{name}' updated successfully")
            return redirect("wallet:admin_cost_list")
            
        except Exception as e:
            messages.error(request, f"Error updating cost: {str(e)}")
    
    # GET request - show form with existing data
    meta = cost.meta or {}
    cost_name = meta.get('cost_name', cost.note)
    cost_category = meta.get('cost_category', 'variable')
    
    context = {
        'business': business,
        'cost': cost,
        'cost_name': cost_name,
        'cost_amount': abs(cost.amount),
        'cost_category': cost_category,
        'is_edit': True,
    }
    
    return render(request, 'wallet/admin_cost_form.html', context)


@login_required
@require_http_methods(["POST"])
def admin_cost_delete(request: HttpRequest, cost_id: int) -> HttpResponse:
    """
    Delete a cost.
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected")
        return redirect("wallet:admin_home")
    
    if not _is_manager(request.user, business):
        messages.error(request, "Manager access required")
        return redirect("wallet:admin_home")
    
    try:
        cost = WalletTransaction.objects.get(
            pk=cost_id,
            business=business,
            ledger=Ledger.COMPANY,
            type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING]
        )
        
        cost_name = (cost.meta or {}).get('cost_name', cost.note)
        cost.delete()
        
        messages.success(request, f"Cost '{cost_name}' deleted successfully")
        
    except WalletTransaction.DoesNotExist:
        messages.error(request, "Cost not found")
    except Exception as e:
        messages.error(request, f"Error deleting cost: {str(e)}")
    
    return redirect("wallet:admin_cost_list")


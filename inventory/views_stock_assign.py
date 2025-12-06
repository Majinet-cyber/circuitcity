# inventory/views_stock_assign.py
"""
Stock assignment views - managers assign/transfer stock ownership to agents.
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, get_object_or_404
from django.views.decorators.http import require_POST, require_http_methods
from django.db import transaction

from inventory.models import InventoryItem
from tenants.models import Membership
from tenants.utils import get_active_business

User = get_user_model()


def _is_manager(user) -> bool:
    """Check if user is manager/staff."""
    try:
        return bool(user.is_authenticated and (user.is_staff or getattr(user.profile, 'is_manager', False)))
    except Exception:
        return bool(user.is_authenticated and user.is_staff)


@login_required
@require_POST
def assign_stock_owner(request: HttpRequest) -> HttpResponse:
    """
    Assign or transfer stock ownership to an agent or back to manager pool.
    
    POST params:
        - stock_id: ID of the InventoryItem
        - owner_id: User ID to assign to (empty/null = manager pool)
    """
    if not _is_manager(request.user):
        messages.error(request, "Access denied. Only managers can assign stock.")
        return redirect(request.META.get('HTTP_REFERER', 'inventory:stock_list'))
    
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect('tenants:activate_mine')
    
    stock_id = request.POST.get('stock_id')
    owner_id = request.POST.get('owner_id', '').strip()
    
    if not stock_id:
        messages.error(request, "Stock ID is required.")
        return redirect(request.META.get('HTTP_REFERER', 'inventory:stock_list'))
    
    try:
        stock_item = get_object_or_404(InventoryItem, id=stock_id, business=business)
    except Exception as e:
        messages.error(request, f"Stock item not found: {e}")
        return redirect(request.META.get('HTTP_REFERER', 'inventory:stock_list'))
    
    # Determine new owner
    new_owner = None
    new_role = "MANAGER"
    
    if owner_id and owner_id != "manager":
        try:
            new_owner = User.objects.get(id=owner_id)
            
            # Validate that user belongs to same business
            membership = Membership.objects.filter(
                user=new_owner,
                business=business,
                status='ACTIVE'
            ).first()
            
            if not membership:
                messages.error(request, f"User {new_owner.username} is not an active member of {business.name}.")
                return redirect(request.META.get('HTTP_REFERER', 'inventory:stock_list'))
            
            new_role = "AGENT"
            
        except User.DoesNotExist:
            messages.error(request, "Selected user not found.")
            return redirect(request.META.get('HTTP_REFERER', 'inventory:stock_list'))
    
    # Update stock item
    with transaction.atomic():
        old_owner_name = stock_item.assigned_agent.get_full_name() if stock_item.assigned_agent else "Manager Pool"
        
        stock_item.assigned_agent = new_owner
        stock_item.assigned_role = new_role
        stock_item.save(update_fields=['assigned_agent', 'assigned_role'])
        
        new_owner_name = new_owner.get_full_name() if new_owner else "Manager Pool"
        
        messages.success(
            request,
            f"Stock {stock_item.imei or stock_item.id} transferred from {old_owner_name} to {new_owner_name}."
        )
    
    return redirect(request.META.get('HTTP_REFERER', 'inventory:stock_list'))


@login_required
@require_POST
def bulk_assign_stock(request: HttpRequest) -> HttpResponse:
    """
    Bulk assign multiple stock items to an agent or manager pool.
    
    POST params:
        - stock_ids[]: Array of InventoryItem IDs
        - owner_id: User ID to assign to (empty/null = manager pool)
    """
    if not _is_manager(request.user):
        messages.error(request, "Access denied. Only managers can assign stock.")
        return redirect(request.META.get('HTTP_REFERER', 'inventory:stock_list'))
    
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect('tenants:activate_mine')
    
    stock_ids = request.POST.getlist('stock_ids[]') or request.POST.getlist('stock_ids')
    owner_id = request.POST.get('owner_id', '').strip()
    
    if not stock_ids:
        messages.error(request, "No stock items selected.")
        return redirect(request.META.get('HTTP_REFERER', 'inventory:stock_list'))
    
    # Determine new owner
    new_owner = None
    new_role = "MANAGER"
    
    if owner_id and owner_id != "manager":
        try:
            new_owner = User.objects.get(id=owner_id)
            
            # Validate that user belongs to same business
            membership = Membership.objects.filter(
                user=new_owner,
                business=business,
                status='ACTIVE'
            ).first()
            
            if not membership:
                messages.error(request, f"User {new_owner.username} is not an active member of {business.name}.")
                return redirect(request.META.get('HTTP_REFERER', 'inventory:stock_list'))
            
            new_role = "AGENT"
            
        except User.DoesNotExist:
            messages.error(request, "Selected user not found.")
            return redirect(request.META.get('HTTP_REFERER', 'inventory:stock_list'))
    
    # Bulk update
    with transaction.atomic():
        updated_count = InventoryItem.objects.filter(
            id__in=stock_ids,
            business=business
        ).update(
            assigned_agent=new_owner,
            assigned_role=new_role
        )
        
        new_owner_name = new_owner.get_full_name() if new_owner else "Manager Pool"
        
        messages.success(
            request,
            f"{updated_count} stock item(s) assigned to {new_owner_name}."
        )
    
    return redirect(request.META.get('HTTP_REFERER', 'inventory:stock_list'))


@login_required
@require_http_methods(["GET"])
def get_business_agents(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to get list of active agents for current business.
    Used by stock assignment UI for populating dropdowns.
    """
    if not _is_manager(request.user):
        return JsonResponse({
            "ok": False,
            "error": "Access denied. Only managers can view agent list."
        }, status=403)
    
    business = get_active_business(request)
    if not business:
        return JsonResponse({
            "ok": False,
            "error": "No active business selected."
        }, status=400)
    
    # Get active agent memberships
    agent_memberships = Membership.objects.filter(
        business=business,
        role='AGENT',
        status='ACTIVE'
    ).select_related('user').order_by('user__first_name', 'user__last_name')
    
    agents = []
    for membership in agent_memberships:
        user = membership.user
        agents.append({
            "id": user.id,
            "username": user.username,
            "full_name": user.get_full_name() or user.username,
            "email": user.email,
        })
    
    return JsonResponse({
        "ok": True,
        "agents": agents
    })


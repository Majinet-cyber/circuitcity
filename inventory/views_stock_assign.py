# inventory/views_stock_assign.py
"""
Stock assignment views (manager-only).
Managers can assign/transfer stock between agents and reclaim stock.
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpRequest, JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .models import InventoryItem
from tenants.models import Business, Membership

try:
    from core.decorators import manager_required
except ImportError:
    def manager_required(view_func):
        """Fallback decorator if not available"""
        from functools import wraps
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not (request.user.is_staff or getattr(request.user, 'is_superuser', False)):
                raise PermissionDenied("Manager access required")
            return view_func(request, *args, **kwargs)
        return _wrapped

try:
    from tenants.utils import get_active_business
except ImportError:
    def get_active_business(request):
        return getattr(request, 'business', None) or getattr(request, 'active_business', None)

User = get_user_model()


def _is_manager(user, business=None) -> bool:
    """Check if user is a manager for the given business."""
    if not user or not user.is_authenticated:
        return False
    
    # Staff and superusers are always managers
    if user.is_staff or user.is_superuser:
        return True
    
    # Check profile.is_manager flag
    try:
        if hasattr(user, 'profile') and getattr(user.profile, 'is_manager', False):
            return True
    except Exception:
        pass
    
    # Check Membership role if business provided
    if business:
        try:
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
@require_http_methods(["POST"])
def assign_stock_owner(request: HttpRequest) -> HttpResponse:
    """
    Assign stock to an agent or reclaim to manager.
    
    POST params:
      - stock_id: int
      - owner_id: int or empty (empty = reclaim to manager)
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected")
        return redirect("inventory:stock_list")
    
    # Permission check
    if not _is_manager(request.user, business):
        messages.error(request, "You don't have permission to assign stock")
        return redirect("inventory:stock_list")
    
    stock_id = request.POST.get("stock_id")
    owner_id = request.POST.get("owner_id", "").strip()
    
    if not stock_id:
        messages.error(request, "Missing stock ID")
        return redirect("inventory:stock_list")
    
    try:
        item = InventoryItem.objects.get(pk=stock_id, business=business)
    except InventoryItem.DoesNotExist:
        messages.error(request, "Stock item not found")
        return redirect("inventory:stock_list")
    
    # Cannot assign sold items
    if item.status == "SOLD":
        messages.error(request, "Cannot assign sold items")
        return redirect("inventory:stock_list")
    
    with transaction.atomic():
        if owner_id:
            # Assign to agent
            try:
                agent = User.objects.get(pk=owner_id)
                
                # Verify agent belongs to this business
                membership = Membership.objects.filter(
                    user=agent,
                    business=business,
                    role='AGENT',
                    status='ACTIVE'
                ).first()
                
                if not membership:
                    messages.error(request, f"User {agent.username} is not an active agent for this business")
                    return redirect("inventory:stock_list")
                
                item.assigned_agent = agent
                item.assigned_role = "AGENT"
                item.save(update_fields=["assigned_agent", "assigned_role", "updated_at"])
                
                messages.success(
                    request,
                    f"Stock assigned to {agent.get_full_name() or agent.username}"
                )
                
            except User.DoesNotExist:
                messages.error(request, "Agent not found")
                return redirect("inventory:stock_list")
        else:
            # Reclaim to manager
            item.assigned_agent = None
            item.assigned_role = "MANAGER"
            item.save(update_fields=["assigned_agent", "assigned_role", "updated_at"])
            
            messages.success(request, "Stock reclaimed to Manager")
    
    return redirect("inventory:stock_list")


@login_required
@require_http_methods(["POST"])
def bulk_assign_stock(request: HttpRequest) -> JsonResponse:
    """
    Bulk assign multiple stock items to an agent.
    
    POST JSON:
      {
        "stock_ids": [1, 2, 3],
        "owner_id": 42 or null
      }
    """
    business = get_active_business(request)
    if not business:
        return JsonResponse({"ok": False, "error": "No active business"}, status=400)
    
    if not _is_manager(request.user, business):
        return JsonResponse({"ok": False, "error": "Manager access required"}, status=403)
    
    import json
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
    
    stock_ids = data.get("stock_ids", [])
    owner_id = data.get("owner_id")
    
    if not isinstance(stock_ids, list) or not stock_ids:
        return JsonResponse({"ok": False, "error": "stock_ids must be a non-empty list"}, status=400)
    
    with transaction.atomic():
        items = InventoryItem.objects.filter(
            pk__in=stock_ids,
            business=business,
            status="IN_STOCK"
        )
        
        if not items.exists():
            return JsonResponse({"ok": False, "error": "No valid items found"}, status=404)
        
        if owner_id:
            try:
                agent = User.objects.get(pk=owner_id)
                membership = Membership.objects.filter(
                    user=agent,
                    business=business,
                    role='AGENT',
                    status='ACTIVE'
                ).first()
                
                if not membership:
                    return JsonResponse({
                        "ok": False,
                        "error": f"User is not an active agent for this business"
                    }, status=400)
                
                updated = items.update(
                    assigned_agent=agent,
                    assigned_role="AGENT"
                )
                
                return JsonResponse({
                    "ok": True,
                    "updated": updated,
                    "message": f"Assigned {updated} items to {agent.get_full_name() or agent.username}"
                })
                
            except User.DoesNotExist:
                return JsonResponse({"ok": False, "error": "Agent not found"}, status=404)
        else:
            # Reclaim all to manager
            updated = items.update(
                assigned_agent=None,
                assigned_role="MANAGER"
            )
            
            return JsonResponse({
                "ok": True,
                "updated": updated,
                "message": f"Reclaimed {updated} items to Manager"
            })


@login_required
@require_http_methods(["GET"])
def get_business_agents(request: HttpRequest) -> JsonResponse:
    """
    Return list of agents for the active business (for populating dropdowns).
    
    Returns:
      {
        "ok": true,
        "agents": [
          {
            "id": 42,
            "username": "john_doe",
            "full_name": "John Doe",
            "location": "Main Store"
          },
          ...
        ]
      }
    """
    business = get_active_business(request)
    if not business:
        return JsonResponse({"ok": False, "error": "No active business"}, status=400)
    
    if not _is_manager(request.user, business):
        return JsonResponse({"ok": False, "error": "Manager access required"}, status=403)
    
    memberships = Membership.objects.filter(
        business=business,
        role='AGENT',
        status='ACTIVE'
    ).select_related('user', 'location')
    
    agents = []
    for m in memberships:
        agents.append({
            "id": m.user_id,
            "username": m.user.username,
            "full_name": m.user.get_full_name() or m.user.username,
            "location": m.location.name if m.location else None,
        })
    
    return JsonResponse({"ok": True, "agents": agents})

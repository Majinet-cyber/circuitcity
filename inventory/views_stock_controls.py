"""
Stock control views: transfer, edit IMEI, archive, restore.
Manager-only operations for phone inventory management.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from tenants.models import Membership
from tenants.utils import get_active_business

from .models import InventoryItem, User


def _is_manager(request: HttpRequest) -> bool:
    """Check if user is a manager or admin."""
    if request.user.is_staff or request.user.is_superuser:
        return True

    if getattr(getattr(request.user, "profile", None), "is_manager", False):
        return True

    biz = get_active_business(request)
    if biz:
        try:
            membership = Membership.objects.filter(
                user=request.user, business=biz, role="MANAGER", status="ACTIVE"
            ).first()
            if membership:
                return True
        except Exception:
            pass

    return False


@login_required
@require_POST
def transfer_stock(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Transfer a stock item to another agent.
    Manager-only. POST params: agent_id (user ID of target agent).
    """
    # Permission check
    if not _is_manager(request):
        return JsonResponse({"ok": False, "error": "Permission denied. Managers only."}, status=403)

    biz = get_active_business(request)
    if not biz:
        return JsonResponse({"ok": False, "error": "No active business."}, status=400)

    # Get the stock item
    item = get_object_or_404(InventoryItem, pk=pk, business=biz)

    # Get target agent
    agent_id = request.POST.get("agent_id")
    if not agent_id:
        return JsonResponse({"ok": False, "error": "agent_id required."}, status=400)

    if agent_id in ("none", "unassign", ""):
        # Transfer to manager pool (unassign)
        item.assigned_agent = None
        item.assigned_role = "MANAGER"
        item.save(update_fields=["assigned_agent", "assigned_role", "updated_at"])
        messages.success(request, f"Stock {item.imei or item.pk} transferred to manager pool.")
        return redirect("inventory:stock_list")

    try:
        agent_id = int(agent_id)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Invalid agent_id."}, status=400)

    # Verify user is active agent or manager for this business
    try:
        membership = Membership.objects.filter(
            user_id=agent_id, business=biz, role__in=["AGENT", "MANAGER"], status="ACTIVE"
        ).first()
        if not membership:
            return JsonResponse({"ok": False, "error": "User not found or inactive."}, status=400)

        agent = membership.user
        assigned_role = membership.role
    except Exception as e:
        return JsonResponse({"ok": False, "error": f"Error finding user: {e}"}, status=400)

    # Transfer
    item.assigned_agent = agent
    item.assigned_role = assigned_role
    item.save(update_fields=["assigned_agent", "assigned_role", "updated_at"])

    messages.success(request, f"Stock {item.imei or item.pk} transferred to {agent.get_full_name() or agent.username}.")
    return redirect("inventory:stock_list")


@login_required
@require_POST
def edit_imei(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Edit the IMEI of a stock item.
    Manager-only. POST params: imei (15 digits).
    """
    # Permission check
    if not _is_manager(request):
        return JsonResponse({"ok": False, "error": "Permission denied. Managers only."}, status=403)

    biz = get_active_business(request)
    if not biz:
        return JsonResponse({"ok": False, "error": "No active business."}, status=400)

    # Get the stock item
    item = get_object_or_404(InventoryItem, pk=pk, business=biz)

    # Get new IMEI
    new_imei = (request.POST.get("imei") or "").strip()
    if not new_imei:
        return JsonResponse({"ok": False, "error": "IMEI required."}, status=400)

    # Validate 15 digits
    if not new_imei.isdigit() or len(new_imei) != 15:
        return JsonResponse({"ok": False, "error": "IMEI must be exactly 15 digits."}, status=400)

    # Check uniqueness (globally, including archived items)
    existing = InventoryItem.all_objects.filter(imei=new_imei).exclude(pk=item.pk).first()
    if existing:
        return JsonResponse(
            {"ok": False, "error": f"IMEI {new_imei} already exists (item #{existing.pk})."}, status=400
        )

    old_imei = item.imei
    item.imei = new_imei

    try:
        item.full_clean()
        item.save(update_fields=["imei", "updated_at"])
    except ValidationError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)

    messages.success(request, f"IMEI updated from {old_imei or '(none)'} to {new_imei}.")
    return redirect("inventory:stock_list")


@login_required
@require_POST
def archive_stock(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Archive (soft-delete) a stock item.
    Manager-only.
    """
    # Permission check
    if not _is_manager(request):
        return JsonResponse({"ok": False, "error": "Permission denied. Managers only."}, status=403)

    biz = get_active_business(request)
    if not biz:
        return JsonResponse({"ok": False, "error": "No active business."}, status=400)

    # Get the stock item
    item = get_object_or_404(InventoryItem, pk=pk, business=biz)

    if item.archived_at:
        return JsonResponse({"ok": False, "error": "Item already archived."}, status=400)

    # Archive it
    item.archived_at = timezone.now()
    item.archived_by = request.user
    item.is_active = False  # Also set legacy flag for compatibility
    item.save(update_fields=["archived_at", "archived_by", "is_active", "updated_at"])

    messages.success(request, f"Stock {item.imei or item.pk} archived.")
    return redirect("inventory:stock_list")


@login_required
@require_POST
def restore_stock(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Restore an archived stock item.
    Manager-only.
    """
    # Permission check
    if not _is_manager(request):
        return JsonResponse({"ok": False, "error": "Permission denied. Managers only."}, status=403)

    biz = get_active_business(request)
    if not biz:
        return JsonResponse({"ok": False, "error": "No active business."}, status=400)

    # Get the stock item (use all_objects to include archived)
    item = get_object_or_404(InventoryItem.all_objects, pk=pk, business=biz)

    if not item.archived_at:
        return JsonResponse({"ok": False, "error": "Item not archived."}, status=400)

    # Restore it
    item.archived_at = None
    item.archived_by = None
    item.is_active = True
    item.save(update_fields=["archived_at", "archived_by", "is_active", "updated_at"])

    messages.success(request, f"Stock {item.imei or item.pk} restored.")
    return redirect("inventory:stock_list")

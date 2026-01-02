"""
PHASE 6: Liquor Agent Assignment Views
Manager and agent views for stock assignment system.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError, PermissionDenied
from django.db.models import Sum, Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from tenants.utils import require_business
from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.helpers import get_active_business
from inventory.models import MerchProduct
from inventory.models_liquor_assignment import (
    LiquorStockAssignment,
    LiquorDailyReconciliation,
    LiquorAgentTarget,
)
from inventory.services_liquor_assignment import (
    assign_stock_to_agent,
    record_bottle_sale,
    return_bottles_to_stock,
    generate_daily_reconciliation,
    finalize_reconciliation,
    get_agent_performance,
    get_top_performing_agents,
)
from . import base


# ==============================================================================
# MANAGER: STOCK ASSIGNMENT
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def assignment_list(request):
    """
    Manager view: List all active and recent assignments.
    Filter by agent, status, date range.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")

    # Permission check
    if not request.user.is_manager(business):
        messages.error(request, "Only managers can view assignments")
        return redirect("verticals:liquor_dashboard")

    # Get filter parameters
    agent_id = request.GET.get("agent")
    status = request.GET.get("status", "").upper()

    # Base query
    assignments = (
        LiquorStockAssignment.objects.filter(business=business)
        .select_related("agent", "product", "assigned_by")
        .order_by("-assigned_at")
    )

    # Apply filters
    if agent_id:
        assignments = assignments.filter(agent_id=agent_id)
    if status and status in ["ACTIVE", "SOLD_OUT", "RETURNED", "RECONCILED"]:
        assignments = assignments.filter(status=status)

    # Get all agents for filter dropdown
    from django.contrib.auth import get_user_model

    User = get_user_model()
    agents = User.objects.filter(liquor_stock_assigned__business=business).distinct().order_by("username")

    # Summary stats
    active_assignments = assignments.filter(status="ACTIVE")
    total_bottles_active = active_assignments.aggregate(total=Sum("bottles_assigned"))["total"] or 0
    total_bottles_sold = active_assignments.aggregate(total=Sum("bottles_sold"))["total"] or 0

    ctx.update(
        {
            "page_title": "Stock Assignments",
            "assignments": assignments[:100],  # Limit for performance
            "agents": agents,
            "selected_agent": agent_id,
            "selected_status": status,
            "total_bottles_active": total_bottles_active,
            "total_bottles_sold": total_bottles_sold,
            "status_choices": LiquorStockAssignment.STATUS_CHOICES,
        }
    )

    return render(request, "verticals/liquor/assignment_list.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def assignment_create(request):
    """
    Manager view: Create new stock assignment to an agent.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")

    # Permission check
    if not request.user.is_manager(business):
        messages.error(request, "Only managers can assign stock")
        return redirect("verticals:liquor_dashboard")

    if request.method == "POST":
        try:
            agent_id = int(request.POST.get("agent_id"))
            product_id = int(request.POST.get("product_id"))
            bottles_count = int(request.POST.get("bottles_count"))
            notes = request.POST.get("notes", "").strip()

            # Get agent
            from django.contrib.auth import get_user_model

            User = get_user_model()
            agent = User.objects.get(pk=agent_id)

            # Create assignment
            assignment = assign_stock_to_agent(
                business=business,
                agent=agent,
                product_id=product_id,
                bottles_count=bottles_count,
                assigned_by=request.user,
                notes=notes,
            )

            messages.success(
                request, f"✅ Assigned {bottles_count} bottles of {assignment.product.name} to {agent.username}"
            )
            return redirect("verticals:liquor_assignment_list")

        except (ValueError, KeyError) as e:
            messages.error(request, f"Invalid input: {e}")
        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Error creating assignment: {e}")

    # Get available products (liquor with stock)
    products = MerchProduct.objects.filter(
        business=business, kind=BusinessKind.LIQUOR, is_active=True, quantity_in_stock__gt=0
    ).order_by("name")

    # Get agents
    from django.contrib.auth import get_user_model

    User = get_user_model()
    agent_group_name = f"biz:{business.pk}:AGENT"
    agents = User.objects.filter(groups__name=agent_group_name).distinct().order_by("username")

    ctx.update(
        {
            "page_title": "Assign Stock",
            "products": products,
            "agents": agents,
        }
    )

    return render(request, "verticals/liquor/assignment_create.html", ctx)


# ==============================================================================
# AGENT: MY STOCK
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def my_stock(request):
    """
    Agent view: View my assigned stock and performance.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")

    # Get active assignments
    my_assignments = (
        LiquorStockAssignment.objects.filter(business=business, agent=request.user, status="ACTIVE")
        .select_related("product", "assigned_by")
        .order_by("-assigned_at")
    )

    # Get recent sold-out assignments (last 7 days)
    recent_soldout = (
        LiquorStockAssignment.objects.filter(
            business=business,
            agent=request.user,
            status="SOLD_OUT",
            assigned_at__gte=timezone.now() - timezone.timedelta(days=7),
        )
        .select_related("product")
        .order_by("-assigned_at")[:10]
    )

    # Get performance metrics
    performance = get_agent_performance(business=business, agent=request.user, days=30)

    # Today's performance
    today = timezone.now().date()
    today_recon = LiquorDailyReconciliation.objects.filter(business=business, agent=request.user, date=today).first()

    # Calculate totals from active assignments
    total_bottles = sum(a.bottles_remaining for a in my_assignments)
    total_value = sum(a.bottles_remaining * a.unit_sell_price for a in my_assignments)

    ctx.update(
        {
            "page_title": "My Assigned Stock",
            "my_assignments": my_assignments,
            "recent_soldout": recent_soldout,
            "total_bottles_in_hand": total_bottles,
            "total_inventory_value": total_value,
            "performance": performance,
            "today_recon": today_recon,
        }
    )

    return render(request, "verticals/liquor/my_stock.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
@require_POST
def return_stock(request, assignment_id):
    """
    Agent action: Return unsold bottles from an assignment.
    """
    business = get_active_business(request)

    try:
        bottles_count = int(request.POST.get("bottles_count", 0))

        # Get assignment
        assignment = get_object_or_404(LiquorStockAssignment, id=assignment_id, business=business, agent=request.user)

        # Return bottles
        result = return_bottles_to_stock(assignment=assignment, bottles_count=bottles_count, returned_by=request.user)

        messages.success(request, f"✅ Returned {bottles_count} bottles of {result['product'].name} to stock")

    except ValidationError as e:
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, f"Error returning stock: {e}")

    return redirect("verticals:liquor_my_stock")


# ==============================================================================
# MANAGER: RECONCILIATION
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def reconciliation_dashboard(request):
    """
    Manager view: Daily reconciliation dashboard.
    Shows all agents' performance for a specific date.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")

    # Permission check
    if not request.user.is_manager(business):
        messages.error(request, "Only managers can view reconciliation")
        return redirect("verticals:liquor_dashboard")

    # Get date (default today)
    date_str = request.GET.get("date")
    if date_str:
        try:
            date = timezone.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            date = timezone.now().date()
    else:
        date = timezone.now().date()

    # Get agents with assignments on this date
    from django.contrib.auth import get_user_model

    User = get_user_model()

    agent_ids = (
        LiquorStockAssignment.objects.filter(business=business, assigned_at__date=date)
        .values_list("agent_id", flat=True)
        .distinct()
    )

    agents = User.objects.filter(pk__in=agent_ids)

    # Generate reconciliation for each agent
    reconciliations = []
    for agent in agents:
        recon = generate_daily_reconciliation(business=business, agent=agent, date=date)
        reconciliations.append(
            {
                "agent": agent,
                "recon": recon,
                "assignments": LiquorStockAssignment.objects.filter(
                    business=business, agent=agent, assigned_at__date=date
                ).select_related("product"),
            }
        )

    # Summary stats
    total_assigned = sum(r["recon"].total_bottles_assigned for r in reconciliations)
    total_sold = sum(r["recon"].total_bottles_sold for r in reconciliations)
    total_revenue = sum(r["recon"].total_revenue for r in reconciliations)

    ctx.update(
        {
            "page_title": "Daily Reconciliation",
            "date": date,
            "reconciliations": reconciliations,
            "total_assigned": total_assigned,
            "total_sold": total_sold,
            "total_revenue": total_revenue,
        }
    )

    return render(request, "verticals/liquor/reconciliation.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
@require_POST
def finalize_reconciliation_view(request, reconciliation_id):
    """
    Manager action: Finalize a daily reconciliation.
    """
    business = get_active_business(request)

    # Permission check
    if not request.user.is_manager(business):
        messages.error(request, "Only managers can finalize reconciliation")
        return redirect("verticals:liquor_dashboard")

    try:
        notes = request.POST.get("notes", "").strip()

        recon = finalize_reconciliation(reconciliation_id=reconciliation_id, reconciled_by=request.user, notes=notes)

        messages.success(request, f"✅ Reconciliation for {recon.agent.username} on {recon.date} finalized")

    except PermissionDenied as e:
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, f"Error finalizing reconciliation: {e}")

    return redirect("verticals:liquor_reconciliation")


# ==============================================================================
# REPORTS
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def agent_performance_report(request):
    """
    Manager view: Agent performance report with rankings.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")

    # Permission check
    if not request.user.is_manager(business):
        messages.error(request, "Only managers can view performance reports")
        return redirect("verticals:liquor_dashboard")

    # Get time period
    days = int(request.GET.get("days", 30))

    # Get top performers
    top_agents = get_top_performing_agents(business=business, days=days, limit=20)

    ctx.update(
        {
            "page_title": "Agent Performance",
            "top_agents": top_agents,
            "days": days,
        }
    )

    return render(request, "verticals/liquor/agent_performance.html", ctx)


# ==============================================================================
# AJAX ENDPOINTS
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def api_product_stock(request, product_id):
    """
    AJAX: Get current stock level for a product.
    """
    business = get_active_business(request)

    try:
        product = MerchProduct.objects.get(id=product_id, business=business)

        return JsonResponse(
            {
                "success": True,
                "product_id": product.id,
                "name": product.name,
                "quantity_in_stock": product.quantity_in_stock or 0,
                "cost_price": float(product.cost_price or 0),
                "selling_price": float(product.selling_price or 0),
            }
        )

    except MerchProduct.DoesNotExist:
        return JsonResponse({"success": False, "error": "Product not found"}, status=404)

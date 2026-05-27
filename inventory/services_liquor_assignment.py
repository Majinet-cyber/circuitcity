"""
PHASE 6: Liquor Agent Assignment Service Layer
Handles stock assignment, reconciliation, and agent performance tracking.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional, Any
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied

from tenants.utils_roles import is_manager as check_is_manager
from inventory.models_liquor_assignment import (
    LiquorStockAssignment,
    LiquorDailyReconciliation,
    LiquorAgentTarget,
)
from inventory.models import MerchProduct


# ==============================================================================
# STOCK ASSIGNMENT
# ==============================================================================


@transaction.atomic
def assign_stock_to_agent(
    *, business, agent, product_id: int, bottles_count: int, assigned_by, notes: str = ""
) -> LiquorStockAssignment:
    """
    Assign bottles of a product to an agent.
    Manager-only operation.

    Args:
        business: Business instance
        agent: User instance (agent receiving stock)
        product_id: Product ID
        bottles_count: Number of bottles to assign
        assigned_by: User making the assignment (must be manager)
        notes: Optional notes

    Returns:
        LiquorStockAssignment instance

    Raises:
        PermissionDenied: If assigned_by is not a manager
        ValidationError: If validation fails
    """
    # Check permissions - use helper function
    if not check_is_manager(assigned_by, business):
        raise PermissionDenied("Only managers can assign stock to agents")

    # Validate bottles count
    if bottles_count <= 0:
        raise ValidationError("Bottles count must be positive")

    # Get product
    product = MerchProduct.objects.select_for_update().get(id=product_id, business=business)

    # Check stock availability
    available_bottles = product.quantity_in_stock or 0
    if available_bottles < bottles_count:
        raise ValidationError(f"Insufficient stock. Available: {available_bottles}, Requested: {bottles_count}")

    # Deduct from main stock
    product.quantity_in_stock -= bottles_count
    product.save(update_fields=["quantity_in_stock"])

    # Create assignment
    assignment = LiquorStockAssignment.objects.create(
        business=business,
        agent=agent,
        product=product,
        bottles_assigned=bottles_count,
        bottles_sold=0,
        bottles_returned=0,
        unit_cost_price=product.cost_price or Decimal("0.00"),
        unit_sell_price=product.selling_price or Decimal("0.00"),
        status="ACTIVE",
        assigned_by=assigned_by,
        notes=notes,
    )

    return assignment


@transaction.atomic
def record_bottle_sale(*, assignment: LiquorStockAssignment, bottles_sold: int = 1) -> LiquorStockAssignment:
    """
    Record that an agent sold bottles from their assignment.

    Args:
        assignment: LiquorStockAssignment instance
        bottles_sold: Number of bottles sold (default 1)

    Returns:
        Updated assignment

    Raises:
        ValidationError: If trying to sell more than available
    """
    assignment = LiquorStockAssignment.objects.select_for_update().get(pk=assignment.pk)

    remaining = assignment.bottles_remaining
    if bottles_sold > remaining:
        raise ValidationError(f"Cannot sell {bottles_sold} bottles. Only {remaining} remaining.")

    assignment.bottles_sold += bottles_sold

    # Update status if sold out
    if assignment.bottles_remaining == 0:
        assignment.status = "SOLD_OUT"

    assignment.save()
    return assignment


@transaction.atomic
def return_bottles_to_stock(*, assignment: LiquorStockAssignment, bottles_count: int, returned_by) -> Dict[str, Any]:
    """
    Return unsold bottles from agent back to main stock.

    Args:
        assignment: LiquorStockAssignment instance
        bottles_count: Number of bottles to return
        returned_by: User returning the stock

    Returns:
        dict with assignment and product info

    Raises:
        ValidationError: If trying to return more than available
    """
    assignment = LiquorStockAssignment.objects.select_for_update().get(pk=assignment.pk)
    product = MerchProduct.objects.select_for_update().get(pk=assignment.product_id)

    remaining = assignment.bottles_remaining
    if bottles_count > remaining:
        raise ValidationError(f"Cannot return {bottles_count} bottles. Only {remaining} remaining.")

    # Update assignment
    assignment.bottles_returned += bottles_count
    if assignment.bottles_remaining == 0:
        assignment.status = "RETURNED"
    assignment.save()

    # Return to main stock
    product.quantity_in_stock += bottles_count
    product.save(update_fields=["quantity_in_stock"])

    return {
        "assignment": assignment,
        "product": product,
        "bottles_returned": bottles_count,
    }


# ==============================================================================
# RECONCILIATION
# ==============================================================================


def generate_daily_reconciliation(*, business, agent, date=None) -> LiquorDailyReconciliation:
    """
    Generate daily reconciliation report for an agent.
    Computes total assignments, sales, returns for the day.

    Args:
        business: Business instance
        agent: User instance
        date: Date to reconcile (defaults to today)

    Returns:
        LiquorDailyReconciliation instance
    """
    if date is None:
        date = timezone.now().date()

    # Get or create reconciliation record
    recon, created = LiquorDailyReconciliation.objects.get_or_create(
        business=business,
        agent=agent,
        date=date,
        defaults={
            "total_bottles_assigned": 0,
            "total_bottles_sold": 0,
            "total_bottles_returned": 0,
            "total_revenue": Decimal("0.00"),
            "total_profit": Decimal("0.00"),
        },
    )

    # Get assignments for this day
    assignments = LiquorStockAssignment.objects.filter(business=business, agent=agent, assigned_at__date=date)

    # Compute totals
    total_assigned = sum(a.bottles_assigned for a in assignments)
    total_sold = sum(a.bottles_sold for a in assignments)
    total_returned = sum(a.bottles_returned for a in assignments)
    total_revenue = sum(a.actual_revenue for a in assignments)
    total_profit = sum(a.expected_profit for a in assignments)

    # Update reconciliation
    recon.total_bottles_assigned = total_assigned
    recon.total_bottles_sold = total_sold
    recon.total_bottles_returned = total_returned
    recon.total_revenue = total_revenue
    recon.total_profit = total_profit
    recon.save()

    return recon


@transaction.atomic
def finalize_reconciliation(*, reconciliation_id: int, reconciled_by, notes: str = "") -> LiquorDailyReconciliation:
    """
    Finalize a daily reconciliation.
    Marks as reconciled and updates all associated assignments.

    Args:
        reconciliation_id: ID of reconciliation to finalize
        reconciled_by: User finalizing (must be manager)
        notes: Optional notes

    Returns:
        Updated reconciliation

    Raises:
        PermissionDenied: If not a manager
    """
    recon = LiquorDailyReconciliation.objects.select_for_update().get(pk=reconciliation_id)

    # Check permissions - use helper function
    if not check_is_manager(reconciled_by, recon.business):
        raise PermissionDenied("Only managers can finalize reconciliations")

    # Mark reconciliation as complete
    recon.is_reconciled = True
    recon.reconciled_at = timezone.now()
    recon.reconciled_by = reconciled_by
    recon.notes = notes
    recon.save()

    # Update all assignments from this day
    assignments = LiquorStockAssignment.objects.filter(
        business=recon.business, agent=recon.agent, assigned_at__date=recon.date, status__in=["ACTIVE", "SOLD_OUT"]
    )

    for assignment in assignments:
        assignment.status = "RECONCILED"
        assignment.reconciled_at = timezone.now()
        assignment.reconciled_by = reconciled_by
        assignment.save()

    return recon


# ==============================================================================
# AGENT PERFORMANCE
# ==============================================================================


def get_agent_performance(*, business, agent, days=30) -> Dict[str, Any]:
    """
    Get comprehensive performance metrics for an agent.

    Args:
        business: Business instance
        agent: User instance
        days: Number of days to look back

    Returns:
        dict with performance metrics
    """
    from django.db.models import Sum

    cutoff = timezone.now() - timezone.timedelta(days=days)

    # Get assignments
    assignments = LiquorStockAssignment.objects.filter(business=business, agent=agent, assigned_at__gte=cutoff)

    # Active assignments (currently assigned)
    active_assignments = assignments.filter(status="ACTIVE")

    # Compute metrics
    total_assigned = assignments.aggregate(total=Sum("bottles_assigned"))["total"] or 0
    total_sold = assignments.aggregate(total=Sum("bottles_sold"))["total"] or 0
    total_returned = assignments.aggregate(total=Sum("bottles_returned"))["total"] or 0

    # CRITICAL FIX: Safely compute revenue and profit (handle None values)
    total_revenue = Decimal("0.00")
    total_profit = Decimal("0.00")
    for a in assignments:
        try:
            rev = a.actual_revenue
            if rev is not None:
                total_revenue += Decimal(str(rev))
        except (ValueError, TypeError, AttributeError):
            pass
        
        try:
            prof = a.expected_profit
            if prof is not None:
                total_profit += Decimal(str(prof))
        except (ValueError, TypeError, AttributeError):
            pass

    # Sell-through rate
    sell_through = Decimal("0.00")
    if total_assigned > 0:
        sell_through = (Decimal(str(total_sold)) / Decimal(str(total_assigned))) * Decimal("100.00")

    # Current inventory - safely handle None values
    current_bottles = 0
    current_value = Decimal("0.00")
    for a in active_assignments:
        try:
            remaining = a.bottles_remaining
            if remaining is not None:
                current_bottles += int(remaining)
                
                # Safe multiplication for value
                unit_price = a.unit_sell_price
                if unit_price is not None:
                    current_value += Decimal(str(remaining)) * Decimal(str(unit_price))
        except (ValueError, TypeError, AttributeError):
            pass

    return {
        "period_days": days,
        "total_bottles_assigned": total_assigned,
        "total_bottles_sold": total_sold,
        "total_bottles_returned": total_returned,
        "total_revenue": total_revenue,
        "total_profit": total_profit,
        "sell_through_rate": sell_through,
        "current_bottles_in_hand": current_bottles,
        "current_inventory_value": current_value,
        "active_assignments_count": active_assignments.count(),
    }


def get_top_performing_agents(*, business, days=30, limit=10) -> List[Dict[str, Any]]:
    """
    Get top performing agents by revenue.

    Args:
        business: Business instance
        days: Number of days to look back
        limit: Max number of agents to return

    Returns:
        List of dicts with agent performance
    """
    from django.contrib.auth import get_user_model
    from django.db.models import Sum

    User = get_user_model()
    cutoff = timezone.now() - timezone.timedelta(days=days)

    # Get all agents with assignments
    agent_ids = (
        LiquorStockAssignment.objects.filter(business=business, assigned_at__gte=cutoff)
        .values_list("agent_id", flat=True)
        .distinct()
    )

    # Compute performance for each
    agent_performance = []
    for agent_id in agent_ids:
        agent = User.objects.get(pk=agent_id)
        perf = get_agent_performance(business=business, agent=agent, days=days)
        perf["agent"] = agent
        agent_performance.append(perf)

    # Sort by revenue (descending)
    agent_performance.sort(key=lambda x: x["total_revenue"], reverse=True)

    return agent_performance[:limit]

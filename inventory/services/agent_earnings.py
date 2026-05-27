# inventory/services/agent_earnings.py
"""
Agent Earnings Service - Single source of truth for agent performance metrics.

Computes agent rankings by commission earnings, with support for:
- Date range filtering (Today, Last 7 Days, This Month, Custom)
- Units sold, revenue, and commission tracking
- Manager and agent views (scoped to business)

IMPORTANT: This service queries BOTH wallet models and sales models to support
different verticals:
- WalletTransaction (old model) + AgentWalletTransaction (new model) for commissions
- Sale model (for some verticals) + InventoryItem (for Phones vertical) for sales data

This ensures the Top Agents card works across all verticals including Phones.
"""
from __future__ import annotations

from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db.models import Sum, Count, Q, Max
from django.db.models.functions import Coalesce
from django.utils import timezone

User = get_user_model()


@dataclass
class AgentEarningRow:
    """Single agent's earnings data for a period."""

    agent_id: int
    agent_name: str
    agent_username: str
    units_sold: int
    total_revenue: Decimal
    total_commission: Decimal
    last_sale_at: Optional[datetime]
    rank: int = 0  # Computed after sorting


def get_agent_earnings(
    business,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    location=None,
    agent_id: Optional[int] = None,
) -> List[AgentEarningRow]:
    """
    Get agent earnings data for a business and date range.

    This is the SINGLE SOURCE OF TRUTH for agent performance metrics.
    Returns agents ranked by total commission (desc), then by revenue (desc).

    Args:
        business: Business instance (required for scoping)
        start_date: Start date for filtering (optional, defaults to month start)
        end_date: End date for filtering (optional, defaults to today)
        location: Location instance for additional scoping (optional)
        agent_id: If provided, returns data for a single agent only

    Returns:
        List of AgentEarningRow objects, sorted by total_commission DESC
    """
    if not business:
        return []

    # Default date range: this month
    if not start_date:
        now = timezone.now()
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if not end_date:
        end_date = timezone.now()

    # Convert dates to datetime if needed
    if isinstance(start_date, date) and not isinstance(start_date, datetime):
        start_date = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
    if isinstance(end_date, date) and not isinstance(end_date, datetime):
        end_date = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

    # Query commissions from BOTH WalletTransaction AND AgentWalletTransaction
    # (Different systems use different wallet models)
    commission_map = {}

    # 1) Query old WalletTransaction model
    try:
        from wallet.models import WalletTransaction, Ledger, TxnType

        commission_qs = WalletTransaction.objects.filter(
            business=business,
            ledger=Ledger.AGENT,
            type=TxnType.COMMISSION,
            effective_date__gte=start_date.date() if hasattr(start_date, "date") else start_date,
            effective_date__lte=end_date.date() if hasattr(end_date, "date") else end_date,
        ).select_related("agent")

        # Optional: filter by specific agent
        if agent_id:
            commission_qs = commission_qs.filter(agent_id=agent_id)

        # Group by agent and sum commissions
        agent_commissions = commission_qs.values(
            "agent_id", "agent__first_name", "agent__last_name", "agent__username"
        ).annotate(total_commission=Coalesce(Sum("amount"), Decimal("0.00")))

        # Build a map of agent_id -> commission
        for row in agent_commissions:
            aid = row["agent_id"]
            if aid:
                commission_map[aid] = Decimal(str(row["total_commission"] or 0))

    except (ImportError, Exception) as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(f"WalletTransaction not available: {e}")

    # 2) Query new AgentWalletTransaction model (used by phones)
    try:
        from wallet.agent_models import AgentWalletTransaction, AgentWalletTransactionType
        from tenants.models import Membership

        # Get all memberships for this business
        memberships = Membership.objects.filter(
            business=business,
            role="AGENT",
        )

        if agent_id:
            memberships = memberships.filter(user_id=agent_id)

        # Get wallets for these memberships
        from wallet.agent_models import AgentWallet

        wallets = AgentWallet.objects.filter(membership__in=memberships).select_related("membership__user")

        # Query commission transactions
        agent_txn_qs = AgentWalletTransaction.objects.filter(
            wallet__in=wallets,
            transaction_type=AgentWalletTransactionType.COMMISSION_SALE,
            is_debit=False,
            effective_date__gte=start_date.date() if hasattr(start_date, "date") else start_date,
            effective_date__lte=end_date.date() if hasattr(end_date, "date") else end_date,
        ).select_related("wallet__membership__user")

        # Group by agent
        for txn in agent_txn_qs:
            agent = txn.wallet.membership.user
            aid = agent.id
            commission_map[aid] = commission_map.get(aid, Decimal("0.00")) + Decimal(str(txn.amount or 0))

    except (ImportError, Exception) as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(f"AgentWalletTransaction not available: {e}")

    # Query sales data from BOTH Sale model AND InventoryItem (for Phones vertical)
    # Build a unified agent_id -> stats dictionary
    agent_stats = {}

    # 1) Query Sale model (used by some verticals)
    try:
        from sales.models import Sale

        sales_qs = Sale.objects.filter(
            location__business=business,
            created_at__gte=start_date,
            created_at__lt=end_date,
        ).select_related("agent", "location")

        # Optional: filter by location
        if location:
            sales_qs = sales_qs.filter(location=location)

        # Optional: filter by specific agent
        if agent_id:
            sales_qs = sales_qs.filter(agent_id=agent_id)

        # Group by agent and aggregate
        sale_data = sales_qs.values("agent_id", "agent__first_name", "agent__last_name", "agent__username").annotate(
            units_sold=Count("id"), total_revenue=Coalesce(Sum("price"), Decimal("0.00")), last_sale_at=Max("sold_at")
        )

        for row in sale_data:
            aid = row["agent_id"]
            if aid:
                agent_stats[aid] = {
                    "agent_id": aid,
                    "agent__first_name": row.get("agent__first_name") or "",
                    "agent__last_name": row.get("agent__last_name") or "",
                    "agent__username": row.get("agent__username") or "",
                    "units_sold": row["units_sold"],
                    "total_revenue": row["total_revenue"],
                    "last_sale_at": row.get("last_sale_at"),
                }

    except (ImportError, Exception) as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(f"Sale model not available or query failed: {e}")

    # 2) Query InventoryItem (Phones vertical tracks sales this way)
    try:
        from inventory.models import InventoryItem

        # Filter sold items by business and date range
        inv_qs = InventoryItem.objects.filter(
            business=business,
            status="SOLD",
            sold_at__isnull=False,
            sold_at__gte=start_date,
            sold_at__lt=end_date,
        ).select_related("assigned_agent")

        # Optional: filter by location
        if location:
            inv_qs = inv_qs.filter(current_location=location)

        # Optional: filter by specific agent
        if agent_id:
            # InventoryItem uses assigned_agent field
            inv_qs = inv_qs.filter(assigned_agent_id=agent_id)

        # Filter to only items with an agent assigned
        inv_qs = inv_qs.filter(assigned_agent__isnull=False)

        # Group by agent and aggregate
        inv_data = inv_qs.values(
            "assigned_agent_id", "assigned_agent__first_name", "assigned_agent__last_name", "assigned_agent__username"
        ).annotate(
            units_sold=Count("id"),
            total_revenue=Coalesce(Sum("selling_price"), Decimal("0.00")),
            last_sale_at=Max("sold_at"),
        )

        # Merge with existing agent_stats
        for row in inv_data:
            aid = row["assigned_agent_id"]
            if aid:
                if aid in agent_stats:
                    # Agent has sales from both sources - merge them
                    agent_stats[aid]["units_sold"] += row["units_sold"]
                    agent_stats[aid]["total_revenue"] += row["total_revenue"]
                    # Use the latest sale date
                    if row.get("last_sale_at"):
                        existing_date = agent_stats[aid].get("last_sale_at")
                        if not existing_date or row["last_sale_at"] > existing_date:
                            agent_stats[aid]["last_sale_at"] = row["last_sale_at"]
                else:
                    # New agent from InventoryItem sales
                    agent_stats[aid] = {
                        "agent_id": aid,
                        "agent__first_name": row.get("assigned_agent__first_name") or "",
                        "agent__last_name": row.get("assigned_agent__last_name") or "",
                        "agent__username": row.get("assigned_agent__username") or "",
                        "units_sold": row["units_sold"],
                        "total_revenue": row["total_revenue"],
                        "last_sale_at": row.get("last_sale_at"),
                    }

    except (ImportError, Exception) as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(f"InventoryItem query failed: {e}")

    # Convert agent_stats dict to list format
    agent_sales = list(agent_stats.values())

    # Build result rows
    results: List[AgentEarningRow] = []
    agent_ids_seen = set()

    for row in agent_sales:
        agent_id = row["agent_id"]
        if not agent_id:
            continue

        agent_ids_seen.add(agent_id)

        first_name = row.get("agent__first_name") or ""
        last_name = row.get("agent__last_name") or ""
        username = row.get("agent__username") or "Unknown"
        agent_name = f"{first_name} {last_name}".strip() or username

        results.append(
            AgentEarningRow(
                agent_id=agent_id,
                agent_name=agent_name,
                agent_username=username,
                units_sold=row["units_sold"],
                total_revenue=Decimal(str(row["total_revenue"] or 0)),
                total_commission=commission_map.get(agent_id, Decimal("0.00")),
                last_sale_at=row.get("last_sale_at"),
            )
        )

    # Also include agents who have commissions but no sales in this period
    # (edge case: e.g., late commission adjustments)
    for agent_id, commission in commission_map.items():
        if agent_id not in agent_ids_seen and commission > 0:
            try:
                agent = User.objects.get(id=agent_id)
                agent_name = agent.get_full_name() or agent.username
                results.append(
                    AgentEarningRow(
                        agent_id=agent_id,
                        agent_name=agent_name,
                        agent_username=agent.username,
                        units_sold=0,
                        total_revenue=Decimal("0.00"),
                        total_commission=commission,
                        last_sale_at=None,
                    )
                )
            except User.DoesNotExist:
                pass

    # Sort by commission (desc), then revenue (desc), then name (asc)
    results.sort(key=lambda x: (-x.total_commission, -x.total_revenue, x.agent_name.lower()))

    # Assign ranks
    for idx, row in enumerate(results, start=1):
        row.rank = idx

    return results


def get_top_agents(
    business,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    location=None,
    limit: int = 5,
) -> List[AgentEarningRow]:
    """
    Get top N agents by commission for a period.

    Convenience function for dashboard "Top Agents" cards.
    """
    all_agents = get_agent_earnings(
        business=business,
        start_date=start_date,
        end_date=end_date,
        location=location,
    )
    return all_agents[:limit]


def get_agent_rank_in_period(
    business,
    agent_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Optional[int]:
    """
    Get an agent's rank for a specific period.

    Returns:
        The agent's rank (1-indexed) or None if agent has no earnings
    """
    all_agents = get_agent_earnings(
        business=business,
        start_date=start_date,
        end_date=end_date,
    )

    for row in all_agents:
        if row.agent_id == agent_id:
            return row.rank

    return None


def format_rank(rank: int) -> str:
    """Format rank with ordinal suffix: 1st, 2nd, 3rd, 4th, etc."""
    if 10 <= rank % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(rank % 10, "th")
    return f"{rank}{suffix}"

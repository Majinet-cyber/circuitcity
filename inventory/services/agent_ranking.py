# inventory/services/agent_ranking.py
"""
Agent ranking service for phones vertical.
Computes sales-based leaderboard per business.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Sum, Q, Count
from django.utils import timezone

from sales.models import Sale
from tenants.models import Business, Membership

User = get_user_model()


def compute_agent_ranking(
    business: Business,
    days: Optional[int] = None,
    agent_user=None,
) -> Dict:
    """
    Compute agent ranking by NUMBER OF SALES (not revenue) within a business.

    Args:
        business: Business instance to scope the ranking
        days: Number of days to look back (None = all-time)
        agent_user: If provided, returns ranking info for this specific agent

    Returns:
        {
            "rankings": [{"agent_id": int, "name": str, "total_sales": Decimal, "rank": int, "sales_count": int}],
            "agent_rank": int|None,  # rank of the specific agent if provided
            "agent_total": Decimal|None,  # total sales of the specific agent
            "agent_above": dict|None,  # agent ranked above
            "agent_below": dict|None,  # agent ranked below
            "period": str,  # "all-time" or "last 30 days"
        }
    """
    # Build the queryset
    sales_qs = Sale.objects.filter(location__business=business).select_related("agent")

    if days:
        cutoff = timezone.now() - timedelta(days=days)
        sales_qs = sales_qs.filter(sold_at__gte=cutoff.date())
        period = f"last {days} days"
    else:
        period = "all-time"

    # Aggregate by agent
    # Rank by sales count (primary), then total_sales as tie-breaker (secondary)
    agent_totals = (
        sales_qs.values("agent_id", "agent__first_name", "agent__last_name", "agent__username")
        .annotate(
            total_sales=Sum("price"),
            sales_count=Count("id"),
        )
        .order_by("-sales_count", "-total_sales")
    )

    rankings = []
    agent_rank = None
    agent_total = None
    agent_above = None
    agent_below = None

    for idx, row in enumerate(agent_totals, start=1):
        name = f"{row['agent__first_name']} {row['agent__last_name']}".strip() or row["agent__username"]
        entry = {
            "agent_id": row["agent_id"],
            "name": name,
            "total_sales": row["total_sales"] or Decimal("0"),
            "sales_count": row["sales_count"],
            "rank": idx,
        }
        rankings.append(entry)

        # Track agent position if specified
        if agent_user and row["agent_id"] == agent_user.id:
            agent_rank = idx
            agent_total = row["total_sales"] or Decimal("0")

            # Find neighbors
            if idx > 1:
                agent_above = rankings[idx - 2]  # previous entry
            if idx < len(list(agent_totals)):
                # Will be filled in next iteration or we fetch explicitly
                pass

    # Fill agent_below if needed
    if agent_rank and agent_rank < len(rankings):
        agent_below = rankings[agent_rank]  # next entry (0-indexed)

    return {
        "rankings": rankings,
        "agent_rank": agent_rank,
        "agent_total": agent_total,
        "agent_above": agent_above,
        "agent_below": agent_below,
        "period": period,
    }


def format_rank(rank: int) -> str:
    """Format rank with ordinal suffix: 1st, 2nd, 3rd, 4th, etc."""
    if 10 <= rank % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(rank % 10, "th")
    return f"{rank}{suffix}"

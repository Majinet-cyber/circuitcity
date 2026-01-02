"""
Gamification utilities for agent rankings and milestones.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from django.contrib.auth import get_user_model
from django.db.models import Count, Sum, Q

from tenants.models import Business, Membership
from sales.models import Sale

User = get_user_model()


@dataclass
class AgentRank:
    """Agent ranking data for gamification."""

    user_id: int
    username: str
    full_name: str
    rank: int
    sales_count: int
    revenue: float
    behind_count: int  # How many sales behind the next rank


def get_agent_rankings(
    business: Business, location=None, start_date=None, end_date=None, limit: int = 10
) -> List[AgentRank]:
    """
    Compute agent rankings for a given business and time period.

    Args:
        business: Business instance to scope rankings
        location: Optional location to further scope (None = all locations)
        start_date: Optional start date (inclusive)
        end_date: Optional end date (exclusive)
        limit: Maximum number of agents to return (default 10)

    Returns:
        List of AgentRank objects, ordered by sales_count descending
    """
    # Get all agents for this business
    memberships = Membership.objects.filter(business=business, role="AGENT").select_related("user")

    if location:
        memberships = memberships.filter(location=location)

    # Build sales queryset
    sales_qs = Sale.objects.filter(agent__in=[m.user for m in memberships])

    if start_date:
        sales_qs = sales_qs.filter(sold_at__gte=start_date)
    if end_date:
        sales_qs = sales_qs.filter(sold_at__lt=end_date)

    # Aggregate by agent
    agent_stats = (
        sales_qs.values("agent").annotate(sales_count=Count("id"), total_revenue=Sum("price")).order_by("-sales_count")
    )

    # Build rankings
    rankings = []
    rank = 1
    prev_sales_count = None

    for i, stats in enumerate(agent_stats[:limit]):
        user_id = stats["agent"]
        sales_count = stats["sales_count"] or 0
        revenue = float(stats["total_revenue"] or 0)

        try:
            user = User.objects.get(id=user_id)
            username = user.username
            full_name = user.get_full_name() or username
        except User.DoesNotExist:
            username = f"User {user_id}"
            full_name = username

        # Calculate "behind count" (how many sales behind the person above)
        if prev_sales_count is not None:
            behind_count = prev_sales_count - sales_count
        else:
            behind_count = 0  # First place has no one above

        rankings.append(
            AgentRank(
                user_id=user_id,
                username=username,
                full_name=full_name,
                rank=rank,
                sales_count=sales_count,
                revenue=revenue,
                behind_count=behind_count,
            )
        )

        prev_sales_count = sales_count
        rank += 1

    return rankings


def get_agent_rank_for_user(
    user_id: int, business: Business, location=None, start_date=None, end_date=None
) -> Optional[AgentRank]:
    """
    Get the ranking info for a specific user.

    Returns:
        AgentRank if user has sales, None otherwise
    """
    # Get full rankings (could optimize this later with a specific query)
    all_rankings = get_agent_rankings(
        business=business,
        location=location,
        start_date=start_date,
        end_date=end_date,
        limit=1000,  # Get all to find user's position
    )

    for ranking in all_rankings:
        if ranking.user_id == user_id:
            return ranking

    return None


def get_gamification_message(rank: Optional[AgentRank]) -> str:
    """
    Generate a motivational gamification message for an agent.

    Args:
        rank: Agent's ranking info (None if no sales yet)

    Returns:
        Motivational message string
    """
    if not rank:
        return "Start selling to join the leaderboard! 🚀"

    if rank.rank == 1:
        return f"🏆 You're #1 this month with {rank.sales_count} sales - don't let anyone catch you!"

    if rank.rank <= 3:
        msg = f"🥈 You're #{rank.rank} with {rank.sales_count} sales this month."
        if rank.behind_count > 0:
            msg += f" Only {rank.behind_count} sales behind #{rank.rank - 1} - keep going!"
        return msg

    msg = f"You're #{rank.rank} with {rank.sales_count} sales this month."
    if rank.behind_count > 0:
        msg += f" Just {rank.behind_count} sales behind #{rank.rank - 1}!"
    return msg


# Milestone thresholds
SALES_MILESTONES = [
    (10, "Rising Star", "⭐"),
    (25, "High Achiever", "🌟"),
    (50, "Sales Champion", "🏅"),
    (100, "Elite Performer", "💎"),
    (250, "Sales Legend", "👑"),
]


def get_current_milestone(sales_count: int) -> Optional[tuple[int, str, str]]:
    """
    Get the current milestone for a given sales count.

    Returns:
        (threshold, name, emoji) or None if no milestone reached
    """
    achieved = None
    for threshold, name, emoji in SALES_MILESTONES:
        if sales_count >= threshold:
            achieved = (threshold, name, emoji)
        else:
            break
    return achieved


def get_next_milestone(sales_count: int) -> Optional[tuple[int, str, str, int]]:
    """
    Get the next milestone to reach.

    Returns:
        (threshold, name, emoji, sales_needed) or None if all milestones achieved
    """
    for threshold, name, emoji in SALES_MILESTONES:
        if sales_count < threshold:
            sales_needed = threshold - sales_count
            return (threshold, name, emoji, sales_needed)
    return None


def check_and_award_milestones(user, business, sales_count, year=None, month=None):
    """
    Check if user has reached any new milestones and award them.

    Args:
        user: User instance
        business: Business instance
        sales_count: Current sales count for the period
        year: Optional year for period-specific milestones
        month: Optional month for period-specific milestones

    Returns:
        List of newly achieved milestones
    """
    from hq.models import AgentMilestone

    newly_achieved = []

    for threshold, name, emoji in SALES_MILESTONES:
        if sales_count >= threshold:
            milestone_type = f"sales_{threshold}"

            # Check if milestone already exists
            existing = AgentMilestone.objects.filter(
                user=user, business=business, milestone_type=milestone_type, year=year, month=month
            ).exists()

            if not existing:
                milestone = AgentMilestone.objects.create(
                    user=user,
                    business=business,
                    milestone_type=milestone_type,
                    milestone_name=name,
                    milestone_emoji=emoji,
                    sales_count=sales_count,
                    year=year,
                    month=month,
                )
                newly_achieved.append(milestone)

    return newly_achieved


def get_user_milestones(user, business, year=None, month=None):
    """
    Get all milestones for a user in a given period.

    Returns:
        QuerySet of AgentMilestone objects
    """
    from hq.models import AgentMilestone

    qs = AgentMilestone.objects.filter(user=user, business=business)

    if year is not None:
        qs = qs.filter(year=year)
    if month is not None:
        qs = qs.filter(month=month)

    return qs.order_by("-sales_count")

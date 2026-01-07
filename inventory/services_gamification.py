"""
PHASE 5: Gamification Service Layer
Handles XP calculations, badge awards, streak updates, and leaderboard generation.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Any
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.contrib.auth import get_user_model

from inventory.models_gamification import (
    AgentStreak,
    AgentXP,
    Badge,
    AgentBadge,
    DailyLeaderboard,
)

User = get_user_model()


# ==============================================================================
# XP REWARDS (CONFIGURABLE)
# ==============================================================================

XP_REWARDS = {
    "grocery_sale": 10,  # Per sale
    "grocery_sale_revenue_bonus": 0.01,  # 0.01 XP per MK 1 revenue
    "stock_in": 5,  # Per stock-in action
    "streak_bonus": 20,  # Bonus for maintaining streak
    "first_sale_of_day": 15,  # First sale of the day
}


# ==============================================================================
# STREAK MANAGEMENT
# ==============================================================================


def record_agent_activity(*, business, agent, activity_date=None) -> AgentStreak:
    """
    Record agent activity and update streak.
    Call this after any qualifying activity (e.g. sale, stock-in).
    """
    if activity_date is None:
        activity_date = timezone.now().date()

    streak, created = AgentStreak.objects.get_or_create(
        business=business,
        agent=agent,
        defaults={
            "current_streak_days": 0,
            "longest_streak_days": 0,
        },
    )

    streak.record_activity(activity_date)
    return streak


# ==============================================================================
# XP MANAGEMENT
# ==============================================================================


def award_xp(*, business, agent, amount: int, reason: str = "") -> Dict[str, Any]:
    """
    Award XP to an agent and return level-up info.

    Returns:
        {
            "xp_gained": int,
            "total_xp": int,
            "xp_today": int,
            "level": int,
            "level_up": bool,
            "old_level": int,
        }
    """
    xp_record, created = AgentXP.objects.get_or_create(
        business=business,
        agent=agent,
        defaults={
            "total_xp": 0,
            "current_level": 1,
            "xp_today": 0,
        },
    )

    result = xp_record.add_xp(amount, reason)
    return result


def calculate_sale_xp(sale_revenue: Decimal, is_first_today: bool = False) -> int:
    """
    Calculate XP for a grocery sale.

    Args:
        sale_revenue: Total revenue from the sale
        is_first_today: Whether this is the agent's first sale today

    Returns:
        Total XP to award
    """
    xp = XP_REWARDS["grocery_sale"]

    # Revenue bonus
    xp += int(sale_revenue * Decimal(str(XP_REWARDS["grocery_sale_revenue_bonus"])))

    # First sale bonus
    if is_first_today:
        xp += XP_REWARDS["first_sale_of_day"]

    return xp


@transaction.atomic
def process_sale_gamification(*, business, agent, sale_revenue: Decimal, sale_date=None) -> Dict[str, Any]:
    """
    Process all gamification for a sale (XP, streak, badges).
    Call this after a grocery sale is completed.

    Returns:
        {
            "xp": {...},  # XP result
            "streak": AgentStreak,
            "badges_earned": [Badge, ...],
            "show_celebration": bool,
        }
    """
    if sale_date is None:
        sale_date = timezone.now().date()

    # Update streak
    streak = record_agent_activity(business=business, agent=agent, activity_date=sale_date)

    # Check if first sale today
    from inventory.models import GrocerySale

    today_sales_count = GrocerySale.objects.filter(business=business, sold_by=agent, sold_at__date=sale_date).count()
    is_first_today = today_sales_count == 1

    # Calculate and award XP
    xp_amount = calculate_sale_xp(sale_revenue, is_first_today)
    xp_result = award_xp(business=business, agent=agent, amount=xp_amount, reason=f"Sale (MK {sale_revenue})")

    # Check for badge eligibility
    badges_earned = check_and_award_badges(business=business, agent=agent, trigger="sale")

    # Determine if we should show celebration UI
    show_celebration = (
        xp_result.get("level_up", False)
        or len(badges_earned) > 0
        or streak.current_streak_days % 7 == 0  # Milestone streak
    )

    return {
        "xp": xp_result,
        "streak": streak,
        "badges_earned": badges_earned,
        "show_celebration": show_celebration,
    }


# ==============================================================================
# BADGE SYSTEM
# ==============================================================================


def check_and_award_badges(*, business, agent, trigger: str) -> List[Badge]:
    """
    Check if agent qualifies for any new badges and award them.

    Args:
        business: Business instance
        agent: User instance
        trigger: What triggered the check ("sale", "streak", etc.)

    Returns:
        List of newly earned badges
    """
    from inventory.models import GrocerySale

    newly_earned = []

    # Get agent's existing badges
    earned_badge_ids = AgentBadge.objects.filter(business=business, agent=agent).values_list("badge_id", flat=True)

    # Check each badge
    all_badges = Badge.objects.all()

    for badge in all_badges:
        if badge.id in earned_badge_ids:
            continue  # Already earned

        # Check eligibility based on badge code
        if _check_badge_eligibility(badge, business, agent):
            # Award badge
            AgentBadge.objects.create(business=business, agent=agent, badge=badge)

            # Award XP
            if badge.xp_reward > 0:
                award_xp(business=business, agent=agent, amount=badge.xp_reward, reason=f"Badge: {badge.name}")

            newly_earned.append(badge)

    return newly_earned


def _check_badge_eligibility(badge: Badge, business, agent) -> bool:
    """
    Check if an agent is eligible for a specific badge.
    Extensible badge logic.
    """
    from inventory.models import GrocerySale

    code = badge.code

    # First sale
    if code == "first_sale":
        return GrocerySale.objects.filter(business=business, sold_by=agent).exists()

    # 10 sales
    if code == "sales_10":
        return GrocerySale.objects.filter(business=business, sold_by=agent).count() >= 10

    # 50 sales
    if code == "sales_50":
        return GrocerySale.objects.filter(business=business, sold_by=agent).count() >= 50

    # 100 sales
    if code == "sales_100":
        return GrocerySale.objects.filter(business=business, sold_by=agent).count() >= 100

    # 7-day streak
    if code == "streak_7":
        streak = AgentStreak.objects.filter(business=business, agent=agent).first()
        return streak and streak.current_streak_days >= 7

    # 30-day streak
    if code == "streak_30":
        streak = AgentStreak.objects.filter(business=business, agent=agent).first()
        return streak and streak.current_streak_days >= 30

    # Revenue milestone (MK 1M)
    if code == "revenue_1m":
        total_revenue = GrocerySale.objects.filter(business=business, sold_by=agent).aggregate(
            total=Sum("total_price")
        )["total"] or Decimal("0")
        return total_revenue >= Decimal("1000000")

    # Level 10
    if code == "level_10":
        xp_record = AgentXP.objects.filter(business=business, agent=agent).first()
        return xp_record and xp_record.current_level >= 10

    return False


# ==============================================================================
# LEADERBOARD
# ==============================================================================


def generate_daily_leaderboard(*, business, date=None) -> List[DailyLeaderboard]:
    """
    Generate leaderboard for a specific date.
    Should be run nightly or on-demand.

    Returns:
        List of DailyLeaderboard entries (top 10)
    """
    from inventory.models import GrocerySale
    from django.db.models import Sum, Count

    if date is None:
        date = timezone.now().date()

    # Get sales for the date
    sales_data = (
        GrocerySale.objects.filter(business=business, sold_at__date=date)
        .values("sold_by")
        .annotate(
            sales_count=Count("id"),
            revenue=Sum("total_price"),
            profit=Sum("total_price") - Sum("total_cost"),
            items_sold=Sum("quantity"),
        )
        .order_by("-revenue")[:10]
    )

    # Clear existing leaderboard for this date
    DailyLeaderboard.objects.filter(business=business, date=date).delete()

    # Create entries
    entries = []
    for rank, data in enumerate(sales_data, start=1):
        agent_id = data["sold_by"]
        if not agent_id:
            continue

        # Get XP earned today
        xp_record = AgentXP.objects.filter(business=business, agent_id=agent_id, last_xp_date=date).first()

        entry = DailyLeaderboard.objects.create(
            business=business,
            date=date,
            agent_id=agent_id,
            rank=rank,
            sales_count=data["sales_count"],
            revenue=data["revenue"] or Decimal("0"),
            profit=data["profit"] or Decimal("0"),
            items_sold=data["items_sold"] or 0,
            xp_earned_today=xp_record.xp_today if xp_record else 0,
        )
        entries.append(entry)

    return entries


def get_agent_stats(*, business, agent, days=30) -> Dict[str, Any]:
    """
    Get comprehensive stats for an agent (for profile/dashboard).

    Returns:
        {
            "xp": {...},
            "streak": {...},
            "badges": [...],
            "sales_30d": int,
            "revenue_30d": Decimal,
            "rank_today": int or None,
        }
    """
    from inventory.models import GrocerySale
    from django.db.models import Sum, Count

    # XP
    xp_record = AgentXP.objects.filter(business=business, agent=agent).first()

    # Streak
    streak = AgentStreak.objects.filter(business=business, agent=agent).first()

    # Badges
    badges = AgentBadge.objects.filter(business=business, agent=agent).select_related("badge").order_by("-earned_at")

    # Sales last 30 days
    cutoff = timezone.now() - timezone.timedelta(days=days)
    sales_stats = GrocerySale.objects.filter(business=business, sold_by=agent, sold_at__gte=cutoff).aggregate(
        count=Count("id"), revenue=Sum("total_price")
    )

    # Today's rank
    today = timezone.now().date()
    rank_entry = DailyLeaderboard.objects.filter(business=business, date=today, agent=agent).first()

    return {
        "xp": {
            "total": xp_record.total_xp if xp_record else 0,
            "level": xp_record.current_level if xp_record else 1,
            "xp_today": xp_record.xp_today if xp_record else 0,
            "progress_percent": xp_record.xp_progress_percent if xp_record else 0,
            "xp_for_next_level": xp_record.xp_for_next_level if xp_record else 100,
        },
        "streak": {
            "current": streak.current_streak_days if streak else 0,
            "longest": streak.longest_streak_days if streak else 0,
            "active": streak.is_active_today if streak else False,
        },
        "badges": [
            {
                "name": ab.badge.name,
                "icon": ab.badge.icon,
                "earned_at": ab.earned_at,
            }
            for ab in badges
        ],
        "sales_30d": sales_stats["count"] or 0,
        "revenue_30d": sales_stats["revenue"] or Decimal("0"),
        "rank_today": rank_entry.rank if rank_entry else None,
    }


# ==============================================================================
# BADGE SEEDING (RUN ONCE)
# ==============================================================================


def seed_badges():
    """
    Create default badges if they don't exist.
    Run this once in migration or management command.
    """
    badges_config = [
        # Sales milestones
        {
            "code": "first_sale",
            "name": "First Sale",
            "description": "Complete your first grocery sale",
            "category": "SALES",
            "icon": "🎯",
            "xp_reward": 50,
            "sort_order": 1,
        },
        {
            "code": "sales_10",
            "name": "Sales Rookie",
            "description": "Complete 10 sales",
            "category": "SALES",
            "icon": "🌟",
            "xp_reward": 100,
            "sort_order": 2,
        },
        {
            "code": "sales_50",
            "name": "Sales Pro",
            "description": "Complete 50 sales",
            "category": "SALES",
            "icon": "💎",
            "xp_reward": 300,
            "sort_order": 3,
        },
        {
            "code": "sales_100",
            "name": "Sales Master",
            "description": "Complete 100 sales",
            "category": "SALES",
            "icon": "👑",
            "xp_reward": 500,
            "sort_order": 4,
        },
        # Streak badges
        {
            "code": "streak_7",
            "name": "Week Warrior",
            "description": "Maintain a 7-day sales streak",
            "category": "STREAK",
            "icon": "🔥",
            "xp_reward": 200,
            "sort_order": 10,
        },
        {
            "code": "streak_30",
            "name": "Month Master",
            "description": "Maintain a 30-day sales streak",
            "category": "STREAK",
            "icon": "⚡",
            "xp_reward": 1000,
            "sort_order": 11,
        },
        # Revenue badges
        {
            "code": "revenue_1m",
            "name": "Million Maker",
            "description": "Generate MK 1,000,000 in revenue",
            "category": "REVENUE",
            "icon": "💰",
            "xp_reward": 500,
            "sort_order": 20,
        },
        # Level badges
        {
            "code": "level_10",
            "name": "Level 10",
            "description": "Reach level 10",
            "category": "SPECIAL",
            "icon": "🏆",
            "xp_reward": 1000,
            "sort_order": 30,
        },
    ]

    created_count = 0
    for config in badges_config:
        badge, created = Badge.objects.get_or_create(code=config["code"], defaults=config)
        if created:
            created_count += 1

    return created_count

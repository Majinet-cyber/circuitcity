"""
PHASE 5: Gamification Models
Streak tracking, XP/levels, badges for groceries vertical (extensible to others)
"""
from __future__ import annotations

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal

User = get_user_model()


class AgentStreak(models.Model):
    """
    Tracks consecutive days of activity for agents (per business).
    Used for gamification and engagement metrics.
    """

    business = models.ForeignKey("tenants.Business", on_delete=models.CASCADE, related_name="agent_streaks")
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sales_streaks")

    # Streak metrics
    current_streak_days = models.PositiveIntegerField(default=0, help_text="Current consecutive days with activity")
    longest_streak_days = models.PositiveIntegerField(default=0, help_text="All-time longest streak")
    last_activity_date = models.DateField(null=True, blank=True, help_text="Last date with activity")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("business", "agent")
        indexes = [
            models.Index(fields=["business", "-current_streak_days"]),
            models.Index(fields=["business", "-longest_streak_days"]),
        ]

    def __str__(self):
        return f"{self.agent.username} - {self.current_streak_days} days"

    @property
    def is_active_today(self):
        """Check if streak is active (activity today)"""
        return self.last_activity_date == timezone.now().date()

    def record_activity(self, activity_date=None):
        """
        Record activity and update streak.
        Call this after a sale is made.
        """
        if activity_date is None:
            activity_date = timezone.now().date()

        if not self.last_activity_date:
            # First activity
            self.current_streak_days = 1
            self.longest_streak_days = 1
            self.last_activity_date = activity_date
        elif activity_date == self.last_activity_date:
            # Same day, no change
            pass
        elif activity_date == self.last_activity_date + timezone.timedelta(days=1):
            # Next day, extend streak
            self.current_streak_days += 1
            if self.current_streak_days > self.longest_streak_days:
                self.longest_streak_days = self.current_streak_days
            self.last_activity_date = activity_date
        elif activity_date > self.last_activity_date + timezone.timedelta(days=1):
            # Gap, reset streak
            self.current_streak_days = 1
            self.last_activity_date = activity_date

        self.save()


class AgentXP(models.Model):
    """
    Experience points and leveling system for agents.
    Earn XP from sales, stock-ins, and other activities.
    """

    business = models.ForeignKey("tenants.Business", on_delete=models.CASCADE, related_name="agent_xp")
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name="xp_records")

    # XP metrics
    total_xp = models.PositiveIntegerField(default=0, help_text="Total experience points earned")
    current_level = models.PositiveIntegerField(default=1, help_text="Current level (1-based)")

    # Today's stats (resets daily)
    xp_today = models.PositiveIntegerField(default=0, help_text="XP earned today")
    last_xp_date = models.DateField(default=timezone.now, help_text="Last date XP was earned")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("business", "agent")
        indexes = [
            models.Index(fields=["business", "-total_xp"]),
            models.Index(fields=["business", "-current_level"]),
        ]

    def __str__(self):
        return f"{self.agent.username} - Level {self.current_level} ({self.total_xp} XP)"

    @property
    def xp_for_next_level(self):
        """Calculate XP needed for next level (100 * level^1.5)"""
        return int(100 * (self.current_level**1.5))

    @property
    def xp_progress_percent(self):
        """Progress toward next level (0-100)"""
        xp_needed = self.xp_for_next_level
        xp_in_level = self.total_xp - self.xp_for_level(self.current_level)
        return min(100, int((xp_in_level / xp_needed) * 100))

    @staticmethod
    def xp_for_level(level):
        """Total XP needed to reach a level"""
        if level <= 1:
            return 0
        return sum(int(100 * (lvl**1.5)) for lvl in range(1, level))

    def add_xp(self, amount, reason=""):
        """
        Add XP and check for level ups.
        Returns dict with level_up flag and new level.
        """
        today = timezone.now().date()

        # Reset daily XP if new day
        if self.last_xp_date != today:
            self.xp_today = 0
            self.last_xp_date = today

        # Add XP
        self.total_xp += amount
        self.xp_today += amount

        # Check for level up
        old_level = self.current_level
        while self.total_xp >= self.xp_for_level(self.current_level + 1):
            self.current_level += 1

        self.save()

        return {
            "xp_gained": amount,
            "total_xp": self.total_xp,
            "xp_today": self.xp_today,
            "level": self.current_level,
            "level_up": self.current_level > old_level,
            "old_level": old_level,
        }


class Badge(models.Model):
    """
    Achievement badges that agents can earn.
    """

    CATEGORY_CHOICES = [
        ("SALES", "Sales"),
        ("STREAK", "Streak"),
        ("REVENUE", "Revenue"),
        ("SPEED", "Speed"),
        ("SPECIAL", "Special"),
    ]

    code = models.CharField(max_length=50, unique=True, help_text="Unique badge code (e.g. 'first_sale', 'streak_7')")
    name = models.CharField(max_length=100, help_text="Display name (e.g. 'First Sale')")
    description = models.TextField(help_text="How to earn this badge")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="SALES")

    # Visual
    icon = models.CharField(max_length=10, default="🏆", help_text="Emoji icon")
    xp_reward = models.PositiveIntegerField(default=0, help_text="XP awarded when badge is earned")

    # Display order
    sort_order = models.PositiveIntegerField(default=100)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return f"{self.icon} {self.name}"


class AgentBadge(models.Model):
    """
    Junction table for badges earned by agents.
    """

    business = models.ForeignKey("tenants.Business", on_delete=models.CASCADE, related_name="agent_badges")
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name="earned_badges")
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name="earned_by")

    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("business", "agent", "badge")
        indexes = [
            models.Index(fields=["business", "agent", "-earned_at"]),
        ]

    def __str__(self):
        return f"{self.agent.username} earned {self.badge.name}"


class DailyLeaderboard(models.Model):
    """
    Daily snapshot of top performers for leaderboard.
    Computed nightly or on-demand.
    """

    business = models.ForeignKey("tenants.Business", on_delete=models.CASCADE, related_name="daily_leaderboards")
    date = models.DateField()
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name="leaderboard_entries")

    # Metrics
    rank = models.PositiveIntegerField()
    sales_count = models.PositiveIntegerField(default=0)
    revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    profit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    items_sold = models.PositiveIntegerField(default=0)

    # XP snapshot
    xp_earned_today = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("business", "date", "agent")
        indexes = [
            models.Index(fields=["business", "-date", "rank"]),
        ]
        ordering = ["rank"]

    def __str__(self):
        return f"#{self.rank} {self.agent.username} on {self.date}"

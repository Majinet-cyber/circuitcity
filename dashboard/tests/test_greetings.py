# dashboard/tests/test_greetings.py
"""
Tests for greeting helpers.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from dashboard.helpers_greetings import (
    get_time_of_day_greeting,
    get_daily_sales_milestone,
    should_show_first_welcome,
    get_personalized_greeting,
)

User = get_user_model()


class TimeOfDayGreetingTest(TestCase):
    """Test time-of-day greeting logic."""

    def test_morning_greeting(self):
        """Test morning greeting (5:00-11:59)."""
        morning = datetime(2025, 1, 1, 8, 0, tzinfo=timezone.get_current_timezone())
        self.assertEqual(get_time_of_day_greeting(morning), "Good morning")

    def test_afternoon_greeting(self):
        """Test afternoon greeting (12:00-16:59)."""
        afternoon = datetime(2025, 1, 1, 14, 0, tzinfo=timezone.get_current_timezone())
        self.assertEqual(get_time_of_day_greeting(afternoon), "Good afternoon")

    def test_evening_greeting(self):
        """Test evening greeting (17:00-23:59)."""
        evening = datetime(2025, 1, 1, 19, 0, tzinfo=timezone.get_current_timezone())
        self.assertEqual(get_time_of_day_greeting(evening), "Good evening")

    def test_late_night_greeting(self):
        """Test late night greeting (0:00-4:59)."""
        late_night = datetime(2025, 1, 1, 2, 0, tzinfo=timezone.get_current_timezone())
        self.assertEqual(get_time_of_day_greeting(late_night), "Good evening")

    def test_boundary_cases(self):
        """Test boundary times."""
        # 5:00 AM - start of morning
        boundary_morning = datetime(2025, 1, 1, 5, 0, tzinfo=timezone.get_current_timezone())
        self.assertEqual(get_time_of_day_greeting(boundary_morning), "Good morning")

        # 12:00 PM - start of afternoon
        boundary_afternoon = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.get_current_timezone())
        self.assertEqual(get_time_of_day_greeting(boundary_afternoon), "Good afternoon")

        # 17:00 - start of evening
        boundary_evening = datetime(2025, 1, 1, 17, 0, tzinfo=timezone.get_current_timezone())
        self.assertEqual(get_time_of_day_greeting(boundary_evening), "Good evening")


class FirstWelcomeTest(TestCase):
    """Test first-time welcome detection."""

    def test_no_last_login_shows_welcome(self):
        """User with no last_login should see welcome."""
        user = User.objects.create_user(username="newuser", password="pass")
        user.last_login = None
        user.save()

        self.assertTrue(should_show_first_welcome(user))

    def test_recent_join_shows_welcome(self):
        """User who joined very recently should see welcome."""
        user = User.objects.create_user(username="recentuser", password="pass")
        now = timezone.now()
        user.date_joined = now - timedelta(minutes=2)
        user.last_login = now
        user.save()

        self.assertTrue(should_show_first_welcome(user))

    def test_old_user_no_welcome(self):
        """User who joined a while ago should not see welcome."""
        user = User.objects.create_user(username="olduser", password="pass")
        now = timezone.now()
        user.date_joined = now - timedelta(days=30)
        user.last_login = now
        user.save()

        self.assertFalse(should_show_first_welcome(user))


class PersonalizedGreetingTest(TestCase):
    """Test complete personalized greeting context."""

    def test_greeting_with_first_name(self):
        """Test greeting uses first name if available."""
        user = User.objects.create_user(username="testuser", password="pass", first_name="John")

        greeting_ctx = get_personalized_greeting(user)

        self.assertEqual(greeting_ctx["user_name"], "John")
        self.assertIn(greeting_ctx["greeting"], ["Good morning", "Good afternoon", "Good evening"])

    def test_greeting_fallback_to_username(self):
        """Test greeting falls back to username if no first name."""
        user = User.objects.create_user(username="testuser", password="pass")

        greeting_ctx = get_personalized_greeting(user)

        self.assertEqual(greeting_ctx["user_name"], "testuser")

    def test_greeting_structure(self):
        """Test greeting context has all expected keys."""
        user = User.objects.create_user(username="testuser", password="pass")

        greeting_ctx = get_personalized_greeting(user)

        self.assertIn("greeting", greeting_ctx)
        self.assertIn("user_name", greeting_ctx)
        self.assertIn("show_welcome", greeting_ctx)
        self.assertIn("milestone", greeting_ctx)

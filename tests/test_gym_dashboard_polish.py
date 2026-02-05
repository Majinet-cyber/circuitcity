"""
Tests for gym dashboard UI polish features:
- Member count badge in sidebar and dashboard
- Month picker filter
- All time filter
- Recent payments respecting filter
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.business_kinds import BusinessKind
from inventory.models_verticals import GymMember, GymPayment, PaymentMethod

User = get_user_model()


class TestGymDashboardPolish(TestCase):
    """Test suite for gym dashboard polish features"""

    def setUp(self):
        """Set up test fixtures"""
        self.client = Client()
        
        # Create user
        self.user = User.objects.create_user(
            username="gymowner",
            email="owner@gym.test",
            password="testpass123"
        )
        
        # Create gym business
        self.business = Business.objects.create(
            name="Test Gym",
            slug="test-gym",
            status="ACTIVE",
            business_kind=BusinessKind.GYM
        )
        
        # Create membership
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Create test members
        self.member1 = GymMember.objects.create(
            business=self.business,
            name="John Doe",
            phone="0991234567",
            email="john@test.com",
            is_active=True,
            is_archived=False
        )
        
        self.member2 = GymMember.objects.create(
            business=self.business,
            name="Jane Smith",
            phone="0997654321",
            email="jane@test.com",
            is_active=True,
            is_archived=False
        )
        
        self.member3 = GymMember.objects.create(
            business=self.business,
            name="Bob Wilson",
            phone="0998888888",
            email="bob@test.com",
            is_active=True,
            is_archived=True  # Archived member
        )
        
        self.today = timezone.now().date()
        self.this_month_start = self.today.replace(day=1)
        
        # Create payments in different time periods
        # Payment this month
        self.payment1 = GymPayment.objects.create(
            member=self.member1,
            membership_amount=Decimal("50000.00"),
            trainer_fee=Decimal("10000.00"),
            payment_method=PaymentMethod.CASH,
            start_date=self.today,
            end_date=self.today + timedelta(days=30),
            paid_by=self.user,
            paid_at=timezone.now(),
            is_active=True
        )
        
        # Payment last month
        last_month = self.this_month_start - timedelta(days=1)
        last_month_start = last_month.replace(day=1)
        self.payment2 = GymPayment.objects.create(
            member=self.member2,
            membership_amount=Decimal("55000.00"),
            trainer_fee=Decimal("0.00"),
            payment_method=PaymentMethod.MOBILE_MONEY,
            start_date=last_month,
            end_date=last_month + timedelta(days=30),
            paid_by=self.user,
            paid_at=timezone.make_aware(
                timezone.datetime.combine(last_month, timezone.datetime.min.time())
            ),
            is_active=True
        )
        
        self.client.login(username="gymowner", password="testpass123")

    def test_dashboard_includes_member_count_in_context(self):
        """Test that dashboard view includes total_members in context"""
        url = reverse("verticals:gym_dashboard")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn("total_members", response.context)
        # Should count only non-archived members
        self.assertEqual(response.context["total_members"], 2)

    def test_member_count_badge_in_dashboard_html(self):
        """Test that member count badge appears in dashboard HTML"""
        url = reverse("verticals:gym_dashboard")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        
        # Check for member count in "Manage members" button
        self.assertIn("Manage members", content)
        # Badge should show count (2 active members)
        self.assertIn("badge", content)

    def test_month_filter_param_changes_date_range(self):
        """Test that month filter parameter changes the query range"""
        # Get last month in YYYY-MM format
        last_month = self.this_month_start - timedelta(days=1)
        month_str = last_month.strftime("%Y-%m")
        
        url = reverse("verticals:gym_dashboard") + f"?range=month&month={month_str}"
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Should show last month's label
        self.assertIn(last_month.strftime("%B %Y"), response.context["range_label"])
        
        # Revenue should include only last month's payment
        revenue = response.context["revenue"]
        self.assertEqual(revenue, Decimal("55000.00"))
        
        # Payment count should be 1
        self.assertEqual(response.context["payment_count"], 1)

    def test_all_time_filter_shows_all_payments(self):
        """Test that all_time filter removes date constraints"""
        url = reverse("verticals:gym_dashboard") + "?range=all_time"
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Should show "All Time" label
        self.assertEqual(response.context["range_label"], "All Time")
        
        # Revenue should include all payments
        revenue = response.context["revenue"]
        expected_revenue = Decimal("50000.00") + Decimal("10000.00") + Decimal("55000.00")
        self.assertEqual(revenue, expected_revenue)
        
        # Payment count should be 2 (both payments)
        self.assertEqual(response.context["payment_count"], 2)

    def test_recent_payments_respect_month_filter(self):
        """Test that recent payments list respects the month filter"""
        # Get last month in YYYY-MM format
        last_month = self.this_month_start - timedelta(days=1)
        month_str = last_month.strftime("%Y-%m")
        
        url = reverse("verticals:gym_dashboard") + f"?range=month&month={month_str}"
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Recent payments should only include last month's payment
        recent_payments = list(response.context["recent_payments"])
        self.assertEqual(len(recent_payments), 1)
        self.assertEqual(recent_payments[0].member, self.member2)

    def test_recent_payments_respect_all_time_filter(self):
        """Test that recent payments list respects the all_time filter"""
        url = reverse("verticals:gym_dashboard") + "?range=all_time"
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Recent payments should include all payments
        recent_payments = list(response.context["recent_payments"])
        self.assertEqual(len(recent_payments), 2)

    def test_recent_payments_respect_mtd_filter(self):
        """Test that recent payments list respects the MTD filter (default)"""
        url = reverse("verticals:gym_dashboard") + "?range=mtd"
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Recent payments should only include this month's payment
        recent_payments = list(response.context["recent_payments"])
        self.assertEqual(len(recent_payments), 1)
        self.assertEqual(recent_payments[0].member, self.member1)

    def test_kpis_respect_month_filter(self):
        """Test that KPIs (revenue, costs, profit) respect the month filter"""
        # Get last month in YYYY-MM format
        last_month = self.this_month_start - timedelta(days=1)
        month_str = last_month.strftime("%Y-%m")
        
        url = reverse("verticals:gym_dashboard") + f"?range=month&month={month_str}"
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Revenue should match last month's payment
        revenue = response.context["revenue"]
        self.assertEqual(revenue, Decimal("55000.00"))
        
        # Payment mix should reflect last month's data
        payment_mix = response.context["payment_mix"]
        mobile_money_item = next((pm for pm in payment_mix if pm["method"] == "Mobile Money"), None)
        self.assertIsNotNone(mobile_money_item)
        self.assertEqual(mobile_money_item["amount"], Decimal("55000.00"))

    def test_invalid_month_format_falls_back_to_mtd(self):
        """Test that invalid month format falls back to MTD"""
        url = reverse("verticals:gym_dashboard") + "?range=month&month=invalid"
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Should fall back to MTD
        self.assertEqual(response.context["range_key"], "mtd")
        self.assertEqual(response.context["range_label"], "Month to Date")

    def test_month_picker_without_month_param_falls_back_to_mtd(self):
        """Test that month picker without month param falls back to MTD"""
        url = reverse("verticals:gym_dashboard") + "?range=month"
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Should fall back to MTD
        self.assertEqual(response.context["range_key"], "mtd")
        self.assertEqual(response.context["range_label"], "Month to Date")

    def test_selected_month_in_context(self):
        """Test that selected_month is included in context for month picker"""
        month_str = "2026-01"
        url = reverse("verticals:gym_dashboard") + f"?range=month&month={month_str}"
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_month"], month_str)

    def test_default_filter_remains_mtd(self):
        """Test that default filter remains MTD (no breaking changes)"""
        url = reverse("verticals:gym_dashboard")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["range_key"], "mtd")
        self.assertEqual(response.context["range_label"], "Month to Date")


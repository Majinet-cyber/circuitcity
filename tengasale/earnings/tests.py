from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from applications.models import FinancingApplication
from commissions.models import Commission
from rewards.models import SpinWallet


class EarningsUrlTests(TestCase):
    def test_earnings_home_url_name_resolves(self):
        self.assertEqual(reverse("earnings_home"), "/earnings/")

    def test_earnings_extra_url_names_resolve(self):
        self.assertEqual(reverse("merchant_leaderboard"), "/earnings/leaderboard/")
        self.assertEqual(reverse("spin_rewards"), "/earnings/spin/")


class EarningsPageTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="merchant", password="test-pass-123")
        self.client.login(username="merchant", password="test-pass-123")
        self.app = FinancingApplication.objects.create(
            created_by=self.user,
            status="approved",
            calculated_total_loan=Decimal("1000000.00"),
        )

    def test_earnings_page_displays_pending_commission_and_spins(self):
        Commission.objects.create(
            user=self.user,
            application=self.app,
            role=Commission.ROLE_MERCHANT,
            commission_percent=Decimal("1.00"),
            sale_amount=Decimal("1000000.00"),
            amount=Decimal("10000.00"),
            status=Commission.STATUS_PENDING,
        )
        SpinWallet.objects.create(user=self.user, available_spins=2, total_spins_earned=2)

        response = self.client.get(reverse("earnings_home"))

        self.assertContains(response, "Pending commissions")
        self.assertContains(response, "MWK 10000.00")
        self.assertContains(response, "Available spins")
        self.assertContains(response, "SPIN & WIN")


class MerchantLeaderboardTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.users = [
            User.objects.create_user(username=f"merchant{i}", password="test-pass-123")
            for i in range(12)
        ]
        self.client.login(username="merchant0", password="test-pass-123")

    def test_leaderboard_ranks_by_sales_count_and_limits_top_ten(self):
        for index, user in enumerate(self.users):
            for _ in range(index + 1):
                FinancingApplication.objects.create(created_by=user, status="approved")

        response = self.client.get(reverse("merchant_leaderboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "merchant11")
        self.assertContains(response, "merchant2")
        self.assertNotContains(response, ">merchant1<")
        self.assertContains(response, "Your rank: #12")

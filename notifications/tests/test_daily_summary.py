# notifications/tests/test_daily_summary.py
"""
Tests for the vertical-aware daily summary system.

Coverage:
  1. Registry routes correctly to Retail / Gym / CarHire providers.
  2. RetailDailySummaryProvider returns retail-only keys (COGS, top_product).
  3. GymDailySummaryProvider NEVER returns COGS or top_product keys.
  4. CarHireDailySummaryProvider NEVER returns COGS or top_product keys.
  5. render_email() returns (html, text) tuple for each provider.
  6. DailySummarySettings.for_business() creates settings idempotently.
  7. Task skips when no recipients.
  8. Task skips when last_sent_date == today.
  9. Task skips when send_hour doesn't match current hour.
 10. Task sends and updates last_sent_date when all conditions are met.
 11. Cross-vertical isolation: retail metrics not present in gym/car-hire.
"""
from __future__ import annotations

from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from inventory.business_kinds import BusinessKind
from notifications.models import BusinessEmailRecipient, DailySummarySettings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_business(pk=1, name="Test Biz", kind=None, currency="MWK"):
    """Return a lightweight MagicMock that quacks like a Business."""
    biz = MagicMock()
    biz.pk = pk
    biz.id = pk
    biz.name = name
    biz.business_kind = kind
    biz.currency = currency
    # daily_summary_settings is accessed by providers — return a simple mock
    ds_mock = MagicMock()
    ds_mock.timezone = "Africa/Blantyre"
    biz.daily_summary_settings = ds_mock
    return biz


def _make_ds_mock(business, send_hour=7, tz="Africa/Blantyre", enabled=True):
    """Return a MagicMock that behaves like DailySummarySettings."""
    ds = MagicMock(spec=DailySummarySettings)
    ds.business = business
    ds.is_enabled = enabled
    ds.send_hour = send_hour
    ds.timezone = tz
    ds.last_sent_date = None
    return ds


# ---------------------------------------------------------------------------
# 1. Registry routing
# ---------------------------------------------------------------------------

class TestProviderRegistry(TestCase):
    def test_gym_kind_returns_gym_provider(self):
        from notifications.daily_summary.gym import GymDailySummaryProvider
        from notifications.daily_summary.registry import get_provider

        biz = _make_business(kind=BusinessKind.GYM)
        self.assertIsInstance(get_provider(biz), GymDailySummaryProvider)

    def test_car_hire_kind_returns_car_hire_provider(self):
        from notifications.daily_summary.car_hire import CarHireDailySummaryProvider
        from notifications.daily_summary.registry import get_provider

        biz = _make_business(kind=BusinessKind.CAR_HIRE)
        self.assertIsInstance(get_provider(biz), CarHireDailySummaryProvider)

    def test_retail_kinds_return_retail_provider(self):
        from notifications.daily_summary.registry import get_provider
        from notifications.daily_summary.retail import RetailDailySummaryProvider

        for kind in (
            BusinessKind.PHONES,
            BusinessKind.GROCERY,
            BusinessKind.PHARMACY,
            BusinessKind.CLOTHING,
            BusinessKind.LIQUOR,
            BusinessKind.HARDWARE,
        ):
            with self.subTest(kind=kind):
                biz = _make_business(kind=kind)
                self.assertIsInstance(get_provider(biz), RetailDailySummaryProvider)

    def test_null_kind_falls_back_to_retail(self):
        from notifications.daily_summary.registry import get_provider
        from notifications.daily_summary.retail import RetailDailySummaryProvider

        biz = _make_business(kind=None)
        self.assertIsInstance(get_provider(biz), RetailDailySummaryProvider)


# ---------------------------------------------------------------------------
# 2. Retail provider metrics shape
# ---------------------------------------------------------------------------

class TestRetailProvider(TestCase):
    def _make_provider(self):
        from notifications.daily_summary.retail import RetailDailySummaryProvider
        return RetailDailySummaryProvider()

    def test_metrics_keys_include_cogs(self):
        provider = self._make_provider()
        biz = _make_business(kind=BusinessKind.PHONES)
        with patch.object(provider, "_populate_phone_sales", return_value=None), \
             patch.object(provider, "_populate_low_stock", return_value=None):
            metrics = provider.get_metrics(biz, date.today())
        self.assertIn("total_cogs", metrics)
        self.assertIn("total_profit", metrics)
        self.assertIn("top_product", metrics)
        self.assertIn("top_category", metrics)
        self.assertIn("biggest_sale_amount", metrics)
        self.assertIn("low_stock_alerts", metrics)

    def test_metrics_defaults_are_safe(self):
        provider = self._make_provider()
        biz = _make_business(kind=BusinessKind.PHONES)
        with patch.object(provider, "_populate_phone_sales", return_value=None), \
             patch.object(provider, "_populate_low_stock", return_value=None):
            metrics = provider.get_metrics(biz, date.today())
        self.assertEqual(metrics["total_sales"], 0)
        self.assertEqual(metrics["total_revenue"], Decimal("0.00"))

    def test_db_error_does_not_propagate(self):
        """Provider must absorb DB errors and return safe defaults."""
        provider = self._make_provider()
        biz = _make_business(kind=BusinessKind.PHONES)
        with patch.object(provider, "_populate_phone_sales", side_effect=Exception("DB down")), \
             patch.object(provider, "_populate_low_stock", side_effect=Exception("DB down")):
            metrics = provider.get_metrics(biz, date.today())
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics["total_sales"], 0)


# ---------------------------------------------------------------------------
# 3 & 11. Gym provider — no COGS, no top_product
# ---------------------------------------------------------------------------

class TestGymProvider(TestCase):
    def _make_provider(self):
        from notifications.daily_summary.gym import GymDailySummaryProvider
        return GymDailySummaryProvider()

    def test_metrics_do_not_contain_cogs(self):
        provider = self._make_provider()
        biz = _make_business(kind=BusinessKind.GYM)
        with patch.object(provider, "_populate_gym_metrics", return_value=None):
            metrics = provider.get_metrics(biz, date.today())
        self.assertNotIn("total_cogs", metrics)

    def test_metrics_do_not_contain_top_product(self):
        provider = self._make_provider()
        biz = _make_business(kind=BusinessKind.GYM)
        with patch.object(provider, "_populate_gym_metrics", return_value=None):
            metrics = provider.get_metrics(biz, date.today())
        self.assertNotIn("top_product", metrics)

    def test_metrics_keys_present(self):
        provider = self._make_provider()
        biz = _make_business(kind=BusinessKind.GYM)
        with patch.object(provider, "_populate_gym_metrics", return_value=None):
            metrics = provider.get_metrics(biz, date.today())
        self.assertIn("new_members_today", metrics)
        self.assertIn("active_members", metrics)
        self.assertIn("membership_revenue_today", metrics)
        self.assertIn("checkins_today", metrics)
        self.assertIn("top_plan", metrics)
        self.assertIn("renewals_due_7_days", metrics)

    def test_db_error_does_not_propagate(self):
        provider = self._make_provider()
        biz = _make_business(kind=BusinessKind.GYM)
        with patch.object(provider, "_populate_gym_metrics", side_effect=Exception("DB down")):
            metrics = provider.get_metrics(biz, date.today())
        self.assertEqual(metrics["new_members_today"], 0)


# ---------------------------------------------------------------------------
# 4 & 11. Car hire provider — no COGS, no top_product
# ---------------------------------------------------------------------------

class TestCarHireProvider(TestCase):
    def _make_provider(self):
        from notifications.daily_summary.car_hire import CarHireDailySummaryProvider
        return CarHireDailySummaryProvider()

    def test_metrics_do_not_contain_cogs(self):
        provider = self._make_provider()
        biz = _make_business(kind=BusinessKind.CAR_HIRE)
        with patch.object(provider, "_populate_car_hire_metrics", return_value=None):
            metrics = provider.get_metrics(biz, date.today())
        self.assertNotIn("total_cogs", metrics)

    def test_metrics_do_not_contain_top_product(self):
        provider = self._make_provider()
        biz = _make_business(kind=BusinessKind.CAR_HIRE)
        with patch.object(provider, "_populate_car_hire_metrics", return_value=None):
            metrics = provider.get_metrics(biz, date.today())
        self.assertNotIn("top_product", metrics)

    def test_metrics_keys_present(self):
        provider = self._make_provider()
        biz = _make_business(kind=BusinessKind.CAR_HIRE)
        with patch.object(provider, "_populate_car_hire_metrics", return_value=None):
            metrics = provider.get_metrics(biz, date.today())
        self.assertIn("rentals_today", metrics)
        self.assertIn("revenue_today", metrics)
        self.assertIn("utilisation_rate", metrics)
        self.assertIn("top_vehicle", metrics)
        self.assertIn("overdue_returns", metrics)
        self.assertIn("maintenance_alerts", metrics)


# ---------------------------------------------------------------------------
# 5. render_email returns (html, text) tuple
# ---------------------------------------------------------------------------

class TestRenderEmail(TestCase):
    def test_retail_render_returns_tuple(self):
        from notifications.daily_summary.retail import RetailDailySummaryProvider
        biz = _make_business()
        biz.name = "Test Store"
        provider = RetailDailySummaryProvider()
        metrics = {
            "total_sales": 5,
            "total_revenue": Decimal("100000"),
            "total_profit": Decimal("20000"),
            "total_cogs": Decimal("80000"),
            "top_product": "Nivea Lotion",
            "top_category": "Skincare",
            "biggest_sale_amount": Decimal("30000"),
            "biggest_sale_ref": "Item #42",
            "low_stock_alerts": 2,
            "currency": "MWK",
        }
        html, text = provider.render_email(biz, metrics, date.today())
        self.assertIn("<html", html.lower())
        self.assertIn("Daily Summary", text)
        self.assertIn("Total Sales Today", html)

    def test_gym_render_returns_tuple(self):
        from notifications.daily_summary.gym import GymDailySummaryProvider
        biz = _make_business(kind=BusinessKind.GYM)
        biz.name = "Fitness Hub"
        provider = GymDailySummaryProvider()
        metrics = {
            "new_members_today": 3,
            "active_members": 45,
            "membership_revenue_today": Decimal("50000"),
            "checkins_today": 22,
            "top_plan": "Monthly",
            "renewals_due_7_days": 8,
            "currency": "MWK",
        }
        html, text = provider.render_email(biz, metrics, date.today())
        self.assertIn("<html", html.lower())
        self.assertNotIn("COGS", html)
        self.assertNotIn("COGS", text)
        self.assertNotIn("Top Product", html)

    def test_car_hire_render_returns_tuple(self):
        from notifications.daily_summary.car_hire import CarHireDailySummaryProvider
        biz = _make_business(kind=BusinessKind.CAR_HIRE)
        biz.name = "Premier Hire"
        provider = CarHireDailySummaryProvider()
        metrics = {
            "rentals_today": 4,
            "revenue_today": Decimal("200000"),
            "utilisation_rate": Decimal("75.0"),
            "top_vehicle": "Toyota Fortuner",
            "overdue_returns": 1,
            "maintenance_alerts": 2,
            "currency": "MWK",
        }
        html, text = provider.render_email(biz, metrics, date.today())
        self.assertIn("<html", html.lower())
        self.assertNotIn("COGS", html)
        self.assertIn("Fleet", html)


# ---------------------------------------------------------------------------
# 6. DailySummarySettings.for_business() — idempotent
# ---------------------------------------------------------------------------

class TestDailySummarySettings(TestCase):
    def test_for_business_creates_once(self):
        from tenants.models import Business
        biz = Business.objects.create(name="Idempotent Test Store", slug="idempotent-test-store")
        s1 = DailySummarySettings.for_business(biz)
        s2 = DailySummarySettings.for_business(biz)
        self.assertEqual(s1.pk, s2.pk)

    def test_default_is_disabled(self):
        from tenants.models import Business
        biz = Business.objects.create(name="Disabled Store Test", slug="disabled-store-test")
        s = DailySummarySettings.for_business(biz)
        self.assertFalse(s.is_enabled)


# ---------------------------------------------------------------------------
# 7–10. Task safeguards (all use MagicMock for ds and business)
# ---------------------------------------------------------------------------

class TestSendDailySummariesTask(TestCase):
    def _make_business_mock(self, kind=BusinessKind.PHONES):
        biz = MagicMock()
        biz.pk = 1
        biz.name = "Mock Business"
        biz.business_kind = kind
        biz.currency = "MWK"
        return biz

    def test_skips_when_no_recipients(self):
        from notifications.tasks_daily_summary import _maybe_send_for_business
        import pytz

        biz = self._make_business_mock()
        ds = _make_ds_mock(biz, send_hour=7)

        tz = pytz.timezone("Africa/Blantyre")
        now_utc = tz.localize(datetime(2025, 1, 15, 7, 5)).astimezone(dt_timezone.utc)

        empty_qs = MagicMock()
        empty_qs.values_list.return_value = []

        with patch("notifications.tasks_daily_summary.BusinessEmailRecipient") as MockRecipient, \
             patch("notifications.tasks_daily_summary.get_provider") as mock_prov:
            MockRecipient.objects.filter.return_value = empty_qs
            _maybe_send_for_business(ds, now_utc)
            mock_prov.assert_not_called()

    def test_skips_when_already_sent_today(self):
        from notifications.tasks_daily_summary import _maybe_send_for_business
        import pytz

        biz = self._make_business_mock()
        ds = _make_ds_mock(biz, send_hour=7)
        ds.last_sent_date = date(2025, 1, 15)

        tz = pytz.timezone("Africa/Blantyre")
        now_utc = tz.localize(datetime(2025, 1, 15, 7, 5)).astimezone(dt_timezone.utc)

        recipient_qs = MagicMock()
        recipient_qs.values_list.return_value = [("mgr@biz.com", "Manager")]

        with patch("notifications.tasks_daily_summary.BusinessEmailRecipient") as MockRecipient, \
             patch("notifications.tasks_daily_summary.get_provider") as mock_prov:
            MockRecipient.objects.filter.return_value = recipient_qs
            _maybe_send_for_business(ds, now_utc)
            mock_prov.assert_not_called()

    def test_skips_when_wrong_hour(self):
        from notifications.tasks_daily_summary import _maybe_send_for_business
        import pytz

        biz = self._make_business_mock()
        ds = _make_ds_mock(biz, send_hour=7)
        ds.last_sent_date = None

        tz = pytz.timezone("Africa/Blantyre")
        # It's 08:05 — send_hour=7, so should be skipped
        now_utc = tz.localize(datetime(2025, 1, 15, 8, 5)).astimezone(dt_timezone.utc)

        recipient_qs = MagicMock()
        recipient_qs.values_list.return_value = [("mgr@biz.com", "Manager")]

        with patch("notifications.tasks_daily_summary.BusinessEmailRecipient") as MockRecipient, \
             patch("notifications.tasks_daily_summary.get_provider") as mock_prov:
            MockRecipient.objects.filter.return_value = recipient_qs
            _maybe_send_for_business(ds, now_utc)
            mock_prov.assert_not_called()

    @patch("notifications.tasks_daily_summary.EmailMultiAlternatives")
    def test_sends_and_updates_last_sent_date(self, MockEmail):
        from notifications.tasks_daily_summary import _maybe_send_for_business
        from notifications.daily_summary.retail import RetailDailySummaryProvider
        import pytz

        biz = self._make_business_mock(kind=BusinessKind.PHONES)
        ds = _make_ds_mock(biz, send_hour=7)
        ds.last_sent_date = None

        mock_msg = MagicMock()
        MockEmail.return_value = mock_msg

        tz = pytz.timezone("Africa/Blantyre")
        now_utc = tz.localize(datetime(2025, 1, 15, 7, 5)).astimezone(dt_timezone.utc)

        recipient_qs = MagicMock()
        recipient_qs.values_list.return_value = [("mgr@biz.com", "Manager")]

        mock_provider = MagicMock(spec=RetailDailySummaryProvider)
        mock_provider.get_metrics.return_value = {}
        mock_provider.render_email.return_value = ("<html>test</html>", "test")

        with patch("notifications.tasks_daily_summary.BusinessEmailRecipient") as MockRecipient, \
             patch("notifications.tasks_daily_summary.get_provider", return_value=mock_provider):
            MockRecipient.objects.filter.return_value = recipient_qs
            _maybe_send_for_business(ds, now_utc)

        mock_msg.send.assert_called_once()
        ds.save.assert_called_once_with(update_fields=["last_sent_date"])
        self.assertEqual(ds.last_sent_date, date(2025, 1, 15))

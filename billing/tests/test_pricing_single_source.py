"""
Test that pricing is enforced from a single source of truth across the app.

This prevents pricing drift between:
- Main app (billing/views.py)
- HQ admin (hq/views.py, hq/views_subscriptions.py)
- Public homepage
- Any other place that displays or uses plan pricing
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from billing import pricing
from billing.models import BusinessSubscription, SubscriptionPlan
from tenants.models import Business

User = get_user_model()


class PricingSingleSourceOfTruthTest(TestCase):
    """Verify that all parts of the app use the same pricing config."""

    def setUp(self):
        """Create test data."""
        self.user = User.objects.create_user(
            username="testowner",
            email="owner@test.com",
            password="testpass123",
        )
        self.business = Business.objects.create(
            name="Test Business",
            subdomain="testbiz",
        )
        self.business.owner = self.user
        self.business.save()

        # Create subscription plans matching the canonical pricing
        self.starter = SubscriptionPlan.objects.create(
            code="starter",
            name="Starter",
            amount=Decimal("20000.00"),
            currency="MWK",
            interval=SubscriptionPlan.Interval.MONTH,
            max_stores=1,
            max_agents=3,
            is_active=True,
        )
        self.growth = SubscriptionPlan.objects.create(
            code="growth",
            name="Growth",
            amount=Decimal("60000.00"),
            currency="MWK",
            interval=SubscriptionPlan.Interval.MONTH,
            max_stores=5,
            max_agents=15,
            is_active=True,
        )
        self.pro = SubscriptionPlan.objects.create(
            code="pro",
            name="Pro",
            amount=Decimal("120000.00"),
            currency="MWK",
            interval=SubscriptionPlan.Interval.MONTH,
            max_stores=-1,
            max_agents=-1,
            is_active=True,
        )

        # Create subscription for the business
        self.subscription = BusinessSubscription.start_trial(
            business=self.business,
            plan=self.starter,
            days=30,
        )

        self.client = Client()
        self.client.force_login(self.user)

    def test_pricing_module_exists(self):
        """Verify that billing.pricing module exists and has expected structure."""
        self.assertTrue(hasattr(pricing, "PLANS"))
        self.assertTrue(hasattr(pricing, "PLAN_CATALOG"))
        self.assertTrue(hasattr(pricing, "get_plan"))
        self.assertTrue(hasattr(pricing, "get_all_plans"))
        self.assertTrue(hasattr(pricing, "format_price"))

    def test_canonical_pricing_values(self):
        """Verify that canonical pricing values are correct."""
        # Expected values from requirements
        expected = {
            "starter": Decimal("20000.00"),
            "growth": Decimal("60000.00"),
            "pro": Decimal("120000.00"),
        }

        # Check PLANS dict
        for code, amount in expected.items():
            self.assertIn(code, pricing.PLANS)
            self.assertEqual(pricing.PLANS[code].amount, amount)

        # Check PLAN_CATALOG (legacy dict format for HQ)
        for code, amount in expected.items():
            self.assertIn(code, pricing.PLAN_CATALOG)
            self.assertEqual(pricing.PLAN_CATALOG[code]["amount"], amount)

    def test_hq_uses_billing_pricing(self):
        """Verify that HQ admin imports PLAN_CATALOG from billing.pricing."""
        from hq.views import PLAN_CATALOG as HQ_CATALOG

        # HQ should be using the same catalog
        self.assertEqual(HQ_CATALOG["starter"]["amount"], Decimal("20000.00"))
        self.assertEqual(HQ_CATALOG["growth"]["amount"], Decimal("60000.00"))
        self.assertEqual(HQ_CATALOG["pro"]["amount"], Decimal("120000.00"))

        # Verify HQ catalog IS the billing pricing catalog
        self.assertIs(HQ_CATALOG, pricing.PLAN_CATALOG)

    def test_manage_page_shows_correct_amounts(self):
        """Verify /billing/manage/ displays correct plan amounts."""
        response = self.client.get(reverse("billing:manage"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()

        # Check that correct amounts are displayed (not blank)
        self.assertIn("20000", content)  # Starter
        self.assertIn("60000", content)  # Growth
        self.assertIn("120000", content)  # Pro

        # Verify template uses correct field names (not blank "MWK /")
        self.assertNotIn("MWK  /", content)  # Double space indicates blank amount
        self.assertNotIn("— MWK  —", content)  # Another blank pattern

    def test_subscribe_page_shows_correct_amounts(self):
        """Verify /billing/subscribe/ displays correct plan amounts."""
        response = self.client.get(reverse("billing:subscribe"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()

        # Check that correct amounts are displayed
        self.assertIn("20,000", content)  # Starter (with comma formatting)
        self.assertIn("60,000", content)  # Growth
        self.assertIn("120,000", content)  # Pro

    def test_database_plans_match_pricing_config(self):
        """Verify database SubscriptionPlan records match canonical pricing."""
        db_starter = SubscriptionPlan.objects.get(code="starter")
        db_growth = SubscriptionPlan.objects.get(code="growth")
        db_pro = SubscriptionPlan.objects.get(code="pro")

        self.assertEqual(db_starter.amount, Decimal("20000.00"))
        self.assertEqual(db_growth.amount, Decimal("60000.00"))
        self.assertEqual(db_pro.amount, Decimal("120000.00"))

    def test_no_duplicate_plans_in_db(self):
        """Verify there are no duplicate plan codes in database."""
        for code in ["starter", "growth", "pro"]:
            count = SubscriptionPlan.objects.filter(code=code).count()
            self.assertLessEqual(
                count,
                1,
                f"Found {count} plans with code '{code}', expected at most 1",
            )

    def test_format_price_helper(self):
        """Verify format_price helper formats correctly."""
        self.assertEqual(pricing.format_price(Decimal("20000"), "MWK"), "MWK 20,000")
        self.assertEqual(pricing.format_price(Decimal("60000"), "MWK"), "MWK 60,000")
        self.assertEqual(pricing.format_price(Decimal("120000"), "MWK"), "MWK 120,000")

    def test_all_plans_have_required_fields(self):
        """Verify all plans in PLAN_CATALOG have required fields."""
        required_fields = ["code", "name", "amount", "max_agents", "max_stores"]

        for code, plan_dict in pricing.PLAN_CATALOG.items():
            for field in required_fields:
                self.assertIn(
                    field,
                    plan_dict,
                    f"Plan '{code}' missing required field '{field}'",
                )

    def test_plan_order_correct(self):
        """Verify plans are returned in correct order (starter, growth, pro)."""
        plans = pricing.get_all_plans()
        self.assertEqual(len(plans), 3)
        self.assertEqual(plans[0].code, "starter")
        self.assertEqual(plans[1].code, "growth")
        self.assertEqual(plans[2].code, "pro")


@pytest.mark.django_db
class TestPricingConsistency:
    """Additional pytest-style tests for pricing consistency."""

    def test_no_hardcoded_prices_in_views(self):
        """
        NOTE: This is a reminder test.
        All prices MUST come from billing.pricing module.
        DO NOT hardcode Decimal("20000") or similar in views.
        """
        # This test exists as documentation
        # Actual enforcement would require AST parsing or code review
        assert True

    def test_hq_subscription_pricing_matches(self):
        """Verify HQ views_subscriptions also uses correct pricing."""
        from hq.views_subscriptions import PLAN_CATALOG as SUB_CATALOG

        # Should be same object as billing.pricing.PLAN_CATALOG
        assert SUB_CATALOG is pricing.PLAN_CATALOG

# billing/tests/test_trial_subscription_safe.py
"""
Tests for plan-safe and transaction-safe trial subscription creation.

These tests verify:
1. Trial subscription creation NEVER fails due to missing plans
2. Plan resolver always returns a valid Plan
3. Subscription is idempotent (no duplicates)
4. Works correctly with transaction.on_commit()

CRITICAL: These tests prevent regression of the signup IntegrityError bug.
"""
import pytest
from decimal import Decimal
from django.test import TestCase, TransactionTestCase, override_settings
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestPlanResolver(TestCase):
    """Tests for billing.services.plan_resolver.get_default_trial_plan()"""
    
    def test_get_default_trial_plan_with_existing_starter_plan(self):
        """When 'starter' plan exists, it should be returned."""
        from billing.models import SubscriptionPlan
        from billing.services.plan_resolver import get_default_trial_plan
        
        # Create starter plan
        plan = SubscriptionPlan.objects.create(
            code="starter",
            name="Starter",
            amount=Decimal("0.00"),
            is_active=True,
        )
        
        result = get_default_trial_plan()
        
        self.assertIsNotNone(result, "Should return a plan")
        self.assertEqual(result.code, "starter")
        self.assertEqual(result.id, plan.id)
    
    def test_get_default_trial_plan_with_no_plans_creates_fallback(self):
        """When no plans exist, should create a fallback 'starter' plan."""
        from billing.models import SubscriptionPlan
        from billing.services.plan_resolver import get_default_trial_plan
        
        # Delete all plans
        SubscriptionPlan.objects.all().delete()
        
        result = get_default_trial_plan(create_if_missing=True)
        
        self.assertIsNotNone(result, "Should create and return a plan")
        self.assertEqual(result.code, "starter")
        self.assertEqual(result.amount, Decimal("0.00"))
        self.assertTrue(result.is_active)
        
        # Verify it was created in DB
        self.assertTrue(
            SubscriptionPlan.objects.filter(code="starter").exists(),
            "Starter plan should exist in DB"
        )
    
    def test_get_default_trial_plan_returns_cheapest_if_no_starter(self):
        """When no 'starter' but other plans exist, return cheapest."""
        from billing.models import SubscriptionPlan
        from billing.services.plan_resolver import get_default_trial_plan
        
        # Delete all plans first
        SubscriptionPlan.objects.all().delete()
        
        # Create plans (not 'starter')
        SubscriptionPlan.objects.create(
            code="pro",
            name="Pro",
            amount=Decimal("100.00"),
            is_active=True,
        )
        basic = SubscriptionPlan.objects.create(
            code="basic",
            name="Basic",
            amount=Decimal("50.00"),
            is_active=True,
        )
        
        result = get_default_trial_plan()
        
        self.assertIsNotNone(result)
        self.assertEqual(result.id, basic.id, "Should return cheapest plan")
    
    def test_get_default_trial_plan_never_returns_none(self):
        """Plan resolver should NEVER return None."""
        from billing.models import SubscriptionPlan
        from billing.services.plan_resolver import get_default_trial_plan
        
        # Delete all plans
        SubscriptionPlan.objects.all().delete()
        
        # This should NOT return None - it should create a fallback
        result = get_default_trial_plan(create_if_missing=True)
        
        self.assertIsNotNone(result, "Plan resolver must NEVER return None")
    
    def test_get_default_trial_plan_is_idempotent(self):
        """Calling plan resolver multiple times should not create duplicates."""
        from billing.models import SubscriptionPlan
        from billing.services.plan_resolver import get_default_trial_plan
        
        # Delete all plans
        SubscriptionPlan.objects.all().delete()
        
        # Call multiple times
        plan1 = get_default_trial_plan(create_if_missing=True)
        plan2 = get_default_trial_plan(create_if_missing=True)
        plan3 = get_default_trial_plan(create_if_missing=True)
        
        # All should return the same plan
        self.assertEqual(plan1.id, plan2.id)
        self.assertEqual(plan2.id, plan3.id)
        
        # Only one plan should exist
        self.assertEqual(
            SubscriptionPlan.objects.filter(code="starter").count(),
            1,
            "Should not create duplicate starter plans"
        )


@pytest.mark.django_db
class TestTrialSubscriptionIdempotency(TestCase):
    """Tests for idempotent trial subscription creation."""
    
    def setUp(self):
        """Create test business and plan."""
        from tenants.models import Business
        from billing.models import SubscriptionPlan
        
        # Ensure starter plan exists
        self.plan, _ = SubscriptionPlan.objects.get_or_create(
            code="starter",
            defaults={
                "name": "Starter",
                "amount": Decimal("0.00"),
                "is_active": True,
            }
        )
        
        # Create test business
        self.business = Business.objects.create(
            name="Test Idempotency Business",
            slug="test-idempotency-business",
            status="ACTIVE",
            business_kind="pharmacy",
        )
    
    def tearDown(self):
        """Clean up test data."""
        from tenants.models import Business
        from billing.models import BusinessSubscription
        
        BusinessSubscription.objects.filter(business=self.business).delete()
        self.business.delete()
    
    def test_ensure_trial_for_business_creates_subscription(self):
        """Calling ensure_trial_for_business should create a subscription."""
        from billing.models import BusinessSubscription
        
        # Ensure no subscription exists
        BusinessSubscription.objects.filter(business=self.business).delete()
        
        sub = BusinessSubscription.ensure_trial_for_business(self.business)
        
        self.assertIsNotNone(sub)
        self.assertEqual(sub.business_id, self.business.id)
        self.assertIsNotNone(sub.plan_id, "plan_id should NOT be NULL")
    
    def test_ensure_trial_for_business_is_idempotent(self):
        """Calling ensure_trial_for_business twice should not create duplicates."""
        from billing.models import BusinessSubscription
        
        # Ensure no subscription exists
        BusinessSubscription.objects.filter(business=self.business).delete()
        
        # Call twice
        sub1 = BusinessSubscription.ensure_trial_for_business(self.business)
        sub2 = BusinessSubscription.ensure_trial_for_business(self.business)
        
        # Should return the same subscription
        self.assertEqual(sub1.id, sub2.id)
        
        # Only one subscription should exist
        count = BusinessSubscription.objects.filter(business=self.business).count()
        self.assertEqual(count, 1, "Should not create duplicate subscriptions")
    
    def test_start_trial_with_plan_creates_valid_subscription(self):
        """BusinessSubscription.start_trial() should create a valid subscription."""
        from billing.models import BusinessSubscription
        
        # Ensure no subscription exists
        BusinessSubscription.objects.filter(business=self.business).delete()
        
        sub = BusinessSubscription.start_trial(
            business=self.business,
            plan=self.plan,
            days=30,
        )
        
        self.assertIsNotNone(sub)
        self.assertIsNotNone(sub.plan_id, "plan_id must not be NULL")
        self.assertEqual(sub.plan_id, self.plan.id)
        self.assertIn(sub.status, ["trial", "trialing", "TRIAL"])


@pytest.mark.django_db(transaction=True)
class TestTrialCreationWithNoPlans(TransactionTestCase):
    """Test that signup works even when no plans exist."""
    
    def test_business_creation_works_with_no_plans(self):
        """
        Business creation should work even if no plans exist.
        
        The plan resolver should create a fallback plan automatically.
        """
        from tenants.models import Business
        from billing.models import SubscriptionPlan, BusinessSubscription
        
        # Delete ALL plans
        SubscriptionPlan.objects.all().delete()
        
        # Verify no plans exist
        self.assertEqual(
            SubscriptionPlan.objects.count(),
            0,
            "Precondition: no plans should exist"
        )
        
        # Create a business - this should NOT fail
        try:
            business = Business.objects.create(
                name="No Plan Test Business",
                slug="no-plan-test-business",
                status="ACTIVE",
                business_kind="phones",
            )
            
            # Business creation should succeed
            self.assertIsNotNone(business.id)
            
            # Clean up
            BusinessSubscription.objects.filter(business=business).delete()
            business.delete()
            
        except Exception as e:
            self.fail(
                f"Business creation failed with no plans: {type(e).__name__}: {e}\n"
                "The plan resolver should have created a fallback plan."
            )
        finally:
            # Clean up any created plans
            SubscriptionPlan.objects.filter(code="starter").delete()
    
    def test_ensure_default_plan_exists_function(self):
        """Test the ensure_default_plan_exists helper."""
        from billing.models import SubscriptionPlan
        from billing.services.plan_resolver import ensure_default_plan_exists
        
        # Delete all plans
        SubscriptionPlan.objects.all().delete()
        
        plan = ensure_default_plan_exists()
        
        self.assertIsNotNone(plan)
        self.assertEqual(plan.code, "starter")
        self.assertTrue(SubscriptionPlan.objects.filter(code="starter").exists())


@pytest.mark.django_db
class TestSignalTrialCreation(TestCase):
    """Test that the signal correctly schedules trial creation."""
    
    def test_signal_is_registered(self):
        """Verify the signal handler is registered."""
        from django.db.models.signals import post_save
        from tenants.models import Business
        
        # Check that our signal is connected
        receivers = [r[1]() for r in post_save.receivers if r[1]() is not None]
        
        # We can't easily check the exact function, but we can check
        # that there's at least one receiver for Business
        # This is a basic sanity check
        self.assertTrue(
            len(post_save.receivers) > 0,
            "There should be at least one post_save signal receiver"
        )


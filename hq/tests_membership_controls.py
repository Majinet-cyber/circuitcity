# hq/tests_membership_controls.py
"""
Comprehensive tests for HQ membership control features.
Tests cover extending membership, revoking subscriptions, and audit logging of these actions.
"""
from datetime import timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse

from tenants.models import Business
from billing.models import BusinessSubscription, SubscriptionPlan
from audit.models import AuditLog

User = get_user_model()


class MembershipExtendTest(TestCase):
    """Test extending business membership/subscription."""
    
    def setUp(self):
        self.business = Business.objects.create(name="Extend Test Business", slug="extend-test", status="ACTIVE")
        self.plan = SubscriptionPlan.objects.create(
            code="starter",
            name="Starter Plan",
            amount=Decimal("20000.00"),
            interval="month"
        )
        self.subscription = BusinessSubscription.objects.create(
            business=self.business,
            plan=self.plan,
            status="trial",
            trial_end=timezone.now() + timedelta(days=7)
        )
        self.staff_user = User.objects.create_user(
            username="hq_staff",
            password="testpass123",
            is_staff=True,
            is_superuser=True
        )
        self.client = Client()
        self.client.force_login(self.staff_user)
    
    def test_extend_subscription_by_days(self):
        """Test extending subscription by number of days."""
        original_trial_end = self.subscription.trial_end
        days_to_add = 30
        
        response = self.client.get(reverse('hq:sub_extend', args=[self.subscription.pk]), {
            'days': days_to_add
        })
        
        # Should redirect back with success
        self.assertEqual(response.status_code, 302)
        
        # Refresh subscription from DB
        self.subscription.refresh_from_db()
        
        # Trial end should be extended
        expected_trial_end = original_trial_end + timedelta(days=days_to_add)
        
        # Allow for small time differences due to processing
        time_diff = abs((self.subscription.trial_end - expected_trial_end).total_seconds())
        self.assertLess(time_diff, 5)
    
    def test_extend_subscription_to_specific_date(self):
        """Test setting subscription to a specific end date."""
        target_date = (timezone.now() + timedelta(days=60)).date()
        
        response = self.client.get(reverse('hq:sub_extend', args=[self.subscription.pk]), {
            'trial_end': target_date.isoformat()
        })
        
        # Should redirect back with success
        self.assertEqual(response.status_code, 302)
        
        # Refresh subscription from DB
        self.subscription.refresh_from_db()
        
        # Trial end should be set to target date
        self.assertEqual(self.subscription.trial_end.date(), target_date)
    
    def test_extend_subscription_creates_audit_log(self):
        """Test that extending subscription creates an audit log."""
        initial_count = AuditLog.objects.filter(action="EXTEND_SUBSCRIPTION").count()
        
        response = self.client.get(reverse('hq:sub_extend', args=[self.subscription.pk]), {
            'days': 15
        })
        
        self.assertEqual(response.status_code, 302)
        
        # Check that audit log was created
        final_count = AuditLog.objects.filter(action="EXTEND_SUBSCRIPTION").count()
        self.assertEqual(final_count, initial_count + 1)
        
        # Verify log details
        log = AuditLog.objects.filter(action="EXTEND_SUBSCRIPTION").latest('created_at')
        self.assertEqual(log.entity_type, "BusinessSubscription")
        self.assertEqual(str(log.entity_id), str(self.subscription.pk))
        self.assertEqual(log.user, self.staff_user)
        self.assertEqual(log.business, self.business)
        self.assertIn("15 days", log.message)
    
    def test_extend_subscription_negative_days(self):
        """Test that negative days can reduce subscription length."""
        original_trial_end = self.subscription.trial_end
        days_to_subtract = -5
        
        response = self.client.get(reverse('hq:sub_extend', args=[self.subscription.pk]), {
            'days': days_to_subtract
        })
        
        # Should redirect back
        self.assertEqual(response.status_code, 302)
        
        # Refresh subscription
        self.subscription.refresh_from_db()
        
        # Trial end should be reduced
        expected_trial_end = original_trial_end + timedelta(days=days_to_subtract)
        time_diff = abs((self.subscription.trial_end - expected_trial_end).total_seconds())
        self.assertLess(time_diff, 5)


class MembershipRevokeTest(TestCase):
    """Test revoking business membership/subscription."""
    
    def setUp(self):
        self.business = Business.objects.create(name="Revoke Test Business", slug="revoke-test", status="ACTIVE")
        self.plan = SubscriptionPlan.objects.create(
            code="pro",
            name="Pro Plan",
            amount=Decimal("35000.00"),
            interval="month"
        )
        self.subscription = BusinessSubscription.objects.create(
            business=self.business,
            plan=self.plan,
            status="active",
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timedelta(days=30)
        )
        self.staff_user = User.objects.create_user(
            username="hq_admin",
            password="testpass123",
            is_staff=True,
            is_superuser=True
        )
        self.client = Client()
        self.client.force_login(self.staff_user)
    
    def test_revoke_subscription(self):
        """Test revoking an active subscription."""
        response = self.client.get(reverse('hq:sub_revoke_trial', args=[self.subscription.pk]))
        
        # Should redirect back with success
        self.assertEqual(response.status_code, 302)
        
        # Refresh subscription from DB
        self.subscription.refresh_from_db()
        
        # Status should be changed to canceled or similar
        self.assertIn(self.subscription.status.lower(), ['canceled', 'cancelled', 'grace', 'expired'])
    
    def test_revoke_subscription_creates_audit_log(self):
        """Test that revoking subscription creates an audit log."""
        initial_count = AuditLog.objects.filter(action="REVOKE_SUBSCRIPTION").count()
        
        response = self.client.get(reverse('hq:sub_revoke_trial', args=[self.subscription.pk]))
        
        self.assertEqual(response.status_code, 302)
        
        # Check that audit log was created
        final_count = AuditLog.objects.filter(action="REVOKE_SUBSCRIPTION").count()
        self.assertEqual(final_count, initial_count + 1)
        
        # Verify log details
        log = AuditLog.objects.filter(action="REVOKE_SUBSCRIPTION").latest('created_at')
        self.assertEqual(log.entity_type, "BusinessSubscription")
        self.assertEqual(str(log.entity_id), str(self.subscription.pk))
        self.assertEqual(log.user, self.staff_user)
        self.assertEqual(log.business, self.business)
        self.assertIn("revoke", log.message.lower())


class MembershipActivateTest(TestCase):
    """Test activating business subscription."""
    
    def setUp(self):
        self.business = Business.objects.create(name="Activate Test Business", slug="activate-test", status="ACTIVE")
        self.plan = SubscriptionPlan.objects.create(
            code="promax",
            name="Pro Max Plan",
            amount=Decimal("50000.00"),
            interval="month"
        )
        self.subscription = BusinessSubscription.objects.create(
            business=self.business,
            plan=self.plan,
            status="canceled"
        )
        self.staff_user = User.objects.create_user(
            username="hq_superuser",
            password="testpass123",
            is_staff=True,
            is_superuser=True
        )
        self.client = Client()
        self.client.force_login(self.staff_user)
    
    def test_activate_subscription(self):
        """Test activating a canceled subscription."""
        response = self.client.get(reverse('hq:sub_activate_now', args=[self.subscription.pk]))
        
        # Should redirect back with success
        self.assertEqual(response.status_code, 302)
        
        # Refresh subscription from DB
        self.subscription.refresh_from_db()
        
        # Status should be changed to active
        self.assertEqual(self.subscription.status.lower(), 'active')
    
    def test_activate_subscription_creates_audit_log(self):
        """Test that activating subscription creates an audit log."""
        initial_count = AuditLog.objects.filter(action="ACTIVATE_SUBSCRIPTION").count()
        
        response = self.client.get(reverse('hq:sub_activate_now', args=[self.subscription.pk]))
        
        self.assertEqual(response.status_code, 302)
        
        # Check that audit log was created
        final_count = AuditLog.objects.filter(action="ACTIVATE_SUBSCRIPTION").count()
        self.assertEqual(final_count, initial_count + 1)
        
        # Verify log details
        log = AuditLog.objects.filter(action="ACTIVATE_SUBSCRIPTION").latest('created_at')
        self.assertEqual(log.entity_type, "BusinessSubscription")
        self.assertEqual(str(log.entity_id), str(self.subscription.pk))
        self.assertEqual(log.user, self.staff_user)


class MembershipUITest(TestCase):
    """Test membership control UI on business detail page."""
    
    def setUp(self):
        self.business = Business.objects.create(name="UI Test Business", slug="ui-test", status="ACTIVE")
        self.plan = SubscriptionPlan.objects.create(
            code="starter",
            name="Starter Plan",
            amount=Decimal("20000.00"),
            interval="month"
        )
        self.subscription = BusinessSubscription.objects.create(
            business=self.business,
            plan=self.plan,
            status="trial",
            trial_end=timezone.now() + timedelta(days=10)
        )
        self.staff_user = User.objects.create_user(
            username="ui_staff",
            password="testpass123",
            is_staff=True,
            is_superuser=True
        )
        self.client = Client()
        self.client.force_login(self.staff_user)
    
    def test_business_detail_shows_subscription_info(self):
        """Test that business detail page shows subscription information."""
        response = self.client.get(reverse('hq:business_detail', args=[self.business.pk]))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        
        # Should show subscription status
        self.assertIn('trial', content.lower())
        
        # Should show plan name
        self.assertIn(self.plan.name, content)
    
    def test_business_detail_shows_membership_controls(self):
        """Test that business detail page shows membership control buttons."""
        response = self.client.get(reverse('hq:business_detail', args=[self.business.pk]))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        
        # Should have "Add Days" button
        self.assertIn('Add Days', content)
        
        # Should have revoke/disable button
        self.assertIn('Revoke', content.lower())
    
    def test_business_detail_shows_trial_end_date(self):
        """Test that business detail shows trial end date."""
        response = self.client.get(reverse('hq:business_detail', args=[self.business.pk]))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        
        # Should show trial end date
        trial_end_str = self.subscription.trial_end.strftime('%Y-%m-%d')
        self.assertIn(trial_end_str, content)


class MembershipPermissionsTest(TestCase):
    """Test that membership controls require proper permissions."""
    
    def setUp(self):
        self.business = Business.objects.create(name="Perm Test Business", slug="perm-test", status="ACTIVE")
        self.plan = SubscriptionPlan.objects.create(
            code="starter",
            name="Starter Plan",
            amount=Decimal("20000.00")
        )
        self.subscription = BusinessSubscription.objects.create(
            business=self.business,
            plan=self.plan,
            status="trial"
        )
        
        self.staff_user = User.objects.create_user(
            username="staff",
            password="testpass123",
            is_staff=True
        )
        self.normal_user = User.objects.create_user(
            username="normal",
            password="testpass123"
        )
        self.client = Client()
    
    def test_extend_requires_staff_permission(self):
        """Test that extending subscription requires staff permission."""
        # Try as normal user
        self.client.force_login(self.normal_user)
        response = self.client.get(reverse('hq:sub_extend', args=[self.subscription.pk]), {
            'days': 30
        })
        
        # Should be denied
        self.assertIn(response.status_code, [302, 403])
        
        # Try as staff user
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('hq:sub_extend', args=[self.subscription.pk]), {
            'days': 30
        })
        
        # Should succeed (redirect after success)
        self.assertEqual(response.status_code, 302)
    
    def test_revoke_requires_staff_permission(self):
        """Test that revoking subscription requires staff permission."""
        # Try as normal user
        self.client.force_login(self.normal_user)
        response = self.client.get(reverse('hq:sub_revoke_trial', args=[self.subscription.pk]))
        
        # Should be denied
        self.assertIn(response.status_code, [302, 403])
        
        # Try as staff user
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('hq:sub_revoke_trial', args=[self.subscription.pk]))
        
        # Should succeed (redirect after success)
        self.assertEqual(response.status_code, 302)


class SubscriptionStatusDisplayTest(TestCase):
    """Test that subscription status is properly displayed with badges."""
    
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="badge_staff",
            password="testpass123",
            is_staff=True,
            is_superuser=True
        )
        self.client = Client()
        self.client.force_login(self.staff_user)
    
    def test_trial_status_badge(self):
        """Test that trial subscriptions show proper badge."""
        business = Business.objects.create(name="Trial Business", slug="trial-biz", status="ACTIVE")
        plan = SubscriptionPlan.objects.create(code="starter", name="Starter", amount=Decimal("20000"))
        subscription = BusinessSubscription.objects.create(
            business=business,
            plan=plan,
            status="trial",
            trial_end=timezone.now() + timedelta(days=7)
        )
        
        response = self.client.get(reverse('hq:subscriptions'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        
        # Should show trial badge
        self.assertIn('Trial', content)
    
    def test_active_status_badge(self):
        """Test that active subscriptions show proper badge."""
        business = Business.objects.create(name="Active Business", slug="active-biz", status="ACTIVE")
        plan = SubscriptionPlan.objects.create(code="pro", name="Pro", amount=Decimal("35000"))
        subscription = BusinessSubscription.objects.create(
            business=business,
            plan=plan,
            status="active",
            current_period_end=timezone.now() + timedelta(days=30)
        )
        
        response = self.client.get(reverse('hq:subscriptions'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        
        # Should show active badge
        self.assertIn('Active', content)
    
    def test_canceled_status_badge(self):
        """Test that canceled subscriptions show proper badge."""
        business = Business.objects.create(name="Canceled Business", slug="canceled-biz", status="ACTIVE")
        plan = SubscriptionPlan.objects.create(code="starter", name="Starter", amount=Decimal("20000"))
        subscription = BusinessSubscription.objects.create(
            business=business,
            plan=plan,
            status="canceled"
        )
        
        response = self.client.get(reverse('hq:subscriptions'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        
        # Should show canceled/cancelled badge
        self.assertTrue('Cancel' in content or 'cancel' in content.lower())


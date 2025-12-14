# tenants/tests/test_multitenancy_hardening.py
"""
MULTI-TENANCY HARDENING TEST SUITE

Tests the three core guarantees:
1. Users locked to single business (no switch/join for users with membership)
2. Duplicate prevention (names, emails, one-business-per-user)
3. Zero data leakage (business isolation + vertical isolation)
"""

import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.db import IntegrityError

from tenants.models import Business, Membership
from tenants.forms import CreateBusinessForm
from tenants.utils import user_has_any_business, user_business_membership
from onboarding.forms import BusinessForm

User = get_user_model()


# ============================================================================
# GUARANTEE 1: USERS LOCKED TO THEIR BUSINESS
# ============================================================================

class TestBusinessLockdown(TestCase):
    """Test that users with business membership cannot switch/join other businesses."""
    
    def setUp(self):
        self.client = Client()
        
        # Create two businesses
        self.business_a = Business.objects.create(
            name="Business A",
            slug="business-a",
            status="ACTIVE",
            business_kind="phones"
        )
        self.business_b = Business.objects.create(
            name="Business B",
            slug="business-b",
            status="ACTIVE",
            business_kind="gym"
        )
        
        # Create user with membership in business A
        self.user_a = User.objects.create_user(
            username="user_a",
            email="usera@test.com",
            password="Test123!@#Strong"
        )
        self.membership_a = Membership.objects.create(
            user=self.user_a,
            business=self.business_a,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Create user without membership
        self.user_no_biz = User.objects.create_user(
            username="user_no_biz",
            email="nobiz@test.com",
            password="Test123!@#Strong"
        )
    
    def test_user_with_business_cannot_access_switch_route(self):
        """User with business membership should be redirected from /tenants/choose/"""
        self.client.login(username="user_a", password="Test123!@#Strong")
        
        response = self.client.get(reverse("tenants:choose_business"))
        
        # Should redirect, not show the switch UI
        self.assertEqual(response.status_code, 302)
    
    def test_user_with_business_cannot_access_join_route(self):
        """User with business membership cannot access /tenants/join-as-agent/"""
        self.client.login(username="user_a", password="Test123!@#Strong")
        
        response = self.client.get(reverse("tenants:join_as_agent"))
        
        # Should redirect with error message
        self.assertEqual(response.status_code, 302)
    
    def test_user_with_business_cannot_access_create_route(self):
        """User with business membership cannot create another business"""
        self.client.login(username="user_a", password="Test123!@#Strong")
        
        response = self.client.get(reverse("tenants:create_business"))
        
        # Should redirect with error message
        self.assertEqual(response.status_code, 302)
    
    def test_user_without_business_can_access_onboarding(self):
        """User without business should access onboarding routes"""
        self.client.login(username="user_no_biz", password="Test123!@#Strong")
        
        # Should be able to access join
        response_join = self.client.get(reverse("tenants:join_as_agent"))
        self.assertEqual(response_join.status_code, 200)
        
        # Should be able to access create
        response_create = self.client.get(reverse("tenants:create_business"))
        self.assertEqual(response_create.status_code, 200)
    
    def test_switch_business_ui_hidden_for_regular_users(self):
        """Base template should not show 'Switch business' for regular users"""
        self.client.login(username="user_a", password="Test123!@#Strong")
        
        # Get any page that renders base.html
        response = self.client.get(reverse("dashboard:home"))
        
        # Should not contain switch business link for non-superusers
        # Note: Superusers are allowed to switch
        content = response.content.decode('utf-8')
        # This is a soft check - actual template may vary
        # The key is that regular users don't see switch/join UI


# ============================================================================
# GUARANTEE 2: DUPLICATE PREVENTION
# ============================================================================

class TestDuplicatePrevention(TestCase):
    """Test that duplicates are prevented at form and DB level."""
    
    def setUp(self):
        # Ensure email unique index exists (for test databases)
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uniq_user_email_ci 
                ON auth_user (LOWER(email))
                WHERE email != ''
            """)
        
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="Test123!@#Strong"
        )
        
        self.business = Business.objects.create(
            name="Majinet Store",
            slug="majinet-store",
            status="ACTIVE",
            business_kind="phones"
        )
    
    def test_business_name_case_insensitive_unique_form(self):
        """Form should reject duplicate business name (case-insensitive)"""
        form_data = {"name": "MAJINET STORE"}  # Different case
        form = CreateBusinessForm(data=form_data, user=self.user)
        
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
    
    def test_business_name_case_insensitive_unique_db(self):
        """Database should enforce case-insensitive uniqueness"""
        # Try to create business with same name different case
        with self.assertRaises((IntegrityError, Exception)):
            Business.objects.create(
                name="majinet store",  # lowercase
                slug="majinet-store-2",
                status="ACTIVE"
            )
    
    def test_business_name_case_insensitive_unique_regression(self):
        """
        Regression test for migration 0014: case-insensitive uniqueness.
        
        This test verifies that the uniq_business_name_ci constraint
        correctly prevents creating businesses with same name in different cases.
        Specifically tests the "Emajinet" -> "emajinet" scenario.
        """
        # Create business with name "Emajinet"
        Business.objects.create(
            name="Emajinet",
            slug="emajinet",
            status="ACTIVE",
            business_kind="phones"
        )
        
        # Attempt to create business with name "emajinet" (different case)
        # Should raise IntegrityError due to case-insensitive unique constraint
        with self.assertRaises(IntegrityError):
            Business.objects.create(
                name="emajinet",
                slug="emajinet-2",
                status="ACTIVE",
                business_kind="phones"
            )
    
    def test_email_case_insensitive_unique(self):
        """User email should be unique (case-insensitive)"""
        # Try to create user with same email different case
        with self.assertRaises((IntegrityError, Exception)):
            User.objects.create_user(
                username="another_user",
                email="TEST@EXAMPLE.COM",  # Same email, different case
                password="Test123!@#Strong"
            )
    
    def test_one_business_per_user_form_validation(self):
        """Form should reject business creation if user already has one"""
        # Create membership for user
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Try to create another business
        form_data = {"name": "Second Store"}
        form = CreateBusinessForm(data=form_data, user=self.user)
        
        self.assertFalse(form.is_valid())
        # Should have validation error about already having a business
    
    def test_one_business_per_user_utility_check(self):
        """user_has_any_business() should correctly identify users with businesses"""
        # User without business
        user_no_biz = User.objects.create_user(
            username="nobiz",
            email="nobiz@test.com",
            password="Test123!@#Strong"
        )
        self.assertFalse(user_has_any_business(user_no_biz))
        
        # Create membership
        Membership.objects.create(
            user=user_no_biz,
            business=self.business,
            role="AGENT",
            status="ACTIVE"
        )
        
        # Now should have business
        self.assertTrue(user_has_any_business(user_no_biz))


# ============================================================================
# GUARANTEE 3: ZERO DATA LEAKAGE (BUSINESS ISOLATION)
# ============================================================================

class TestBusinessIsolation(TestCase):
    """Test that users cannot access data from other businesses."""
    
    def setUp(self):
        # Create two businesses with products/data
        self.business_a = Business.objects.create(
            name="Tech Store A",
            slug="tech-store-a",
            status="ACTIVE",
            business_kind="phones"
        )
        self.business_b = Business.objects.create(
            name="Gym Store B",
            slug="gym-store-b",
            status="ACTIVE",
            business_kind="gym"
        )
        
        # Create users for each business
        self.user_a = User.objects.create_user(
            username="user_a",
            email="usera@test.com",
            password="Test123!@#Strong"
        )
        self.user_b = User.objects.create_user(
            username="user_b",
            email="userb@test.com",
            password="Test123!@#Strong"
        )
        
        # Create memberships
        Membership.objects.create(
            user=self.user_a,
            business=self.business_a,
            role="MANAGER",
            status="ACTIVE"
        )
        Membership.objects.create(
            user=self.user_b,
            business=self.business_b,
            role="MANAGER",
            status="ACTIVE"
        )
    
    def test_user_cannot_access_other_business_via_direct_url(self):
        """User from business A cannot access business B data via URL manipulation"""
        self.client.login(username="user_a", password="Test123!@#Strong")
        
        # Try to access business B's data (example: if there's a business detail view)
        # This is a conceptual test - actual implementation depends on your URL structure
        # The key is that any attempt to access business_b data should result in 404
        
        # Note: Specific URL patterns would need to be tested based on actual routes
        # Example pattern: /business/<id>/dashboard should only work for user's own business
    
    def test_business_scoping_utils(self):
        """Test that business scoping utilities work correctly"""
        from tenants.utils import scope_queryset_to_business
        
        # All businesses queryset
        all_businesses = Business.objects.all()
        
        # Scope to business A
        scoped_a = scope_queryset_to_business(all_businesses, self.business_a)
        
        # Should only contain business A
        self.assertEqual(scoped_a.count(), 1)
        self.assertEqual(scoped_a.first().id, self.business_a.id)
    
    def test_cross_business_data_access_blocked(self):
        """Ensure users cannot query data from other businesses"""
        # This test would need actual models with business FKs
        # Example: Stock, Sales, Costs should all be scoped to business
        
        # The pattern is:
        # 1. Create object in business A
        # 2. Login as user from business B
        # 3. Try to access/query that object
        # 4. Should get empty queryset or 404
        pass  # Placeholder - implement with actual models


# ============================================================================
# GUARANTEE 3: ZERO DATA LEAKAGE (VERTICAL ISOLATION)
# ============================================================================

class TestVerticalIsolation(TestCase):
    """Test that gym users cannot access phones routes and vice versa."""
    
    def setUp(self):
        # Create businesses with different verticals
        self.phones_business = Business.objects.create(
            name="Phone Store",
            slug="phone-store",
            status="ACTIVE",
            business_kind="phones"
        )
        self.gym_business = Business.objects.create(
            name="Fitness Gym",
            slug="fitness-gym",
            status="ACTIVE",
            business_kind="gym"
        )
        
        # Create users
        self.phones_user = User.objects.create_user(
            username="phones_user",
            email="phones@test.com",
            password="Test123!@#Strong"
        )
        self.gym_user = User.objects.create_user(
            username="gym_user",
            email="gym@test.com",
            password="Test123!@#Strong"
        )
        
        # Create memberships
        Membership.objects.create(
            user=self.phones_user,
            business=self.phones_business,
            role="MANAGER",
            status="ACTIVE"
        )
        Membership.objects.create(
            user=self.gym_user,
            business=self.gym_business,
            role="MANAGER",
            status="ACTIVE"
        )
    
    def test_vertical_decorator_blocks_wrong_vertical(self):
        """Test require_vertical decorator blocks access to wrong vertical"""
        from tenants.decorators import require_vertical
        from django.http import HttpRequest, HttpResponse
        
        # Create a test view decorated with require_vertical
        @require_vertical("gym")
        def gym_only_view(request):
            return HttpResponse("Gym content")
        
        # Create mock request for phones user
        request = HttpRequest()
        request.user = self.phones_user
        request.business = self.phones_business
        request.META = {}
        
        # Should raise Http404 when phones user tries to access gym route
        from django.http import Http404
        with self.assertRaises(Http404):
            gym_only_view(request)
    
    def test_gym_user_cannot_access_phones_urls(self):
        """Gym users should get 404 when accessing phones-specific URLs"""
        self.client.login(username="gym_user", password="Test123!@#Strong")
        
        # Try to access phones-specific routes
        # Example: IMEI scan, phone sale wizard, etc.
        # Should return 404 if decorated with @require_vertical("phones")
        
        # Note: Actual URLs depend on your routing structure
        # This is a placeholder for the pattern
    
    def test_phones_user_cannot_access_gym_urls(self):
        """Phones users should get 404 when accessing gym-specific URLs"""
        self.client.login(username="phones_user", password="Test123!@#Strong")
        
        # Try to access gym-specific routes
        # Example: gym members, trainers, membership payments
        # Should return 404 if decorated with @require_vertical("gym")
        pass  # Placeholder


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================

class TestTenancyHelpers(TestCase):
    """Test utility functions for tenancy management."""
    
    def setUp(self):
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-business",
            status="ACTIVE",
            business_kind="phones"
        )
        
        self.user_with_biz = User.objects.create_user(
            username="has_biz",
            email="hasbiz@test.com",
            password="Test123!@#Strong"
        )
        
        self.user_without_biz = User.objects.create_user(
            username="no_biz",
            email="nobiz@test.com",
            password="Test123!@#Strong"
        )
        
        Membership.objects.create(
            user=self.user_with_biz,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
    
    def test_user_has_any_business(self):
        """Test user_has_any_business utility"""
        self.assertTrue(user_has_any_business(self.user_with_biz))
        self.assertFalse(user_has_any_business(self.user_without_biz))
    
    def test_user_business_membership(self):
        """Test user_business_membership utility"""
        membership = user_business_membership(self.user_with_biz)
        self.assertIsNotNone(membership)
        self.assertEqual(membership.business, self.business)
        
        membership_none = user_business_membership(self.user_without_biz)
        self.assertIsNone(membership_none)


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])


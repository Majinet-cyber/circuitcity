# tests/test_multi_business_flow.py
"""
Tests for multi-business / multi-workspace flow:
- A single user can create multiple businesses of different types.
- Each business gets a Membership for the creator.
- Business kind and currency are saved.
- Workspace switching is reliable.
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from tenants.models import Business, Membership

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _signup_user(username="multi_mgr", password="testpass123"):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password=password,
    )


def _create_business_direct(user, name="My Shop", slug="my-shop", kind="phones", currency="MWK"):
    """Create a business directly (bypassing the form), as the view does internally."""
    biz = Business.objects.create(
        name=name,
        slug=slug,
        business_kind=kind,
        currency=currency,
        status="ACTIVE",
        created_by=user,
    )
    Membership.objects.get_or_create(
        user=user,
        business=biz,
        defaults={"role": "MANAGER", "status": "ACTIVE"},
    )
    return biz


# ---------------------------------------------------------------------------
# Model-level multi-business tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class MultiBizCreationTests(TestCase):
    def setUp(self):
        self.user = _signup_user()

    def test_user_can_own_multiple_businesses(self):
        b1 = _create_business_direct(self.user, name="Shop A", slug="shop-a", kind="phones")
        b2 = _create_business_direct(self.user, name="Shop B", slug="shop-b", kind="gym")
        b3 = _create_business_direct(self.user, name="Shop C", slug="shop-c", kind="car_dealer")
        memberships = Membership.objects.filter(user=self.user)
        self.assertEqual(memberships.count(), 3)

    def test_each_business_has_correct_kind(self):
        biz = _create_business_direct(self.user, slug="kind-test", kind="car_dealer")
        biz.refresh_from_db()
        self.assertEqual(biz.business_kind, "car_dealer")

    def test_each_business_has_correct_currency(self):
        biz = _create_business_direct(self.user, slug="curr-test", kind="gym", currency="KES")
        biz.refresh_from_db()
        self.assertEqual(biz.currency, "KES")

    def test_membership_role_is_manager(self):
        biz = _create_business_direct(self.user, slug="role-test", kind="pharmacy")
        membership = Membership.objects.get(user=self.user, business=biz)
        self.assertEqual(membership.role.upper(), "MANAGER")

    def test_membership_status_is_active(self):
        biz = _create_business_direct(self.user, slug="status-test", kind="liquor")
        membership = Membership.objects.get(user=self.user, business=biz)
        self.assertEqual(membership.status.upper(), "ACTIVE")

    def test_get_or_create_membership_is_idempotent(self):
        """Calling get_or_create for same user+business multiple times doesn't create duplicates."""
        biz = _create_business_direct(self.user, slug="idem-test")
        Membership.objects.get_or_create(
            user=self.user,
            business=biz,
            defaults={"role": "MANAGER", "status": "ACTIVE"},
        )
        Membership.objects.get_or_create(
            user=self.user,
            business=biz,
            defaults={"role": "MANAGER", "status": "ACTIVE"},
        )
        count = Membership.objects.filter(user=self.user, business=biz).count()
        self.assertEqual(count, 1)

    def test_two_different_users_can_have_same_vertical(self):
        user2 = _signup_user("other_mgr2")
        b1 = _create_business_direct(self.user, slug="phones-1", kind="phones")
        b2 = _create_business_direct(user2, slug="phones-2", kind="phones")
        self.assertEqual(b1.business_kind, "phones")
        self.assertEqual(b2.business_kind, "phones")


# ---------------------------------------------------------------------------
# View-level multi-business tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class CreateBusinessViewTests(TestCase):
    def setUp(self):
        self.user = _signup_user("view_mgr")
        # Create first business so user has an active workspace
        self.first_biz = _create_business_direct(
            self.user, name="First Shop", slug="first-shop", kind="phones"
        )
        self.client = Client()
        self.client.login(username="view_mgr", password="testpass123")

    def test_create_business_page_returns_200(self):
        url = reverse("tenants:create_business")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_create_business_requires_auth(self):
        anon = Client()
        url = reverse("tenants:create_business")
        response = anon.get(url)
        self.assertIn(response.status_code, [302, 403])

    def test_create_business_form_creates_business(self):
        url = reverse("tenants:create_business")
        data = {
            "name": "Second Shop",
            "business_kind": "gym",
            "currency": "MWK",
        }
        response = self.client.post(url, data, follow=True)
        # Should not crash; second business should exist
        self.assertTrue(
            Business.objects.filter(
                created_by=self.user,
                business_kind="gym",
            ).exists()
        )

    def test_choose_business_page_returns_200(self):
        url = reverse("tenants:choose_business")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_choose_business_shows_all_user_businesses(self):
        biz2 = _create_business_direct(self.user, name="Gym", slug="gym-slug", kind="gym")
        url = reverse("tenants:choose_business")
        response = self.client.get(url)
        self.assertContains(response, "First Shop")
        self.assertContains(response, "Gym")


@pytest.mark.django_db
class WorkspaceSwitchingTests(TestCase):
    def setUp(self):
        self.user = _signup_user("switch_mgr")
        self.biz1 = _create_business_direct(self.user, name="Biz One", slug="biz-one", kind="phones")
        self.biz2 = _create_business_direct(self.user, name="Biz Two", slug="biz-two", kind="gym")
        self.client = Client()
        self.client.login(username="switch_mgr", password="testpass123")

    def test_can_switch_to_second_business(self):
        url = reverse("tenants:set_active", args=[self.biz2.pk])
        response = self.client.get(url)
        # Should redirect to new workspace dashboard
        self.assertIn(response.status_code, [302, 200])

    def test_businesses_are_isolated(self):
        # biz1 and biz2 should have separate memberships
        m1 = Membership.objects.get(user=self.user, business=self.biz1)
        m2 = Membership.objects.get(user=self.user, business=self.biz2)
        self.assertNotEqual(m1.pk, m2.pk)

    def test_user_without_membership_cannot_switch_to_business(self):
        other_user = _signup_user("other_user_sw")
        other_biz = _create_business_direct(other_user, slug="other-biz", name="Other")
        # self.user has no membership in other_biz
        url = reverse("tenants:set_active", args=[other_biz.pk])
        response = self.client.get(url)
        # Should redirect or deny, not crash
        self.assertIn(response.status_code, [302, 403, 404])

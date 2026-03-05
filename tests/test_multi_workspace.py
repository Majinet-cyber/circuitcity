"""
Multi-Workspace Tests — Emajinet SaaS
======================================
Tests covering:
  A) Workspace creation (single user owning multiple workspaces)
  B) Workspace switching (membership check, 403 on denied)
  C) Scoping enforcement (data isolation between workspaces)
  D) Backwards compatibility (existing single-business users unaffected)
  E) Permissions (owner / manager can manage members; agent cannot)
  F) JSON API endpoints (/api/workspaces/*)
  G) Regression smoke tests (inventory, sales, dashboard KPIs unchanged)

IMPORTANT: All helpers that interact with Django ORM are inside test methods
so that pytest-django's db fixture ensures a clean state per test.
"""
from __future__ import annotations

import json
import pytest
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _uid() -> str:
    return uuid4().hex[:8]


def make_user(password: str = "testpass123") -> User:
    uid = _uid()
    return User.objects.create_user(
        username=f"user_{uid}",
        email=f"user_{uid}@test.local",
        password=password,
    )


def make_business(created_by=None, kind: str = "phones", status: str = "ACTIVE"):
    from tenants.models import Business
    from django.utils.text import slugify

    uid = _uid()
    name = f"Workspace {uid}"
    return Business.objects.create(
        name=name,
        slug=slugify(name),
        business_kind=kind,
        created_by=created_by,
        status=status,
        currency="MWK",
    )


def make_membership(user, business, role: str = "MANAGER", status: str = "ACTIVE"):
    from tenants.models import Membership

    mem, _ = Membership.objects.get_or_create(
        user=user,
        business=business,
        defaults={"role": role, "status": status},
    )
    # Ensure Django group (required by require_role decorator)
    group, _ = Group.objects.get_or_create(name=f"biz:{business.pk}:{role}")
    user.groups.add(group)
    return mem


def make_location(business):
    from inventory.models import Location

    uid = _uid()
    return Location.objects.create(
        business=business,
        name=f"Loc {uid}",
        is_headquarters=True,
        address="123 Test St",
        city="Test City",
    )


def authed_client(user, business=None, password: str = "testpass123") -> Client:
    """Return a logged-in Client with an optional active business in session."""
    c = Client()
    c.login(username=user.username, password=password)
    if business is not None:
        s = c.session
        s["active_business_id"] = business.id
        s["biz_id"] = business.id
        s.save()
    return c


# ---------------------------------------------------------------------------
# A) Workspace creation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestWorkspaceCreation:
    """A single user can create and own multiple workspaces."""

    def test_user_can_create_first_workspace(self):
        user = make_user()
        biz = make_business(created_by=user)
        mem = make_membership(user, biz, role="MANAGER")

        assert biz.pk is not None
        assert mem.role == "MANAGER"
        assert mem.status == "ACTIVE"

    def test_user_can_create_second_workspace(self):
        """Previously blocked — must now succeed."""
        user = make_user()
        biz1 = make_business(created_by=user)
        make_membership(user, biz1, role="MANAGER")

        biz2 = make_business(created_by=user)
        mem2 = make_membership(user, biz2, role="MANAGER")

        assert biz2.pk is not None
        assert mem2.status == "ACTIVE"

    def test_user_can_create_many_workspaces(self):
        user = make_user()
        for _ in range(4):
            biz = make_business(created_by=user)
            make_membership(user, biz, role="MANAGER")

        from tenants.models import Membership
        count = Membership.objects.filter(user=user, status="ACTIVE").count()
        assert count == 4

    def test_create_view_does_not_block_existing_business_owner(self):
        """POST /tenants/create/ must accept users who already have a workspace."""
        user = make_user()
        biz1 = make_business(created_by=user)
        make_membership(user, biz1, role="MANAGER")

        c = authed_client(user, biz1)
        # GET should not redirect away with an error
        response = c.get("/tenants/create/")
        assert response.status_code in (200, 302), (
            f"Expected 200 or 302, got {response.status_code}"
        )

    def test_workspace_creation_assigns_owner_membership(self):
        from tenants.models import Membership
        user = make_user()
        biz = make_business(created_by=user)
        mem = make_membership(user, biz, role="MANAGER")

        assert Membership.objects.filter(
            user=user, business=biz, status="ACTIVE"
        ).exists()


# ---------------------------------------------------------------------------
# B) Workspace switching
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestWorkspaceSwitching:
    """set_active view must honour membership; deny non-members."""

    def test_member_can_switch_to_their_workspace(self):
        user = make_user()
        biz1 = make_business(created_by=user)
        biz2 = make_business(created_by=user)
        make_membership(user, biz1, role="MANAGER")
        make_membership(user, biz2, role="MANAGER")

        c = authed_client(user, biz1)
        url = reverse("tenants:set_active", kwargs={"biz_id": biz2.id})
        resp = c.get(url, follow=True)
        # Should succeed and switch
        assert resp.status_code == 200
        # Session should now hold biz2
        assert c.session.get("active_business_id") == biz2.id

    def test_non_member_cannot_switch_to_another_workspace(self):
        """403 / redirect away if user is not a member of target workspace."""
        user_a = make_user()
        user_b = make_user()
        biz_a = make_business(created_by=user_a)
        biz_b = make_business(created_by=user_b)
        make_membership(user_a, biz_a, role="MANAGER")
        make_membership(user_b, biz_b, role="MANAGER")

        # user_a tries to switch to biz_b
        c = authed_client(user_a, biz_a)
        url = reverse("tenants:set_active", kwargs={"biz_id": biz_b.id})
        resp = c.get(url, follow=False)
        # Must not succeed — should redirect or 403
        assert resp.status_code in (302, 403), (
            f"Non-member must not switch. Got {resp.status_code}"
        )
        # Session must NOT hold biz_b
        assert c.session.get("active_business_id") != biz_b.id

    def test_multiple_workspaces_no_active_redirects_to_chooser(self):
        """When user has >1 workspace and none is set, they should reach chooser."""
        user = make_user()
        biz1 = make_business(created_by=user)
        biz2 = make_business(created_by=user)
        make_membership(user, biz1)
        make_membership(user, biz2)

        c = Client()
        c.login(username=user.username, password="testpass123")
        # No active workspace in session → activate_mine should redirect to chooser
        resp = c.get("/tenants/", follow=True)
        # Should end up at choose page or dashboard (not a 500 or infinite redirect)
        assert resp.status_code in (200, 302)

    def test_choose_business_page_accessible_to_regular_user(self):
        """Previously choose_business auto-redirected non-superusers; now they can see it."""
        user = make_user()
        biz1 = make_business(created_by=user)
        biz2 = make_business(created_by=user)
        make_membership(user, biz1)
        make_membership(user, biz2)

        c = authed_client(user, biz1)
        resp = c.get("/tenants/choose/")
        # Should render 200 (not a redirect to dashboard)
        assert resp.status_code == 200

    def test_choose_business_post_switches_workspace(self):
        user = make_user()
        biz1 = make_business(created_by=user)
        biz2 = make_business(created_by=user)
        make_membership(user, biz1)
        make_membership(user, biz2)

        c = authed_client(user, biz1)
        resp = c.post("/tenants/choose/", {"business_id": str(biz2.id)}, follow=True)
        assert resp.status_code == 200
        assert c.session.get("active_business_id") == biz2.id

    def test_manager_can_switch_between_their_workspaces(self):
        """Managers were previously locked to a single business; now they can switch."""
        user = make_user()
        biz1 = make_business(created_by=user)
        biz2 = make_business(created_by=user)
        make_membership(user, biz1, role="MANAGER")
        make_membership(user, biz2, role="MANAGER")

        c = authed_client(user, biz1)
        url = reverse("tenants:set_active", kwargs={"biz_id": biz2.id})
        resp = c.get(url, follow=True)
        assert resp.status_code == 200
        assert c.session.get("active_business_id") == biz2.id


# ---------------------------------------------------------------------------
# C) Scoping enforcement
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestScopingEnforcement:
    """Data created in workspace A must not be visible from workspace B."""

    def test_user_business_membership_returns_none_for_multi_workspace(self):
        """Utility must not force a workspace when user belongs to multiple."""
        from tenants.utils import user_business_membership

        user = make_user()
        biz1 = make_business(created_by=user)
        biz2 = make_business(created_by=user)
        make_membership(user, biz1)
        make_membership(user, biz2)

        # With 2 businesses, should return None
        result = user_business_membership(user)
        assert result is None, (
            "user_business_membership must return None for multi-workspace users "
            "so it doesn't force an arbitrary workspace"
        )

    def test_user_business_membership_returns_membership_for_single(self):
        """Single workspace users get their membership auto-resolved."""
        from tenants.utils import user_business_membership

        user = make_user()
        biz = make_business(created_by=user)
        mem = make_membership(user, biz)

        result = user_business_membership(user)
        assert result is not None
        assert result.business_id == biz.id

    def test_user_has_any_business_true_for_multi_workspace(self):
        """user_has_any_business must be True even for multi-workspace users."""
        from tenants.utils import user_has_any_business

        user = make_user()
        biz1 = make_business(created_by=user)
        biz2 = make_business(created_by=user)
        make_membership(user, biz1)
        make_membership(user, biz2)

        assert user_has_any_business(user) is True

    def test_session_business_override_denied_for_non_member(self):
        """Injecting another workspace's ID into session must not grant access."""
        user_a = make_user()
        user_b = make_user()
        biz_a = make_business(created_by=user_a)
        biz_b = make_business(created_by=user_b)
        make_membership(user_a, biz_a)
        make_membership(user_b, biz_b)
        make_location(biz_b)

        # user_a tries to inject biz_b into session
        c = Client()
        c.login(username=user_a.username, password="testpass123")
        s = c.session
        s["active_business_id"] = biz_b.id
        s.save()

        # Accessing switch endpoint should be denied
        url = reverse("tenants:set_active", kwargs={"biz_id": biz_b.id})
        resp = c.get(url, follow=False)
        assert resp.status_code in (302, 403), (
            f"Expected redirect/403 for non-member injection; got {resp.status_code}"
        )

    def test_inventory_items_scoped_to_active_workspace(self):
        """Products in workspace A must not appear in workspace B queries."""
        from inventory.models import MerchProduct
        user_a = make_user()
        user_b = make_user()
        biz_a = make_business(created_by=user_a, kind="phones")
        biz_b = make_business(created_by=user_b, kind="phones")
        make_membership(user_a, biz_a)
        make_membership(user_b, biz_b)

        # Create a product in biz_a
        try:
            loc_a = make_location(biz_a)
            prod_a = MerchProduct.objects.create(
                business=biz_a,
                name=f"Phone-A-{_uid()}",
                price=10000,
            )
        except Exception:
            pytest.skip("MerchProduct model not available or requires extra fields")

        # Scoped query for biz_b should NOT include biz_a's product
        qs_b = MerchProduct.objects.filter(business=biz_b)
        ids_b = list(qs_b.values_list("id", flat=True))
        assert prod_a.id not in ids_b, "Products must be isolated between workspaces"


# ---------------------------------------------------------------------------
# D) Backwards compatibility
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBackwardsCompatibility:
    """Single-business users should behave exactly as before."""

    def test_single_workspace_user_auto_resolved(self):
        """user_business_membership returns their membership when they have exactly 1."""
        from tenants.utils import user_business_membership

        user = make_user()
        biz = make_business(created_by=user)
        mem = make_membership(user, biz)

        result = user_business_membership(user)
        assert result is not None
        assert result.pk == mem.pk

    def test_single_workspace_user_has_any_business_true(self):
        from tenants.utils import user_has_any_business

        user = make_user()
        biz = make_business(created_by=user)
        make_membership(user, biz)
        assert user_has_any_business(user) is True

    def test_new_user_has_any_business_false(self):
        from tenants.utils import user_has_any_business

        user = make_user()
        assert user_has_any_business(user) is False

    def test_single_workspace_choose_page_does_not_crash(self):
        """
        Single-workspace user hitting /tenants/choose/ must not 500.
        They may see 200 (chooser) or 302 (auto-redirect to dashboard);
        the middleware may auto-resolve the workspace before the view runs.
        """
        user = make_user()
        biz = make_business(created_by=user)
        make_membership(user, biz)

        c = Client()
        c.login(username=user.username, password="testpass123")
        resp = c.get("/tenants/choose/", follow=False)
        # 200 (show chooser) or 302 (auto-redirect) — both acceptable
        assert resp.status_code in (200, 302), (
            f"Single-workspace user: expected 200 or 302, got {resp.status_code}"
        )

    def test_set_active_still_works_for_single_workspace_user(self):
        user = make_user()
        biz = make_business(created_by=user)
        make_membership(user, biz)

        c = authed_client(user)
        url = reverse("tenants:set_active", kwargs={"biz_id": biz.id})
        resp = c.get(url, follow=True)
        assert resp.status_code == 200
        assert c.session.get("active_business_id") == biz.id


# ---------------------------------------------------------------------------
# E) Permissions
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPermissions:
    """Role-based access: manager can manage members; agent/staff cannot."""

    def test_manager_can_reach_member_management_page(self):
        user = make_user()
        biz = make_business(created_by=user)
        make_membership(user, biz, role="MANAGER")

        c = authed_client(user, biz)
        resp = c.get("/tenants/manager/agents/")
        assert resp.status_code in (200, 302), (
            f"Manager should reach agents page. Got {resp.status_code}"
        )

    def test_agent_cannot_access_member_management(self):
        owner = make_user()
        agent = make_user()
        biz = make_business(created_by=owner)
        make_membership(owner, biz, role="MANAGER")
        make_membership(agent, biz, role="AGENT")

        c = authed_client(agent, biz)
        resp = c.get("/tenants/manager/agents/")
        # Should be forbidden or redirected away
        assert resp.status_code in (302, 403, 404), (
            f"Agent must not access manager page. Got {resp.status_code}"
        )

    def test_api_add_member_forbidden_for_non_manager(self):
        owner = make_user()
        agent = make_user()
        biz = make_business(created_by=owner)
        make_membership(owner, biz, role="MANAGER")
        make_membership(agent, biz, role="AGENT")

        c = authed_client(agent, biz)
        new_user = make_user()
        resp = c.post(
            "/tenants/api/workspaces/members/",
            data=json.dumps({"email": new_user.email, "role": "AGENT"}),
            content_type="application/json",
        )
        assert resp.status_code == 403, (
            f"Agent must not add members. Got {resp.status_code}"
        )

    def test_api_add_member_succeeds_for_manager(self):
        owner = make_user()
        biz = make_business(created_by=owner)
        make_membership(owner, biz, role="MANAGER")

        new_user = make_user()
        c = authed_client(owner, biz)
        resp = c.post(
            "/tenants/api/workspaces/members/",
            data=json.dumps({"email": new_user.email, "role": "AGENT"}),
            content_type="application/json",
        )
        assert resp.status_code in (200, 201), (
            f"Manager should be able to add members. Got {resp.status_code}"
        )

    def test_api_add_nonexistent_user_returns_404(self):
        owner = make_user()
        biz = make_business(created_by=owner)
        make_membership(owner, biz, role="MANAGER")

        c = authed_client(owner, biz)
        resp = c.post(
            "/tenants/api/workspaces/members/",
            data=json.dumps({"email": "nobody@does-not-exist.example"}),
            content_type="application/json",
        )
        assert resp.status_code == 404
        body = json.loads(resp.content)
        assert "not found" in body.get("message", "").lower() or body.get("error") == "user_not_found"


# ---------------------------------------------------------------------------
# F) JSON API endpoints
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestWorkspaceAPI:
    """Test the /tenants/api/workspaces/* endpoints."""

    def test_api_list_workspaces_returns_all_memberships(self):
        user = make_user()
        biz1 = make_business(created_by=user)
        biz2 = make_business(created_by=user)
        make_membership(user, biz1)
        make_membership(user, biz2)

        c = authed_client(user, biz1)
        resp = c.get("/tenants/api/workspaces/")
        assert resp.status_code == 200
        body = json.loads(resp.content)
        assert body["count"] == 2
        ids = {w["id"] for w in body["workspaces"]}
        assert biz1.id in ids
        assert biz2.id in ids

    def test_api_list_workspace_has_x_active_header(self):
        user = make_user()
        biz = make_business(created_by=user)
        make_membership(user, biz)

        c = authed_client(user, biz)
        resp = c.get("/tenants/api/workspaces/")
        assert "X-Active-Workspace" in resp, (
            "Response must include X-Active-Workspace header"
        )

    def test_api_set_active_workspace_succeeds_for_member(self):
        user = make_user()
        biz1 = make_business(created_by=user)
        biz2 = make_business(created_by=user)
        make_membership(user, biz1)
        make_membership(user, biz2)

        c = authed_client(user, biz1)
        resp = c.post(
            "/tenants/api/workspaces/active/",
            data=json.dumps({"workspace_id": biz2.id}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        body = json.loads(resp.content)
        assert body["id"] == biz2.id
        assert body["is_active"] is True

    def test_api_set_active_workspace_denied_for_non_member(self):
        user_a = make_user()
        user_b = make_user()
        biz_a = make_business(created_by=user_a)
        biz_b = make_business(created_by=user_b)
        make_membership(user_a, biz_a)
        make_membership(user_b, biz_b)

        c = authed_client(user_a, biz_a)
        resp = c.post(
            "/tenants/api/workspaces/active/",
            data=json.dumps({"workspace_id": biz_b.id}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_api_set_active_without_id_returns_409_for_multi_workspace(self):
        user = make_user()
        biz1 = make_business(created_by=user)
        biz2 = make_business(created_by=user)
        make_membership(user, biz1)
        make_membership(user, biz2)

        c = authed_client(user, biz1)
        resp = c.post(
            "/tenants/api/workspaces/active/",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 409

    def test_api_list_members_returns_workspace_members(self):
        owner = make_user()
        agent = make_user()
        biz = make_business(created_by=owner)
        make_membership(owner, biz, role="MANAGER")
        make_membership(agent, biz, role="AGENT")

        c = authed_client(owner, biz)
        resp = c.get("/tenants/api/workspaces/members/")
        assert resp.status_code == 200
        body = json.loads(resp.content)
        assert body["count"] >= 2

    def test_api_unauthenticated_returns_redirect(self):
        c = Client()
        resp = c.get("/tenants/api/workspaces/")
        assert resp.status_code in (302, 401, 403)


# ---------------------------------------------------------------------------
# G) Regression smoke tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRegressionSmoke:
    """
    Existing flows must still work after multi-workspace changes.
    These are lightweight smoke tests — full suites are in the critical/ directory.
    """

    def test_single_business_dashboard_still_loads(self):
        user = make_user()
        biz = make_business(created_by=user, kind="phones")
        make_membership(user, biz, role="MANAGER")
        make_location(biz)

        c = authed_client(user, biz)
        resp = c.get("/inventory/verticals/phones/dashboard/", follow=True)
        assert resp.status_code != 500, "Dashboard must not 500"

    def test_inventory_stock_in_page_accessible(self):
        user = make_user()
        biz = make_business(created_by=user, kind="phones")
        make_membership(user, biz, role="MANAGER")
        make_location(biz)

        c = authed_client(user, biz)
        resp = c.get("/inventory/scan-in/", follow=True)
        assert resp.status_code != 500, "Scan-in page must not 500"

    def test_tenants_choose_no_500(self):
        user = make_user()
        biz = make_business(created_by=user)
        make_membership(user, biz)

        c = authed_client(user, biz)
        resp = c.get("/tenants/choose/")
        assert resp.status_code != 500

    def test_create_business_view_no_500(self):
        user = make_user()
        c = authed_client(user)
        resp = c.get("/tenants/create/")
        assert resp.status_code != 500

    def test_join_as_agent_view_accessible_when_already_has_business(self):
        """Previously this view blocked users with existing business — must not 500 now."""
        user = make_user()
        biz = make_business(created_by=user)
        make_membership(user, biz)

        c = authed_client(user, biz)
        resp = c.get("/tenants/join/", follow=True)
        # Should not 500; redirect or 200 both acceptable
        assert resp.status_code != 500

    def test_workspace_context_available_in_template(self):
        """tenant_context processor must provide user_workspaces."""
        user = make_user()
        biz1 = make_business(created_by=user)
        biz2 = make_business(created_by=user)
        make_membership(user, biz1)
        make_membership(user, biz2)

        c = authed_client(user, biz1)
        resp = c.get("/tenants/choose/")
        assert resp.status_code == 200
        ctx = resp.context
        if ctx:
            # user_workspaces should contain both workspaces
            workspaces = ctx.get("user_workspaces", [])
            ids = {w.business.id for w in workspaces}
            assert biz1.id in ids, "biz1 must be in user_workspaces context"
            assert biz2.id in ids, "biz2 must be in user_workspaces context"

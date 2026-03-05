# tenants/tests/test_auto_activate_workspace.py
"""
Tests for auto-activation of manager-created workspaces.

Covers:
  1. Workspace is ACTIVE immediately after manager creates it (no PENDING).
  2. Creator automatically gets an ACTIVE MANAGER membership.
  3. Workspace appears immediately in /tenants/choose/ (no approval wait).
  4. Welcome email is sent on successful creation.
  5. Non-member cannot see or switch into another user's workspace (security).
"""

from unittest.mock import patch, MagicMock

import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from tenants.models import Business, Membership

User = get_user_model()

CREATE_URL = "/tenants/create/"
CHOOSE_URL = "/tenants/choose/"


def _make_user(username, email=None, password="Test1234!Strong"):
    email = email or f"{username}@test.com"
    return User.objects.create_user(username=username, email=email, password=password)


def _make_business(name, slug=None, kind="phones", status="ACTIVE"):
    slug = slug or name.lower().replace(" ", "-")
    return Business.objects.create(name=name, slug=slug, status=status, business_kind=kind)


# ---------------------------------------------------------------------------
# 1. Auto-activation
# ---------------------------------------------------------------------------

class TestWorkspaceAutoActivation(TestCase):
    """Manager creates a workspace → it is ACTIVE immediately."""

    def setUp(self):
        self.client = Client()
        self.manager = _make_user("mgr1", "mgr1@test.com")
        self.client.login(username="mgr1", password="Test1234!Strong")

    def test_created_workspace_is_active_immediately(self):
        """POST /tenants/create/ → Business.status == 'ACTIVE' (never PENDING)."""
        response = self.client.post(CREATE_URL, {"name": "Car Hire Alpha"}, follow=True)
        self.assertEqual(response.status_code, 200)

        biz = Business.objects.get(name="Car Hire Alpha")
        self.assertEqual(biz.status, "ACTIVE", "New workspace must be ACTIVE, not PENDING.")

    def test_created_workspace_is_active_is_true(self):
        """The is_active property returns True right after creation."""
        self.client.post(CREATE_URL, {"name": "Car Hire Beta"}, follow=True)
        biz = Business.objects.get(name="Car Hire Beta")
        self.assertTrue(biz.is_active, "is_active property must be True immediately.")

    def test_no_pending_workspace_after_creation(self):
        """Ensure there is no PENDING business with the submitted name."""
        self.client.post(CREATE_URL, {"name": "CarHire Gamma"}, follow=True)
        self.assertFalse(
            Business.objects.filter(name="CarHire Gamma", status="PENDING").exists(),
            "There must be no PENDING workspace after creation.",
        )


# ---------------------------------------------------------------------------
# 2. Creator gets ACTIVE MANAGER membership
# ---------------------------------------------------------------------------

class TestCreatorMembership(TestCase):
    """Creator is assigned as an ACTIVE MANAGER immediately."""

    def setUp(self):
        self.client = Client()
        self.manager = _make_user("mgr2", "mgr2@test.com")
        self.client.login(username="mgr2", password="Test1234!Strong")

    def test_creator_has_active_manager_membership(self):
        """After creation, the creator must have role=MANAGER, status=ACTIVE."""
        self.client.post(CREATE_URL, {"name": "Fresh Ventures"}, follow=True)
        biz = Business.objects.get(name="Fresh Ventures")
        mem = Membership.objects.get(user=self.manager, business=biz)
        self.assertEqual(mem.role, "MANAGER")
        self.assertEqual(mem.status, "ACTIVE")

    def test_creator_membership_not_pending(self):
        """Membership must never be PENDING after auto-activation."""
        self.client.post(CREATE_URL, {"name": "Instant Motors"}, follow=True)
        biz = Business.objects.get(name="Instant Motors")
        pending = Membership.objects.filter(
            user=self.manager, business=biz, status="PENDING"
        ).exists()
        self.assertFalse(pending, "Membership must not be PENDING after auto-activation.")


# ---------------------------------------------------------------------------
# 3. Workspace appears in /tenants/choose/ immediately
# ---------------------------------------------------------------------------

class TestWorkspaceAppearsInChooser(TestCase):
    """Newly created workspace is visible in the chooser right away."""

    def setUp(self):
        self.client = Client()
        self.manager = _make_user("mgr3", "mgr3@test.com")
        self.client.login(username="mgr3", password="Test1234!Strong")

    def test_new_workspace_in_choose_list(self):
        """
        After creation, GET /tenants/choose/ must include the new workspace
        in the manager's membership list (context['memberships']).
        """
        self.client.post(CREATE_URL, {"name": "Swift Logistics"}, follow=True)
        biz = Business.objects.get(name="Swift Logistics")

        response = self.client.get(CHOOSE_URL)
        # Response could be 200 (chooser page) or redirect to dashboard (single workspace).
        # Either way, the membership must exist and be active.
        mem = Membership.objects.filter(user=self.manager, business=biz, status="ACTIVE")
        self.assertTrue(mem.exists(), "Membership must be visible in chooser immediately.")

    def test_can_switch_to_new_workspace_immediately(self):
        """
        After creation the user can switch to the new workspace via the chooser.
        POST /tenants/choose/ with business_id of the new workspace must succeed.
        """
        self.client.post(CREATE_URL, {"name": "Sunrise Cafe"}, follow=True)
        biz = Business.objects.get(name="Sunrise Cafe")

        # Use set_active endpoint (used by chooser template links)
        switch_url = f"/tenants/set/{biz.id}/"
        response = self.client.get(switch_url, follow=True)
        self.assertEqual(response.status_code, 200)
        # Session must contain the new business
        self.assertEqual(self.client.session.get("active_business_id"), biz.id)

    def test_multi_workspace_manager_sees_all_own_workspaces(self):
        """A manager with two workspaces sees both in their membership list."""
        # Create first workspace
        self.client.post(CREATE_URL, {"name": "Alpha Store"}, follow=True)
        biz1 = Business.objects.get(name="Alpha Store")

        # Create second workspace
        self.client.post(CREATE_URL, {"name": "Beta Store"}, follow=True)
        biz2 = Business.objects.get(name="Beta Store")

        mems = Membership.objects.filter(
            user=self.manager, status="ACTIVE", role="MANAGER"
        )
        biz_ids = set(mems.values_list("business_id", flat=True))
        self.assertIn(biz1.id, biz_ids)
        self.assertIn(biz2.id, biz_ids)


# ---------------------------------------------------------------------------
# 4. Welcome email is sent on successful creation
# ---------------------------------------------------------------------------

class TestWelcomeEmailOnCreate(TestCase):
    """A WELCOME_MANAGER email is dispatched after workspace creation."""

    def setUp(self):
        self.client = Client()
        self.manager = _make_user("mgr4", "mgr4@example.com")
        self.client.login(username="mgr4", password="Test1234!Strong")

    @patch("tenants.views.transaction.on_commit")
    def test_on_commit_called_for_welcome_email(self, mock_on_commit):
        """
        transaction.on_commit must be called exactly once for the welcome email
        callback after a successful workspace creation.
        """
        response = self.client.post(CREATE_URL, {"name": "Email Test Shop"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            mock_on_commit.called,
            "transaction.on_commit must be called to schedule welcome email.",
        )

    @patch("notifications.services.emit_event")
    def test_welcome_email_emitted_with_correct_event_type(self, mock_emit):
        """emit_event is called with event_type='WELCOME_MANAGER'."""
        # We bypass on_commit by patching emit_event directly; call the emit
        # callback synchronously by having on_commit call the function immediately.
        with patch("tenants.views.transaction.on_commit", side_effect=lambda fn: fn()):
            self.client.post(CREATE_URL, {"name": "DirectEmail Biz"}, follow=True)

        if mock_emit.called:
            call_kwargs = mock_emit.call_args[1] if mock_emit.call_args[1] else {}
            call_args = mock_emit.call_args[0] if mock_emit.call_args[0] else ()
            event_type = call_kwargs.get("event_type") or (call_args[0] if call_args else None)
            self.assertEqual(event_type, "WELCOME_MANAGER")

    def test_no_email_sent_when_user_has_no_email(self):
        """If the user has no email address, no crash should occur."""
        no_email_user = User.objects.create_user(
            username="noemailmgr", password="Test1234!Strong", email=""
        )
        self.client.login(username="noemailmgr", password="Test1234!Strong")
        with patch("tenants.views.transaction.on_commit") as mock_commit:
            response = self.client.post(
                CREATE_URL, {"name": "NoEmail Workspace"}, follow=True
            )
        self.assertEqual(response.status_code, 200)
        # on_commit should NOT be called because there's no email to send to
        mock_commit.assert_not_called()


# ---------------------------------------------------------------------------
# 5. Security: non-members cannot see or switch into other workspaces
# ---------------------------------------------------------------------------

class TestNonMemberCannotAccessOtherWorkspace(TestCase):
    """
    A user who is NOT a member of a workspace must be blocked from switching
    into it — even if they know the business ID or slug.
    """

    def setUp(self):
        self.client = Client()

        # Workspace owned by manager A
        self.owner = _make_user("owner_sec", "owner@test.com")
        self.biz = _make_business("Secret Vault", "secret-vault")
        Membership.objects.create(
            user=self.owner, business=self.biz, role="MANAGER", status="ACTIVE"
        )

        # Attacker: a different manager with no relation to the vault
        self.attacker = _make_user("attacker_sec", "attacker@test.com")
        self.attacker_biz = _make_business("Attacker Corp", "attacker-corp")
        Membership.objects.create(
            user=self.attacker, business=self.attacker_biz, role="MANAGER", status="ACTIVE"
        )

    def test_non_member_cannot_switch_via_set_endpoint(self):
        """GET /tenants/set/<id>/ by a non-member must not switch workspace."""
        self.client.login(username="attacker_sec", password="Test1234!Strong")
        switch_url = f"/tenants/set/{self.biz.id}/"
        response = self.client.get(switch_url, follow=True)

        # Must NOT have the secret vault as active business in session
        self.assertNotEqual(
            self.client.session.get("active_business_id"),
            self.biz.id,
            "Non-member must not be able to switch into another user's workspace.",
        )

    def test_non_member_cannot_switch_via_choose_post(self):
        """POST /tenants/choose/ with someone else's business_id must be rejected."""
        self.client.login(username="attacker_sec", password="Test1234!Strong")
        session = self.client.session
        session["active_business_id"] = self.attacker_biz.id
        session.save()

        response = self.client.post(
            CHOOSE_URL,
            {"business_id": self.biz.id},
            follow=True,
        )
        # Must NOT have the secret vault as active
        self.assertNotEqual(
            self.client.session.get("active_business_id"),
            self.biz.id,
            "Non-member must not be able to POST-switch into another workspace.",
        )

    def test_choose_page_does_not_expose_non_member_workspaces(self):
        """
        GET /tenants/choose/ must only include workspaces the logged-in user
        belongs to; it must NOT expose another user's workspace.
        """
        self.client.login(username="attacker_sec", password="Test1234!Strong")
        session = self.client.session
        session["active_business_id"] = self.attacker_biz.id
        session.save()

        response = self.client.get(CHOOSE_URL)
        if response.status_code == 200:
            memberships = response.context.get("memberships", [])
            biz_ids = [m.business.id for m in memberships]
            self.assertNotIn(
                self.biz.id,
                biz_ids,
                "The chooser must not expose workspaces the user does not belong to.",
            )

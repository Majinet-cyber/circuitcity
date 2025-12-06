# tests/test_agents_and_invites.py
"""
Comprehensive tests for agent invite + login + suspend/restore flows.
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from tenants.models import Business, Membership, AgentInvite

try:
    from inventory.models import Location
except ImportError:
    Location = None

User = get_user_model()


class AgentInviteFlowTestCase(TestCase):
    """Test the complete agent invite + login flow."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        
        # Create a manager user
        self.manager = User.objects.create_user(
            username="manager1",
            password="testpass123",
            email="manager@test.com"
        )
        
        # Create a business
        self.business = Business.objects.create(
            name="Test Shop",
            slug="test-shop",
            status="ACTIVE"
        )
        
        # Create manager membership
        self.manager_membership = Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Create a location if available
        if Location:
            self.location = Location.objects.create(
                business=self.business,
                name="Main Store"
            )
        else:
            self.location = None

    def test_manager_can_invite_agent_and_get_link_and_password(self):
        """Manager invites an agent and receives both invite link and temp password."""
        # Login as manager
        self.client.login(username="manager1", password="testpass123")
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Create invite
        response = self.client.post(
            reverse('tenants:create_agent_invite'),
            {
                'invited_name': 'Test Agent',
                'email': 'agent@test.com',
                'phone': '',
                'ttl_days': '7',
                'message': 'Welcome!',
            }
        )
        
        # Should redirect with success
        self.assertEqual(response.status_code, 302)
        
        # Check that invite was created
        invite = AgentInvite.objects.filter(business=self.business).first()
        self.assertIsNotNone(invite)
        self.assertEqual(invite.invited_name, 'Test Agent')
        self.assertEqual(invite.email, 'agent@test.com')
        
        # Check that temp password was generated (hash exists)
        self.assertTrue(invite.temp_password_hash)
        
        # Check redirect URL contains latest_link and temp_password params
        redirect_url = response.url
        self.assertIn('latest_link=', redirect_url)
        self.assertIn('temp_password=', redirect_url)

    def test_agent_can_login_with_default_password(self):
        """Agent can log in using the temporary password."""
        # Create an invite with a known temp password
        invite = AgentInvite.objects.create(
            business=self.business,
            invited_name="Agent User",
            email="agent2@test.com",
            status="SENT",
            expires_at=timezone.now() + timedelta(days=7)
        )
        
        # Set a known temp password
        temp_password = "TempPass123"
        invite.set_temp_password(temp_password)
        invite.save()
        
        # Create user for this agent
        agent_user = User.objects.create_user(
            username="agent2",
            password=temp_password,
            email="agent2@test.com"
        )
        
        # Create membership
        Membership.objects.create(
            user=agent_user,
            business=self.business,
            role="AGENT",
            status="ACTIVE"
        )
        
        # Try to login with temp password
        login_success = self.client.login(username="agent2", password=temp_password)
        self.assertTrue(login_success, "Agent should be able to login with temp password")

    def test_agent_cannot_login_when_suspended(self):
        """Suspended agent cannot log in."""
        # Create agent user
        agent_user = User.objects.create_user(
            username="agent3",
            password="testpass123",
            email="agent3@test.com",
            is_active=True
        )
        
        # Create membership
        membership = Membership.objects.create(
            user=agent_user,
            business=self.business,
            role="AGENT",
            status="ACTIVE"
        )
        
        # Login as manager
        self.client.login(username="manager1", password="testpass123")
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Suspend the agent
        response = self.client.post(
            reverse('tenants:suspend_agent', args=[membership.id])
        )
        self.assertEqual(response.status_code, 302)
        
        # Refresh membership
        membership.refresh_from_db()
        agent_user.refresh_from_db()
        
        # Check that agent is suspended
        self.assertEqual(membership.status, "SUSPENDED")
        self.assertFalse(agent_user.is_active)
        
        # Logout manager
        self.client.logout()
        
        # Try to login as suspended agent
        login_success = self.client.login(username="agent3", password="testpass123")
        self.assertFalse(login_success, "Suspended agent should not be able to login")

    def test_manager_can_restore_suspended_agent(self):
        """Manager can restore a suspended agent."""
        # Create suspended agent
        agent_user = User.objects.create_user(
            username="agent4",
            password="testpass123",
            email="agent4@test.com",
            is_active=False  # Suspended
        )
        
        membership = Membership.objects.create(
            user=agent_user,
            business=self.business,
            role="AGENT",
            status="SUSPENDED"
        )
        
        # Login as manager
        self.client.login(username="manager1", password="testpass123")
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Restore the agent
        response = self.client.post(
            reverse('tenants:restore_agent', args=[membership.id])
        )
        self.assertEqual(response.status_code, 302)
        
        # Refresh
        membership.refresh_from_db()
        agent_user.refresh_from_db()
        
        # Check that agent is restored
        self.assertEqual(membership.status, "ACTIVE")
        self.assertTrue(agent_user.is_active)
        
        # Logout manager
        self.client.logout()
        
        # Agent should now be able to login
        login_success = self.client.login(username="agent4", password="testpass123")
        self.assertTrue(login_success, "Restored agent should be able to login")

    def test_invite_link_allows_setting_password_and_marks_used(self):
        """Agent can use invite link to set password and join."""
        # Create an invite
        invite = AgentInvite.objects.create(
            business=self.business,
            invited_name="New Agent",
            email="newagent@test.com",
            status="SENT",
            expires_at=timezone.now() + timedelta(days=7)
        )
        
        # Generate temp password
        temp_password = invite.create_and_set_temp_password()
        invite.save()
        
        # Agent visits invite link
        invite_url = reverse('tenants:invite_accept', args=[invite.token])
        response = self.client.get(invite_url)
        
        # Should show signup/accept page
        self.assertEqual(response.status_code, 200)
        
        # Agent creates account via the invite
        response = self.client.post(
            invite_url,
            {
                'username': 'newagent',
                'password1': 'newpass123',
                'password2': 'newpass123',
            }
        )
        
        # Should redirect after success
        self.assertEqual(response.status_code, 302)
        
        # Check that user was created
        new_user = User.objects.filter(username='newagent').first()
        self.assertIsNotNone(new_user)
        
        # Check that membership was created
        membership = Membership.objects.filter(
            user=new_user,
            business=self.business,
            role="AGENT"
        ).first()
        self.assertIsNotNone(membership)
        self.assertEqual(membership.status, "ACTIVE")
        
        # Check that invite was marked as joined
        invite.refresh_from_db()
        self.assertEqual(invite.status, "JOINED")

    def test_invite_invalid_or_expired_token_shows_friendly_message(self):
        """Invalid or expired invite token shows friendly error."""
        # Test with fake token
        fake_url = reverse('tenants:invite_accept', args=['fake-token-12345'])
        response = self.client.get(fake_url)
        
        # Should return 404 or error page
        self.assertIn(response.status_code, [404, 400])
        
        # Create expired invite
        expired_invite = AgentInvite.objects.create(
            business=self.business,
            invited_name="Expired Agent",
            email="expired@test.com",
            status="EXPIRED",
            expires_at=timezone.now() - timedelta(days=1)
        )
        
        # Try to access expired invite
        expired_url = reverse('tenants:invite_accept', args=[expired_invite.token])
        response = self.client.get(expired_url)
        
        # Should show expired message
        self.assertIn(response.status_code, [410, 400, 200])
        if response.status_code == 200:
            self.assertIn(b'expired', response.content.lower())

    def test_manager_can_assign_location_to_agent(self):
        """Manager can assign/change agent's location."""
        if not Location:
            self.skipTest("Location model not available")
        
        # Create agent
        agent_user = User.objects.create_user(
            username="agent5",
            password="testpass123",
            email="agent5@test.com"
        )
        
        membership = Membership.objects.create(
            user=agent_user,
            business=self.business,
            role="AGENT",
            status="ACTIVE"
        )
        
        # Login as manager
        self.client.login(username="manager1", password="testpass123")
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Assign location
        response = self.client.post(
            reverse('tenants:edit_agent_location', args=[membership.id]),
            {'location_id': self.location.id}
        )
        self.assertEqual(response.status_code, 302)
        
        # Refresh membership
        membership.refresh_from_db()
        
        # Check that location was assigned
        self.assertEqual(membership.location, self.location)

    def test_temp_password_verification(self):
        """Test temp password hashing and verification."""
        invite = AgentInvite.objects.create(
            business=self.business,
            invited_name="Test",
            email="test@test.com"
        )
        
        # Generate temp password
        temp_pass = invite.create_and_set_temp_password()
        invite.save()
        
        # Verify correct password
        self.assertTrue(invite.check_temp_password(temp_pass))
        
        # Verify wrong password
        self.assertFalse(invite.check_temp_password("wrongpass"))
        
        # Check that password is not stored in plaintext
        self.assertNotEqual(invite.temp_password_hash, temp_pass)
        self.assertTrue(len(invite.temp_password_hash) > 20)  # Hashed


class AgentInviteEdgeCasesTestCase(TestCase):
    """Test edge cases and error handling."""

    def setUp(self):
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-biz",
            status="ACTIVE"
        )

    def test_invite_without_email_or_phone(self):
        """Can create invite with just a name."""
        invite = AgentInvite.objects.create(
            business=self.business,
            invited_name="Name Only",
            status="SENT"
        )
        
        self.assertEqual(invite.invited_name, "Name Only")
        self.assertEqual(invite.email, "")
        self.assertEqual(invite.phone, "")

    def test_multiple_invites_same_email(self):
        """Can create multiple invites for same email (resend scenario)."""
        invite1 = AgentInvite.objects.create(
            business=self.business,
            invited_name="Agent",
            email="same@test.com",
            status="SENT"
        )
        
        invite2 = AgentInvite.objects.create(
            business=self.business,
            invited_name="Agent",
            email="same@test.com",
            status="SENT"
        )
        
        # Both should exist with different tokens
        self.assertNotEqual(invite1.token, invite2.token)

    def test_invite_token_is_unique(self):
        """Each invite gets a unique token."""
        invite1 = AgentInvite.objects.create(
            business=self.business,
            invited_name="Agent 1"
        )
        
        invite2 = AgentInvite.objects.create(
            business=self.business,
            invited_name="Agent 2"
        )
        
        self.assertNotEqual(invite1.token, invite2.token)
        self.assertTrue(len(invite1.token) > 10)
        self.assertTrue(len(invite2.token) > 10)
    
    def test_invite_accept_get_renders_form(self):
        """GET request to invite accept URL renders the form page."""
        invite = AgentInvite.objects.create(
            business=self.business,
            email="newhire@test.com",
            invited_name="New Hire",
            expires_at=timezone.now() + timedelta(days=7)
        )
        
        url = reverse("tenants:invite_accept", args=[invite.token])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Join")
        self.assertContains(response, self.business.name)
        # Check for CSRF token in the form
        self.assertContains(response, "csrfmiddlewaretoken")
    
    def test_invite_accept_post_no_csrf_error(self):
        """
        POST to invite accept doesn't fail with CSRF 403.
        This is a smoke test to ensure CSRF handling is correct.
        We don't validate the full flow (user/membership creation) here,
        just that the POST doesn't return a 403 CSRF error.
        """
        invite = AgentInvite.objects.create(
            business=self.business,
            email="newhire@test.com",
            invited_name="New Hire",
            expires_at=timezone.now() + timedelta(days=7)
        )
        
        url = reverse("tenants:invite_accept", args=[invite.token])
        
        # Simulate POST with valid signup data
        post_data = {
            "email": "newhire@test.com",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
            "name": "New Hire",
        }
        
        # Django test client automatically handles CSRF
        response = self.client.post(url, post_data, follow=True)
        
        # The key assertion: should NOT return 403 (CSRF error)
        self.assertNotEqual(response.status_code, 403, 
            "POST should not fail with CSRF 403 error")
        
        # Should be either 200 (success), 400 (validation error), or 500 (other error)
        # but NOT 403 which would indicate CSRF problems
        self.assertIn(response.status_code, [200, 400, 500],
            f"Expected 200/400/500, got {response.status_code}")
    
    def test_invite_accept_creates_user_and_membership(self):
        """
        Complete invite accept flow:
        - POST with valid data creates user, logs them in, creates membership
        - Invite is marked as used
        - User is redirected to agent dashboard
        """
        # Create a fresh invite
        invite = AgentInvite.objects.create(
            business=self.business,
            email="newhire@example.com",
            invited_name="New Hire",
            token="test-token-12345",
            expires_at=timezone.now() + timedelta(days=7),
            status="SENT"
        )
        
        # Verify user doesn't exist yet
        self.assertFalse(User.objects.filter(email="newhire@example.com").exists())
        
        # POST to accept invite
        url = reverse("tenants:invite_accept", args=[invite.token])
        post_data = {
            "email": "newhire@example.com",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        }
        
        response = self.client.post(url, post_data, follow=True)
        
        # Should succeed (200 OK after redirect)
        self.assertEqual(response.status_code, 200, 
            f"Expected 200 after successful invite accept, got {response.status_code}")
        
        # User should now exist
        user = User.objects.filter(email="newhire@example.com").first()
        self.assertIsNotNone(user, "User should be created")
        
        # User should have a usable password
        self.assertTrue(user.has_usable_password(), "User should have a usable password")
        
        # Membership should exist and be ACTIVE
        membership = Membership.objects.filter(
            user=user,
            business=self.business
        ).first()
        self.assertIsNotNone(membership, "Membership should be created")
        self.assertEqual(membership.status, "ACTIVE")
        self.assertEqual(membership.role, "AGENT")
        
        # Invite should be marked as JOINED
        invite.refresh_from_db()
        self.assertEqual(invite.status, "JOINED", "Invite should be marked JOINED")
        self.assertEqual(invite.joined_user, user, "Invite should reference the joined user")
        
        # User should be logged in (session has _auth_user_id)
        self.assertIn('_auth_user_id', self.client.session, 
            "User should be logged in after accepting invite")


class AgentDefaultLocationTestCase(TestCase):
    """Test that agents are always assigned a default location."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        
        # Create a manager user
        self.manager = User.objects.create_user(
            username="manager1",
            password="testpass123",
            email="manager@test.com"
        )
        
        # Create a business
        self.business = Business.objects.create(
            name="Test Shop",
            slug="test-shop",
            status="ACTIVE"
        )
        
        # Create manager membership
        self.manager_membership = Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )

    def test_agent_invite_with_no_locations_creates_default_location(self):
        """
        When a business has no locations and an agent accepts an invite,
        a default location is created automatically.
        """
        if not Location:
            self.skipTest("Location model not available")
        
        # Ensure business has no locations
        Location.objects.filter(business=self.business).delete()
        self.assertEqual(Location.objects.filter(business=self.business).count(), 0)
        
        # Create an invite without a location
        invite = AgentInvite.objects.create(
            business=self.business,
            invited_name="New Agent",
            email="newagent@test.com",
            status="SENT",
            expires_at=timezone.now() + timedelta(days=7),
            location=None,  # No location specified
        )
        
        # Accept the invite via POST
        invite_url = reverse('tenants:invite_accept', args=[invite.token])
        response = self.client.post(
            invite_url,
            {
                'email': 'newagent@test.com',
                'password1': 'NewPass123!',
                'password2': 'NewPass123!',
            },
            follow=True
        )
        
        # Should succeed
        self.assertEqual(response.status_code, 200, 
            f"Invite accept should succeed, got {response.status_code}")
        
        # User should be created
        user = User.objects.filter(email='newagent@test.com').first()
        self.assertIsNotNone(user, "User should be created")
        
        # A location should now exist for this business
        location = Location.objects.filter(business=self.business).first()
        self.assertIsNotNone(location, "A default location should be created")
        self.assertEqual(location.name, self.business.name, 
            "Default location should have business name")
        
        # Membership should exist with location
        membership = Membership.objects.filter(
            user=user,
            business=self.business,
            role="AGENT"
        ).first()
        self.assertIsNotNone(membership, "Membership should be created")
        self.assertIsNotNone(membership.location, "Membership must have a location")
        self.assertEqual(membership.location, location, 
            "Membership should use the default location")
        
        # Membership should pass validation (no ValidationError)
        try:
            membership.full_clean()
        except Exception as e:
            self.fail(f"Membership should be valid, got error: {e}")

    def test_agent_invite_with_existing_locations_uses_first_location(self):
        """
        When a business has existing locations, the agent is assigned
        to the first location (stable order).
        """
        if not Location:
            self.skipTest("Location model not available")
        
        # Create multiple locations
        loc1 = Location.objects.create(business=self.business, name="Store A")
        loc2 = Location.objects.create(business=self.business, name="Store B")
        loc3 = Location.objects.create(business=self.business, name="Store C")
        
        # Create an invite without a location
        invite = AgentInvite.objects.create(
            business=self.business,
            invited_name="New Agent",
            email="newagent2@test.com",
            status="SENT",
            expires_at=timezone.now() + timedelta(days=7),
            location=None,
        )
        
        # Accept the invite
        invite_url = reverse('tenants:invite_accept', args=[invite.token])
        response = self.client.post(
            invite_url,
            {
                'email': 'newagent2@test.com',
                'password1': 'NewPass123!',
                'password2': 'NewPass123!',
            },
            follow=True
        )
        
        # Should succeed
        self.assertEqual(response.status_code, 200)
        
        # User and membership should be created
        user = User.objects.filter(email='newagent2@test.com').first()
        self.assertIsNotNone(user)
        
        membership = Membership.objects.filter(
            user=user,
            business=self.business,
            role="AGENT"
        ).first()
        self.assertIsNotNone(membership)
        self.assertIsNotNone(membership.location, "Membership must have a location")
        
        # Should use the first location by ID
        first_location = Location.objects.filter(business=self.business).order_by("id").first()
        self.assertEqual(membership.location, first_location,
            "Should use the first location when no location specified")

    def test_agent_invite_with_matching_location_name_uses_that_location(self):
        """
        When a location exists with the same name as the business (case-insensitive),
        that location is preferred as the default.
        """
        if not Location:
            self.skipTest("Location model not available")
        
        # Create locations, one matching the business name
        loc1 = Location.objects.create(business=self.business, name="Store A")
        loc_matching = Location.objects.create(business=self.business, name="Test Shop")  # Matches business.name
        loc3 = Location.objects.create(business=self.business, name="Store C")
        
        # Create an invite without a location
        invite = AgentInvite.objects.create(
            business=self.business,
            invited_name="New Agent",
            email="newagent3@test.com",
            status="SENT",
            expires_at=timezone.now() + timedelta(days=7),
            location=None,
        )
        
        # Accept the invite
        invite_url = reverse('tenants:invite_accept', args=[invite.token])
        response = self.client.post(
            invite_url,
            {
                'email': 'newagent3@test.com',
                'password1': 'NewPass123!',
                'password2': 'NewPass123!',
            },
            follow=True
        )
        
        # Should succeed
        self.assertEqual(response.status_code, 200)
        
        # User and membership should be created
        user = User.objects.filter(email='newagent3@test.com').first()
        self.assertIsNotNone(user)
        
        membership = Membership.objects.filter(
            user=user,
            business=self.business,
            role="AGENT"
        ).first()
        self.assertIsNotNone(membership)
        self.assertIsNotNone(membership.location, "Membership must have a location")
        
        # Should use the location with matching name
        self.assertEqual(membership.location, loc_matching,
            "Should use location with name matching business name")

    def test_get_default_location_for_business_helper(self):
        """Test the get_default_location_for_business helper function directly."""
        if not Location:
            self.skipTest("Location model not available")
        
        from tenants.services.invites import get_default_location_for_business
        
        # Test 1: No locations exist -> creates one
        Location.objects.filter(business=self.business).delete()
        location = get_default_location_for_business(self.business)
        self.assertIsNotNone(location, "Should return a location")
        self.assertEqual(location.business, self.business)
        self.assertEqual(location.name, self.business.name)
        
        # Test 2: Calling again returns the same location (idempotent)
        location2 = get_default_location_for_business(self.business)
        self.assertEqual(location, location2, "Should return the same location")
        
        # Test 3: Multiple locations exist -> returns matching name
        Location.objects.filter(business=self.business).delete()
        loc1 = Location.objects.create(business=self.business, name="Store A")
        loc2 = Location.objects.create(business=self.business, name=self.business.name)
        loc3 = Location.objects.create(business=self.business, name="Store C")
        
        location3 = get_default_location_for_business(self.business)
        self.assertEqual(location3, loc2, "Should return location with matching name")
        
        # Test 4: No matching name -> returns first location
        Location.objects.filter(business=self.business).delete()
        loc_a = Location.objects.create(business=self.business, name="Alpha")
        loc_b = Location.objects.create(business=self.business, name="Beta")
        
        location4 = get_default_location_for_business(self.business)
        self.assertEqual(location4, loc_a, "Should return first location when no name match")

    def test_membership_validation_passes_with_location(self):
        """
        Ensure that AGENT memberships with a location pass validation.
        This confirms we're not triggering the ValidationError anymore.
        """
        if not Location:
            self.skipTest("Location model not available")
        
        # Create a location
        location = Location.objects.create(business=self.business, name="Main Store")
        
        # Create an agent user
        agent = User.objects.create_user(
            username="agent_test",
            password="testpass123",
            email="agent_test@test.com"
        )
        
        # Create membership with location
        membership = Membership(
            user=agent,
            business=self.business,
            role="AGENT",
            status="ACTIVE",
            location=location
        )
        
        # Should not raise ValidationError
        try:
            membership.full_clean()
            membership.save()
        except Exception as e:
            self.fail(f"Membership with location should be valid, got error: {e}")
        
        # Confirm it was saved
        self.assertIsNotNone(membership.pk)
        self.assertEqual(membership.location, location)

    def test_membership_validation_fails_without_location(self):
        """
        Ensure that AGENT memberships WITHOUT a location fail validation.
        This confirms the validation rule is still enforced.
        """
        if not Location:
            self.skipTest("Location model not available")
        
        # Create an agent user
        agent = User.objects.create_user(
            username="agent_test2",
            password="testpass123",
            email="agent_test2@test.com"
        )
        
        # Create membership without location
        membership = Membership(
            user=agent,
            business=self.business,
            role="AGENT",
            status="ACTIVE",
            location=None  # Missing location
        )
        
        # Should raise ValidationError
        with self.assertRaises(ValidationError) as cm:
            membership.full_clean()
        
        # Check that the error is about location
        self.assertIn('location', cm.exception.message_dict,
            "ValidationError should mention location field")
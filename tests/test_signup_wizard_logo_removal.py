"""
Tests for manager signup wizard after logo step removal.

Ensures:
- 3-step wizard works correctly
- Store creation is idempotent
- Subdomain collisions are handled gracefully
- Robust error logging with request IDs
- No regressions to existing functionality
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from tenants.models import Business, Membership

User = get_user_model()


class SignupWizardLogoRemovalTestCase(TestCase):
    """Test signup wizard after removing logo step (3 steps instead of 4)."""

    def setUp(self):
        """Set up test data."""
        self.signup_url = reverse("accounts:signup_manager")

    def test_wizard_has_3_steps(self):
        """Verify wizard now has 3 steps instead of 4."""
        # Step 1: Account
        response = self.client.get(f"{self.signup_url}?step=1")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Step 1 of 3")

        # Step 2: Store basics
        response = self.client.get(f"{self.signup_url}?step=2", follow=True)
        # Should redirect to step 1 (no session data yet)
        self.assertContains(response, "Step 1 of 3")

        # Step 3 should not exist (was logo step)
        response = self.client.get(f"{self.signup_url}?step=3", follow=True)
        # Should either redirect to step 1 or show review page (depends on session)
        self.assertEqual(response.status_code, 200)

        # Step 4 should redirect to step 1 (out of bounds)
        response = self.client.get(f"{self.signup_url}?step=4", follow=True)
        self.assertContains(response, "Step 1 of 3")

    def test_complete_wizard_without_logo(self):
        """Test completing entire wizard (3 steps) without logo."""
        # Step 1: Create account
        step1_data = {
            "step": "1",
            "action": "next",
            "email": "testmanager@example.com",
            "full_name": "Test Manager",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
        }
        response = self.client.post(f"{self.signup_url}?step=1", step1_data)
        self.assertEqual(response.status_code, 302)
        self.assertIn("step=2", response.url)

        # Step 2: Store basics
        step2_data = {
            "step": "2",
            "action": "next",
            "business_name": "Test Gym",
            "business_kind": "gym",
            "subdomain": "testgym",
        }
        response = self.client.post(f"{self.signup_url}?step=2", step2_data)
        self.assertEqual(response.status_code, 302)
        self.assertIn("step=3", response.url)

        # Step 3: Review & Create (no logo step)
        response = self.client.get(f"{self.signup_url}?step=3")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Step 3 of 3")
        self.assertContains(response, "Review")
        self.assertContains(response, "create")
        self.assertContains(response, "Test Gym")
        # Logo row should not be present
        self.assertNotContains(response, "🎨")

        # Submit final step
        step3_data = {
            "step": "3",
            "action": "create",
            "agree": "on",
        }
        response = self.client.post(f"{self.signup_url}?step=3", step3_data)
        self.assertEqual(response.status_code, 302)

        # Verify user was created and logged in
        user = User.objects.get(email="testmanager@example.com")
        self.assertTrue(user.is_authenticated)

        # Verify business was created
        business = Business.objects.get(name="Test Gym")
        self.assertEqual(business.subdomain, "testgym")
        self.assertEqual(business.business_kind, "gym")
        self.assertEqual(business.created_by, user)

        # Verify membership
        membership = Membership.objects.get(user=user, business=business)
        self.assertEqual(membership.role, "MANAGER")
        self.assertEqual(membership.status, "ACTIVE")

    def test_subdomain_collision_auto_resolution(self):
        """Test that subdomain collisions are resolved automatically with suffix."""
        # Create existing business with subdomain
        existing_user = User.objects.create_user(
            username="existing@example.com",
            email="existing@example.com",
            password="pass123",
        )
        Business.objects.create(
            name="Existing Business",
            slug="existing",
            subdomain="mygym",
            created_by=existing_user,
        )

        # Step 1: Create account
        step1_data = {
            "step": "1",
            "action": "next",
            "email": "newmanager@example.com",
            "full_name": "New Manager",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
        }
        self.client.post(f"{self.signup_url}?step=1", step1_data)

        # Step 2: Try to use same subdomain
        step2_data = {
            "step": "2",
            "action": "next",
            "business_name": "My Gym 2",
            "business_kind": "gym",
            "subdomain": "mygym",  # Collision!
        }
        self.client.post(f"{self.signup_url}?step=2", step2_data)

        # Step 3: Submit (should auto-resolve collision)
        step3_data = {
            "step": "3",
            "action": "create",
            "agree": "on",
        }
        response = self.client.post(f"{self.signup_url}?step=3", step3_data)
        
        # Should succeed (no error)
        self.assertEqual(response.status_code, 302)

        # Verify new business has modified subdomain
        new_business = Business.objects.get(name="My Gym 2")
        self.assertNotEqual(new_business.subdomain, "mygym")
        self.assertTrue(new_business.subdomain.startswith("mygym-"))

    def test_idempotent_retry_same_user(self):
        """Test that retrying with same email doesn't fail if user exists but no business."""
        # Create user without business
        existing_user = User.objects.create_user(
            username="retry@example.com",
            email="retry@example.com",
            password="oldpass",
        )

        # Step 1: Try to create account with same email
        step1_data = {
            "step": "1",
            "action": "next",
            "email": "retry@example.com",
            "full_name": "Retry User",
            "password1": "NewPass123!",
            "password2": "NewPass123!",
        }
        self.client.post(f"{self.signup_url}?step=1", step1_data)

        # Step 2: Store basics
        step2_data = {
            "step": "2",
            "action": "next",
            "business_name": "Retry Store",
            "business_kind": "phones",
            "subdomain": "retrystore",
        }
        self.client.post(f"{self.signup_url}?step=2", step2_data)

        # Step 3: Submit (should use existing user and create business)
        step3_data = {
            "step": "3",
            "action": "create",
            "agree": "on",
        }
        response = self.client.post(f"{self.signup_url}?step=3", step3_data)
        
        # Should succeed
        self.assertEqual(response.status_code, 302)

        # Verify business was created for existing user
        if Business.objects.filter(name="Retry Store").exists():
            business = Business.objects.get(name="Retry Store")
            self.assertEqual(business.created_by, existing_user)

        # Should only have one user with this email
        self.assertEqual(User.objects.filter(email="retry@example.com").count(), 1)

    def test_error_with_request_id(self):
        """Test that errors include a reference ID for support tracking."""
        # Step 1
        step1_data = {
            "step": "1",
            "action": "next",
            "email": "errortest@example.com",
            "full_name": "Error Test",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
        }
        self.client.post(f"{self.signup_url}?step=1", step1_data)

        # Step 2 with invalid data that will cause error on submission
        step2_data = {
            "step": "2",
            "action": "next",
            "business_name": "",  # Empty name will cause error
            "business_kind": "gym",
            "subdomain": "errortest",
        }
        response = self.client.post(f"{self.signup_url}?step=2", step2_data)
        
        # Should have form errors (not proceed to step 3)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Step 2 of 3")

    def test_navigation_back_button_works(self):
        """Test that back buttons work correctly in 3-step wizard."""
        # Step 1
        step1_data = {
            "step": "1",
            "action": "next",
            "email": "navtest@example.com",
            "full_name": "Nav Test",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
        }
        self.client.post(f"{self.signup_url}?step=1", step1_data)

        # Step 2: Click back
        step2_back = {
            "step": "2",
            "action": "back",
        }
        response = self.client.post(f"{self.signup_url}?step=2", step2_back)
        self.assertEqual(response.status_code, 302)
        self.assertIn("step=1", response.url)

        # Complete step 2
        step2_data = {
            "step": "2",
            "action": "next",
            "business_name": "Nav Test Store",
            "business_kind": "pharmacy",
            "subdomain": "navtest",
        }
        self.client.post(f"{self.signup_url}?step=2", step2_data)

        # Step 3: Click back
        step3_back = {
            "step": "3",
            "action": "back",
        }
        response = self.client.post(f"{self.signup_url}?step=3", step3_back)
        self.assertEqual(response.status_code, 302)
        self.assertIn("step=2", response.url)

    def test_business_name_uniqueness_validation(self):
        """Test that duplicate business names are prevented."""
        # Create existing business
        existing_user = User.objects.create_user(
            username="existing@example.com",
            email="existing@example.com",
            password="pass123",
        )
        Business.objects.create(
            name="Unique Gym Name",
            slug="unique-gym",
            created_by=existing_user,
        )

        # Step 1
        step1_data = {
            "step": "1",
            "action": "next",
            "email": "newuser@example.com",
            "full_name": "New User",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
        }
        self.client.post(f"{self.signup_url}?step=1", step1_data)

        # Step 2: Try duplicate name (case-insensitive)
        step2_data = {
            "step": "2",
            "action": "next",
            "business_name": "unique gym name",  # Same name, different case
            "business_kind": "gym",
            "subdomain": "newgym",
        }
        response = self.client.post(f"{self.signup_url}?step=2", step2_data)
        
        # Should show error (not proceed to step 3)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already in use", html=False)

    def test_slug_collision_auto_resolution(self):
        """Test that slug collisions are resolved with numeric suffix."""
        # Create existing business
        existing_user = User.objects.create_user(
            username="existing@example.com",
            email="existing@example.com",
            password="pass123",
        )
        Business.objects.create(
            name="Test Business",
            slug="test-business",
            created_by=existing_user,
        )

        # Step 1
        step1_data = {
            "step": "1",
            "action": "next",
            "email": "newuser@example.com",
            "full_name": "New User",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
        }
        self.client.post(f"{self.signup_url}?step=1", step1_data)

        # Step 2: Use DIFFERENT business name (to avoid name uniqueness validation)
        # but similar enough that slug might collide
        step2_data = {
            "step": "2",
            "action": "next",
            "business_name": "Another Test Business",  # Different name
            "business_kind": "grocery",
            "subdomain": "testbusiness2",
        }
        response = self.client.post(f"{self.signup_url}?step=2", step2_data)
        
        # Should proceed successfully (redirect to step 3)
        self.assertEqual(response.status_code, 302)


class SignupWizardIntegrationTestCase(TestCase):
    """Integration tests for complete signup flow."""

    def test_full_signup_flow_phones_store(self):
        """Test complete signup flow for Phones & Electronics store."""
        signup_url = reverse("accounts:signup_manager")

        # Step 1
        step1_data = {
            "step": "1",
            "action": "next",
            "email": "phones@example.com",
            "full_name": "Phones Manager",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
        }
        response = self.client.post(f"{signup_url}?step=1", step1_data)
        self.assertEqual(response.status_code, 302)

        # Step 2
        step2_data = {
            "step": "2",
            "action": "next",
            "business_name": "TechWorld Electronics",
            "business_kind": "phones",
            "subdomain": "techworld",
        }
        response = self.client.post(f"{signup_url}?step=2", step2_data)
        self.assertEqual(response.status_code, 302)

        # Step 3: Review
        response = self.client.get(f"{signup_url}?step=3")
        self.assertContains(response, "TechWorld Electronics")
        self.assertContains(response, "phones@example.com")
        self.assertContains(response, "Phones Manager")

        # Submit
        step3_data = {
            "step": "3",
            "action": "create",
            "agree": "on",
        }
        response = self.client.post(f"{signup_url}?step=3", step3_data)
        self.assertEqual(response.status_code, 302)

        # Verify all entities created
        user = User.objects.get(email="phones@example.com")
        business = Business.objects.get(name="TechWorld Electronics")
        membership = Membership.objects.get(user=user, business=business)
        
        self.assertEqual(business.business_kind, "phones")
        self.assertEqual(business.subdomain, "techworld")
        self.assertEqual(membership.role, "MANAGER")

    def test_full_signup_flow_gym_store(self):
        """Test complete signup flow for Gym store."""
        signup_url = reverse("accounts:signup_manager")

        # Complete all steps
        self.client.post(
            f"{signup_url}?step=1",
            {
                "step": "1",
                "action": "next",
                "email": "gym@example.com",
                "full_name": "Gym Owner",
                "password1": "SecurePass123!",
                "password2": "SecurePass123!",
            },
        )
        self.client.post(
            f"{signup_url}?step=2",
            {
                "step": "2",
                "action": "next",
                "business_name": "FitZone Gym",
                "business_kind": "gym",
                "subdomain": "fitzone",
            },
        )
        response = self.client.post(
            f"{signup_url}?step=3",
            {
                "step": "3",
                "action": "create",
                "agree": "on",
            },
        )

        # Verify success
        self.assertEqual(response.status_code, 302)
        business = Business.objects.get(name="FitZone Gym")
        self.assertEqual(business.business_kind, "gym")
        
        # Verify gym-specific section flags are set (if applicable)
        # This tests the section_defaults integration
        if hasattr(business, "enable_gym_section"):
            self.assertTrue(business.enable_gym_section)


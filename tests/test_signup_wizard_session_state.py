"""
Tests for manager signup wizard session state persistence.

Ensures that after fixing the step=4/step=3 mismatch, the wizard:
1. Properly persists data across steps in session
2. Pre-fills forms when navigating back
3. Successfully creates store on final submit (step 3)
4. Handles step=4 backward compatibility
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from tenants.models import Business, Membership

User = get_user_model()


class SignupWizardSessionStateTestCase(TestCase):
    """Test signup wizard session state persistence after step routing fix."""

    def setUp(self):
        """Set up test data."""
        self.signup_url = reverse("accounts:signup_manager")

    def test_step1_data_persists_in_session(self):
        """Test that step 1 data is saved to session and can be retrieved."""
        # Submit step 1
        step1_data = {
            "step": "1",
            "action": "next",
            "email": "persist@example.com",
            "full_name": "Persist Test",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
        }
        response = self.client.post(f"{self.signup_url}?step=1", step1_data)
        self.assertEqual(response.status_code, 302)
        self.assertIn("step=2", response.url)

        # Check session has step1 data
        session = self.client.session
        wizard_key = "manager_wizard_data"
        self.assertIn(wizard_key, session)
        self.assertIn("step1", session[wizard_key])
        self.assertEqual(session[wizard_key]["step1"]["email"], "persist@example.com")
        self.assertEqual(session[wizard_key]["step1"]["full_name"], "Persist Test")

    def test_back_navigation_preserves_step1_inputs(self):
        """Test that navigating back to step 1 shows pre-filled values from session."""
        # Submit step 1
        step1_data = {
            "step": "1",
            "action": "next",
            "email": "backtest@example.com",
            "full_name": "Back Test User",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
        }
        self.client.post(f"{self.signup_url}?step=1", step1_data)

        # Now at step 2, go back to step 1 (GET)
        response = self.client.get(f"{self.signup_url}?step=1")
        self.assertEqual(response.status_code, 200)
        
        # Check that form initial values are present in context
        # (Forms will be pre-filled with initial= data)
        self.assertIn("form", response.context)
        form = response.context["form"]
        self.assertEqual(form.initial.get("email"), "backtest@example.com")
        self.assertEqual(form.initial.get("full_name"), "Back Test User")

    def test_step2_data_persists_and_back_works(self):
        """Test step 2 data persists and back navigation preserves step 2 inputs."""
        # Submit step 1
        step1_data = {
            "step": "1",
            "action": "next",
            "email": "step2test@example.com",
            "full_name": "Step2 Test",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
        }
        self.client.post(f"{self.signup_url}?step=1", step1_data)

        # Submit step 2
        step2_data = {
            "step": "2",
            "action": "next",
            "business_name": "Test Store Two",
            "business_kind": "phones",
            "subdomain": "teststoretwo",
        }
        response = self.client.post(f"{self.signup_url}?step=2", step2_data)
        self.assertEqual(response.status_code, 302)
        self.assertIn("step=3", response.url)

        # Navigate back to step 2 (GET)
        response = self.client.get(f"{self.signup_url}?step=2")
        self.assertEqual(response.status_code, 200)
        
        # Form should be pre-filled
        form = response.context["form"]
        self.assertEqual(form.initial.get("business_name"), "Test Store Two")
        self.assertEqual(form.initial.get("business_kind"), "phones")
        self.assertEqual(form.initial.get("subdomain"), "teststoretwo")

    def test_final_submit_step3_creates_store(self):
        """Test that final submit on step 3 (NOT step 4) creates the store successfully."""
        # Submit step 1
        step1_data = {
            "step": "1",
            "action": "next",
            "email": "finaltest@example.com",
            "full_name": "Final Test",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
        }
        self.client.post(f"{self.signup_url}?step=1", step1_data)

        # Submit step 2
        step2_data = {
            "step": "2",
            "action": "next",
            "business_name": "Final Test Store",
            "business_kind": "gym",
            "subdomain": "finaltest",
        }
        self.client.post(f"{self.signup_url}?step=2", step2_data)

        # Submit step 3 (final)
        step3_data = {
            "step": "3",
            "action": "create",
            "agree": "on",
        }
        response = self.client.post(f"{self.signup_url}?step=3", step3_data)
        
        # Should redirect on success
        self.assertEqual(response.status_code, 302)

        # Verify user was created
        user = User.objects.get(email="finaltest@example.com")
        self.assertTrue(user.is_authenticated)

        # Verify business was created
        business = Business.objects.get(name="Final Test Store")
        self.assertEqual(business.subdomain, "finaltest")
        self.assertEqual(business.business_kind, "gym")

        # Verify membership
        membership = Membership.objects.get(user=user, business=business)
        self.assertEqual(membership.role, "MANAGER")

    def test_step4_backward_compat_redirects_to_step3(self):
        """Test that accessing step=4 redirects to step=3 for backward compatibility."""
        # Submit steps 1 and 2
        step1_data = {
            "step": "1",
            "action": "next",
            "email": "compat@example.com",
            "full_name": "Compat Test",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
        }
        self.client.post(f"{self.signup_url}?step=1", step1_data)

        step2_data = {
            "step": "2",
            "action": "next",
            "business_name": "Compat Store",
            "business_kind": "liquor",
            "subdomain": "compatstore",
        }
        self.client.post(f"{self.signup_url}?step=2", step2_data)

        # Try to access step=4 (old step)
        response = self.client.get(f"{self.signup_url}?step=4")
        
        # Should redirect to step=3
        self.assertEqual(response.status_code, 302)
        self.assertIn("step=3", response.url)

    def test_step4_post_redirects_to_step3(self):
        """Test that POST to step=4 also redirects to step=3."""
        # Submit steps 1 and 2
        step1_data = {
            "step": "1",
            "action": "next",
            "email": "postcompat@example.com",
            "full_name": "Post Compat",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
        }
        self.client.post(f"{self.signup_url}?step=1", step1_data)

        step2_data = {
            "step": "2",
            "action": "next",
            "business_name": "Post Compat Store",
            "business_kind": "clothing",
            "subdomain": "postcompat",
        }
        self.client.post(f"{self.signup_url}?step=2", step2_data)

        # Try to POST to step=4 (e.g., from old cached template)
        step4_data = {
            "step": "4",  # Old step number
            "action": "create",
            "agree": "on",
        }
        response = self.client.post(f"{self.signup_url}?step=4", step4_data)
        
        # Should redirect to step=3
        self.assertEqual(response.status_code, 302)
        self.assertIn("step=3", response.url)

    def test_session_cleared_on_success(self):
        """Test that wizard session data is cleared after successful completion."""
        # Complete full wizard
        step1_data = {
            "step": "1",
            "action": "next",
            "email": "cleartest@example.com",
            "full_name": "Clear Test",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
        }
        self.client.post(f"{self.signup_url}?step=1", step1_data)

        step2_data = {
            "step": "2",
            "action": "next",
            "business_name": "Clear Test Store",
            "business_kind": "cement",
            "subdomain": "cleartest",
        }
        self.client.post(f"{self.signup_url}?step=2", step2_data)

        step3_data = {
            "step": "3",
            "action": "create",
            "agree": "on",
        }
        self.client.post(f"{self.signup_url}?step=3", step3_data)

        # Check that wizard data is cleared from session
        session = self.client.session
        wizard_key = "manager_wizard_data"
        self.assertNotIn(wizard_key, session)

    def test_validation_error_preserves_form_data(self):
        """Test that validation errors don't wipe previously entered data."""
        # Submit step 1
        step1_data = {
            "step": "1",
            "action": "next",
            "email": "valtest@example.com",
            "full_name": "Val Test",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
        }
        self.client.post(f"{self.signup_url}?step=1", step1_data)

        # Submit step 2 with missing required field
        step2_data = {
            "step": "2",
            "action": "next",
            "business_name": "",  # Missing - will cause validation error
            "business_kind": "grocery",
            "subdomain": "valtest",
        }
        response = self.client.post(f"{self.signup_url}?step=2", step2_data)
        
        # Should stay on step 2 with error
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Step 2 of 3")
        
        # Form should still have the valid fields (business_kind, subdomain)
        form = response.context["form"]
        # Django forms preserve POST data when invalid
        self.assertEqual(form.data.get("business_kind"), "grocery")
        self.assertEqual(form.data.get("subdomain"), "valtest")

    def test_back_from_step3_to_step2_preserves_data(self):
        """Test clicking back from step 3 review page goes to step 2 with data intact."""
        # Submit steps 1 and 2
        step1_data = {
            "step": "1",
            "action": "next",
            "email": "backstep3@example.com",
            "full_name": "Back Step3 Test",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
        }
        self.client.post(f"{self.signup_url}?step=1", step1_data)

        step2_data = {
            "step": "2",
            "action": "next",
            "business_name": "Back Step3 Store",
            "business_kind": "pharmacy",
            "subdomain": "backstep3",
        }
        self.client.post(f"{self.signup_url}?step=2", step2_data)

        # Now at step 3, click back
        step3_back = {
            "step": "3",
            "action": "back",
        }
        response = self.client.post(f"{self.signup_url}?step=3", step3_back)
        
        # Should redirect to step 2
        self.assertEqual(response.status_code, 302)
        self.assertIn("step=2", response.url)

        # Get step 2 and verify data is still there
        response = self.client.get(f"{self.signup_url}?step=2")
        form = response.context["form"]
        self.assertEqual(form.initial.get("business_name"), "Back Step3 Store")
        self.assertEqual(form.initial.get("business_kind"), "pharmacy")
        self.assertEqual(form.initial.get("subdomain"), "backstep3")

    def test_multiple_back_forth_navigation(self):
        """Test going back and forth multiple times preserves all data."""
        # Step 1
        step1_data = {
            "step": "1",
            "action": "next",
            "email": "multistep@example.com",
            "full_name": "Multi Step Test",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
        }
        self.client.post(f"{self.signup_url}?step=1", step1_data)

        # Step 2
        step2_data = {
            "step": "2",
            "action": "next",
            "business_name": "Multi Step Store",
            "business_kind": "phones",
            "subdomain": "multistep",
        }
        self.client.post(f"{self.signup_url}?step=2", step2_data)

        # Go to step 3, then back to step 2
        self.client.get(f"{self.signup_url}?step=3")
        response = self.client.get(f"{self.signup_url}?step=2")
        form = response.context["form"]
        self.assertEqual(form.initial.get("business_name"), "Multi Step Store")

        # Go back to step 1
        response = self.client.get(f"{self.signup_url}?step=1")
        form = response.context["form"]
        self.assertEqual(form.initial.get("email"), "multistep@example.com")

        # Go forward to step 2 again
        response = self.client.get(f"{self.signup_url}?step=2")
        form = response.context["form"]
        self.assertEqual(form.initial.get("business_name"), "Multi Step Store")

        # Go forward to step 3 and complete
        step3_data = {
            "step": "3",
            "action": "create",
            "agree": "on",
        }
        response = self.client.post(f"{self.signup_url}?step=3", step3_data)
        self.assertEqual(response.status_code, 302)

        # Verify everything was created correctly
        user = User.objects.get(email="multistep@example.com")
        business = Business.objects.get(name="Multi Step Store")
        self.assertEqual(business.created_by, user)


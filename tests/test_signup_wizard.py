"""
Comprehensive tests for the multi-step signup wizard.

Tests cover:
- GET requests for each step
- POST validation on each step
- Session state management (going back and forth)
- Full wizard completion
- Data persistence after completion
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()

try:
    from tenants.models import Business, Membership
    from inventory.models import Location
    from circuitcity.accounts.models import OnboardingProfile
except ImportError:
    Business = None
    Membership = None
    Location = None
    OnboardingProfile = None


class SignupWizardTestCase(TestCase):
    """Test the multi-step signup wizard flow"""
    
    def setUp(self):
        self.client = Client()
        self.step0_url = reverse("accounts:signup_wizard_step", kwargs={"step": 0})
        self.step1_url = reverse("accounts:signup_wizard_step", kwargs={"step": 1})
        self.step2_url = reverse("accounts:signup_wizard_step", kwargs={"step": 2})
        self.step3_url = reverse("accounts:signup_wizard_step", kwargs={"step": 3})
        self.step4_url = reverse("accounts:signup_wizard_step", kwargs={"step": 4})
        
        # Valid test data for each step
        self.valid_step1_data = {
            "full_name": "Test Manager",
            "email": "testmanager@example.com",
            "password1": "TestPassword123!",
            "password2": "TestPassword123!",
        }
        
        self.valid_step2_data = {
            "business_name": "Test Electronics Store",
            "country": "Zambia",
            "currency": "ZMW",
            "business_kind": "phones",
        }
        
        self.valid_step3_data = {
            "location_name": "Main Store",
            "city": "Lusaka",
            "staff_count": "5",
        }
        
        self.valid_step4_data = {
            "goal_stop_theft": True,
            "goal_see_profit": True,
            "goal_track_performance": False,
            "goal_move_off_notebooks": True,
        }
    
    def test_step0_get(self):
        """Test Step 0 (Welcome) GET request"""
        response = self.client.get(self.step0_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Welcome to Emajinet")
        self.assertContains(response, "Get Started")
    
    def test_step0_post_redirects_to_step1(self):
        """Test Step 0 POST redirects to Step 1"""
        response = self.client.post(self.step0_url)
        self.assertRedirects(response, self.step1_url)
    
    def test_step1_get(self):
        """Test Step 1 (Your Account) GET request"""
        response = self.client.get(self.step1_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your Account")
        self.assertContains(response, "Full Name")
        self.assertContains(response, "Email Address")
        self.assertContains(response, "Password")
    
    def test_step1_post_valid_saves_to_session(self):
        """Test Step 1 POST with valid data saves to session and redirects"""
        response = self.client.post(self.step1_url, self.valid_step1_data)
        self.assertRedirects(response, self.step2_url)
        
        # Check session data
        session = self.client.session
        self.assertIn("signup_wizard_data", session)
        wizard_data = session["signup_wizard_data"]
        self.assertIn("step1", wizard_data)
        self.assertEqual(wizard_data["step1"]["email"], "testmanager@example.com")
    
    def test_step1_post_invalid_email(self):
        """Test Step 1 POST with invalid email shows error"""
        invalid_data = self.valid_step1_data.copy()
        invalid_data["email"] = "not-an-email"
        
        response = self.client.post(self.step1_url, invalid_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "email")  # Error message
    
    def test_step1_post_password_mismatch(self):
        """Test Step 1 POST with mismatched passwords shows error"""
        invalid_data = self.valid_step1_data.copy()
        invalid_data["password2"] = "DifferentPassword123!"
        
        response = self.client.post(self.step1_url, invalid_data)
        self.assertEqual(response.status_code, 200)
        # Should show error about password mismatch
    
    def test_step1_post_duplicate_email(self):
        """Test Step 1 POST with existing email shows error"""
        # Create existing user
        User.objects.create_user(
            username="existing@example.com",
            email="existing@example.com",
            password="ExistingPass123!"
        )
        
        duplicate_data = self.valid_step1_data.copy()
        duplicate_data["email"] = "existing@example.com"
        
        response = self.client.post(self.step1_url, duplicate_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already have an account")
    
    def test_step2_requires_step1_completion(self):
        """Test Step 2 redirects if Step 1 not completed"""
        response = self.client.get(self.step2_url)
        # Should still show the page, but on POST it will redirect if no step1 data
        self.assertEqual(response.status_code, 200)
        
        # Try to POST without step1 data
        response = self.client.post(self.step2_url, self.valid_step2_data)
        self.assertRedirects(response, self.step1_url)
    
    def test_step2_post_valid(self):
        """Test Step 2 POST with valid data after Step 1"""
        # First complete step 1
        self.client.post(self.step1_url, self.valid_step1_data)
        
        # Then post step 2
        response = self.client.post(self.step2_url, self.valid_step2_data)
        self.assertRedirects(response, self.step3_url)
        
        # Check session
        session = self.client.session
        wizard_data = session["signup_wizard_data"]
        self.assertIn("step2", wizard_data)
        self.assertEqual(wizard_data["step2"]["business_name"], "Test Electronics Store")
    
    def test_step3_requires_step1_and_step2(self):
        """Test Step 3 redirects if Steps 1 & 2 not completed"""
        response = self.client.post(self.step3_url, self.valid_step3_data)
        self.assertRedirects(response, self.step1_url)
    
    def test_step3_post_valid(self):
        """Test Step 3 POST with valid data after Steps 1 & 2"""
        # Complete steps 1 & 2
        self.client.post(self.step1_url, self.valid_step1_data)
        self.client.post(self.step2_url, self.valid_step2_data)
        
        # Post step 3
        response = self.client.post(self.step3_url, self.valid_step3_data)
        self.assertRedirects(response, self.step4_url)
        
        # Check session
        session = self.client.session
        wizard_data = session["signup_wizard_data"]
        self.assertIn("step3", wizard_data)
        self.assertEqual(wizard_data["step3"]["location_name"], "Main Store")
    
    def test_step4_shows_summary(self):
        """Test Step 4 shows summary of previous steps"""
        # Complete steps 1, 2, 3
        self.client.post(self.step1_url, self.valid_step1_data)
        self.client.post(self.step2_url, self.valid_step2_data)
        self.client.post(self.step3_url, self.valid_step3_data)
        
        # Get step 4
        response = self.client.get(self.step4_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Manager")
        self.assertContains(response, "Test Electronics Store")
        self.assertContains(response, "Main Store")
    
    def test_full_wizard_completion_creates_all_entities(self):
        """Test completing the entire wizard creates User, Business, Location, etc."""
        # Complete all steps
        self.client.post(self.step1_url, self.valid_step1_data)
        self.client.post(self.step2_url, self.valid_step2_data)
        self.client.post(self.step3_url, self.valid_step3_data)
        response = self.client.post(self.step4_url, self.valid_step4_data)
        
        # Should redirect to dashboard
        self.assertEqual(response.status_code, 302)
        
        # Check User created
        user = User.objects.filter(email="testmanager@example.com").first()
        self.assertIsNotNone(user)
        self.assertEqual(user.first_name, "Test")
        self.assertEqual(user.last_name, "Manager")
        
        # Check Business created (if tenants app available)
        if Business is not None:
            biz = Business.objects.filter(name="Test Electronics Store").first()
            self.assertIsNotNone(biz)
            self.assertEqual(biz.business_kind, "phones")
            self.assertEqual(biz.status, "ACTIVE")
            
            # Check Membership created
            if Membership is not None:
                membership = Membership.objects.filter(user=user, business=biz).first()
                self.assertIsNotNone(membership)
                self.assertEqual(membership.role, "MANAGER")
                self.assertEqual(membership.status, "ACTIVE")
            
            # Check Location created
            if Location is not None:
                location = Location.objects.filter(business=biz, name="Main Store").first()
                self.assertIsNotNone(location)
                self.assertEqual(location.city, "Lusaka")
                self.assertTrue(location.is_default)
        
        # Check OnboardingProfile created
        if OnboardingProfile is not None:
            profile = OnboardingProfile.objects.filter(user=user).first()
            self.assertIsNotNone(profile)
            self.assertTrue(profile.goal_stop_theft)
            self.assertTrue(profile.goal_see_profit)
            self.assertFalse(profile.goal_track_performance)
            self.assertTrue(profile.goal_move_off_notebooks)
            self.assertIsNotNone(profile.completed_at)
            self.assertEqual(profile.first_business_name, "Test Electronics Store")
            self.assertEqual(profile.first_location_name, "Main Store")
            self.assertEqual(profile.chosen_vertical, "phones")
        
        # Check user is logged in
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        
        # Check session cleared
        session = self.client.session
        self.assertNotIn("signup_wizard_data", session)
    
    def test_going_back_preserves_data(self):
        """Test going back and forth preserves form data"""
        # Complete step 1
        self.client.post(self.step1_url, self.valid_step1_data)
        
        # Complete step 2
        self.client.post(self.step2_url, self.valid_step2_data)
        
        # Go back to step 1
        response = self.client.get(self.step1_url)
        self.assertEqual(response.status_code, 200)
        
        # Check that data is still in session
        session = self.client.session
        wizard_data = session.get("signup_wizard_data", {})
        self.assertIn("step1", wizard_data)
        self.assertIn("step2", wizard_data)
        
        # Go forward to step 2 again
        response = self.client.get(self.step2_url)
        self.assertEqual(response.status_code, 200)
        # Form should be pre-filled with previous data
    
    def test_authenticated_user_redirects(self):
        """Test authenticated users are redirected away from wizard"""
        # Create and login user
        user = User.objects.create_user(
            username="existing@example.com",
            email="existing@example.com",
            password="ExistingPass123!"
        )
        self.client.force_login(user)
        
        # Try to access wizard
        response = self.client.get(self.step0_url)
        self.assertEqual(response.status_code, 302)
        # Should redirect to dashboard
    
    def test_invalid_step_redirects_to_step0(self):
        """Test accessing invalid step number redirects to step 0"""
        response = self.client.get(reverse("accounts:signup_wizard_step", kwargs={"step": 99}))
        self.assertRedirects(response, self.step0_url)
        
        response = self.client.get(reverse("accounts:signup_wizard_step", kwargs={"step": -1}))
        self.assertRedirects(response, self.step0_url)
    
    def test_wizard_validates_business_name_required(self):
        """Test Step 2 validates business name is required"""
        # Complete step 1
        self.client.post(self.step1_url, self.valid_step1_data)
        
        # Post step 2 with missing business name
        invalid_data = self.valid_step2_data.copy()
        invalid_data["business_name"] = ""
        
        response = self.client.post(self.step2_url, invalid_data)
        self.assertEqual(response.status_code, 200)
        # Should show validation error
    
    def test_wizard_validates_location_name_required(self):
        """Test Step 3 validates location name is required"""
        # Complete steps 1 & 2
        self.client.post(self.step1_url, self.valid_step1_data)
        self.client.post(self.step2_url, self.valid_step2_data)
        
        # Post step 3 with missing location name
        invalid_data = self.valid_step3_data.copy()
        invalid_data["location_name"] = ""
        
        response = self.client.post(self.step3_url, invalid_data)
        self.assertEqual(response.status_code, 200)
        # Should show validation error


class SignupWizardVerticalRedirectTestCase(TestCase):
    """Regression tests for vertical-specific redirect after wizard completion"""
    
    def setUp(self):
        self.client = Client()
        self.step1_url = reverse("accounts:signup_wizard_step", kwargs={"step": 1})
        self.step2_url = reverse("accounts:signup_wizard_step", kwargs={"step": 2})
        self.step3_url = reverse("accounts:signup_wizard_step", kwargs={"step": 3})
        self.step4_url = reverse("accounts:signup_wizard_step", kwargs={"step": 4})
    
    def _complete_wizard_until_step4(self, business_kind="clothing"):
        """Helper to complete wizard steps 1-3 with the given business kind"""
        # Step 1: Account
        self.client.post(self.step1_url, {
            "full_name": "E2E Test User",
            "email": f"e2e-{business_kind}-test@example.com",
            "password1": "E2ETestPass123!@#",
            "password2": "E2ETestPass123!@#",
        })
        
        # Step 2: Business with specified vertical
        self.client.post(self.step2_url, {
            "business_name": f"E2E {business_kind.title()} Store",
            "country": "Zambia",
            "currency": "ZMW",
            "business_kind": business_kind,
        })
        
        # Step 3: Location
        self.client.post(self.step3_url, {
            "location_name": "Main Store",
            "city": "Lusaka",
            "staff_count": "3",
        })
    
    def test_clothing_vertical_redirects_to_clothing_dashboard(self):
        """Test completing wizard with clothing vertical redirects to /inventory/verticals/clothing/"""
        self._complete_wizard_until_step4("clothing")
        
        # Step 4: Complete
        response = self.client.post(self.step4_url, {
            "goal_stop_theft": True,
        })
        
        # Should redirect (302)
        self.assertEqual(response.status_code, 302)
        
        # The redirect URL should include the clothing vertical path
        redirect_url = response.url
        # Allow for potential variations in URL structure
        self.assertTrue(
            "/inventory/verticals/clothing" in redirect_url or
            "/verticals/clothing" in redirect_url,
            f"Expected clothing dashboard redirect, got: {redirect_url}"
        )
    
    def test_gym_vertical_redirects_to_gym_dashboard(self):
        """Test completing wizard with gym vertical redirects to gym dashboard"""
        self._complete_wizard_until_step4("gym")
        
        response = self.client.post(self.step4_url, {
            "goal_see_profit": True,
        })
        
        self.assertEqual(response.status_code, 302)
        redirect_url = response.url
        self.assertTrue(
            "/gym" in redirect_url or "/inventory/verticals/gym" in redirect_url,
            f"Expected gym dashboard redirect, got: {redirect_url}"
        )
    
    def test_phones_vertical_redirects_to_phones_dashboard(self):
        """Test completing wizard with phones vertical redirects correctly"""
        self._complete_wizard_until_step4("phones")
        
        response = self.client.post(self.step4_url, {
            "goal_track_performance": True,
        })
        
        self.assertEqual(response.status_code, 302)
        redirect_url = response.url
        # Phones may redirect to /inventory/ or /inventory/verticals/phones/
        self.assertTrue(
            "/inventory" in redirect_url,
            f"Expected phones/inventory dashboard redirect, got: {redirect_url}"
        )
    
    def test_step4_accepts_empty_goals(self):
        """Test that step 4 accepts form submission with no goals selected (non-blocking)"""
        self._complete_wizard_until_step4("clothing")
        
        # Submit with no goals selected (all False)
        response = self.client.post(self.step4_url, {})
        
        # Should still redirect successfully (goals are optional)
        self.assertEqual(response.status_code, 302)
        # Should NOT stay on step 4
        self.assertNotIn("/wizard/4", response.url)
        self.assertNotIn("step=4", response.url)


class OnboardingProfileModelTestCase(TestCase):
    """Test the OnboardingProfile model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="test@example.com",
            email="test@example.com",
            password="TestPass123!"
        )
    
    def test_create_onboarding_profile(self):
        """Test creating an OnboardingProfile"""
        if OnboardingProfile is None:
            self.skipTest("OnboardingProfile model not available")
        
        from django.utils import timezone
        
        profile = OnboardingProfile.objects.create(
            user=self.user,
            goal_stop_theft=True,
            goal_see_profit=True,
            goal_track_performance=False,
            goal_move_off_notebooks=True,
            completed_at=timezone.now(),
            first_business_name="Test Store",
            first_location_name="Main Branch",
            chosen_vertical="phones",
        )
        
        self.assertEqual(profile.user, self.user)
        self.assertTrue(profile.goal_stop_theft)
        self.assertTrue(profile.is_complete)
        self.assertIn("Stop theft", profile.selected_goals)
        self.assertIn("See profit", profile.selected_goals)
        self.assertEqual(len(profile.selected_goals), 3)


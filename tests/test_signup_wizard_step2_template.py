"""
Test that signup wizard step 2 template renders without VariableDoesNotExist errors.

This test ensures that the template correctly accesses form fields via form.field_name.errors
instead of form.errors.field_name, which can cause VariableDoesNotExist exceptions.
"""
from django.test import Client, TestCase
from django.urls import reverse


class SignupWizardStep2TemplateTest(TestCase):
    """Test signup wizard step 2 template rendering"""

    def setUp(self):
        self.client = Client()
        self.url = reverse("accounts:signup_manager") + "?step=2"

    def test_step2_renders_without_errors_on_get(self):
        """
        Test that step 2 GET request renders without VariableDoesNotExist errors.

        This test ensures:
        - Template doesn't crash when accessing form.business_name.errors
        - Template doesn't crash when accessing form.business_kind.errors
        - Page contains the expected form fields
        """
        # First, complete step 1 to set up wizard session
        step1_url = reverse("accounts:signup_manager") + "?step=1"
        step1_data = {
            "step": "1",
            "email": "test@example.com",
            "full_name": "Test User",
            "password1": "xK9$mP2#vL7@qR4!",  # Strong random password
            "password2": "xK9$mP2#vL7@qR4!",
            "action": "next",
        }
        response = self.client.post(step1_url, data=step1_data, follow=True)

        # Should end up on step 2 (either directly or via redirect)
        self.assertEqual(response.status_code, 200)

        # Should contain the form fields with correct names
        self.assertContains(response, 'name="business_name"')
        self.assertContains(response, 'name="business_kind"')
        self.assertContains(response, 'name="subdomain"')

        # Should not contain error indicators on initial load
        self.assertNotContains(response, "is-error")

    def test_step2_shows_validation_errors_on_invalid_post(self):
        """
        Test that step 2 POST with invalid data shows errors correctly.

        This ensures:
        - Validation errors are displayed
        - Template handles form.field.errors correctly
        - Error styling is applied
        """
        # First, complete step 1
        step1_url = reverse("accounts:signup_manager") + "?step=1"
        step1_data = {
            "step": "1",
            "email": "test2@example.com",
            "full_name": "Test User 2",
            "password1": "xK9$mP2#vL7@qR4!",  # Strong random password
            "password2": "xK9$mP2#vL7@qR4!",
            "action": "next",
        }
        self.client.post(step1_url, data=step1_data)

        # POST step 2 with missing required fields
        response = self.client.post(
            self.url,
            data={
                "step": "2",
                "action": "next",
                # Missing business_name and business_kind
            },
        )

        # Should stay on step 2 (not redirect)
        self.assertEqual(response.status_code, 200)

        # Should show error styling
        self.assertContains(response, "is-error")

        # Should contain error messages
        self.assertContains(response, "This field is required", count=2)  # business_name and business_kind

    def test_step2_preserves_values_after_validation_error(self):
        """
        Test that step 2 preserves form values after validation errors.

        This ensures:
        - form.business_name.value works correctly
        - form.business_kind.value works correctly
        - Values persist after validation failure
        """
        # First, complete step 1
        step1_url = reverse("accounts:signup_manager") + "?step=1"
        step1_data = {
            "step": "1",
            "email": "test3@example.com",
            "full_name": "Test User 3",
            "password1": "xK9$mP2#vL7@qR4!",  # Strong random password
            "password2": "xK9$mP2#vL7@qR4!",
            "action": "next",
        }
        self.client.post(step1_url, data=step1_data)

        # POST step 2 with partial data (missing business_kind)
        response = self.client.post(
            self.url,
            data={
                "step": "2",
                "business_name": "My Test Store",
                "action": "next",
                # Missing business_kind
            },
        )

        # Should stay on step 2
        self.assertEqual(response.status_code, 200)

        # Should preserve the business_name value
        self.assertContains(response, 'value="My Test Store"')

    def test_step2_redirects_if_step1_not_completed(self):
        """
        Test that accessing step 2 without completing step 1 redirects back.

        This ensures wizard flow integrity.
        """
        # Try to access step 2 directly without completing step 1
        response = self.client.get(self.url)

        # Should redirect to step 1
        self.assertEqual(response.status_code, 302)
        self.assertIn("step=1", response.url)

    def test_step2_successful_submission_redirects_to_step3(self):
        """
        Test that valid step 2 submission redirects to step 3.

        This ensures the wizard progresses correctly.
        """
        # First, complete step 1
        step1_url = reverse("accounts:signup_manager") + "?step=1"
        step1_data = {
            "step": "1",
            "email": "test4@example.com",
            "full_name": "Test User 4",
            "password1": "xK9$mP2#vL7@qR4!",  # Strong random password
            "password2": "xK9$mP2#vL7@qR4!",
            "action": "next",
        }
        self.client.post(step1_url, data=step1_data)

        # POST step 2 with valid data
        response = self.client.post(
            self.url,
            data={
                "step": "2",
                "business_name": "Valid Store Name",
                "business_kind": "phones",
                "subdomain": "validstore",
                "action": "next",
            },
        )

        # Should redirect to step 3
        self.assertEqual(response.status_code, 302)
        self.assertIn("step=3", response.url)

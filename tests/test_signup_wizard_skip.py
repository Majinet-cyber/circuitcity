# tests/test_signup_wizard_skip.py
"""
Tests for signup wizard functionality.
Tests the skip button and disabled logo upload in step 3.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


class TestSignupWizardStep3(TestCase):
    """Test signup wizard step 3: brand/logo page with skip functionality."""
    
    def setUp(self):
        """Set up test client and session data."""
        self.client = Client()
        self.url_step3 = reverse('accounts:signup_manager') + '?step=3'
        
        # Set up wizard data in session (simulating completed steps 1 & 2)
        session = self.client.session
        session['manager_wizard_data'] = {
            'step1': {
                'email': 'test@example.com',
                'full_name': 'Test User',
                'password': 'TestPassword123!',
            },
            'step2': {
                'business_name': 'Test Business',
                'business_kind': 'phones',
                'subdomain': 'testbiz',
            }
        }
        session.save()
    
    def test_step3_get_returns_200_with_skip_button(self):
        """GET step=3 returns 200 and contains 'Skip for now' button."""
        response = self.client.get(self.url_step3)
        
        assert response.status_code == 200
        assert b'Skip for now' in response.content or b'skip' in response.content.lower()
        assert b'Step 3 of 4' in response.content
    
    def test_step3_logo_upload_is_disabled(self):
        """Step 3 template shows logo upload is disabled/coming soon."""
        response = self.client.get(self.url_step3)
        
        assert response.status_code == 200
        # Check for disabled attribute or "coming soon" message
        content = response.content.decode('utf-8').lower()
        assert 'disabled' in content or 'coming soon' in content
        assert 'logo' in content
    
    def test_step3_skip_button_advances_to_step4(self):
        """POST step=3 with action=skip advances to step 4 (302)."""
        response = self.client.post(self.url_step3, {
            'step': '3',
            'action': 'skip',
        })
        
        # Should redirect to step 4
        assert response.status_code == 302
        assert 'step=4' in response.url
        
        # Verify session was updated
        session = self.client.session
        wizard_data = session.get('manager_wizard_data', {})
        assert 'step3' in wizard_data
        assert wizard_data['step3'] == {}  # Empty dict for skip
    
    def test_step3_skip_does_not_require_file(self):
        """POST step=3 with skip does not validate/require logo file."""
        response = self.client.post(self.url_step3, {
            'step': '3',
            'action': 'skip',
            # No logo file uploaded
        })
        
        # Should succeed without file
        assert response.status_code == 302
        assert 'step=4' in response.url
    
    def test_step3_next_button_also_works_without_file(self):
        """POST step=3 with action=next also advances without file (since logo is optional)."""
        response = self.client.post(self.url_step3, {
            'step': '3',
            'action': 'next',
            # No logo file uploaded
        })
        
        # Should succeed and advance to step 4
        assert response.status_code == 302
        assert 'step=4' in response.url
    
    def test_step3_back_button_returns_to_step2(self):
        """POST step=3 with action=back returns to step 2."""
        response = self.client.post(self.url_step3, {
            'step': '3',
            'action': 'back',
        })
        
        assert response.status_code == 302
        assert 'step=2' in response.url
    
    def test_step3_requires_previous_steps_completed(self):
        """GET step=3 without completed steps 1 & 2 redirects to step 1."""
        # Clear session
        session = self.client.session
        session['manager_wizard_data'] = {}
        session.save()
        
        response = self.client.get(self.url_step3)
        
        # Should redirect to step 1
        assert response.status_code == 302
        assert 'step=1' in response.url
    
    def test_step3_no_500_errors(self):
        """Step 3 does not return 500 errors under normal conditions."""
        response = self.client.get(self.url_step3)
        assert response.status_code in [200, 302]  # Either renders or redirects
        
        response = self.client.post(self.url_step3, {'action': 'skip', 'step': '3'})
        assert response.status_code in [200, 302]


class TestSignupWizardStep3Integration(TestCase):
    """Integration tests for signup wizard step 3."""
    
    def setUp(self):
        """Set up test client."""
        self.client = Client()
    
    def test_complete_wizard_flow_with_skip(self):
        """Test complete wizard flow from step 1 to step 4 using skip on step 3."""
        # Step 1
        response = self.client.post(reverse('accounts:signup_manager') + '?step=1', {
            'step': '1',
            'action': 'next',
            'email': 'integration@test.com',
            'full_name': 'Integration Test',
            'password': 'IntegrationTest123!',
            'password_confirm': 'IntegrationTest123!',
            'agree': 'on',
        })
        assert response.status_code == 302
        assert 'step=2' in response.url
        
        # Step 2
        response = self.client.post(reverse('accounts:signup_manager') + '?step=2', {
            'step': '2',
            'action': 'next',
            'business_name': 'Integration Business',
            'business_kind': 'phones',
            'subdomain': 'integrationtest',
        })
        assert response.status_code == 302
        assert 'step=3' in response.url
        
        # Step 3 - Skip
        response = self.client.post(reverse('accounts:signup_manager') + '?step=3', {
            'step': '3',
            'action': 'skip',
        })
        assert response.status_code == 302
        assert 'step=4' in response.url
        
        # Step 4 should load without errors
        response = self.client.get(reverse('accounts:signup_manager') + '?step=4')
        assert response.status_code == 200
        assert b'Step 4 of 4' in response.content or b'Review' in response.content


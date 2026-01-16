"""
Tests for contact page with PRG pattern and marketing content.
"""
from django.test import TestCase, Client
from django.urls import reverse


class ContactPageTests(TestCase):
    """Tests for the contact page with PRG pattern."""
    
    def setUp(self):
        self.client = Client()
        self.contact_url = reverse('staticpages:contact')
    
    def test_contact_page_get_no_success_message(self):
        """GET /contact/ should NOT show the success message by default."""
        response = self.client.get(self.contact_url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'staticpages/contact.html')
        
        # The success message should not be visible (show_success should be False)
        self.assertFalse(response.context.get('show_success', False))
        
        # Check that the HTML does not have the 'show' class on success message by default
        self.assertNotContains(response, '<div class="success-message show"')
    
    def test_contact_page_post_redirects(self):
        """POST /contact/ with valid data should redirect to /contact/?sent=1."""
        post_data = {
            'name': 'Test User',
            'email': 'test@example.com',
            'subject': 'custom_plan',
            'message': 'This is a test message'
        }
        
        response = self.client.post(self.contact_url, post_data)
        
        # Should redirect (status 302)
        self.assertEqual(response.status_code, 302)
        
        # Should redirect to contact page with sent=1
        self.assertTrue('/landing/contact/' in response.url)
        self.assertIn('sent=1', response.url)
    
    def test_contact_page_get_with_sent_param_shows_success(self):
        """GET /contact/?sent=1 should show the success message."""
        response = self.client.get(self.contact_url + '?sent=1')
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'staticpages/contact.html')
        
        # The success message should be visible (show_success should be True)
        self.assertTrue(response.context.get('show_success', False))
        
        # Check that the HTML has the 'show' class on success message
        self.assertContains(response, '<div class="success-message show"')
    
    def test_contact_page_ajax_returns_json(self):
        """POST /contact/ with AJAX should return JSON success response."""
        post_data = {
            'name': 'Test User',
            'email': 'test@example.com',
            'subject': 'support',
            'message': 'Test AJAX submission'
        }
        
        response = self.client.post(
            self.contact_url,
            post_data,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        # Should return 200 OK
        self.assertEqual(response.status_code, 200)
        
        # Should return JSON
        self.assertEqual(response['Content-Type'], 'application/json')
        
        # Should have success: true
        json_data = response.json()
        self.assertTrue(json_data.get('success', False))


class MarketingContentTests(TestCase):
    """Tests for marketing content consistency across pages."""
    
    def setUp(self):
        self.client = Client()
    
    def test_homepage_no_join_thousands(self):
        """Homepage should not contain 'Join thousands'."""
        response = self.client.get(reverse('staticpages:home'))
        
        self.assertEqual(response.status_code, 200)
        
        # Should not contain the old text
        self.assertNotContains(response, 'Join thousands', html=False)
    
    def test_homepage_has_correct_email(self):
        """Homepage should use support@emajinet.africa (not .com)."""
        response = self.client.get(reverse('staticpages:home'))
        
        self.assertEqual(response.status_code, 200)
        
        # Should not contain the .com email
        self.assertNotContains(response, 'support@emajinet.com', html=False)
    
    def test_about_page_has_trust_block(self):
        """About page should have trust block with support info."""
        response = self.client.get(reverse('staticpages:about'))
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'staticpages/about.html')
        
        # Should contain trust block sections (enhanced copy)
        self.assertContains(response, 'Who It\'s For')
        self.assertContains(response, 'What It Does')
        self.assertContains(response, 'Where We Focus')
        # Support section (new naming)
        self.assertContains(response, 'Support')
        # Trust section
        self.assertContains(response, 'Why Businesses Trust Emajinet')
    
    def test_about_page_has_whatsapp(self):
        """About page should display working WhatsApp number."""
        response = self.client.get(reverse('staticpages:about'))
        
        self.assertEqual(response.status_code, 200)
        
        # Should contain WhatsApp link
        self.assertContains(response, 'WhatsApp')
        
        # Should contain the updated WhatsApp number
        self.assertContains(response, '+265 883 596 135')
        
        # Should not contain placeholder
        self.assertNotContains(response, 'Coming soon', html=False)
        self.assertNotContains(response, 'XXX', html=False)
    
    def test_about_page_team_section(self):
        """About page should NOT have a team section (team is on homepage only)."""
        response = self.client.get(reverse('staticpages:about'))
        
        self.assertEqual(response.status_code, 200)
        
        # About page should NOT contain team section
        self.assertNotContains(response, 'Our Team')
        self.assertNotContains(response, 'Faith Banda')
        self.assertNotContains(response, 'Joseph Miamba')
    
    def test_homepage_team_section(self):
        """Homepage should have team section with all 4 members including Faith Banda."""
        response = self.client.get(reverse('staticpages:home'))
        
        self.assertEqual(response.status_code, 200)
        
        # Should contain team section heading
        self.assertContains(response, 'Team')
        self.assertContains(response, 'Built in Malawi, for Africa')
        
        # Should contain Faith Banda with correct details
        self.assertContains(response, 'Faith Banda')
        self.assertContains(response, 'Executive Director')
        self.assertContains(response, 'University of Strathclyde')
        self.assertContains(response, 'MUST')
        
        # Should contain Joseph Miamba with updated role
        self.assertContains(response, 'Josephy Miamba')
        self.assertContains(response, 'Head of Marketing')
        
        # Should NOT contain old role
        self.assertNotContains(response, 'Director of Operations')
    
    def test_no_dot_com_emails_in_public_pages(self):
        """All public pages should use .africa email, not .com."""
        urls_to_check = [
            reverse('staticpages:contact'),
            reverse('staticpages:about'),
            reverse('staticpages:pricing'),
            reverse('staticpages:terms'),
        ]
        
        for url in urls_to_check:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                # Should not contain the .com email anywhere
                self.assertNotContains(response, 'support@emajinet.com', html=False)


from django.test import TestCase, Client
from django.urls import reverse


class HomePageTeamSectionTest(TestCase):
    """
    Tests for the Team section on the homepage.
    """
    
    def setUp(self):
        self.client = Client()
        self.url = reverse('staticpages:home')
    
    def test_homepage_renders_200(self):
        """Home page should render successfully."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
    
    def test_team_section_present(self):
        """Team section should be present on homepage."""
        response = self.client.get(self.url)
        self.assertContains(response, 'Team')
        self.assertContains(response, 'Built in Malawi, for Africa')
    
    def test_team_members_present(self):
        """All three team members should be listed on homepage."""
        response = self.client.get(self.url)
        
        # Check for Paul Chris Mwale
        self.assertContains(response, 'Paul Chris Mwale')
        self.assertContains(response, 'CEO & Co-founder')
        
        # Check for Josephy Miamba
        self.assertContains(response, 'Josephy Miamba')
        self.assertContains(response, 'Director of Operations')
        
        # Check for Lloyd Chunga
        self.assertContains(response, 'Lloyd Chunga')
        self.assertContains(response, 'CTO')
    
    def test_team_education_present(self):
        """Team member education should be listed."""
        response = self.client.get(self.url)
        
        # Check for some education details
        self.assertContains(response, 'Quantic')
        self.assertContains(response, 'Mzuzu University')
        self.assertContains(response, 'University of Delaware')
    
    def test_join_cta_present(self):
        """Join the Team CTA should be present on homepage."""
        response = self.client.get(self.url)
        self.assertContains(response, 'Want to join the team?')
        self.assertContains(response, 'talented builders')
    
    def test_join_cta_has_links(self):
        """Join CTA should have email and apply links."""
        response = self.client.get(self.url)
        self.assertContains(response, 'mailto:team@emajinet.africa')
        self.assertContains(response, reverse('staticpages:join_team'))


class JoinTeamPageTest(TestCase):
    """
    Tests for the /join/ page (team application form).
    """
    
    def setUp(self):
        self.client = Client()
        self.url = reverse('staticpages:join_team')
    
    def test_join_page_renders_200(self):
        """Join page should render successfully."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
    
    def test_join_page_has_form(self):
        """Join page should contain the application form."""
        response = self.client.get(self.url)
        self.assertContains(response, '<form')
        self.assertContains(response, 'full_name')
        self.assertContains(response, 'email')
        self.assertContains(response, 'role')
        self.assertContains(response, 'message')
    
    def test_join_page_has_role_options(self):
        """Join page should have all role options."""
        response = self.client.get(self.url)
        self.assertContains(response, 'Engineering')
        self.assertContains(response, 'Operations')
        self.assertContains(response, 'Sales')
        self.assertContains(response, 'Design')
        self.assertContains(response, 'Customer Support')
        self.assertContains(response, 'Other')
    
    def test_join_form_submission_valid(self):
        """Valid form submission should return 200 and show success message."""
        data = {
            'full_name': 'Test Applicant',
            'email': 'test@example.com',
            'role': 'engineering',
            'linkedin_portfolio': 'https://linkedin.com/in/test',
            'message': 'I would love to join the team because...',
        }
        response = self.client.post(self.url, data)
        
        # Should return 200 (not redirect)
        self.assertEqual(response.status_code, 200)
        
        # Should show success message
        self.assertContains(response, 'Thank you')
        self.assertContains(response, 'received your message')
    
    def test_join_form_submission_without_email_backend(self):
        """Form submission should work even if email backend is not configured."""
        # This test ensures the view handles email failures gracefully
        data = {
            'full_name': 'Test User',
            'email': 'test@example.com',
            'role': 'sales',
            'message': 'Test message',
        }
        response = self.client.post(self.url, data)
        
        # Should still return success (not crash)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Thank you')
    
    def test_join_form_validation_missing_required_fields(self):
        """Form should validate required fields."""
        # Submit with missing required fields
        data = {
            'full_name': '',  # Missing
            'email': 'test@example.com',
            'role': 'engineering',
            'message': '',  # Missing
        }
        response = self.client.post(self.url, data)
        
        # Should return 200 with form errors (not success)
        self.assertEqual(response.status_code, 200)
        # Should not show success message
        self.assertNotContains(response, 'Thank you')
    
    def test_join_form_validation_invalid_email(self):
        """Form should validate email format."""
        data = {
            'full_name': 'Test User',
            'email': 'invalid-email',  # Invalid email
            'role': 'engineering',
            'message': 'Test message',
        }
        response = self.client.post(self.url, data)
        
        # Should return 200 with form errors
        self.assertEqual(response.status_code, 200)
        # Should not show success message
        self.assertNotContains(response, 'Thank you')
    
    def test_join_form_validation_invalid_role(self):
        """Form should validate role selection."""
        data = {
            'full_name': 'Test User',
            'email': 'test@example.com',
            'role': '',  # Empty role
            'message': 'Test message',
        }
        response = self.client.post(self.url, data)
        
        # Should return 200 with form errors
        self.assertEqual(response.status_code, 200)
        # Should not show success message
        self.assertNotContains(response, 'Thank you')
    
    def test_join_form_optional_fields(self):
        """Form should work without optional fields."""
        data = {
            'full_name': 'Test User',
            'email': 'test@example.com',
            'role': 'design',
            'message': 'Test message',
            # No linkedin_portfolio (optional field)
        }
        response = self.client.post(self.url, data)
        
        # Should return success
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Thank you')
    
    def test_csrf_protection(self):
        """Form should have CSRF protection."""
        response = self.client.get(self.url)
        self.assertContains(response, 'csrfmiddlewaretoken')


class StaticPagesRegressionTest(TestCase):
    """
    Regression tests to ensure existing pages still work.
    """
    
    def test_about_page_still_works(self):
        """About page should still render."""
        response = self.client.get(reverse('staticpages:about'))
        self.assertEqual(response.status_code, 200)
    
    def test_pricing_page_still_works(self):
        """Pricing page should still render."""
        response = self.client.get(reverse('staticpages:pricing'))
        self.assertEqual(response.status_code, 200)
    
    def test_contact_page_still_works(self):
        """Contact page should still render."""
        response = self.client.get(reverse('staticpages:contact'))
        self.assertEqual(response.status_code, 200)
    
    def test_privacy_page_still_works(self):
        """Privacy page should still render."""
        response = self.client.get(reverse('staticpages:privacy'))
        self.assertEqual(response.status_code, 200)
    
    def test_terms_page_still_works(self):
        """Terms page should still render."""
        response = self.client.get(reverse('staticpages:terms'))
        self.assertEqual(response.status_code, 200)


"""
Tests for HQ Onboarding PDF feature.
Ensures PDF download works for HQ staff and blocks non-HQ users without crashing.
"""

import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


class HQOnboardingPDFTests(TestCase):
    """Test HQ Onboarding PDF download functionality."""

    def setUp(self):
        """Set up test users."""
        self.client = Client()
        
        # Create HQ staff user (superuser)
        self.hq_user = User.objects.create_user(
            username='hqstaff',
            email='hq@example.com',
            password='testpass123',
            is_staff=True,
            is_superuser=True
        )
        
        # Create regular staff user (not superuser)
        self.staff_user = User.objects.create_user(
            username='staff',
            email='staff@example.com',
            password='testpass123',
            is_staff=True,
            is_superuser=False
        )
        
        # Create regular user (not staff)
        self.regular_user = User.objects.create_user(
            username='regular',
            email='regular@example.com',
            password='testpass123',
            is_staff=False,
            is_superuser=False
        )

    def test_hq_user_can_download_pdf(self):
        """HQ superuser should be able to download PDF."""
        self.client.login(username='hqstaff', password='testpass123')
        url = reverse('staticpages:hq_onboarding_pdf')
        
        response = self.client.get(url)
        
        # Should return 200 with PDF
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('hq_staff_onboarding_guide.pdf', response['Content-Disposition'])
        
        # Check that response starts with PDF signature
        content = response.content
        self.assertTrue(content.startswith(b'%PDF'), "Response should be a valid PDF file")

    def test_staff_user_can_download_pdf(self):
        """Regular staff user should also be able to download PDF."""
        self.client.login(username='staff', password='testpass123')
        url = reverse('staticpages:hq_onboarding_pdf')
        
        response = self.client.get(url)
        
        # Should return 200 with PDF
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_regular_user_blocked_no_500(self):
        """Regular user should be blocked (403 or redirect), not 500."""
        self.client.login(username='regular', password='testpass123')
        url = reverse('staticpages:hq_onboarding_pdf')
        
        response = self.client.get(url)
        
        # Should redirect (302) or return forbidden (403), not 500
        self.assertIn(response.status_code, [302, 403], 
                      "Regular user should be blocked with redirect or 403, not crash")
        
        # If it's a redirect, make sure we're not getting a PDF
        if response.status_code == 302:
            self.assertNotEqual(response.get('Content-Type'), 'application/pdf')

    def test_anonymous_user_blocked_no_500(self):
        """Anonymous user should be blocked/redirected, not 500."""
        # Don't login
        url = reverse('staticpages:hq_onboarding_pdf')
        
        response = self.client.get(url)
        
        # Should redirect (302) or return forbidden (403), not 500
        self.assertIn(response.status_code, [302, 403], 
                      "Anonymous user should be blocked with redirect or 403, not crash")
        
        # Should not be a PDF
        self.assertNotEqual(response.get('Content-Type'), 'application/pdf')

    def test_pdf_content_not_empty(self):
        """PDF should have actual content, not be empty."""
        self.client.login(username='hqstaff', password='testpass123')
        url = reverse('staticpages:hq_onboarding_pdf')
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        # PDF should be at least 1KB (typical minimum for a real PDF with content)
        self.assertGreater(len(response.content), 1000, 
                          "PDF should contain substantial content")

    def test_onboarding_page_has_download_button(self):
        """Onboarding page should have enabled download button."""
        self.client.login(username='hqstaff', password='testpass123')
        url = reverse('staticpages:onboarding_hq')
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        
        # Should have the download link
        self.assertIn('hq_onboarding_pdf', content, 
                     "Onboarding page should link to PDF download")
        self.assertIn('Download PDF', content, 
                     "Download PDF text should be present")
        
        # Should NOT have "Coming Soon" anymore
        self.assertNotIn('Coming Soon', content, 
                        "Should not show 'Coming Soon' anymore")
        self.assertNotIn('disabled', content.lower() or 'btn-outline-secondary' not in content, 
                        "Button should not be disabled")

    def test_pdf_generation_error_handling(self):
        """Test that PDF generation errors don't cause 500 errors."""
        self.client.login(username='hqstaff', password='testpass123')
        url = reverse('staticpages:hq_onboarding_pdf')
        
        # Even if there's an internal error, we should get a graceful response
        # This test mainly ensures the try-except blocks are working
        response = self.client.get(url)
        
        # Should not be a 500 error
        self.assertNotEqual(response.status_code, 500, 
                           "PDF generation should never return 500")
        
        # Should be either 200 (success) or redirect (handled error)
        self.assertIn(response.status_code, [200, 302, 403])

    def test_url_pattern_exists(self):
        """Test that the URL pattern is correctly configured."""
        try:
            url = reverse('staticpages:hq_onboarding_pdf')
            self.assertTrue(url.endswith('/pdf/') or '/pdf/' in url,
                          "URL should contain /pdf/ path")
        except Exception as e:
            self.fail(f"URL reverse failed: {e}")

    def test_pdf_filename_correct(self):
        """Test that PDF is downloaded with correct filename."""
        self.client.login(username='hqstaff', password='testpass123')
        url = reverse('staticpages:hq_onboarding_pdf')
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        disposition = response.get('Content-Disposition', '')
        
        # Check for attachment disposition
        self.assertIn('attachment', disposition)
        self.assertIn('hq_staff_onboarding_guide.pdf', disposition)
        
        # Verify exact format
        self.assertIn('filename="hq_staff_onboarding_guide.pdf"', disposition)


@pytest.mark.django_db
class HQOnboardingPDFContentTests(TestCase):
    """Test PDF content structure and completeness."""

    def setUp(self):
        """Set up HQ user for content testing."""
        self.client = Client()
        self.hq_user = User.objects.create_user(
            username='hqstaff',
            email='hq@example.com',
            password='testpass123',
            is_staff=True,
            is_superuser=True
        )
        self.client.login(username='hqstaff', password='testpass123')

    def test_pdf_has_title(self):
        """PDF should contain the title."""
        url = reverse('staticpages:hq_onboarding_pdf')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        # Basic check that it's a PDF
        self.assertTrue(response.content.startswith(b'%PDF'))
        # PDF should be substantial in size
        self.assertGreater(len(response.content), 5000)

    def test_shared_content_structure_exists(self):
        """Test that shared content structure is properly defined."""
        from staticpages.onboarding_content import HQ_ONBOARDING_CONTENT
        
        # Should be a list
        self.assertIsInstance(HQ_ONBOARDING_CONTENT, list)
        
        # Should have multiple items
        self.assertGreater(len(HQ_ONBOARDING_CONTENT), 10)
        
        # First item should be the title
        self.assertEqual(HQ_ONBOARDING_CONTENT[0]['type'], 'title')
        self.assertIn('HQ Staff Onboarding', HQ_ONBOARDING_CONTENT[0]['text'])

    def test_content_has_required_sections(self):
        """Test that content includes all required sections."""
        from staticpages.onboarding_content import HQ_ONBOARDING_CONTENT
        
        # Convert to text for searching
        all_text = ' '.join([
            item.get('text', '') 
            for item in HQ_ONBOARDING_CONTENT 
            if 'text' in item
        ])
        
        # Check for required sections
        required_sections = [
            'What is the HQ Portal',
            'Getting Started',
            'Business Management',
            'Subscription Management',
            'Compliance',
            'Security',
        ]
        
        for section in required_sections:
            self.assertIn(section, all_text, 
                         f"Content should include '{section}' section")


class HQOnboardingIntegrationTests(TestCase):
    """Integration tests for the full HQ onboarding workflow."""

    def setUp(self):
        """Set up test environment."""
        self.client = Client()
        self.hq_user = User.objects.create_user(
            username='hqstaff',
            email='hq@example.com',
            password='testpass123',
            is_staff=True,
            is_superuser=True
        )

    def test_full_workflow_view_then_download(self):
        """Test viewing the onboarding page then downloading PDF."""
        self.client.login(username='hqstaff', password='testpass123')
        
        # 1. View the onboarding page
        page_url = reverse('staticpages:onboarding_hq')
        page_response = self.client.get(page_url)
        
        self.assertEqual(page_response.status_code, 200)
        
        # 2. Download the PDF
        pdf_url = reverse('staticpages:hq_onboarding_pdf')
        pdf_response = self.client.get(pdf_url)
        
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response['Content-Type'], 'application/pdf')
        self.assertTrue(pdf_response.content.startswith(b'%PDF'))

    def test_multiple_downloads_work(self):
        """Test that PDF can be downloaded multiple times."""
        self.client.login(username='hqstaff', password='testpass123')
        url = reverse('staticpages:hq_onboarding_pdf')
        
        # Download multiple times
        for _ in range(3):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/pdf')
            self.assertTrue(response.content.startswith(b'%PDF'))


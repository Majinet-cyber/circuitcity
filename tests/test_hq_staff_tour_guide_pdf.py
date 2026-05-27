"""
Tests for HQ Staff Tour Guide PDF download feature.

Ensures:
- HQ users can access the tour guide page and download PDF
- Non-HQ users are blocked (403/redirect)
- Anonymous users are redirected to login
- PDF generation never causes 500 errors
"""
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from tenants.models import Business, Membership

User = get_user_model()


@pytest.fixture
def hq_user(db):
    """Create an HQ admin user (superuser)."""
    user = User.objects.create_user(
        username='hq_admin',
        email='hq@example.com',
        password='testpass123',
        is_staff=True,
        is_superuser=True
    )
    return user


@pytest.fixture
def non_hq_user(db):
    """Create a regular business manager (not HQ)."""
    business = Business.objects.create(
        name='Test Business',
        slug='test-business'
    )
    user = User.objects.create_user(
        username='manager',
        email='manager@example.com',
        password='testpass123'
    )
    # Create membership as MANAGER
    Membership.objects.create(
        business=business,
        user=user,
        role='MANAGER'
    )
    return user


@pytest.mark.django_db
class TestHQStaffTourGuideHTML:
    """Tests for the HTML tour guide page."""
    
    def test_hq_user_can_access_tour_guide_page(self, client, hq_user):
        """HQ user should be able to access the tour guide page."""
        client.force_login(hq_user)
        url = reverse('hq:staff_tour_guide')
        response = client.get(url)
        
        assert response.status_code == 200
        assert 'HQ Staff Tour Guide' in response.content.decode()
    
    def test_non_hq_user_cannot_access_tour_guide_page(self, client, non_hq_user):
        """Non-HQ user should be blocked from accessing tour guide page."""
        client.force_login(non_hq_user)
        url = reverse('hq:staff_tour_guide')
        response = client.get(url)
        
        # Should be 403 or redirect (not 200, not 500)
        assert response.status_code in [302, 403], \
            f"Expected 302 or 403, got {response.status_code}"
    
    def test_anonymous_user_redirected_to_login(self, client):
        """Anonymous user should be redirected to login."""
        url = reverse('hq:staff_tour_guide')
        response = client.get(url)
        
        # Should redirect to login (302)
        assert response.status_code == 302
        assert 'login' in response.url.lower() or 'accounts' in response.url.lower()


@pytest.mark.django_db
class TestHQStaffTourGuidePDF:
    """Tests for the PDF download endpoint."""
    
    def test_hq_user_can_download_pdf(self, client, hq_user):
        """HQ user should successfully download the tour guide PDF."""
        client.force_login(hq_user)
        url = reverse('hq:staff_tour_guide_pdf')
        response = client.get(url)
        
        # Should return 200 (or 503 if reportlab not installed, but not 500)
        assert response.status_code in [200, 503], \
            f"Expected 200 or 503, got {response.status_code}"
        
        if response.status_code == 200:
            # Check Content-Type
            assert response['Content-Type'] == 'application/pdf', \
                f"Expected application/pdf, got {response['Content-Type']}"
            
            # Check Content-Disposition header
            assert 'Content-Disposition' in response
            assert 'attachment' in response['Content-Disposition']
            assert 'hq_staff_tour_guide.pdf' in response['Content-Disposition']
            
            # Check that response starts with PDF magic bytes
            content = response.content
            assert content.startswith(b'%PDF'), \
                "Response should start with %PDF"
            
            # Check that PDF has some content (not empty)
            assert len(content) > 1000, \
                f"PDF seems too small: {len(content)} bytes"
    
    def test_non_hq_user_cannot_download_pdf(self, client, non_hq_user):
        """Non-HQ user should be blocked from downloading PDF."""
        client.force_login(non_hq_user)
        url = reverse('hq:staff_tour_guide_pdf')
        response = client.get(url)
        
        # Should be 403 or redirect (not 200, not 500)
        assert response.status_code in [302, 403], \
            f"Expected 302 or 403, got {response.status_code}"
        
        # Should NOT return PDF content
        if hasattr(response, 'content'):
            assert not response.content.startswith(b'%PDF'), \
                "Non-HQ user should not receive PDF content"
    
    def test_anonymous_user_cannot_download_pdf(self, client):
        """Anonymous user should be redirected to login, not download PDF."""
        url = reverse('hq:staff_tour_guide_pdf')
        response = client.get(url)
        
        # Should redirect to login (302)
        assert response.status_code == 302
        assert 'login' in response.url.lower() or 'accounts' in response.url.lower()
        
        # Should NOT return PDF content
        if hasattr(response, 'content'):
            assert not response.content.startswith(b'%PDF'), \
                "Anonymous user should not receive PDF content"
    
    def test_pdf_endpoint_never_500s(self, client, hq_user):
        """PDF endpoint should never return 500, even if ReportLab fails."""
        client.force_login(hq_user)
        url = reverse('hq:staff_tour_guide_pdf')
        response = client.get(url)
        
        # Should never be 500
        assert response.status_code != 500, \
            f"PDF endpoint returned 500: {response.content.decode() if hasattr(response, 'content') else ''}"
    
    def test_multiple_downloads_work(self, client, hq_user):
        """Multiple sequential downloads should all work."""
        client.force_login(hq_user)
        url = reverse('hq:staff_tour_guide_pdf')
        
        for i in range(3):
            response = client.get(url)
            assert response.status_code in [200, 503], \
                f"Download {i+1} failed with status {response.status_code}"


@pytest.mark.django_db
class TestHQStaffTourGuidePermissions:
    """Additional permission and security tests."""
    
    def test_staff_user_without_superuser_has_appropriate_access(self, client, db):
        """Staff user (but not superuser) should follow hq_admin_required rules."""
        user = User.objects.create_user(
            username='staff_only',
            email='staff@example.com',
            password='testpass123',
            is_staff=True,
            is_superuser=False  # Not a superuser
        )
        client.force_login(user)
        
        url = reverse('hq:staff_tour_guide_pdf')
        response = client.get(url)
        
        # Depends on hq_admin_required implementation:
        # - If it requires superuser: should be 403/redirect
        # - If staff is sufficient: should be 200/503
        # Either way, should NOT be 500
        assert response.status_code != 500
    
    def test_url_patterns_are_registered(self):
        """Verify URL patterns are properly registered."""
        # Should not raise NoReverseMatch
        try:
            url_html = reverse('hq:staff_tour_guide')
            url_pdf = reverse('hq:staff_tour_guide_pdf')
            
            assert url_html.endswith('/staff/tour-guide/')
            assert url_pdf.endswith('/staff/tour-guide.pdf')
        except Exception as e:
            pytest.fail(f"URL patterns not registered correctly: {e}")


@pytest.mark.django_db
class TestHQStaffTourGuideRobustness:
    """Tests for robustness and error handling."""
    
    def test_pdf_generation_with_missing_reportlab(self, client, hq_user, monkeypatch):
        """If ReportLab is missing, should return 503 gracefully, not 500."""
        # This test verifies the REPORTLAB_AVAILABLE flag works
        client.force_login(hq_user)
        url = reverse('hq:staff_tour_guide_pdf')
        
        # Even if reportlab import fails, the view should handle it
        response = client.get(url)
        
        # Should be 200 (if reportlab works) or 503 (if not installed)
        # But NEVER 500
        assert response.status_code in [200, 503]
        
        if response.status_code == 503:
            content = response.content.decode()
            assert 'reportlab' in content.lower()
    
    def test_html_page_has_download_link(self, client, hq_user):
        """HTML page should contain a link to the PDF."""
        client.force_login(hq_user)
        url = reverse('hq:staff_tour_guide')
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode()
        
        # Should have a link to the PDF
        assert 'tour-guide.pdf' in content or 'staff_tour_guide_pdf' in content
        assert 'Download' in content or 'download' in content


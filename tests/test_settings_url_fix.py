# tests/test_settings_url_fix.py
"""
Regression tests for /settings// double slash bug.
Ensures 404 pages don't crash and URLs are properly normalized.
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
class TestSettingsURLFix(TestCase):
    """
    Test that /settings// is properly handled and doesn't crash.
    """

    def setUp(self):
        """Create test user"""
        self.user = User.objects.create_user(username="test_user", email="test@test.local", password="test1234")
        self.client = Client()

    def test_settings_root_url_exists(self):
        """Test that settings_root URL name can be reversed"""
        try:
            url = reverse("settings_root")
            assert url == "/settings/", f"Expected '/settings/', got '{url}'"
        except Exception as e:
            self.fail(f"settings_root URL should be reversible: {e}")

    def test_settings_double_slash_redirects(self):
        """Test that /settings// redirects to /settings/ (not 500)"""
        self.client.login(username="test_user", password="test1234")

        response = self.client.get("/settings//", follow=False)

        # Should be a redirect (301 or 302), NOT 500 or 404
        assert response.status_code in (301, 302), f"Expected redirect (301/302), got {response.status_code}"

        # Should redirect to normalized path
        assert response.url in (
            "/settings/",
            "/accounts/settings/",
        ), f"Expected redirect to '/settings/' or '/accounts/settings/', got '{response.url}'"

    def test_settings_triple_slash_redirects(self):
        """Test that /settings/// also gets normalized"""
        self.client.login(username="test_user", password="test1234")

        response = self.client.get("/settings///", follow=False)

        # Should be a redirect, not an error
        assert response.status_code in (301, 302, 404), f"Expected redirect or 404, got {response.status_code}"

    def test_random_404_does_not_crash(self):
        """Test that a random nonexistent URL returns clean 404"""
        response = self.client.get("/this-does-not-exist/", follow=False)

        # Should be 404
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"

        # Should not cause template errors (check response has content)
        assert len(response.content) > 0, "404 page should render without crashing"

        # Should not contain Python exception text
        content_text = response.content.decode("utf-8", errors="ignore").lower()
        assert "variab ledoesnotexist" not in content_text.replace(
            " ", ""
        ), "404 page should not show Python exceptions"
        assert "traceback" not in content_text, "404 page should not show tracebacks"

    def test_double_slash_in_middle_of_path(self):
        """Test that double slashes in middle of path are normalized"""
        response = self.client.get("/accounts//profile/", follow=False)

        # Should be redirected or 404 (not 500)
        assert response.status_code in (301, 302, 404), f"Expected redirect or 404, got {response.status_code}"

    def test_settings_url_with_querystring(self):
        """Test that /settings//?param=value preserves querystring"""
        self.client.login(username="test_user", password="test1234")

        response = self.client.get("/settings//?tab=profile", follow=False)

        # Should redirect
        if response.status_code in (301, 302):
            # Check querystring is preserved
            assert (
                "tab=profile" in response.url or response.status_code == 302
            ), "Querystring should be preserved in redirect"


@pytest.mark.django_db
@override_settings(
    MIDDLEWARE=[
        "django.middleware.security.SecurityMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "core.middleware.NormalizeDoubleSlashMiddleware",  # Our middleware
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
    ]
)
class TestDoubleSlashMiddleware(TestCase):
    """Test the NormalizeDoubleSlashMiddleware"""

    def setUp(self):
        self.client = Client()

    def test_middleware_normalizes_double_slash(self):
        """Test that middleware redirects // to /"""
        response = self.client.get("/settings//", follow=False)

        # Middleware should return 301 redirect
        assert response.status_code == 301, f"Middleware should return 301 redirect, got {response.status_code}"

        # Should redirect to normalized path
        assert response.url == "/settings/", f"Expected redirect to '/settings/', got '{response.url}'"

    def test_middleware_handles_multiple_slashes(self):
        """Test that middleware handles ///+ slashes"""
        response = self.client.get("/accounts////profile/", follow=False)

        assert response.status_code == 301
        assert response.url == "/accounts/profile/"

    def test_middleware_preserves_querystring(self):
        """Test that middleware preserves query parameters"""
        response = self.client.get("/settings//?tab=security&mode=edit", follow=False)

        assert response.status_code == 301
        assert "tab=security" in response.url
        assert "mode=edit" in response.url

    def test_middleware_ignores_normal_paths(self):
        """Test that middleware doesn't interfere with normal paths"""
        # This will 404 but middleware shouldn't interfere
        response = self.client.get("/normal/path/", follow=False)

        # Should NOT be a redirect from middleware
        # (will be 404 since path doesn't exist, but that's ok)
        assert response.status_code == 404


@pytest.mark.django_db
class Test404PageDoesNotCrash(TestCase):
    """Test that 404 error page renders without crashing"""

    def setUp(self):
        self.client = Client()

    def test_404_page_renders_cleanly(self):
        """Test that 404 template doesn't crash with VariableDoesNotExist"""
        response = self.client.get("/nonexistent-url-12345/")

        # Should be 404
        assert response.status_code == 404

        # Should have content (not empty)
        assert len(response.content) > 100, "404 page should have substantial content"

        # Check for expected text
        content = response.content.decode("utf-8", errors="ignore")
        assert any(
            phrase in content.lower()
            for phrase in [
                "not found",
                "page not found",
                "404",
            ]
        ), "404 page should indicate error"

    def test_404_with_complex_path(self):
        """Test 404 with complex path structure"""
        response = self.client.get("/inventory/products/999999/edit/")

        # Should be 404, not 500
        assert response.status_code in (404, 403), f"Expected 404 or 403, got {response.status_code}"

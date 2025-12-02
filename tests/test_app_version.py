"""
Tests for app version functionality.
"""
import json
import pytest
from django.test import Client, RequestFactory, override_settings
from django.template import Context, Template
from cc.context_processors import app_version
from core.views_debug import app_version_view


@pytest.mark.django_db
class TestAppVersion:
    """Test app version functionality."""

    def test_version_context_processor(self):
        """Test that app_version context processor returns version."""
        factory = RequestFactory()
        request = factory.get("/")
        
        context = app_version(request)
        
        assert "APP_VERSION" in context
        assert context["APP_VERSION"]  # Should have a value

    @override_settings(APP_VERSION="9.9.9")
    def test_version_context_processor_custom_version(self):
        """Test context processor with custom version."""
        factory = RequestFactory()
        request = factory.get("/")
        
        context = app_version(request)
        
        assert context["APP_VERSION"] == "9.9.9"

    def test_version_api_endpoint(self):
        """Test that version API endpoint returns JSON with version."""
        client = Client()
        response = client.get("/api/version/")
        
        assert response.status_code == 200
        assert response["Content-Type"] == "application/json"
        
        data = response.json()
        assert "version" in data
        assert data["version"]  # Should have a value

    @override_settings(APP_VERSION="9.9.9")
    def test_version_api_endpoint_custom_version(self):
        """Test version API with custom version."""
        client = Client()
        response = client.get("/api/version/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "9.9.9"

    @override_settings(APP_VERSION="1.2.3")
    def test_version_in_rendered_template(self):
        """Test that APP_VERSION appears in rendered templates."""
        # Create a simple test template
        template = Template("Version: {{ APP_VERSION }}")
        
        factory = RequestFactory()
        request = factory.get("/")
        
        # Create context with our context processor
        context = Context(app_version(request))
        
        rendered = template.render(context)
        assert "1.2.3" in rendered

    def test_version_api_no_cache(self):
        """Test that version API can be called multiple times (no aggressive caching)."""
        client = Client()
        
        # Call twice to ensure it works consistently
        response1 = client.get("/api/version/")
        response2 = client.get("/api/version/")
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        data1 = response1.json()
        data2 = response2.json()
        
        assert data1["version"] == data2["version"]

    def test_version_view_function_directly(self):
        """Test app_version_view function directly."""
        factory = RequestFactory()
        request = factory.get("/api/version/")
        
        response = app_version_view(request)
        
        assert response.status_code == 200
        # Parse JSON from response content
        data = json.loads(response.content)
        assert "version" in data


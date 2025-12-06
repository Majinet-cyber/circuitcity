# tests/test_landing_page.py
"""
Tests for the landing page (home) improvements.

Ensures:
- Mission statement is present
- T.S. Eliot motto is present with correct attribution
- All primary CTAs use uniform blue button styling
- Page renders correctly
"""
import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_landing_page_renders(client):
    """Test that the landing page renders successfully."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    assert "Emajinet" in response.content.decode()


def test_landing_page_contains_mission_statement(client):
    """Test that the landing page contains the mission statement."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for mission section heading
    assert "Our Mission" in content
    
    # Check for mission statement text
    assert "Spotify of every small business" in content or "sportify of every small business" in content.lower()
    assert "replacing hardcovers" in content.lower()
    assert "AI MBA manager" in content


def test_landing_page_contains_ts_eliot_motto(client):
    """Test that the landing page contains the T.S. Eliot motto."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for the quote
    assert "We shall not cease from exploration" in content
    assert "And the end of all our exploring" in content
    assert "Will be to arrive where we started" in content
    assert "And know the place for the first time" in content
    
    # Check for attribution
    assert "T.S. Eliot" in content
    assert "Four Quartets" in content


def test_landing_page_buttons_use_uniform_blue_class(client):
    """
    Test that main CTAs use consistent blue button styling.
    
    All primary action buttons should use btn-primary class.
    """
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check that btn-primary class is used for main CTAs
    assert 'class="btn btn-primary"' in content
    
    # Count occurrences of primary buttons (should be at least 2)
    primary_button_count = content.count('btn btn-primary')
    assert primary_button_count >= 2, f"Expected at least 2 primary buttons, found {primary_button_count}"
    
    # Verify that "Get Started" buttons use btn-primary
    assert 'Get Started' in content
    # Find Get Started buttons and verify they use btn-primary
    get_started_sections = content.split('Get Started')
    for i, section in enumerate(get_started_sections[:-1]):  # All but the last split
        # Look backwards from "Get Started" to find the button class
        last_500_chars = section[-500:] if len(section) > 500 else section
        assert 'btn-primary' in last_500_chars or 'btn btn-primary' in last_500_chars, \
            f"Get Started button {i+1} does not use btn-primary class"


def test_landing_page_has_consistent_color_scheme(client):
    """Test that the landing page uses a consistent blue color scheme."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for primary color definition (should be blue)
    assert '--primary: #4f46e5' in content or 'var(--primary)' in content
    
    # Verify blue is used in gradients and highlights
    assert '#4f46e5' in content or '79, 70, 229' in content  # RGB of primary blue


def test_landing_page_sections_are_present(client):
    """Test that all major sections are present on the landing page."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for major sections
    assert "How It Works" in content
    assert "Powerful Features" in content or "Features" in content
    assert "Our Mission" in content
    
    # Check for hero section content
    assert "Doing business" in content
    assert "shouldn't be a headache" in content or "shouldn't be a headache" in content.lower()


def test_landing_page_has_navigation(client):
    """Test that the landing page has proper navigation."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for navigation elements
    assert "Login" in content
    assert "Get Started" in content
    assert "About" in content or "How It Works" in content


def test_landing_page_cta_links_work(client):
    """Test that CTA links on the landing page are valid."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check that login links exist
    assert '/login/' in content or 'login' in content.lower()
    
    # Check that internal anchors exist for smooth scrolling
    assert '#how-it-works' in content or 'how-it-works' in content


def test_landing_page_is_mobile_responsive(client):
    """Test that the landing page has responsive design elements."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for viewport meta tag
    assert 'viewport' in content.lower()
    assert 'width=device-width' in content.lower()
    
    # Check for responsive CSS (media queries)
    assert '@media' in content.lower()
    assert 'max-width' in content.lower() or 'min-width' in content.lower()


def test_landing_page_has_premium_styling(client):
    """Test that the landing page has premium styling elements."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for premium styling elements
    assert 'box-shadow' in content.lower() or 'shadow' in content.lower()
    assert 'border-radius' in content.lower() or 'rounded' in content.lower()
    assert 'gradient' in content.lower()
    
    # Check for glassmorphic/modern effects
    assert 'backdrop-filter' in content.lower() or 'blur' in content.lower()


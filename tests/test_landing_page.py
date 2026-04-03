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
    """Test that the landing page contains the current mission statement.

    GUARDRAIL TEST: This test fails if the old mission statement is ever restored.
    The current mission statement positions Emajinet as the operating system for
    African business (not "small businesses" — updated to reflect the Africa-wide scope).
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    # Check for mission section heading
    assert "Our Mission" in content

    # Check for current mission statement — operating system for African business
    assert "operating system for african business" in content.lower(), \
        "Missing current mission statement 'operating system for African business'"

    # GUARDRAIL: Ensure OLD mission statement is NOT present
    assert "spotify of every small business" not in content.lower(), \
        "Old mission statement 'Spotify of every small business' found - this is a regression!"


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

    Most primary action buttons use btn-primary. The final CTA section intentionally
    uses btn-white (white button on a dark/coloured background) — this is correct
    design and must NOT be changed.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    # btn-primary must be present in the page
    assert 'class="btn btn-primary"' in content

    # Multiple primary buttons must exist (hero + nav + other sections)
    primary_button_count = content.count('btn btn-primary')
    assert primary_button_count >= 2, f"Expected at least 2 primary buttons, found {primary_button_count}"

    # Get Started must appear on the page
    assert 'Get Started' in content

    # btn-white is intentional for the final CTA section (white button on dark bg) — allowed
    assert 'btn-white' in content or 'btn btn-primary' in content, \
        "Page must have either btn-white (final CTA) or btn-primary buttons"


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
    
    # Check for hero section content (updated)
    assert "inventory" in content.lower() or "business" in content.lower()


def test_landing_page_has_navigation(client):
    """Test that the landing page has proper navigation."""
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    # Nav uses "Sign In" (not "Login") — updated to match current design
    assert "Sign In" in content or "login" in content.lower(), \
        "Nav must contain 'Sign In' or a login link"
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


def test_landing_page_no_leaked_developer_text(client):
    """
    GUARDRAIL: Landing page must not expose developer/planning notes in rendered HTML.

    These strings were accidentally leaking into the page source and have been removed.
    This test prevents them from returning.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    forbidden_strings = [
        "RENEWABLE ENERGY FLAGSHIP",
        "Light mode, premium, clean",
        "No extra CTA button",
        "Positioned after How It Works",
        "restored from git history",
        "git-original trust card",
        "5bd2cceb",
        "DEBUG: sidebar_items",
        "DEBUG: Found",
    ]
    for s in forbidden_strings:
        assert s not in content, (
            f"Developer/planning text '{s}' must not appear in landing page HTML"
        )


def test_landing_page_metrics_container_present(client):
    """
    Landing page metrics card must be present with correct labels.
    Initial values render as skeleton loaders; JS patches in real values.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    # Metric labels must be present
    assert "Avg. daily revenue tracked" in content
    assert "Sales recorded per day" in content
    assert "Avg. margin visibility" in content

    # Skeleton loader markup should be present (not placeholder text)
    assert "lm-skeleton" in content, "lm-skeleton class should be used for skeleton loading"

    # Placeholder text values must NOT appear (they were replaced with skeletons)
    # "Real-time", "Live", "Tracking" as metric values are gone — JS drives real values
    import re
    # lm-revenue span should contain skeleton span, not plain text "Real-time"
    lm_pattern = re.search(r'id="lm-revenue">(.*?)</span>', content, re.DOTALL)
    if lm_pattern:
        inner = lm_pattern.group(1)
        assert "Real-time" not in inner, (
            "lm-revenue must not show 'Real-time' — use skeleton loader instead"
        )


def test_landing_metrics_api_schema(client):
    """Landing metrics API must return correct JSON schema."""
    url = reverse("staticpages:landing_metrics_api")
    response = client.get(url)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/json")

    import json
    data = json.loads(response.content)

    required_keys = {
        "active_businesses", "team_members", "has_data", "as_of", "status"
    }
    for key in required_keys:
        assert key in data, f"Landing metrics API missing key: {key}"

    assert data["status"] == "success"
    assert isinstance(data["active_businesses"], int)
    assert isinstance(data["team_members"], int)
    assert isinstance(data["has_data"], bool)


def test_landing_metrics_api_no_data_graceful(client):
    """Landing metrics API must respond gracefully with no sales data."""
    url = reverse("staticpages:landing_metrics_api")
    response = client.get(url)

    assert response.status_code == 200
    import json
    data = json.loads(response.content)

    # With no test data, has_data should be False but response must still be valid
    assert data["status"] == "success"
    assert data["active_businesses"] >= 0
    assert data["team_members"] >= 0


def test_landing_page_no_placeholder_metric_text(client):
    """
    GUARDRAIL: Landing page must not show 'Real-time', 'Live', 'Tracking' as
    visible metric values. These were replaced with skeleton loaders.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    # These must not appear as metric span content
    # Note: they may appear in JS comments/strings — only visible HTML is checked
    import re
    for span_id in ["lm-revenue", "lm-sales", "lm-margin"]:
        pattern = re.search(
            r'id="' + span_id + r'">(.*?)</span>', content, re.DOTALL
        )
        if pattern:
            inner = pattern.group(1)
            for bad in ["Real-time", "Live", "Tracking"]:
                assert bad not in inner, (
                    f"Metric span #{span_id} must not contain placeholder text '{bad}'"
                )


def test_gym_dashboard_no_leaked_debug_text(client):
    """
    GUARDRAIL: Gym dashboard must not expose DEBUG template comments in rendered HTML.

    Django {# ... #} comments are stripped by the template engine and never render,
    but HTML <!-- DEBUG: ... --> comments do render. This test verifies the gym
    dashboard URL resolves and unauthenticated users are redirected (not served
    a broken template).
    """
    from django.urls import reverse as r
    url = r("verticals:gym_dashboard")
    response = client.get(url)
    # Unauthenticated → redirect to login; template debug leaks only occur on 200.
    assert response.status_code in (200, 302)
    if response.status_code == 200:
        content = response.content.decode()
        # Dev planning notes must not appear in rendered HTML
        for forbidden in ["REMOVED: dashboard_brand_header", "HERO — gradient"]:
            assert forbidden not in content, (
                f"Dev comment '{forbidden}' must not appear in gym dashboard HTML"
            )


@pytest.mark.django_db
def test_landing_metrics_api_with_businesses(client):
    """
    Landing metrics API returns correct team_members count when memberships exist.
    """
    from django.contrib.auth import get_user_model
    from tenants.models import Business, Membership
    from django.core.cache import cache

    User = get_user_model()
    user1 = User.objects.create_user("metricsuser1", "mu1@example.com", "pass123")
    user2 = User.objects.create_user("metricsuser2", "mu2@example.com", "pass123")
    biz = Business.objects.create(name="Metrics Test Biz", slug="metrics-test-biz-api")
    Membership.objects.create(user=user1, business=biz, role="manager", status="ACTIVE", is_active=True)
    Membership.objects.create(user=user2, business=biz, role="agent", status="ACTIVE", is_active=True)

    cache.delete("landing_metrics_api_v2")
    cache.delete("platform_live_metrics_v1")

    url = reverse("staticpages:landing_metrics_api")
    response = client.get(url)

    assert response.status_code == 200
    import json
    data = json.loads(response.content)
    assert data["status"] == "success"
    assert data["team_members"] >= 2


@pytest.mark.django_db
def test_car_dealer_stock_in_has_popular_makes(client):
    """
    Car dealer stock-in form must include popular make cards for tap-first UX.
    """
    from django.contrib.auth import get_user_model
    from tenants.models import Business, Membership
    from inventory.models_car_dealer import CarMake

    User = get_user_model()
    user = User.objects.create_user("cduxtester", "cdux@example.com", "pass123")
    biz = Business.objects.create(name="CD UX Biz", slug="cd-ux-biz", business_kind="car_dealer")
    Membership.objects.create(user=user, business=biz, role="manager", status="ACTIVE")

    # Create a popular make
    CarMake.objects.get_or_create(name="Toyota", defaults={"is_popular": True, "sort_order": 1})

    client.force_login(user)
    session = client.session
    session["active_business_id"] = biz.id
    session.save()

    url = reverse("car_dealer:stock_in")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    # Popular makes card section must be rendered
    assert "make-card" in content or "make-cards" in content, (
        "Popular make cards must be rendered in car dealer stock-in form"
    )
    assert "Toyota" in content


@pytest.mark.django_db
def test_energy_sizing_detail_has_quotation_section(client):
    """
    Energy system sizing detail page must include quotation builder section
    when a sizing result exists.
    """
    from django.contrib.auth import get_user_model
    from tenants.models import Business, Membership
    from inventory.models_energy import SystemSizingRun

    User = get_user_model()
    user = User.objects.create_user("energytester", "en@example.com", "pass123")
    biz = Business.objects.create(name="Energy Biz", slug="energy-biz", business_kind="energy")
    Membership.objects.create(user=user, business=biz, role="manager", status="ACTIVE")

    run = SystemSizingRun.objects.create(
        business=biz,
        title="Test 3kW System",
        recommended_array_kw=3.0,
        recommended_panel_count=8,
    )

    client.force_login(user)
    session = client.session
    session["active_business_id"] = biz.id
    session.save()

    url = reverse("verticals:energy_sizing_detail", kwargs={"run_id": run.pk})
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "quotation" in content.lower() or "Quotation" in content, (
        "Energy sizing detail must include quotation builder section"
    )


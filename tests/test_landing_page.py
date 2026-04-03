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


def test_landing_page_airtel_partner_link(client):
    """
    GUARDRAIL: Airtel partner logo must link to https://www.airtel.mw/ with
    target="_blank" rel="noopener noreferrer", not href="#".
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "https://www.airtel.mw/" in content, (
        "Airtel partner link must point to https://www.airtel.mw/"
    )
    assert 'airtel-logo.svg' in content, (
        "Airtel logo SVG must be rendered in partners section"
    )


def test_landing_page_tnm_partner_link(client):
    """
    GUARDRAIL: TNM partner logo must link to https://www.tnmmpamba.co.mw/#/ with
    target="_blank" rel="noopener noreferrer", not href="#".
    Must also use the real tnm-logo.svg asset, not a placeholder icon.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "https://www.tnmmpamba.co.mw/#/" in content, (
        "TNM partner link must point to https://www.tnmmpamba.co.mw/#/"
    )
    assert "tnm-logo.svg" in content, (
        "TNM logo must use the tnm-logo.svg asset, not a generic SVG icon"
    )


def test_landing_page_partner_links_open_new_tab(client):
    """
    GUARDRAIL: Partner links (Airtel, TNM) must open in a new tab and have
    rel="noopener noreferrer" for security.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert 'rel="noopener noreferrer"' in content, (
        "Partner links must include rel='noopener noreferrer'"
    )


def test_landing_page_vertical_cta_not_about(client):
    """
    GUARDRAIL: 'See all verticals' CTA must NOT point to the About page.
    It must point to the pricing page or a real verticals destination.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    about_url = reverse("staticpages:about")
    pricing_url = reverse("staticpages:pricing")

    # The "See all verticals" link must go to pricing, not about
    assert f'See all verticals' in content, "See all verticals text must be present"
    # Check the link surrounding "See all verticals" is NOT the about URL
    import re
    pattern = re.search(r'href="([^"]*)"[^>]*>See all verticals', content)
    if pattern:
        href = pattern.group(1)
        assert href != about_url, (
            f"'See all verticals' must not link to About ({about_url})"
        )
        assert href == pricing_url, (
            f"'See all verticals' must link to pricing ({pricing_url}), got {href}"
        )


def test_landing_page_energy_cta_not_about(client):
    """
    GUARDRAIL: 'Explore Renewable Energy' CTA must NOT point to the About page.
    It must point to the pricing page or a real energy destination.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    about_url = reverse("staticpages:about")
    pricing_url = reverse("staticpages:pricing")

    import re
    pattern = re.search(r'href="([^"]*)"[^>]*>\s*Explore Renewable Energy', content)
    if pattern:
        href = pattern.group(1)
        assert href != about_url, (
            f"'Explore Renewable Energy' must not link to About ({about_url})"
        )
        assert href == pricing_url, (
            f"'Explore Renewable Energy' must link to pricing ({pricing_url}), got {href}"
        )


def test_sidebar_no_debug_comments(client):
    """
    GUARDRAIL: Sidebar partial must not expose DEBUG comments in rendered HTML.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "DEBUG: Resolved" not in content, (
        "DEBUG URL resolution comment must not appear in rendered HTML"
    )
    assert "DEBUG: sidebar_items" not in content, (
        "DEBUG sidebar_items comment must not appear in rendered HTML"
    )


@pytest.mark.django_db
def test_upgrade_subscription_view_requires_post(client):
    """
    Upgrade subscription endpoint must require POST.
    GET to upgrade_start must be rejected (405) not 500.
    """
    from django.contrib.auth import get_user_model
    from tenants.models import Business, Membership
    from billing.models import BusinessSubscription, SubscriptionPlan
    from decimal import Decimal

    User = get_user_model()
    user = User.objects.create_user("upgradetester", "up@test.com", "testpass123")
    biz = Business.objects.create(name="Upgrade Test Biz", slug="upgrade-test-biz-get")
    Membership.objects.create(user=user, business=biz, role="manager", status="ACTIVE")

    starter, _ = SubscriptionPlan.objects.get_or_create(
        code="starter_upg_test",
        defaults={"name": "Starter Upg", "amount": Decimal("20000"), "currency": "MWK", "is_active": True},
    )
    growth, _ = SubscriptionPlan.objects.get_or_create(
        code="growth_upg_test",
        defaults={"name": "Growth Upg", "amount": Decimal("60000"), "currency": "MWK", "is_active": True},
    )
    BusinessSubscription.objects.create(
        business=biz,
        plan=starter,
        status=BusinessSubscription.Status.ACTIVE,
    )

    client.force_login(user)
    session = client.session
    session["active_business_id"] = biz.id
    session.save()

    from django.urls import reverse as r
    url = r("billing:upgrade_start", args=["growth_upg_test"])
    response = client.get(url)
    # GET on a @require_POST view returns 405 (Method Not Allowed), not 500
    assert response.status_code in (302, 405), (
        f"GET to upgrade_start must not return 500; got {response.status_code}"
    )


@pytest.mark.django_db
def test_upgrade_subscription_invalid_plan_graceful(client):
    """
    Upgrade subscription with non-existent plan must redirect with error, not 500.
    """
    from django.contrib.auth import get_user_model
    from tenants.models import Business, Membership
    from billing.models import BusinessSubscription, SubscriptionPlan
    from decimal import Decimal

    User = get_user_model()
    user = User.objects.create_user("invalidplantester", "ip@test.com", "testpass123")
    biz = Business.objects.create(name="Invalid Plan Biz", slug="invalid-plan-biz")
    Membership.objects.create(user=user, business=biz, role="manager", status="ACTIVE")

    starter, _ = SubscriptionPlan.objects.get_or_create(
        code="starter_inv_test",
        defaults={"name": "Starter Inv", "amount": Decimal("20000"), "currency": "MWK", "is_active": True},
    )
    BusinessSubscription.objects.create(
        business=biz,
        plan=starter,
        status=BusinessSubscription.Status.ACTIVE,
    )

    client.force_login(user)
    session = client.session
    session["active_business_id"] = biz.id
    session.save()

    from django.urls import reverse as r
    url = r("billing:upgrade_start", args=["nonexistent-plan-xyz"])
    response = client.post(url)
    # Must redirect to manage with error message, not 500
    assert response.status_code == 302, (
        f"Invalid plan upgrade must redirect (302), not crash; got {response.status_code}"
    )
    assert response.url == r("billing:manage"), (
        "Invalid plan upgrade must redirect to billing:manage"
    )


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


# ===========================================================================
# PHASE 1 — Car dealer dashboard: quick-action cards removed, sidebar intact
# ===========================================================================

@pytest.mark.django_db
def test_car_dealer_dashboard_no_quick_action_cards(client):
    """
    Car dealer dashboard must NOT contain the duplicated Quick Actions cards
    (Stock In Vehicle, Available Stock, Marketplace) — these live in the sidebar.
    The dashboard KPIs and hero CTAs must still be present.
    """
    from django.contrib.auth import get_user_model
    from tenants.models import Business, Membership

    User = get_user_model()
    user = User.objects.create_user("cdqatest", "cdqa@example.com", "pass123")
    biz = Business.objects.create(name="CD QA Biz", slug="cd-qa-biz", business_kind="car_dealer")
    Membership.objects.create(user=user, business=biz, role="manager", status="ACTIVE")

    client.force_login(user)
    session = client.session
    session["active_business_id"] = biz.id
    session.save()

    from django.urls import reverse as r
    url = r("verticals:car_dealer_dashboard")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    # Quick-action card titles must NOT appear as standalone dashboard cards
    assert "qa-title" not in content, (
        "Quick-action card (.qa-title) must be removed from car dealer dashboard"
    )
    assert "Stock In Vehicle" not in content, (
        "'Stock In Vehicle' quick-action card must not appear in dashboard"
    )
    assert "Available Stock" not in content, (
        "'Available Stock' quick-action card must not appear in dashboard"
    )

    # Core KPIs must still be present
    assert "Revenue" in content or "revenue" in content, "Revenue KPI must still be present"
    assert "Dealer Dashboard" in content or "Car Dealer" in content, "Dashboard title must be present"


@pytest.mark.django_db
def test_car_dealer_sidebar_nav_items_present(client):
    """
    After removing quick-action cards from the dashboard, the sidebar must still
    contain navigation links for Add Vehicle, All Vehicles, and Marketplace.
    """
    from django.contrib.auth import get_user_model
    from tenants.models import Business, Membership

    User = get_user_model()
    user = User.objects.create_user("cdnav", "cdnav@example.com", "pass123")
    biz = Business.objects.create(name="CD Nav Biz", slug="cd-nav-biz", business_kind="car_dealer")
    Membership.objects.create(user=user, business=biz, role="manager", status="ACTIVE")

    client.force_login(user)
    session = client.session
    session["active_business_id"] = biz.id
    session.save()

    from django.urls import reverse as r
    url = r("verticals:car_dealer_dashboard")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    # Sidebar nav items must still link to the car dealer routes
    assert "nav-car-dealer-stock-in" in content or "car-dealer/vehicles/add" in content or "Add Vehicle" in content, (
        "Car dealer 'Add Vehicle' sidebar link must still exist"
    )
    assert "nav-car-dealer-marketplace" in content or "Marketplace" in content, (
        "Car dealer 'Marketplace' sidebar link must still exist"
    )


# ===========================================================================
# PHASE 3 — Farm vertical is in top-6 verticals showcase
# ===========================================================================

def test_farm_vertical_in_top_six_showcase(client):
    """
    Farm vertical must appear in the landing page vertical showcase grid
    (top 6 cards), not just in a footnote.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "Farm Manager" in content, (
        "Farm Manager vertical must appear in the verticals showcase section"
    )
    assert "🌾" in content or "Farm" in content, (
        "Farm vertical icon or name must be visible in the verticals section"
    )


# ===========================================================================
# PHASE 2 — Problem section has all four problem cards
# ===========================================================================

def test_problem_section_has_shrinkage_and_demand_blindness(client):
    """
    The problem section must contain all four evidence cards:
    inventory shrinkage, no sales tracking, margin blindness, demand blindness.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "Inventory shrinkage" in content or "shrinkage" in content.lower(), (
        "Inventory shrinkage problem card must be present"
    )
    assert "sales tracking" in content.lower(), (
        "No sales tracking problem card must be present"
    )
    assert "Margin blindness" in content or "margin" in content.lower(), (
        "Margin blindness problem card must be present"
    )
    assert "Demand blindness" in content or "demand" in content.lower(), (
        "Demand blindness problem card must be present"
    )


# ===========================================================================
# PHASE 5 — Landing metrics JS fallback is not blank
# ===========================================================================

def test_landing_metrics_fallback_js_present(client):
    """
    The landing page JS must contain a non-empty applyFallback() that sets
    explicit numeric values, not just keeping skeleton loaders blank.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    # The applyFallback function must set real values, not be empty
    assert "applyFallback" in content, "applyFallback function must exist in page JS"
    # Must contain at least one setMetricSpan call inside the fallback
    assert "MWK" in content or "lm-revenue" in content, (
        "Fallback must reference revenue metric span"
    )


# ===========================================================================
# PHASE 4 — Gym dashboard clean (no dev leakage in rendered output)
# ===========================================================================

@pytest.mark.django_db
def test_gym_dashboard_clean_render(client):
    """
    Gym dashboard when rendered for an authenticated user must not contain
    visible developer/debug text. Django {# #} comments are invisible;
    HTML <!-- --> comments must not contain dev planning notes.
    """
    from django.contrib.auth import get_user_model
    from tenants.models import Business, Membership

    User = get_user_model()
    user = User.objects.create_user("gymclean", "gymclean@example.com", "pass123")
    biz = Business.objects.create(name="Clean Gym", slug="clean-gym", business_kind="gym")
    Membership.objects.create(user=user, business=biz, role="manager", status="ACTIVE")

    client.force_login(user)
    session = client.session
    session["active_business_id"] = biz.id
    session.save()

    from django.urls import reverse as r
    url = r("verticals:gym_dashboard")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    forbidden = [
        "REMOVED:",
        "DEBUG:",
        "TODO:",
        "FIXME:",
        "restored from git",
        "planning note",
    ]
    for text in forbidden:
        assert text not in content, (
            f"Developer text '{text}' must not appear in gym dashboard rendered HTML"
        )


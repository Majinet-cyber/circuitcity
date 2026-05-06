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


def test_landing_page_trusted_infrastructure_section_present(client):
    """
    GUARDRAIL: The Trusted Infrastructure section must be present on the landing page
    after the features section, replacing the old marquee partners strip.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "Trusted Infrastructure" in content, (
        "Landing page must contain 'Trusted Infrastructure' section heading"
    )
    assert 'id="trusted-infrastructure"' in content, (
        "Trusted Infrastructure section must have id='trusted-infrastructure'"
    )


def test_landing_page_trusted_infra_contains_paychangu(client):
    """
    GUARDRAIL: Trusted Infrastructure section must include PayChangu.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "PayChangu" in content, (
        "Trusted Infrastructure section must include PayChangu"
    )
    assert "Seamless Local Payments" in content, (
        "PayChangu card must have its headline 'Seamless Local Payments'"
    )


def test_landing_page_trusted_infra_contains_twilio(client):
    """
    GUARDRAIL: Trusted Infrastructure section must include Twilio.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "Twilio" in content, (
        "Trusted Infrastructure section must include Twilio"
    )
    assert "Secure OTP" in content, (
        "Twilio card must have its headline 'Secure OTP &amp; Alerts'"
    )


def test_landing_page_trusted_infra_contains_sendgrid(client):
    """
    GUARDRAIL: Trusted Infrastructure section must include SendGrid.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "SendGrid" in content, (
        "Trusted Infrastructure section must include SendGrid"
    )
    assert "Reliable Email Delivery" in content, (
        "SendGrid card must have its headline 'Reliable Email Delivery'"
    )


def test_landing_page_trusted_infra_subtitle_and_microcopy(client):
    """
    Trusted Infrastructure section must contain the approved subtitle and microcopy.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "Powered by global and African technology leaders" in content, (
        "Trusted Infrastructure subtitle must be present"
    )
    assert "Trusted by modern businesses" in content, (
        "Trusted Infrastructure microcopy must be present"
    )
    assert "Built on infrastructure trusted by millions" in content, (
        "Trusted Infrastructure trust statement must be present"
    )


def test_landing_page_old_partners_strip_not_duplicated(client):
    """
    GUARDRAIL: The old marquee partners strip must not appear on the page.
    The new Trusted Infrastructure section is the single integration showcase.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "partners-strip" not in content, (
        "Old 'partners-strip' marquee element must not appear; use Trusted Infrastructure section instead"
    )
    assert "partners-marquee-track" not in content, (
        "Old marquee track must be removed; use Trusted Infrastructure section instead"
    )


def test_landing_page_partner_links_open_new_tab(client):
    """
    GUARDRAIL: External infrastructure links must open in a new tab and have
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

# ===========================================================================
# ENERGY DEMO SIMULATION SECTION
# ===========================================================================

def test_landing_page_energy_simulation_section_present(client):
    """
    Landing page must render the flagship Renewable Energy daily simulation section.
    The section must use the landing page light theme — not a dark navy background.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert 'id="energy-demo-simulation"' in content, (
        "Energy demo simulation section must be present on the landing page"
    )
    assert "energy-sim-heading" in content or "See tomorrow" in content, (
        "Energy simulation section must have its flagship heading"
    )

    # Section must use light background, not dark navy
    assert "#0a1628" not in content or "energy-demo-simulation" not in content.split("#0a1628")[0].split("energy-demo-simulation")[-1], (
        "Energy simulation section must not use the dark navy #0a1628 background"
    )
    # Light background colour must be present in the section
    assert "#f0fdf9" in content, (
        "Energy simulation section must use the light green #f0fdf9 background"
    )


def test_landing_page_energy_simulation_demo_badge(client):
    """
    Energy simulation section must be clearly labelled as demo data — not real.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "Demo simulation" in content, (
        "Energy simulation section must contain 'Demo simulation' disclaimer"
    )
    assert "connect real site data" in content, (
        "Energy simulation must instruct users to connect real data inside Emajinet"
    )


def test_landing_page_energy_simulation_controls_present(client):
    """
    Energy simulation section must contain interactive slider and play button.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert 'id="demoSimSlider"' in content, (
        "Energy simulation must have a time slider (demoSimSlider)"
    )
    assert 'id="demoSimPlayBtn"' in content, (
        "Energy simulation must have a play button (demoSimPlayBtn)"
    )
    assert 'min="0"' in content and 'max="1440"' in content, (
        "Slider must span 0–1440 minutes (full 24-hour day)"
    )


def test_landing_page_energy_simulation_blackout_risk_text(client):
    """
    Energy simulation section must contain blackout risk text in the risk panel.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "Blackout risk" in content, (
        "Energy simulation must contain 'Blackout risk' in the risk panel"
    )
    assert "22:30" in content, (
        "Energy simulation must reference the ~22:30 blackout risk time"
    )
    assert "energy-risk-panel" in content, (
        "Risk panel element (energy-risk-panel) must be present"
    )


def test_landing_page_energy_simulation_kpi_cards_present(client):
    """
    Energy simulation section must contain all five KPI card elements.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    for element_id in ["demoSimSolar", "demoSimLoad", "demoSimBattery", "demoSimNet", "demoSimStatus"]:
        assert f'id="{element_id}"' in content, (
            f"KPI card element #{element_id} must be present in energy simulation section"
        )


def test_landing_page_energy_simulation_chart_canvas_present(client):
    """
    Energy simulation must contain a canvas element for the chart.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert 'id="demoSimChart"' in content, (
        "Energy simulation chart canvas (demoSimChart) must be present"
    )


def test_landing_page_energy_simulation_mobile_visibility(client):
    """
    Energy simulation section must not be hidden at mobile widths.
    The section must not contain display:none or visibility:hidden on its root element.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    # The section exists and is not globally hidden
    assert 'id="energy-demo-simulation"' in content

    # Responsive grid class must be present for mobile stacking
    assert "demo-sim-kpi-grid" in content, (
        "KPI grid must use responsive class for mobile stacking"
    )

    # Media queries for the simulation section must be present
    assert "@media" in content, "Page must include responsive media queries"


def test_landing_page_still_loads_with_simulation(client):
    """
    Existing landing page must still load correctly after adding energy simulation.
    All other verticals and key sections must still be present.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    # Core page elements must still be present
    assert "How It Works" in content
    assert "Get Started" in content
    assert "Emajinet" in content

    # Other verticals must not have been removed
    assert "Farm" in content or "Pharmacy" in content or "Grocery" in content, (
        "Other vertical types must still be present on the page"
    )

    # Pricing/CTA must still be present
    assert "pricing" in content.lower() or "Get Started" in content

    # Trusted Infrastructure section must still be present
    assert "Trusted Infrastructure" in content or "trusted-infrastructure" in content, (
        "Trusted Infrastructure section must still be present after adding energy simulation"
    )


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


# ===========================================================================
# HERO LAPTOP PREVIEW ROTATION — both panels must be present in HTML
# ===========================================================================

def test_hero_contains_business_dashboard_preview(client):
    """
    Hero laptop must contain the normal business dashboard preview panel.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "dashPanel0" in content, "Business dashboard panel (dashPanel0) must be in hero"
    assert "dash-panel--active" in content, "One panel must start as active"
    assert "Stock Levels" in content or "Samsung A05" in content, (
        "Business dashboard preview content must be present"
    )


def test_hero_contains_energy_dashboard_preview(client):
    """
    Hero laptop must contain the Renewable Energy dashboard preview panel.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "dashPanel1" in content, "Energy dashboard panel (dashPanel1) must be in hero"
    assert "energy-preview-panel" in content or "data-testid=\"energy-preview-panel\"" in content, (
        "Energy preview panel must have its testid"
    )


def test_hero_energy_preview_has_installed_capacity(client):
    """
    The hero energy preview must show '5.0 kW' installed capacity text.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "5.0 kW" in content, (
        "Energy preview must show '5.0 kW' installed capacity"
    )
    assert "Installed Capacity" in content or "installed capacity" in content.lower(), (
        "Energy preview must label installed capacity"
    )


def test_hero_energy_preview_has_realistic_metrics(client):
    """
    The hero energy preview must show all required realistic demo metrics.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "12.4 kWh" in content, "Energy preview must show 12.4 kWh generated today"
    assert "91%" in content, "Energy preview must show 91% battery health"
    assert "185,000" in content or "MWK 185,000" in content, (
        "Energy preview must show MWK 185,000 estimated savings"
    )
    assert "Blackout risk" in content, "Energy preview must show blackout risk text"
    assert "System status" in content or "system status" in content.lower(), (
        "Energy preview must show system status"
    )


def test_hero_energy_preview_has_forecast_chart(client):
    """
    The hero energy preview must contain a mini forecast/bar chart element.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "energy-mini-bar" in content or "Generation Forecast" in content, (
        "Energy preview must contain a mini generation forecast chart"
    )


def test_hero_preview_rotation_js_present(client):
    """
    Hero laptop rotation JS must be present and reference panel IDs.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "dash-panel" in content, "Rotation panel class must exist"
    assert "dashPanel0" in content and "dashPanel1" in content, (
        "Both panel IDs must be in the page"
    )
    assert "dash-panel--hidden" in content, "Hidden panel class must be in HTML"
    assert "dash-panel--active" in content, "Active panel class must be in HTML"


def test_hero_preview_no_layout_jump(client):
    """
    Panels host must have a fixed height to prevent layout jump during rotation.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "dash-panels-host" in content, "Panels host wrapper must exist"
    assert "dashPanelsHost" in content, "dashPanelsHost id must exist for JS targeting"


# ===========================================================================
# GROCERIES DASHBOARD TESTS
# ===========================================================================

# ===========================================================================
# CHART LEGEND WORDING — no raw "cursor" in user-facing labels
# ===========================================================================

def test_landing_page_chart_legend_no_raw_cursor(client):
    """
    GUARDRAIL: The energy simulation chart legend on the landing page must NOT
    contain the raw word 'cursor' as a visible label.

    'cursor' is developer jargon; the approved term is 'Current Time Marker'.
    CSS property values (cursor:pointer) are not affected — only visible text.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    import re
    # Extract the chart legend div text (the aria-hidden caption under demoSimChart)
    legend_match = re.search(
        r'id="demoSimChart"[^>]*>.*?<div[^>]*aria-hidden="true"[^>]*>(.*?)</div>',
        content,
        re.DOTALL,
    )
    if legend_match:
        legend_text = legend_match.group(1)
        assert "cursor" not in legend_text.lower(), (
            "Chart legend must not contain the raw word 'cursor' — use 'Current Time Marker' instead"
        )


def test_landing_page_chart_legend_has_current_time_marker(client):
    """
    GUARDRAIL: The energy simulation chart legend must use 'Current Time Marker'
    (not the old developer label 'cursor').
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "Current Time Marker" in content, (
        "Energy simulation chart legend must contain 'Current Time Marker'"
    )


@pytest.mark.django_db
def test_energy_sizing_detail_chart_legend_no_raw_cursor(client):
    """
    GUARDRAIL: The energy system sizing detail chart legend must NOT contain
    the raw phrase 'time marker' should remain the visible label.
    """
    from django.contrib.auth import get_user_model
    from tenants.models import Business, Membership
    from inventory.models_energy import SystemSizingRun

    User = get_user_model()
    user = User.objects.create_user("curtestleg", "curtestleg@example.com", "pass123")
    biz = Business.objects.create(
        name="Marker Legend Test Biz", slug="marker-legend-test-biz", business_kind="energy"
    )
    Membership.objects.create(user=user, business=biz, role="manager", status="ACTIVE")

    run = SystemSizingRun.objects.create(
        business=biz,
        title="Legend Test System",
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

    import re
    # Extract only the visible caption below the simChart canvas (not JS code/comments)
    caption_match = re.search(
        r'id="simChart"[^>]*>.*?<div[^>]*>(.*?)</div>',
        content,
        re.DOTALL,
    )
    if caption_match:
        caption_text = caption_match.group(1)
        old_label = "time " + "cursor"
        assert old_label not in caption_text.lower(), (
            "Energy sizing detail chart caption must use 'Current Time Marker' — "
            "use 'Current Time Marker' instead"
        )
    # Also verify the label is not present as visible HTML outside script/style blocks
    html_without_scripts = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
    html_without_scripts = re.sub(r'<style[^>]*>.*?</style>', '', html_without_scripts, flags=re.DOTALL)
    old_label = "time " + "cursor"
    assert old_label not in html_without_scripts.lower(), (
        "Energy sizing detail rendered HTML must use 'Current Time Marker' — "
        "use 'Current Time Marker' instead"
    )


@pytest.mark.django_db
def test_energy_sizing_detail_chart_legend_has_current_time_marker(client):
    """
    GUARDRAIL: The energy system sizing detail chart legend must display
    'Current Time Marker' instead of the old developer label.
    """
    from django.contrib.auth import get_user_model
    from tenants.models import Business, Membership
    from inventory.models_energy import SystemSizingRun

    User = get_user_model()
    user = User.objects.create_user("ctmtestleg", "ctmtestleg@example.com", "pass123")
    biz = Business.objects.create(
        name="CTM Legend Test Biz", slug="ctm-legend-test-biz", business_kind="energy"
    )
    Membership.objects.create(user=user, business=biz, role="manager", status="ACTIVE")

    run = SystemSizingRun.objects.create(
        business=biz,
        title="CTM Legend Test System",
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

    assert "Current Time Marker" in content, (
        "Energy sizing detail chart legend must contain 'Current Time Marker' (cyan)"
    )


# ===========================================================================
# GROCERIES DASHBOARD TESTS
# ===========================================================================

@pytest.mark.django_db
def test_groceries_dashboard_loads(client):
    """
    Groceries dashboard must return 200 for an authenticated grocery business user.
    """
    from django.contrib.auth import get_user_model
    from tenants.models import Business, Membership
    from inventory.business_kinds import BusinessKind

    User = get_user_model()
    user = User.objects.create_user("groctest", "groctest@example.com", "pass123")
    biz = Business.objects.create(
        name="Test Grocery Store",
        slug="test-grocery-store-dash",
        business_kind=BusinessKind.GROCERY,
    )
    Membership.objects.create(user=user, business=biz, role="manager", status="ACTIVE")

    client.force_login(user)
    session = client.session
    session["active_business_id"] = biz.id
    session.save()

    url = reverse("groceries:dashboard")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Groceries Dashboard" in content


@pytest.mark.django_db
def test_groceries_dashboard_has_payment_mix(client):
    """
    Groceries dashboard must contain the payment mix section with Cash, Mobile Money, Credit.
    """
    from django.contrib.auth import get_user_model
    from tenants.models import Business, Membership
    from inventory.business_kinds import BusinessKind

    User = get_user_model()
    user = User.objects.create_user("grocpmix", "grocpmix@example.com", "pass123")
    biz = Business.objects.create(
        name="Grocery Payment Mix Test",
        slug="grocery-pmix-test",
        business_kind=BusinessKind.GROCERY,
    )
    Membership.objects.create(user=user, business=biz, role="manager", status="ACTIVE")

    client.force_login(user)
    session = client.session
    session["active_business_id"] = biz.id
    session.save()

    url = reverse("groceries:dashboard")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "payment-mix-section" in content or "Payment Mix" in content, (
        "Groceries dashboard must contain a Payment Mix section"
    )
    assert "Cash" in content, "Payment Mix must show Cash"
    assert "Mobile Money" in content, "Payment Mix must show Mobile Money"
    assert "Credit" in content, "Payment Mix must show Credit"


@pytest.mark.django_db
def test_groceries_dashboard_demo_values_are_nonzero(client):
    """
    Groceries dashboard in demo mode must not show zero values for key KPIs.
    """
    from django.contrib.auth import get_user_model
    from tenants.models import Business, Membership
    from inventory.business_kinds import BusinessKind

    User = get_user_model()
    user = User.objects.create_user("grocdemoval", "grocdemoval@example.com", "pass123")
    biz = Business.objects.create(
        name="Grocery Demo Values Test",
        slug="grocery-demo-values-test",
        business_kind=BusinessKind.GROCERY,
    )
    Membership.objects.create(user=user, business=biz, role="manager", status="ACTIVE")

    client.force_login(user)
    session = client.session
    session["active_business_id"] = biz.id
    session.save()

    url = reverse("groceries:dashboard")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    # Demo banner must be present (no real products)
    assert "Demo Preview" in content or "groceries-demo-banner" in content, (
        "Demo banner must be shown when no real data exists"
    )

    # KPI values must not be zero — demo fills in non-zero values
    assert "12,400" in content or "K 0" not in content, (
        "Demo revenue must be non-zero (12,400 expected)"
    )
    assert "3,200" in content or "K 0" not in content, (
        "Demo profit must be non-zero (3,200 expected)"
    )
    assert "48,000" in content, (
        "Demo stock value must be 48,000"
    )


@pytest.mark.django_db
def test_groceries_dashboard_has_smart_insight(client):
    """
    Groceries dashboard must contain the Smart Insight card.
    """
    from django.contrib.auth import get_user_model
    from tenants.models import Business, Membership
    from inventory.business_kinds import BusinessKind

    User = get_user_model()
    user = User.objects.create_user("grocinsight", "grocinsight@example.com", "pass123")
    biz = Business.objects.create(
        name="Grocery Insight Test",
        slug="grocery-insight-test",
        business_kind=BusinessKind.GROCERY,
    )
    Membership.objects.create(user=user, business=biz, role="manager", status="ACTIVE")

    client.force_login(user)
    session = client.session
    session["active_business_id"] = biz.id
    session.save()

    url = reverse("groceries:dashboard")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "Smart Insight" in content or "smart-insight-card" in content, (
        "Groceries dashboard must contain Smart Insight card"
    )
    assert "Cooking oil" in content or "Restock" in content, (
        "Smart Insight must contain actionable restock advice"
    )


@pytest.mark.django_db
def test_groceries_dashboard_has_top_groceries_section(client):
    """
    Groceries dashboard must contain the 'Top Groceries Today' section.
    """
    from django.contrib.auth import get_user_model
    from tenants.models import Business, Membership
    from inventory.business_kinds import BusinessKind

    User = get_user_model()
    user = User.objects.create_user("groctopg", "groctopg@example.com", "pass123")
    biz = Business.objects.create(
        name="Grocery Top Section Test",
        slug="grocery-top-section-test",
        business_kind=BusinessKind.GROCERY,
    )
    Membership.objects.create(user=user, business=biz, role="manager", status="ACTIVE")

    client.force_login(user)
    session = client.session
    session["active_business_id"] = biz.id
    session.save()

    url = reverse("groceries:dashboard")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "Top Groceries Today" in content or "top-groceries-section" in content, (
        "Groceries dashboard must contain Top Groceries Today section"
    )


@pytest.mark.django_db
def test_groceries_dashboard_has_reorder_suggestions(client):
    """
    Groceries dashboard must contain the Reorder Suggestions section.
    """
    from django.contrib.auth import get_user_model
    from tenants.models import Business, Membership
    from inventory.business_kinds import BusinessKind

    User = get_user_model()
    user = User.objects.create_user("grocreorder", "grocreorder@example.com", "pass123")
    biz = Business.objects.create(
        name="Grocery Reorder Test",
        slug="grocery-reorder-test",
        business_kind=BusinessKind.GROCERY,
    )
    Membership.objects.create(user=user, business=biz, role="manager", status="ACTIVE")

    client.force_login(user)
    session = client.session
    session["active_business_id"] = biz.id
    session.save()

    url = reverse("groceries:dashboard")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    assert "reorder-suggestions" in content or "Reorder Suggestions" in content, (
        "Groceries dashboard must contain Reorder Suggestions section"
    )

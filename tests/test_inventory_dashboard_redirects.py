# tests/test_inventory_dashboard_redirects.py
"""
Regression tests to prevent infinite redirect loops on /inventory/dashboard/.

These tests guard against the ERR_TOO_MANY_REDIRECTS issue where:
- vertical_dispatcher redirects to "inventory:inventory_dashboard" (itself) for PHONES businesses
- require_business decorator redirects back when no business is set
- dashboard:home redirects to inventory:dashboard creating a loop

CRITICAL: These tests ensure that redirect chains always terminate cleanly.
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

User = get_user_model()


@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123"
    )


@pytest.fixture
def phones_business(db):
    """Create a PHONES business for testing."""
    from tenants.models import Business
    return Business.objects.create(
        name="Test Phones Store",
        slug="test-phones",
        status="ACTIVE",
        business_kind="phones"  # PHONES vertical
    )


@pytest.fixture
def phones_membership(db, user, phones_business):
    """Create an ACTIVE membership for the user in the phones business."""
    from tenants.models import Membership
    return Membership.objects.create(
        user=user,
        business=phones_business,
        role="MANAGER",
        status="ACTIVE"
    )


@pytest.fixture
def client_logged_in(client, user):
    """Return a logged-in client."""
    client.force_login(user)
    return client


@pytest.mark.django_db
class TestInventoryDashboardRedirectLoops:
    """
    Test suite to prevent infinite redirect loops on /inventory/dashboard/.
    """

    def test_anonymous_user_redirected_to_login_not_looped(self, client):
        """
        Anonymous user accessing /inventory/dashboard/ should be redirected to login.
        The redirect target MUST NOT be /inventory/dashboard/ itself.
        """
        response = client.get("/inventory/dashboard/", follow=False)
        
        # Should redirect (302)
        assert response.status_code == 302, (
            f"Anonymous user should be redirected, got {response.status_code}"
        )
        
        # Redirect target must NOT BE /inventory/dashboard/ (but ?next= is OK)
        location = response["Location"]
        # Extract the path without query string
        redirect_path = location.split("?")[0]
        assert not redirect_path.rstrip("/").endswith("/inventory/dashboard"), (
            f"Redirect loop detected: anonymous user redirected to {redirect_path}"
        )
        
        # Should redirect to login
        assert "/accounts/login" in location or "/login" in location, (
            f"Expected redirect to login, got {location}"
        )

    def test_authenticated_user_no_business_redirected_to_choose_not_looped(
        self, client_logged_in
    ):
        """
        Authenticated user with NO active business should be redirected to choose-business.
        The redirect target MUST NOT be /inventory/dashboard/.
        """
        response = client_logged_in.get("/inventory/dashboard/", follow=False)
        
        # Should redirect (302)
        assert response.status_code == 302, (
            f"User without business should be redirected, got {response.status_code}"
        )
        
        # Redirect target must NOT be /inventory/dashboard/
        location = response["Location"]
        assert "/inventory/dashboard" not in location, (
            f"Redirect loop detected: user without business redirected to {location}"
        )
        
        # Should redirect to choose-business or activate-mine or tenants
        assert (
            "/tenants/choose" in location
            or "/tenants/activate" in location
            or "/accounts/settings" in location
        ), f"Expected redirect to business selection, got {location}"

    def test_authenticated_user_with_phones_business_gets_200_dashboard(
        self, client_logged_in, phones_business, phones_membership
    ):
        """
        Authenticated user WITH active PHONES business should get a 200 OK dashboard.
        No redirect should occur.
        """
        # Set active business in session
        session = client_logged_in.session
        session["active_business_id"] = phones_business.id
        session.save()
        
        response = client_logged_in.get("/inventory/dashboard/", follow=False)
        
        # Should render successfully (200 OK)
        assert response.status_code == 200, (
            f"User with PHONES business should get 200 OK, got {response.status_code}. "
            f"Location: {response.get('Location', 'N/A')}"
        )
        
        # Should NOT redirect
        assert "Location" not in response, (
            f"User with active business should NOT be redirected, "
            f"but got Location: {response.get('Location')}"
        )

    def test_hard_guard_against_self_redirect(self, client_logged_in):
        """
        Hard guard: any redirect from /inventory/dashboard/ MUST NOT target itself.
        This test catches self-redirect loops regardless of the scenario.
        """
        # Try with no business
        response = client_logged_in.get("/inventory/dashboard/", follow=False)
        
        if response.status_code == 302:
            location = response["Location"]
            # Normalize paths
            normalized_location = location.rstrip("/").split("?")[0]
            
            assert not normalized_location.endswith("/inventory/dashboard"), (
                f"CRITICAL: Self-redirect loop detected! "
                f"/inventory/dashboard/ redirects to {location}"
            )

    def test_follow_redirects_terminates_cleanly_anonymous(self, client):
        """
        Following redirects for anonymous user should terminate at login page (200 OK).
        This ensures no redirect loops exist in the chain.
        """
        # follow=True will raise an exception if there's a redirect loop
        response = client.get("/inventory/dashboard/", follow=True)
        
        # Should eventually land on a 200 OK page (login)
        assert response.status_code == 200, (
            f"Redirect chain should terminate with 200, got {response.status_code}"
        )
        
        # Should be on login page
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else "/"
        assert "/login" in final_url or "login" in response.request["PATH_INFO"], (
            f"Should land on login page, final URL: {final_url}"
        )

    def test_follow_redirects_terminates_cleanly_no_business(self, client_logged_in):
        """
        Following redirects for authenticated user without business should terminate cleanly.
        This ensures no redirect loops exist in the chain.
        """
        # follow=True will raise an exception if there's a redirect loop
        response = client_logged_in.get("/inventory/dashboard/", follow=True)
        
        # Should eventually land on a 200 OK page (choose-business or activate-mine)
        assert response.status_code == 200, (
            f"Redirect chain should terminate with 200, got {response.status_code}"
        )
        
        # Should NOT be on /inventory/dashboard/
        final_path = response.request.get("PATH_INFO", "")
        assert "/inventory/dashboard" not in final_path, (
            f"Should NOT end up back on /inventory/dashboard/, final path: {final_path}"
        )

    def test_vertical_dispatcher_does_not_redirect_phones_to_itself(
        self, client_logged_in, phones_business, phones_membership
    ):
        """
        CRITICAL: vertical_dispatcher should NOT redirect PHONES businesses back to
        inventory:inventory_dashboard (which is the same URL).
        
        This is the core fix for the ERR_TOO_MANY_REDIRECTS issue.
        """
        # Set active business in session
        session = client_logged_in.session
        session["active_business_id"] = phones_business.id
        session.save()
        
        # Access the dashboard
        response = client_logged_in.get("/inventory/dashboard/", follow=False)
        
        # For PHONES vertical, should render (200) NOT redirect (302)
        assert response.status_code == 200, (
            f"PHONES business should render dashboard directly (200), "
            f"got {response.status_code}. "
            f"If 302, this indicates the old self-redirect bug is back!"
        )
        
        # Absolutely NO redirect should occur
        assert "Location" not in response, (
            f"CRITICAL: PHONES business redirected to {response.get('Location')}. "
            f"This is the self-redirect loop bug!"
        )


@pytest.mark.django_db
class TestOtherVerticalsRedirect:
    """
    Test that other verticals (gym, liquor, pharmacy, clothing) DO redirect properly.
    """

    def test_liquor_business_redirects_to_liquor_dashboard(
        self, client_logged_in, user, db
    ):
        """
        Liquor business should redirect to verticals:liquor_dashboard.
        """
        from tenants.models import Business, Membership
        
        # Create LIQUOR business
        liquor_biz = Business.objects.create(
            name="Test Liquor Store",
            slug="test-liquor",
            status="ACTIVE",
            business_kind="liquor"
        )
        
        Membership.objects.create(
            user=user,
            business=liquor_biz,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Set active business in session
        session = client_logged_in.session
        session["active_business_id"] = liquor_biz.id
        session.save()
        
        response = client_logged_in.get("/inventory/dashboard/", follow=False)
        
        # Should redirect (302) to liquor dashboard
        assert response.status_code == 302, (
            f"Liquor business should redirect to liquor dashboard, got {response.status_code}"
        )
        
        location = response["Location"]
        
        # Should redirect to verticals liquor dashboard
        assert (
            "/verticals/liquor" in location or "liquor" in location
        ), f"Expected redirect to liquor dashboard, got {location}"
        
        # Should NOT redirect back to /inventory/dashboard/
        assert "/inventory/dashboard" not in location, (
            f"Liquor business should NOT redirect to /inventory/dashboard/, got {location}"
        )


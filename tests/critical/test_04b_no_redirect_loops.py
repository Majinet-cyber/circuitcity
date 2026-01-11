# tests/critical/test_04b_no_redirect_loops.py
"""
CRITICAL TEST 04b: No Redirect Loops in Core Flows

These tests ensure that core endpoints don't have redirect loops that would
break the user experience. Redirect loops are a critical bug class.

FAILURE HERE = Users stuck in infinite redirects = Critical UX failure

Fix History:
- 2026-01-11: Fixed hardware redirect loop. phone_scan_in now renders generic
  scan_in template for non-PHONES businesses instead of redirecting to itself.
"""
import pytest
from django.test import Client
from django.test.client import RedirectCycleError

from tests.critical.conftest import (
    CORE_VERTICALS,
    CORE_STOCK_VERTICALS,
    CORE_SALES_VERTICALS,
    VERTICAL_ENDPOINTS,
    get_dashboard_url,
    get_stock_add_url,
    get_sell_url,
    setup_authenticated_client,
    bootstrap_business_with_user,
)

# All tests in this module are critical
pytestmark = [pytest.mark.critical, pytest.mark.django_db]

# Maximum allowed redirects before considering it a loop
MAX_ALLOWED_REDIRECTS = 3


def _check_no_redirect_loop(client, url, vertical, endpoint_type):
    """Helper to check for redirect loops and return response or raise."""
    try:
        response = client.get(url, follow=True)
    except RedirectCycleError:
        pytest.fail(f"{vertical} {endpoint_type} has redirect loop at {url}")
    
    # Check redirect chain length
    if hasattr(response, "redirect_chain") and len(response.redirect_chain) > MAX_ALLOWED_REDIRECTS:
        pytest.fail(
            f"{vertical} {endpoint_type} has excessive redirects "
            f"({len(response.redirect_chain)} > {MAX_ALLOWED_REDIRECTS}): {response.redirect_chain}"
        )
    
    return response


class TestDashboardNoRedirectLoops:
    """Test that dashboard endpoints don't have redirect loops."""
    
    @pytest.mark.parametrize("vertical", CORE_VERTICALS)
    def test_dashboard_no_redirect_loop(self, vertical):
        """Dashboard should not have redirect loops for authenticated users."""
        user, business, location = bootstrap_business_with_user(vertical)
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url(vertical)
        if not dashboard_url:
            pytest.skip(f"No dashboard URL for {vertical}")
        
        response = _check_no_redirect_loop(client, dashboard_url, vertical, "dashboard")
        
        # Must not be 500
        assert response.status_code != 500, \
            f"{vertical} dashboard returned 500 after redirects"


class TestStockAddNoRedirectLoops:
    """Test that stock add endpoints don't have redirect loops."""
    
    @pytest.mark.parametrize("vertical", CORE_STOCK_VERTICALS)
    def test_stock_add_no_redirect_loop(self, vertical):
        """Stock add should not have redirect loops for authenticated users."""
        # FIXED: hardware redirect loop resolved - phone_scan_in now renders generic template
        # for non-PHONES businesses instead of redirecting to itself
        
        user, business, location = bootstrap_business_with_user(vertical)
        client = setup_authenticated_client(user, business, location)
        
        stock_add_url = get_stock_add_url(vertical)
        if not stock_add_url:
            pytest.skip(f"No stock add URL for {vertical}")
        
        response = _check_no_redirect_loop(client, stock_add_url, vertical, "stock_add")
        
        # Must not be 500
        assert response.status_code != 500, \
            f"{vertical} stock add returned 500 after redirects"


class TestSellNoRedirectLoops:
    """Test that sell endpoints don't have redirect loops."""
    
    @pytest.mark.parametrize("vertical", CORE_SALES_VERTICALS)
    def test_sell_no_redirect_loop(self, vertical):
        """Sell endpoint should not have redirect loops for authenticated users."""
        # FIXED: hardware scan-sold uses generic ScanSoldView directly with no redirect issues
        
        user, business, location = bootstrap_business_with_user(vertical)
        client = setup_authenticated_client(user, business, location)
        
        sell_url = get_sell_url(vertical)
        if not sell_url:
            pytest.skip(f"No sell URL for {vertical}")
        
        response = _check_no_redirect_loop(client, sell_url, vertical, "sell")
        
        # Must not be 500
        assert response.status_code != 500, \
            f"{vertical} sell returned 500 after redirects"


class TestHardwareRedirectLoopFixed:
    """Test that the hardware redirect loop bug is fixed."""
    
    def test_hardware_stock_add_no_redirect_loop(self):
        """
        This test verifies the hardware stock_add redirect loop is fixed.
        
        FIX APPLIED: phone_scan_in now renders the generic scan_in template
        for non-PHONES businesses instead of redirecting to inventory:scan_in
        (which caused a loop since that route points back to phone_scan_in).
        """
        user, business, location = bootstrap_business_with_user("hardware")
        client = setup_authenticated_client(user, business, location)
        
        stock_add_url = get_stock_add_url("hardware")
        
        # The bug is fixed - this should NOT raise RedirectCycleError
        response = client.get(stock_add_url, follow=True)
        
        # Must return 200 (page renders successfully)
        assert response.status_code == 200, "Hardware stock add should return 200"
        
        # Must have no excessive redirects
        assert len(response.redirect_chain) <= MAX_ALLOWED_REDIRECTS, (
            f"Too many redirects: {response.redirect_chain}"
        )


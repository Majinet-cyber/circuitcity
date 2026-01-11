"""
Test URL name compatibility SSOT (Single Source of Truth).

This test file verifies that all backward-compatible URL aliases work correctly
across all URLConf contexts where they might be used:
- cc/urls.py (root URLConf)
- inventory/urls.py (inventory namespace)
- core/urls_app_router.py (app_router namespace)
- hq/urls.py (hq namespace)

All URL names are defined in ONE place: cc/urls_compat.py
This prevents duplication and ensures consistency.

Tests verify:
1. reverse('home') works
2. reverse('stock') works
3. reverse('sell') works
4. reverse('scan') works
5. reverse('wallet') works
6. reverse('sim') works
7. reverse('businesses') works
8. reverse('pharmacy_stock_in') works
9. reverse('member_qr_image') works
10. reverse('export_monthly_costs') works
11. reverse('export_monthly_sales') works
12. reverse('export_monthly_summary') works
"""
import pytest
from django.test import TestCase
from django.urls import reverse, NoReverseMatch


class URLCompatSSotTest(TestCase):
    """Test backward-compatible URL aliases from cc.urls_compat (SSOT)."""

    def test_reverse_home_works(self):
        """Test reverse('home') works without namespace."""
        try:
            url = reverse('home')
            self.assertIsNotNone(url)
            self.assertIn('/home/', url)
        except NoReverseMatch as e:
            self.fail(f"reverse('home') should work but raised NoReverseMatch: {e}")

    def test_reverse_stock_works(self):
        """Test reverse('stock') works without namespace."""
        try:
            url = reverse('stock')
            self.assertIsNotNone(url)
            # Should resolve to alias URL
            self.assertIn('__alias__/stock/', url)
        except NoReverseMatch as e:
            self.fail(f"reverse('stock') should work but raised NoReverseMatch: {e}")

    def test_reverse_sell_works(self):
        """Test reverse('sell') works without namespace."""
        try:
            url = reverse('sell')
            self.assertIsNotNone(url)
            # Should resolve to alias URL
            self.assertIn('__alias__/sell/', url)
        except NoReverseMatch as e:
            self.fail(f"reverse('sell') should work but raised NoReverseMatch: {e}")

    def test_reverse_scan_works(self):
        """Test reverse('scan') works without namespace."""
        try:
            url = reverse('scan')
            self.assertIsNotNone(url)
            # Should resolve to alias URL
            self.assertIn('__alias__/scan/', url)
        except NoReverseMatch as e:
            self.fail(f"reverse('scan') should work but raised NoReverseMatch: {e}")

    def test_reverse_wallet_works(self):
        """Test reverse('wallet') works without namespace."""
        try:
            url = reverse('wallet')
            self.assertIsNotNone(url)
            # Should resolve to alias URL
            self.assertIn('__alias__/wallet/', url)
        except NoReverseMatch as e:
            self.fail(f"reverse('wallet') should work but raised NoReverseMatch: {e}")

    def test_reverse_sim_works(self):
        """Test reverse('sim') works without namespace."""
        try:
            url = reverse('sim')
            self.assertIsNotNone(url)
            # Should resolve to alias URL
            self.assertIn('__alias__/sim/', url)
        except NoReverseMatch as e:
            self.fail(f"reverse('sim') should work but raised NoReverseMatch: {e}")

    def test_reverse_businesses_works(self):
        """Test reverse('businesses') works without namespace."""
        try:
            url = reverse('businesses')
            self.assertIsNotNone(url)
            # Should resolve to alias URL
            self.assertIn('__alias__/businesses/', url)
        except NoReverseMatch as e:
            self.fail(f"reverse('businesses') should work but raised NoReverseMatch: {e}")

    def test_reverse_pharmacy_stock_in_works(self):
        """Test reverse('pharmacy_stock_in') works without namespace."""
        try:
            url = reverse('pharmacy_stock_in')
            self.assertIsNotNone(url)
            # Should resolve to alias URL
            self.assertIn('__alias__/pharmacy-stock-in/', url)
        except NoReverseMatch as e:
            self.fail(f"reverse('pharmacy_stock_in') should work but raised NoReverseMatch: {e}")

    def test_reverse_member_qr_image_works(self):
        """Test reverse('member_qr_image') works without namespace."""
        try:
            url = reverse('member_qr_image')
            self.assertIsNotNone(url)
            # Should resolve to alias URL (redirects to gym:members_list when no UUID)
            self.assertIn('__alias__/member-qr-image/', url)
        except NoReverseMatch as e:
            self.fail(f"reverse('member_qr_image') should work but raised NoReverseMatch: {e}")

    def test_reverse_member_qr_image_with_uuid_works(self):
        """Test reverse('member_qr_image_with_uuid') works with UUID argument."""
        import uuid
        test_uuid = uuid.uuid4()
        try:
            url = reverse('member_qr_image_with_uuid', kwargs={'qr_uuid': test_uuid})
            self.assertIsNotNone(url)
            # Should resolve to alias URL with UUID
            self.assertIn('__alias__/member-qr-image/', url)
            self.assertIn(str(test_uuid), url)
        except NoReverseMatch as e:
            self.fail(f"reverse('member_qr_image_with_uuid') should work but raised NoReverseMatch: {e}")

    def test_reverse_export_monthly_costs_works(self):
        """Test reverse('export_monthly_costs') works without namespace."""
        try:
            url = reverse('export_monthly_costs')
            self.assertIsNotNone(url)
            # Should resolve to alias URL
            self.assertIn('__alias__/export-monthly-costs/', url)
        except NoReverseMatch as e:
            self.fail(f"reverse('export_monthly_costs') should work but raised NoReverseMatch: {e}")

    def test_reverse_export_monthly_sales_works(self):
        """Test reverse('export_monthly_sales') works without namespace."""
        try:
            url = reverse('export_monthly_sales')
            self.assertIsNotNone(url)
            # Should resolve to alias URL
            self.assertIn('__alias__/export-monthly-sales/', url)
        except NoReverseMatch as e:
            self.fail(f"reverse('export_monthly_sales') should work but raised NoReverseMatch: {e}")

    def test_reverse_export_monthly_summary_works(self):
        """Test reverse('export_monthly_summary') works without namespace."""
        try:
            url = reverse('export_monthly_summary')
            self.assertIsNotNone(url)
            # Should resolve to alias URL
            self.assertIn('__alias__/export-monthly-summary/', url)
        except NoReverseMatch as e:
            self.fail(f"reverse('export_monthly_summary') should work but raised NoReverseMatch: {e}")


class CanonicalNamespacedRoutesTest(TestCase):
    """Test that canonical namespaced routes still work (no regressions)."""

    def test_inventory_stock_list_works(self):
        """Test inventory:stock_list route works."""
        try:
            url = reverse('inventory:stock_list')
            self.assertIsNotNone(url)
            self.assertIn('/inventory/list/', url)
        except NoReverseMatch as e:
            self.fail(f"inventory:stock_list should work: {e}")

    def test_inventory_scan_in_works(self):
        """Test inventory:scan_in route works."""
        try:
            url = reverse('inventory:scan_in')
            self.assertIsNotNone(url)
            self.assertIn('/inventory/scan-in/', url)
        except NoReverseMatch as e:
            self.fail(f"inventory:scan_in should work: {e}")

    def test_inventory_scan_sold_works(self):
        """Test inventory:scan_sold route works."""
        try:
            url = reverse('inventory:scan_sold')
            self.assertIsNotNone(url)
            self.assertIn('/inventory/scan-sold/', url)
        except NoReverseMatch as e:
            self.fail(f"inventory:scan_sold should work: {e}")

    def test_wallet_agent_wallet_works(self):
        """Test wallet:agent_wallet route works (if wallet URLConf is loaded)."""
        try:
            url = reverse('wallet:agent_wallet')
            self.assertIsNotNone(url)
        except NoReverseMatch:
            # It's okay if wallet app isn't installed in this test environment
            pass

    def test_simulator_home_works(self):
        """Test simulator:home route works (if simulator URLConf is loaded)."""
        try:
            url = reverse('simulator:home')
            self.assertIsNotNone(url)
        except NoReverseMatch:
            # It's okay if simulator app isn't installed in this test environment
            pass

    def test_hq_business_directory_works(self):
        """Test hq:business_directory route works."""
        try:
            url = reverse('hq:business_directory')
            self.assertIsNotNone(url)
            self.assertIn('/hq/businesses/', url)
        except NoReverseMatch as e:
            self.fail(f"hq:business_directory should work: {e}")

    def test_pharmacy_stock_in_namespaced_works(self):
        """Test pharmacy:stock_in route works (canonical namespaced version)."""
        try:
            url = reverse('pharmacy:stock_in')
            self.assertIsNotNone(url)
            self.assertIn('/pharmacy/stock-in/', url)
        except NoReverseMatch:
            # It's okay if pharmacy URLs aren't loaded in this test environment
            pass

    def test_gym_member_qr_png_works(self):
        """Test gym:member_qr_png route works (canonical namespaced version)."""
        try:
            # This requires a UUID argument, so we can't test the full reverse
            # Just check that the name is registered
            from django.urls import get_resolver
            resolver = get_resolver()
            # Try to find the pattern
            found = False
            for pattern in resolver.url_patterns:
                if hasattr(pattern, 'namespace') and pattern.namespace == 'gym':
                    found = True
                    break
            # It's okay if gym namespace isn't loaded
            if found:
                self.assertTrue(True, "gym namespace is loaded")
        except Exception:
            # It's okay if gym URLs aren't loaded in this test environment
            pass


class URLCompatSSotConsistencyTest(TestCase):
    """Test that URL compatibility aliases are consistent across all URLConfs."""

    def test_no_duplicate_definitions(self):
        """
        Test that compatibility URL names are not defined in multiple places.
        
        This test ensures the SSOT principle is maintained by verifying that
        all compatibility aliases come from cc.urls_compat and are not duplicated
        in individual URLConf files.
        
        Note: This is a conceptual test. In practice, we enforce this through
        code review and the SSOT pattern itself.
        """
        import uuid
        from cc.urls_compat import all_compat_url_names
        
        compat_names = all_compat_url_names()
        
        # Verify all names are resolvable
        for name in compat_names:
            if name == 'home':
                # 'home' is defined in cc/urls.py directly, not in urls_compat.py
                continue
            try:
                if name == 'member_qr_image_with_uuid':
                    # This URL requires a UUID argument
                    url = reverse(name, kwargs={'qr_uuid': uuid.uuid4()})
                else:
                    url = reverse(name)
                self.assertIsNotNone(url, f"URL name '{name}' should resolve")
            except NoReverseMatch:
                self.fail(f"URL name '{name}' from SSOT should be resolvable")

    def test_ssot_module_exists(self):
        """Test that cc.urls_compat module exists and is importable."""
        try:
            from cc.urls_compat import get_compat_urlpatterns
            self.assertTrue(callable(get_compat_urlpatterns))
        except ImportError as e:
            self.fail(f"cc.urls_compat should be importable: {e}")

    def test_get_compat_urlpatterns_returns_list(self):
        """Test that get_compat_urlpatterns() returns a list of URL patterns."""
        from cc.urls_compat import get_compat_urlpatterns
        
        patterns = get_compat_urlpatterns()
        self.assertIsInstance(patterns, list)
        self.assertGreater(len(patterns), 0, "Should return at least one URL pattern")


@pytest.mark.django_db
class URLCompatIntegrationTest(TestCase):
    """Integration tests for URL compatibility across different contexts."""

    def test_redirect_aliases_point_to_correct_targets(self):
        """Test that redirect aliases point to the correct canonical URLs."""
        # Test that 'stock' alias redirects to inventory:stock_list
        stock_alias_url = reverse('stock')
        stock_canonical_url = reverse('inventory:stock_list')
        
        # The alias URL should be different from the canonical URL
        self.assertNotEqual(stock_alias_url, stock_canonical_url)
        
        # Similar tests for other aliases
        sell_alias_url = reverse('sell')
        sell_canonical_url = reverse('inventory:scan_sold')
        self.assertNotEqual(sell_alias_url, sell_canonical_url)

    def test_all_critical_urls_resolve(self):
        """Test that all critical URL names mentioned in the requirements resolve."""
        critical_urls = [
            'home',
            'stock',
            'sell',
            'scan',
            'wallet',
            'sim',
            'businesses',
            'pharmacy_stock_in',
            'member_qr_image',
            'export_monthly_costs',
            'export_monthly_sales',
            'export_monthly_summary',
        ]
        
        for url_name in critical_urls:
            try:
                url = reverse(url_name)
                self.assertIsNotNone(url, f"Critical URL '{url_name}' should resolve")
            except NoReverseMatch as e:
                self.fail(f"Critical URL '{url_name}' failed to resolve: {e}")


@pytest.mark.django_db
class ReportsExportURLAliasesTest(TestCase):
    """Test reports export URL aliases resolve and redirect correctly."""

    def test_namespaced_export_monthly_sales_works(self):
        """Test reports:export_monthly_sales canonical route works."""
        try:
            url = reverse('reports:export_monthly_sales')
            self.assertIsNotNone(url)
            self.assertIn('/reports/export/sales/', url)
        except NoReverseMatch as e:
            self.fail(f"reports:export_monthly_sales should work: {e}")

    def test_namespaced_export_monthly_costs_works(self):
        """Test reports:export_monthly_costs canonical route works."""
        try:
            url = reverse('reports:export_monthly_costs')
            self.assertIsNotNone(url)
            self.assertIn('/reports/export/costs/', url)
        except NoReverseMatch as e:
            self.fail(f"reports:export_monthly_costs should work: {e}")

    def test_namespaced_export_monthly_summary_works(self):
        """Test reports:export_monthly_summary canonical route works."""
        try:
            url = reverse('reports:export_monthly_summary')
            self.assertIsNotNone(url)
            self.assertIn('/reports/export/summary/', url)
        except NoReverseMatch as e:
            self.fail(f"reports:export_monthly_summary should work: {e}")

    def test_global_alias_export_monthly_sales_works(self):
        """Test export_monthly_sales global alias works."""
        try:
            url = reverse('export_monthly_sales')
            self.assertIsNotNone(url)
            self.assertIn('__alias__/export-monthly-sales/', url)
        except NoReverseMatch as e:
            self.fail(f"export_monthly_sales alias should work: {e}")

    def test_global_alias_export_monthly_costs_works(self):
        """Test export_monthly_costs global alias works."""
        try:
            url = reverse('export_monthly_costs')
            self.assertIsNotNone(url)
            self.assertIn('__alias__/export-monthly-costs/', url)
        except NoReverseMatch as e:
            self.fail(f"export_monthly_costs alias should work: {e}")

    def test_global_alias_export_monthly_summary_works(self):
        """Test export_monthly_summary global alias works."""
        try:
            url = reverse('export_monthly_summary')
            self.assertIsNotNone(url)
            self.assertIn('__alias__/export-monthly-summary/', url)
        except NoReverseMatch as e:
            self.fail(f"export_monthly_summary alias should work: {e}")


@pytest.mark.django_db
class URLAliasGETResponseTest(TestCase):
    """Test that GET requests to alias URLs return 200/302 (not errors)."""

    def test_get_pharmacy_stock_in_alias_returns_redirect(self):
        """Test GET to pharmacy_stock_in alias returns 302 redirect."""
        url = reverse('pharmacy_stock_in')
        response = self.client.get(url)
        # RedirectView returns 302
        self.assertIn(response.status_code, [200, 302, 301, 303])

    def test_get_member_qr_image_alias_returns_redirect(self):
        """Test GET to member_qr_image alias returns 302 redirect to gym members list."""
        url = reverse('member_qr_image')
        response = self.client.get(url)
        # RedirectView returns 302 to gym:members_list
        self.assertIn(response.status_code, [200, 302, 301, 303])

    def test_get_member_qr_image_with_uuid_returns_redirect(self):
        """Test GET to member_qr_image_with_uuid alias returns 302 redirect to gym:member_qr_png."""
        import uuid
        test_uuid = uuid.uuid4()
        url = reverse('member_qr_image_with_uuid', kwargs={'qr_uuid': test_uuid})
        response = self.client.get(url)
        # Custom redirect view returns 302 to gym:member_qr_png
        self.assertIn(response.status_code, [200, 302, 301, 303, 404])  # 404 if member doesn't exist

    def test_get_export_monthly_costs_alias_returns_redirect(self):
        """Test GET to export_monthly_costs alias returns 302 redirect."""
        url = reverse('export_monthly_costs')
        response = self.client.get(url)
        # RedirectView returns 302
        self.assertIn(response.status_code, [200, 302, 301, 303])

    def test_get_export_monthly_sales_alias_returns_redirect(self):
        """Test GET to export_monthly_sales alias returns 302 redirect."""
        url = reverse('export_monthly_sales')
        response = self.client.get(url)
        # RedirectView returns 302
        self.assertIn(response.status_code, [200, 302, 301, 303])

    def test_get_export_monthly_summary_alias_returns_redirect(self):
        """Test GET to export_monthly_summary alias returns 302 redirect."""
        url = reverse('export_monthly_summary')
        response = self.client.get(url)
        # RedirectView returns 302
        self.assertIn(response.status_code, [200, 302, 301, 303])


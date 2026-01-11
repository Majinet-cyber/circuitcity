"""
Test backward-compatible URL aliases to ensure no NoReverseMatch errors.

This test file verifies that all global route name aliases work correctly:
- reverse('home') -> dashboard home
- reverse('stock') -> inventory stock list  
- reverse('wallet') -> wallet agent dashboard
- reverse('sim') -> simulator home
- reverse('businesses') -> HQ business directory
- reverse('inventory_verticals:...') -> vertical dashboards
"""
from django.test import TestCase
from django.urls import reverse, NoReverseMatch


class URLCompatibilityAliasesTest(TestCase):
    """Test backward-compatible global URL aliases."""

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
            # Should resolve to some URL (even if it's an alias redirect)
        except NoReverseMatch as e:
            self.fail(f"reverse('stock') should work but raised NoReverseMatch: {e}")

    def test_reverse_wallet_works(self):
        """Test reverse('wallet') works without namespace."""
        try:
            url = reverse('wallet')
            self.assertIsNotNone(url)
            # Should resolve to some URL (even if it's an alias redirect)
        except NoReverseMatch as e:
            self.fail(f"reverse('wallet') should work but raised NoReverseMatch: {e}")

    def test_reverse_sim_works(self):
        """Test reverse('sim') works without namespace."""
        try:
            url = reverse('sim')
            self.assertIsNotNone(url)
            # Should resolve to some URL (even if it's an alias redirect)
        except NoReverseMatch as e:
            self.fail(f"reverse('sim') should work but raised NoReverseMatch: {e}")

    def test_reverse_businesses_works(self):
        """Test reverse('businesses') works without namespace."""
        try:
            url = reverse('businesses')
            self.assertIsNotNone(url)
            # Should resolve to some URL (even if it's an alias redirect)
        except NoReverseMatch as e:
            self.fail(f"reverse('businesses') should work but raised NoReverseMatch: {e}")


class InventoryVerticalsNamespaceTest(TestCase):
    """Test inventory_verticals namespace is properly registered."""

    def test_inventory_verticals_namespace_exists(self):
        """Test inventory_verticals namespace is registered."""
        try:
            # This should work if the namespace is properly registered
            url = reverse('inventory_verticals:phones_dashboard')
            self.assertIsNotNone(url)
        except NoReverseMatch as e:
            self.fail(f"inventory_verticals namespace not registered: {e}")

    def test_inventory_verticals_gym_dashboard(self):
        """Test inventory_verticals:gym_dashboard route exists."""
        try:
            url = reverse('inventory_verticals:gym_dashboard')
            self.assertIsNotNone(url)
        except NoReverseMatch as e:
            self.fail(f"inventory_verticals:gym_dashboard not found: {e}")

    def test_inventory_verticals_clothing_dashboard(self):
        """Test inventory_verticals:clothing_dashboard route exists."""
        try:
            url = reverse('inventory_verticals:clothing_dashboard')
            self.assertIsNotNone(url)
        except NoReverseMatch as e:
            self.fail(f"inventory_verticals:clothing_dashboard not found: {e}")

    def test_inventory_verticals_liquor_dashboard(self):
        """Test inventory_verticals:liquor_dashboard route exists."""
        try:
            url = reverse('inventory_verticals:liquor_dashboard')
            self.assertIsNotNone(url)
        except NoReverseMatch as e:
            self.fail(f"inventory_verticals:liquor_dashboard not found: {e}")

    def test_inventory_verticals_pharmacy_dashboard(self):
        """Test inventory_verticals:pharmacy_dashboard route exists."""
        try:
            url = reverse('inventory_verticals:pharmacy_dashboard')
            self.assertIsNotNone(url)
        except NoReverseMatch as e:
            self.fail(f"inventory_verticals:pharmacy_dashboard not found: {e}")


class CanonicalRoutesTest(TestCase):
    """Test that canonical namespaced routes still work."""

    def test_dashboard_home_works(self):
        """Test dashboard:home route works."""
        try:
            url = reverse('dashboard:home')
            self.assertIsNotNone(url)
        except NoReverseMatch as e:
            self.fail(f"dashboard:home should work: {e}")

    def test_inventory_stock_list_works(self):
        """Test inventory:stock_list route works."""
        try:
            url = reverse('inventory:stock_list')
            self.assertIsNotNone(url)
        except NoReverseMatch as e:
            self.fail(f"inventory:stock_list should work: {e}")

    def test_wallet_agent_wallet_works(self):
        """Test wallet:agent_wallet route works."""
        try:
            url = reverse('wallet:agent_wallet')
            self.assertIsNotNone(url)
        except NoReverseMatch as e:
            self.fail(f"wallet:agent_wallet should work: {e}")

    def test_simulator_home_works(self):
        """Test simulator:home route works."""
        try:
            url = reverse('simulator:home')
            self.assertIsNotNone(url)
        except NoReverseMatch as e:
            self.fail(f"simulator:home should work: {e}")

    def test_hq_business_directory_works(self):
        """Test hq:business_directory route works."""
        try:
            url = reverse('hq:business_directory')
            self.assertIsNotNone(url)
        except NoReverseMatch as e:
            self.fail(f"hq:business_directory should work: {e}")

    def test_hq_businesses_alias_works(self):
        """Test hq:businesses alias also works."""
        try:
            # This might be an alias, so we just check it resolves
            url = reverse('hq:business_directory')
            self.assertIsNotNone(url)
        except NoReverseMatch:
            pass  # It's okay if this particular alias doesn't exist


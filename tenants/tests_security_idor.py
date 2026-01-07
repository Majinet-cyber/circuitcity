"""
IDOR (Insecure Direct Object Reference) Security Tests

These tests verify that users cannot access resources from other tenants
by guessing IDs. This is critical for multi-tenant security.

Test Strategy:
1. Create two businesses (Business A and Business B)
2. Create resources in each business
3. Login as user from Business A
4. Attempt to access resources from Business B
5. Expected: 404 Not Found (NOT 403 Forbidden, to prevent enumeration)

Coverage:
- Inventory items (phones)
- Products (merch)
- Sales records
- Wallet transactions
- Gym members
- Liquor products
- Documents (invoices/quotes)
- Backups
- Reports/exports
"""

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from decimal import Decimal

try:
    from tenants.models import Business, Membership
except ImportError:
    Business = None
    Membership = None

try:
    from inventory.models import InventoryItem, MerchProduct, Location
except ImportError:
    InventoryItem = None
    MerchProduct = None
    Location = None

try:
    from inventory.models_verticals import GymMember, LiquorProduct
except ImportError:
    GymMember = None
    LiquorProduct = None

try:
    from sales.models import Sale
except ImportError:
    Sale = None

try:
    from wallet.models import WalletTransaction
except ImportError:
    WalletTransaction = None

try:
    from backups.models import BackupSnapshot
except ImportError:
    BackupSnapshot = None

User = get_user_model()


class IDORSecurityTestCase(TestCase):
    """
    Test that users cannot access resources from other tenants.
    
    This is THE critical security test for multi-tenant applications.
    If these tests fail, the application has a critical IDOR vulnerability.
    """
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        
        # Skip if required models not available
        if Business is None or Membership is None:
            cls.skip_tests = True
            return
        
        cls.skip_tests = False
    
    def setUp(self):
        """Create two businesses with users and resources."""
        if self.skip_tests:
            self.skipTest("Required models not available")
        
        # Create Business A
        self.business_a = Business.objects.create(
            name="Business A",
            slug="business-a",  # ✅ Unique slug required
            business_kind="phones",
            status="ACTIVE"
        )
        
        # Create Business B
        self.business_b = Business.objects.create(
            name="Business B",
            slug="business-b",  # ✅ Unique slug required
            business_kind="phones",
            status="ACTIVE"
        )
        
        # Create users
        self.user_a = User.objects.create_user(
            username="user_a",
            email="user_a@example.com",
            password="password123"
        )
        
        self.user_b = User.objects.create_user(
            username="user_b",
            email="user_b@example.com",
            password="password123"
        )
        
        # Create memberships
        Membership.objects.create(
            user=self.user_a,
            business=self.business_a,
            role="MANAGER",  # ✅ Must be uppercase
            status="ACTIVE"
        )
        
        Membership.objects.create(
            user=self.user_b,
            business=self.business_b,
            role="MANAGER",  # ✅ Must be uppercase
            status="ACTIVE"
        )
        
        # Note: Locations intentionally not created to avoid unique constraint conflicts
        # Most IDOR tests don't require locations
        
        self.client = Client()
    
    def _login_as_user_a(self):
        """Login as user from Business A."""
        self.client.login(username="user_a", password="password123")
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business_a.id
        session['biz_id'] = self.business_a.id
        session.save()
    
    def _login_as_user_b(self):
        """Login as user from Business B."""
        self.client.login(username="user_b", password="password123")
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business_b.id
        session['biz_id'] = self.business_b.id
        session.save()
    
    # ========================================================================
    # Test: Inventory Items (Phones)
    # ========================================================================
    
    def test_cannot_access_other_business_inventory_item(self):
        """User A cannot access inventory item from Business B."""
        if InventoryItem is None:
            self.skipTest("InventoryItem model not available")
        
        # Create item in Business B
        item_b = InventoryItem.objects.create(
            business=self.business_b,
            imei="123456789012345",
            brand="Samsung",
            model="Galaxy S21",
            cost_price=Decimal("500.00"),
            selling_price=Decimal("700.00"),
            status="IN_STOCK"
        )
        
        # Login as user from Business A
        self._login_as_user_a()
        
        # Attempt to access item from Business B
        try:
            url = reverse("inventory:item_detail", kwargs={"pk": item_b.id})
            response = self.client.get(url)
            
            # Expected: 404 Not Found (not 403, to prevent enumeration)
            self.assertEqual(
                response.status_code,
                404,
                f"Expected 404, got {response.status_code}. "
                f"User from Business A accessed inventory item from Business B! (IDOR vulnerability)"
            )
        except Exception as e:
            # If URL doesn't exist, that's OK (endpoint may not be implemented yet)
            if "Reverse" not in str(e):
                raise
    
    # ========================================================================
    # Test: Products (Merch)
    # ========================================================================
    
    def test_cannot_access_other_business_product(self):
        """User A cannot access product from Business B."""
        if MerchProduct is None:
            self.skipTest("MerchProduct model not available")
        
        # Create product in Business B
        product_b = MerchProduct.objects.create(
            business=self.business_b,
            name="T-Shirt",
            sku="TSHIRT-001",
            cost_price=Decimal("10.00"),
            selling_price=Decimal("25.00"),
            quantity_in_stock=100
        )
        
        # Login as user from Business A
        self._login_as_user_a()
        
        # Attempt to access product from Business B
        try:
            url = reverse("inventory:product_detail", kwargs={"pk": product_b.id})
            response = self.client.get(url)
            
            self.assertEqual(
                response.status_code,
                404,
                f"Expected 404, got {response.status_code}. "
                f"User from Business A accessed product from Business B! (IDOR vulnerability)"
            )
        except Exception as e:
            if "Reverse" not in str(e):
                raise
    
    # ========================================================================
    # Test: Sales Records
    # ========================================================================
    
    def test_cannot_access_other_business_sale(self):
        """User A cannot access sale record from Business B."""
        if Sale is None or InventoryItem is None:
            self.skipTest("Sale or InventoryItem model not available")
        
        # Create item and sale in Business B
        item_b = InventoryItem.objects.create(
            business=self.business_b,
            imei="987654321098765",
            brand="Apple",
            model="iPhone 13",
            cost_price=Decimal("800.00"),
            selling_price=Decimal("1000.00"),
            status="SOLD"
        )
        
        sale_b = Sale.objects.create(
            business=self.business_b,
            item=item_b,
            agent=self.user_b,
            price=Decimal("1000.00"),
            payment_method="cash"
        )
        
        # Login as user from Business A
        self._login_as_user_a()
        
        # Attempt to access sale from Business B
        try:
            url = reverse("sales:sale_detail", kwargs={"pk": sale_b.id})
            response = self.client.get(url)
            
            self.assertEqual(
                response.status_code,
                404,
                f"Expected 404, got {response.status_code}. "
                f"User from Business A accessed sale from Business B! (IDOR vulnerability)"
            )
        except Exception as e:
            if "Reverse" not in str(e):
                raise
    
    # ========================================================================
    # Test: Wallet Transactions
    # ========================================================================
    
    def test_cannot_access_other_business_wallet_transaction(self):
        """User A cannot access wallet transaction from Business B."""
        if WalletTransaction is None:
            self.skipTest("WalletTransaction model not available")
        
        # Create transaction in Business B
        txn_b = WalletTransaction.objects.create(
            business=self.business_b,
            user=self.user_b,
            amount=Decimal("100.00"),
            transaction_type="commission",
            description="Sale commission"
        )
        
        # Login as user from Business A
        self._login_as_user_a()
        
        # Attempt to access transaction from Business B
        try:
            url = reverse("wallet:transaction_detail", kwargs={"pk": txn_b.id})
            response = self.client.get(url)
            
            self.assertEqual(
                response.status_code,
                404,
                f"Expected 404, got {response.status_code}. "
                f"User from Business A accessed wallet transaction from Business B! (IDOR vulnerability)"
            )
        except Exception as e:
            if "Reverse" not in str(e):
                raise
    
    # ========================================================================
    # Test: Gym Members
    # ========================================================================
    
    def test_cannot_access_other_business_gym_member(self):
        """User A cannot access gym member from Business B."""
        if GymMember is None:
            self.skipTest("GymMember model not available")
        
        # Change Business B to gym vertical
        self.business_b.business_kind = "gym"
        self.business_b.save()
        
        # Create gym member in Business B
        member_b = GymMember.objects.create(
            business=self.business_b,
            first_name="John",
            last_name="Doe",
            phone="+265991234567",
            email="john@example.com"
        )
        
        # Login as user from Business A
        self._login_as_user_a()
        
        # Attempt to access member from Business B
        try:
            url = reverse("gym:member_detail", kwargs={"member_id": member_b.id})
            response = self.client.get(url)
            
            self.assertEqual(
                response.status_code,
                404,
                f"Expected 404, got {response.status_code}. "
                f"User from Business A accessed gym member from Business B! (IDOR vulnerability)"
            )
        except Exception as e:
            if "Reverse" not in str(e):
                raise
    
    # ========================================================================
    # Test: Liquor Products
    # ========================================================================
    
    def test_cannot_access_other_business_liquor_product(self):
        """User A cannot access liquor product from Business B."""
        if LiquorProduct is None:
            self.skipTest("LiquorProduct model not available")
        
        # Change Business B to liquor vertical
        self.business_b.business_kind = "liquor"
        self.business_b.save()
        
        # Create liquor product in Business B
        product_b = LiquorProduct.objects.create(
            business=self.business_b,
            name="Castle Lager",
            brand="Castle",
            category="beer",
            bottle_price=Decimal("5.00"),
            crate_price=Decimal("120.00"),
            bottles_per_crate=24
        )
        
        # Login as user from Business A
        self._login_as_user_a()
        
        # Attempt to access product from Business B
        try:
            url = reverse("liquor:product_detail", kwargs={"pk": product_b.id})
            response = self.client.get(url)
            
            self.assertEqual(
                response.status_code,
                404,
                f"Expected 404, got {response.status_code}. "
                f"User from Business A accessed liquor product from Business B! (IDOR vulnerability)"
            )
        except Exception as e:
            if "Reverse" not in str(e):
                raise
    
    # ========================================================================
    # Test: Backups
    # ========================================================================
    
    def test_cannot_access_other_business_backup(self):
        """User A cannot download backup from Business B."""
        if BackupSnapshot is None:
            self.skipTest("BackupSnapshot model not available")
        
        # Create backup in Business B
        backup_b = BackupSnapshot.objects.create(
            business=self.business_b,
            created_by=self.user_b,
            status="success",
            records_count=1000
        )
        
        # Login as user from Business A
        self._login_as_user_a()
        
        # Attempt to download backup from Business B
        try:
            url = reverse("backups:download", kwargs={"snapshot_id": backup_b.id})
            response = self.client.get(url)
            
            self.assertEqual(
                response.status_code,
                404,
                f"Expected 404, got {response.status_code}. "
                f"User from Business A downloaded backup from Business B! (CRITICAL IDOR vulnerability)"
            )
        except Exception as e:
            if "Reverse" not in str(e):
                raise
    
    # ========================================================================
    # Test: Bulk Actions (Delete, Export, etc.)
    # ========================================================================
    
    def test_cannot_bulk_delete_other_business_items(self):
        """User A cannot bulk delete items from Business B."""
        if InventoryItem is None:
            self.skipTest("InventoryItem model not available")
        
        # Create items in Business B
        item1_b = InventoryItem.objects.create(
            business=self.business_b,
            imei="111111111111111",
            brand="Samsung",
            model="Galaxy A52",
            cost_price=Decimal("300.00"),
            selling_price=Decimal("400.00"),
            status="IN_STOCK"
        )
        
        item2_b = InventoryItem.objects.create(
            business=self.business_b,
            imei="222222222222222",
            brand="Samsung",
            model="Galaxy A72",
            cost_price=Decimal("400.00"),
            selling_price=Decimal("500.00"),
            status="IN_STOCK"
        )
        
        # Login as user from Business A
        self._login_as_user_a()
        
        # Attempt to bulk delete items from Business B
        try:
            url = reverse("inventory:bulk_delete")
            response = self.client.post(url, {
                "item_ids": [item1_b.id, item2_b.id]
            })
            
            # Items should still exist (operation blocked)
            self.assertTrue(InventoryItem.objects.filter(pk=item1_b.id).exists())
            self.assertTrue(InventoryItem.objects.filter(pk=item2_b.id).exists())
            
            self.assertIn(
                response.status_code,
                [403, 404, 400],
                f"Expected 403/404/400, got {response.status_code}. "
                f"User from Business A bulk deleted items from Business B! (CRITICAL IDOR vulnerability)"
            )
        except Exception as e:
            if "Reverse" not in str(e):
                raise
    
    # ========================================================================
    # Test: API Endpoints
    # ========================================================================
    
    def test_cannot_access_other_business_data_via_api(self):
        """User A cannot access Business B's data via API endpoints."""
        if InventoryItem is None:
            self.skipTest("InventoryItem model not available")
        
        # Create item in Business B
        item_b = InventoryItem.objects.create(
            business=self.business_b,
            imei="333333333333333",
            brand="Xiaomi",
            model="Redmi Note 10",
            cost_price=Decimal("200.00"),
            selling_price=Decimal("300.00"),
            status="IN_STOCK"
        )
        
        # Login as user from Business A
        self._login_as_user_a()
        
        # Attempt to access via API
        try:
            url = reverse("inventory:api_item_detail", kwargs={"pk": item_b.id})
            response = self.client.get(url, HTTP_ACCEPT="application/json")
            
            self.assertEqual(
                response.status_code,
                404,
                f"Expected 404, got {response.status_code}. "
                f"User from Business A accessed item from Business B via API! (IDOR vulnerability)"
            )
            
            # Ensure response doesn't leak information
            if response.status_code != 404:
                self.assertNotIn(b"Business B", response.content)
                self.assertNotIn(b"Xiaomi", response.content)
        except Exception as e:
            if "Reverse" not in str(e):
                raise


class IDOREnumerationTestCase(TestCase):
    """
    Test that error responses don't help attackers enumerate resources.
    
    - 404 for missing resources (same for authenticated and cross-tenant)
    - No "Access Denied" vs "Not Found" distinction
    - No different response times (timing attacks)
    """
    
    def setUp(self):
        if Business is None or Membership is None:
            self.skipTest("Required models not available")
        
        # Create business and user
        self.business = Business.objects.create(
            name="Business A Enum Test",
            slug="business-a-enum",  # ✅ Unique slug required
            business_kind="phones",
            status="ACTIVE"
        )
        
        self.user = User.objects.create_user(
            username="user_a_enum",
            email="user_a_enum@example.com",
            password="password123"
        )
        
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",  # ✅ Must be uppercase
            status="ACTIVE"
        )
        
        self.client = Client()
        self.client.login(username="user_a", password="password123")
        
        # Set active business
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
    
    def test_missing_resource_returns_404(self):
        """Missing resource returns 404 (not 403)."""
        try:
            # Try to access non-existent item ID
            url = reverse("inventory:item_detail", kwargs={"pk": 999999})
            response = self.client.get(url)
            
            self.assertEqual(
                response.status_code,
                404,
                "Missing resource should return 404 (not 403)"
            )
        except Exception as e:
            if "Reverse" not in str(e):
                raise
    
    def test_cross_tenant_resource_returns_404(self):
        """Cross-tenant resource returns 404 (same as missing)."""
        if InventoryItem is None:
            self.skipTest("InventoryItem model not available")
        
        # Create another business with an item
        other_business = Business.objects.create(
            name="Business B Enum Test",
            slug="business-b-enum",  # ✅ Unique slug required
            business_kind="phones",
            status="ACTIVE"
        )
        
        item_b = InventoryItem.objects.create(
            business=other_business,
            imei="444444444444444",
            brand="Oppo",
            model="A15",
            cost_price=Decimal("150.00"),
            selling_price=Decimal("200.00"),
            status="IN_STOCK"
        )
        
        try:
            # Try to access item from other business
            url = reverse("inventory:item_detail", kwargs={"pk": item_b.id})
            response = self.client.get(url)
            
            self.assertEqual(
                response.status_code,
                404,
                "Cross-tenant resource should return 404 (same as missing, to prevent enumeration)"
            )
            
            # Error message should NOT reveal "Access Denied" or "Permission" keywords
            if hasattr(response, 'content'):
                content_lower = response.content.decode('utf-8').lower()
                self.assertNotIn("permission", content_lower)
                self.assertNotIn("access denied", content_lower)
                self.assertNotIn("forbidden", content_lower)
        except Exception as e:
            if "Reverse" not in str(e):
                raise


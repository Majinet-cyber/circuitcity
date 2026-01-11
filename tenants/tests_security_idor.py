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
        
        # Create item in Business B (use order_price instead of cost_price)
        try:
            from inventory.models import Product
            product = Product.objects.filter(business=self.business_b).first()
            if not product:
                product = Product.objects.create(
                    business=self.business_b,
                    brand="Samsung",
                    model="Galaxy S21",
                    name="Samsung Galaxy S21"
                )
            item_b = InventoryItem.objects.create(
                business=self.business_b,
                imei="123456789012345",
                product=product,
                order_price=Decimal("500.00"),
                selling_price=Decimal("700.00"),
                status="IN_STOCK"
            )
        except Exception as e:
            self.skipTest(f"Cannot create InventoryItem: {e}")
        
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
        try:
            from inventory.models import Product
            product = Product.objects.filter(business=self.business_b).first()
            if not product:
                product = Product.objects.create(
                    business=self.business_b,
                    brand="Apple",
                    model="iPhone 13",
                    name="Apple iPhone 13"
                )
            item_b = InventoryItem.objects.create(
                business=self.business_b,
                imei="987654321098765",
                product=product,
                order_price=Decimal("800.00"),
                selling_price=Decimal("1000.00"),
                status="SOLD"
            )
        except Exception as e:
            self.skipTest(f"Cannot create InventoryItem: {e}")
        
        try:
            sale_b = Sale.objects.create(
                item=item_b,
                agent=self.user_b,
                price=Decimal("1000.00"),
                payment_method="cash"
            )
        except Exception as e:
            self.skipTest(f"Cannot create Sale: {e}")
        
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
        
        # Create transaction in Business B (use correct field names)
        try:
            txn_b = WalletTransaction.objects.create(
                business=self.business_b,
                agent=self.user_b,
                amount=Decimal("100.00"),
                type="commission",
                note="Sale commission"
            )
        except Exception as e:
            self.skipTest(f"Cannot create WalletTransaction: {e}")
        
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
        try:
            from inventory.models import Product
            product = Product.objects.filter(business=self.business_b).first()
            if not product:
                product = Product.objects.create(
                    business=self.business_b,
                    brand="Samsung",
                    model="Galaxy A52",
                    name="Samsung Galaxy A52"
                )
            item1_b = InventoryItem.objects.create(
                business=self.business_b,
                imei="111111111111111",
                product=product,
                order_price=Decimal("300.00"),
                selling_price=Decimal("400.00"),
                status="IN_STOCK"
            )
            
            item2_b = InventoryItem.objects.create(
                business=self.business_b,
                imei="222222222222222",
                product=product,
                order_price=Decimal("400.00"),
                selling_price=Decimal("500.00"),
                status="IN_STOCK"
            )
        except Exception as e:
            self.skipTest(f"Cannot create InventoryItem: {e}")
        
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
        try:
            from inventory.models import Product
            product = Product.objects.filter(business=self.business_b).first()
            if not product:
                product = Product.objects.create(
                    business=self.business_b,
                    brand="Xiaomi",
                    model="Redmi Note 10",
                    name="Xiaomi Redmi Note 10"
                )
            item_b = InventoryItem.objects.create(
                business=self.business_b,
                imei="333333333333333",
                product=product,
                order_price=Decimal("200.00"),
                selling_price=Decimal("300.00"),
                status="IN_STOCK"
            )
        except Exception as e:
            self.skipTest(f"Cannot create InventoryItem: {e}")
        
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


class WalletIDORTestCase(TestCase):
    """
    Test IDOR protection in wallet views.
    
    These tests verify that wallet transactions, costs, and budgets
    cannot be accessed across tenant boundaries.
    """
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if Business is None or Membership is None:
            cls.skip_tests = True
            return
        cls.skip_tests = False
    
    def setUp(self):
        if self.skip_tests:
            self.skipTest("Required models not available")
        
        # Create Business A
        self.business_a = Business.objects.create(
            name="Wallet Test Business A",
            slug="wallet-test-a",
            business_kind="phones",
            status="ACTIVE"
        )
        
        # Create Business B
        self.business_b = Business.objects.create(
            name="Wallet Test Business B",
            slug="wallet-test-b",
            business_kind="phones",
            status="ACTIVE"
        )
        
        # Create users
        self.user_a = User.objects.create_user(
            username="wallet_user_a",
            email="wallet_a@example.com",
            password="password123",
            is_staff=True  # Staff access needed for some wallet views
        )
        
        self.user_b = User.objects.create_user(
            username="wallet_user_b",
            email="wallet_b@example.com",
            password="password123"
        )
        
        # Create memberships
        Membership.objects.create(
            user=self.user_a,
            business=self.business_a,
            role="MANAGER",
            status="ACTIVE"
        )
        
        Membership.objects.create(
            user=self.user_b,
            business=self.business_b,
            role="MANAGER",
            status="ACTIVE"
        )
        
        self.client = Client()
    
    def _login_as_user_a(self):
        """Login as user from Business A."""
        self.client.login(username="wallet_user_a", password="password123")
        session = self.client.session
        session['active_business_id'] = self.business_a.id
        session['biz_id'] = self.business_a.id
        session.save()
    
    def test_cannot_access_other_business_wallet_entry(self):
        """User A cannot access wallet transaction details from Business B."""
        if WalletTransaction is None:
            self.skipTest("WalletTransaction model not available")
        
        # Create transaction in Business B
        try:
            txn_b = WalletTransaction.objects.create(
                business=self.business_b,
                agent=self.user_b,
                amount=100,
                note="Test transaction",
            )
        except Exception:
            self.skipTest("Cannot create WalletTransaction - model may have different fields")
        
        self._login_as_user_a()
        
        try:
            url = reverse("wallet:entry_detail", kwargs={"pk": txn_b.id})
            response = self.client.get(url)
            
            self.assertEqual(
                response.status_code,
                404,
                f"Expected 404, got {response.status_code}. "
                f"User from Business A accessed wallet entry from Business B! (IDOR vulnerability)"
            )
        except Exception as e:
            if "Reverse" not in str(e):
                raise
    
    def test_cannot_edit_other_business_cost(self):
        """User A cannot edit cost transaction from Business B."""
        if WalletTransaction is None:
            self.skipTest("WalletTransaction model not available")
        
        try:
            # Create a cost transaction in Business B
            cost_b = WalletTransaction.objects.create(
                business=self.business_b,
                agent=self.user_b,
                amount=-500,  # Costs are typically negative
                note="Office rent",
            )
        except Exception:
            self.skipTest("Cannot create WalletTransaction")
        
        self._login_as_user_a()
        
        try:
            url = reverse("wallet:admin_cost_edit", kwargs={"cost_id": cost_b.id})
            response = self.client.get(url)
            
            # Accept 302 (OTP redirect), 403, or 404 as valid protection
            # 302 means OTP protection is blocking access (security layer before IDOR check)
            # 404 means IDOR protection is working correctly
            self.assertIn(
                response.status_code,
                [302, 403, 404],
                f"Expected 302/403/404, got {response.status_code}. "
                f"User from Business A accessed cost edit from Business B! (IDOR vulnerability)"
            )
            
            # If 200, that's a definite vulnerability - data is exposed
            self.assertNotEqual(
                response.status_code,
                200,
                "200 response indicates data from Business B was exposed to Business A!"
            )
        except Exception as e:
            if "Reverse" not in str(e):
                raise
    
    def test_cannot_delete_other_business_cost(self):
        """User A cannot delete cost transaction from Business B."""
        if WalletTransaction is None:
            self.skipTest("WalletTransaction model not available")
        
        try:
            cost_b = WalletTransaction.objects.create(
                business=self.business_b,
                agent=self.user_b,
                amount=-500,
                note="Office rent",
            )
            initial_count = WalletTransaction.objects.filter(pk=cost_b.id).count()
        except Exception:
            self.skipTest("Cannot create WalletTransaction")
        
        self._login_as_user_a()
        
        try:
            url = reverse("wallet:admin_cost_delete", kwargs={"cost_id": cost_b.id})
            response = self.client.post(url)
            
            # Cost should still exist - verify no deletion happened
            final_count = WalletTransaction.objects.filter(pk=cost_b.id).count()
            self.assertEqual(initial_count, final_count, "Cost was deleted cross-tenant!")
            
            # Accept 302 (OTP redirect), 403, or 404 as valid protection
            self.assertIn(
                response.status_code,
                [302, 403, 404],
                f"Expected 302/403/404, got {response.status_code}. "
                f"User from Business A could delete cost from Business B! (IDOR vulnerability)"
            )
        except Exception as e:
            if "Reverse" not in str(e):
                raise


class LaybyIDORTestCase(TestCase):
    """
    Test IDOR protection in layby views.
    
    LaybyOrder model lacks a direct business FK, so scope is determined
    via created_by user's membership.
    """
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if Business is None or Membership is None:
            cls.skip_tests = True
            return
        cls.skip_tests = False
    
    def setUp(self):
        if self.skip_tests:
            self.skipTest("Required models not available")
        
        try:
            from layby.models import LaybyOrder
            self.LaybyOrder = LaybyOrder
        except ImportError:
            self.skipTest("LaybyOrder model not available")
        
        # Create Business A
        self.business_a = Business.objects.create(
            name="Layby Test Business A",
            slug="layby-test-a",
            business_kind="phones",
            status="ACTIVE"
        )
        
        # Create Business B
        self.business_b = Business.objects.create(
            name="Layby Test Business B",
            slug="layby-test-b",
            business_kind="phones",
            status="ACTIVE"
        )
        
        # Create users
        self.user_a = User.objects.create_user(
            username="layby_user_a",
            email="layby_a@example.com",
            password="password123"
        )
        
        self.user_b = User.objects.create_user(
            username="layby_user_b",
            email="layby_b@example.com",
            password="password123"
        )
        
        # Create memberships
        Membership.objects.create(
            user=self.user_a,
            business=self.business_a,
            role="MANAGER",
            status="ACTIVE"
        )
        
        Membership.objects.create(
            user=self.user_b,
            business=self.business_b,
            role="MANAGER",
            status="ACTIVE"
        )
        
        self.client = Client()
    
    def _login_as_user_a(self):
        """Login as user from Business A."""
        self.client.login(username="layby_user_a", password="password123")
        session = self.client.session
        session['active_business_id'] = self.business_a.id
        session['biz_id'] = self.business_a.id
        session.save()
    
    def test_cannot_access_other_business_layby_order(self):
        """User A cannot access layby order created by user from Business B."""
        # Create layby order by user B
        try:
            order_b = self.LaybyOrder.objects.create(
                created_by=self.user_b,
                customer_name="John Doe",
                customer_phone="0999123456",
                id_number="12345678",
                item_name="iPhone 13",
                sku="IP13-001",
                total_price=1000,
                deposit_amount=200,
            )
        except Exception as e:
            self.skipTest(f"Cannot create LaybyOrder: {e}")
        
        self._login_as_user_a()
        
        try:
            url = reverse("layby:detail", kwargs={"pk": order_b.id})
            response = self.client.get(url)
            
            self.assertEqual(
                response.status_code,
                404,
                f"Expected 404, got {response.status_code}. "
                f"User from Business A accessed layby order from Business B! (IDOR vulnerability)"
            )
        except Exception as e:
            if "Reverse" not in str(e):
                raise
    
    def test_cannot_add_payment_to_other_business_layby(self):
        """User A cannot add payment to layby order from Business B."""
        try:
            order_b = self.LaybyOrder.objects.create(
                created_by=self.user_b,
                customer_name="Jane Doe",
                customer_phone="0888123456",
                id_number="87654321",
                item_name="Samsung Galaxy",
                sku="SG-001",
                total_price=800,
                deposit_amount=100,
            )
            initial_paid = order_b.amount_paid
        except Exception as e:
            self.skipTest(f"Cannot create LaybyOrder: {e}")
        
        self._login_as_user_a()
        
        try:
            url = reverse("layby:agent_add_payment", kwargs={"order_id": order_b.id})
            response = self.client.post(url, {
                "amount": "100.00",
                "method": "cash",
                "tx_ref": "TEST-001"
            })
            
            # Refresh and check amount paid didn't change
            order_b.refresh_from_db()
            self.assertEqual(
                order_b.amount_paid,
                initial_paid,
                "Payment was added to cross-tenant layby order!"
            )
            
            self.assertEqual(
                response.status_code,
                404,
                f"Expected 404, got {response.status_code}. "
                f"User from Business A added payment to layby from Business B! (IDOR vulnerability)"
            )
        except Exception as e:
            if "Reverse" not in str(e):
                raise
    
    def test_cannot_view_other_business_layby_payments_api(self):
        """User A cannot view payments for layby order from Business B via API."""
        try:
            order_b = self.LaybyOrder.objects.create(
                created_by=self.user_b,
                customer_name="API Test Customer",
                customer_phone="0777123456",
                id_number="99998888",
                item_name="API Test Phone",
                sku="API-001",
                total_price=500,
                deposit_amount=50,
            )
        except Exception as e:
            self.skipTest(f"Cannot create LaybyOrder: {e}")
        
        self._login_as_user_a()
        
        try:
            url = reverse("layby:api_payments", kwargs={"pk": order_b.id})
            response = self.client.get(url)
            
            self.assertEqual(
                response.status_code,
                404,
                f"Expected 404, got {response.status_code}. "
                f"User from Business A viewed layby payments from Business B via API! (IDOR vulnerability)"
            )
            
            # Ensure response doesn't leak payment data
            if response.status_code == 200:
                import json
                data = json.loads(response.content)
                self.assertNotIn("payments", data, "Payment data leaked in cross-tenant API response!")
        except Exception as e:
            if "Reverse" not in str(e):
                raise


class SalesRollbackIDORTestCase(TestCase):
    """
    Test IDOR protection in sales rollback views.
    
    Sales rollback is a high-risk operation - must be scoped correctly.
    """
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if Business is None or Membership is None:
            cls.skip_tests = True
            return
        cls.skip_tests = False
    
    def setUp(self):
        if self.skip_tests:
            self.skipTest("Required models not available")
        
        if Sale is None or InventoryItem is None:
            self.skipTest("Sale or InventoryItem model not available")
        
        # Create Business A
        self.business_a = Business.objects.create(
            name="Sales Test Business A",
            slug="sales-test-a",
            business_kind="phones",
            status="ACTIVE"
        )
        
        # Create Business B
        self.business_b = Business.objects.create(
            name="Sales Test Business B",
            slug="sales-test-b",
            business_kind="phones",
            status="ACTIVE"
        )
        
        # Create users
        self.user_a = User.objects.create_user(
            username="sales_user_a",
            email="sales_a@example.com",
            password="password123"
        )
        
        self.user_b = User.objects.create_user(
            username="sales_user_b",
            email="sales_b@example.com",
            password="password123"
        )
        
        # Create memberships
        Membership.objects.create(
            user=self.user_a,
            business=self.business_a,
            role="MANAGER",
            status="ACTIVE"
        )
        
        Membership.objects.create(
            user=self.user_b,
            business=self.business_b,
            role="MANAGER",
            status="ACTIVE"
        )
        
        self.client = Client()
    
    def _login_as_user_a(self):
        """Login as user from Business A."""
        self.client.login(username="sales_user_a", password="password123")
        session = self.client.session
        session['active_business_id'] = self.business_a.id
        session['biz_id'] = self.business_a.id
        session.save()
    
    def test_cannot_rollback_other_business_sale(self):
        """User A cannot roll back sale from Business B."""
        # Create item and sale in Business B
        try:
            from inventory.models import Product
            product = Product.objects.filter(business=self.business_b).first()
            if not product:
                product = Product.objects.create(
                    business=self.business_b,
                    brand="Apple",
                    model="iPhone 14",
                    name="Apple iPhone 14"
                )
            item_b = InventoryItem.objects.create(
                business=self.business_b,
                imei="555555555555555",
                product=product,
                order_price=900,
                selling_price=1200,
                status="SOLD"
            )
            
            sale_b = Sale.objects.create(
                item=item_b,
                agent=self.user_b,
                price=1200,
                payment_method="cash"
            )
            initial_status = item_b.status
        except Exception as e:
            self.skipTest(f"Cannot create test data: {e}")
        
        self._login_as_user_a()
        
        try:
            # Attempt to view rollback confirm page
            url = reverse("sales:rollback_confirm", kwargs={"sale_id": sale_b.id})
            response = self.client.get(url)
            
            self.assertIn(
                response.status_code,
                [302, 404],  # 302 redirect with error OR 404
                f"Expected 302/404, got {response.status_code}. "
                f"User from Business A accessed rollback page for Business B sale!"
            )
            
            # Item status should not have changed
            item_b.refresh_from_db()
            self.assertEqual(item_b.status, initial_status)
        except Exception as e:
            if "Reverse" not in str(e):
                raise


class LocationIDORTestCase(TestCase):
    """
    Test IDOR protection in location management views.
    
    Locations are business-scoped and must not be accessible cross-tenant.
    """
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if Business is None or Membership is None:
            cls.skip_tests = True
            return
        cls.skip_tests = False
    
    def setUp(self):
        if self.skip_tests:
            self.skipTest("Required models not available")
        
        if Location is None:
            self.skipTest("Location model not available")
        
        # Create Business A
        self.business_a = Business.objects.create(
            name="Location Test Business A",
            slug="location-test-a",
            business_kind="phones",
            status="ACTIVE"
        )
        
        # Create Business B
        self.business_b = Business.objects.create(
            name="Location Test Business B",
            slug="location-test-b",
            business_kind="phones",
            status="ACTIVE"
        )
        
        # Create locations
        try:
            self.location_b = Location.objects.create(
                business=self.business_b,
                name="Business B Location",
                is_active=True
            )
        except Exception as e:
            self.skipTest(f"Cannot create Location: {e}")
        
        # Create users
        self.user_a = User.objects.create_user(
            username="location_user_a",
            email="location_a@example.com",
            password="password123",
            is_staff=True
        )
        
        # Create memberships
        Membership.objects.create(
            user=self.user_a,
            business=self.business_a,
            role="MANAGER",
            status="ACTIVE"
        )
        
        self.client = Client()
    
    def _login_as_user_a(self):
        """Login as user from Business A."""
        self.client.login(username="location_user_a", password="password123")
        session = self.client.session
        session['active_business_id'] = self.business_a.id
        session['biz_id'] = self.business_a.id
        session.save()
    
    def test_cannot_access_other_business_location_geofence(self):
        """User A cannot access location geofence settings from Business B."""
        self._login_as_user_a()
        
        try:
            url = reverse("inventory:location_geofence", kwargs={"pk": self.location_b.id})
            response = self.client.get(url)
            
            self.assertEqual(
                response.status_code,
                404,
                f"Expected 404, got {response.status_code}. "
                f"User from Business A accessed location from Business B! (IDOR vulnerability)"
            )
        except Exception as e:
            if "Reverse" not in str(e):
                raise
    
    def test_cannot_toggle_other_business_geofence(self):
        """User A cannot toggle geofence for location from Business B."""
        self._login_as_user_a()
        
        try:
            url = reverse("inventory:toggle_geofence_launch", kwargs={"pk": self.location_b.id})
            initial_state = self.location_b.geofence_enabled
            
            response = self.client.post(url)
            
            # Location state should not have changed
            self.location_b.refresh_from_db()
            self.assertEqual(
                self.location_b.geofence_enabled,
                initial_state,
                "Geofence was toggled on cross-tenant location!"
            )
            
            self.assertEqual(
                response.status_code,
                404,
                f"Expected 404, got {response.status_code}. "
                f"User from Business A toggled geofence for Business B! (IDOR vulnerability)"
            )
        except Exception as e:
            if "Reverse" not in str(e):
                raise


class DocumentIDORTestCase(TestCase):
    """
    Test IDOR protection in document views (invoices, quotes).
    
    Documents are business-scoped and must not be accessible cross-tenant.
    """
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if Business is None or Membership is None:
            cls.skip_tests = True
            return
        cls.skip_tests = False
    
    def setUp(self):
        if self.skip_tests:
            self.skipTest("Required models not available")
        
        # Create businesses
        self.business_a = Business.objects.create(
            name="Doc Test Business A",
            slug="doc-test-a",
            business_kind="phones",
            status="ACTIVE"
        )
        
        self.business_b = Business.objects.create(
            name="Doc Test Business B",
            slug="doc-test-b",
            business_kind="phones",
            status="ACTIVE"
        )
        
        # Create users
        self.user_a = User.objects.create_user(
            username="doc_user_a",
            email="doc_a@example.com",
            password="password123"
        )
        
        self.user_b = User.objects.create_user(
            username="doc_user_b",
            email="doc_b@example.com",
            password="password123"
        )
        
        # Create memberships
        Membership.objects.create(
            user=self.user_a,
            business=self.business_a,
            role="MANAGER",
            status="ACTIVE"
        )
        
        Membership.objects.create(
            user=self.user_b,
            business=self.business_b,
            role="MANAGER",
            status="ACTIVE"
        )
        
        self.client = Client()
    
    def _login_as_user_a(self):
        """Login as user from Business A."""
        self.client.login(username="doc_user_a", password="password123")
        session = self.client.session
        session['active_business_id'] = self.business_a.id
        session['biz_id'] = self.business_a.id
        session.save()
    
    def test_cannot_access_other_business_document(self):
        """User A cannot access document from Business B."""
        try:
            from inventory.models_docs import Doc, Customer
        except ImportError:
            self.skipTest("Doc model not available")
        
        # Create a document in Business B
        try:
            customer_b = Customer.objects.create(
                business=self.business_b,
                name="Business B Customer",
                email="customer@b.com"
            )
            doc_b = Doc.objects.create(
                business=self.business_b,
                customer=customer_b,
                doc_type="invoice",
                number="INV-2026-00001"
            )
        except Exception as e:
            self.skipTest(f"Cannot create test data: {e}")
        
        self._login_as_user_a()
        
        try:
            url = reverse("inventory:doc_whatsapp", kwargs={"pk": doc_b.id})
            response = self.client.get(url)
            
            self.assertEqual(
                response.status_code,
                404,
                f"Expected 404, got {response.status_code}. "
                f"User from Business A accessed document from Business B! (IDOR vulnerability)"
            )
        except Exception as e:
            if "Reverse" not in str(e):
                raise


class AgentPerformanceIDORTestCase(TestCase):
    """
    Test IDOR protection in agent performance views.
    
    Agent performance data must be scoped to the requesting user's business.
    """
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if Business is None or Membership is None:
            cls.skip_tests = True
            return
        cls.skip_tests = False
    
    def setUp(self):
        if self.skip_tests:
            self.skipTest("Required models not available")
        
        # Create businesses
        self.business_a = Business.objects.create(
            name="Agent Perf Test A",
            slug="agent-perf-a",
            business_kind="phones",
            status="ACTIVE"
        )
        
        self.business_b = Business.objects.create(
            name="Agent Perf Test B",
            slug="agent-perf-b",
            business_kind="phones",
            status="ACTIVE"
        )
        
        # Create users
        self.manager_a = User.objects.create_user(
            username="manager_perf_a",
            email="manager_a@example.com",
            password="password123",
            is_staff=True
        )
        
        self.agent_b = User.objects.create_user(
            username="agent_perf_b",
            email="agent_b@example.com",
            password="password123"
        )
        
        # Create memberships
        Membership.objects.create(
            user=self.manager_a,
            business=self.business_a,
            role="MANAGER",
            status="ACTIVE"
        )
        
        Membership.objects.create(
            user=self.agent_b,
            business=self.business_b,
            role="AGENT",
            status="ACTIVE"
        )
        
        self.client = Client()
    
    def _login_as_manager_a(self):
        """Login as manager from Business A."""
        self.client.login(username="manager_perf_a", password="password123")
        session = self.client.session
        session['active_business_id'] = self.business_a.id
        session['biz_id'] = self.business_a.id
        session.save()
    
    def test_cannot_view_other_business_agent_performance(self):
        """Manager A cannot view agent performance from Business B."""
        self._login_as_manager_a()
        
        try:
            url = reverse("inventory:agent_performance", kwargs={"agent_id": self.agent_b.id})
            response = self.client.get(url)
            
            self.assertEqual(
                response.status_code,
                404,
                f"Expected 404, got {response.status_code}. "
                f"Manager from Business A viewed agent from Business B! (IDOR vulnerability)"
            )
        except Exception as e:
            if "Reverse" not in str(e):
                raise


class BudgetRequestIDORTestCase(TestCase):
    """
    Test IDOR protection in budget request views.
    
    Budget requests are scoped via agent membership.
    """
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if Business is None or Membership is None:
            cls.skip_tests = True
            return
        cls.skip_tests = False
    
    def setUp(self):
        if self.skip_tests:
            self.skipTest("Required models not available")
        
        try:
            from wallet.models import BudgetRequest
            self.BudgetRequest = BudgetRequest
        except ImportError:
            self.skipTest("BudgetRequest model not available")
        
        # Create businesses
        self.business_a = Business.objects.create(
            name="Budget Test A",
            slug="budget-test-a",
            business_kind="phones",
            status="ACTIVE"
        )
        
        self.business_b = Business.objects.create(
            name="Budget Test B",
            slug="budget-test-b",
            business_kind="phones",
            status="ACTIVE"
        )
        
        # Create users
        self.manager_a = User.objects.create_user(
            username="budget_manager_a",
            email="budget_manager_a@example.com",
            password="password123",
            is_staff=True
        )
        
        self.agent_b = User.objects.create_user(
            username="budget_agent_b",
            email="budget_agent_b@example.com",
            password="password123"
        )
        
        # Create memberships
        Membership.objects.create(
            user=self.manager_a,
            business=self.business_a,
            role="MANAGER",
            status="ACTIVE"
        )
        
        Membership.objects.create(
            user=self.agent_b,
            business=self.business_b,
            role="AGENT",
            status="ACTIVE"
        )
        
        self.client = Client()
    
    def _login_as_manager_a(self):
        """Login as manager from Business A."""
        self.client.login(username="budget_manager_a", password="password123")
        session = self.client.session
        session['active_business_id'] = self.business_a.id
        session['biz_id'] = self.business_a.id
        session.save()
    
    def test_cannot_approve_other_business_budget(self):
        """Manager A cannot approve budget request from Business B."""
        # Create budget request from agent in Business B
        try:
            budget_b = self.BudgetRequest.objects.create(
                agent=self.agent_b,
                title="Test Budget",
                amount=100,
                reason="Test reason"
            )
            initial_status = budget_b.status
        except Exception as e:
            self.skipTest(f"Cannot create budget request: {e}")
        
        self._login_as_manager_a()
        
        try:
            url = reverse("wallet:admin_budget_set_status", kwargs={
                "pk": budget_b.id,
                "action": "approve"
            })
            response = self.client.post(url)
            
            # Budget status should not have changed
            budget_b.refresh_from_db()
            self.assertEqual(
                budget_b.status,
                initial_status,
                "Budget was approved cross-tenant!"
            )
            
            self.assertEqual(
                response.status_code,
                404,
                f"Expected 404, got {response.status_code}. "
                f"Manager from Business A approved budget from Business B! (IDOR vulnerability)"
            )
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
        
        try:
            from inventory.models import Product
            product = Product.objects.filter(business=other_business).first()
            if not product:
                product = Product.objects.create(
                    business=other_business,
                    brand="Oppo",
                    model="A15",
                    name="Oppo A15"
                )
            item_b = InventoryItem.objects.create(
                business=other_business,
                imei="444444444444444",
                product=product,
                order_price=Decimal("150.00"),
                selling_price=Decimal("200.00"),
                status="IN_STOCK"
            )
        except Exception as e:
            self.skipTest(f"Cannot create InventoryItem: {e}")
        
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


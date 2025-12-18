# sales/tests/test_fast_sell.py
"""
Tests for Fast Sell feature and Liquor Barman attribution.
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone

from tenants.models import Business, Membership
from inventory.models import MerchProduct, Location
from inventory.models_verticals import LiquorSale
from sales.models import LiquorSaleAttribution

User = get_user_model()


class FastSellLookupTests(TestCase):
    """Tests for Fast Sell product lookup"""
    
    def setUp(self):
        self.client = Client()
        
        # Create business
        self.business = Business.objects.create(
            name="Test Liquor Store",
            slug="test-liquor",
            business_kind="liquor"
        )
        
        # Create location
        self.location = Location.objects.create(
            name="Main Store",
            business=self.business
        )
        
        # Create user
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123"
        )
        
        # Attach user to business via Membership
        Membership.objects.create(
            user=self.user,
            business=self.business,
            location=self.location,
            role='AGENT',
            status='ACTIVE'
        )
        
        # Create test product with barcode
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Test Beer",
            kind="liquor",
            category="beer",
            barcode="123456789",
            quantity_in_stock=10,
            cost_price=Decimal("500.00"),
            selling_price=Decimal("800.00"),
            is_active=True
        )
        
        self.client.login(username="testuser", password="testpass123")
    
    def test_lookup_returns_found_product(self):
        """Lookup should return product when barcode matches"""
        response = self.client.get(
            '/verticals/liquor/api/fast-sell/lookup/',
            {'barcode': '123456789'}
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertTrue(data['found'])
        self.assertEqual(data['product']['name'], 'Test Beer')
        self.assertEqual(data['stock_qty'], 10)
        self.assertEqual(data['selling_price'], 800.0)
        self.assertFalse(data['needs_price'])
    
    def test_lookup_returns_not_found_for_missing_barcode(self):
        """Lookup should return not found for non-existent barcode"""
        response = self.client.get(
            '/verticals/liquor/api/fast-sell/lookup/',
            {'barcode': '999999999'}
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertFalse(data['found'])
    
    def test_lookup_returns_needs_price_when_price_missing(self):
        """Lookup should indicate when selling price is missing"""
        self.product.selling_price = Decimal("0.00")
        self.product.save()
        
        response = self.client.get(
            '/verticals/liquor/api/fast-sell/lookup/',
            {'barcode': '123456789'}
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertTrue(data['found'])
        self.assertTrue(data['needs_price'])


class FastSellCreateTests(TestCase):
    """Tests for Fast Sell sale creation"""
    
    def setUp(self):
        self.client = Client()
        
        # Create business
        self.business = Business.objects.create(
            name="Test Liquor Store",
            slug="test-liquor",
            business_kind="liquor"
        )
        
        # Create location
        self.location = Location.objects.create(
            name="Main Store",
            business=self.business
        )
        
        # Create user
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123"
        )
        
        # Attach user to business via Membership
        Membership.objects.create(
            user=self.user,
            business=self.business,
            location=self.location,
            role='AGENT',
            status='ACTIVE'
        )
        
        # Create test product
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Test Beer",
            kind="liquor",
            category="beer",
            barcode="123456789",
            quantity_in_stock=10,
            cost_price=Decimal("500.00"),
            selling_price=Decimal("800.00"),
            is_active=True
        )
        
        self.client.login(username="testuser", password="testpass123")
    
    def test_fast_sell_decrements_stock(self):
        """Fast sell should decrement product stock"""
        response = self.client.post(
            '/verticals/liquor/api/fast-sell/sell/',
            data={'barcode': '123456789', 'quantity': 2, 'payment_method': 'cash'},
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_in_stock, 8)
    
    def test_fast_sell_creates_sale_record(self):
        """Fast sell should create LiquorSale record"""
        response = self.client.post(
            '/verticals/liquor/api/fast-sell/sell/',
            data={'barcode': '123456789', 'quantity': 1, 'payment_method': 'cash'},
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertIn('sale_id', data)
        
        # Verify sale exists
        sale = LiquorSale.objects.get(id=data['sale_id'])
        self.assertEqual(sale.quantity, 1)
        self.assertEqual(sale.unit_price, Decimal("800.00"))
        self.assertEqual(sale.payment_method, "cash")
    
    def test_fast_sell_updates_price_when_provided(self):
        """Fast sell should update product price when provided"""
        # Set product price to 0
        self.product.selling_price = Decimal("0.00")
        self.product.save()
        
        response = self.client.post(
            '/verticals/liquor/api/fast-sell/sell/',
            data={
                'barcode': '123456789',
                'quantity': 1,
                'payment_method': 'cash',
                'selling_price': '850.00'
            },
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        
        self.product.refresh_from_db()
        self.assertEqual(self.product.selling_price, Decimal("850.00"))


class LiquorBarmanAttributionTests(TestCase):
    """Tests for Liquor Barman sale attribution"""
    
    def setUp(self):
        self.client = Client()
        
        # Create business
        self.business = Business.objects.create(
            name="Test Liquor Store",
            slug="test-liquor",
            business_kind="liquor"
        )
        
        # Create location
        self.location = Location.objects.create(
            name="Main Store",
            business=self.business
        )
        
        # Create barman
        self.barman = User.objects.create_user(
            username="barman",
            password="testpass123"
        )
        
        # Create agent
        self.agent = User.objects.create_user(
            username="agent1",
            password="testpass123"
        )
        
        # Attach to business via Membership
        Membership.objects.create(
            user=self.barman,
            business=self.business,
            location=self.location,
            role='AGENT',
            status='ACTIVE'
        )
        Membership.objects.create(
            user=self.agent,
            business=self.business,
            location=self.location,
            role='AGENT',
            status='ACTIVE'
        )
        
        # Add LIQUOR_BARMAN role
        from django.contrib.auth.models import Group
        barman_group = Group.objects.create(name=f"biz:{self.business.pk}:LIQUOR_BARMAN")
        self.barman.groups.add(barman_group)
        
        # Add AGENT role
        agent_group = Group.objects.create(name=f"biz:{self.business.pk}:AGENT")
        self.agent.groups.add(agent_group)
        
        # Create test product
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Test Beer",
            kind="liquor",
            category="beer",
            barcode="123456789",
            quantity_in_stock=10,
            cost_price=Decimal("500.00"),
            selling_price=Decimal("800.00"),
            is_active=True
        )
    
    def test_barman_can_assign_sale_to_agent(self):
        """Barman should be able to assign sale to agent"""
        self.client.login(username="barman", password="testpass123")
        
        response = self.client.post(
            '/verticals/liquor/api/fast-sell/sell/',
            data={
                'barcode': '123456789',
                'quantity': 1,
                'payment_method': 'cash',
                'attributed_to_agent_id': self.agent.id
            },
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        
        # Verify attribution was created
        attribution = LiquorSaleAttribution.objects.get(liquor_sale_id=data['sale_id'])
        self.assertEqual(attribution.attributed_by, self.barman)
        self.assertEqual(attribution.attributed_to, self.agent)
        self.assertEqual(attribution.status, LiquorSaleAttribution.STATUS_PENDING)
    
    def test_attribution_can_be_reconciled(self):
        """Attribution should be markable as reconciled"""
        # Create attribution
        sale = LiquorSale.objects.create(
            business=self.business,
            product=self.product,
            unit="bottle",
            quantity=1,
            unit_price=Decimal("800.00"),
            total_price=Decimal("800.00"),
            unit_cost=Decimal("500.00"),
            total_cost=Decimal("500.00"),
            payment_method="cash",
            sold_by=self.barman,
        )
        
        attribution = LiquorSaleAttribution.objects.create(
            liquor_sale_id=sale.id,
            business=self.business,
            attributed_by=self.barman,
            attributed_to=self.agent,
            sale_amount=Decimal("800.00"),
            status=LiquorSaleAttribution.STATUS_PENDING
        )
        
        # Mark as reconciled
        attribution.mark_reconciled(self.barman)
        
        # Verify status changed
        attribution.refresh_from_db()
        self.assertEqual(attribution.status, LiquorSaleAttribution.STATUS_RECONCILED)
        self.assertEqual(attribution.reconciled_by, self.barman)
        self.assertIsNotNone(attribution.reconciled_at)
    
    def test_agent_sees_pending_count(self):
        """Agent should see count of pending attributions"""
        # Create multiple attributions
        for i in range(3):
            sale = LiquorSale.objects.create(
                business=self.business,
                product=self.product,
                unit="bottle",
                quantity=1,
                unit_price=Decimal("800.00"),
                total_price=Decimal("800.00"),
                unit_cost=Decimal("500.00"),
                total_cost=Decimal("500.00"),
                payment_method="cash",
                sold_by=self.barman,
            )
            
            LiquorSaleAttribution.objects.create(
                liquor_sale_id=sale.id,
                business=self.business,
                attributed_by=self.barman,
                attributed_to=self.agent,
                sale_amount=Decimal("800.00"),
                status=LiquorSaleAttribution.STATUS_PENDING
            )
        
        # Count pending attributions for agent
        pending_count = LiquorSaleAttribution.objects.filter(
            business=self.business,
            attributed_to=self.agent,
            status=LiquorSaleAttribution.STATUS_PENDING
        ).count()
        
        self.assertEqual(pending_count, 3)


class FastSellPermissionTests(TestCase):
    """Tests for Fast Sell permissions"""
    
    def setUp(self):
        self.client = Client()
        
        # Create business
        self.business = Business.objects.create(
            name="Test Liquor Store",
            slug="test-liquor",
            business_kind="liquor"
        )
    
    def test_unauthenticated_cannot_access_fast_sell(self):
        """Unauthenticated users should not access Fast Sell"""
        response = self.client.get('/verticals/liquor/fast-sell/')
        self.assertEqual(response.status_code, 302)  # Redirect to login
    
    def test_wrong_vertical_cannot_access_liquor_fast_sell(self):
        """Users from other verticals should not access liquor Fast Sell"""
        # Create pharmacy business
        pharmacy_business = Business.objects.create(
            name="Test Pharmacy",
            slug="test-pharmacy",
            business_kind="pharmacy"
        )
        
        location = Location.objects.create(
            name="Main Store",
            business=pharmacy_business
        )
        
        user = User.objects.create_user(
            username="pharmacist",
            password="testpass123"
        )
        
        Membership.objects.create(
            user=user,
            business=pharmacy_business,
            location=location,
            role='AGENT',
            status='ACTIVE'
        )
        
        self.client.login(username="pharmacist", password="testpass123")
        
        # Should not access liquor fast sell
        response = self.client.get('/verticals/liquor/fast-sell/')
        self.assertIn(response.status_code, [302, 403, 404])


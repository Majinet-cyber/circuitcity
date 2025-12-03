# tests/test_verticals_liquor.py
"""
Tests for liquor store functionality: products, sales, credits, payments.
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct
from inventory.models_verticals import (
    LiquorSale, LiquorCredit, LiquorCreditPayment, LiquorStockEditRequest,
    LiquorWalletEntry, LiquorUnitType, LiquorSaleType, LiquorCreditStatus,
    LiquorCreditPaymentStatus
)
from inventory.liquor_seed import (
    create_default_liquor_catalog, should_seed_liquor_products, get_catalog_summary
)
from tenants.models import Business

User = get_user_model()


@pytest.fixture
def business():
    """Create a test liquor business"""
    return Business.objects.create(
        name="Test Liquor Store",
        slug="test-liquor",
        status="ACTIVE",
        business_kind=BusinessKind.LIQUOR
    )


@pytest.fixture
def manager(business):
    """Create a manager user"""
    user = User.objects.create_user(username="manager", password="pass")
    user.is_staff = False
    user.save()
    return user


@pytest.fixture
def bartender(business):
    """Create a bartender user"""
    user = User.objects.create_user(username="bartender", password="pass")
    user.is_staff = False
    user.save()
    return user


@pytest.fixture
def liquor_product(business):
    """Create a liquor product with shots"""
    return MerchProduct.objects.create(
        business=business,
        name="Test Whiskey",
        kind=BusinessKind.LIQUOR,
        category="spirits",
        has_shots=True,
        shots_per_bottle=25,
        barman_shots_reserved=2,
        price_per_bottle=Decimal("15000.00"),
        price_per_shot=Decimal("750.00"),
        is_active=True
    )


@pytest.mark.django_db
class TestLiquorProduct:
    """Test liquor product configuration"""
    
    def test_sellable_shots_calculation(self, liquor_product):
        """Test that sellable shots = total - reserved"""
        assert liquor_product.sellable_shots_per_bottle == 23
    
    def test_product_with_no_shots(self, business):
        """Test product without shots"""
        product = MerchProduct.objects.create(
            business=business,
            name="Beer",
            kind=BusinessKind.LIQUOR,
            category="beer",
            has_shots=False,
            price_per_bottle=Decimal("2000.00"),
            is_active=True
        )
        assert product.sellable_shots_per_bottle == 0


@pytest.mark.django_db
class TestLiquorSales:
    """Test liquor sales (bottle vs shot)"""
    
    def test_bottle_sale(self, business, liquor_product, bartender):
        """Test selling a bottle"""
        sale = LiquorSale.objects.create(
            business=business,
            product=liquor_product,
            unit=LiquorUnitType.BOTTLE,
            quantity=2,
            unit_price=liquor_product.price_per_bottle,
            sold_by=bartender
        )
        
        assert sale.total_price == Decimal("30000.00")  # 2 × 15000
        assert sale.is_credit is False
        assert sale.sale_type == LiquorSaleType.SALE
    
    def test_shot_sale(self, business, liquor_product, bartender):
        """Test selling shots"""
        sale = LiquorSale.objects.create(
            business=business,
            product=liquor_product,
            unit=LiquorUnitType.SHOT,
            quantity=10,
            unit_price=liquor_product.price_per_shot,
            sold_by=bartender
        )
        
        assert sale.total_price == Decimal("7500.00")  # 10 × 750
        assert sale.unit == LiquorUnitType.SHOT
    
    def test_credit_sale(self, business, liquor_product, bartender):
        """Test credit sale creates credit record"""
        sale = LiquorSale.objects.create(
            business=business,
            product=liquor_product,
            unit=LiquorUnitType.BOTTLE,
            quantity=1,
            unit_price=liquor_product.price_per_bottle,
            sale_type=LiquorSaleType.CREDIT,
            sold_by=bartender
        )
        
        assert sale.is_credit is True
        assert sale.sale_type == LiquorSaleType.CREDIT


@pytest.mark.django_db
class TestLiquorCredit:
    """Test credit system"""
    
    def test_create_credit(self, business, manager):
        """Test creating a credit record"""
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name="John Doe",
            customer_phone="0999123456",
            amount=Decimal("10000.00"),
            created_by=manager
        )
        
        assert credit.status == LiquorCreditStatus.OPEN
        assert credit.balance == Decimal("10000.00")
        assert credit.amount_paid == Decimal("0.00")
    
    def test_credit_payment_updates_balance(self, business, manager):
        """Test that payment updates credit balance"""
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name="Jane Doe",
            customer_phone="0999654321",
            amount=Decimal("5000.00"),
            created_by=manager
        )
        
        # Simulate payment
        credit.amount_paid = Decimal("2000.00")
        credit.save()
        credit.update_status()
        
        assert credit.balance == Decimal("3000.00")
        assert credit.status == LiquorCreditStatus.PARTIAL
    
    def test_credit_fully_settled(self, business, manager):
        """Test credit marked as settled when fully paid"""
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name="Bob Smith",
            customer_phone="0999111222",
            amount=Decimal("8000.00"),
            created_by=manager
        )
        
        credit.amount_paid = Decimal("8000.00")
        credit.save()
        credit.update_status()
        
        assert credit.status == LiquorCreditStatus.SETTLED
        assert credit.balance == Decimal("0.00")
        assert credit.settled_at is not None


@pytest.mark.django_db
class TestLiquorCreditPayment:
    """Test credit payment approval workflow"""
    
    def test_bartender_submits_payment(self, business, manager, bartender):
        """Test bartender submits payment with proof"""
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name="Alice",
            customer_phone="0999999999",
            amount=Decimal("5000.00"),
            created_by=manager
        )
        
        payment = LiquorCreditPayment.objects.create(
            credit=credit,
            amount=Decimal("2000.00"),
            transaction_id="TXN12345",
            paid_by=bartender
        )
        
        assert payment.status == LiquorCreditPaymentStatus.PENDING
        assert payment.reviewed_by is None
    
    def test_manager_approves_payment(self, business, manager, bartender):
        """Test manager approves payment"""
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name="Charlie",
            customer_phone="0999888777",
            amount=Decimal("10000.00"),
            created_by=manager
        )
        
        payment = LiquorCreditPayment.objects.create(
            credit=credit,
            amount=Decimal("5000.00"),
            transaction_id="TXN67890",
            paid_by=bartender
        )
        
        # Manager approves
        payment.approve(manager)
        
        assert payment.status == LiquorCreditPaymentStatus.APPROVED
        assert payment.reviewed_by == manager
        assert payment.reviewed_at is not None
        
        # Check credit updated
        credit.refresh_from_db()
        assert credit.amount_paid == Decimal("5000.00")
        assert credit.status == LiquorCreditStatus.PARTIAL
    
    def test_manager_rejects_payment(self, business, manager, bartender):
        """Test manager rejects payment"""
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name="David",
            customer_phone="0999777666",
            amount=Decimal("3000.00"),
            created_by=manager
        )
        
        payment = LiquorCreditPayment.objects.create(
            credit=credit,
            amount=Decimal("1000.00"),
            transaction_id="TXN11111",
            paid_by=bartender
        )
        
        # Manager rejects
        payment.reject(manager, reason="Invalid proof")
        
        assert payment.status == LiquorCreditPaymentStatus.REJECTED
        assert payment.review_reason == "Invalid proof"
        
        # Credit should not be updated
        credit.refresh_from_db()
        assert credit.amount_paid == Decimal("0.00")


@pytest.mark.django_db
class TestLiquorStockEditRequest:
    """Test stock edit request workflow"""
    
    def test_bartender_requests_edit(self, business, liquor_product, bartender):
        """Test bartender creates stock edit request"""
        request = LiquorStockEditRequest.objects.create(
            business=business,
            product=liquor_product,
            requested_changes={"quantity": 50},
            reason="Received new stock",
            requested_by=bartender
        )
        
        assert request.status == "pending"
        assert request.reviewed_by is None


@pytest.mark.django_db
class TestLiquorWalletEntry:
    """Test wallet entries for liquor business"""
    
    def test_create_income_entry(self, business, liquor_product, bartender):
        """Test creating income wallet entry from sale"""
        sale = LiquorSale.objects.create(
            business=business,
            product=liquor_product,
            unit=LiquorUnitType.BOTTLE,
            quantity=1,
            unit_price=Decimal("15000.00"),
            sold_by=bartender
        )
        
        entry = LiquorWalletEntry.objects.create(
            business=business,
            amount=sale.total_price,
            description=f"Sale of {liquor_product.name}",
            entry_type="income",
            related_sale=sale,
            created_by=bartender
        )
        
        assert entry.entry_type == "income"
        assert entry.amount == Decimal("15000.00")


@pytest.mark.django_db
class TestLiquorViews:
    """Test liquor view endpoints"""
    
    def test_sell_liquor_page_loads(self, client, business, manager, liquor_product):
        """Test that /liquor/sell/ loads successfully"""
        from tenants.models import Membership
        
        # Create membership for manager (managers can have null location)
        Membership.objects.create(
            user=manager,
            business=business,
            role="MANAGER",
            status="ACTIVE",
            location=None
        )
        
        # Login
        client.force_login(manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Access sell page
        response = client.get('/liquor/sell/')
        
        assert response.status_code == 200
        assert b'Sell Liquor' in response.content or b'sell' in response.content.lower()
    
    def test_credits_list_page_loads(self, client, business, manager):
        """Test that /liquor/credits/ loads successfully"""
        from tenants.models import Membership
        
        # Create membership for manager
        Membership.objects.create(
            user=manager,
            business=business,
            role="MANAGER",
            status="ACTIVE",
            location=None
        )
        
        # Login
        client.force_login(manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Access credits page
        response = client.get('/liquor/credits/')
        
        assert response.status_code == 200
        assert b'Credit' in response.content or b'credit' in response.content.lower()
    
    def test_sales_list_page_loads(self, client, business, manager):
        """Test that /liquor/sales/ loads successfully"""
        from tenants.models import Membership
        
        # Create membership for manager
        Membership.objects.create(
            user=manager,
            business=business,
            role="MANAGER",
            status="ACTIVE",
            location=None
        )
        
        # Login
        client.force_login(manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Access sales list page
        response = client.get('/liquor/sales/')
        
        assert response.status_code == 200
    
    def test_liquor_routes_require_liquor_business(self, client, manager):
        """Test that liquor routes require a liquor business"""
        from tenants.models import Membership
        
        # Create a phones business instead
        phones_business = Business.objects.create(
            name="Test Phones Store",
            slug="test-phones",
            status="ACTIVE",
            business_kind=BusinessKind.PHONES
        )
        
        Membership.objects.create(
            user=manager,
            business=phones_business,
            role="MANAGER",
            status="ACTIVE",
            location=None
        )
        
        # Login
        client.force_login(manager)
        
        # Set phones business as active
        session = client.session
        session['active_business_id'] = phones_business.id
        session.save()
        
        # Try to access liquor route - should be forbidden or redirected
        response = client.get('/liquor/sell/')
        
        # Should not be 200 (either 403 Forbidden or redirect)
        assert response.status_code != 200


@pytest.mark.django_db
class TestLiquorSeedCatalog:
    """Test liquor product seeding functionality"""
    
    def test_should_seed_empty_business(self, business):
        """Test that empty liquor business should be seeded"""
        assert should_seed_liquor_products(business) is True
    
    def test_should_not_seed_business_with_products(self, business):
        """Test that business with products should not be seeded"""
        # Create a product
        MerchProduct.objects.create(
            business=business,
            name="Test Product",
            kind=BusinessKind.LIQUOR,
            category="beer",
            price_per_bottle=Decimal("1000.00"),
            is_active=True
        )
        assert should_seed_liquor_products(business) is False
    
    def test_create_default_catalog(self, business):
        """Test creating default catalog"""
        results = create_default_liquor_catalog(business)
        
        # Check that products were created
        assert results["created"] > 0
        assert results["skipped"] == 0
        
        # Verify products exist in database
        beer_count = MerchProduct.objects.filter(
            business=business,
            kind=BusinessKind.LIQUOR,
            category="beer"
        ).count()
        assert beer_count > 0
        
        # Verify whiskey products have shots enabled
        whiskey = MerchProduct.objects.filter(
            business=business,
            kind=BusinessKind.LIQUOR,
            category="whiskey"
        ).first()
        assert whiskey is not None
        assert whiskey.has_shots is True
        assert whiskey.price_per_shot is not None
        assert whiskey.shots_per_bottle > 0
    
    def test_create_catalog_twice_no_duplicates(self, business):
        """Test that calling create twice doesn't duplicate products"""
        # First call
        results1 = create_default_liquor_catalog(business)
        created_first = results1["created"]
        
        # Second call (should skip existing)
        results2 = create_default_liquor_catalog(business)
        assert results2["created"] == 0
        assert results2["skipped"] == created_first
        
        # Verify total count matches first creation
        total_products = MerchProduct.objects.filter(
            business=business,
            kind=BusinessKind.LIQUOR
        ).count()
        assert total_products == created_first
    
    def test_catalog_summary(self):
        """Test getting catalog summary"""
        summary = get_catalog_summary()
        
        assert summary["total_categories"] > 0
        assert summary["total_products"] > 0
        assert "Beer" in summary["categories"]
        assert "Whiskey" in summary["categories"]
        
        # Verify beer doesn't have shots
        assert summary["categories"]["Beer"]["has_shots"] is False
        
        # Verify whiskey has shots
        assert summary["categories"]["Whiskey"]["has_shots"] is True
    
    def test_specific_malawi_products_created(self, business):
        """Test that specific Malawi products are created"""
        create_default_liquor_catalog(business)
        
        # Check for specific products
        kuche_kuche = MerchProduct.objects.filter(
            business=business,
            name__icontains="Kuche Kuche"
        ).first()
        assert kuche_kuche is not None
        assert kuche_kuche.category == "beer"
        assert kuche_kuche.has_shots is False
        
        jameson = MerchProduct.objects.filter(
            business=business,
            name__icontains="Jameson"
        ).first()
        assert jameson is not None
        assert jameson.category == "whiskey"
        assert jameson.has_shots is True


@pytest.mark.django_db
class TestLiquorStockTargets:
    """Test stock target configuration and auto-adjust logic"""
    
    def test_product_has_default_target_fields(self, liquor_product):
        """Test that products have stock target fields with defaults"""
        assert hasattr(liquor_product, 'target_bottles')
        assert hasattr(liquor_product, 'auto_adjust_enabled')
        assert hasattr(liquor_product, 'auto_adjust_pct')
        assert liquor_product.target_bottles == 0
        assert liquor_product.auto_adjust_enabled is True
        assert liquor_product.auto_adjust_pct == 20
    
    def test_set_per_product_target(self, liquor_product):
        """Test setting a per-product target"""
        liquor_product.target_bottles = 100
        liquor_product.save()
        
        liquor_product.refresh_from_db()
        assert liquor_product.target_bottles == 100
    
    def test_liquor_stock_settings_creation(self, business):
        """Test creating business-level stock settings"""
        from inventory.models_verticals import LiquorStockSettings
        
        settings = LiquorStockSettings.objects.create(
            business=business,
            beer_target=500,
            cider_target=400,
            spirits_target=600,
            whiskey_target=300,
            wine_target=350,
            default_auto_adjust_pct=25
        )
        
        assert settings.beer_target == 500
        assert settings.cider_target == 400
        assert settings.default_auto_adjust_pct == 25
    
    def test_auto_adjust_logic(self, business, liquor_product, bartender):
        """Test smart auto-adjust logic based on sales"""
        from datetime import timedelta
        from inventory.liquor_utils import recalculate_liquor_targets_for_business
        
        # Enable auto-adjust for product
        liquor_product.auto_adjust_enabled = True
        liquor_product.auto_adjust_pct = 20
        liquor_product.target_bottles = 0
        liquor_product.save()
        
        # Create sales over the last 7 days with varying quantities
        for i in range(7):
            sold_at = timezone.now() - timedelta(days=i)
            quantity = 10 + (i * 2)  # Peak will be 22 bottles
            
            LiquorSale.objects.create(
                business=business,
                product=liquor_product,
                unit=LiquorUnitType.BOTTLE,
                quantity=quantity,
                unit_price=liquor_product.price_per_bottle,
                total_price=quantity * liquor_product.price_per_bottle,
                sale_type=LiquorSaleType.SALE,
                sold_by=bartender,
                sold_at=sold_at
            )
        
        # Run auto-adjust
        updated = recalculate_liquor_targets_for_business(business)
        
        # Should have updated this product
        assert liquor_product.id in updated
        
        # Refresh product
        liquor_product.refresh_from_db()
        
        # Peak was 22 bottles, with 20% increase should be ceil(22 * 1.2) = 27
        assert liquor_product.target_bottles == 27
    
    def test_stock_overview_data_with_per_product_targets(self, business, liquor_product):
        """Test stock overview uses per-product targets when available"""
        from inventory.liquor_utils import get_stock_overview_data
        
        # Set a per-product target
        liquor_product.target_bottles = 150
        liquor_product.save()
        
        # Get overview data
        data = get_stock_overview_data(business)
        
        # Find spirits category
        spirits_row = next((c for c in data["categories"] if c["category"] == "spirits"), None)
        assert spirits_row is not None
        assert spirits_row["target"] == 150  # Should use per-product target
        assert spirits_row["using_per_product_targets"] is True
    
    def test_stock_overview_data_with_business_defaults(self, business, liquor_product):
        """Test stock overview falls back to business defaults when no per-product targets"""
        from inventory.liquor_utils import get_stock_overview_data
        from inventory.models_verticals import LiquorStockSettings
        
        # Create business settings
        settings = LiquorStockSettings.objects.create(
            business=business,
            spirits_target=450,
        )
        
        # Don't set per-product target (or set to 0)
        liquor_product.target_bottles = 0
        liquor_product.save()
        
        # Get overview data
        data = get_stock_overview_data(business)
        
        # Find spirits category
        spirits_row = next((c for c in data["categories"] if c["category"] == "spirits"), None)
        assert spirits_row is not None
        assert spirits_row["target"] == 450  # Should use business default
        assert spirits_row["using_per_product_targets"] is False
    
    def test_stock_warnings_generated(self, business, liquor_product):
        """Test that stock overview generates appropriate warnings"""
        from inventory.liquor_utils import get_stock_overview_data
        
        # Set a target much higher than current stock
        liquor_product.target_bottles = 1000
        liquor_product.quantity = 100  # Only 10% of target
        liquor_product.save()
        
        # Get overview data
        data = get_stock_overview_data(business)
        
        # Should have at least one warning
        assert len(data["warnings"]) > 0
        
        # Should be a critical or warning type
        warning = data["warnings"][0]
        assert warning["type"] in ["danger", "warning"]
        assert "spirits" in warning["category"].lower()
# tests/test_wallet_costs.py
"""
Tests for admin wallet cost management features.
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone

from wallet.models import WalletTransaction, Ledger, TxnType
from wallet.utils import compute_business_costs, compute_revenue_costs_profit
from tenants.models import Business


@pytest.mark.django_db
class TestWalletCosts:
    
    def test_create_once_off_cost(self, business):
        """Test creating a once-off cost transaction."""
        cost = WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-50000.00"),
            note="Office supplies",
            business=business,
            is_recurring=False,
        )
        
        assert cost.amount == Decimal("-50000.00")
        assert not cost.is_recurring
        assert cost.ledger == Ledger.COMPANY
    
    def test_create_recurring_cost(self, business):
        """Test creating a recurring cost transaction."""
        today = timezone.localdate()
        
        cost = WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            type=TxnType.COST_RECURRING,
            amount=Decimal("-200000.00"),
            note="Monthly rent",
            business=business,
            is_recurring=True,
            recurrence="monthly",
            effective_from=today.replace(day=1),
        )
        
        assert cost.amount == Decimal("-200000.00")
        assert cost.is_recurring
        assert cost.effective_from is not None
    
    def test_compute_business_costs_once_off_only(self, business):
        """Test computing costs with only once-off costs."""
        today = timezone.localdate()
        month_start = today.replace(day=1)
        
        # Create once-off cost
        WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-50000.00"),
            note="Office supplies",
            business=business,
            effective_date=today,
        )
        
        result = compute_business_costs(business, month_start, today)
        
        assert result["once_off_total"] == Decimal("50000.00")
        assert result["recurring_total"] == Decimal("0.00")
        assert result["total"] == Decimal("50000.00")
    
    def test_compute_business_costs_with_recurring(self, business):
        """Test computing costs including recurring costs."""
        today = timezone.localdate()
        month_start = today.replace(day=1)
        
        # Create recurring cost
        WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            type=TxnType.COST_RECURRING,
            amount=Decimal("-200000.00"),
            note="Monthly rent",
            business=business,
            is_recurring=True,
            recurrence="monthly",
            effective_from=month_start,
        )
        
        result = compute_business_costs(business, month_start, today)
        
        assert result["recurring_total"] == Decimal("200000.00")
    
    def test_profit_calculation(self, business):
        """Test Revenue - Costs = Profit calculation."""
        today = timezone.localdate()
        month_start = today.replace(day=1)
        
        # Create costs
        WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-50000.00"),
            business=business,
            effective_date=today,
        )
        
        revenue = Decimal("1000000.00")
        
        result = compute_revenue_costs_profit(business, revenue, month_start, today)
        
        assert result["revenue"] == Decimal("1000000.00")
        assert result["costs"] == Decimal("50000.00")
        assert result["profit"] == Decimal("950000.00")
        assert result["profit_margin"] == Decimal("95.00")
    
    def test_negative_amount_rejected(self, business):
        """Test that forms reject negative cost amounts."""
        # This would be tested with AdminCostForm
        from wallet.forms import AdminCostForm
        
        form = AdminCostForm(data={
            'amount': Decimal("-100.00"),
            'note': 'Test',
            'effective_date': timezone.localdate(),
            'type': TxnType.COST_ONCE_OFF,
        }, business=business)
        
        assert not form.is_valid()
        assert 'amount' in form.errors
    
    def test_costs_scoped_by_business(self, business):
        """Test that costs are scoped to business."""
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        
        # Create another business
        other_business = Business.objects.create(
            name="Other Business",
            slug="other-biz",
            status="ACTIVE",
        )
        
        today = timezone.localdate()
        month_start = today.replace(day=1)
        
        # Create cost for main business
        WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-50000.00"),
            business=business,
            effective_date=today,
        )
        
        # Create cost for other business
        WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-30000.00"),
            business=other_business,
            effective_date=today,
        )
        
        # Compute costs for main business only
        result = compute_business_costs(business, month_start, today)
        assert result["total"] == Decimal("50000.00")
        
        # Compute costs for other business
        result_other = compute_business_costs(other_business, month_start, today)
        assert result_other["total"] == Decimal("30000.00")


@pytest.fixture
def business():
    """Create a test business."""
    return Business.objects.create(
        name="Test Business",
        slug="test-biz",
        status="ACTIVE",
    )


@pytest.mark.django_db
class TestAdminCostsBusinessScoping:
    """Test that admin costs are properly scoped to businesses"""
    
    def test_costs_scoped_to_business(self):
        """Test that costs for Business A are not visible to Business B"""
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        
        # Create two businesses
        business_a = Business.objects.create(
            name="Business A",
            slug="biz-a",
            status="ACTIVE",
        )
        
        business_b = Business.objects.create(
            name="Business B",
            slug="biz-b",
            status="ACTIVE",
        )
        
        today = timezone.localdate()
        
        # Create costs for Business A
        WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-50000.00"),
            note="Business A Cost",
            business=business_a,
            effective_date=today,
        )
        
        # Create costs for Business B
        WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            type=TxnType.COST_RECURRING,
            amount=Decimal("-30000.00"),
            note="Business B Cost",
            business=business_b,
            effective_date=today,
            is_recurring=True,
        )
        
        # Get costs for Business A
        costs_a = WalletTransaction.objects.filter(
            business=business_a,
            ledger=Ledger.COMPANY,
            type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING]
        )
        
        # Get costs for Business B
        costs_b = WalletTransaction.objects.filter(
            business=business_b,
            ledger=Ledger.COMPANY,
            type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING]
        )
        
        assert costs_a.count() == 1
        assert costs_b.count() == 1
        assert costs_a.first().note == "Business A Cost"
        assert costs_b.first().note == "Business B Cost"
    
    def test_fixed_vs_variable_costs(self):
        """Test that costs can be categorized as fixed or variable"""
        business = Business.objects.create(
            name="Test Business",
            slug="test-biz",
            status="ACTIVE",
        )
        
        from wallet.services_costs import add_business_cost
        
        today = timezone.localdate()
        
        # Add fixed cost
        fixed_cost = add_business_cost(
            business=business,
            name="Office Rent",
            amount=Decimal("200000.00"),
            cost_category="fixed",
            is_recurring=True,
            effective_date=today,
        )
        
        # Add variable cost
        variable_cost = add_business_cost(
            business=business,
            name="Marketing Expense",
            amount=Decimal("50000.00"),
            cost_category="variable",
            is_recurring=False,
            effective_date=today,
        )
        
        assert fixed_cost.meta['cost_category'] == 'fixed'
        assert variable_cost.meta['cost_category'] == 'variable'
        assert fixed_cost.is_recurring is True
        assert variable_cost.is_recurring is False


@pytest.mark.django_db
class TestProfitCalculationWithOverheadCosts:
    """Test that overhead costs are properly included in profit calculations"""
    
    def test_clothing_profit_includes_overhead_costs(self):
        """Test that clothing dashboard profit = revenue - COGS - overhead"""
        from django.contrib.auth import get_user_model
        from inventory.models import MerchProduct
        from inventory.models_verticals import ClothingSale, PaymentMethod
        from inventory.business_kinds import BusinessKind
        from wallet.services_costs import add_business_cost
        
        User = get_user_model()
        
        # Create test user and business
        user = User.objects.create_user(
            username='test@example.com',
            email='test@example.com',
            password='testpass123'
        )
        
        business = Business.objects.create(
            name="Fashion Store",
            slug="fashion",
            status="ACTIVE",
            business_kind=BusinessKind.CLOTHING
        )
        
        today = timezone.localdate()
        month_start = today.replace(day=1)
        
        # Create a product
        product = MerchProduct.objects.create(
            business=business,
            name='Suit - M - Black',
            kind=BusinessKind.CLOTHING,
            cost_price=Decimal('500.00'),
            selling_price=Decimal('800.00'),
            quantity_in_stock=100
        )
        
        # Create sales (3 units)
        for i in range(3):
            ClothingSale.objects.create(
                business=business,
                product=product,
                quantity=1,
                unit_price=Decimal('800.00'),
                total_price=Decimal('800.00'),
                unit_cost=Decimal('500.00'),
                total_cost=Decimal('500.00'),
                payment_method=PaymentMethod.CASH,
                sold_by=user,
                sold_at=timezone.now()
            )
        
        # Add overhead costs
        add_business_cost(
            business=business,
            name="Rent",
            amount=Decimal("100000.00"),
            cost_category="fixed",
            is_recurring=True,
            effective_date=today,
        )
        
        add_business_cost(
            business=business,
            name="Utilities",
            amount=Decimal("20000.00"),
            cost_category="variable",
            is_recurring=False,
            effective_date=today,
        )
        
        # Calculate metrics using the new function
        from inventory.verticals.base import clothing_sales_metrics
        
        metrics = clothing_sales_metrics(
            business,
            period='mtd'
        )
        
        # Expected values:
        # Revenue: 3 × 800 = 2400
        # COGS: 3 × 500 = 1500
        # Overhead: 100000 + 20000 = 120000
        # Profit: 2400 - 1500 - 120000 = -119100 (loss)
        
        assert metrics['revenue'] == Decimal('2400.00')
        assert metrics['cost_of_goods'] == Decimal('1500.00')
        assert metrics['overhead_costs'] == Decimal('120000.00')
        assert metrics['profit'] == Decimal('-119100.00')
    
    def test_date_filters_respected_for_costs(self):
        """Test that costs outside the selected date range are not included"""
        from django.contrib.auth import get_user_model
        from inventory.models import MerchProduct
        from inventory.models_verticals import ClothingSale, PaymentMethod
        from inventory.business_kinds import BusinessKind
        from wallet.services_costs import add_business_cost
        
        User = get_user_model()
        
        user = User.objects.create_user(
            username='test2@example.com',
            email='test2@example.com',
            password='testpass123'
        )
        
        business = Business.objects.create(
            name="Fashion Store 2",
            slug="fashion2",
            status="ACTIVE",
            business_kind=BusinessKind.CLOTHING
        )
        
        product = MerchProduct.objects.create(
            business=business,
            name='Shirt - L - White',
            kind=BusinessKind.CLOTHING,
            cost_price=Decimal('200.00'),
            selling_price=Decimal('400.00'),
            quantity_in_stock=100
        )
        
        today = timezone.localdate()
        last_week = today - timedelta(days=7)
        
        # Create sale today
        ClothingSale.objects.create(
            business=business,
            product=product,
            quantity=1,
            unit_price=Decimal('400.00'),
            total_price=Decimal('400.00'),
            unit_cost=Decimal('200.00'),
            total_cost=Decimal('200.00'),
            payment_method=PaymentMethod.CASH,
            sold_by=user,
            sold_at=timezone.now()
        )
        
        # Add cost today (should be included)
        add_business_cost(
            business=business,
            name="Cost Today",
            amount=Decimal("10000.00"),
            cost_category="variable",
            effective_date=today,
        )
        
        # Add cost last week (should NOT be included in "today" filter)
        add_business_cost(
            business=business,
            name="Cost Last Week",
            amount=Decimal("50000.00"),
            cost_category="variable",
            effective_date=last_week,
        )
        
        # Calculate metrics for today only
        from inventory.verticals.base import clothing_sales_metrics
        
        metrics = clothing_sales_metrics(
            business,
            period='today'
        )
        
        # Should only include today's cost
        assert metrics['overhead_costs'] == Decimal('10000.00')
        assert metrics['profit'] == Decimal('-9800.00')  # 400 - 200 - 10000
    
    def test_recurring_costs_included_in_calculations(self):
        """Test that recurring costs are properly included in profit calculations"""
        business = Business.objects.create(
            name="Test Business 3",
            slug="test-biz-3",
            status="ACTIVE",
        )
        
        from wallet.services_costs import add_business_cost, get_recurring_costs_for_month
        
        today = timezone.localdate()
        
        # Add recurring cost
        add_business_cost(
            business=business,
            name="Monthly Rent",
            amount=Decimal("200000.00"),
            cost_category="fixed",
            is_recurring=True,
            effective_date=today.replace(day=1),  # First of month
        )
        
        # Get recurring costs for current month
        recurring_total = get_recurring_costs_for_month(
            business,
            today.year,
            today.month
        )
        
        assert recurring_total == Decimal('200000.00')


@pytest.mark.django_db
class TestAdminCostsPageAccess:
    """Test admin costs page URL resolution and access."""
    
    def test_admin_costs_urls_resolve(self):
        """Test that admin costs URLs can be reversed."""
        from django.urls import reverse
        
        url_list = reverse("wallet:admin_cost_list")
        url_create = reverse("wallet:admin_costs_create")
        
        assert url_list == "/wallet/admin/costs/"
        assert url_create == "/wallet/admin/costs/new/"
    
    def test_admin_costs_page_loads_for_manager(self, client):
        """Test that admin costs page loads successfully for a manager."""
        from django.contrib.auth import get_user_model
        from django.urls import reverse
        from tenants.models import Membership
        
        User = get_user_model()
        
        # Create business
        business = Business.objects.create(
            name="Test Business",
            slug="test-biz",
            status="ACTIVE",
        )
        
        # Create manager user
        manager = User.objects.create_user(
            username='manager@example.com',
            email='manager@example.com',
            password='testpass123',
            is_staff=True
        )
        
        # Create membership
        Membership.objects.create(
            user=manager,
            business=business,
            role='MANAGER',
            status='ACTIVE'
        )
        
        # Login as manager
        client.force_login(manager)
        
        # Make request to admin costs list page
        resp = client.get(reverse("wallet:admin_cost_list"))
        
        # Should return 200 (not 500)
        assert resp.status_code == 200
        assert b'Business Costs' in resp.content or b'business costs' in resp.content.lower()
    
    def test_admin_costs_page_loads_without_notifications_context(self, client):
        """Test that admin costs page loads even without notifications context processor."""
        from django.contrib.auth import get_user_model
        from django.urls import reverse
        from django.test import RequestFactory
        from wallet.views_costs import admin_cost_list
        from tenants.models import Membership
        
        User = get_user_model()
        factory = RequestFactory()
        
        # Create business
        business = Business.objects.create(
            name="Test Business",
            slug="test-biz",
            status="ACTIVE",
        )
        
        # Create manager user
        manager = User.objects.create_user(
            username='manager2@example.com',
            email='manager2@example.com',
            password='testpass123',
            is_staff=True
        )
        
        # Create membership
        Membership.objects.create(
            user=manager,
            business=business,
            role='MANAGER',
            status='ACTIVE'
        )
        
        # Create a request with minimal context (no notifications context processor)
        request = factory.get(reverse("wallet:admin_cost_list"))
        request.user = manager
        request.business = business
        
        # Call the view directly
        response = admin_cost_list(request)
        
        # Should return 200, not raise VariableDoesNotExist
        assert response.status_code == 200
    
    def test_admin_cost_create_url_accessible(self, client):
        """Test that the create cost URL is accessible."""
        from django.contrib.auth import get_user_model
        from django.urls import reverse
        from tenants.models import Membership
        
        User = get_user_model()
        
        # Create business
        business = Business.objects.create(
            name="Test Business",
            slug="test-biz",
            status="ACTIVE",
        )
        
        # Create manager user
        manager = User.objects.create_user(
            username='manager3@example.com',
            email='manager3@example.com',
            password='testpass123',
            is_staff=True
        )
        
        # Create membership
        Membership.objects.create(
            user=manager,
            business=business,
            role='MANAGER',
            status='ACTIVE'
        )
        
        # Login
        client.force_login(manager)
        
        # Access create form
        resp = client.get(reverse("wallet:admin_costs_create"))
        
        # Should show the form
        assert resp.status_code == 200
        assert b'Add New Cost' in resp.content or b'Add Cost' in resp.content


@pytest.mark.django_db
class TestBusinessSpendTrend:
    """Test business spend trend chart data generation."""
    
    def test_spend_trend_includes_costs_and_commissions(self, client):
        """Test that spend trend includes both costs and commissions."""
        from django.contrib.auth import get_user_model
        from django.urls import reverse
        import json
        
        User = get_user_model()
        
        # Create business
        business = Business.objects.create(
            name="Test Business",
            slug="test-biz",
            status="ACTIVE",
        )
        
        # Create manager user
        manager = User.objects.create_user(
            username="manager",
            email="manager@test.com",
            password="password123",
            is_staff=True,
        )
        
        # Create membership
        from tenants.models import BusinessUserMembership
        BusinessUserMembership.objects.create(
            user=manager,
            business=business,
            role='MANAGER',
            status='ACTIVE'
        )
        
        # Create a cost transaction
        today = timezone.localdate()
        cost = WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-1000.00"),
            note="Test Cost",
            business=business,
            effective_date=today,
        )
        
        # Create a commission
        try:
            from sales.models import SaleCommission, Sale
            from inventory.models import InventoryItem, Location
            
            # Create location
            location = Location.objects.create(
                name="Test Location",
                business=business,
                status="ACTIVE",
            )
            
            # Create inventory item
            item = InventoryItem.objects.create(
                imei="123456789012345",
                model="Test Phone",
                location=location,
                status="SOLD",
            )
            
            # Create sale
            sale = Sale.objects.create(
                item=item,
                agent=manager,
                location=location,
                sold_at=today,
                price=Decimal("10000.00"),
            )
            
            # Create commission
            commission = SaleCommission.objects.create(
                sale=sale,
                agent=manager,
                business=business,
                base_commission=Decimal("500.00"),
                net_amount=Decimal("500.00"),
            )
        except Exception:
            # If models not available, skip commission part
            commission = None
        
        # Login as manager
        client.force_login(manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Access admin home
        resp = client.get(reverse("wallet:admin_home"))
        
        # Should return 200
        assert resp.status_code == 200
        
        # Check that business_spend_trend is in context
        assert "business_spend_trend" in resp.context
        
        # Parse the JSON data
        trend_data = json.loads(resp.context["business_spend_trend"])
        
        # Should have at least one entry
        assert len(trend_data) >= 1
        
        # Find today's entry
        today_str = str(today)
        today_entry = None
        for entry in trend_data:
            if entry['date'] == today_str:
                today_entry = entry
                break
        
        # Should have today's data
        assert today_entry is not None
        
        # Should have cost of 1000 (stored as -1000, converted to positive)
        assert float(today_entry['costs']) == 1000.0
        
        # If commission was created, should have commission of 500
        if commission:
            assert float(today_entry['commissions']) == 500.0
    
    def test_spend_trend_empty_data(self, client):
        """Test that spend trend handles empty data gracefully."""
        from django.contrib.auth import get_user_model
        from django.urls import reverse
        import json
        
        User = get_user_model()
        
        # Create business with no costs or commissions
        business = Business.objects.create(
            name="Empty Business",
            slug="empty-biz",
            status="ACTIVE",
        )
        
        # Create manager user
        manager = User.objects.create_user(
            username="empty_manager",
            email="empty@test.com",
            password="password123",
            is_staff=True,
        )
        
        # Create membership
        from tenants.models import BusinessUserMembership
        BusinessUserMembership.objects.create(
            user=manager,
            business=business,
            role='MANAGER',
            status='ACTIVE'
        )
        
        # Login as manager
        client.force_login(manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Access admin home
        resp = client.get(reverse("wallet:admin_home"))
        
        # Should return 200
        assert resp.status_code == 200
        
        # Check that business_spend_trend is in context
        assert "business_spend_trend" in resp.context
        
        # Parse the JSON data
        trend_data = json.loads(resp.context["business_spend_trend"])
        
        # Should be an empty list or have all zeros
        if len(trend_data) > 0:
            # All entries should have zero costs and commissions
            for entry in trend_data:
                assert entry['costs'] == 0 or entry['costs'] == 0.0
                assert entry['commissions'] == 0 or entry['commissions'] == 0.0
        else:
            # Empty list is also acceptable
            assert trend_data == []
    
    def test_spend_trend_multiple_days(self, client):
        """Test spend trend with data across multiple days."""
        from django.contrib.auth import get_user_model
        from django.urls import reverse
        import json
        
        User = get_user_model()
        
        # Create business
        business = Business.objects.create(
            name="Multi Day Business",
            slug="multi-day-biz",
            status="ACTIVE",
        )
        
        # Create manager user
        manager = User.objects.create_user(
            username="multi_manager",
            email="multi@test.com",
            password="password123",
            is_staff=True,
        )
        
        # Create membership
        from tenants.models import BusinessUserMembership
        BusinessUserMembership.objects.create(
            user=manager,
            business=business,
            role='MANAGER',
            status='ACTIVE'
        )
        
        # Create costs for different days
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        two_days_ago = today - timedelta(days=2)
        
        WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-1000.00"),
            note="Cost Today",
            business=business,
            effective_date=today,
        )
        
        WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-2000.00"),
            note="Cost Yesterday",
            business=business,
            effective_date=yesterday,
        )
        
        WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            type=TxnType.COST_RECURRING,
            amount=Decimal("-5000.00"),
            note="Recurring Cost",
            business=business,
            effective_date=two_days_ago,
            is_recurring=True,
        )
        
        # Login as manager
        client.force_login(manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Access admin home
        resp = client.get(reverse("wallet:admin_home"))
        
        # Should return 200
        assert resp.status_code == 200
        
        # Check that business_spend_trend is in context
        assert "business_spend_trend" in resp.context
        
        # Parse the JSON data
        trend_data = json.loads(resp.context["business_spend_trend"])
        
        # Should have at least 3 entries (one for each day with costs)
        assert len(trend_data) >= 3
        
        # Data should be sorted by date
        dates = [entry['date'] for entry in trend_data]
        assert dates == sorted(dates)
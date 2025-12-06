"""
Tests for dashboard chart APIs (/dashboard/api/sales-trend/ and /dashboard/api/top-models/).

These tests ensure:
1. APIs return HTTP 200 and valid JSON even with NO sales
2. APIs include manager sales (not just agent sales)
3. JSON shape matches what the frontend expects: {labels: [...], values: [...]}
"""
import pytest
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def business(db):
    """Create a test business."""
    from tenants.models import Business
    return Business.objects.create(
        name='Test Business',
        slug='test-business',
        business_kind='phones',
        status='ACTIVE'
    )


@pytest.fixture
def other_business(db):
    """Create another test business for isolation tests."""
    from tenants.models import Business
    return Business.objects.create(
        name='Other Business',
        slug='other-business',
        business_kind='phones',
        status='ACTIVE'
    )


@pytest.fixture
def manager_user(db, business):
    """Create a manager user linked to business."""
    from tenants.models import Membership
    from django.contrib.auth.models import Group
    
    user = User.objects.create_user(
        username='manager',
        password='testpass123',
        email='manager@test.com'
    )
    
    # Create Manager group if it doesn't exist
    manager_group, _ = Group.objects.get_or_create(name='Manager')
    user.groups.add(manager_group)
    
    # Create membership linking user to business
    Membership.objects.create(
        user=user,
        business=business,
        role='MANAGER'
    )
    
    return user


@pytest.fixture
def phone_product(db):
    """Create a test phone product."""
    from inventory.models import Product
    return Product.objects.create(
        code='IPHONE-13-PRO',
        name='iPhone 13 Pro',
        model='iPhone 13 Pro',
        brand='Apple',
        cost_price=Decimal('800.00'),
        sale_price=Decimal('1000.00')
    )


@pytest.fixture
def authenticated_client(client, manager_user, business):
    """Client with logged-in manager and active business set in session."""
    client.force_login(manager_user)
    # Set active business in session (simulates @require_business decorator)
    session = client.session
    session['active_business_id'] = business.id
    session.save()
    return client


# ============================================================================
# TESTS
# ============================================================================


@pytest.mark.django_db
class TestDashboardSalesTrendAPI:
    """Tests for /dashboard/api/sales-trend/ endpoint."""
    
    def test_sales_trend_returns_valid_json_without_sales(self, authenticated_client):
        """API returns 200 and valid JSON when there are NO sales."""
        # Call the API
        response = authenticated_client.get('/dashboard/api/sales-trend/?period=30d&metric=amount')
        
        # Should return 200
        assert response.status_code == 200
        
        # Should be valid JSON
        data = response.json()
        assert "labels" in data
        assert "values" in data
        
        # Should have empty or zero values (30 days worth)
        assert isinstance(data["labels"], list)
        assert isinstance(data["values"], list)
        assert len(data["labels"]) == 30
        assert len(data["values"]) == 30
        assert all(v == 0 for v in data["values"])
    
    def test_sales_trend_includes_manager_sales(self, authenticated_client, manager_user, business, phone_product):
        """API includes sales made by managers (not just agents)."""
        from inventory.models import InventoryItem
        
        # Create a sold item assigned to manager
        now = timezone.now()
        item = InventoryItem.objects.create(
            business=business,
            product=phone_product,
            imei='123456789012345',
            status='SOLD',
            sold_at=now,
            selling_price=Decimal('1000.00'),
            assigned_agent=manager_user
        )
        
        # Call the API
        response = authenticated_client.get('/dashboard/api/sales-trend/?period=30d&metric=amount')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have non-zero values
        assert sum(data["values"]) > 0
        
        # Today's date should have the sale
        today_str = timezone.localdate().isoformat()
        if today_str in data["labels"]:
            idx = data["labels"].index(today_str)
            assert data["values"][idx] == 1000.0
    
    def test_sales_trend_metric_count(self, authenticated_client, manager_user, business, phone_product):
        """API supports metric=count parameter."""
        from inventory.models import InventoryItem
        
        # Create 3 sold items
        now = timezone.now()
        for i in range(3):
            InventoryItem.objects.create(
                business=business,
                product=phone_product,
                imei=f'12345678901234{i}',
                status='SOLD',
                sold_at=now,
                selling_price=Decimal('1000.00'),
                assigned_agent=manager_user
            )
        
        # Call API with metric=count
        response = authenticated_client.get('/dashboard/api/sales-trend/?period=30d&metric=count')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have count = 3 for today
        today_str = timezone.localdate().isoformat()
        if today_str in data["labels"]:
            idx = data["labels"].index(today_str)
            assert data["values"][idx] == 3
    
    def test_sales_trend_period_week(self, authenticated_client):
        """API supports period=week parameter (7 days)."""
        response = authenticated_client.get('/dashboard/api/sales-trend/?period=week&metric=amount')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return 7 days
        assert len(data["labels"]) == 7
        assert len(data["values"]) == 7
    
    def test_sales_trend_period_today(self, authenticated_client):
        """API supports period=today parameter (1 day)."""
        response = authenticated_client.get('/dashboard/api/sales-trend/?period=today&metric=amount')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return 1 day
        assert len(data["labels"]) == 1
        assert len(data["values"]) == 1
    
    def test_sales_trend_scoped_to_business(self, authenticated_client, manager_user, business, other_business, phone_product):
        """API only returns sales for the current business."""
        from inventory.models import InventoryItem
        
        # Create sale for current business
        now = timezone.now()
        InventoryItem.objects.create(
            business=business,
            product=phone_product,
            imei='111111111111111',
            status='SOLD',
            sold_at=now,
            selling_price=Decimal('1000.00'),
            assigned_agent=manager_user
        )
        
        # Create sale for OTHER business
        InventoryItem.objects.create(
            business=other_business,
            product=phone_product,
            imei='222222222222222',
            status='SOLD',
            sold_at=now,
            selling_price=Decimal('2000.00'),
            assigned_agent=manager_user
        )
        
        # Call API
        response = authenticated_client.get('/dashboard/api/sales-trend/?period=30d&metric=amount')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should only include current business sale (1000), not other business (2000)
        today_str = timezone.localdate().isoformat()
        if today_str in data["labels"]:
            idx = data["labels"].index(today_str)
            assert data["values"][idx] == 1000.0


@pytest.mark.django_db
class TestDashboardTopModelsAPI:
    """Tests for /dashboard/api/top-models/ endpoint."""
    
    def test_top_models_returns_valid_json_without_sales(self, authenticated_client):
        """API returns 200 and valid JSON when there are NO sales."""
        # Call the API
        response = authenticated_client.get('/dashboard/api/top-models/?period=month')
        
        # Should return 200
        assert response.status_code == 200
        
        # Should be valid JSON
        data = response.json()
        assert "labels" in data
        assert "values" in data
        
        # Should have empty arrays
        assert isinstance(data["labels"], list)
        assert isinstance(data["values"], list)
        assert len(data["labels"]) == 0
        assert len(data["values"]) == 0
    
    def test_top_models_includes_manager_sales(self, authenticated_client, manager_user, business, phone_product):
        """API includes sales made by managers."""
        from inventory.models import InventoryItem
        
        # Create sold items assigned to manager
        now = timezone.now()
        for i in range(3):
            InventoryItem.objects.create(
                business=business,
                product=phone_product,
                imei=f'12345678901234{i}',
                status='SOLD',
                sold_at=now,
                selling_price=Decimal('1000.00'),
                assigned_agent=manager_user
            )
        
        # Call the API
        response = authenticated_client.get('/dashboard/api/top-models/?period=month')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have the product in results
        assert len(data["labels"]) > 0
        assert len(data["values"]) > 0
        assert phone_product.name in data["labels"]
        
        # Should have count = 3
        idx = data["labels"].index(phone_product.name)
        assert data["values"][idx] == 3
    
    def test_top_models_returns_top_5(self, authenticated_client, manager_user, business):
        """API returns at most top 5 models."""
        from inventory.models import InventoryItem, Product
        
        # Create 8 products with different sales counts
        now = timezone.now()
        for i in range(8):
            product = Product.objects.create(
                code=f'PHONE-MODEL-{i}',
                name=f'Phone Model {i}',
                model=f'Model {i}',
                brand='TestBrand'
            )
            # Create sales (8, 7, 6, ... 1)
            for j in range(8 - i):
                InventoryItem.objects.create(
                    business=business,
                    product=product,
                    imei=f'1234567890123{i}{j}',
                    status='SOLD',
                    sold_at=now,
                    selling_price=Decimal('1000.00'),
                    assigned_agent=manager_user
                )
        
        # Call the API
        response = authenticated_client.get('/dashboard/api/top-models/?period=month')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return at most 5 models
        assert len(data["labels"]) == 5
        assert len(data["values"]) == 5
        
        # Should be ordered by count descending
        assert data["values"] == sorted(data["values"], reverse=True)
        
        # Top model should have 8 sales
        assert data["values"][0] == 8
    
    def test_top_models_period_today(self, authenticated_client, manager_user, business, phone_product):
        """API supports period=today parameter."""
        from inventory.models import InventoryItem
        
        # Create sale today
        now = timezone.now()
        InventoryItem.objects.create(
            business=business,
            product=phone_product,
            imei='111111111111111',
            status='SOLD',
            sold_at=now,
            selling_price=Decimal('1000.00'),
            assigned_agent=manager_user
        )
        
        # Create sale yesterday (should not be included)
        yesterday = now - timedelta(days=1)
        InventoryItem.objects.create(
            business=business,
            product=phone_product,
            imei='222222222222222',
            status='SOLD',
            sold_at=yesterday,
            selling_price=Decimal('1000.00'),
            assigned_agent=manager_user
        )
        
        # Call API with period=today
        response = authenticated_client.get('/dashboard/api/top-models/?period=today')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should only include today's sale (count = 1)
        if phone_product.name in data["labels"]:
            idx = data["labels"].index(phone_product.name)
            assert data["values"][idx] == 1
    
    def test_top_models_scoped_to_business(self, authenticated_client, manager_user, business, other_business, phone_product):
        """API only returns sales for the current business."""
        from inventory.models import InventoryItem
        
        # Create 2 sales for current business
        now = timezone.now()
        for i in range(2):
            InventoryItem.objects.create(
                business=business,
                product=phone_product,
                imei=f'11111111111111{i}',
                status='SOLD',
                sold_at=now,
                selling_price=Decimal('1000.00'),
                assigned_agent=manager_user
            )
        
        # Create 5 sales for OTHER business
        for i in range(5):
            InventoryItem.objects.create(
                business=other_business,
                product=phone_product,
                imei=f'22222222222222{i}',
                status='SOLD',
                sold_at=now,
                selling_price=Decimal('1000.00'),
                assigned_agent=manager_user
            )
        
        # Call API
        response = authenticated_client.get('/dashboard/api/top-models/?period=month')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should only include current business sales (2), not other business (5)
        if phone_product.name in data["labels"]:
            idx = data["labels"].index(phone_product.name)
            assert data["values"][idx] == 2

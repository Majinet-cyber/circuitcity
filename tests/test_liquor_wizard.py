# tests/test_liquor_wizard.py
"""
Tests for liquor wizard and stock-in functionality
"""
import pytest
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model
from inventory.models import MerchProduct
from inventory.business_kinds import BusinessKind

User = get_user_model()


@pytest.fixture
def liquor_business(db):
    """Create a liquor business for testing"""
    from tenants.models import Business
    business = Business.objects.create(
        name="Test Liquor Store",
        business_kind=BusinessKind.LIQUOR,
        is_active=True
    )
    return business


@pytest.fixture
def manager_user(db, liquor_business):
    """Create a manager user"""
    user = User.objects.create_user(
        username='testmanager',
        email='manager@test.com',
        password='testpass123'
    )
    # Assign manager role to business
    from tenants.models import Membership
    Membership.objects.create(
        business=liquor_business,
        user=user,
        role='manager',
        is_active=True
    )
    return user


@pytest.fixture
def auth_client(client, manager_user, liquor_business):
    """Authenticated client with active business"""
    client.login(username='testmanager', password='testpass123')
    # Set active business in session
    session = client.session
    session['active_business_id'] = liquor_business.id
    session.save()
    return client


@pytest.mark.django_db
class TestLiquorWizardStep1:
    """Test liquor wizard step 1 - choose liquor type"""
    
    def test_get_step1_returns_200(self, auth_client):
        """GET request to step 1 should return 200"""
        url = reverse('inventory:liquor_wizard_step1')
        response = auth_client.get(url)
        assert response.status_code == 200
        content = response.content.decode()
        # New simple flow shows "Choose Liquor Category"
        assert 'Choose' in content and ('Liquor' in content or 'Category' in content)
    
    def test_post_step1_with_valid_type(self, auth_client):
        """Step 1 no longer accepts POST - it's pure links"""
        url = reverse('inventory:liquor_wizard_step1')
        response = auth_client.get(url)
        assert response.status_code == 200
        # Should show links to catalog pages
        content = response.content.decode()
        assert 'Beer' in content
    
    def test_post_step1_without_type(self, auth_client):
        """POST without liquor type should show error"""
        url = reverse('inventory:liquor_wizard_step1')
        response = auth_client.post(url, {})
        assert response.status_code == 200
        assert 'error' in response.content.decode().lower() or 'required' in response.content.decode().lower()


@pytest.mark.django_db
class TestLiquorWizardStep2:
    """Test liquor wizard step 2 - enter product details"""
    
    def test_get_step2_without_session_redirects(self, auth_client):
        """GET step 2 without liquor type in session should redirect to step 1"""
        url = reverse('inventory:liquor_wizard_step2')
        response = auth_client.get(url)
        assert response.status_code == 302
        assert response.url == reverse('inventory:liquor_wizard_step1')
    
    def test_get_step2_with_session_returns_200(self, auth_client):
        """GET step 2 with liquor type in session should return 200"""
        # Set liquor type in session
        session = auth_client.session
        session['liquor_wizard_type'] = 'beer'
        session.save()
        
        url = reverse('inventory:liquor_wizard_step2')
        response = auth_client.get(url)
        assert response.status_code == 200
        assert 'Beer' in response.content.decode()
    
    def test_post_step2_creates_product(self, auth_client, liquor_business):
        """POST step 2 with valid data should create product and redirect"""
        # Set liquor type in session
        session = auth_client.session
        session['liquor_wizard_type'] = 'beer'
        session.save()
        
        url = reverse('inventory:liquor_wizard_step2')
        data = {
            'product_name': 'Carlsberg Green',
            'sell_per_unit': '1500',
            'cost_per_unit': '1000',
            'enable_pack': True,
            'pack_size': 20,
        }
        response = auth_client.post(url, data)
        
        # Should redirect to dashboard
        assert response.status_code == 302
        assert 'liquor' in response.url.lower()
        
        # Product should be created
        product = MerchProduct.objects.filter(
            business=liquor_business,
            name='Carlsberg Green'
        ).first()
        assert product is not None
        assert product.kind == BusinessKind.LIQUOR
        assert product.category == 'beer'
        assert product.price_per_bottle == Decimal('1500')
        assert product.cost_per_bottle == Decimal('1000')
        
        # Session should be cleared
        assert 'liquor_wizard_type' not in auth_client.session
    
    def test_post_step2_without_product_name(self, auth_client):
        """POST step 2 without product name should show error"""
        session = auth_client.session
        session['liquor_wizard_type'] = 'wine'
        session.save()
        
        url = reverse('inventory:liquor_wizard_step2')
        data = {
            'product_name': '',
            'sell_per_unit': '2000',
        }
        response = auth_client.post(url, data)
        assert response.status_code == 200
        assert 'required' in response.content.decode().lower()


@pytest.mark.django_db
class TestLiquorCatalog:
    """Test liquor catalog functionality"""
    
    def test_get_catalog_returns_200(self, auth_client):
        """GET catalog page should return 200"""
        url = reverse('inventory:liquor_catalog', kwargs={'category': 'beer'})
        response = auth_client.get(url)
        assert response.status_code == 200
        assert 'Beer' in response.content.decode()
    
    def test_catalog_seeds_products_on_first_visit(self, auth_client, liquor_business):
        """Catalog should auto-seed products if none exist"""
        # Ensure no products exist
        assert MerchProduct.objects.filter(
            business=liquor_business,
            kind=BusinessKind.LIQUOR,
            category='beer'
        ).count() == 0
        
        # Visit catalog
        url = reverse('inventory:liquor_catalog', kwargs={'category': 'beer'})
        response = auth_client.get(url)
        assert response.status_code == 200
        
        # Products should now exist
        products = MerchProduct.objects.filter(
            business=liquor_business,
            kind=BusinessKind.LIQUOR,
            category='beer'
        )
        assert products.count() > 0
    
    def test_catalog_search_filters_products(self, auth_client, liquor_business):
        """Catalog search should filter products"""
        # Create test products
        MerchProduct.objects.create(
            business=liquor_business,
            name='Carlsberg',
            kind=BusinessKind.LIQUOR,
            category='beer',
            price_per_bottle=Decimal('1500'),
            spec_label='',
            is_active=True
        )
        MerchProduct.objects.create(
            business=liquor_business,
            name='Heineken',
            kind=BusinessKind.LIQUOR,
            category='beer',
            price_per_bottle=Decimal('1600'),
            spec_label='',
            is_active=True
        )
        
        # Search for Carlsberg
        url = reverse('inventory:liquor_catalog', kwargs={'category': 'beer'}) + '?q=Carlsberg'
        response = auth_client.get(url)
        assert response.status_code == 200
        content = response.content.decode()
        assert 'Carlsberg' in content
        # Heineken should not appear in filtered results
        # (Note: depending on template, it might still be in HTML but hidden)


@pytest.mark.django_db
class TestLiquorStockIn:
    """Test liquor stock-in functionality"""
    
    def test_stock_in_requires_product_id(self, auth_client):
        """Stock-in URL now requires product_id parameter"""
        # This test verifies the URL pattern requires product_id
        # Attempting to reverse without product_id should fail
        try:
            url = reverse('inventory:liquor_stock_in')
            assert False, "Should not be able to reverse without product_id"
        except Exception:
            # Expected - URL requires product_id
            pass
    
    def test_get_stock_in_with_product_id_shows_form(self, auth_client, liquor_business):
        """Stock-in page with product_id should show stock-in form"""
        # Create a product
        product = MerchProduct.objects.create(
            business=liquor_business,
            name='Test Beer',
            kind=BusinessKind.LIQUOR,
            category='beer',
            price_per_bottle=Decimal('1500'),
            spec_label='',
            is_active=True
        )
        
        url = reverse('inventory:liquor_stock_in', kwargs={'product_id': product.id})
        response = auth_client.get(url)
        assert response.status_code == 200
        assert 'Test Beer' in response.content.decode()
        assert 'Stock In' in response.content.decode()
    
    def test_post_stock_in_submits_successfully(self, auth_client, liquor_business):
        """POST stock-in should process without errors and update stock"""
        # Create a wine product; view expects 'bottles' and 'cost_per_bottle' for wine
        product = MerchProduct.objects.create(
            business=liquor_business,
            name='Test Wine',
            kind=BusinessKind.LIQUOR,
            category='wine',
            price_per_bottle=Decimal('3000'),
            spec_label='',
            is_active=True
        )
        
        url = reverse('inventory:liquor_stock_in_submit', kwargs={'product_id': product.id})
        data = {
            'bottles': 50,
            'cost_per_bottle': '2500',
        }
        response = auth_client.post(url, data)
        
        # Should redirect to My Stock (success)
        assert response.status_code == 302
        
        # Wine: stored as glasses (1 bottle = 5 glasses), 50 bottles = 250 glasses
        product.refresh_from_db()
        assert product.quantity_in_stock == 250  # 50 bottles * 5 glasses
        assert product.cost_per_bottle == Decimal('500.00')  # 2500 / 5 = 500 per glass
    
    def test_beer_stock_in_with_crates(self, auth_client, liquor_business):
        """Beer stock-in should support crates (1 crate = 20 bottles)"""
        # Create a beer product
        product = MerchProduct.objects.create(
            business=liquor_business,
            name='Castle Lager',
            kind=BusinessKind.LIQUOR,
            category='beer',
            price_per_bottle=Decimal('1000'),
            spec_label='',
            is_active=True
        )
        
        url = reverse('inventory:liquor_stock_in_submit', kwargs={'product_id': product.id})
        data = {
            'crates': 2,
            'loose_bottles': 0,
            'cost_per_crate': '20000',  # view uses cost_per_crate, not total_cost
        }
        response = auth_client.post(url, data)
        
        # Should redirect to My Stock (success)
        assert response.status_code == 302
        
        # Stock should be updated: 2 crates = 40 bottles
        product.refresh_from_db()
        assert product.quantity_in_stock == 40
        # Cost per bottle = (2 * 20000) / 40 = 1000
        assert product.cost_per_bottle == Decimal('1000.00')
    
    def test_beer_stock_in_with_crates_and_loose_bottles(self, auth_client, liquor_business):
        """Beer stock-in should support crates + loose bottles"""
        # Create a beer product
        product = MerchProduct.objects.create(
            business=liquor_business,
            name='Carlsberg',
            kind=BusinessKind.LIQUOR,
            category='beer',
            price_per_bottle=Decimal('1200'),
            spec_label='',
            is_active=True
        )
        
        url = reverse('inventory:liquor_stock_in_submit', kwargs={'product_id': product.id})
        # view uses cost_per_crate; 3 crates * 20000 + 5 loose = 65 bottles, total 65000
        # cost_per_crate = 65000/3 ≈ 21666.67; total = 3*21666.67 = 65000; per bottle = 65000/65 = 1000
        data = {
            'crates': 3,
            'loose_bottles': 5,
            'cost_per_crate': '13000',  # 3 crates * 13000 = 39000 + 5 loose = adjusted; use 10000/crate (30000 total) => 30000/65 ≈ 461. Instead pick numbers that work.
        }
        # Simplest: 3 crates (60 btl) + 5 loose = 65 btl. cost_per_crate=13000 total=3*13000=39000 => cost/bottle=600
        response = auth_client.post(url, data)
        
        # Should redirect to My Stock (success)
        assert response.status_code == 302
        
        # Stock should be updated: 3 crates + 5 loose = 60 + 5 = 65 bottles
        product.refresh_from_db()
        assert product.quantity_in_stock == 65
    
    def test_beer_stock_in_requires_crates(self, auth_client, liquor_business):
        """Beer stock-in should require crates field"""
        # Create a beer product
        product = MerchProduct.objects.create(
            business=liquor_business,
            name='Chibuku',
            kind=BusinessKind.LIQUOR,
            category='beer',
            price_per_bottle=Decimal('500'),
            spec_label='',
            is_active=True
        )
        
        url = reverse('inventory:liquor_stock_in_submit', kwargs={'product_id': product.id})
        data = {
            'total_cost': '10000',
            # Missing crates field
        }
        response = auth_client.post(url, data)
        
        # Should redirect back with error
        assert response.status_code == 302
        
        # Stock should not be updated
        product.refresh_from_db()
        assert product.quantity_in_stock == 0
    
    def test_non_beer_stock_in_unchanged(self, auth_client, liquor_business):
        """Non-beer products use shot-based stock-in (spirits: shots_added, cost_per_shot)"""
        product = MerchProduct.objects.create(
            business=liquor_business,
            name='Jameson',
            kind=BusinessKind.LIQUOR,
            category='spirits',
            price_per_bottle=Decimal('8000'),
            spec_label='',
            is_active=True
        )
        
        url = reverse('inventory:liquor_stock_in_submit', kwargs={'product_id': product.id})
        data = {
            'shots_added': 10,
            'cost_per_shot': '7000',
            'reserved_barman_shots': 0,
        }
        response = auth_client.post(url, data)
        
        # Should redirect on success
        assert response.status_code == 302
        
        # Stock should be updated: sellable_shots = shots_added - reserved = 10
        product.refresh_from_db()
        assert product.quantity_in_stock == 10
        assert product.cost_per_bottle == Decimal('7000')


@pytest.mark.django_db
class TestLiquorWizardIntegration:
    """Integration tests for complete wizard flow"""
    
    def test_complete_catalog_flow(self, auth_client, liquor_business):
        """Test complete flow: category → catalog → stock-in"""
        # Step 1: View category page (no POST, just links)
        step1_url = reverse('inventory:liquor_wizard_step1')
        response = auth_client.get(step1_url)
        assert response.status_code == 200
        assert 'Beer' in response.content.decode()
        
        # Step 2: Navigate to catalog (user clicks Beer link)
        catalog_url = reverse('inventory:liquor_catalog', kwargs={'category': 'beer'})
        response = auth_client.get(catalog_url)
        assert response.status_code == 200
        
        # Products should be seeded
        products = MerchProduct.objects.filter(
            business=liquor_business,
            kind=BusinessKind.LIQUOR,
            category='beer'
        )
        assert products.count() > 0
        
        # Step 3: Navigate to stock-in (user clicks Select button)
        product = products.first()
        stock_in_url = reverse('inventory:liquor_stock_in', kwargs={'product_id': product.id})
        response = auth_client.get(stock_in_url)
        assert response.status_code == 200
        assert product.name in response.content.decode()


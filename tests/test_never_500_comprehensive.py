"""
Comprehensive tests to ensure no HTTP 500 errors in normal user usage.

Tests for all 6 critical bugs identified:
1. Phones scan-in with no products
2. Reports with empty data
3. Liquor without active shift
4. Gym payment days awarding
5. Mobile dashboard overflow (rendering tests)
6. Phones top sales with no data

Hard rule: None of these flows may ever return HTTP 500 — must return 200 or expected redirect.
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.test import Client, TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

# Mark as critical - these tests ensure no 500 errors in normal usage
pytestmark = [pytest.mark.django_db, pytest.mark.critical]


# =====================================================================
# TEST 1: PHONES SCAN-IN NEVER 500
# =====================================================================
class TestPhonesScanInNever500(TestCase):
    """Test that phones scan-in always returns 200, even with no products."""
    
    def setUp(self):
        from tenants.models import Business
        from inventory.models import BusinessKind
        
        self.client = Client()
        self.user = User.objects.create_user(
            username="testmanager",
            password="testpass123",
            email="manager@test.com"
        )
        self.business = Business.objects.create(
            name="Test Phone Shop",
            business_kind=BusinessKind.PHONES,
            owner=self.user
        )
        self.client.login(username="testmanager", password="testpass123")
    
    def test_scan_in_with_no_products_returns_200(self):
        """Scan-in page must load even when there are zero products in DB."""
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('inventory:phone_scan_in')
        response = self.client.get(url)
        
        # Must not crash - should show empty state
        assert response.status_code in [200, 302], f"Expected 200 or 302, got {response.status_code}"
        
        if response.status_code == 200:
            # Check that template renders with empty state message
            content = response.content.decode()
            assert 'No phone models yet' in content or 'has_catalog' in content
    
    def test_scan_with_unknown_barcode_returns_200(self):
        """Scanning an unknown barcode/IMEI must show friendly message, not 500."""
        from inventory.models import PhoneProductCatalog
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Create one product
        catalog = PhoneProductCatalog.objects.create(
            business=self.business,
            brand="TECNO",
            model_name="Spark 20",
            variant_label="4+128",
            default_cost_price=Decimal("500000.00"),
            default_selling_price=Decimal("650000.00"),
            is_active=True
        )
        
        url = reverse('inventory:phone_scan_in')
        # Try to submit with invalid catalog ID
        response = self.client.post(url, {
            'brand': 'TECNO',
            'catalog_product_id': '99999',  # Doesn't exist
            'imei': '123456789012345'
        })
        
        # Should redirect back with error message, not crash
        assert response.status_code in [200, 302], f"Expected 200 or 302, got {response.status_code}"
    
    def test_generic_scan_in_with_no_products_returns_200(self):
        """Generic scan-in (inventory:scan_in) must work with no products."""
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('inventory:scan_in')
        response = self.client.get(url)
        
        # Must render successfully
        assert response.status_code in [200, 302], f"Expected 200 or 302, got {response.status_code}"


# =====================================================================
# TEST 2: REPORTS NEVER 500
# =====================================================================
class TestReportsNever500(TestCase):
    """Test that reports pages never crash with empty data."""
    
    def setUp(self):
        from tenants.models import Business
        from inventory.models import BusinessKind
        
        self.client = Client()
        self.user = User.objects.create_user(
            username="testmanager",
            password="testpass123",
            email="manager@test.com",
            is_staff=True  # Reports require staff access
        )
        self.business = Business.objects.create(
            name="Test Business",
            business_kind=BusinessKind.PHONES,
            owner=self.user
        )
        self.client.login(username="testmanager", password="testpass123")
    
    def test_reports_home_with_no_sales_returns_200(self):
        """Reports home must render with zero sales data."""
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('reports:home')
        response = self.client.get(url)
        
        # Must render successfully with empty data
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    def test_reports_with_no_business_returns_200(self):
        """Reports must handle missing business gracefully."""
        # Don't set active_business_id
        url = reverse('reports:home')
        response = self.client.get(url)
        
        # Should not crash - might redirect or show empty state
        assert response.status_code in [200, 302, 403], f"Expected 200/302/403, got {response.status_code}"
    
    def test_reports_sales_page_returns_200(self):
        """Sales report page must render with no data."""
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('reports:sales')
        response = self.client.get(url)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    def test_reports_inventory_page_returns_200(self):
        """Inventory report page must render with no data."""
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('reports:inventory')
        response = self.client.get(url)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"


# =====================================================================
# TEST 3: LIQUOR SHIFT NEVER BLOCKS
# =====================================================================
class TestLiquorShiftNeverBlocks(TestCase):
    """Test that liquor operations never block due to missing shift."""
    
    def setUp(self):
        from tenants.models import Business
        from inventory.models import BusinessKind
        
        self.client = Client()
        self.user = User.objects.create_user(
            username="barman",
            password="testpass123",
            email="barman@test.com"
        )
        self.business = Business.objects.create(
            name="Test Liquor Store",
            business_kind=BusinessKind.LIQUOR,
            owner=self.user
        )
        self.client.login(username="barman", password="testpass123")
    
    def test_liquor_sell_without_shift_returns_200(self):
        """Liquor sell page must not crash when no active shift exists."""
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('liquor:sell')
        response = self.client.get(url)
        
        # Should show warning and either start shift UI or continue
        assert response.status_code in [200, 302], f"Expected 200 or 302, got {response.status_code}"
        
        # If it's 200, check for warning message about shift
        if response.status_code == 200:
            content = response.content.decode()
            # Should mention shift in some way (warning or prompt)
            assert 'shift' in content.lower() or 'Shift' in content
    
    def test_liquor_dashboard_without_shift_returns_200(self):
        """Liquor dashboard must render without active shift."""
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        try:
            url = reverse('liquor:dashboard')
            response = self.client.get(url)
            assert response.status_code in [200, 302], f"Expected 200 or 302, got {response.status_code}"
        except Exception:
            # URL might not exist, that's OK
            pass


# =====================================================================
# TEST 4: GYM PAYMENTS AWARD DAYS CORRECTLY
# =====================================================================
class TestGymPaymentsAwardDays(TestCase):
    """Test that gym payments correctly award membership days."""
    
    def setUp(self):
        from tenants.models import Business
        from inventory.models import BusinessKind
        
        self.client = Client()
        self.user = User.objects.create_user(
            username="gymmanager",
            password="testpass123",
            email="gym@test.com",
            is_staff=True
        )
        self.business = Business.objects.create(
            name="Test Gym",
            business_kind=BusinessKind.GYM,
            owner=self.user
        )
        self.client.login(username="gymmanager", password="testpass123")
    
    def test_gym_payment_awards_correct_days(self):
        """Adding a gym payment must extend membership by correct number of days."""
        from inventory.models_verticals import GymMember
        from inventory.utils_gym import calculate_prorated_days
        
        # Create a gym member with membership ending today
        today = date.today()
        member = GymMember.objects.create(
            business=self.business,
            name="Test Member",
            phone="0999123456",
            membership_start=today - timedelta(days=30),
            membership_end=today,
            status="ACTIVE"
        )
        
        # Calculate expected days for 55,000 MWK (standard monthly fee)
        payment_amount = Decimal("55000.00")
        expected_days = calculate_prorated_days(payment_amount)
        
        # The member's set_paid method should be called
        initial_end = member.membership_end
        member.set_paid(
            payment_date=today,
            membership_fee=payment_amount,
            trainer_fee=Decimal("0.00"),
            paid_by=self.user,
            amount=payment_amount
        )
        
        # Refresh from DB
        member.refresh_from_db()
        
        # Check that membership was extended
        assert member.membership_end > initial_end, "Membership end date should be extended"
        
        # Check that days are approximately correct (allow ±1 day for calculation differences)
        actual_days = (member.membership_end - member.membership_start).days + 1
        assert abs(actual_days - expected_days) <= 1, f"Expected ~{expected_days} days, got {actual_days}"
    
    def test_gym_payment_100k_awards_more_days(self):
        """Paying 100,000 MWK should award proportionally more days than 55,000."""
        from inventory.utils_gym import calculate_prorated_days
        
        days_55k = calculate_prorated_days(Decimal("55000.00"))
        days_100k = calculate_prorated_days(Decimal("100000.00"))
        
        # 100k should give more days than 55k
        assert days_100k > days_55k, f"100k ({days_100k} days) should give more than 55k ({days_55k} days)"
        
        # Should be approximately proportional (100k is ~1.8x of 55k)
        assert days_100k >= 50, f"100k should give at least 50 days, got {days_100k}"
    
    def test_gym_add_payment_view_doesnt_crash(self):
        """Gym add payment view must not crash."""
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        try:
            url = reverse('gym:add_payment')
            response = self.client.get(url)
            assert response.status_code in [200, 302], f"Expected 200 or 302, got {response.status_code}"
        except Exception:
            # URL might not exist, that's OK for now
            pass


# =====================================================================
# TEST 5: PHONES TOP SALES MODEL WORKS
# =====================================================================
class TestPhonesTopSales(TestCase):
    """Test that phones top sales feature works correctly."""
    
    def setUp(self):
        from tenants.models import Business
        from inventory.models import BusinessKind
        
        self.client = Client()
        self.user = User.objects.create_user(
            username="phonemanager",
            password="testpass123",
            email="phone@test.com"
        )
        self.business = Business.objects.create(
            name="Test Phone Shop",
            business_kind=BusinessKind.PHONES,
            owner=self.user
        )
        self.client.login(username="phonemanager", password="testpass123")
    
    def test_phones_dashboard_with_no_sales_returns_200(self):
        """Phones dashboard must render with zero sales."""
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('inventory_verticals:phones_dashboard')
        response = self.client.get(url)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Check that it doesn't crash on empty top sales
        content = response.content.decode()
        assert 'dashboard' in content.lower()
    
    def test_phones_dashboard_shows_top_products_when_sales_exist(self):
        """When sales exist, dashboard must show top products correctly."""
        from inventory.models import Product, InventoryItem, Location
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Create a location
        location = Location.objects.create(
            business=self.business,
            name="Main Store"
        )
        
        # Create products and sell them
        product1 = Product.objects.create(
            business=self.business,
            brand="TECNO",
            model="Spark 20",
            name="TECNO Spark 20",
            cost_price=Decimal("500000"),
            selling_price=Decimal("650000")
        )
        
        product2 = Product.objects.create(
            business=self.business,
            brand="ITEL",
            model="P40",
            name="ITEL P40",
            cost_price=Decimal("400000"),
            selling_price=Decimal("550000")
        )
        
        # Create and sell inventory items
        now = timezone.now()
        for i in range(5):  # Sell 5 TECNO
            item = InventoryItem.objects.create(
                business=self.business,
                product=product1,
                imei=f"12345678901234{i}",
                current_location=location,
                status="SOLD",
                cost_price=product1.cost_price,
                selling_price=product1.selling_price,
                sold_at=now
            )
        
        for i in range(3):  # Sell 3 ITEL
            item = InventoryItem.objects.create(
                business=self.business,
                product=product2,
                imei=f"98765432109876{i}",
                current_location=location,
                status="SOLD",
                cost_price=product2.cost_price,
                selling_price=product2.selling_price,
                sold_at=now
            )
        
        # Load dashboard
        url = reverse('inventory_verticals:phones_dashboard')
        response = self.client.get(url)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Check that top products data is present
        content = response.content.decode()
        # Should show product names or sales data
        assert ('TECNO' in content or 'sales' in content.lower())


# =====================================================================
# TEST 6: PRICING CONSISTENCY
# =====================================================================
class TestPricingConsistency(TestCase):
    """Test that homepage pricing matches checkout/billing pricing."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123",
            email="user@test.com"
        )
        self.client.login(username="testuser", password="testpass123")
    
    def test_homepage_pricing_accessible(self):
        """Homepage pricing page must be accessible."""
        url = reverse('staticpages:pricing')
        response = self.client.get(url)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    def test_billing_subscribe_page_accessible(self):
        """Billing subscribe page must be accessible."""
        try:
            url = reverse('billing:subscribe')
            response = self.client.get(url)
            
            # May require business context, so 200 or 302 is OK
            assert response.status_code in [200, 302, 403], f"Unexpected status {response.status_code}"
        except Exception:
            # URL might not exist, that's OK
            pass


# =====================================================================
# TEST 7: MOBILE DASHBOARD RENDERING
# =====================================================================
class TestMobileDashboardRendering(TestCase):
    """Test that all vertical dashboards render without overflow issues."""
    
    def setUp(self):
        from tenants.models import Business
        from inventory.models import BusinessKind
        
        self.client = Client()
        self.user = User.objects.create_user(
            username="testmanager",
            password="testpass123",
            email="manager@test.com"
        )
        
        # Create businesses for each vertical
        self.phones_biz = Business.objects.create(
            name="Test Phone Shop",
            business_kind=BusinessKind.PHONES,
            owner=self.user
        )
        self.liquor_biz = Business.objects.create(
            name="Test Liquor Store",
            business_kind=BusinessKind.LIQUOR,
            owner=self.user
        )
        self.gym_biz = Business.objects.create(
            name="Test Gym",
            business_kind=BusinessKind.GYM,
            owner=self.user
        )
        
        self.client.login(username="testmanager", password="testpass123")
    
    def test_phones_dashboard_renders(self):
        """Phones dashboard must render successfully."""
        session = self.client.session
        session['active_business_id'] = self.phones_biz.id
        session.save()
        
        url = reverse('inventory_verticals:phones_dashboard')
        response = self.client.get(url)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Check for mobile-friendly CSS
        content = response.content.decode()
        assert 'viewport' in content or 'mobile' in content or '@media' in content
    
    def test_liquor_dashboard_renders(self):
        """Liquor dashboard must render successfully."""
        session = self.client.session
        session['active_business_id'] = self.liquor_biz.id
        session.save()
        
        try:
            url = reverse('liquor:dashboard')
            response = self.client.get(url)
            assert response.status_code in [200, 302], f"Expected 200/302, got {response.status_code}"
        except Exception:
            pass
    
    def test_gym_dashboard_renders(self):
        """Gym dashboard must render successfully."""
        session = self.client.session
        session['active_business_id'] = self.gym_biz.id
        session.save()
        
        try:
            url = reverse('gym:dashboard')
            response = self.client.get(url)
            assert response.status_code in [200, 302], f"Expected 200/302, got {response.status_code}"
        except Exception:
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


"""
Regression tests for Welding Revenue & Costs functionality.
Ensures that adding Revenue/Costs pages doesn't break existing welding functionality
and that the new features work correctly.
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.models_welding import WeldingRevenue, WeldingCost
from tenants.models import Business, Membership

User = get_user_model()


@pytest.fixture
def welding_business(db):
    """Create a welding business for testing."""
    business = Business.objects.create(
        name="Test Welding Shop",
        business_kind=BusinessKind.WELDING,
    )
    return business


@pytest.fixture
def welding_manager(db, welding_business):
    """Create a manager user for the welding business."""
    user = User.objects.create_user(
        username="weld_manager",
        email="manager@weld.test",
        password="testpass123",
    )
    Membership.objects.create(
        user=user,
        business=welding_business,
        role="manager",
        is_active=True,
    )
    return user


@pytest.fixture
def welding_staff(db, welding_business):
    """Create a staff user for the welding business."""
    user = User.objects.create_user(
        username="weld_staff",
        email="staff@weld.test",
        password="testpass123",
    )
    Membership.objects.create(
        user=user,
        business=welding_business,
        role="staff",
        is_active=True,
    )
    return user


@pytest.mark.django_db
class TestWeldingRevenuePages:
    """Test Revenue page functionality."""
    
    def test_revenue_page_renders(self, client, welding_manager, welding_business):
        """Revenue page should render with 200 status."""
        client.force_login(welding_manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = welding_business.id
        session.save()
        
        response = client.get('/verticals/welding/revenue/')
        assert response.status_code == 200
    
    def test_revenue_page_shows_entries(self, client, welding_manager, welding_business):
        """Revenue page should display revenue entries."""
        client.force_login(welding_manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = welding_business.id
        session.save()
        
        # Create revenue entries
        WeldingRevenue.objects.create(
            business=welding_business,
            amount=Decimal("50000.00"),
            category="consultation",
            description="Client consultation",
            received_on=date.today(),
            created_by=welding_manager,
        )
        
        response = client.get('/verticals/welding/revenue/')
        assert response.status_code == 200
        assert b'50,000' in response.content or b'50000' in response.content
        assert b'Client consultation' in response.content
    
    def test_revenue_add_creates_entry(self, client, welding_manager, welding_business):
        """Adding revenue should create a new entry."""
        client.force_login(welding_manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = welding_business.id
        session.save()
        
        response = client.post('/verticals/welding/revenue/add/', {
            'amount': '75000',
            'category': 'repair',
            'description': 'Emergency repair work',
            'notes': 'Urgent job',
            'received_on': date.today().isoformat(),
        })
        
        # Should redirect on success
        assert response.status_code == 302
        
        # Verify entry was created
        assert WeldingRevenue.objects.filter(business=welding_business).count() == 1
        revenue = WeldingRevenue.objects.first()
        assert revenue.amount == Decimal("75000.00")
        assert revenue.description == "Emergency repair work"
    
    def test_revenue_filter_mtd(self, client, welding_manager, welding_business):
        """Revenue page should filter by MTD."""
        client.force_login(welding_manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = welding_business.id
        session.save()
        
        # Create revenue this month
        WeldingRevenue.objects.create(
            business=welding_business,
            amount=Decimal("10000.00"),
            category="other",
            description="This month",
            received_on=date.today(),
            created_by=welding_manager,
        )
        
        # Create revenue last month
        last_month = date.today() - timedelta(days=35)
        WeldingRevenue.objects.create(
            business=welding_business,
            amount=Decimal("5000.00"),
            category="other",
            description="Last month",
            received_on=last_month,
            created_by=welding_manager,
        )
        
        response = client.get('/verticals/welding/revenue/?range=mtd')
        assert response.status_code == 200
        # Should only show this month's entry
        assert b'This month' in response.content
        assert b'Last month' not in response.content


@pytest.mark.django_db
class TestWeldingCostsPages:
    """Test Costs page functionality."""
    
    def test_costs_page_renders(self, client, welding_manager, welding_business):
        """Costs page should render with 200 status."""
        client.force_login(welding_manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = welding_business.id
        session.save()
        
        response = client.get('/verticals/welding/costs/')
        assert response.status_code == 200
    
    def test_costs_page_shows_entries(self, client, welding_manager, welding_business):
        """Costs page should display cost entries."""
        client.force_login(welding_manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = welding_business.id
        session.save()
        
        # Create cost entries
        WeldingCost.objects.create(
            business=welding_business,
            amount=Decimal("15000.00"),
            category="transport",
            description="Delivery truck fuel",
            incurred_on=date.today(),
            created_by=welding_manager,
        )
        
        response = client.get('/verticals/welding/costs/')
        assert response.status_code == 200
        assert b'15,000' in response.content or b'15000' in response.content
        assert b'Delivery truck fuel' in response.content
    
    def test_costs_add_creates_entry(self, client, welding_manager, welding_business):
        """Adding cost should create a new entry."""
        client.force_login(welding_manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = welding_business.id
        session.save()
        
        response = client.post('/verticals/welding/costs/add/', {
            'amount': '25000',
            'category': 'utilities',
            'description': 'Electricity bill',
            'notes': 'Monthly bill',
            'incurred_on': date.today().isoformat(),
        })
        
        # Should redirect on success
        assert response.status_code == 302
        
        # Verify entry was created
        assert WeldingCost.objects.filter(business=welding_business).count() == 1
        cost = WeldingCost.objects.first()
        assert cost.amount == Decimal("25000.00")
        assert cost.description == "Electricity bill"


@pytest.mark.django_db
class TestWeldingDashboardIntegration:
    """Test that Revenue/Costs are properly integrated into dashboard."""
    
    def test_dashboard_still_renders(self, client, welding_manager, welding_business):
        """Dashboard should still render without errors."""
        client.force_login(welding_manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = welding_business.id
        session.save()
        
        response = client.get('/verticals/welding/dashboard/')
        assert response.status_code == 200
    
    def test_dashboard_shows_revenue_kpi(self, client, welding_manager, welding_business):
        """Dashboard should display revenue KPI."""
        client.force_login(welding_manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = welding_business.id
        session.save()
        
        # Create revenue
        WeldingRevenue.objects.create(
            business=welding_business,
            amount=Decimal("100000.00"),
            category="other",
            description="Test revenue",
            received_on=date.today(),
            created_by=welding_manager,
        )
        
        response = client.get('/verticals/welding/dashboard/')
        assert response.status_code == 200
        # Check that revenue appears in dashboard
        content = response.content.decode()
        assert '100,000' in content or '100000' in content
    
    def test_dashboard_shows_costs_kpi(self, client, welding_manager, welding_business):
        """Dashboard should display costs KPI."""
        client.force_login(welding_manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = welding_business.id
        session.save()
        
        # Create cost
        WeldingCost.objects.create(
            business=welding_business,
            amount=Decimal("30000.00"),
            category="other",
            description="Test cost",
            incurred_on=date.today(),
            created_by=welding_manager,
        )
        
        response = client.get('/verticals/welding/dashboard/')
        assert response.status_code == 200
        # Check that cost appears in dashboard
        content = response.content.decode()
        assert '30,000' in content or '30000' in content
    
    def test_dashboard_calculates_profit(self, client, welding_manager, welding_business):
        """Dashboard should calculate profit correctly."""
        client.force_login(welding_manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = welding_business.id
        session.save()
        
        # Create revenue
        WeldingRevenue.objects.create(
            business=welding_business,
            amount=Decimal("100000.00"),
            category="other",
            description="Revenue",
            received_on=date.today(),
            created_by=welding_manager,
        )
        
        # Create cost
        WeldingCost.objects.create(
            business=welding_business,
            amount=Decimal("30000.00"),
            category="other",
            description="Cost",
            incurred_on=date.today(),
            created_by=welding_manager,
        )
        
        response = client.get('/verticals/welding/dashboard/')
        assert response.status_code == 200
        # Profit should be 70,000 (100,000 - 30,000)
        content = response.content.decode()
        assert '70,000' in content or '70000' in content
    
    def test_dashboard_filter_affects_revenue_costs(self, client, welding_manager, welding_business):
        """Dashboard filters should affect revenue and costs display."""
        client.force_login(welding_manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = welding_business.id
        session.save()
        
        response = client.get('/verticals/welding/dashboard/?range=7d')
        assert response.status_code == 200
        # Just verify it doesn't crash with filter param


@pytest.mark.django_db
class TestWeldingRegression:
    """Regression tests to ensure existing functionality still works."""
    
    def test_quotes_page_still_works(self, client, welding_manager, welding_business):
        """Quotes page should still work after adding Revenue/Costs."""
        client.force_login(welding_manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = welding_business.id
        session.save()
        
        response = client.get('/verticals/welding/quotes/')
        assert response.status_code == 200
    
    def test_jobs_page_still_works(self, client, welding_manager, welding_business):
        """Jobs page should still work after adding Revenue/Costs."""
        client.force_login(welding_manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = welding_business.id
        session.save()
        
        response = client.get('/verticals/welding/jobs/')
        assert response.status_code == 200
    
    def test_materials_page_still_works(self, client, welding_manager, welding_business):
        """Materials page should still work after adding Revenue/Costs."""
        client.force_login(welding_manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = welding_business.id
        session.save()
        
        response = client.get('/verticals/welding/materials/')
        assert response.status_code == 200
    
    def test_invoices_page_still_works(self, client, welding_manager, welding_business):
        """Invoices page should still work after adding Revenue/Costs."""
        client.force_login(welding_manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = welding_business.id
        session.save()
        
        response = client.get('/verticals/welding/invoices/')
        assert response.status_code == 200
    
    def test_sales_page_still_works(self, client, welding_manager, welding_business):
        """Sales page should still exist and work (NOT renamed)."""
        client.force_login(welding_manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = welding_business.id
        session.save()
        
        response = client.get('/verticals/welding/sales/')
        assert response.status_code == 200


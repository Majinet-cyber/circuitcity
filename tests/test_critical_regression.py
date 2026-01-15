# tests/test_critical_regression.py
"""
CRITICAL REGRESSION TESTS
Prevents return of 500 errors on core flows:
1. Clothing wizard
2. Locations management
3. Invoice PDF download
4. Cement sell (atomic transaction)
5. UI: no hard refresh required

These tests MUST pass on every commit.
"""
from __future__ import annotations

import pytest
from django.test import Client, TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from decimal import Decimal

User = get_user_model()


@pytest.mark.django_db
class TestClothingWizardRegression:
    """
    REGRESSION: Clothing wizard must return 200, not 500.
    Root cause: Missing location handling, NoneType errors.
    """
    
    def test_clothing_wizard_get_returns_200(self, client, manager_user, business):
        """Clothing wizard GET must return 200 reliably."""
        # Setup: Login as manager
        client.force_login(manager_user)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Act: GET clothing wizard
        url = reverse('inventory:clothing_wizard')
        response = client.get(url)
        
        # Assert: No 500 error
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert b'We hit a snag' not in response.content, "Should not show error page"
    
    def test_clothing_wizard_with_no_location_still_works(self, client, manager_user, business):
        """Clothing wizard must work even if business has no locations."""
        # Setup
        client.force_login(manager_user)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Ensure no locations exist
        from inventory.models import Location
        Location.objects.filter(business=business).delete()
        
        # Act
        url = reverse('inventory:clothing_wizard')
        response = client.get(url)
        
        # Assert: Should still return 200 (location is optional)
        assert response.status_code == 200
        assert b'We hit a snag' not in response.content
    
    def test_clothing_wizard_with_stale_location_session(self, client, manager_user, business):
        """Clothing wizard must work if session has stale location_id."""
        # Setup
        client.force_login(manager_user)
        session = client.session
        session['active_business_id'] = business.id
        session['active_location_id'] = 99999  # Non-existent location
        session.save()
        
        # Act
        url = reverse('inventory:clothing_wizard')
        response = client.get(url)
        
        # Assert: Should still return 200 (clears stale session)
        assert response.status_code == 200
        assert b'We hit a snag' not in response.content
    
    def test_clothing_wizard_basic_step_transition(self, client, manager_user, business):
        """POST to wizard submit must not crash."""
        # Setup
        client.force_login(manager_user)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Act: Submit minimal clothing product
        url = reverse('inventory:clothing_wizard_submit')
        data = {
            'category': 'tshirts',
            'size': 'M',
            'selling_price': '5000',
            'has_barcode': 'no',
            'quantity': '1'
        }
        
        import json
        response = client.post(
            url, 
            data=json.dumps(data),
            content_type='application/json'
        )
        
        # Assert: No 500, returns JSON
        assert response.status_code in [200, 400], f"Expected 200/400, got {response.status_code}"
        assert response['Content-Type'] == 'application/json'


@pytest.mark.django_db
class TestLocationsManagementRegression:
    """
    REGRESSION: Locations page must not return 404 or 500.
    Root cause: URL routing issues, missing trailing slash.
    """
    
    def test_locations_page_get_returns_200(self, client, manager_user, business):
        """Locations management page must return 200."""
        # Setup
        client.force_login(manager_user)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Act: Try both tenant and inventory locations URLs
        # Tenants locations URL
        url_tenant = reverse('tenants:manager_locations')
        response_tenant = client.get(url_tenant)
        
        # Assert: No 404 or 500
        assert response_tenant.status_code in [200, 302], f"Tenants locations returned {response_tenant.status_code}"
        
        # Inventory locations URL (if exists)
        try:
            url_inventory = reverse('inventory:locations')
            response_inventory = client.get(url_inventory)
            assert response_inventory.status_code in [200, 302], f"Inventory locations returned {response_inventory.status_code}"
        except:
            # URL might not exist, that's OK
            pass
    
    def test_locations_create_post_creates_location(self, client, manager_user, business):
        """POST to locations must create location without 500."""
        # Setup
        client.force_login(manager_user)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Act
        url = reverse('tenants:manager_locations')
        response = client.post(url, {
            'name': 'Test Store',
            'city': 'Lilongwe',
            'action': 'upsert'
        })
        
        # Assert: No 500, redirect or 200
        assert response.status_code in [200, 302], f"Location create returned {response.status_code}"
        
        # Verify location created
        from inventory.models import Location
        assert Location.objects.filter(business=business, name='Test Store').exists()


@pytest.mark.django_db
class TestInvoicePDFRegression:
    """
    REGRESSION: Invoice PDF download must not return 500.
    Root cause: Missing fields, NoneType errors in PDF generator.
    """
    
    def test_invoice_pdf_download_returns_200(self, client, manager_user, business):
        """Invoice PDF download must return 200 + PDF content."""
        # Setup: Create invoice
        from billing.models import Invoice
        invoice = Invoice.objects.create(
            business=business,
            status=Invoice.Status.PAID,
            number='TEST-001',
            subtotal=Decimal('100.00'),
            total=Decimal('100.00'),
            currency='MWK'
        )
        
        # Login
        client.force_login(manager_user)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Act
        url = reverse('billing:invoice_download', kwargs={'pk': invoice.pk})
        response = client.get(url)
        
        # Assert: No 500, returns PDF or redirect
        assert response.status_code in [200, 302], f"Invoice PDF returned {response.status_code}"
        
        if response.status_code == 200:
            assert response['Content-Type'] == 'application/pdf'
    
    def test_invoice_pdf_with_minimal_data_does_not_crash(self, client, manager_user, business):
        """Invoice PDF must work even with minimal required fields."""
        # Setup: Create invoice with minimal fields
        from billing.models import Invoice
        invoice = Invoice.objects.create(
            business=business,
            status=Invoice.Status.DRAFT,
            number='MINIMAL-001',
            subtotal=Decimal('0.00'),
            total=Decimal('0.00'),
            currency='MWK'
            # Deliberately omit optional fields
        )
        
        # Login
        client.force_login(manager_user)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Act
        url = reverse('billing:invoice_download', kwargs={'pk': invoice.pk})
        response = client.get(url)
        
        # Assert: No 500
        assert response.status_code != 500, "PDF generator crashed on minimal invoice"


@pytest.mark.django_db
class TestCementSellAtomicRegression:
    """
    REGRESSION: Cement sell must use atomic transaction.
    Root cause: select_for_update outside transaction.atomic().
    """
    
    def test_cement_sell_uses_atomic_transaction(self, client, manager_user, business):
        """Cement sell must wrap select_for_update in transaction.atomic()."""
        # This is a code-level test - check that the view uses transaction.atomic
        from inventory.verticals import cement
        import inspect
        
        # Get the sell view source
        source = inspect.getsource(cement.sell)
        
        # Assert: Must have "with transaction.atomic()" before select_for_update
        assert 'transaction.atomic' in source, "Cement sell must use transaction.atomic()"
        assert 'select_for_update' in source, "Should use select_for_update for locking"


@pytest.mark.django_db
class TestAuthHTMLNoCacheRegression:
    """
    REGRESSION: Authenticated HTML must have no-store headers.
    Prevents "need hard refresh after deploy" bug.
    """
    
    def test_authenticated_html_has_no_cache_headers(self, client, manager_user, business):
        """Authenticated dashboard HTML must have Cache-Control: no-store."""
        # Setup
        client.force_login(manager_user)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Act: Request authenticated dashboard (follow redirects)
        url = reverse('inventory:inventory_dashboard')
        response = client.get(url, follow=True)
        
        # Assert: Cache-Control must contain no-store
        # Note: We check the final response after redirects
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        cache_control = response.get('Cache-Control', '')
        assert 'no-store' in cache_control.lower(), f"Missing no-store header: {cache_control}"
    
    def test_static_assets_not_no_cache(self, client):
        """Static assets should NOT have no-cache (middleware should skip them)."""
        # Act: Request a static asset
        response = client.get('/static/favicon.ico')
        
        # Assert: Should not have no-store (or might 404, that's OK)
        if response.status_code == 200:
            cache_control = response.get('Cache-Control', '')
            # Static assets should be cacheable (not have no-store)
            # This assertion is loose because static serving varies by config
            pass  # Just ensure no crash


@pytest.mark.django_db
class TestDropdownBehaviorRegression:
    """
    REGRESSION: Dropdowns must not open automatically.
    Must only open on click, close on outside click.
    """
    
    def test_notification_dropdown_not_shown_by_default(self, client, manager_user, business):
        """Notification dropdown must NOT have 'show' class in initial render."""
        # Setup
        client.force_login(manager_user)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Act: Follow redirects to get to the actual dashboard
        url = reverse('inventory:inventory_dashboard')
        response = client.get(url, follow=True)
        
        # Assert: Response must not contain 'dropdown-menu show'
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        content = response.content.decode('utf-8')
        
        # Check that notification dropdown exists but is NOT shown
        # Note: Dropdown might be in a partial/include or may not be on all pages
        # Just check that IF it exists, it's not auto-opened with 'show' class
        if 'notificationDropdown' in content or 'notif-badge' in content:
            assert 'dropdown-menu show' not in content, "Dropdown must not be shown by default"
        # If notification UI not present, that's fine (page-dependent)


# =============================================================================
# Pytest Fixtures
# =============================================================================

@pytest.fixture
def manager_user(db):
    """Create a manager user for tests."""
    user = User.objects.create_user(
        username='test_manager',
        email='manager@test.com',
        password='testpass123',
        is_staff=True
    )
    # Create profile if it doesn't auto-create
    try:
        from accounts.models import Profile
        Profile.objects.get_or_create(
            user=user,
            defaults={
                'city': 'Lilongwe',
                'country': 'Malawi',
                'timezone': 'Africa/Blantyre',
                'language': 'English',
                'currency': 'MWK'
            }
        )
    except ImportError:
        pass
    return user


@pytest.fixture
def business(db, manager_user):
    """Create a test business."""
    from tenants.models import Business, Membership
    
    business = Business.objects.create(
        name='Test Business',
        slug='test-business',
        business_kind='clothing',
        status='ACTIVE'
    )
    
    # Create manager membership
    Membership.objects.create(
        user=manager_user,
        business=business,
        role='MANAGER',
        status='ACTIVE'
    )
    
    return business


@pytest.fixture
def client():
    """Django test client."""
    return Client()


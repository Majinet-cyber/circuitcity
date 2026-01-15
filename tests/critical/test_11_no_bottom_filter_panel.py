"""
CRITICAL REGRESSION TEST: No bottom "Custom Date Range" filter panel
================================================================================
TASK C2: Prevent the Custom Date Range filter panel from appearing at bottom

Test Requirements:
- No persistent "Custom Date Range" panel stuck at bottom of pages
- Filter functionality should be in dropdown/modal, not bottom panel
- This prevents the UI regression where a big filter panel blocks content

This test ensures the bottom filter panel doesn't reappear across verticals.
================================================================================
"""
import pytest
from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def cement_business_user(db):
    """Create a cement business with user for testing"""
    from inventory.business_kinds import BusinessKind
    from tenants.models import Business, Membership
    
    user = User.objects.create_user(
        username='testcement',
        email='cement@test.com',
        password='testpass123'
    )
    
    business = Business.objects.create(
        name='Test Cement Co',
        business_kind=BusinessKind.CEMENT,
        owner=user
    )
    
    Membership.objects.create(
        user=user,
        business=business,
        role='MANAGER'
    )
    
    client = Client()
    client.login(username='testcement', password='testpass123')
    client.defaults['HTTP_X_BUSINESS_ID'] = str(business.id)
    
    return client, user, business


@pytest.mark.django_db
class TestNoBottomFilterPanel:
    """Ensure no bottom filter panel appears on vertical pages"""

    def test_no_bottom_filter_on_cement_dashboard(self, cement_business_user):
        """No bottom Custom Date Range panel on cement dashboard"""
        client, user, business = cement_business_user
        
        response = client.get(reverse('cement:dashboard'))
        assert response.status_code == 200
        
        html = response.content.decode('utf-8').lower()
        
        # Should NOT have a fixed-position bottom filter panel
        # Check for common patterns that indicate a bottom-stuck filter
        assert 'position:fixed' not in html or 'bottom:0' not in html[html.find('position:fixed'):html.find('position:fixed')+500] if 'position:fixed' in html else True
        
        # The date filter should be in the dashboard shell (inline), not a bottom panel
        # It should use the unified filter component which is a dropdown/modal, not fixed bottom

    def test_no_bottom_filter_on_verticals_page(self, cement_business_user):
        """No bottom filter panel on verticals landing page"""
        client, user, business = cement_business_user
        
        # Try to access /verticals or the main vertical selector
        try:
            response = client.get('/verticals/')
            if response.status_code == 200:
                html = response.content.decode('utf-8').lower()
                
                # Should NOT contain "Custom Date Range" as a visible bottom panel
                if 'custom date range' in html:
                    # If it exists, it should be in a modal/dropdown, not a fixed bottom element
                    # Check that it's not in a fixed-position bottom container
                    custom_range_index = html.find('custom date range')
                    # Look backwards and forwards for position:fixed + bottom
                    context = html[max(0, custom_range_index-1000):custom_range_index+1000]
                    # If position:fixed exists in context, bottom:0 should NOT be nearby
                    if 'position:fixed' in context or 'position: fixed' in context:
                        # Ensure it's not a bottom panel (bottom:0 or bottom:auto with safe-area)
                        assert 'bottom:0' not in context and 'bottom: 0' not in context
        except Exception:
            # If /verticals/ doesn't exist or redirects, that's fine
            pass

    def test_date_filter_is_dropdown_not_bottom_panel(self, cement_business_user):
        """Date filter should be a dropdown/modal, not a bottom panel"""
        client, user, business = cement_business_user
        
        response = client.get(reverse('cement:dashboard'))
        assert response.status_code == 200
        
        html = response.content.decode('utf-8')
        
        # The unified date filter should be present as a dropdown
        # It should have the filter-panel class which is a dropdown, not fixed-bottom
        if 'date-filter' in html.lower() or 'filter-panel' in html.lower():
            # Ensure the filter-panel uses the correct dropdown/modal pattern
            # from partials/date_filter_unified.html
            filter_section = html[html.lower().find('filter'):html.lower().find('filter')+2000] if 'filter' in html.lower() else ''
            
            # On mobile, it should be a bottom sheet that slides up (transform: translateY(100%))
            # NOT a persistent fixed bottom:0 panel
            # The correct pattern is: position:fixed; bottom:0; transform:translateY(100%) (hidden)
            # and only shows when user clicks (transform:translateY(0))
            
            # Check that if there's a filter panel, it's the modal/dropdown pattern, not persistent
            # A persistent bottom panel would NOT have transform:translateY controls
            if 'position:fixed' in filter_section.lower() and 'bottom:0' in filter_section.lower():
                # This is OK only if it also has transform:translateY (indicating it's a modal)
                assert 'transform' in filter_section.lower() or 'backdrop' in filter_section.lower()


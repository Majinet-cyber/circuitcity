"""
CRITICAL REGRESSION TEST: Navbar dropdowns must be closed on page load
================================================================================
TASK B2: Prevent navbar dropdowns from auto-opening on page load

Test Requirements:
- Notifications dropdown must NOT have "show" class on page load
- Avatar/profile menu must NOT have "show" class on page load
- aria-expanded must be "false" initially on both dropdowns
- Dropdowns should only open when user clicks the icon

This test prevents the UI regression where dropdowns appear open/overlapping
before user interaction (seen on cement dashboard and other pages).
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
class TestNavbarDropdownsClosed:
    """Ensure navbar dropdowns are closed by default on all authenticated pages"""

    def test_notifications_dropdown_closed_on_dashboard(self, cement_business_user):
        """Notifications dropdown must be closed on dashboard load"""
        client, user, business = cement_business_user
        
        # Request cement dashboard (or any authenticated page)
        response = client.get(reverse('cement:dashboard'))
        assert response.status_code == 200
        
        html = response.content.decode('utf-8')
        
        # Assert notifications button exists with correct testid
        assert 'id="ccNotifBtn"' in html
        assert 'data-testid="nav-notifications"' in html
        
        # CRITICAL: aria-expanded MUST be false initially on the notification button
        # Find the notification button section
        notif_btn_index = html.find('id="ccNotifBtn"')
        assert notif_btn_index > 0, "Notification button not found"
        
        # Check a reasonable section around the button (300 chars should cover the button element)
        notif_btn_section = html[max(0, notif_btn_index-200):notif_btn_index+300]
        assert 'aria-expanded="false"' in notif_btn_section, "Notification button should have aria-expanded='false' initially"
        
        # CRITICAL: Dropdown menu must NOT have "show" class in initial render
        notif_menu_index = html.find('id="ccNotifMenu"')
        if notif_menu_index > 0:
            # Check the menu element and ensure it doesn't have "show" class
            notif_menu_section = html[notif_menu_index:notif_menu_index+400]
            # The dropdown-menu element should not have "show" as one of its classes
            # It should be class="dropdown-menu" or class="dropdown-menu something-else" but NOT "dropdown-menu show"
            assert 'dropdown-menu show' not in notif_menu_section, "Notification dropdown should not have 'show' class initially"

    def test_avatar_dropdown_closed_on_dashboard(self, cement_business_user):
        """Avatar/profile dropdown must be closed on dashboard load"""
        client, user, business = cement_business_user
        
        response = client.get(reverse('cement:dashboard'))
        assert response.status_code == 200
        
        html = response.content.decode('utf-8')
        
        # Assert avatar button exists with correct testid
        assert 'id="userMenuBtn"' in html
        assert 'data-testid="nav-avatar"' in html
        
        # CRITICAL: aria-expanded MUST be false initially
        # Find the userMenuBtn section
        user_btn_index = html.find('id="userMenuBtn"')
        assert user_btn_index > 0, "User menu button not found"
        
        user_btn_section = html[max(0, user_btn_index-200):user_btn_index+300]
        assert 'aria-expanded="false"' in user_btn_section, "Avatar button should have aria-expanded='false' initially"
        
        # CRITICAL: User menu must NOT have "show" class in initial render
        user_menu_index = html.find('id="userMenu"')
        if user_menu_index > 0:
            user_menu_section = html[user_menu_index:user_menu_index+400]
            assert 'dropdown-menu show' not in user_menu_section, "Avatar dropdown should not have 'show' class initially"

    def test_both_dropdowns_closed_on_stock_list(self, cement_business_user):
        """Both dropdowns closed on stock list page (representative page test)"""
        client, user, business = cement_business_user
        
        response = client.get(reverse('cement:stock_list'))
        assert response.status_code == 200
        
        html = response.content.decode('utf-8')
        
        # Both dropdowns should have aria-expanded="false"
        assert 'id="ccNotifBtn"' in html
        assert 'id="userMenuBtn"' in html
        
        # Find notification button section
        notif_btn_index = html.find('id="ccNotifBtn"')
        if notif_btn_index > 0:
            notif_section = html[max(0, notif_btn_index-200):notif_btn_index+300]
            assert 'aria-expanded="false"' in notif_section, "Notifications button should be closed"
        
        # Find avatar button section
        avatar_btn_index = html.find('id="userMenuBtn"')
        if avatar_btn_index > 0:
            avatar_section = html[max(0, avatar_btn_index-200):avatar_btn_index+300]
            assert 'aria-expanded="false"' in avatar_section, "Avatar button should be closed"

    def test_no_show_class_on_any_navbar_dropdown_menus(self, cement_business_user):
        """No navbar dropdown menu should have 'show' class on page load"""
        client, user, business = cement_business_user
        
        response = client.get(reverse('cement:dashboard'))
        assert response.status_code == 200
        
        html = response.content.decode('utf-8')
        
        # Check for the specific dropdown menus and ensure they don't have "show" class
        # This is a comprehensive check that catches any accidental auto-opening
        
        # Notification menu check
        notif_menu_index = html.find('id="ccNotifMenu"')
        if notif_menu_index > 0:
            notif_menu_section = html[notif_menu_index:notif_menu_index+500]
            assert 'dropdown-menu show' not in notif_menu_section, "Notification menu should not have 'show' class"
        
        # User menu check
        user_menu_index = html.find('id="userMenu"')
        if user_menu_index > 0:
            user_menu_section = html[user_menu_index:user_menu_index+500]
            assert 'dropdown-menu show' not in user_menu_section, "User menu should not have 'show' class"


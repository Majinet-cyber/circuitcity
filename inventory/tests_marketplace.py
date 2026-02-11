# inventory/tests_marketplace.py
"""
Regression tests for marketplace functionality.

Tests:
1. /marketplace/ returns 200 and only shows active listings
2. Public business page shows active listings
3. Enquiry submission creates MarketplaceEnquiry and redirects/returns success
4. Manager-only listing create/edit/delete requires auth
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.models_marketplace import MarketplaceListing, MarketplaceEnquiry

User = get_user_model()


@pytest.mark.django_db
class MarketplacePublicTests(TestCase):
    """Test public marketplace pages (no login required)."""

    def setUp(self):
        """Set up test data."""
        # Create business
        self.business = Business.objects.create(
            name="Test Shop",
            slug="test-shop",
            business_kind="phones",
        )
        
        # Create active listing
        self.active_listing = MarketplaceListing.objects.create(
            business=self.business,
            title="iPhone 13",
            description="Brand new iPhone 13",
            price=Decimal("500000.00"),
            vertical="phones",
            is_active=True,
        )
        
        # Create inactive listing
        self.inactive_listing = MarketplaceListing.objects.create(
            business=self.business,
            title="Old Phone",
            description="Inactive listing",
            price=Decimal("100000.00"),
            vertical="phones",
            is_active=False,
        )
        
        self.client = Client()

    def test_marketplace_page_returns_200(self):
        """Test /marketplace/ returns 200."""
        url = reverse('inventory:marketplace_public')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_marketplace_only_shows_active_listings(self):
        """Test /marketplace/ only shows active listings."""
        url = reverse('inventory:marketplace_public')
        response = self.client.get(url)
        
        # Check active listing is shown
        self.assertContains(response, "iPhone 13")
        
        # Check inactive listing is NOT shown
        self.assertNotContains(response, "Old Phone")

    def test_business_public_page_returns_200(self):
        """Test /public/<business_slug>/ returns 200."""
        url = reverse('inventory:business_public_page', args=[self.business.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_business_public_page_shows_active_listings(self):
        """Test business public page only shows active listings."""
        url = reverse('inventory:business_public_page', args=[self.business.slug])
        response = self.client.get(url)
        
        # Check active listing is shown
        self.assertContains(response, "iPhone 13")
        
        # Check inactive listing is NOT shown
        self.assertNotContains(response, "Old Phone")

    def test_enquiry_submission_creates_record(self):
        """Test enquiry submission creates MarketplaceEnquiry."""
        url = reverse('inventory:submit_enquiry', args=[self.active_listing.id])
        
        data = {
            'email': 'customer@example.com',
            'name': 'John Doe',
            'phone': '+265991234567',
            'message': 'I want to buy this phone',
        }
        
        response = self.client.post(url, data, follow=True)
        
        # Check enquiry was created
        self.assertEqual(MarketplaceEnquiry.objects.count(), 1)
        
        enquiry = MarketplaceEnquiry.objects.first()
        self.assertEqual(enquiry.email, 'customer@example.com')
        self.assertEqual(enquiry.name, 'John Doe')
        self.assertEqual(enquiry.phone, '+265991234567')
        self.assertEqual(enquiry.message, 'I want to buy this phone')
        self.assertEqual(enquiry.listing, self.active_listing)
        self.assertEqual(enquiry.business, self.business)
        self.assertFalse(enquiry.is_read)

    def test_enquiry_submission_requires_email(self):
        """Test enquiry submission requires email."""
        url = reverse('inventory:submit_enquiry', args=[self.active_listing.id])
        
        data = {
            'name': 'John Doe',
            'message': 'I want to buy this phone',
        }
        
        response = self.client.post(url, data, follow=True)
        
        # Check enquiry was NOT created
        self.assertEqual(MarketplaceEnquiry.objects.count(), 0)


@pytest.mark.django_db
class MarketplaceManagerTests(TestCase):
    """Test manager-only marketplace features."""

    def setUp(self):
        """Set up test data."""
        # Create user and business
        self.user = User.objects.create_user(
            username='manager',
            email='manager@example.com',
            password='testpass123'
        )
        
        self.business = Business.objects.create(
            name="Test Shop",
            slug="test-shop",
            business_kind="phones",
        )
        
        # Create membership
        self.membership = Membership.objects.create(
            user=self.user,
            business=self.business,
            role='manager',
            status='ACTIVE',
        )
        
        self.client = Client()

    def test_create_listing_requires_auth(self):
        """Test creating listing requires authentication."""
        url = reverse('inventory:create_listing')
        response = self.client.get(url)
        
        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response.url)

    def test_create_listing_works_for_manager(self):
        """Test manager can create listing."""
        self.client.login(username='manager', password='testpass123')
        
        url = reverse('inventory:create_listing')
        data = {
            'title': 'New Phone',
            'description': 'Brand new phone',
            'price': '300000',
            'vertical': 'phones',
        }
        
        response = self.client.post(url, data, follow=True)
        
        # Check listing was created
        self.assertEqual(MarketplaceListing.objects.count(), 1)
        
        listing = MarketplaceListing.objects.first()
        self.assertEqual(listing.title, 'New Phone')
        self.assertEqual(listing.business, self.business)
        self.assertEqual(listing.created_by, self.user)
        self.assertTrue(listing.is_active)

    def test_edit_listing_requires_auth(self):
        """Test editing listing requires authentication."""
        listing = MarketplaceListing.objects.create(
            business=self.business,
            title="Test Listing",
            is_active=True,
        )
        
        url = reverse('inventory:edit_listing', args=[listing.id])
        response = self.client.get(url)
        
        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response.url)

    def test_delete_listing_requires_auth(self):
        """Test deleting listing requires authentication."""
        listing = MarketplaceListing.objects.create(
            business=self.business,
            title="Test Listing",
            is_active=True,
        )
        
        url = reverse('inventory:delete_listing', args=[listing.id])
        response = self.client.post(url)
        
        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response.url)
        
        # Listing should still exist
        self.assertTrue(MarketplaceListing.objects.filter(id=listing.id).exists())

    def test_delete_listing_works_for_manager(self):
        """Test manager can delete listing."""
        self.client.login(username='manager', password='testpass123')
        
        listing = MarketplaceListing.objects.create(
            business=self.business,
            title="Test Listing",
            is_active=True,
        )
        
        url = reverse('inventory:delete_listing', args=[listing.id])
        response = self.client.post(url, follow=True)
        
        # Listing should be deleted
        self.assertFalse(MarketplaceListing.objects.filter(id=listing.id).exists())

    def test_view_enquiries_requires_auth(self):
        """Test viewing enquiries requires authentication."""
        url = reverse('inventory:view_enquiries')
        response = self.client.get(url)
        
        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response.url)

    def test_manager_can_view_enquiries(self):
        """Test manager can view enquiries for their business."""
        self.client.login(username='manager', password='testpass123')
        
        # Create listing and enquiry
        listing = MarketplaceListing.objects.create(
            business=self.business,
            title="Test Listing",
            is_active=True,
        )
        
        enquiry = MarketplaceEnquiry.objects.create(
            listing=listing,
            business=self.business,
            email='customer@example.com',
            name='Customer',
            message='I want this',
        )
        
        url = reverse('inventory:view_enquiries')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'customer@example.com')
        self.assertContains(response, 'I want this')


@pytest.mark.django_db
class MarketplaceSecurityTests(TestCase):
    """Test security and data isolation."""

    def setUp(self):
        """Set up test data with multiple businesses."""
        # Business 1
        self.business1 = Business.objects.create(
            name="Shop 1",
            slug="shop-1",
        )
        
        self.user1 = User.objects.create_user(
            username='manager1',
            password='testpass123'
        )
        
        Membership.objects.create(
            user=self.user1,
            business=self.business1,
            role='manager',
            status='ACTIVE',
        )
        
        # Business 2
        self.business2 = Business.objects.create(
            name="Shop 2",
            slug="shop-2",
        )
        
        self.user2 = User.objects.create_user(
            username='manager2',
            password='testpass123'
        )
        
        Membership.objects.create(
            user=self.user2,
            business=self.business2,
            role='manager',
            status='ACTIVE',
        )
        
        self.client = Client()

    def test_manager_cannot_edit_other_business_listing(self):
        """Test manager cannot edit listing from another business."""
        # Create listing for business 2
        listing = MarketplaceListing.objects.create(
            business=self.business2,
            title="Business 2 Listing",
            is_active=True,
        )
        
        # Login as manager 1
        self.client.login(username='manager1', password='testpass123')
        
        # Try to edit business 2's listing
        url = reverse('inventory:edit_listing', args=[listing.id])
        response = self.client.get(url)
        
        # Should return 404 (not found in their business)
        self.assertEqual(response.status_code, 404)

    def test_manager_cannot_delete_other_business_listing(self):
        """Test manager cannot delete listing from another business."""
        # Create listing for business 2
        listing = MarketplaceListing.objects.create(
            business=self.business2,
            title="Business 2 Listing",
            is_active=True,
        )
        
        # Login as manager 1
        self.client.login(username='manager1', password='testpass123')
        
        # Try to delete business 2's listing
        url = reverse('inventory:delete_listing', args=[listing.id])
        response = self.client.post(url)
        
        # Should return 404
        self.assertEqual(response.status_code, 404)
        
        # Listing should still exist
        self.assertTrue(MarketplaceListing.objects.filter(id=listing.id).exists())


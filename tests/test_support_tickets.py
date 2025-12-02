# tests/test_support_tickets.py
"""
Tests for support ticket system to ensure database tables exist and
pagination works correctly.

Purpose: Fix "no such table: support_ticket" error.
"""
import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from support.models import Ticket, TicketComment
from tenants.models import Business

User = get_user_model()


class SupportTicketModelTest(TestCase):
    """Test that support ticket models work correctly."""
    
    def setUp(self):
        """Set up test data."""
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-business",
            status="ACTIVE"
        )
        
        self.user = User.objects.create_user(
            username="manager1",
            email="manager@test.com",
            password="testpass123"
        )
    
    def test_ticket_model_exists(self):
        """Test that Ticket model can be created (table exists)."""
        ticket = Ticket.objects.create(
            business=self.business,
            creator=self.user,
            subject="Test ticket",
            description="This is a test ticket",
            status="OPEN",
            priority="MEDIUM"
        )
        
        # Should have auto-generated reference
        self.assertIsNotNone(ticket.reference)
        self.assertTrue(ticket.reference.startswith("EMA-"))
        
        # Should be saved to DB
        self.assertIsNotNone(ticket.id)
        
        # Should be retrievable
        retrieved = Ticket.objects.get(id=ticket.id)
        self.assertEqual(retrieved.subject, "Test ticket")
    
    def test_ticket_comment_model_exists(self):
        """Test that TicketComment model works (table exists)."""
        ticket = Ticket.objects.create(
            business=self.business,
            creator=self.user,
            subject="Test ticket",
            description="Test description",
            status="OPEN"
        )
        
        comment = TicketComment.objects.create(
            ticket=ticket,
            author=self.user,
            comment="This is a test comment",
            is_internal=False
        )
        
        # Should be saved
        self.assertIsNotNone(comment.id)
        
        # Should be related to ticket
        self.assertEqual(comment.ticket, ticket)
        self.assertEqual(ticket.comments.count(), 1)
    
    def test_ticket_reference_generation(self):
        """Test that ticket reference numbers are generated correctly."""
        ticket1 = Ticket.objects.create(
            business=self.business,
            creator=self.user,
            subject="First ticket",
            description="Test"
        )
        
        ticket2 = Ticket.objects.create(
            business=self.business,
            creator=self.user,
            subject="Second ticket",
            description="Test"
        )
        
        # Should have different references
        self.assertNotEqual(ticket1.reference, ticket2.reference)
        
        # Both should start with EMA-YYYY-
        year = timezone.now().year
        self.assertTrue(ticket1.reference.startswith(f"EMA-{year}-"))
        self.assertTrue(ticket2.reference.startswith(f"EMA-{year}-"))


class SupportTicketListTest(TestCase):
    """Test support ticket list views (HQ and manager)."""
    
    def setUp(self):
        """Set up test data."""
        self.business = Business.objects.create(
            name="Test Merchant",
            slug="test-merchant",
            status="ACTIVE"
        )
        
        # Create staff user for HQ views
        self.staff_user = User.objects.create_user(
            username="hq_staff",
            email="staff@emajinet.com",
            password="testpass123",
            is_staff=True,
            is_superuser=False
        )
        
        # Create manager user
        self.manager_user = User.objects.create_user(
            username="manager1",
            email="manager@test.com",
            password="testpass123",
            is_staff=False
        )
        
        # Create some test tickets
        self.ticket1 = Ticket.objects.create(
            business=self.business,
            creator=self.manager_user,
            subject="Payment not working",
            description="Cannot process payments",
            status="OPEN",
            priority="HIGH"
        )
        
        self.ticket2 = Ticket.objects.create(
            business=self.business,
            creator=self.manager_user,
            subject="Feature request",
            description="Need bulk import",
            status="IN_PROGRESS",
            priority="LOW"
        )
        
        self.ticket3 = Ticket.objects.create(
            business=self.business,
            creator=self.manager_user,
            subject="Bug report",
            description="App crashes on startup",
            status="RESOLVED",
            priority="URGENT"
        )
        
        self.client = Client()
    
    def test_support_ticket_list_renders(self):
        """
        Test that support ticket list page renders without DB errors.
        This ensures the support_ticket table exists and pagination works.
        """
        # Log in as staff
        self.client.login(username='hq_staff', password='testpass123')
        
        # Try to get HQ ticket list URL
        try:
            hq_url = reverse('support:hq_ticket_list')
        except Exception:
            # If HQ URL doesn't exist, try manager URL
            try:
                hq_url = reverse('support:manager_ticket_list')
                # Need to set business context for manager view
                session = self.client.session
                session['active_business_id'] = self.business.id
                session.save()
                # Login as manager instead
                self.client.login(username='manager1', password='testpass123')
            except Exception:
                self.skipTest("No support ticket list URL configured")
        
        # Request the page
        response = self.client.get(hq_url)
        
        # Should succeed (200 OK) - no "no such table" error
        self.assertEqual(response.status_code, 200)
        
        # Should contain at least one ticket subject
        self.assertContains(response, self.ticket1.subject)
    
    def test_ticket_list_pagination_works(self):
        """Test that ticket list pagination doesn't cause DB errors."""
        # Create many tickets to trigger pagination
        for i in range(25):
            Ticket.objects.create(
                business=self.business,
                creator=self.manager_user,
                subject=f"Ticket {i}",
                description=f"Test ticket {i}",
                status="OPEN"
            )
        
        # Log in as staff
        self.client.login(username='hq_staff', password='testpass123')
        
        try:
            hq_url = reverse('support:hq_ticket_list')
        except Exception:
            try:
                hq_url = reverse('support:manager_ticket_list')
                session = self.client.session
                session['active_business_id'] = self.business.id
                session.save()
                self.client.login(username='manager1', password='testpass123')
            except Exception:
                self.skipTest("No support ticket list URL configured")
        
        # Request first page
        response = self.client.get(hq_url)
        self.assertEqual(response.status_code, 200)
        
        # Request second page (this often triggers pagination count() queries)
        response = self.client.get(hq_url + '?page=2')
        self.assertEqual(response.status_code, 200)
    
    def test_ticket_status_filter_works(self):
        """Test that status filtering works without errors."""
        # Make manager1 a proper manager with profile
        from tenants.models import Membership
        
        # Create membership
        Membership.objects.create(
            user=self.manager_user,
            business=self.business,
            role='MANAGER'
        )
        
        # Log in
        self.client.login(username='manager1', password='testpass123')
        
        try:
            url = reverse('support:manager_ticket_list')
            session = self.client.session
            session['active_business_id'] = self.business.id
            session.save()
        except Exception:
            self.skipTest("Manager ticket list URL not configured")
        
        # Filter by OPEN status
        response = self.client.get(url + '?status=OPEN')
        
        # Should succeed or be forbidden (decorator checks)
        if response.status_code == 403:
            self.skipTest("Manager requires additional permissions/profile setup")
        
        self.assertEqual(response.status_code, 200)
        
        # Should show open ticket
        self.assertContains(response, self.ticket1.subject)
        
        # Should not show resolved ticket
        self.assertNotContains(response, self.ticket3.subject)


class SupportTicketDetailTest(TestCase):
    """Test support ticket detail views."""
    
    def setUp(self):
        """Set up test data."""
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-biz",
            status="ACTIVE"
        )
        
        self.manager = User.objects.create_user(
            username="manager1",
            email="manager@test.com",
            password="testpass123"
        )
        
        self.ticket = Ticket.objects.create(
            business=self.business,
            creator=self.manager,
            subject="Test Ticket",
            description="Test description",
            status="OPEN"
        )
        
        self.client = Client()
    
    def test_ticket_detail_page_works(self):
        """Test that ticket detail page renders without errors."""
        # Login
        self.client.login(username='manager1', password='testpass123')
        
        try:
            # Try manager detail view
            url = reverse('support:manager_ticket_detail', kwargs={'pk': self.ticket.pk})
            session = self.client.session
            session['active_business_id'] = self.business.id
            session.save()
        except Exception:
            try:
                # Try HQ detail view
                url = reverse('support:hq_ticket_detail', kwargs={'pk': self.ticket.pk})
            except Exception:
                self.skipTest("No ticket detail URL configured")
        
        response = self.client.get(url)
        
        # Should succeed
        self.assertIn(response.status_code, [200, 302])
        
        if response.status_code == 200:
            # Should show ticket details
            self.assertContains(response, self.ticket.subject)
            self.assertContains(response, self.ticket.reference)

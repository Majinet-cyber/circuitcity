# tests/test_support_tickets.py
"""
Tests for the support ticket system.
"""
import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from tenants.models import Business, Membership
from support.models import Ticket, TicketComment

User = get_user_model()


@pytest.mark.django_db
class TicketSystemTest(TestCase):
    """Test ticket creation and management."""
    
    def setUp(self):
        """Create test users and business."""
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-business",
            status="ACTIVE"
        )
        
        self.manager = User.objects.create_user(
            username="manager",
            password="password123"
        )
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        self.hq_staff = User.objects.create_user(
            username="hq_staff",
            password="password123",
            is_staff=True
        )
        
        self.client = Client()
    
    def test_manager_can_create_ticket(self):
        """Managers can create support tickets."""
        self.client.login(username="manager", password="password123")
        
        # Set active business
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Create ticket
        response = self.client.post('/support/tickets/create/', {
            'subject': 'Test Issue',
            'description': 'This is a test issue description.',
            'priority': 'MEDIUM'
        }, follow=True)
        
        self.assertEqual(response.status_code, 200)
        
        # Verify ticket was created
        ticket = Ticket.objects.filter(business=self.business).first()
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket.subject, 'Test Issue')
        self.assertTrue(ticket.reference.startswith('EMA-'))
    
    def test_ticket_reference_generation(self):
        """Tickets get unique reference numbers."""
        ticket1 = Ticket.objects.create(
            business=self.business,
            creator=self.manager,
            subject="First Ticket",
            description="Description",
            status="OPEN"
        )
        
        ticket2 = Ticket.objects.create(
            business=self.business,
            creator=self.manager,
            subject="Second Ticket",
            description="Description",
            status="OPEN"
        )
        
        self.assertTrue(ticket1.reference.startswith('EMA-'))
        self.assertTrue(ticket2.reference.startswith('EMA-'))
        self.assertNotEqual(ticket1.reference, ticket2.reference)
    
    def test_hq_can_view_all_tickets(self):
        """HQ staff can see tickets from all businesses."""
        # Create another business with a ticket
        other_business = Business.objects.create(
            name="Other Business",
            slug="other-business",
            status="ACTIVE"
        )
        
        Ticket.objects.create(
            business=self.business,
            creator=self.manager,
            subject="Ticket 1",
            description="Description",
            status="OPEN"
        )
        
        Ticket.objects.create(
            business=other_business,
            creator=self.manager,
            subject="Ticket 2",
            description="Description",
            status="OPEN"
        )
        
        # Login as HQ staff
        self.client.login(username="hq_staff", password="password123")
        
        response = self.client.get('/support/hq/tickets/')
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode()
        self.assertIn("Ticket 1", content)
        self.assertIn("Ticket 2", content)
    
    def test_manager_cannot_see_other_business_tickets(self):
        """Managers only see their own business's tickets."""
        # Create another business
        other_business = Business.objects.create(
            name="Other Business",
            slug="other-business",
            status="ACTIVE"
        )
        
        # Create tickets for both businesses
        my_ticket = Ticket.objects.create(
            business=self.business,
            creator=self.manager,
            subject="My Ticket",
            description="Description",
            status="OPEN"
        )
        
        other_ticket = Ticket.objects.create(
            business=other_business,
            creator=self.manager,
            subject="Other Ticket",
            description="Description",
            status="OPEN"
        )
        
        # Login as manager
        self.client.login(username="manager", password="password123")
        
        # Set active business
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get('/support/tickets/')
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode()
        self.assertIn("My Ticket", content)
        self.assertNotIn("Other Ticket", content)
    
    def test_ticket_comments(self):
        """Comments can be added to tickets."""
        ticket = Ticket.objects.create(
            business=self.business,
            creator=self.manager,
            subject="Test Ticket",
            description="Description",
            status="OPEN"
        )
        
        comment = TicketComment.objects.create(
            ticket=ticket,
            author=self.manager,
            comment="This is a test comment"
        )
        
        self.assertEqual(ticket.comments.count(), 1)
        self.assertEqual(comment.comment, "This is a test comment")
    
    def test_internal_comments_hidden_from_managers(self):
        """Internal comments are only visible to HQ staff."""
        ticket = Ticket.objects.create(
            business=self.business,
            creator=self.manager,
            subject="Test Ticket",
            description="Description",
            status="OPEN"
        )
        
        # Public comment
        TicketComment.objects.create(
            ticket=ticket,
            author=self.hq_staff,
            comment="Public comment",
            is_internal=False
        )
        
        # Internal comment
        TicketComment.objects.create(
            ticket=ticket,
            author=self.hq_staff,
            comment="Internal note",
            is_internal=True
        )
        
        # Login as manager
        self.client.login(username="manager", password="password123")
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get(f'/support/tickets/{ticket.pk}/')
        content = response.content.decode()
        
        self.assertIn("Public comment", content)
        self.assertNotIn("Internal note", content)


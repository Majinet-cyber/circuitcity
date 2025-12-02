# support/tests.py
"""
Tests for the support ticket system.
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from tenants.models import Business, Membership
from support.models import Ticket

User = get_user_model()


@pytest.fixture
def hq_user(db):
    """Create an HQ staff user."""
    user = User.objects.create_user(
        username="hq_staff",
        email="hq@test.com",
        password="testpass123",
        is_staff=True
    )
    return user


@pytest.fixture
def manager_user(db):
    """Create a manager user."""
    return User.objects.create_user(
        username="manager",
        email="manager@test.com",
        password="testpass123"
    )


@pytest.fixture
def test_business(db):
    """Create a test business."""
    return Business.objects.create(
        name="Test Business",
        slug="test-business",
        status="ACTIVE"
    )


@pytest.fixture
def test_ticket(db, test_business, manager_user):
    """Create a test ticket."""
    ticket = Ticket.objects.create(
        business=test_business,
        creator=manager_user,
        subject="Test Issue",
        description="This is a test issue description.",
        status="OPEN",
        priority="MEDIUM"
    )
    # Generate reference number
    ticket.reference = f"EMA-2025-{ticket.id:06d}"
    ticket.save()
    return ticket


@pytest.mark.django_db
class TestHQTicketsPage:
    """Test the HQ tickets list page."""

    def test_hq_tickets_page_loads_for_staff(self, client: Client, hq_user):
        """HQ staff should be able to access the tickets page."""
        client.force_login(hq_user)
        
        response = client.get(reverse('support:hq_ticket_list'))
        
        assert response.status_code == 200
        assert 'tickets' in response.context
        assert 'status_choices' in response.context
        assert 'priority_choices' in response.context
        assert 'businesses' in response.context

    def test_hq_tickets_page_shows_ticket(
        self, client: Client, hq_user, test_ticket
    ):
        """HQ tickets page should display created tickets."""
        client.force_login(hq_user)
        
        response = client.get(reverse('support:hq_ticket_list'))
        
        assert response.status_code == 200
        content = response.content.decode()
        assert test_ticket.subject in content
        assert test_ticket.reference in content

    def test_hq_tickets_page_requires_staff(self, client: Client, manager_user):
        """Non-staff users should not be able to access HQ tickets page."""
        client.force_login(manager_user)
        
        response = client.get(reverse('support:hq_ticket_list'))
        
        # Should redirect (403 or 302)
        assert response.status_code in [302, 403]

    def test_hq_ticket_detail_loads(
        self, client: Client, hq_user, test_ticket
    ):
        """HQ staff should be able to view ticket details."""
        client.force_login(hq_user)
        
        response = client.get(
            reverse('support:hq_ticket_detail', kwargs={'pk': test_ticket.pk})
        )
        
        assert response.status_code == 200
        assert 'ticket' in response.context
        assert response.context['ticket'] == test_ticket
        assert 'update_form' in response.context
        assert 'comment_form' in response.context


@pytest.mark.django_db
class TestManagerTickets:
    """Test manager ticket views."""

    def test_manager_ticket_list_requires_business(
        self, client: Client, manager_user
    ):
        """Manager must have an active business to view tickets."""
        client.force_login(manager_user)
        
        response = client.get(reverse('support:manager_ticket_list'))
        
        # Should redirect or return 403
        assert response.status_code in [302, 403]

    def test_manager_can_view_their_tickets(
        self, client: Client, manager_user, test_business, test_ticket
    ):
        """Manager should see only their business's tickets."""
        # Create membership
        Membership.objects.create(
            user=manager_user,
            business=test_business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        client.force_login(manager_user)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = test_business.id
        session.save()
        
        response = client.get(reverse('support:manager_ticket_list'))
        
        assert response.status_code == 200
        assert 'tickets' in response.context


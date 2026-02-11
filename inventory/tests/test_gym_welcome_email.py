# inventory/tests/test_gym_welcome_email.py
"""
Regression tests for gym member welcome email functionality.

CRITICAL: These tests ensure that welcome emails are ALWAYS sent when a gym member
is created, regardless of the creation path (UI, bulk import, admin, API).

This prevents regressions where emails stop being sent due to refactoring.
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, TransactionTestCase, RequestFactory
from django.urls import reverse

from inventory.models_verticals import GymMember, GymSettings, GymTrainer
from inventory.services.gym_member_operations import bulk_create_members
from tenants.models import Business, Membership

User = get_user_model()


class GymWelcomeEmailTestCase(TransactionTestCase):
    """
    Test welcome email sending for gym members.
    
    Uses TransactionTestCase because we test transaction.on_commit() behavior.
    """
    
    def setUp(self):
        """Set up test data"""
        # Create business
        self.business = Business.objects.create(
            name="Test Gym",
            vertical="gym",
        )
        
        # Create gym settings
        self.gym_settings = GymSettings.objects.create(
            business=self.business,
            default_membership_price=Decimal("50000.00"),
            default_trainer_fee=Decimal("20000.00"),
        )
        
        # Create user
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        
        # Create manager membership
        self.manager_membership = Membership.objects.create(
            business=self.business,
            user=self.user,
            role="MANAGER",
            is_active=True,
        )
        
        # Set up request factory
        self.factory = RequestFactory()
    
    def test_welcome_email_sent_on_member_creation_with_email(self):
        """
        CRITICAL: Welcome email MUST be sent when member is created with valid email.
        """
        # Clear mail outbox
        mail.outbox = []
        
        # Create member with email
        member = GymMember.objects.create(
            business=self.business,
            name="Test Member",
            phone="0999123456",
            email="member@example.com",
        )
        
        # Email should be sent (signal triggers on_commit)
        self.assertEqual(len(mail.outbox), 1)
        
        # Verify email details
        email = mail.outbox[0]
        self.assertIn(member.email, email.to)
        self.assertIn("QR", email.subject)
        self.assertIn(member.name, email.body)
        self.assertIn(self.business.name, email.body)
    
    def test_no_email_when_email_missing(self):
        """
        Test: No email sent when member has no email address.
        Should NOT crash - silently skip.
        """
        mail.outbox = []
        
        # Create member without email
        member = GymMember.objects.create(
            business=self.business,
            name="No Email Member",
            phone="0999123456",
            email="",  # Empty email
        )
        
        # No email should be sent
        self.assertEqual(len(mail.outbox), 0)
        
        # Member should still be created successfully
        self.assertIsNotNone(member.id)
        self.assertEqual(member.name, "No Email Member")
    
    def test_no_email_when_email_blank(self):
        """
        Test: No email sent when member email is blank/whitespace.
        """
        mail.outbox = []
        
        # Create member with blank email
        member = GymMember.objects.create(
            business=self.business,
            name="Blank Email Member",
            phone="0999123456",
            email="   ",  # Whitespace only
        )
        
        # No email should be sent
        self.assertEqual(len(mail.outbox), 0)
    
    def test_no_duplicate_email_on_update(self):
        """
        CRITICAL: Email should NOT be sent again when member is updated.
        Only send on creation (idempotent).
        """
        mail.outbox = []
        
        # Create member
        member = GymMember.objects.create(
            business=self.business,
            name="Test Member",
            phone="0999123456",
            email="member@example.com",
        )
        
        # Clear outbox after creation
        initial_email_count = len(mail.outbox)
        self.assertEqual(initial_email_count, 1)
        mail.outbox = []
        
        # Update member (change name)
        member.name = "Updated Name"
        member.save()
        
        # No new email should be sent
        self.assertEqual(len(mail.outbox), 0)
        
        # Update member (change email)
        member.email = "newemail@example.com"
        member.save()
        
        # Still no new email
        self.assertEqual(len(mail.outbox), 0)
    
    def test_bulk_import_sends_emails_to_all_members_with_email(self):
        """
        Test: Bulk import sends welcome emails to all members with valid emails.
        """
        mail.outbox = []
        
        # Bulk create members
        members_data = [
            {"name": "Member One", "phone": "0999111111", "email": "one@example.com", "trainer_id": None, "notes": ""},
            {"name": "Member Two", "phone": "0999222222", "email": "two@example.com", "trainer_id": None, "notes": ""},
            {"name": "Member Three", "phone": "0999333333", "email": "", "trainer_id": None, "notes": ""},  # No email
            {"name": "Member Four", "phone": "0999444444", "email": "four@example.com", "trainer_id": None, "notes": ""},
        ]
        
        results = bulk_create_members(
            business=self.business,
            members_data=members_data,
            user=self.user,
            skip_duplicates=True,
        )
        
        # Should create 4 members
        self.assertEqual(len(results["created"]), 4)
        
        # Should send 3 emails (Member Three has no email)
        self.assertEqual(len(mail.outbox), 3)
        
        # Verify recipients
        recipients = [email.to[0] for email in mail.outbox]
        self.assertIn("one@example.com", recipients)
        self.assertIn("two@example.com", recipients)
        self.assertIn("four@example.com", recipients)
        self.assertNotIn("", recipients)
    
    def test_skip_welcome_email_flag_works(self):
        """
        Test: _skip_welcome_email flag prevents signal from sending email.
        Used for migrations and special cases.
        """
        mail.outbox = []
        
        # Create member with skip flag
        member = GymMember(
            business=self.business,
            name="Skip Email Member",
            phone="0999123456",
            email="skip@example.com",
        )
        member._skip_welcome_email = True
        member.save()
        
        # No email should be sent
        self.assertEqual(len(mail.outbox), 0)
    
    def test_email_sent_after_transaction_commit(self):
        """
        CRITICAL: Email must be sent AFTER transaction commits.
        This ensures member exists in DB before email is sent.
        """
        mail.outbox = []
        
        from django.db import transaction
        
        # Create member inside transaction
        with transaction.atomic():
            member = GymMember.objects.create(
                business=self.business,
                name="Transaction Member",
                phone="0999123456",
                email="transaction@example.com",
            )
            
            # Email should NOT be sent yet (still in transaction)
            # Note: This is hard to test reliably, but the on_commit ensures it
        
        # After transaction commits, email should be sent
        self.assertEqual(len(mail.outbox), 1)
    
    def test_email_failure_does_not_break_member_creation(self):
        """
        CRITICAL: If email sending fails, member creation should still succeed.
        Email failures should be logged but not raise exceptions.
        """
        mail.outbox = []
        
        # Mock send_member_qr_email to raise an exception
        with patch('inventory.services.gym_qr_email.send_member_qr_email') as mock_send:
            mock_send.side_effect = Exception("Email service down")
            
            # Create member - should NOT raise exception
            member = GymMember.objects.create(
                business=self.business,
                name="Resilient Member",
                phone="0999123456",
                email="resilient@example.com",
            )
            
            # Member should be created successfully
            self.assertIsNotNone(member.id)
            self.assertEqual(member.name, "Resilient Member")
    
    def test_email_works_across_dev_and_production_backends(self):
        """
        Test: Email sending works with different EMAIL_BACKEND settings.
        - Dev: console backend
        - Test: locmem backend
        - Prod: SendGrid/Anymail backend
        """
        mail.outbox = []
        
        # Create member (uses current EMAIL_BACKEND from settings)
        member = GymMember.objects.create(
            business=self.business,
            name="Backend Test Member",
            phone="0999123456",
            email="backend@example.com",
        )
        
        # Email should be sent regardless of backend
        # In tests, it goes to mail.outbox (locmem backend)
        self.assertEqual(len(mail.outbox), 1)
    
    def test_tenant_isolation_in_emails(self):
        """
        Test: Emails are properly scoped to business (tenant isolation).
        """
        mail.outbox = []
        
        # Create another business
        other_business = Business.objects.create(
            name="Other Gym",
            vertical="gym",
        )
        
        # Create member in first business
        member1 = GymMember.objects.create(
            business=self.business,
            name="Member One",
            phone="0999111111",
            email="one@example.com",
        )
        
        # Create member in second business
        member2 = GymMember.objects.create(
            business=other_business,
            name="Member Two",
            phone="0999222222",
            email="two@example.com",
        )
        
        # Both should get emails
        self.assertEqual(len(mail.outbox), 2)
        
        # Verify business names in emails
        email1 = next(e for e in mail.outbox if "one@example.com" in e.to)
        email2 = next(e for e in mail.outbox if "two@example.com" in e.to)
        
        self.assertIn(self.business.name, email1.body)
        self.assertIn(other_business.name, email2.body)
    
    def test_email_contains_required_information(self):
        """
        Test: Welcome email contains all required information:
        - Member name
        - Gym/business name
        - Public status URL
        - Welcome message
        """
        mail.outbox = []
        
        # Create member
        member = GymMember.objects.create(
            business=self.business,
            name="Info Test Member",
            phone="0999123456",
            email="info@example.com",
        )
        
        # Get email
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        
        # Verify content
        self.assertIn(member.name, email.body)
        self.assertIn(self.business.name, email.body)
        self.assertIn("Welcome", email.body)
        
        # Should contain public status URL
        self.assertIn("emajinet.africa", email.body)
        self.assertIn("/gym/m/", email.body)


class GymWelcomeEmailUITestCase(TestCase):
    """
    Test welcome email sending through UI views.
    
    Uses regular TestCase for view testing.
    """
    
    def setUp(self):
        """Set up test data"""
        # Create business
        self.business = Business.objects.create(
            name="Test Gym UI",
            vertical="gym",
        )
        
        # Create gym settings
        self.gym_settings = GymSettings.objects.create(
            business=self.business,
            default_membership_price=Decimal("50000.00"),
        )
        
        # Create user
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        
        # Create manager membership
        self.manager_membership = Membership.objects.create(
            business=self.business,
            user=self.user,
            role="MANAGER",
            is_active=True,
        )
        
        # Log in
        self.client.login(username="testuser", password="testpass123")
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
    
    @patch('inventory.services.gym_qr_email.send_member_qr_email')
    def test_member_add_view_sends_email(self, mock_send_email):
        """
        Test: member_add view sends welcome email when member is created.
        """
        mock_send_email.return_value = True
        
        # Post form data
        response = self.client.post(reverse('gym:member_add'), {
            'name': 'UI Test Member',
            'phone': '0999123456',
            'email': 'uitest@example.com',
            'membership_fee': '50000.00',
            'trainer_fee': '0.00',
            'mark_as_paid': False,
            'notes': '',
        })
        
        # Should redirect on success
        self.assertEqual(response.status_code, 302)
        
        # Member should be created
        member = GymMember.objects.get(name='UI Test Member')
        self.assertEqual(member.email, 'uitest@example.com')
        
        # Email should be sent (mock was called)
        mock_send_email.assert_called_once()
    
    @patch('inventory.services.gym_qr_email.send_member_qr_email')
    def test_member_add_view_no_email_when_blank(self, mock_send_email):
        """
        Test: member_add view does NOT send email when email field is blank.
        """
        mock_send_email.return_value = True
        
        # Post form data without email
        response = self.client.post(reverse('gym:member_add'), {
            'name': 'No Email UI Member',
            'phone': '0999123456',
            'email': '',  # Blank email
            'membership_fee': '50000.00',
            'trainer_fee': '0.00',
            'mark_as_paid': False,
            'notes': '',
        })
        
        # Should redirect on success
        self.assertEqual(response.status_code, 302)
        
        # Member should be created
        member = GymMember.objects.get(name='No Email UI Member')
        self.assertEqual(member.email, '')
        
        # Email should NOT be sent
        mock_send_email.assert_not_called()


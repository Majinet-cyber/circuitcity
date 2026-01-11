# cc/tests/test_email_dispatcher.py
"""
Unit and integration tests for email dispatcher SSOT.
"""

from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, TransactionTestCase

from cc.models_email import EmailDeliveryLog
from cc.services.email_dispatcher import EmailEvent, send_event_email

User = get_user_model()


class EmailDeliveryLogModelTests(TestCase):
    """Test EmailDeliveryLog model methods."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_create_email_log(self):
        """Test creating EmailDeliveryLog."""
        log = EmailDeliveryLog.objects.create(
            event=EmailEvent.SALE_OCCURRED,
            to='manager@example.com',
            subject='Sale Completed',
            template_name='sale_instant.html',
            status='pending',
            user=self.user,
            metadata={'sale_id': 123}
        )
        
        assert log.event == EmailEvent.SALE_OCCURRED
        assert log.to == 'manager@example.com'
        assert log.status == 'pending'
        assert log.attempts == 0
        assert log.user == self.user
    
    def test_mark_sent(self):
        """Test marking email as sent."""
        log = EmailDeliveryLog.objects.create(
            event=EmailEvent.USER_SIGNUP,
            to='user@example.com',
            subject='Welcome!',
            status='pending'
        )
        
        log.mark_sent()
        log.refresh_from_db()
        
        assert log.status == 'sent'
        assert log.sent_at is not None
    
    def test_mark_failed(self):
        """Test marking email as failed with error."""
        log = EmailDeliveryLog.objects.create(
            event=EmailEvent.OTP_REQUEST,
            to='user@example.com',
            subject='OTP Code',
            status='pending'
        )
        
        error = 'SMTP connection failed'
        log.mark_failed(error)
        log.refresh_from_db()
        
        assert log.status == 'failed'
        assert log.last_error == error
    
    def test_increment_attempts(self):
        """Test incrementing attempt counter."""
        log = EmailDeliveryLog.objects.create(
            event=EmailEvent.AGENT_COMMISSION,
            to='agent@example.com',
            subject='Commission Earned',
            status='pending'
        )
        
        log.increment_attempts()
        log.refresh_from_db()
        assert log.attempts == 1
        assert log.status == 'pending'  # Still pending on first attempt
        
        log.increment_attempts()
        log.refresh_from_db()
        assert log.attempts == 2
        assert log.status == 'retrying'  # Retrying after 2nd attempt


class EmailDispatcherTests(TransactionTestCase):
    """Test email dispatcher service."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        mail.outbox = []
    
    @patch('cc.services.email_dispatcher._enqueue_email_task')
    def test_send_event_email_creates_log(self, mock_enqueue):
        """Test that send_event_email creates EmailDeliveryLog."""
        context = {
            'sale_id': 123,
            'total': 1000,
            'business_name': 'Test Shop',
        }
        
        log_id = send_event_email(
            EmailEvent.SALE_OCCURRED,
            to='manager@example.com',
            context=context,
            user=self.user
        )
        
        assert log_id is not None
        log = EmailDeliveryLog.objects.get(id=log_id)
        assert log.event == EmailEvent.SALE_OCCURRED
        assert log.to == 'manager@example.com'
        assert log.status == 'pending'
        assert 'Sale Completed' in log.subject
        
        # Check task was enqueued
        mock_enqueue.assert_called_once_with(log_id)
    
    @patch('cc.services.email_dispatcher._enqueue_email_task')
    def test_send_to_multiple_recipients(self, mock_enqueue):
        """Test sending to multiple recipients."""
        context = {'business_name': 'Test Shop'}
        
        log_id = send_event_email(
            EmailEvent.IMPORTANT_ALERT,
            to=['manager1@example.com', 'manager2@example.com'],
            context={'alert_title': 'System Alert', 'business_name': 'Test Shop'},
            force=True
        )
        
        log = EmailDeliveryLog.objects.get(id=log_id)
        assert log.to == 'manager1@example.com'  # Primary recipient
    
    @patch('cc.services.email_dispatcher._enqueue_email_task')
    def test_custom_event_with_template(self, mock_enqueue):
        """Test custom email event with explicit template."""
        context = {
            'subject': 'Custom Email',
            'html_template': 'emails/custom.html',
            'message': 'Custom message'
        }
        
        log_id = send_event_email(
            EmailEvent.CUSTOM,
            to='user@example.com',
            context=context,
            force=True
        )
        
        log = EmailDeliveryLog.objects.get(id=log_id)
        assert log.subject == 'Custom Email'
        assert log.event == EmailEvent.CUSTOM
    
    def test_invalid_event_raises_error(self):
        """Test that invalid event type raises ValueError."""
        with pytest.raises(ValueError, match='Unknown email event'):
            send_event_email(
                'INVALID_EVENT',
                to='user@example.com',
                context={}
            )
    
    def test_no_recipients_raises_error(self):
        """Test that empty recipient list raises ValueError."""
        with pytest.raises(ValueError, match='At least one recipient required'):
            send_event_email(
                EmailEvent.SALE_OCCURRED,
                to=[],
                context={'business_name': 'Test'}
            )


class EmailPreferenceTests(TransactionTestCase):
    """Test user preference checking for emails."""
    
    def setUp(self):
        from notifications.models import NotificationPreference
        
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create preferences with sale emails disabled
        self.prefs = NotificationPreference.objects.create(
            user=self.user,
            sale_emails_enabled=False,
            commission_emails_enabled=True
        )
    
    @patch('cc.services.email_dispatcher._enqueue_email_task')
    def test_respects_user_preferences(self, mock_enqueue):
        """Test that non-transactional emails respect user preferences."""
        context = {'business_name': 'Test Shop', 'total': 1000}
        
        # Sale email should be skipped (preference disabled)
        log_id = send_event_email(
            EmailEvent.SALE_OCCURRED,
            to='test@example.com',
            context=context,
            user=self.user
        )
        
        # Log created but marked as skipped
        log = EmailDeliveryLog.objects.get(id=log_id)
        # Check that email was not enqueued
        mock_enqueue.assert_not_called()
    
    @patch('cc.services.email_dispatcher._enqueue_email_task')
    def test_transactional_emails_bypass_preferences(self, mock_enqueue):
        """Test that transactional emails bypass user preferences."""
        context = {'code': '123456'}
        
        # OTP is transactional, should always send
        log_id = send_event_email(
            EmailEvent.OTP_REQUEST,
            to='test@example.com',
            context=context,
            user=self.user
        )
        
        log = EmailDeliveryLog.objects.get(id=log_id)
        assert log.status == 'pending'
        mock_enqueue.assert_called_once()
    
    @patch('cc.services.email_dispatcher._enqueue_email_task')
    def test_force_flag_bypasses_preferences(self, mock_enqueue):
        """Test that force=True bypasses user preferences."""
        context = {'business_name': 'Test Shop', 'total': 1000}
        
        # Force send even though preference disabled
        log_id = send_event_email(
            EmailEvent.SALE_OCCURRED,
            to='test@example.com',
            context=context,
            user=self.user,
            force=True
        )
        
        log = EmailDeliveryLog.objects.get(id=log_id)
        assert log.status == 'pending'
        mock_enqueue.assert_called_once()


# tests/test_whatsapp.py
"""
Tests for WhatsApp notification functionality.
"""
import pytest
from unittest.mock import patch, Mock
from django.test import TestCase
from django.contrib.auth import get_user_model

from tenants.models import Business
from notifications.models import WhatsAppPreference
from notifications import whatsapp_service

User = get_user_model()


class WhatsAppServiceTests(TestCase):
    """Tests for WhatsApp service functions."""
    
    def test_normalize_phone_number_with_plus(self):
        """Test phone normalization when number already has +."""
        result = whatsapp_service.normalize_phone_number("+265888123456")
        assert result == "+265888123456"
    
    def test_normalize_phone_number_with_leading_zero(self):
        """Test phone normalization with leading 0."""
        with patch('django.conf.settings.WHATSAPP_DEFAULT_COUNTRY_CODE', "+265"):
            result = whatsapp_service.normalize_phone_number("0888123456")
            assert result == "+265888123456"
    
    def test_normalize_phone_number_without_zero(self):
        """Test phone normalization without leading 0."""
        with patch('django.conf.settings.WHATSAPP_DEFAULT_COUNTRY_CODE', "+265"):
            result = whatsapp_service.normalize_phone_number("888123456")
            assert result == "+265888123456"
    
    @patch('notifications.whatsapp_service.requests')
    @patch('notifications.whatsapp_service.is_whatsapp_configured', return_value=True)
    def test_send_whatsapp_message_success(self, mock_is_configured, mock_requests):
        """Test sending WhatsApp message successfully."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_requests.post.return_value = mock_response
        
        with patch('django.conf.settings.WHATSAPP_API_BASE_URL', "https://graph.facebook.com/v21.0/"), \
             patch('django.conf.settings.WHATSAPP_PHONE_NUMBER_ID', "123456"), \
             patch('django.conf.settings.WHATSAPP_ACCESS_TOKEN', "test_token"):
            
            result = whatsapp_service.send_whatsapp_message(
                "+265888123456",
                "Test message"
            )
            
            assert result is True
            mock_requests.post.assert_called_once()
    
    @patch('notifications.whatsapp_service.is_whatsapp_configured', return_value=False)
    def test_send_whatsapp_message_not_configured(self, mock_is_configured):
        """Test sending message when WhatsApp not configured."""
        result = whatsapp_service.send_whatsapp_message(
            "+265888123456",
            "Test message"
        )
        
        assert result is False


class WhatsAppPreferenceTests(TestCase):
    """Tests for WhatsAppPreference model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="test123"
        )
    
    def test_create_preference(self):
        """Test creating WhatsApp preference."""
        pref = WhatsAppPreference.objects.create(
            user=self.user,
            phone_number="+265888123456",
            is_enabled=True,
            receive_sale_alerts=True,
            receive_low_stock_alerts=True
        )
        
        assert pref.phone_number == "+265888123456"
        assert pref.is_enabled
        assert pref.receive_sale_alerts
    
    def test_get_or_default(self):
        """Test get_or_default class method."""
        # No preference exists
        pref = WhatsAppPreference.get_or_default(self.user)
        assert pref.phone_number == ""
        assert not pref.is_enabled
        assert pref.pk is None  # Not saved
        
        # Create preference
        WhatsAppPreference.objects.create(
            user=self.user,
            phone_number="+265888123456",
            is_enabled=True
        )
        
        # Now should return the saved preference
        pref = WhatsAppPreference.get_or_default(self.user)
        assert pref.phone_number == "+265888123456"
        assert pref.is_enabled
        assert pref.pk is not None


class WhatsAppNotificationTests(TestCase):
    """Tests for WhatsApp notification helpers."""
    
    def setUp(self):
        self.business = Business.objects.create(name="Test Biz", slug="test")
        self.user = User.objects.create_user(
            username="manager",
            email="manager@test.com",
            password="test123"
        )
        self.pref = WhatsAppPreference.objects.create(
            user=self.user,
            phone_number="+265888123456",
            is_enabled=True,
            receive_sale_alerts=True,
            receive_profit_milestones=True,
            receive_low_stock_alerts=True
        )
    
    @patch('notifications.whatsapp_service.send_whatsapp_message')
    def test_notify_manager_sale(self, mock_send):
        """Test notifying manager about a sale."""
        mock_send.return_value = True
        
        sale_info = {
            "product_name": "Test Product",
            "quantity": 5,
            "amount": 10000,
            "location_name": "Main Store"
        }
        
        result = whatsapp_service.notify_manager_sale(
            self.user,
            self.business,
            sale_info
        )
        
        assert result is True
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert "Test Product" in call_args[0][1]  # Check message body
    
    @patch('notifications.whatsapp_service.send_whatsapp_message')
    def test_notify_manager_sale_disabled(self, mock_send):
        """Test notification not sent when user has disabled sale alerts."""
        self.pref.receive_sale_alerts = False
        self.pref.save()
        
        sale_info = {"product_name": "Test", "quantity": 1, "amount": 1000}
        
        result = whatsapp_service.notify_manager_sale(
            self.user,
            self.business,
            sale_info
        )
        
        assert result is False
        mock_send.assert_not_called()
    
    @patch('notifications.whatsapp_service.send_whatsapp_message')
    def test_notify_manager_low_stock(self, mock_send):
        """Test notifying manager about low stock."""
        mock_send.return_value = True
        
        result = whatsapp_service.notify_manager_low_stock(
            self.user,
            self.business,
            "Paracetamol",
            5,
            10
        )
        
        assert result is True
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert "Paracetamol" in call_args[0][1]
        assert "5" in call_args[0][1]


@pytest.mark.django_db
class WhatsAppIntegrationTest:
    """Integration test for WhatsApp notifications."""
    
    @patch('notifications.whatsapp_service.send_whatsapp_message')
    def test_sale_triggers_whatsapp(self, mock_send):
        """Test that recording a sale triggers WhatsApp notification."""
        mock_send.return_value = True
        
        # Setup
        business = Business.objects.create(name="Test", slug="test")
        user = User.objects.create_user(username="mgr", password="test")
        
        WhatsAppPreference.objects.create(
            user=user,
            phone_number="+265888123456",
            is_enabled=True,
            receive_sale_alerts=True
        )
        
        # Simulate sale (in real code, this would trigger notification)
        sale_info = {
            "product_name": "Product",
            "quantity": 1,
            "amount": 1000
        }
        
        result = whatsapp_service.notify_manager_sale(user, business, sale_info)
        
        assert result is True
        assert mock_send.call_count == 1


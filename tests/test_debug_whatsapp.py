"""
Tests for the debug WhatsApp test view.

Ensures the debug view is properly restricted to staff users and correctly
handles API calls with proper mocking.
"""
from unittest.mock import patch, Mock
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


class DebugWhatsAppTestViewTests(TestCase):
    """Tests for the /debug/whatsapp-test/ view."""
    
    def setUp(self):
        self.client = Client()
        self.url = reverse("debug:whatsapp_test")
        
        # Create test users
        self.normal_user = User.objects.create_user(
            username="normaluser",
            email="normal@example.com",
            password="testpass123"
        )
        
        self.staff_user = User.objects.create_user(
            username="staffuser",
            email="staff@example.com",
            password="testpass123",
            is_staff=True
        )
        
        self.superuser = User.objects.create_superuser(
            username="superuser",
            email="super@example.com",
            password="testpass123"
        )
    
    def test_non_logged_in_user_redirected_to_login(self):
        """Test that non-logged-in users are redirected to login."""
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.url)
    
    def test_normal_user_gets_403(self):
        """Test that normal (non-staff) logged-in users get 403."""
        self.client.force_login(self.normal_user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 403)
        self.assertIn(b"Access denied", response.content)
    
    def test_staff_user_can_access_get(self):
        """Test that staff users can access the GET view."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"WhatsApp", response.content)
    
    def test_superuser_can_access_get(self):
        """Test that superusers can access the GET view."""
        self.client.force_login(self.superuser)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"WhatsApp", response.content)
    
    @patch("notifications.whatsapp.send_whatsapp_text")
    def test_staff_user_can_post_success(self, mock_send):
        """Test that staff user can POST and send message successfully."""
        # Mock successful API response
        mock_send.return_value = {
            "messaging_product": "whatsapp",
            "contacts": [{"input": "265883596135", "wa_id": "265883596135"}],
            "messages": [{"id": "wamid.test123"}]
        }
        
        self.client.force_login(self.staff_user)
        response = self.client.post(self.url, {
            "to_number": "265883596135"
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"sent successfully", response.content)
        
        # Verify API was called
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        
        # Check arguments
        self.assertEqual(call_args[0][0], "265883596135")
        self.assertIn("Emajinet test", call_args[0][1])
    
    @patch("notifications.whatsapp.send_whatsapp_text")
    def test_staff_user_post_api_error(self, mock_send):
        """Test that API errors are handled correctly."""
        # Mock error - raise WhatsAppError
        from notifications.whatsapp import WhatsAppError
        mock_send.side_effect = WhatsAppError("WhatsApp API error 400: Invalid phone number")
        
        self.client.force_login(self.staff_user)
        response = self.client.post(self.url, {
            "to_number": "invalid_number"
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Error", response.content)
        
        # Verify API was called
        mock_send.assert_called_once()
    
    def test_post_missing_phone_number(self):
        """Test POST with missing phone number shows error."""
        self.client.force_login(self.staff_user)
        response = self.client.post(self.url, {
            "to_number": ""
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"required", response.content.lower())
    
    def test_post_without_env_vars(self):
        """Test POST without environment variables configured."""
        with patch.dict("os.environ", {
            "WHATSAPP_TOKEN": "",
            "WHATSAPP_PHONE_NUMBER_ID": ""
        }):
            self.client.force_login(self.staff_user)
            response = self.client.post(self.url, {
                "to_number": "265883596135"
            })
            
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Error", response.content)
            self.assertIn(b"not configured", response.content.lower())
    
    @patch("notifications.whatsapp.send_whatsapp_text")
    def test_normal_user_cannot_post(self, mock_send):
        """Test that normal users cannot POST even with valid data."""
        # Mock successful API response
        mock_send.return_value = {"success": True}
        
        self.client.force_login(self.normal_user)
        response = self.client.post(self.url, {
            "to_number": "265883596135"
        })
        
        # Should get 403, not proceed to sending
        self.assertEqual(response.status_code, 403)
        mock_send.assert_not_called()


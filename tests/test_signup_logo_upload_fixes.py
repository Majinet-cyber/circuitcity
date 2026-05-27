# tests/test_signup_logo_upload_fixes.py
"""
Tests for signup logo upload defensive handling:
1. Logo upload failures must never crash signup (never 500)
2. Invalid/corrupt files must be handled gracefully
3. Signup continues as if "Skip" was pressed on any error
4. User sees friendly warning message
"""
from io import BytesIO
from unittest.mock import patch, Mock
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.messages import get_messages

from tenants.models import Business

User = get_user_model()


class SignupLogoUploadDefensiveTestCase(TestCase):
    """Test signup logo upload never crashes signup process."""

    def setUp(self):
        """Set up test client and common data."""
        self.client = Client()
        self.signup_url = reverse("accounts:signup_manager")
        
        # Test data for wizard steps
        self.step1_data = {
            "step": "1",
            "action": "next",
            "email": "testmanager@example.com",
            "password": "SecurePass123!@#",
            "password_confirm": "SecurePass123!@#",
        }
        
        self.step2_data = {
            "step": "2",
            "action": "next",
            "business_name": "Test Store",
            "business_kind": "RETAIL",
        }

    def _complete_step1_and_2(self):
        """Helper to complete steps 1 and 2."""
        # Step 1
        response = self.client.get(self.signup_url + "?step=1")
        self.assertEqual(response.status_code, 200)
        
        response = self.client.post(self.signup_url + "?step=1", self.step1_data)
        self.assertIn(response.status_code, [200, 302])  # May redirect or show step 2
        
        # Step 2
        response = self.client.post(self.signup_url + "?step=2", self.step2_data)
        self.assertIn(response.status_code, [200, 302])

    def test_logo_upload_with_invalid_file_does_not_crash(self):
        """Test that uploading an invalid file does not cause 500 error."""
        self._complete_step1_and_2()
        
        # Create an invalid "image" file (just text)
        invalid_file = SimpleUploadedFile(
            "test.jpg",
            b"This is not a valid image file",
            content_type="image/jpeg"
        )
        
        step3_data = {
            "step": "3",
            "action": "next",
            "logo": invalid_file,
        }
        
        response = self.client.post(
            self.signup_url + "?step=3",
            step3_data,
            format="multipart"
        )
        
        # Should NOT return 500
        self.assertNotEqual(response.status_code, 500, "Should not crash on invalid file")
        
        # Should redirect to step 4 (continuing signup)
        self.assertIn(response.status_code, [200, 302])
        
        if response.status_code == 302:
            self.assertIn("step=4", response.url)
        
        # Check for warning message
        messages = list(get_messages(response.wsgi_request))
        message_texts = [str(m) for m in messages]
        self.assertTrue(
            any("Logo upload is not available" in msg or "continuing without a logo" in msg.lower() 
                for msg in message_texts),
            "Should show user-friendly warning message"
        )

    def test_logo_upload_with_oversized_file_does_not_crash(self):
        """Test that uploading a file >5MB does not crash."""
        self._complete_step1_and_2()
        
        # Create a file larger than 5MB
        large_data = b"x" * (6 * 1024 * 1024)  # 6MB
        large_file = SimpleUploadedFile(
            "large.jpg",
            large_data,
            content_type="image/jpeg"
        )
        
        step3_data = {
            "step": "3",
            "action": "next",
            "logo": large_file,
        }
        
        response = self.client.post(
            self.signup_url + "?step=3",
            step3_data,
            format="multipart"
        )
        
        # Should NOT return 500
        self.assertNotEqual(response.status_code, 500, "Should not crash on oversized file")
        
        # Should continue to step 4
        self.assertIn(response.status_code, [200, 302])

    def test_logo_upload_with_corrupt_image_does_not_crash(self):
        """Test that a corrupt image file does not crash."""
        self._complete_step1_and_2()
        
        # Create a corrupt image (invalid header)
        corrupt_file = SimpleUploadedFile(
            "corrupt.png",
            b"\x89PNG\r\n\x1a\n" + b"CORRUPT DATA",
            content_type="image/png"
        )
        
        step3_data = {
            "step": "3",
            "action": "next",
            "logo": corrupt_file,
        }
        
        response = self.client.post(
            self.signup_url + "?step=3",
            step3_data,
            format="multipart"
        )
        
        # Should NOT return 500
        self.assertNotEqual(response.status_code, 500, "Should not crash on corrupt image")
        
        # Should continue (either show step 4 or redirect)
        self.assertIn(response.status_code, [200, 302])

    @patch("circuitcity.accounts.forms.process_avatar")
    def test_logo_processing_exception_handled_gracefully(self, mock_process):
        """Test that exceptions during image processing are caught."""
        self._complete_step1_and_2()
        
        # Make process_avatar raise an exception
        mock_process.side_effect = Exception("Image processing failed")
        
        # Create a valid-looking file
        valid_file = SimpleUploadedFile(
            "test.jpg",
            b"\xFF\xD8\xFF\xE0" + b"\x00" * 100,  # Minimal JPEG header
            content_type="image/jpeg"
        )
        
        step3_data = {
            "step": "3",
            "action": "next",
            "logo": valid_file,
        }
        
        response = self.client.post(
            self.signup_url + "?step=3",
            step3_data,
            format="multipart"
        )
        
        # Should NOT return 500
        self.assertNotEqual(response.status_code, 500, "Should not crash on processing error")
        
        # Should continue to step 4
        self.assertIn(response.status_code, [200, 302])
        
        # Check for warning message
        messages = list(get_messages(response.wsgi_request))
        message_texts = [str(m) for m in messages]
        self.assertTrue(
            any("Logo upload is not available" in msg for msg in message_texts),
            "Should show warning message on processing error"
        )

    def test_logo_skip_behavior_preserved(self):
        """Test that skipping logo (no file uploaded) still works."""
        self._complete_step1_and_2()
        
        step3_data = {
            "step": "3",
            "action": "next",
            # No logo file
        }
        
        response = self.client.post(self.signup_url + "?step=3", step3_data)
        
        # Should succeed and proceed
        self.assertIn(response.status_code, [200, 302])
        
        if response.status_code == 302:
            self.assertIn("step=4", response.url)

    @patch("circuitcity.accounts.views.log")
    def test_unexpected_error_logged_and_handled(self, mock_log):
        """Test that unexpected errors are logged and handled gracefully."""
        self._complete_step1_and_2()
        
        # Patch base64.b64encode to raise unexpected error
        with patch("base64.b64encode", side_effect=RuntimeError("Unexpected error")):
            test_file = SimpleUploadedFile(
                "test.jpg",
                b"fake image data",
                content_type="image/jpeg"
            )
            
            step3_data = {
                "step": "3",
                "action": "next",
                "logo": test_file,
            }
            
            response = self.client.post(
                self.signup_url + "?step=3",
                step3_data,
                format="multipart"
            )
            
            # Should NOT crash
            self.assertNotEqual(response.status_code, 500)
            
            # Should continue to next step
            self.assertIn(response.status_code, [200, 302])
            
            # Should log the error
            self.assertTrue(
                mock_log.error.called or mock_log.warning.called,
                "Error should be logged"
            )

    def test_logo_not_saved_on_error(self):
        """Test that logo is not saved to business when upload fails."""
        self._complete_step1_and_2()
        
        # Create invalid file
        invalid_file = SimpleUploadedFile(
            "test.jpg",
            b"Not an image",
            content_type="image/jpeg"
        )
        
        step3_data = {
            "step": "3",
            "action": "next",
            "logo": invalid_file,
        }
        
        response = self.client.post(
            self.signup_url + "?step=3",
            step3_data,
            format="multipart"
        )
        
        # Continue to step 4 and complete signup
        step4_data = {
            "step": "4",
            "action": "finish",
            "agree_terms": "on",
        }
        
        response = self.client.post(self.signup_url + "?step=4", step4_data)
        
        # Check that business was created but has no logo
        if User.objects.filter(email=self.step1_data["email"]).exists():
            user = User.objects.get(email=self.step1_data["email"])
            memberships = user.memberships.all()
            
            if memberships.exists():
                business = memberships.first().business
                # Logo should not be saved
                if hasattr(business, "logo"):
                    self.assertFalse(business.logo, "Logo should not be saved on upload error")

    def test_valid_logo_upload_still_works(self):
        """Test that valid logo uploads still work (regression test)."""
        self._complete_step1_and_2()
        
        # Create a minimal valid PNG (1x1 pixel)
        # PNG signature + IHDR + IEND
        valid_png = (
            b"\x89PNG\r\n\x1a\n"  # PNG signature
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde"  # IHDR chunk
            b"\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"  # IDAT
            b"\x00\x00\x00\x00IEND\xaeB`\x82"  # IEND
        )
        
        valid_file = SimpleUploadedFile(
            "valid.png",
            valid_png,
            content_type="image/png"
        )
        
        step3_data = {
            "step": "3",
            "action": "next",
            "logo": valid_file,
        }
        
        response = self.client.post(
            self.signup_url + "?step=3",
            step3_data,
            format="multipart"
        )
        
        # Should succeed
        self.assertNotEqual(response.status_code, 500)
        self.assertIn(response.status_code, [200, 302])
        
        # Should NOT show error message if validation passes
        messages = list(get_messages(response.wsgi_request))
        message_texts = [str(m) for m in messages]
        # Should either have no messages or success-type messages, not error about logo
        if message_texts:
            self.assertFalse(
                any("Logo upload is not available" in msg for msg in message_texts),
                "Should not show error message for valid uploads"
            )


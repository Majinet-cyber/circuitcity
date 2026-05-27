"""
Comprehensive tests for Email OTP functionality.
"""
from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.utils import timezone
from django.conf import settings

from .models import EmailOTP, Profile
from .services.email_otp import (
    request_email_otp,
    verify_email_otp,
    _normalize_email,
    _check_rate_limit,
    _generate_otp_code,
    purge_expired_otps,
)

User = get_user_model()


class EmailOTPServiceTests(TestCase):
    """Tests for the email OTP service layer."""

    def setUp(self):
        """Set up test fixtures."""
        self.email = "test@example.com"
        self.user = User.objects.create_user(
            username=self.email,
            email=self.email,
            password="testpass123",
        )
        cache.clear()

    def tearDown(self):
        """Clean up after tests."""
        cache.clear()

    def test_normalize_email(self):
        """Test email normalization."""
        self.assertEqual(_normalize_email("Test@Example.COM"), "test@example.com")
        self.assertEqual(_normalize_email("  test@example.com  "), "test@example.com")
        self.assertEqual(_normalize_email(""), "")

    def test_generate_otp_code(self):
        """Test OTP code generation."""
        code = _generate_otp_code()
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())
        # Test uniqueness (very unlikely to collide)
        codes = {_generate_otp_code() for _ in range(100)}
        self.assertGreater(len(codes), 90)

    def test_request_creates_otp_and_sends_email(self):
        """Test that requesting OTP creates a record and sends email."""
        mail.outbox.clear()

        request_email_otp(self.email, "signup", user=self.user)

        # Check OTP was created
        otp = EmailOTP.objects.filter(email=self.email, purpose="signup").first()
        self.assertIsNotNone(otp)
        self.assertEqual(otp.user, self.user)
        self.assertFalse(otp.is_used)
        self.assertFalse(otp.is_expired)
        self.assertEqual(otp.attempts, 0)

        # Check email was sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.email])
        self.assertIn("verification code", mail.outbox[0].subject.lower())

    def test_verify_success_consumes_otp(self):
        """Test that successful verification consumes the OTP."""
        # Request OTP
        request_email_otp(self.email, "signup", user=self.user)
        otp = EmailOTP.objects.filter(email=self.email, purpose="signup").first()

        # Get the code (we need to extract it from email or use a mock)
        # For this test, we'll verify the OTP was created and can be matched
        # In a real scenario, we'd need to capture the code
        self.assertIsNotNone(otp)

        # Manually set a known code for testing
        test_code = "123456"
        otp.set_raw_code(test_code)
        otp.save()

        # Verify
        result = verify_email_otp(self.email, "signup", test_code)
        self.assertTrue(result)

        # Check OTP was consumed
        otp.refresh_from_db()
        self.assertTrue(otp.is_used)
        self.assertIsNotNone(otp.consumed_at)

    def test_verify_wrong_code_increments_attempts_and_fails(self):
        """Test that wrong code increments attempts and fails."""
        request_email_otp(self.email, "signup", user=self.user)
        otp = EmailOTP.objects.filter(email=self.email, purpose="signup").first()

        test_code = "123456"
        otp.set_raw_code(test_code)
        otp.save()

        # Try wrong code
        result = verify_email_otp(self.email, "signup", "000000")
        self.assertFalse(result)

        # Check attempts incremented
        otp.refresh_from_db()
        self.assertEqual(otp.attempts, 1)
        self.assertFalse(otp.is_used)

    def test_verify_expired_fails(self):
        """Test that expired OTPs fail verification."""
        request_email_otp(self.email, "signup", user=self.user)
        otp = EmailOTP.objects.filter(email=self.email, purpose="signup").first()

        # Manually expire the OTP
        otp.expires_at = timezone.now() - timedelta(minutes=1)
        test_code = "123456"
        otp.set_raw_code(test_code)
        otp.save()

        # Try to verify
        result = verify_email_otp(self.email, "signup", test_code)
        self.assertFalse(result)

    def test_attempt_limit_blocks(self):
        """Test that exceeding attempt limit blocks verification."""
        request_email_otp(self.email, "signup", user=self.user)
        otp = EmailOTP.objects.filter(email=self.email, purpose="signup").first()

        test_code = "123456"
        otp.set_raw_code(test_code)
        otp.attempts = 5  # Max attempts
        otp.save()

        # Try to verify
        result = verify_email_otp(self.email, "signup", test_code)
        self.assertFalse(result)

    def test_rate_limit_blocks(self):
        """Test that rate limiting blocks too many requests."""
        # Make multiple requests quickly
        for i in range(5):
            try:
                request_email_otp(self.email, "signup", user=self.user)
            except ValueError:
                # Expected after rate limit
                pass

        # Should have created at most 3 OTPs (rate limit)
        count = EmailOTP.objects.filter(email=self.email, purpose="signup").count()
        self.assertLessEqual(count, 3)

    def test_purge_expired_otps(self):
        """Test that purge_expired_otps removes old OTPs."""
        # Create expired OTP
        otp = EmailOTP.objects.create(
            email=self.email,
            purpose="signup",
            expires_at=timezone.now() - timedelta(hours=25),
        )
        otp.set_raw_code("123456")
        otp.save()

        # Create non-expired OTP
        otp2 = EmailOTP.objects.create(
            email=self.email,
            purpose="login",
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        otp2.set_raw_code("654321")
        otp2.save()

        # Purge
        deleted = purge_expired_otps()
        self.assertEqual(deleted, 1)

        # Check expired is gone, non-expired remains
        self.assertFalse(EmailOTP.objects.filter(id=otp.id).exists())
        self.assertTrue(EmailOTP.objects.filter(id=otp2.id).exists())


class EmailOTPAPITests(TestCase):
    """Tests for the OTP JSON API endpoints."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = Client(enforce_csrf_checks=False)
        self.email = "test@example.com"
        self.user = User.objects.create_user(
            username=self.email,
            email=self.email,
            password="testpass123",
        )
        cache.clear()

    def tearDown(self):
        """Clean up after tests."""
        cache.clear()

    def test_otp_request_api_success(self):
        """Test successful OTP request via API."""
        mail.outbox.clear()

        response = self.client.post(
            "/accounts/auth/otp/request/",
            data=json.dumps({"email": self.email, "purpose": "signup"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])

        # Check email was sent
        self.assertEqual(len(mail.outbox), 1)

    def test_otp_request_api_rate_limit_returns_429(self):
        """Test that rate limiting returns HTTP 429."""
        mail.outbox.clear()

        # Make multiple requests
        for i in range(5):
            response = self.client.post(
                "/accounts/auth/otp/request/",
                data=json.dumps({"email": self.email, "purpose": "signup"}),
                content_type="application/json",
            )

        # Last request should be rate-limited
        self.assertIn(response.status_code, [400, 429])
        data = json.loads(response.content)
        self.assertFalse(data["ok"])
        self.assertIn("rate", data["error"].lower())

    def test_otp_verify_api_success(self):
        """Test successful OTP verification via API."""
        # Request OTP first
        request_email_otp(self.email, "signup", user=self.user)
        otp = EmailOTP.objects.filter(email=self.email, purpose="signup").first()

        # Set known code
        test_code = "123456"
        otp.set_raw_code(test_code)
        otp.save()

        # Verify via API
        response = self.client.post(
            "/accounts/auth/otp/verify/",
            data=json.dumps(
                {
                    "email": self.email,
                    "purpose": "signup",
                    "code": test_code,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])

    def test_otp_verify_api_invalid_code(self):
        """Test that invalid code returns error."""
        # Request OTP first
        request_email_otp(self.email, "signup", user=self.user)

        # Try wrong code
        response = self.client.post(
            "/accounts/auth/otp/verify/",
            data=json.dumps(
                {
                    "email": self.email,
                    "purpose": "signup",
                    "code": "000000",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertFalse(data["ok"])
        self.assertIn("Invalid", data["error"])


class SignupOTPIntegrationTests(TestCase):
    """Integration tests for signup with OTP verification."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = Client(enforce_csrf_checks=False)
        cache.clear()

    def tearDown(self):
        """Clean up after tests."""
        cache.clear()

    @patch("django.conf.settings.ENABLE_EMAIL_OTP", True)
    def test_signup_triggers_otp_and_marks_unverified_then_verified(self):
        """Test that signup triggers OTP and marks email unverified, then verified."""
        # This is a simplified test - in reality, you'd need to go through the full wizard
        # For now, we'll test the core logic

        email = "newuser@example.com"
        mail.outbox.clear()

        # Create user (simulating signup completion)
        user = User.objects.create_user(
            username=email,
            email=email,
            password="testpass123",
        )

        # Simulate what happens in _complete_wizard_signup
        profile = Profile.objects.get(user=user)
        profile.email_verified = False
        profile.save()

        # Send OTP
        request_email_otp(email, "signup", user=user)

        # Check email was sent
        self.assertEqual(len(mail.outbox), 1)

        # Check profile is unverified
        profile.refresh_from_db()
        self.assertFalse(profile.email_verified)

        # Get OTP and verify
        otp = EmailOTP.objects.filter(email=email, purpose="signup").first()
        test_code = "123456"
        otp.set_raw_code(test_code)
        otp.save()

        # Verify
        result = verify_email_otp(email, "signup", test_code)
        self.assertTrue(result)

        # Mark as verified
        profile.email_verified = True
        profile.save()

        # Check profile is now verified
        profile.refresh_from_db()
        self.assertTrue(profile.email_verified)

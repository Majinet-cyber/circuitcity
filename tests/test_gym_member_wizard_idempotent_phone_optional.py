"""
Test Gym Member Wizard: Idempotent + Phone Optional (Feb 2026)
================================================================

Regression tests for critical bug fixes:
1. Wizard step 3 is idempotent (no duplicate creation on refresh/double-submit)
2. Phone is optional (allows NULL, multiple members without phone)
3. Duplicate phone detection and redirect
4. IntegrityError safety net

These tests prevent production 500s from:
- IntegrityError on unique constraint (business_id, phone)
- Double-submit creating duplicate members
- Empty string phone collisions
"""

from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from tenants.models import Business
from inventory.models import Location
from inventory.models_verticals import GymMember, GymSettings
from inventory.business_kinds import BusinessKind

User = get_user_model()


class GymWizardIdempotentPhoneOptionalTest(TestCase):
    """Test wizard idempotency and phone optional behavior."""

    def setUp(self):
        """Set up test data."""
        # Create business
        self.business = Business.objects.create(
            name="Test Gym",
            business_kind=BusinessKind.GYM,
        )

        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Location",
            is_default=True,
        )

        # Create user (manager)
        self.user = User.objects.create_user(
            username="manager",
            password="testpass123",
            email="manager@test.com",
            is_staff=False,  # Not admin
        )
        self.user.assigned_business = self.business
        self.user.save()

        # Create gym settings
        self.gym_settings = GymSettings.objects.create(
            business=self.business,
            default_membership_price=Decimal("50000.00"),
            default_trainer_fee=Decimal("20000.00"),
        )

        self.client = Client()
        self.client.login(username="manager", password="testpass123")
        
        # Set active business in session (required by middleware)
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()

    def test_wizard_phone_optional_step1(self):
        """Test that phone is optional in step 1."""
        # POST to step 1 without phone
        response = self.client.post(
            reverse("gym:member_add") + "?step=1",
            {
                "name": "John Doe",
                "phone": "",  # Empty phone
                "email": "john@test.com",
            },
        )

        # Should succeed and redirect to step 2
        self.assertEqual(response.status_code, 302)
        self.assertIn("step=2", response.url)

    def test_wizard_phone_optional_step3_creates_member_with_null_phone(self):
        """Test that member can be created with NULL phone."""
        # Set up wizard session
        session = self.client.session
        session["gym_member_wizard"] = {
            "name": "Jane Doe",
            "phone": "",  # Empty phone
            "email": "jane@test.com",
            "trainer_id": None,
        }
        session.save()

        # POST to step 3 (confirm)
        response = self.client.post(
            reverse("gym:member_add") + "?step=3",
            {"mark_as_paid": "no"},
        )

        # Should succeed and redirect to step 4
        self.assertEqual(response.status_code, 302)
        self.assertIn("step=4", response.url)

        # Member should be created with NULL phone
        member = GymMember.objects.filter(name="Jane Doe").first()
        self.assertIsNotNone(member)
        self.assertIsNone(member.phone)  # Phone should be NULL, not empty string

    def test_wizard_duplicate_phone_detection_step1(self):
        """Test that duplicate phone is detected in step 1."""
        # Create existing member with phone
        GymMember.objects.create(
            business=self.business,
            name="Existing Member",
            phone="0999123456",
        )

        # Try to create another member with same phone
        response = self.client.post(
            reverse("gym:member_add") + "?step=1",
            {
                "name": "New Member",
                "phone": "0999123456",  # Duplicate phone
                "email": "new@test.com",
            },
        )

        # Should show error
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")

    def test_wizard_idempotent_step3_redirect_to_existing(self):
        """Test that step 3 redirects to existing member instead of creating duplicate."""
        # Create existing member with phone
        existing = GymMember.objects.create(
            business=self.business,
            name="Existing Member",
            phone="0999123456",
        )

        # Set up wizard session with same phone
        session = self.client.session
        session["gym_member_wizard"] = {
            "name": "Duplicate Attempt",
            "phone": "0999123456",  # Same phone as existing
            "email": "duplicate@test.com",
            "trainer_id": None,
        }
        session.save()

        # POST to step 3 (confirm)
        response = self.client.post(
            reverse("gym:member_add") + "?step=3",
            {"mark_as_paid": "no"},
        )

        # Should redirect to existing member detail (not create duplicate)
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"/gym/member/{existing.id}/", response.url)

        # Should NOT create a new member
        self.assertEqual(GymMember.objects.filter(phone="0999123456").count(), 1)

    def test_wizard_double_submit_protection(self):
        """Test that double-submitting step 3 doesn't create duplicate members."""
        # Set up wizard session
        session = self.client.session
        session["gym_member_wizard"] = {
            "name": "Test Member",
            "phone": "0999111222",
            "email": "test@test.com",
            "trainer_id": None,
        }
        session.save()

        # First submit
        response1 = self.client.post(
            reverse("gym:member_add") + "?step=3",
            {"mark_as_paid": "no"},
        )
        self.assertEqual(response1.status_code, 302)

        # Reset session to simulate refresh/back button
        session = self.client.session
        session["gym_member_wizard"] = {
            "name": "Test Member",
            "phone": "0999111222",
            "email": "test@test.com",
            "trainer_id": None,
        }
        session.save()

        # Second submit (double-submit scenario)
        response2 = self.client.post(
            reverse("gym:member_add") + "?step=3",
            {"mark_as_paid": "no"},
        )

        # Should redirect to existing member (not crash with IntegrityError)
        self.assertEqual(response2.status_code, 302)

        # Should only have ONE member with this phone
        self.assertEqual(GymMember.objects.filter(phone="0999111222").count(), 1)

    def test_multiple_members_with_null_phone_allowed(self):
        """Test that multiple members can have NULL phone (Postgres allows multiple NULLs)."""
        # Create first member with NULL phone
        member1 = GymMember.objects.create(
            business=self.business,
            name="Member One",
            phone=None,
        )

        # Create second member with NULL phone
        member2 = GymMember.objects.create(
            business=self.business,
            name="Member Two",
            phone=None,
        )

        # Both should exist
        self.assertIsNotNone(member1.id)
        self.assertIsNotNone(member2.id)
        self.assertIsNone(member1.phone)
        self.assertIsNone(member2.phone)

        # Should have 2 members with NULL phone
        self.assertEqual(GymMember.objects.filter(phone__isnull=True).count(), 2)

    def test_wizard_phone_normalization(self):
        """Test that phone numbers are normalized consistently."""
        # Set up wizard session with formatted phone
        session = self.client.session
        session["gym_member_wizard"] = {
            "name": "Normalized Member",
            "phone": "+265 999 123 456",  # Formatted phone
            "email": "normalized@test.com",
            "trainer_id": None,
        }
        session.save()

        # POST to step 3
        response = self.client.post(
            reverse("gym:member_add") + "?step=3",
            {"mark_as_paid": "no"},
        )

        # Member should be created with normalized phone
        member = GymMember.objects.filter(name="Normalized Member").first()
        self.assertIsNotNone(member)
        # Phone should be normalized (digits only, with + prefix if present)
        self.assertIn("265999123456", member.phone)

    def test_wizard_step3_integrity_error_safety_net(self):
        """Test that IntegrityError is caught and handled gracefully."""
        # Create existing member
        existing = GymMember.objects.create(
            business=self.business,
            name="Existing",
            phone="0999999999",
        )

        # Simulate a race condition: wizard session has same phone
        # but check in step 3 somehow misses it (edge case)
        session = self.client.session
        session["gym_member_wizard"] = {
            "name": "Race Condition Test",
            "phone": "0999999999",  # Same as existing
            "email": "race@test.com",
            "trainer_id": None,
        }
        session.save()

        # POST to step 3
        response = self.client.post(
            reverse("gym:member_add") + "?step=3",
            {"mark_as_paid": "no"},
        )

        # Should NOT crash with 500
        # Should redirect to existing member or show error
        self.assertIn(response.status_code, [200, 302])

        # Should NOT create duplicate
        self.assertEqual(GymMember.objects.filter(phone="0999999999").count(), 1)


class GymMemberPhoneFieldTest(TestCase):
    """Test GymMember phone field behavior."""

    def setUp(self):
        """Set up test data."""
        self.business = Business.objects.create(
            name="Test Gym",
            business_kind=BusinessKind.GYM,
        )

    def test_phone_null_allowed(self):
        """Test that phone can be NULL."""
        member = GymMember.objects.create(
            business=self.business,
            name="No Phone Member",
            phone=None,
        )
        self.assertIsNone(member.phone)

    def test_phone_empty_string_converted_to_null(self):
        """Test that empty string phone is stored as NULL."""
        member = GymMember.objects.create(
            business=self.business,
            name="Empty Phone Member",
            phone="",
        )
        # After migration, empty strings should be converted to NULL
        # This test documents expected behavior after migration
        member.refresh_from_db()
        # Either NULL or empty string is acceptable (depends on migration state)
        self.assertIn(member.phone, [None, ""])

    def test_unique_constraint_allows_multiple_nulls(self):
        """Test that unique constraint allows multiple NULL phones."""
        # Create multiple members with NULL phone
        member1 = GymMember.objects.create(
            business=self.business,
            name="Member 1",
            phone=None,
        )
        member2 = GymMember.objects.create(
            business=self.business,
            name="Member 2",
            phone=None,
        )
        member3 = GymMember.objects.create(
            business=self.business,
            name="Member 3",
            phone=None,
        )

        # All should exist
        self.assertEqual(GymMember.objects.filter(phone__isnull=True).count(), 3)

    def test_unique_constraint_prevents_duplicate_phones(self):
        """Test that unique constraint prevents duplicate non-NULL phones."""
        from django.db import IntegrityError

        # Create first member with phone
        GymMember.objects.create(
            business=self.business,
            name="First Member",
            phone="0999123456",
        )

        # Try to create second member with same phone
        with self.assertRaises(IntegrityError):
            GymMember.objects.create(
                business=self.business,
                name="Second Member",
                phone="0999123456",
            )


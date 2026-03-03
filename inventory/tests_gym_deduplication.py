"""
Tests for gym member deduplication, merge, and bulk operations.

Tests cover:
1. Duplicate prevention (canonical name normalization + unique constraint)
2. Merge operation (history preservation)
3. Bulk create (validation, duplicate detection)
4. Auto-dedupe migration
"""
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from inventory.models_verticals import (
    GymMember,
    GymPayment,
    GymCheckIn,
    GymMemberLog,
    GymTrainer,
    normalize_member_name,
)
from inventory.services.gym_member_operations import (
    merge_members,
    find_duplicate_members,
    choose_canonical_member,
    dedupe_members,
    bulk_create_members,
)
from tenants.models import Business

User = get_user_model()


class NormalizationTests(TestCase):
    """Test name normalization function"""

    def test_normalize_strips_whitespace(self):
        """Strip leading/trailing whitespace"""
        self.assertEqual(normalize_member_name("  John Doe  "), "john doe")

    def test_normalize_collapses_internal_whitespace(self):
        """Collapse multiple spaces to single space"""
        self.assertEqual(normalize_member_name("John    Doe"), "john doe")
        self.assertEqual(normalize_member_name("John\t\tDoe"), "john doe")

    def test_normalize_casefolding(self):
        """Convert to lowercase (casefold)"""
        self.assertEqual(normalize_member_name("JOHN DOE"), "john doe")
        self.assertEqual(normalize_member_name("John Doe"), "john doe")
        self.assertEqual(normalize_member_name("jOhN dOe"), "john doe")

    def test_normalize_combined(self):
        """Test combination of all normalization rules"""
        self.assertEqual(normalize_member_name("  LYDIA  MAJAWA  "), "lydia majawa")
        self.assertEqual(normalize_member_name("Lydia Majawa"), "lydia majawa")
        self.assertEqual(normalize_member_name("lydia  majawa"), "lydia majawa")

    def test_normalize_empty_string(self):
        """Handle empty strings gracefully"""
        self.assertEqual(normalize_member_name(""), "")
        self.assertEqual(normalize_member_name("   "), "")


class DuplicatePreventionTests(TransactionTestCase):
    """Test duplicate prevention at model/DB level"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.business = Business.objects.create(name="Test Gym", kind="gym")

    def test_create_member_auto_populates_canonical(self):
        """Member.save() should auto-populate name_canonical"""
        member = GymMember.objects.create(
            business=self.business,
            name="Lydia Majawa",
            phone="0999123456",
        )
        self.assertEqual(member.name_canonical, "lydia majawa")

    def test_duplicate_name_blocked_case_insensitive(self):
        """Cannot create duplicate with different casing"""
        GymMember.objects.create(
            business=self.business,
            name="Lydia Majawa",
            phone="0999123456",
        )

        with self.assertRaises(IntegrityError):
            GymMember.objects.create(
                business=self.business,
                name="lydia majawa",  # lowercase
                phone="0888765432",
            )

    def test_duplicate_name_blocked_extra_spaces(self):
        """Cannot create duplicate with extra spaces"""
        GymMember.objects.create(
            business=self.business,
            name="Lydia Majawa",
            phone="0999123456",
        )

        with self.assertRaises(IntegrityError):
            GymMember.objects.create(
                business=self.business,
                name="Lydia  Majawa",  # double space
                phone="0888765432",
            )

    def test_same_name_different_business_allowed(self):
        """Same name in different businesses is allowed"""
        business2 = Business.objects.create(name="Test Gym 2", kind="gym")

        member1 = GymMember.objects.create(
            business=self.business,
            name="Lydia Majawa",
            phone="0999123456",
        )

        member2 = GymMember.objects.create(
            business=business2,
            name="Lydia Majawa",
            phone="0888765432",
        )

        self.assertEqual(member1.name_canonical, member2.name_canonical)
        self.assertNotEqual(member1.business, member2.business)

    def test_deleted_member_does_not_block_new_member(self):
        """Soft-deleted members don't block creating new member with same name"""
        member1 = GymMember.objects.create(
            business=self.business,
            name="Lydia Majawa",
            phone="0999123456",
        )

        # Soft delete
        member1.is_deleted = True
        member1.deleted_at = timezone.now()
        member1.save()

        # Should be able to create new member with same name
        member2 = GymMember.objects.create(
            business=self.business,
            name="Lydia Majawa",
            phone="0888765432",
        )

        self.assertEqual(member2.name_canonical, "lydia majawa")
        self.assertNotEqual(member1.id, member2.id)


class MergeOperationTests(TransactionTestCase):
    """Test member merge operation"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.business = Business.objects.create(name="Test Gym", kind="gym")

    def test_merge_moves_payments(self):
        """Payments are moved from source to target"""
        source = GymMember.objects.create(
            business=self.business,
            name="Lydia A",
            phone="0999123456",
        )
        target = GymMember.objects.create(
            business=self.business,
            name="Lydia B",
            phone="0888765432",
        )

        # Create payments for source
        GymPayment.objects.create(
            member=source,
            membership_amount=Decimal("55000"),
            trainer_fee=Decimal("0"),
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
            paid_by=self.user,
        )
        GymPayment.objects.create(
            member=source,
            membership_amount=Decimal("55000"),
            trainer_fee=Decimal("0"),
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
            paid_by=self.user,
        )

        # Merge
        stats = merge_members(source, target, self.user, "duplicate", "")

        # Verify
        self.assertEqual(stats["payments_moved"], 2)
        self.assertEqual(GymPayment.objects.filter(member=target).count(), 2)
        self.assertEqual(GymPayment.objects.filter(member=source).count(), 0)

    def test_merge_moves_checkins_with_duplicate_handling(self):
        """Check-ins are moved, duplicates on same day are resolved"""
        source = GymMember.objects.create(
            business=self.business,
            name="Lydia A",
            phone="0999123456",
        )
        target = GymMember.objects.create(
            business=self.business,
            name="Lydia B",
            phone="0888765432",
        )

        today = timezone.now().date()
        yesterday = today - timezone.timedelta(days=1)

        # Source has check-in today and yesterday
        GymCheckIn.objects.create(
            business=self.business,
            member=source,
            timestamp=timezone.now().replace(hour=10, minute=0),
        )
        GymCheckIn.objects.create(
            business=self.business,
            member=source,
            timestamp=timezone.now().replace(hour=10, minute=0) - timezone.timedelta(days=1),
        )

        # Target already has check-in today (earlier)
        GymCheckIn.objects.create(
            business=self.business,
            member=target,
            timestamp=timezone.now().replace(hour=9, minute=0),
        )

        # Merge
        stats = merge_members(source, target, self.user, "duplicate", "")

        # Verify: yesterday's check-in moved, today's duplicate handled
        target_checkins = GymCheckIn.objects.filter(member=target).order_by("-timestamp")
        self.assertEqual(target_checkins.count(), 2)  # One from today (earliest), one from yesterday

    def test_merge_soft_deletes_source(self):
        """Source member is soft-deleted after merge"""
        source = GymMember.objects.create(
            business=self.business,
            name="Lydia A",
            phone="0999123456",
        )
        target = GymMember.objects.create(
            business=self.business,
            name="Lydia B",
            phone="0888765432",
        )

        merge_members(source, target, self.user, "duplicate", "test merge")

        source.refresh_from_db()
        self.assertTrue(source.is_deleted)
        self.assertIsNotNone(source.deleted_at)
        self.assertEqual(source.deleted_by, self.user)
        self.assertEqual(source.delete_reason, "duplicate")
        self.assertEqual(source.delete_notes, "test merge")
        self.assertEqual(source.merged_into, target)

    def test_merge_creates_audit_log(self):
        """Merge operation creates audit log"""
        source = GymMember.objects.create(
            business=self.business,
            name="Lydia A",
            phone="0999123456",
        )
        target = GymMember.objects.create(
            business=self.business,
            name="Lydia B",
            phone="0888765432",
        )

        merge_members(source, target, self.user, "duplicate", "test merge")

        # Check audit log was created
        logs = GymMemberLog.objects.filter(member=target, performed_by=self.user)
        self.assertTrue(logs.exists())

        log = logs.first()
        self.assertEqual(log.changes["action"], "merged_from")
        self.assertEqual(log.changes["source_member_id"], source.id)

    def test_merge_prevents_self_merge(self):
        """Cannot merge a member into itself"""
        member = GymMember.objects.create(
            business=self.business,
            name="Lydia",
            phone="0999123456",
        )

        with self.assertRaises(ValueError):
            merge_members(member, member, self.user, "duplicate", "")

    def test_merge_prevents_cross_business_merge(self):
        """Cannot merge members from different businesses"""
        business2 = Business.objects.create(name="Test Gym 2", kind="gym")

        source = GymMember.objects.create(
            business=self.business,
            name="Lydia A",
            phone="0999123456",
        )
        target = GymMember.objects.create(
            business=business2,
            name="Lydia B",
            phone="0888765432",
        )

        with self.assertRaises(ValueError):
            merge_members(source, target, self.user, "duplicate", "")

    def test_merge_combines_gamification_stats(self):
        """Merge combines gamification stats (streaks, badges)"""
        source = GymMember.objects.create(
            business=self.business,
            name="Lydia A",
            phone="0999123456",
            streak_days=10,
            total_checkins=50,
            badge_level="gold",
        )
        target = GymMember.objects.create(
            business=self.business,
            name="Lydia B",
            phone="0888765432",
            streak_days=5,
            total_checkins=30,
            badge_level="silver",
        )

        merge_members(source, target, self.user, "duplicate", "")

        target.refresh_from_db()
        self.assertEqual(target.streak_days, 10)  # Took higher
        self.assertEqual(target.total_checkins, 80)  # Sum
        self.assertEqual(target.badge_level, "gold")  # Took higher


class ChooseCanonicalTests(TestCase):
    """Test canonical member selection logic"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.business = Business.objects.create(name="Test Gym", kind="gym")

    def test_choose_member_with_most_payments(self):
        """Member with most payments is chosen"""
        member1 = GymMember.objects.create(
            business=self.business,
            name="Lydia A",
            phone="0999123456",
            joined_at=timezone.now(),
        )
        member2 = GymMember.objects.create(
            business=self.business,
            name="Lydia B",
            phone="0888765432",
            joined_at=timezone.now(),
        )

        # Member2 has more payments
        for _ in range(3):
            GymPayment.objects.create(
                member=member2,
                membership_amount=Decimal("55000"),
                trainer_fee=Decimal("0"),
                start_date=timezone.now().date(),
                end_date=timezone.now().date(),
                paid_by=self.user,
            )

        canonical = choose_canonical_member([member1, member2])
        self.assertEqual(canonical, member2)

    def test_choose_earliest_if_no_payments(self):
        """If no payments, choose member with earliest joined_at"""
        member1 = GymMember.objects.create(
            business=self.business,
            name="Lydia A",
            phone="0999123456",
            joined_at=timezone.now() - timezone.timedelta(days=10),
        )
        member2 = GymMember.objects.create(
            business=self.business,
            name="Lydia B",
            phone="0888765432",
            joined_at=timezone.now(),
        )

        canonical = choose_canonical_member([member1, member2])
        self.assertEqual(canonical, member1)


class BulkCreateTests(TransactionTestCase):
    """Test bulk member creation"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.business = Business.objects.create(name="Test Gym", kind="gym")

    def test_bulk_create_multiple_members(self):
        """Can create multiple members at once"""
        members_data = [
            {"name": "John Doe", "phone": "0999123456", "email": "john@example.com"},
            {"name": "Jane Smith", "phone": "0888765432", "email": "jane@example.com"},
            {"name": "Bob Wilson", "phone": "0777654321", "email": ""},
        ]

        results = bulk_create_members(self.business, members_data, self.user)

        self.assertEqual(len(results["created"]), 3)
        self.assertEqual(len(results["skipped_duplicates"]), 0)
        self.assertEqual(len(results["errors"]), 0)

    def test_bulk_create_skips_duplicates(self):
        """Duplicates in batch are skipped"""
        # Create existing member
        GymMember.objects.create(
            business=self.business,
            name="John Doe",
            phone="0999000000",
        )

        members_data = [
            {"name": "John Doe", "phone": "0999123456", "email": "john@example.com"},  # Duplicate
            {"name": "Jane Smith", "phone": "0888765432", "email": "jane@example.com"},  # New
        ]

        results = bulk_create_members(self.business, members_data, self.user, skip_duplicates=True)

        self.assertEqual(len(results["created"]), 1)
        self.assertEqual(len(results["skipped_duplicates"]), 1)
        self.assertEqual(results["created"][0].name, "Jane Smith")

    def test_bulk_create_skips_duplicate_in_batch(self):
        """Duplicate names within the same batch are skipped"""
        members_data = [
            {"name": "John Doe", "phone": "0999123456", "email": "john@example.com"},
            {"name": "Jane Smith", "phone": "0888765432", "email": "jane@example.com"},
            {"name": "john doe", "phone": "0777654321", "email": "john2@example.com"},  # Duplicate in batch
        ]

        results = bulk_create_members(self.business, members_data, self.user, skip_duplicates=True)

        self.assertEqual(len(results["created"]), 2)
        self.assertEqual(len(results["skipped_duplicates"]), 1)

    def test_bulk_create_validates_phone(self):
        """Invalid phone numbers are reported as errors"""
        members_data = [
            {"name": "John Doe", "phone": "invalid", "email": "john@example.com"},
            {"name": "Jane Smith", "phone": "0888765432", "email": "jane@example.com"},
        ]

        results = bulk_create_members(self.business, members_data, self.user)

        self.assertEqual(len(results["errors"]), 1)
        self.assertEqual(len(results["created"]), 1)
        self.assertIn("phone", results["errors"][0]["error"].lower())

    def test_bulk_create_validates_email(self):
        """Invalid emails are reported as errors"""
        members_data = [
            {"name": "John Doe", "phone": "0999123456", "email": "not-an-email"},
            {"name": "Jane Smith", "phone": "0888765432", "email": "jane@example.com"},
        ]

        results = bulk_create_members(self.business, members_data, self.user)

        self.assertEqual(len(results["errors"]), 1)
        self.assertEqual(len(results["created"]), 1)
        self.assertIn("email", results["errors"][0]["error"].lower())

    def test_bulk_create_skips_empty_names(self):
        """Empty names are silently skipped"""
        members_data = [
            {"name": "", "phone": "0999123456", "email": "john@example.com"},
            {"name": "Jane Smith", "phone": "0888765432", "email": "jane@example.com"},
        ]

        results = bulk_create_members(self.business, members_data, self.user)

        self.assertEqual(len(results["created"]), 1)
        self.assertEqual(results["created"][0].name, "Jane Smith")


class DedupeServiceTests(TransactionTestCase):
    """Test dedupe service function"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.business = Business.objects.create(name="Test Gym", kind="gym")

    def test_find_duplicate_members(self):
        """find_duplicate_members finds all duplicate groups"""
        # Create duplicates
        GymMember.objects.create(business=self.business, name="Lydia Majawa", phone="0999111111")
        GymMember.objects.create(business=self.business, name="LYDIA MAJAWA", phone="0999222222")
        GymMember.objects.create(business=self.business, name="John Doe", phone="0999333333")
        GymMember.objects.create(business=self.business, name="john doe", phone="0999444444")

        groups = find_duplicate_members(self.business)

        self.assertEqual(len(groups), 2)  # Two duplicate groups
        # Each group should have 2 members
        self.assertEqual(len(groups[0]), 2)
        self.assertEqual(len(groups[1]), 2)

    def test_dedupe_members_dry_run(self):
        """Dry run doesn't make changes"""
        GymMember.objects.create(business=self.business, name="Lydia Majawa", phone="0999111111")
        GymMember.objects.create(business=self.business, name="LYDIA MAJAWA", phone="0999222222")

        stats = dedupe_members(self.business, self.user, dry_run=True)

        self.assertEqual(stats["duplicate_groups_found"], 1)
        self.assertEqual(stats["members_merged"], 0)
        # Both members still exist
        self.assertEqual(GymMember.objects.filter(business=self.business).count(), 2)

    def test_dedupe_members_merges_duplicates(self):
        """dedupe_members merges all duplicate groups"""
        GymMember.objects.create(business=self.business, name="Lydia Majawa", phone="0999111111")
        GymMember.objects.create(business=self.business, name="LYDIA MAJAWA", phone="0999222222")
        GymMember.objects.create(business=self.business, name="John Doe", phone="0999333333")

        stats = dedupe_members(self.business, self.user, dry_run=False)

        self.assertEqual(stats["duplicate_groups_found"], 1)
        self.assertEqual(stats["members_merged"], 1)
        self.assertEqual(stats["canonical_members_kept"], 1)

        # Only 2 active members remain (1 merged)
        self.assertEqual(GymMember.objects.filter(business=self.business).count(), 2)

















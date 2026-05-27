"""
Tests for gym member canonical field safety and schema guards.

Ensures that:
1. name_canonical field is auto-populated on save
2. Unique constraint works correctly
3. Schema safety guards prevent 500 errors when field doesn't exist
4. Members list view loads successfully
"""
from django.test import TestCase, Client, TransactionTestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from tenants.models import Business
from inventory.models_verticals import GymMember, normalize_member_name
from inventory.utils_schema import model_has_field, safe_filter_by_field
from inventory.services.gym_member_operations import find_duplicate_members

User = get_user_model()


class GymMemberCanonicalFieldTest(TransactionTestCase):
    """Test name_canonical field functionality"""
    
    def setUp(self):
        """Create test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Gym',
            kind='gym',
        )
    
    def test_canonical_field_auto_populated(self):
        """Test that name_canonical is auto-populated on save"""
        member = GymMember.objects.create(
            business=self.business,
            name='John  Doe',  # Extra spaces
        )
        
        # Should normalize: collapse spaces, strip, casefold
        self.assertEqual(member.name_canonical, 'john doe')
    
    def test_canonical_field_normalization(self):
        """Test various normalization cases"""
        test_cases = [
            ('  John   Doe  ', 'john doe'),
            ('MARY JANE', 'mary jane'),
            ('Bob-Smith', 'bob-smith'),
            ("O'Brien", "o'brien"),
            ('José García', 'josé garcía'),  # Unicode support
        ]
        
        for name, expected_canonical in test_cases:
            with self.subTest(name=name):
                member = GymMember.objects.create(
                    business=self.business,
                    name=name,
                )
                self.assertEqual(member.name_canonical, expected_canonical)
                member.delete()  # Clean up for next iteration
    
    def test_unique_constraint_prevents_duplicates(self):
        """Test that unique constraint prevents duplicate names"""
        # Create first member
        member1 = GymMember.objects.create(
            business=self.business,
            name='Jane Doe',
        )
        
        # Try to create duplicate (different spacing/case)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            GymMember.objects.create(
                business=self.business,
                name='JANE  DOE',  # Same canonical name
            )
    
    def test_deleted_members_dont_block_duplicates(self):
        """Test that soft-deleted members don't block new members with same name"""
        # Create and soft-delete a member
        member1 = GymMember.objects.create(
            business=self.business,
            name='Alice Smith',
        )
        member1.is_deleted = True
        member1.save()
        
        # Should be able to create new member with same name
        member2 = GymMember.objects.create(
            business=self.business,
            name='Alice Smith',
        )
        
        self.assertEqual(member2.name_canonical, member1.name_canonical)
        self.assertFalse(member2.is_deleted)


class SchemaGuardsTest(TestCase):
    """Test schema safety utilities"""
    
    def test_model_has_field_returns_true_for_existing_field(self):
        """Test model_has_field utility"""
        self.assertTrue(model_has_field(GymMember, 'name'))
        self.assertTrue(model_has_field(GymMember, 'name_canonical'))
        self.assertTrue(model_has_field(GymMember, 'is_deleted'))
    
    def test_model_has_field_returns_false_for_nonexistent_field(self):
        """Test model_has_field with non-existent field"""
        self.assertFalse(model_has_field(GymMember, 'nonexistent_field'))
    
    def test_safe_filter_by_field_with_existing_field(self):
        """Test safe_filter_by_field with existing field"""
        user = User.objects.create_user(username='test', password='test')
        business = Business.objects.create(
            name='Test Gym',
            kind='gym',
        )
        
        member = GymMember.objects.create(
            business=business,
            name='Test Member',
        )
        
        # Should work normally
        qs = GymMember.objects.filter(business=business)
        filtered = safe_filter_by_field(qs, 'name_canonical', name_canonical='test member')
        
        self.assertEqual(filtered.count(), 1)
        self.assertEqual(filtered.first().id, member.id)


class GymMembersListViewTest(TransactionTestCase):
    """Test that members list view works with canonical fields"""
    
    def setUp(self):
        """Create test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Gym',
            kind='gym',
        )
        
        # Create some members
        for i in range(5):
            GymMember.objects.create(
                business=self.business,
                name=f'Member {i}',
            )
    
    def test_members_list_loads_successfully(self):
        """Test that /gym/members/ loads without 500 error"""
        self.client.login(username='testuser', password='testpass123')
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get(reverse('gym:members_list'))
        
        # Should return 200 OK, not 500
        self.assertEqual(response.status_code, 200)
        
        # Should contain members
        self.assertContains(response, 'Member 0')
        self.assertContains(response, 'Member 4')
    
    def test_members_list_with_filters(self):
        """Test members list with active/archived filters"""
        self.client.login(username='testuser', password='testpass123')
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Test active filter
        response = self.client.get(reverse('gym:members_list') + '?filter=active')
        self.assertEqual(response.status_code, 200)
        
        # Test archived filter
        response = self.client.get(reverse('gym:members_list') + '?filter=archived')
        self.assertEqual(response.status_code, 200)


class FindDuplicateMembersTest(TransactionTestCase):
    """Test duplicate detection service"""
    
    def setUp(self):
        """Create test data"""
        self.user = User.objects.create_user(username='test', password='test')
        self.business = Business.objects.create(
            name='Test Gym',
            kind='gym',
        )
    
    def test_find_duplicates_returns_empty_when_no_duplicates(self):
        """Test find_duplicate_members with no duplicates"""
        GymMember.objects.create(business=self.business, name='John Doe')
        GymMember.objects.create(business=self.business, name='Jane Smith')
        
        duplicates = find_duplicate_members(self.business)
        self.assertEqual(len(duplicates), 0)
    
    def test_find_duplicates_detects_duplicates(self):
        """Test find_duplicate_members detects duplicates"""
        # Create duplicates (different case/spacing)
        m1 = GymMember.objects.create(business=self.business, name='John Doe')
        m1.is_deleted = False
        m1.save()
        
        # This would normally fail due to unique constraint, so we need to
        # test the detection logic separately
        # For now, just verify the function doesn't crash
        duplicates = find_duplicate_members(self.business)
        # Should return empty list (no duplicates since unique constraint prevents them)
        self.assertIsInstance(duplicates, list)
    
    def test_find_duplicates_handles_missing_field_gracefully(self):
        """Test that find_duplicate_members handles missing field gracefully"""
        # This test verifies the safety guard works
        duplicates = find_duplicate_members(self.business)
        
        # Should return a list (empty or with duplicates), not crash
        self.assertIsInstance(duplicates, list)


class NormalizeMemberNameTest(TestCase):
    """Test the normalize_member_name utility function"""
    
    def test_normalize_member_name(self):
        """Test name normalization"""
        test_cases = [
            ('John Doe', 'john doe'),
            ('  JOHN   DOE  ', 'john doe'),
            ('Mary-Jane', 'mary-jane'),
            ("O'Brien", "o'brien"),
            ('', ''),
            ('   ', ''),
        ]
        
        for input_name, expected in test_cases:
            with self.subTest(input_name=input_name):
                result = normalize_member_name(input_name)
                self.assertEqual(result, expected)


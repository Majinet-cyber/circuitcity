"""
Comprehensive tests for gym member barcode/QR code and scanning features.
"""
import json
from decimal import Decimal

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse

from tenants.models import Business, Membership, Location
from inventory.models_verticals import (
    GymMember, GymTrainer, GymSettings, GymMemberStatus
)
from inventory.business_kinds import BusinessKind

User = get_user_model()


class GymBarcodeTestCase(TestCase):
    """Test gym member barcode generation and QR codes"""
    
    def setUp(self):
        """Create test business, user, and gym settings"""
        # Create user
        self.user = User.objects.create_user(
            username="gymmanager",
            email="manager@gym.test",
            password="testpass123"
        )
        
        # Create business
        self.business = Business.objects.create(
            name="Test Gym",
            business_kind=BusinessKind.GYM,
            currency="MWK",
            country="MW"
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Location",
            city="Lilongwe"
        )
        
        # Create membership
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            is_active=True
        )
        
        # Create gym settings
        self.gym_settings = GymSettings.objects.create(
            business=self.business,
            default_membership_price=Decimal("55000.00"),
            default_trainer_fee=Decimal("15000.00")
        )
        
        # Create trainer
        self.trainer = GymTrainer.objects.create(
            business=self.business,
            name="John Trainer",
            phone="0999123456",
            is_active=True
        )
        
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_member_code_auto_generated(self):
        """Test that member_code is automatically generated on member creation"""
        member = GymMember.objects.create(
            business=self.business,
            name="Test Member",
            phone="0991234567"
        )
        
        self.assertIsNotNone(member.member_code)
        self.assertTrue(member.member_code.startswith("GYM-"))
        self.assertEqual(len(member.member_code), 10)  # GYM-XXXXXX format
    
    def test_member_code_uniqueness(self):
        """Test that member codes are unique per business"""
        member1 = GymMember.objects.create(
            business=self.business,
            name="Member One",
            phone="0991111111"
        )
        
        member2 = GymMember.objects.create(
            business=self.business,
            name="Member Two",
            phone="0992222222"
        )
        
        self.assertNotEqual(member1.member_code, member2.member_code)
    
    def test_member_qr_code_generation(self):
        """Test that QR code data URL is generated correctly"""
        member = GymMember.objects.create(
            business=self.business,
            name="Test Member",
            phone="0991234567"
        )
        
        qr_url = member.get_qr_code_data_url()
        
        self.assertIsNotNone(qr_url)
        self.assertTrue(qr_url.startswith("data:image/png;base64,"))
        self.assertGreater(len(qr_url), 100)  # Should have substantial base64 content
    
    def test_member_code_preserved_on_update(self):
        """Test that member_code doesn't change when member is updated"""
        member = GymMember.objects.create(
            business=self.business,
            name="Test Member",
            phone="0991234567"
        )
        
        original_code = member.member_code
        
        # Update member
        member.name = "Updated Name"
        member.save()
        
        member.refresh_from_db()
        self.assertEqual(member.member_code, original_code)


class GymScanLookupTestCase(TestCase):
    """Test gym member scanning and lookup API"""
    
    def setUp(self):
        """Create test data"""
        # Create user
        self.user = User.objects.create_user(
            username="gymstaff",
            email="staff@gym.test",
            password="testpass123"
        )
        
        # Create business
        self.business = Business.objects.create(
            name="Test Gym",
            business_kind=BusinessKind.GYM,
            currency="MWK",
            country="MW"
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Location",
            city="Lilongwe"
        )
        
        # Create membership
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="AGENT",
            is_active=True
        )
        
        # Create active member
        today = timezone.now().date()
        self.active_member = GymMember.objects.create(
            business=self.business,
            name="Active Member",
            phone="0991111111",
            status=GymMemberStatus.ACTIVE,
            membership_start=today,
            membership_end=today + timezone.timedelta(days=20),
            membership_fee=Decimal("55000.00")
        )
        
        # Create expired member
        self.expired_member = GymMember.objects.create(
            business=self.business,
            name="Expired Member",
            phone="0992222222",
            status=GymMemberStatus.BEHIND_SCHEDULE,
            membership_start=today - timezone.timedelta(days=40),
            membership_end=today - timezone.timedelta(days=10),
            membership_fee=Decimal("55000.00")
        )
        
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_scan_page_loads(self):
        """Test that the scan member page loads correctly"""
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session['active_location_id'] = self.location.id
        session.save()
        
        response = self.client.get(reverse('gym:scan_member'))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Scan Member")
    
    def test_scan_lookup_active_member(self):
        """Test scanning an active member returns correct status"""
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session['active_location_id'] = self.location.id
        session.save()
        
        response = self.client.post(
            reverse('gym:scan_lookup'),
            data=json.dumps({"code": self.active_member.member_code}),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["member"]["name"], "Active Member")
        self.assertEqual(data["member"]["status_color"], "success")
        self.assertTrue(data["member"]["is_active"])
        self.assertFalse(data["member"]["is_overdue"])
        self.assertGreater(data["member"]["days_left"], 0)
    
    def test_scan_lookup_expired_member(self):
        """Test scanning an expired member returns correct status"""
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session['active_location_id'] = self.location.id
        session.save()
        
        response = self.client.post(
            reverse('gym:scan_lookup'),
            data=json.dumps({"code": self.expired_member.member_code}),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["member"]["name"], "Expired Member")
        self.assertEqual(data["member"]["status_color"], "danger")
        self.assertFalse(data["member"]["is_active"])
        self.assertTrue(data["member"]["is_overdue"])
        self.assertEqual(data["member"]["days_left"], 0)
    
    def test_scan_lookup_invalid_code(self):
        """Test scanning with invalid code returns error"""
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session['active_location_id'] = self.location.id
        session.save()
        
        response = self.client.post(
            reverse('gym:scan_lookup'),
            data=json.dumps({"code": "GYM-INVALID"}),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 404)
        
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["error"].lower())
    
    def test_scan_lookup_no_code(self):
        """Test scanning without providing code returns error"""
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session['active_location_id'] = self.location.id
        session.save()
        
        response = self.client.post(
            reverse('gym:scan_lookup'),
            data=json.dumps({}),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 400)
        
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertIn("no code", data["error"].lower())
    
    def test_scan_lookup_wrong_business(self):
        """Test that members from other businesses cannot be scanned"""
        # Create another business
        other_business = Business.objects.create(
            name="Other Gym",
            business_kind=BusinessKind.GYM,
            currency="MWK",
            country="MW"
        )
        
        # Create member in other business
        other_member = GymMember.objects.create(
            business=other_business,
            name="Other Member",
            phone="0993333333"
        )
        
        # Set active business to original business
        session = self.client.session
        session['active_business_id'] = self.business.id
        session['active_location_id'] = self.location.id
        session.save()
        
        # Try to scan member from other business
        response = self.client.post(
            reverse('gym:scan_lookup'),
            data=json.dumps({"code": other_member.member_code}),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertFalse(data["ok"])


class GymWizardTestCase(TestCase):
    """Test gym member addition wizard flow"""
    
    def setUp(self):
        """Create test data"""
        # Create user
        self.user = User.objects.create_user(
            username="gymmanager",
            email="manager@gym.test",
            password="testpass123"
        )
        
        # Create business
        self.business = Business.objects.create(
            name="Test Gym",
            business_kind=BusinessKind.GYM,
            currency="MWK",
            country="MW"
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Location",
            city="Lilongwe"
        )
        
        # Create membership
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            is_active=True
        )
        
        # Create gym settings
        GymSettings.objects.create(
            business=self.business,
            default_membership_price=Decimal("55000.00"),
            default_trainer_fee=Decimal("15000.00")
        )
        
        # Create trainer
        self.trainer = GymTrainer.objects.create(
            business=self.business,
            name="John Trainer",
            phone="0999123456",
            is_active=True
        )
        
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_wizard_step_0_welcome(self):
        """Test wizard welcome screen loads"""
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session['active_location_id'] = self.location.id
        session.save()
        
        response = self.client.get(reverse('gym:member_add') + '?step=0')
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add New Member")
        self.assertContains(response, "Get Started")
    
    def test_wizard_complete_flow_no_trainer(self):
        """Test complete wizard flow without trainer"""
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session['active_location_id'] = self.location.id
        session.save()
        
        # Step 1: Submit member details
        response = self.client.post(
            reverse('gym:member_add') + '?step=1',
            {
                'name': 'Test Member',
                'phone': '0991234567',
                'email': 'test@member.com'
            }
        )
        self.assertRedirects(response, reverse('gym:member_add') + '?step=2')
        
        # Step 2: Select no trainer
        response = self.client.post(
            reverse('gym:member_add') + '?step=2',
            {'trainer_id': 'none'}
        )
        self.assertRedirects(response, reverse('gym:member_add') + '?step=3')
        
        # Step 3: Confirm (not marking as paid)
        response = self.client.post(
            reverse('gym:member_add') + '?step=3',
            {}
        )
        self.assertRedirects(response, reverse('gym:member_add') + '?step=4')
        
        # Verify member was created
        member = GymMember.objects.get(phone='0991234567')
        self.assertEqual(member.name, 'Test Member')
        self.assertEqual(member.business, self.business)
        self.assertIsNone(member.trainer)
        self.assertFalse(member.has_trainer)
        self.assertIsNotNone(member.member_code)
        
    def test_wizard_complete_flow_with_trainer(self):
        """Test complete wizard flow with trainer assignment"""
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session['active_location_id'] = self.location.id
        session.save()
        
        # Step 1: Submit member details
        self.client.post(
            reverse('gym:member_add') + '?step=1',
            {
                'name': 'Member With Trainer',
                'phone': '0997654321',
                'email': ''
            }
        )
        
        # Step 2: Select trainer
        self.client.post(
            reverse('gym:member_add') + '?step=2',
            {'trainer_id': str(self.trainer.id)}
        )
        
        # Step 3: Confirm and mark as paid
        self.client.post(
            reverse('gym:member_add') + '?step=3',
            {'mark_as_paid': 'yes'}
        )
        
        # Verify member was created with trainer
        member = GymMember.objects.get(phone='0997654321')
        self.assertEqual(member.name, 'Member With Trainer')
        self.assertEqual(member.trainer, self.trainer)
        self.assertTrue(member.has_trainer)
        self.assertEqual(member.status, GymMemberStatus.ACTIVE)
        self.assertIsNotNone(member.membership_start)
        self.assertIsNotNone(member.membership_end)


class GymBarcodeIntegrationTestCase(TestCase):
    """Integration tests for complete barcode workflow"""
    
    def setUp(self):
        """Create test data"""
        # Create user
        self.user = User.objects.create_user(
            username="gymstaff",
            email="staff@gym.test",
            password="testpass123"
        )
        
        # Create business
        self.business = Business.objects.create(
            name="Test Gym",
            business_kind=BusinessKind.GYM,
            currency="MWK",
            country="MW"
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Location",
            city="Lilongwe"
        )
        
        # Create membership
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="AGENT",
            is_active=True
        )
        
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_end_to_end_member_creation_and_scan(self):
        """Test complete flow: create member -> get QR code -> scan"""
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session['active_location_id'] = self.location.id
        session.save()
        
        # 1. Create member
        member = GymMember.objects.create(
            business=self.business,
            name="E2E Test Member",
            phone="0998888888",
            status=GymMemberStatus.ACTIVE,
            membership_start=timezone.now().date(),
            membership_end=timezone.now().date() + timezone.timedelta(days=25),
            membership_fee=Decimal("55000.00")
        )
        
        # 2. Verify QR code generated
        self.assertIsNotNone(member.member_code)
        qr_url = member.get_qr_code_data_url()
        self.assertTrue(qr_url.startswith("data:image/png;base64,"))
        
        # 3. Scan the member
        response = self.client.post(
            reverse('gym:scan_lookup'),
            data=json.dumps({"code": member.member_code}),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # 4. Verify scan results
        self.assertTrue(data["ok"])
        self.assertEqual(data["member"]["name"], "E2E Test Member")
        self.assertEqual(data["member"]["phone"], "0998888888")
        self.assertEqual(data["member"]["days_left"], 25)
        self.assertTrue(data["member"]["is_active"])
        self.assertEqual(data["member"]["status_color"], "success")


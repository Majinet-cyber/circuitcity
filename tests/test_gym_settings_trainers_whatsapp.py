"""
Tests for Gym Settings, Trainers, and WhatsApp features.
Tests all 4 requirements from the implementation spec.
"""
import pytest
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model

from tenants.models import Business
from inventory.models_verticals import GymSettings, GymTrainer, GymMember

User = get_user_model()


@pytest.fixture
def gym_business(db):
    """Create a gym business for testing"""
    business = Business.objects.create(
        name="Test Gym",
        business_kind="gym",
        is_active=True,
    )
    return business


@pytest.fixture
def manager_user(db, gym_business):
    """Create a manager user with access to gym business"""
    user = User.objects.create_user(
        username="gymmanager",
        email="manager@gym.com",
        password="testpass123",
        is_staff=True,  # Staff users have manager permissions
    )
    return user


@pytest.fixture
def gym_member(db, gym_business):
    """Create a test gym member"""
    member = GymMember.objects.create(
        business=gym_business,
        name="Test Member",
        phone="0999123456",
        email="member@test.com",
        membership_fee=Decimal("50000.00"),
    )
    return member


# ==============================================================================
# 1. SETTINGS BUTTON IN SIDEBAR
# ==============================================================================

@pytest.mark.django_db
class TestGymSettingsSidebar:
    """Test that Settings button appears in gym sidebar"""

    def test_settings_in_sidebar_config(self):
        """Test that settings item is in gym sidebar configuration"""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        items = get_vertical_sidebar_items("gym")
        
        # Find settings item
        settings_item = None
        for item in items:
            if item.get("key") == "settings":
                settings_item = item
                break
        
        assert settings_item is not None, "Settings item not found in gym sidebar"
        assert settings_item["url"] == "gym:settings"
        assert settings_item["label"] == "Settings"
        assert settings_item["icon"] == "bi-gear"
        assert settings_item["require_manager"] is True

    def test_trainers_sidebar_points_to_gym_trainers_list(self):
        """Test that Trainers sidebar item points to gym:trainers_list"""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        items = get_vertical_sidebar_items("gym")
        
        # Find trainers item
        trainers_item = None
        for item in items:
            if item.get("key") == "trainers":
                trainers_item = item
                break
        
        assert trainers_item is not None, "Trainers item not found in gym sidebar"
        assert trainers_item["url"] == "gym:trainers_list"
        assert trainers_item["active_prefix"] == "/gym/trainers/"


# ==============================================================================
# 2. GYM SETTINGS: MEMBERSHIP FEE + TRAINER FEE
# ==============================================================================

@pytest.mark.django_db
class TestGymSettingsModel:
    """Test GymSettings model and default values"""

    def test_gym_settings_auto_created_with_defaults(self, gym_business):
        """Test that GymSettings is auto-created with correct defaults"""
        settings, created = GymSettings.objects.get_or_create(business=gym_business)
        
        assert settings.default_membership_price == Decimal("50000.00")
        assert settings.default_trainer_fee == Decimal("50000.00")

    def test_gym_settings_editable(self, gym_business):
        """Test that gym settings can be edited"""
        settings = GymSettings.objects.create(
            business=gym_business,
            default_membership_price=Decimal("60000.00"),
            default_trainer_fee=Decimal("40000.00"),
        )
        
        settings.default_membership_price = Decimal("70000.00")
        settings.save()
        
        settings.refresh_from_db()
        assert settings.default_membership_price == Decimal("70000.00")


@pytest.mark.django_db
class TestGymSettingsView:
    """Test gym settings view and form"""

    def test_settings_view_accessible_by_manager(self, client, gym_business, manager_user):
        """Test that settings view is accessible by manager"""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:settings")
        response = client.get(url)
        
        assert response.status_code == 200
        assert "form" in response.context
        assert "gym_settings" in response.context

    def test_settings_view_creates_default_trainers(self, client, gym_business, manager_user):
        """Test that accessing settings view creates default trainers"""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        # Ensure no trainers exist
        assert GymTrainer.objects.filter(business=gym_business).count() == 0
        
        url = reverse("gym:settings")
        response = client.get(url)
        
        assert response.status_code == 200
        
        # Check that default trainers were created
        trainers = GymTrainer.objects.filter(business=gym_business, is_active=True)
        trainer_names = [t.name for t in trainers]
        
        assert "Lester" in trainer_names
        assert "Steve" in trainer_names
        assert "Philip" in trainer_names
        assert "Ben" in trainer_names

    def test_settings_form_updates_fees(self, client, gym_business, manager_user):
        """Test that settings form can update fees"""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:settings")
        data = {
            "default_membership_price": "75000.00",
            "default_trainer_fee": "45000.00",
            "support_phone": "0999111222",
            "support_email": "support@gym.com",
            "arrears_message": "Please renew your membership.",
        }
        
        response = client.post(url, data)
        
        assert response.status_code == 302  # Redirect on success
        
        # Check that settings were updated
        settings = GymSettings.objects.get(business=gym_business)
        assert settings.default_membership_price == Decimal("75000.00")
        assert settings.default_trainer_fee == Decimal("45000.00")


@pytest.mark.django_db
class TestMemberFeePrefill:
    """Test that member fees are pre-filled from settings"""

    def test_add_member_prefills_membership_fee(self, client, gym_business, manager_user):
        """Test that add member form prefills membership fee from settings"""
        # Create settings with custom fee
        GymSettings.objects.create(
            business=gym_business,
            default_membership_price=Decimal("55000.00"),
            default_trainer_fee=Decimal("35000.00"),
        )
        
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:member_add_old")
        response = client.get(url)
        
        assert response.status_code == 200
        form = response.context.get("form")
        assert form.initial.get("membership_fee") == Decimal("55000.00")
        assert form.initial.get("trainer_fee") == Decimal("35000.00")

    def test_edit_member_shows_existing_fee(self, client, gym_business, manager_user, gym_member):
        """Test that edit member form shows member's existing fee, not default"""
        # Create settings with different default
        GymSettings.objects.create(
            business=gym_business,
            default_membership_price=Decimal("60000.00"),
        )
        
        # Member has different fee
        gym_member.membership_fee = Decimal("45000.00")
        gym_member.save()
        
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:member_edit", args=[gym_member.id])
        response = client.get(url)
        
        assert response.status_code == 200
        form = response.context.get("form")
        # Should show member's existing fee, not default
        assert form.initial.get("membership_fee") == Decimal("45000.00")


# ==============================================================================
# 3. TRAINERS: SEED 4 DEFAULT + SELECTABLE
# ==============================================================================

@pytest.mark.django_db
class TestGymTrainers:
    """Test gym trainers functionality"""

    def test_default_trainers_seeded(self, gym_business):
        """Test that default trainers are seeded"""
        # Simulate settings view access (which seeds trainers)
        default_trainers = ["Lester", "Steve", "Philip", "Ben"]
        for trainer_name in default_trainers:
            GymTrainer.objects.get_or_create(
                business=gym_business,
                name=trainer_name,
                defaults={"is_active": True}
            )
        
        trainers = GymTrainer.objects.filter(business=gym_business, is_active=True)
        trainer_names = [t.name for t in trainers]
        
        assert len(trainer_names) == 4
        assert "Lester" in trainer_names
        assert "Steve" in trainer_names
        assert "Philip" in trainer_names
        assert "Ben" in trainer_names

    def test_trainer_unique_per_business(self, gym_business):
        """Test that trainer names are unique per business"""
        GymTrainer.objects.create(business=gym_business, name="Lester")
        
        # Try to create duplicate
        trainer, created = GymTrainer.objects.get_or_create(
            business=gym_business,
            name="Lester",
        )
        
        assert not created  # Should not create duplicate
        assert GymTrainer.objects.filter(business=gym_business, name="Lester").count() == 1

    def test_member_can_have_trainer(self, gym_business):
        """Test that member can be assigned a trainer"""
        trainer = GymTrainer.objects.create(
            business=gym_business,
            name="Steve",
            is_active=True,
        )
        
        member = GymMember.objects.create(
            business=gym_business,
            name="Test Member",
            phone="0999111222",
            trainer=trainer,
        )
        
        assert member.trainer == trainer
        assert member.trainer.name == "Steve"

    def test_member_trainer_optional(self, gym_business):
        """Test that trainer is optional for member"""
        member = GymMember.objects.create(
            business=gym_business,
            name="Test Member",
            phone="0999111222",
            trainer=None,
        )
        
        assert member.trainer is None

    def test_trainers_list_view_accessible(self, client, gym_business, manager_user):
        """Test that trainers list view is accessible"""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:trainers_list")
        response = client.get(url)
        
        assert response.status_code == 200

    def test_add_trainer_view_works(self, client, gym_business, manager_user):
        """Test that add trainer view works"""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:trainer_add")
        data = {
            "name": "New Trainer",
            "phone": "0999222333",
            "email": "trainer@gym.com",
            "notes": "Test trainer",
        }
        
        response = client.post(url, data)
        
        assert response.status_code == 302  # Redirect on success
        
        # Check trainer was created
        trainer = GymTrainer.objects.get(business=gym_business, name="New Trainer")
        assert trainer.phone == "0999222333"


# ==============================================================================
# 4. WHATSAPP MESSAGE SENDING
# ==============================================================================

@pytest.mark.django_db
class TestWhatsAppMessaging:
    """Test WhatsApp message generation and sending"""

    def test_whatsapp_forward_view_accessible(self, client, gym_member):
        """Test that WhatsApp forward view is accessible"""
        url = reverse("gym:member_whatsapp_forward", args=[gym_member.qr_uuid])
        response = client.get(url)
        
        assert response.status_code == 200
        assert "message_template" in response.context

    def test_whatsapp_message_contains_member_info(self, client, gym_member):
        """Test that WhatsApp message contains member name, code, and QR link"""
        url = reverse("gym:member_whatsapp_forward", args=[gym_member.qr_uuid])
        response = client.get(url)
        
        message = response.context["message_template"]
        
        assert gym_member.name in message
        assert gym_member.member_number or gym_member.member_code in message
        assert "qr" in message.lower()

    def test_whatsapp_phone_normalization_malawi_0_prefix(self, client, gym_member):
        """Test phone normalization: 0999123456 -> 265999123456"""
        url = reverse("gym:member_whatsapp_forward", args=[gym_member.qr_uuid])
        
        response = client.post(url, {"phone": "0999123456"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "265999123456" in data["whatsapp_url"]

    def test_whatsapp_phone_normalization_9_digits(self, client, gym_member):
        """Test phone normalization: 999123456 -> 265999123456"""
        url = reverse("gym:member_whatsapp_forward", args=[gym_member.qr_uuid])
        
        response = client.post(url, {"phone": "999123456"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "265999123456" in data["whatsapp_url"]

    def test_whatsapp_phone_normalization_265_prefix(self, client, gym_member):
        """Test phone normalization: 265999123456 -> 265999123456"""
        url = reverse("gym:member_whatsapp_forward", args=[gym_member.qr_uuid])
        
        response = client.post(url, {"phone": "265999123456"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "265999123456" in data["whatsapp_url"]

    def test_whatsapp_invalid_phone_returns_error(self, client, gym_member):
        """Test that invalid phone number returns error"""
        url = reverse("gym:member_whatsapp_forward", args=[gym_member.qr_uuid])
        
        response = client.post(url, {"phone": "123"})  # Too short
        
        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    def test_whatsapp_url_format(self, client, gym_member):
        """Test that WhatsApp URL is in wa.me format"""
        url = reverse("gym:member_whatsapp_forward", args=[gym_member.qr_uuid])
        
        response = client.post(url, {"phone": "0999123456"})
        
        data = response.json()
        whatsapp_url = data["whatsapp_url"]
        
        assert whatsapp_url.startswith("https://wa.me/")
        assert "text=" in whatsapp_url  # Message is URL encoded

    def test_whatsapp_button_on_member_detail(self, client, gym_business, manager_user, gym_member):
        """Test that WhatsApp button appears on member detail page"""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:member_detail", args=[gym_member.id])
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode()
        
        # Check for WhatsApp button
        assert "whatsapp" in content.lower()
        assert str(gym_member.qr_uuid) in content


# ==============================================================================
# INTEGRATION TESTS
# ==============================================================================

@pytest.mark.django_db
class TestGymIntegration:
    """Integration tests for all features working together"""

    def test_full_flow_settings_to_member_with_trainer(self, client, gym_business, manager_user):
        """Test full flow: configure settings -> add member with trainer -> send WhatsApp"""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        # 1. Configure settings
        settings_url = reverse("gym:settings")
        settings_data = {
            "default_membership_price": "55000.00",
            "default_trainer_fee": "35000.00",
            "support_phone": "0999111222",
            "support_email": "support@gym.com",
            "arrears_message": "Please renew.",
        }
        response = client.post(settings_url, settings_data)
        assert response.status_code == 302
        
        # 2. Verify default trainers were created
        trainers = GymTrainer.objects.filter(business=gym_business, is_active=True)
        assert trainers.count() >= 4
        
        # 3. Add member with trainer
        trainer = trainers.first()
        member_url = reverse("gym:member_add_old")
        member_data = {
            "name": "Integration Test Member",
            "phone": "0999888777",
            "email": "member@test.com",
            "trainer": trainer.id,
            "membership_fee": "55000.00",
            "trainer_fee": "35000.00",
            "mark_as_paid": False,
        }
        response = client.post(member_url, member_data)
        assert response.status_code == 302
        
        # 4. Get member and verify
        member = GymMember.objects.get(business=gym_business, phone="0999888777")
        assert member.trainer == trainer
        assert member.membership_fee == Decimal("55000.00")
        
        # 5. Send WhatsApp message
        whatsapp_url = reverse("gym:member_whatsapp_forward", args=[member.qr_uuid])
        whatsapp_response = client.post(whatsapp_url, {"phone": "0999123456"})
        assert whatsapp_response.status_code == 200
        
        data = whatsapp_response.json()
        assert data["success"] is True
        assert "wa.me" in data["whatsapp_url"]


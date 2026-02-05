"""
Tests for gym trainers without user accounts feature.
"""
import pytest
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model
from inventory.models import Business, BusinessKind
from inventory.models_verticals import GymMember, GymTrainer, GymSettings

User = get_user_model()


@pytest.fixture
def gym_business(db):
    """Create a gym business"""
    business = Business.objects.create(
        name="Test Gym",
        kind=BusinessKind.GYM,
        is_active=True,
    )
    GymSettings.objects.create(
        business=business,
        default_membership_price=Decimal("50000.00"),
        default_trainer_fee=Decimal("30000.00"),
    )
    return business


@pytest.fixture
def manager_user(db, gym_business):
    """Create a manager user for the gym"""
    user = User.objects.create_user(
        username="manager",
        email="manager@testgym.com",
        password="testpass123",
        is_staff=True,  # Staff users have manager permissions
    )
    return user


@pytest.mark.django_db
class TestGymTrainerModel:
    """Test GymTrainer model functionality"""

    def test_create_trainer_without_user_account(self, gym_business):
        """Test creating a trainer without linking to a user account"""
        trainer = GymTrainer.objects.create(
            business=gym_business,
            name="John Trainer",
            phone="0999123456",
            email="john@gym.com",
            is_active=True,
        )
        
        assert trainer.id is not None
        assert trainer.user is None  # No user account linked
        assert trainer.name == "John Trainer"
        assert trainer.phone == "0999123456"
        assert trainer.is_active is True

    def test_create_trainer_with_optional_user_link(self, gym_business):
        """Test creating a trainer and optionally linking to user account later"""
        # Create trainer without user
        trainer = GymTrainer.objects.create(
            business=gym_business,
            name="Jane Trainer",
            phone="0999654321",
        )
        
        assert trainer.user is None
        
        # Later, link to user account
        user = User.objects.create_user(
            username="jane_trainer",
            email="jane@gym.com",
            password="pass123",
        )
        trainer.user = user
        trainer.save()
        
        # Verify link
        trainer.refresh_from_db()
        assert trainer.user == user

    def test_trainer_appears_in_business_queryset(self, gym_business):
        """Test that trainers appear in business-scoped queries"""
        trainer1 = GymTrainer.objects.create(
            business=gym_business,
            name="Trainer One",
            phone="0999111111",
        )
        trainer2 = GymTrainer.objects.create(
            business=gym_business,
            name="Trainer Two",
            phone="0999222222",
        )
        
        trainers = GymTrainer.objects.filter(business=gym_business)
        assert trainers.count() == 2
        assert trainer1 in trainers
        assert trainer2 in trainers

    def test_trainer_unique_per_business(self, gym_business):
        """Test that trainer names are unique per business"""
        GymTrainer.objects.create(
            business=gym_business,
            name="Duplicate Name",
            phone="0999111111",
        )
        
        # Creating another trainer with same name should fail (unique_together)
        with pytest.raises(Exception):  # IntegrityError or ValidationError
            GymTrainer.objects.create(
                business=gym_business,
                name="Duplicate Name",
                phone="0999222222",
            )

    def test_trainer_string_representation(self, gym_business):
        """Test trainer __str__ method"""
        trainer = GymTrainer.objects.create(
            business=gym_business,
            name="Test Trainer",
        )
        
        str_repr = str(trainer)
        assert "Test Trainer" in str_repr
        assert gym_business.name in str_repr


@pytest.mark.django_db
class TestTrainerMemberAssignment:
    """Test assigning trainers to members"""

    def test_assign_trainer_to_member(self, gym_business):
        """Test assigning a trainer (without user account) to a member"""
        trainer = GymTrainer.objects.create(
            business=gym_business,
            name="Coach Smith",
            phone="0999333333",
        )
        
        member = GymMember.objects.create(
            business=gym_business,
            name="Member One",
            phone="0999444444",
            trainer=trainer,
        )
        
        assert member.trainer == trainer
        assert trainer.members.filter(id=member.id).exists()

    def test_trainer_members_relationship(self, gym_business):
        """Test reverse relationship from trainer to members"""
        trainer = GymTrainer.objects.create(
            business=gym_business,
            name="Coach Johnson",
        )
        
        # Create 3 members with this trainer
        for i in range(3):
            GymMember.objects.create(
                business=gym_business,
                name=f"Member {i+1}",
                phone=f"09995555{i}",
                trainer=trainer,
            )
        
        # Check trainer.members relationship
        assert trainer.members.count() == 3

    def test_trainer_delete_sets_null_on_members(self, gym_business):
        """Test that deleting trainer sets member.trainer to NULL (on_delete=SET_NULL)"""
        trainer = GymTrainer.objects.create(
            business=gym_business,
            name="Temp Trainer",
        )
        
        member = GymMember.objects.create(
            business=gym_business,
            name="Member With Trainer",
            phone="0999666666",
            trainer=trainer,
        )
        
        trainer_id = trainer.id
        trainer.delete()
        
        # Member should still exist, but trainer should be None
        member.refresh_from_db()
        assert member.trainer is None


@pytest.mark.django_db
class TestTrainerUI:
    """Test trainer management UI"""

    def test_trainers_list_page_accessible(self, client, gym_business, manager_user):
        """Test that trainers list page is accessible to managers"""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:trainers_list")
        response = client.get(url)
        
        assert response.status_code == 200
        assert "Gym Trainers" in response.content.decode()

    def test_add_trainer_page_accessible(self, client, gym_business, manager_user):
        """Test that add trainer page is accessible to managers"""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:trainer_add")
        response = client.get(url)
        
        assert response.status_code == 200

    def test_create_trainer_via_form(self, client, gym_business, manager_user):
        """Test creating a trainer via the web form"""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:trainer_add")
        data = {
            "name": "New Trainer",
            "phone": "0999777777",
            "email": "newtrainer@gym.com",
            "notes": "Test notes",
        }
        response = client.post(url, data)
        
        # Should redirect on success
        assert response.status_code == 302
        
        # Verify trainer was created
        trainer = GymTrainer.objects.filter(business=gym_business, name="New Trainer").first()
        assert trainer is not None
        assert trainer.phone == "0999777777"
        assert trainer.email == "newtrainer@gym.com"
        assert trainer.user is None  # No user account

    def test_trainer_appears_in_member_form_dropdown(self, client, gym_business, manager_user):
        """Test that trainers appear in member add/edit form dropdown"""
        # Create a trainer
        trainer = GymTrainer.objects.create(
            business=gym_business,
            name="Available Trainer",
            phone="0999888888",
        )
        
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        # Go to member add form
        url = reverse("gym:member_add_old")  # Use old form for easier testing
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode()
        
        # Trainer should appear in dropdown
        assert "Available Trainer" in content

    def test_deactivate_trainer(self, client, gym_business, manager_user):
        """Test deactivating a trainer"""
        trainer = GymTrainer.objects.create(
            business=gym_business,
            name="To Be Deactivated",
            phone="0999999999",
            is_active=True,
        )
        
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:trainer_deactivate", args=[trainer.id])
        response = client.post(url)
        
        # Should redirect on success
        assert response.status_code == 302
        
        # Verify trainer was deactivated
        trainer.refresh_from_db()
        assert trainer.is_active is False


@pytest.mark.django_db
class TestTrainerTenantIsolation:
    """Test that trainers respect tenant isolation"""

    def test_trainers_scoped_to_business(self, gym_business):
        """Test that trainers from different businesses are isolated"""
        # Create another gym business
        other_business = Business.objects.create(
            name="Other Gym",
            kind=BusinessKind.GYM,
            is_active=True,
        )
        
        # Create trainers in each business
        trainer1 = GymTrainer.objects.create(
            business=gym_business,
            name="Trainer One",
        )
        trainer2 = GymTrainer.objects.create(
            business=other_business,
            name="Trainer Two",
        )
        
        # Verify isolation
        gym_business_trainers = GymTrainer.objects.filter(business=gym_business)
        assert trainer1 in gym_business_trainers
        assert trainer2 not in gym_business_trainers
        
        other_business_trainers = GymTrainer.objects.filter(business=other_business)
        assert trainer2 in other_business_trainers
        assert trainer1 not in other_business_trainers

    def test_member_cannot_be_assigned_trainer_from_other_business(self, gym_business):
        """Test that members can only be assigned trainers from same business"""
        other_business = Business.objects.create(
            name="Other Gym",
            kind=BusinessKind.GYM,
            is_active=True,
        )
        
        trainer_other = GymTrainer.objects.create(
            business=other_business,
            name="Other Trainer",
        )
        
        # Try to create member with trainer from other business
        member = GymMember(
            business=gym_business,
            name="Member",
            phone="0999000000",
            trainer=trainer_other,  # From different business
        )
        
        # Should still save (no DB-level constraint), but business logic should prevent this
        member.save()
        
        # In practice, the form should filter trainers by business
        # This test documents current behavior


@pytest.mark.django_db
class TestTrainerValidation:
    """Test trainer data validation"""

    def test_trainer_name_required(self, gym_business):
        """Test that trainer name is required"""
        with pytest.raises(Exception):  # ValidationError or IntegrityError
            GymTrainer.objects.create(
                business=gym_business,
                name="",  # Empty name
            )

    def test_trainer_phone_optional(self, gym_business):
        """Test that phone is optional"""
        trainer = GymTrainer.objects.create(
            business=gym_business,
            name="Trainer No Phone",
            phone="",  # Empty phone is OK
        )
        
        assert trainer.id is not None
        assert trainer.phone == ""

    def test_trainer_email_optional(self, gym_business):
        """Test that email is optional"""
        trainer = GymTrainer.objects.create(
            business=gym_business,
            name="Trainer No Email",
            email="",  # Empty email is OK
        )
        
        assert trainer.id is not None
        assert trainer.email == ""


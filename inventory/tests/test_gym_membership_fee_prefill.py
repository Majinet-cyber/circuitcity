"""
Tests for membership fee prefill behavior in gym member forms.

Requirements:
- Create form: prefill with GymSettings.default_membership_price (if set)
- Edit form: show member's existing membership_fee (never overwrite with default)
- Settings form: allow changing default_membership_fee
"""
import pytest
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model
from inventory.models import Business, BusinessKind
from inventory.models_verticals import GymMember, GymSettings

User = get_user_model()


@pytest.fixture
def gym_business(db):
    """Create a gym business with settings"""
    business = Business.objects.create(
        name="Test Gym",
        kind=BusinessKind.GYM,
        is_active=True,
    )
    # Create settings with default fees
    GymSettings.objects.create(
        business=business,
        default_membership_price=Decimal("50000.00"),
        default_trainer_fee=Decimal("30000.00"),
    )
    return business


@pytest.fixture
def manager_user(db, gym_business):
    """Create a manager user"""
    user = User.objects.create_user(
        username="manager",
        email="manager@testgym.com",
        password="testpass123",
        is_staff=True,  # Staff users have manager permissions
    )
    return user


@pytest.mark.django_db
class TestMembershipFeePrefillOnCreate:
    """Test membership fee prefill behavior on member creation"""

    def test_create_form_prefills_default_fee_from_settings(self, client, gym_business, manager_user):
        """Test that member create form prefills with default fee from GymSettings"""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        # Get member add form
        url = reverse("gym:member_add_old")  # Use old form for direct testing
        response = client.get(url)
        
        assert response.status_code == 200
        
        # Check that form has default membership fee prefilled
        form = response.context.get("form")
        assert form is not None
        assert form.initial.get("membership_fee") == Decimal("50000.00")

    def test_create_form_uses_empty_fee_if_no_default_set(self, client, manager_user):
        """Test that form is empty if no default fee is set"""
        # Create business without default fee
        business = Business.objects.create(
            name="Gym No Defaults",
            kind=BusinessKind.GYM,
            is_active=True,
        )
        GymSettings.objects.create(
            business=business,
            default_membership_price=None,  # No default
            default_trainer_fee=None,
        )
        
        from tenants.models import Membership
        Membership.objects.create(
            user=manager_user,
            business=business,
            role="MANAGER",
            status="ACTIVE",
        )
        
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = business.id
        session.save()
        
        url = reverse("gym:member_add_old")
        response = client.get(url)
        
        form = response.context.get("form")
        # Should be None or not set (not prefilled)
        initial_fee = form.initial.get("membership_fee")
        assert initial_fee is None or initial_fee == Decimal("0.00")

    def test_created_member_uses_default_fee(self, client, gym_business, manager_user):
        """Test that newly created member gets default fee from settings"""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:member_add_old")
        data = {
            "name": "New Member",
            "phone": "0999111111",
            "email": "member@test.com",
            "membership_fee": "",  # Empty, should use default
            "trainer_fee": "",
            "mark_as_paid": False,
        }
        response = client.post(url, data)
        
        # Should redirect on success
        assert response.status_code == 302
        
        # Check member was created with default fee
        member = GymMember.objects.get(business=gym_business, phone="0999111111")
        assert member.membership_fee == Decimal("50000.00")

    def test_created_member_uses_custom_fee_if_provided(self, client, gym_business, manager_user):
        """Test that manager can override default fee during creation"""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:member_add_old")
        data = {
            "name": "Custom Fee Member",
            "phone": "0999222222",
            "email": "custom@test.com",
            "membership_fee": "75000.00",  # Custom fee
            "trainer_fee": "",
            "mark_as_paid": False,
        }
        response = client.post(url, data)
        
        assert response.status_code == 302
        
        # Check member was created with custom fee
        member = GymMember.objects.get(business=gym_business, phone="0999222222")
        assert member.membership_fee == Decimal("75000.00")


@pytest.mark.django_db
class TestMembershipFeePrefillOnEdit:
    """Test membership fee prefill behavior on member edit"""

    def test_edit_form_shows_member_existing_fee(self, client, gym_business, manager_user):
        """Test that edit form shows member's existing fee (NOT default from settings)"""
        # Create member with custom fee
        member = GymMember.objects.create(
            business=gym_business,
            name="Existing Member",
            phone="0999333333",
            membership_fee=Decimal("60000.00"),  # Different from default
        )
        
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        # Get edit form
        url = reverse("gym:member_edit", args=[member.id])
        response = client.get(url)
        
        assert response.status_code == 200
        
        # Check that form shows member's existing fee, NOT default
        form = response.context.get("form")
        assert form is not None
        
        # Form should have member's fee in initial data
        initial_fee = form.initial.get("membership_fee")
        assert initial_fee == Decimal("60000.00")  # Member's fee
        assert initial_fee != Decimal("50000.00")  # NOT default

    def test_edit_form_preserves_fee_on_validation_error(self, client, gym_business, manager_user):
        """Test that edit form preserves fee even if validation error occurs"""
        member = GymMember.objects.create(
            business=gym_business,
            name="Member",
            phone="0999444444",
            membership_fee=Decimal("65000.00"),
        )
        
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        # Submit invalid data (e.g., empty name)
        url = reverse("gym:member_edit", args=[member.id])
        data = {
            "name": "",  # Invalid
            "phone": "0999444444",
            "membership_fee": "65000.00",
        }
        response = client.post(url, data)
        
        # Should re-render form with errors (not redirect)
        assert response.status_code == 200
        
        # Fee should still be member's existing fee
        member.refresh_from_db()
        assert member.membership_fee == Decimal("65000.00")

    def test_edit_form_does_not_overwrite_with_default(self, client, gym_business, manager_user):
        """Test that editing member doesn't overwrite fee with default from settings"""
        # Create member with custom fee
        member = GymMember.objects.create(
            business=gym_business,
            name="Member Custom",
            phone="0999555555",
            membership_fee=Decimal("40000.00"),  # Lower than default
        )
        
        # Change default in settings
        settings = GymSettings.objects.get(business=gym_business)
        settings.default_membership_price = Decimal("55000.00")
        settings.save()
        
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        # Edit member (change name only)
        url = reverse("gym:member_edit", args=[member.id])
        data = {
            "name": "Member Custom Updated",
            "phone": "0999555555",
            "email": "",
            "trainer": "",
            "notes": "",
            # Don't include membership_fee in POST (form might not include it)
        }
        response = client.post(url, data)
        
        # Member fee should remain unchanged
        member.refresh_from_db()
        assert member.membership_fee == Decimal("40000.00")  # Original fee
        assert member.membership_fee != Decimal("55000.00")  # NOT new default


@pytest.mark.django_db
class TestGymSettingsDefaultFee:
    """Test changing default membership fee in GymSettings"""

    def test_settings_page_displays_default_fee(self, client, gym_business, manager_user):
        """Test that gym settings page shows default membership fee"""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:settings")
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode()
        
        # Should contain default fee field
        assert "default_membership_price" in content or "Default Membership Fee" in content

    def test_update_default_fee_in_settings(self, client, gym_business, manager_user):
        """Test updating default membership fee in settings"""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:settings")
        data = {
            "support_phone": "",
            "support_email": "",
            "default_membership_price": "60000.00",  # New default
            "default_trainer_fee": "30000.00",
            "arrears_message": "Please renew.",
        }
        response = client.post(url, data)
        
        # Should redirect on success
        assert response.status_code == 302
        
        # Verify settings updated
        settings = GymSettings.objects.get(business=gym_business)
        assert settings.default_membership_price == Decimal("60000.00")

    def test_changed_default_fee_applies_to_new_members_only(self, client, gym_business, manager_user):
        """Test that changing default fee affects only new members (not existing)"""
        # Create member with current default
        existing_member = GymMember.objects.create(
            business=gym_business,
            name="Existing",
            phone="0999666666",
            membership_fee=Decimal("50000.00"),  # Current default
        )
        
        # Change default fee in settings
        settings = GymSettings.objects.get(business=gym_business)
        settings.default_membership_price = Decimal("70000.00")
        settings.save()
        
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        # Create new member (should get new default)
        url = reverse("gym:member_add_old")
        data = {
            "name": "New Member",
            "phone": "0999777777",
            "email": "",
            "membership_fee": "",  # Use default
            "trainer_fee": "",
            "mark_as_paid": False,
        }
        client.post(url, data)
        
        # New member should have new default
        new_member = GymMember.objects.get(phone="0999777777")
        assert new_member.membership_fee == Decimal("70000.00")
        
        # Existing member should be unchanged
        existing_member.refresh_from_db()
        assert existing_member.membership_fee == Decimal("50000.00")


@pytest.mark.django_db
class TestTrainerFeePrefill:
    """Test trainer fee prefill behavior (similar to membership fee)"""

    def test_create_form_prefills_default_trainer_fee(self, client, gym_business, manager_user):
        """Test that trainer fee is prefilled with default from settings"""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:member_add_old")
        response = client.get(url)
        
        form = response.context.get("form")
        assert form.initial.get("trainer_fee") == Decimal("30000.00")

    def test_edit_form_shows_member_existing_trainer_fee(self, client, gym_business, manager_user):
        """Test that edit form shows member's existing trainer fee"""
        member = GymMember.objects.create(
            business=gym_business,
            name="Member with Trainer",
            phone="0999888888",
            trainer_fee=Decimal("35000.00"),  # Custom trainer fee
        )
        
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        url = reverse("gym:member_edit", args=[member.id])
        response = client.get(url)
        
        form = response.context.get("form")
        assert form.initial.get("trainer_fee") == Decimal("35000.00")


@pytest.mark.django_db
class TestCurrencyFormatting:
    """Test that currency is formatted consistently"""

    def test_membership_fee_displays_as_decimal(self, client, gym_business, manager_user):
        """Test that membership fee displays with proper decimal formatting"""
        member = GymMember.objects.create(
            business=gym_business,
            name="Member",
            phone="0999999999",
            membership_fee=Decimal("50000.00"),
        )
        
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = gym_business.id
        session.save()
        
        # View member detail page
        url = reverse("gym:member_detail", args=[member.id])
        response = client.get(url)
        
        # Fee should be displayed somewhere (exact format varies by template)
        content = response.content.decode()
        # Should contain the fee value in some form
        assert "50000" in content or "50,000" in content


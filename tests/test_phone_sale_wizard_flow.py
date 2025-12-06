"""
Tests for Phone Sale Wizard - Model/Variant Flow

Ensures that:
1. Step 2: Model selection properly stores the selected model
2. Step 3: Variant selection uses the CORRECT model from Step 2
3. Title on Step 3 shows the model actually selected (e.g., "Pop 10" not "Spark 40")
4. "Start Over" properly clears wizard state
"""
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model

from tenants.models import Business, Membership
from inventory.models_phone_products import PhoneProductCatalog
from inventory.business_kinds import BusinessKind
from inventory.phone_catalog_seed import seed_phone_catalog

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def phone_business():
    """Create a PHONES business with seeded catalog."""
    business = Business.objects.create(
        name="Test Phone Shop",
        slug="test-phone-shop",
        status="ACTIVE",
        kind=BusinessKind.PHONES
    )
    # Seed catalog with TECNO Pop 10 and Spark 40
    seed_phone_catalog(business)
    return business


@pytest.fixture
def manager_user(phone_business):
    """Create a manager user for the phone business."""
    user = User.objects.create_user(
        username="manager@test.com",
        email="manager@test.com",
        password="testpass123"
    )
    Membership.objects.create(
        user=user,
        business=phone_business,
        role="MANAGER",
        status="ACTIVE"
    )
    return user


class TestPhoneSaleWizardModelVariantFlow:
    """Test the wizard correctly tracks selected model through all steps."""
    
    def test_wizard_step1_brand_selection(self, client, manager_user, phone_business):
        """Test Step 1: Brand selection works."""
        client.force_login(manager_user)
        client.session["active_business_id"] = phone_business.id
        client.session.save()
        
        url = reverse("inventory:phone_sale_wizard")
        response = client.get(url)
        
        assert response.status_code == 200
        assert "Step 1" in response.content.decode()
        assert "Choose Brand" in response.content.decode()
        assert "TECNO" in response.content.decode()
    
    def test_wizard_step2_shows_correct_models(self, client, manager_user, phone_business):
        """Test Step 2: After selecting TECNO, shows TECNO models."""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = phone_business.id
        session["sale_wizard_brand"] = "TECNO"
        session["sale_wizard_step"] = 2
        session.save()
        
        url = reverse("inventory:phone_sale_wizard") + "?step=2"
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode()
        
        # Should show "Step 2: Choose TECNO Model"
        assert "Step 2" in content
        assert "TECNO" in content
        
        # Should show TECNO models
        assert "Pop 10" in content
        assert "Spark 40" in content
    
    def test_wizard_step2_post_saves_correct_model(self, client, manager_user, phone_business):
        """Test Step 2: POSTing a model selection saves the correct model name."""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = phone_business.id
        session["sale_wizard_brand"] = "TECNO"
        session["sale_wizard_step"] = 2
        session.save()
        
        # Find a Pop 10 variant
        pop10 = PhoneProductCatalog.objects.filter(
            business=phone_business,
            brand="TECNO",
            model_name="Pop 10"
        ).first()
        assert pop10 is not None, "Pop 10 should exist in catalog"
        
        url = reverse("inventory:phone_sale_wizard") + "?step=2"
        response = client.post(url, {
            "product_id": pop10.id,
        })
        
        # Should redirect to step 3
        assert response.status_code == 302
        assert "step=3" in response.url
        
        # Session should have correct model name
        session = client.session
        assert session.get("sale_wizard_model") == "Pop 10"
        assert session.get("sale_wizard_product_id") == str(pop10.id)
    
    def test_wizard_step3_uses_selected_model_in_title(self, client, manager_user, phone_business):
        """
        CRITICAL TEST: Step 3 title must use the model selected in Step 2.
        If user chose Pop 10 in Step 2, Step 3 should say "Choose TECNO Pop 10 Variant",
        NOT "Choose TECNO Spark 40 Variant".
        """
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = phone_business.id
        session["sale_wizard_brand"] = "TECNO"
        session["sale_wizard_model"] = "Pop 10"  # User chose Pop 10
        session["sale_wizard_step"] = 3
        
        # Store a Pop 10 product_id
        pop10 = PhoneProductCatalog.objects.filter(
            business=phone_business,
            brand="TECNO",
            model_name="Pop 10"
        ).first()
        session["sale_wizard_product_id"] = pop10.id
        session.save()
        
        url = reverse("inventory:phone_sale_wizard") + "?step=3"
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode()
        
        # Must show "TECNO Pop 10 Variant" in title
        assert "Step 3" in content
        assert "Pop 10" in content
        
        # Must NOT show "Spark 40" in the title
        # (It's OK if Spark 40 appears elsewhere, but not in the Step 3 title)
        assert "Choose TECNO Pop 10 Variant" in content or "Pop 10 Variant" in content
    
    def test_wizard_step3_shows_only_selected_model_variants(self, client, manager_user, phone_business):
        """Test Step 3: Variants shown are only for the selected model."""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = phone_business.id
        session["sale_wizard_brand"] = "TECNO"
        session["sale_wizard_model"] = "Pop 10"
        session["sale_wizard_step"] = 3
        
        pop10 = PhoneProductCatalog.objects.filter(
            business=phone_business,
            brand="TECNO",
            model_name="Pop 10"
        ).first()
        session["sale_wizard_product_id"] = pop10.id
        session.save()
        
        url = reverse("inventory:phone_sale_wizard") + "?step=3"
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode()
        
        # Get all Pop 10 variants
        pop10_variants = PhoneProductCatalog.objects.filter(
            business=phone_business,
            brand="TECNO",
            model_name="Pop 10"
        )
        
        # All Pop 10 variants should be present
        for variant in pop10_variants:
            assert variant.variant_label in content
        
        # Context should have correct model
        assert response.context["model"] == "Pop 10"
        assert response.context["brand"] == "TECNO"
    
    def test_wizard_step3_without_session_redirects(self, client, manager_user, phone_business):
        """Test Step 3: Direct access without session state redirects to Step 1."""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = phone_business.id
        # Deliberately don't set wizard state
        session.save()
        
        url = reverse("inventory:phone_sale_wizard") + "?step=3"
        response = client.get(url)
        
        # Should redirect back to step 1 or 2
        assert response.status_code == 302
    
    def test_wizard_reset_clears_all_state(self, client, manager_user, phone_business):
        """Test wizard reset clears all session state."""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = phone_business.id
        session["sale_wizard_brand"] = "TECNO"
        session["sale_wizard_model"] = "Pop 10"
        session["sale_wizard_variant"] = "2+64"
        session["sale_wizard_step"] = 3
        session.save()
        
        # Reset wizard
        url = reverse("inventory:phone_sale_wizard_reset")
        response = client.post(url)
        
        assert response.status_code == 302
        
        # Session should be cleared
        session = client.session
        assert "sale_wizard_brand" not in session
        assert "sale_wizard_model" not in session
        assert "sale_wizard_variant" not in session
        assert "sale_wizard_step" not in session
    
    def test_full_wizard_flow_pop10(self, client, manager_user, phone_business):
        """Test full wizard flow: TECNO → Pop 10 → variant → confirm."""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = phone_business.id
        session.save()
        
        # Step 1: Choose TECNO
        url1 = reverse("inventory:phone_sale_wizard")
        response1 = client.post(url1, {"brand": "TECNO"})
        assert response1.status_code == 302
        assert "step=2" in response1.url
        
        # Session should have brand
        session = client.session
        assert session.get("sale_wizard_brand") == "TECNO"
        
        # Step 2: Choose Pop 10
        pop10 = PhoneProductCatalog.objects.filter(
            business=phone_business,
            brand="TECNO",
            model_name="Pop 10"
        ).first()
        
        url2 = reverse("inventory:phone_sale_wizard") + "?step=2"
        response2 = client.post(url2, {
            "product_id": pop10.id,
        })
        assert response2.status_code == 302
        assert "step=3" in response2.url
        
        # Session should have model = "Pop 10"
        session = client.session
        assert session.get("sale_wizard_model") == "Pop 10"
        
        # Step 3: Verify title shows Pop 10
        url3 = reverse("inventory:phone_sale_wizard") + "?step=3"
        response3 = client.get(url3)
        assert response3.status_code == 200
        content3 = response3.content.decode()
        
        # CRITICAL: Title must say "Pop 10", not "Spark 40"
        assert "Pop 10" in content3
        assert response3.context["model"] == "Pop 10"
        assert response3.context["step_title"] == "Step 3: Choose TECNO Pop 10 Variant"
    
    def test_full_wizard_flow_spark40(self, client, manager_user, phone_business):
        """Test full wizard flow: TECNO → Spark 40 → variant → confirm."""
        client.force_login(manager_user)
        session = client.session
        session["active_business_id"] = phone_business.id
        session.save()
        
        # Step 1: Choose TECNO
        url1 = reverse("inventory:phone_sale_wizard")
        response1 = client.post(url1, {"brand": "TECNO"})
        assert response1.status_code == 302
        
        # Step 2: Choose Spark 40
        spark40 = PhoneProductCatalog.objects.filter(
            business=phone_business,
            brand="TECNO",
            model_name="Spark 40"
        ).first()
        
        url2 = reverse("inventory:phone_sale_wizard") + "?step=2"
        response2 = client.post(url2, {
            "product_id": spark40.id,
        })
        assert response2.status_code == 302
        assert "step=3" in response2.url
        
        # Session should have model = "Spark 40"
        session = client.session
        assert session.get("sale_wizard_model") == "Spark 40"
        
        # Step 3: Verify title shows Spark 40
        url3 = reverse("inventory:phone_sale_wizard") + "?step=3"
        response3 = client.get(url3)
        assert response3.status_code == 200
        
        # CRITICAL: Title must say "Spark 40", not "Pop 10"
        assert response3.context["model"] == "Spark 40"
        assert response3.context["step_title"] == "Step 3: Choose TECNO Spark 40 Variant"


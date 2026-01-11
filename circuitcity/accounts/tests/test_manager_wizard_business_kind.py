"""
Regression tests for manager signup wizard business_kind persistence.

BUG FIX: Ensure business_kind selected in Step 2 is:
1. Displayed correctly in Step 3 summary (not "—" or wrong value)
2. Saved correctly to the Business model
3. Routes to correct dashboard (not /verticals/none)

CRITICAL: Farm, Welding, Hardware, and all other business kinds must work.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TransactionTestCase
from django.urls import reverse
from tenants.models import Business, Membership

User = get_user_model()


@pytest.mark.django_db
class TestManagerWizardBusinessKindPersistence:
    """Test business_kind is correctly persisted throughout wizard flow."""

    def test_step2_to_step3_farm_persistence(self):
        """
        CRITICAL: Selecting 'farm' in Step 2 must show 'Farm Manager' in Step 3.
        
        BUG: Previously showed "—" or wrong value due to hardcoded template.
        """
        client = Client()
        
        # Step 1: Account details
        response = client.post(
            reverse("accounts:signup_manager") + "?step=1",
            {
                "action": "next",
                "email": "farmtest@test.com",
                "full_name": "Farm Test User",
                "password1": "SecurePass123!@#",
                "password2": "SecurePass123!@#",
            },
        )
        assert response.status_code == 302, "Step 1 should redirect to step 2"
        assert "step=2" in response.url
        
        # Step 2: Store basics with FARM selected
        response = client.post(
            reverse("accounts:signup_manager") + "?step=2",
            {
                "action": "next",
                "business_name": "My Farm Store",
                "business_kind": "farm",  # CRITICAL: farm selected
                "subdomain": "",
            },
        )
        assert response.status_code == 302, "Step 2 should redirect to step 3"
        assert "step=3" in response.url
        
        # Step 3: Review & Create - verify farm is displayed
        response = client.get(reverse("accounts:signup_manager") + "?step=3")
        assert response.status_code == 200
        
        # CRITICAL: Step 3 must show "Farm Manager", not "—"
        content = response.content.decode("utf-8")
        assert "Farm Manager" in content, "Step 3 MUST display 'Farm Manager' for farm business_kind"
        assert "My Farm Store" in content, "Store name should be shown"
        
        # Verify the summary context has correct data
        summary = response.context["summary"]
        assert summary["business_kind"] == "farm", "Summary must contain business_kind='farm'"
        assert summary["business_kind_display"] == "Farm Manager", "Display name must be 'Farm Manager'"

    def test_step2_to_step3_welding_persistence(self):
        """
        CRITICAL: Selecting 'welding' in Step 2 must show 'Welding Workshop' in Step 3.
        """
        client = Client()
        
        # Step 1
        client.post(
            reverse("accounts:signup_manager") + "?step=1",
            {
                "action": "next",
                "email": "weldtest@test.com",
                "full_name": "Weld Test User",
                "password1": "SecurePass123!@#",
                "password2": "SecurePass123!@#",
            },
        )
        
        # Step 2: Welding selected
        client.post(
            reverse("accounts:signup_manager") + "?step=2",
            {
                "action": "next",
                "business_name": "My Welding Shop",
                "business_kind": "welding",  # CRITICAL: welding selected
                "subdomain": "",
            },
        )
        
        # Step 3: Verify welding display
        response = client.get(reverse("accounts:signup_manager") + "?step=3")
        content = response.content.decode("utf-8")
        
        assert "Welding Workshop" in content, "Step 3 MUST display 'Welding Workshop'"
        assert "My Welding Shop" in content
        
        summary = response.context["summary"]
        assert summary["business_kind"] == "welding"
        assert summary["business_kind_display"] == "Welding Workshop"

    def test_step2_to_step3_hardware_persistence(self):
        """
        CRITICAL: Selecting 'hardware' in Step 2 must show 'Hardware & General Dealers' in Step 3.
        """
        client = Client()
        
        # Step 1
        client.post(
            reverse("accounts:signup_manager") + "?step=1",
            {
                "action": "next",
                "email": "hwtest@test.com",
                "full_name": "Hardware Test User",
                "password1": "SecurePass123!@#",
                "password2": "SecurePass123!@#",
            },
        )
        
        # Step 2: Hardware selected
        client.post(
            reverse("accounts:signup_manager") + "?step=2",
            {
                "action": "next",
                "business_name": "My Hardware Store",
                "business_kind": "hardware",
                "subdomain": "",
            },
        )
        
        # Step 3: Verify hardware display
        response = client.get(reverse("accounts:signup_manager") + "?step=3")
        content = response.content.decode("utf-8")
        
        assert "Hardware & General Dealers" in content
        summary = response.context["summary"]
        assert summary["business_kind"] == "hardware"
        assert summary["business_kind_display"] == "Hardware & General Dealers"

    @pytest.mark.parametrize(
        "business_kind,expected_display",
        [
            ("phones", "Phones & Electronics"),
            ("liquor", "Liquor / Bar"),
            ("grocery", "Grocery / General"),
            ("pharmacy", "Cosmetics & Pharmacy"),
            ("clothing", "Clothing"),
            ("gym", "Gym / Fitness"),
            ("cement", "Cement / Building Materials"),
            ("farm", "Farm Manager"),
            ("welding", "Welding Workshop"),
            ("hardware", "Hardware & General Dealers"),
        ],
    )
    def test_all_business_kinds_display_correctly(self, business_kind, expected_display):
        """
        CRITICAL: ALL business kinds must display correctly in Step 3.
        
        This prevents regressions where new kinds are added but templates aren't updated.
        """
        client = Client()
        
        # Step 1
        client.post(
            reverse("accounts:signup_manager") + "?step=1",
            {
                "action": "next",
                "email": f"{business_kind}test@test.com",
                "full_name": "Test User",
                "password1": "SecurePass123!@#",
                "password2": "SecurePass123!@#",
            },
        )
        
        # Step 2: Select this business_kind
        client.post(
            reverse("accounts:signup_manager") + "?step=2",
            {
                "action": "next",
                "business_name": f"My {business_kind.title()} Store",
                "business_kind": business_kind,
                "subdomain": "",
            },
        )
        
        # Step 3: Verify display
        response = client.get(reverse("accounts:signup_manager") + "?step=3")
        content = response.content.decode("utf-8")
        
        assert expected_display in content, (
            f"Step 3 must display '{expected_display}' for business_kind='{business_kind}', "
            f"but it was not found in the page content."
        )
        
        summary = response.context["summary"]
        assert summary["business_kind"] == business_kind
        assert summary["business_kind_display"] == expected_display


class TestManagerWizardBusinessKindCreation(TransactionTestCase):
    """Test Business model is created with correct business_kind."""

    def test_created_business_has_farm_kind(self):
        """
        CRITICAL: Completing wizard with 'farm' must create Business with business_kind='farm'.
        """
        client = Client()
        
        # Complete all steps
        client.post(
            reverse("accounts:signup_manager") + "?step=1",
            {
                "action": "next",
                "email": "farmcreate@test.com",
                "full_name": "Farm Creator",
                "password1": "SecurePass123!@#",
                "password2": "SecurePass123!@#",
            },
        )
        
        client.post(
            reverse("accounts:signup_manager") + "?step=2",
            {
                "action": "next",
                "business_name": "Farm Creation Test",
                "business_kind": "farm",
                "subdomain": "",
            },
        )
        
        # Step 3: Create the store
        response = client.post(
            reverse("accounts:signup_manager") + "?step=3",
            {
                "action": "create",
                "agree": "on",
            },
            follow=True,
        )
        
        # Verify redirect was successful
        assert response.status_code == 200, "Creation should succeed"
        
        # Verify Business was created with correct business_kind
        business = Business.objects.filter(name="Farm Creation Test").first()
        assert business is not None, "Business should be created"
        assert business.business_kind == "farm", (
            f"Business.business_kind MUST be 'farm', got '{business.business_kind}'"
        )
        
        # Verify user was created and assigned
        user = User.objects.filter(email="farmcreate@test.com").first()
        assert user is not None
        membership = Membership.objects.filter(user=user, business=business).first()
        assert membership is not None
        assert membership.role == "MANAGER"

    def test_created_business_has_welding_kind(self):
        """
        CRITICAL: Completing wizard with 'welding' must create Business with business_kind='welding'.
        """
        client = Client()
        
        client.post(
            reverse("accounts:signup_manager") + "?step=1",
            {
                "action": "next",
                "email": "weldcreate@test.com",
                "full_name": "Weld Creator",
                "password1": "SecurePass123!@#",
                "password2": "SecurePass123!@#",
            },
        )
        
        client.post(
            reverse("accounts:signup_manager") + "?step=2",
            {
                "action": "next",
                "business_name": "Welding Creation Test",
                "business_kind": "welding",
                "subdomain": "",
            },
        )
        
        response = client.post(
            reverse("accounts:signup_manager") + "?step=3",
            {
                "action": "create",
                "agree": "on",
            },
            follow=True,
        )
        
        assert response.status_code == 200
        business = Business.objects.filter(name="Welding Creation Test").first()
        assert business is not None
        assert business.business_kind == "welding"

    def test_post_create_redirect_not_verticals_none_for_farm(self):
        """
        CRITICAL: After creating a farm business, redirect should NOT go to /verticals/none/.
        
        BUG: Previously new business kinds would redirect to generic /verticals/none/ page.
        FIX: Must route to the correct vertical dashboard.
        """
        client = Client()
        
        client.post(
            reverse("accounts:signup_manager") + "?step=1",
            {
                "action": "next",
                "email": "farmredirect@test.com",
                "full_name": "Farm Redirect Test",
                "password1": "SecurePass123!@#",
                "password2": "SecurePass123!@#",
            },
        )
        
        client.post(
            reverse("accounts:signup_manager") + "?step=2",
            {
                "action": "next",
                "business_name": "Farm Redirect Test Store",
                "business_kind": "farm",
                "subdomain": "",
            },
        )
        
        response = client.post(
            reverse("accounts:signup_manager") + "?step=3",
            {
                "action": "create",
                "agree": "on",
            },
            follow=True,
        )
        
        # Check final URL after all redirects
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else response.request["PATH_INFO"]
        
        assert "/verticals/none" not in final_url, (
            f"CRITICAL: Farm business should NOT redirect to /verticals/none/. "
            f"Got: {final_url}"
        )
        
        # Should redirect to farm dashboard or inventory dashboard
        assert (
            "/verticals/farm" in final_url
            or "/inventory/dashboard" in final_url
            or "/dashboard" in final_url
        ), f"Should redirect to valid dashboard, got: {final_url}"

    def test_post_create_redirect_not_verticals_none_for_welding(self):
        """
        CRITICAL: After creating a welding business, redirect should NOT go to /verticals/none/.
        """
        client = Client()
        
        client.post(
            reverse("accounts:signup_manager") + "?step=1",
            {
                "action": "next",
                "email": "weldredirect@test.com",
                "full_name": "Weld Redirect Test",
                "password1": "SecurePass123!@#",
                "password2": "SecurePass123!@#",
            },
        )
        
        client.post(
            reverse("accounts:signup_manager") + "?step=2",
            {
                "action": "next",
                "business_name": "Welding Redirect Test Store",
                "business_kind": "welding",
                "subdomain": "",
            },
        )
        
        response = client.post(
            reverse("accounts:signup_manager") + "?step=3",
            {
                "action": "create",
                "agree": "on",
            },
            follow=True,
        )
        
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else response.request["PATH_INFO"]
        
        assert "/verticals/none" not in final_url, (
            f"CRITICAL: Welding business should NOT redirect to /verticals/none/. "
            f"Got: {final_url}"
        )


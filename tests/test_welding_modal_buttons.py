"""
Regression tests for Welding Quote Modal Button Fix (2026-01-19)

CRITICAL BUG FIX: Buttons "Add Material", "Add Cost", etc. were blinking but not opening modals.

ROOT CAUSE: Bootstrap's automatic data-attribute initialization wasn't capturing
buttons that trigger modals moved by the modal portal script.

SOLUTION: Explicit JavaScript initialization of modal triggers in quote_detail.html.

These tests verify:
1. Explicit modal initialization script exists
2. Modal buttons and targets are present
3. AJAX endpoints return 200
4. No regressions across other verticals
"""
import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestWeldingQuoteModalButtonsRegression:
    """
    Regression tests for welding quote modal buttons.
    Ensures buttons reliably open modals after explicit initialization fix.
    """

    @pytest.fixture
    def welding_business(self, db):
        """Create a welding business."""
        from tenants.models import Business
        from inventory.business_kinds import BusinessKind
        
        business = Business.objects.create(
            name="Test Welding Modal Buttons",
            kind=BusinessKind.WELDING,
            is_active=True,
        )
        return business

    @pytest.fixture
    def welding_manager(self, db, welding_business):
        """Create manager user with welding business."""
        from tenants.models import Membership
        
        user = User.objects.create_user(
            username="weld_modal_mgr",
            email="weld_modal_mgr@test.com",
            password="testpass123",
        )
        Membership.objects.create(
            user=user,
            business=welding_business,
            role="manager",
        )
        return user

    @pytest.fixture
    def authenticated_client(self, client, welding_manager, welding_business):
        """Client authenticated as welding manager."""
        client.force_login(welding_manager)
        session = client.session
        session['active_business_id'] = welding_business.id
        session.save()
        return client

    def test_welding_quote_modal_buttons_have_explicit_handlers(self, authenticated_client, welding_business):
        """
        Welding quote detail page must include explicit JavaScript to initialize modal buttons.
        This ensures buttons work even if Bootstrap's automatic initialization fails.
        
        CRITICAL: Verifies the fix for "buttons blink but do nothing" bug.
        """
        from inventory.models_welding import WeldingQuote
        
        quote = WeldingQuote.objects.create(
            business=welding_business,
            customer_name="Test Customer Modal Init",
            status="draft",
        )
        
        response = authenticated_client.get(f"/verticals/welding/quotes/{quote.id}/")
        assert response.status_code == 200, "Quote detail page must return 200"
        
        html = response.content.decode('utf-8')
        
        # Verify explicit modal initialization script exists
        assert 'bootstrap.Modal' in html, \
            "Explicit Modal initialization missing - buttons won't work!"
        
        # Verify modal trigger selection
        assert "querySelectorAll('[data-bs-toggle=\"modal\"]')" in html or \
               'querySelectorAll(\'[data-bs-toggle="modal"]\')' in html, \
               "Explicit modal trigger selection missing"
        
        # Verify modal show() call
        assert 'modalInstance.show()' in html, \
            "Explicit modal show() call missing - modals won't open!"
        
        # Verify defensive error logging
        assert 'console.error' in html or 'console.warn' in html, \
            "No error logging for debugging modal issues"

    def test_welding_quote_add_material_button_wiring(self, authenticated_client, welding_business):
        """
        Verify 'Add Material' button has correct data-bs-toggle and data-bs-target.
        Also verify the target modal exists in the HTML.
        """
        from inventory.models_welding import WeldingQuote, WeldingMaterial
        
        # Create a material so it appears in the modal
        WeldingMaterial.objects.create(
            business=welding_business,
            code="ROD_6013",
            name="Welding Rod 6013",
            category="electrodes",
            unit="kg",
            price_mwk=5000,
        )
        
        quote = WeldingQuote.objects.create(
            business=welding_business,
            customer_name="Test Customer Material",
            status="draft",
        )
        
        response = authenticated_client.get(f"/verticals/welding/quotes/{quote.id}/")
        assert response.status_code == 200
        
        html = response.content.decode('utf-8')
        
        # Verify "Add Material" button exists with correct attributes
        assert 'data-bs-toggle="modal"' in html, \
            "Add Material button missing data-bs-toggle"
        assert 'data-bs-target="#materialPickerModal"' in html, \
            "Add Material button missing correct data-bs-target"
        
        # Verify material picker modal exists
        assert 'id="materialPickerModal"' in html, \
            "Material picker modal missing from HTML"
        assert 'class="modal fade"' in html, \
            "Modal missing Bootstrap classes"
        
        # Verify materials are loaded in modal
        assert 'Welding Rod 6013' in html, \
            "Materials not loaded in modal"

    def test_welding_quote_add_cost_button_wiring(self, authenticated_client, welding_business):
        """
        Verify 'Add Cost' button has correct data-bs-toggle and data-bs-target.
        Also verify the target modal exists in the HTML.
        """
        from inventory.models_welding import WeldingQuote
        
        quote = WeldingQuote.objects.create(
            business=welding_business,
            customer_name="Test Customer Cost",
            status="draft",
        )
        
        response = authenticated_client.get(f"/verticals/welding/quotes/{quote.id}/")
        assert response.status_code == 200
        
        html = response.content.decode('utf-8')
        
        # Verify "Add Cost" button exists with correct attributes
        assert 'data-bs-target="#costPickerModal"' in html, \
            "Add Cost button missing correct data-bs-target"
        
        # Verify cost picker modal exists
        assert 'id="costPickerModal"' in html, \
            "Cost picker modal missing from HTML"
        
        # Verify modal has form with correct fields
        assert 'name="cost_type"' in html, \
            "Cost form missing cost_type field"
        assert 'name="amount"' in html, \
            "Cost form missing amount field"
        
        # Verify cost types are in select options
        assert '<option value="labour">Labour</option>' in html
        assert '<option value="transport">Transport</option>' in html
        assert '<option value="profit">Profit/Markup</option>' in html

    def test_welding_quote_ajax_add_line_item_returns_200(self, authenticated_client, welding_business):
        """
        Verify AJAX endpoint for adding line items returns 200 and success:true.
        This ensures the modal submission actually works.
        """
        from inventory.models_welding import WeldingQuote, WeldingMaterial
        
        material = WeldingMaterial.objects.create(
            business=welding_business,
            code="STEEL_10",
            name="Steel Bar 10mm",
            category="steel_bars",
            unit="m",
            price_mwk=3000,
        )
        
        quote = WeldingQuote.objects.create(
            business=welding_business,
            customer_name="Test Customer AJAX",
            status="draft",
        )
        
        # Test add line item endpoint
        response = authenticated_client.post(
            f"/verticals/welding/quotes/{quote.id}/add-line-item/",
            {
                "material_id": material.id,
                "quantity": "10",
                "unit_price": "3000",
            }
        )
        
        assert response.status_code == 200, \
            f"Add line item endpoint failed: {response.status_code}"
        
        data = response.json()
        assert data["success"] is True, \
            f"Add line item returned success:false - {data.get('error', 'no error message')}"
        
        # Verify line item was created
        assert "line_item" in data
        assert data["line_item"]["material_name"] == "Steel Bar 10mm"
        assert data["line_item"]["quantity"] == "10"

    def test_welding_quote_ajax_add_cost_returns_200(self, authenticated_client, welding_business):
        """
        Verify AJAX endpoint for adding costs returns 200 and success:true.
        This ensures the cost modal submission actually works.
        """
        from inventory.models_welding import WeldingQuote
        
        quote = WeldingQuote.objects.create(
            business=welding_business,
            customer_name="Test Customer Cost AJAX",
            status="draft",
        )
        
        # Test add cost endpoint
        response = authenticated_client.post(
            f"/verticals/welding/quotes/{quote.id}/add-cost/",
            {
                "cost_type": "labour",
                "description": "Welding work",
                "amount": "15000",
            }
        )
        
        assert response.status_code == 200, \
            f"Add cost endpoint failed: {response.status_code}"
        
        data = response.json()
        assert data["success"] is True, \
            f"Add cost returned success:false - {data.get('error', 'no error message')}"
        
        # Verify cost was created
        assert "cost" in data
        assert data["cost"]["cost_type"] == "labour"
        assert data["cost"]["amount"] == "15000"

    def test_welding_quote_non_draft_has_no_modal_buttons(self, authenticated_client, welding_business):
        """
        Verify that non-draft quotes (accepted/sent) don't render modal buttons.
        This ensures the is_editable check works correctly.
        """
        from inventory.models_welding import WeldingQuote, WeldingQuoteStatus
        
        quote = WeldingQuote.objects.create(
            business=welding_business,
            customer_name="Test Customer Locked",
            status=WeldingQuoteStatus.ACCEPTED,
        )
        
        response = authenticated_client.get(f"/verticals/welding/quotes/{quote.id}/")
        assert response.status_code == 200
        
        html = response.content.decode('utf-8')
        
        # Modal buttons should NOT exist
        # Note: We're checking for the specific context where button + modal target appear together
        # Individual words like "Add" might appear in other contexts
        add_material_button_pattern = 'data-bs-target="#materialPickerModal"'
        assert add_material_button_pattern not in html, \
            "Add Material button should not exist for non-draft quotes"
        
        # Modals should NOT exist
        assert 'id="materialPickerModal"' not in html, \
            "Material picker modal should not exist for non-draft quotes"
        assert 'id="costPickerModal"' not in html, \
            "Cost picker modal should not exist for non-draft quotes"

    def test_welding_quote_modals_have_test_hooks(self, authenticated_client, welding_business):
        """
        Verify modals have stable IDs for E2E testing.
        This ensures Cypress/Playwright tests can select modals reliably.
        """
        from inventory.models_welding import WeldingQuote
        
        quote = WeldingQuote.objects.create(
            business=welding_business,
            customer_name="Test Customer Hooks",
            status="draft",
        )
        
        response = authenticated_client.get(f"/verticals/welding/quotes/{quote.id}/")
        assert response.status_code == 200
        
        html = response.content.decode('utf-8')
        
        # Verify stable modal IDs (test hooks)
        assert 'id="materialPickerModal"' in html, \
            "Material modal missing stable ID for E2E tests"
        assert 'id="costPickerModal"' in html, \
            "Cost modal missing stable ID for E2E tests"
        
        # Verify search input has ID (for E2E testing)
        assert 'id="materialSearch"' in html, \
            "Material search input missing ID for E2E tests"
        
        # Verify cost form has ID (for E2E testing)
        assert 'id="costForm"' in html, \
            "Cost form missing ID for E2E tests"


@pytest.mark.django_db
class TestWeldingQuoteModalNoRegressions:
    """
    Verify that the modal button fix doesn't break other verticals or pages.
    """

    def test_other_verticals_still_work(self, client):
        """
        Smoke test: Other vertical dashboards still return 200.
        This ensures the modal fix didn't introduce global breakage.
        """
        from tenants.models import Business, Membership
        from inventory.business_kinds import BusinessKind
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        
        # Test multiple verticals
        verticals_to_test = [
            (BusinessKind.PHONES, "/verticals/phones/dashboard/"),
            (BusinessKind.CEMENT, "/verticals/cement/dashboard/"),
            (BusinessKind.CLOTHING, "/verticals/clothing/dashboard/"),
        ]
        
        for kind, url in verticals_to_test:
            # Create business and user
            business = Business.objects.create(
                name=f"Test {kind} Business",
                kind=kind,
                is_active=True,
            )
            
            user = User.objects.create_user(
                username=f"test_{kind}",
                email=f"test_{kind}@test.com",
                password="testpass123",
            )
            
            Membership.objects.create(
                user=user,
                business=business,
                role="manager",
            )
            
            # Login and test
            client.force_login(user)
            session = client.session
            session['active_business_id'] = business.id
            session.save()
            
            response = client.get(url)
            assert response.status_code == 200, \
                f"{kind} dashboard broken after welding modal fix!"
            
            # Cleanup
            client.logout()

    def test_base_html_modal_portal_still_works(self, client):
        """
        Verify base.html modal portal (#cc-modal-root) still exists.
        This ensures the previous z-index fix is still in place.
        """
        from tenants.models import Business, Membership
        from inventory.business_kinds import BusinessKind
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        
        business = Business.objects.create(
            name="Test Modal Portal",
            kind=BusinessKind.WELDING,
            is_active=True,
        )
        
        user = User.objects.create_user(
            username="test_portal",
            email="test_portal@test.com",
            password="testpass123",
        )
        
        Membership.objects.create(
            user=user,
            business=business,
            role="manager",
        )
        
        client.force_login(user)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        response = client.get("/verticals/welding/dashboard/")
        assert response.status_code == 200
        
        html = response.content.decode('utf-8')
        
        # Verify modal portal exists
        assert 'id="cc-modal-root"' in html, \
            "Modal portal missing - previous z-index fix broken!"
        
        # Verify modal portal script exists
        assert 'cc-modal-root' in html.lower(), \
            "Modal portal script missing from base.html"


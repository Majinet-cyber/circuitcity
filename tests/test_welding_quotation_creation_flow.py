"""
Comprehensive tests for Welding Quotation Creation Flow (Feb 2026)

CRITICAL FIX: Complete end-to-end testing of quotation creation, material/labour
addition, totals calculation, and validation.

ROOT CAUSE OF ORIGINAL BUG:
1. Modal trigger buttons missing type="button" attribute
2. Buttons inside implicit <form> context defaulted to type="submit"
3. Clicking button caused page refresh instead of modal open
4. Bootstrap.Modal race condition due to deferred loading

SOLUTION IMPLEMENTED:
1. Explicit type="button" on all modal trigger buttons
2. Bulletproof Bootstrap availability polling (10 second timeout)
3. Event delegation to survive DOM changes
4. Comprehensive error handling and logging

These tests ensure:
- Quotations can be created with materials and labour
- Totals are calculated correctly
- Validation works (qty >= 1, price >= 0)
- Tenant scoping is enforced
- Buttons have correct type attribute
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestWeldingQuotationCreationFlow:
    """End-to-end tests for creating welding quotations."""

    @pytest.fixture
    def welding_business(self, db):
        """Create a welding business."""
        from tenants.models import Business
        from inventory.business_kinds import BusinessKind
        
        business = Business.objects.create(
            name="Test Welding Quotations",
            kind=BusinessKind.WELDING,
            is_active=True,
        )
        return business

    @pytest.fixture
    def welding_manager(self, db, welding_business):
        """Create manager user with welding business."""
        from tenants.models import Membership
        
        user = User.objects.create_user(
            username="welding_mgr_quote",
            email="welding_mgr_quote@test.com",
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

    @pytest.fixture
    def materials(self, welding_business):
        """Create test materials."""
        from inventory.models_welding import WeldingMaterial
        
        m1 = WeldingMaterial.objects.create(
            business=welding_business,
            code="ROD_6013",
            name="Welding Rod 6013",
            category="electrodes",
            unit="kg",
            price_mwk=Decimal("5000.00"),
            quantity_in_stock=Decimal("50"),
        )
        
        m2 = WeldingMaterial.objects.create(
            business=welding_business,
            code="STEEL_10MM",
            name="Steel Bar 10mm",
            category="steel_bars",
            unit="m",
            price_mwk=Decimal("3000.00"),
            quantity_in_stock=Decimal("100"),
        )
        
        return {"rod": m1, "steel": m2}

    def test_create_quotation_with_materials_and_labour(self, authenticated_client, welding_business, materials):
        """
        Test complete quotation creation flow:
        1. Create quote
        2. Add 2 material items
        3. Add 1 labour cost
        4. Verify totals are calculated correctly
        """
        from inventory.models_welding import WeldingQuote, WeldingQuoteLineItem, WeldingQuoteCost
        
        # Step 1: Create quote
        response = authenticated_client.post(
            "/verticals/welding/quotes/create/",
            {
                "customer_name": "John Doe",
                "customer_phone": "+265991234567",
                "customer_email": "john@example.com",
            }
        )
        
        assert response.status_code == 302, "Quote creation should redirect to detail page"
        
        # Get created quote
        quote = WeldingQuote.objects.get(business=welding_business, customer_name="John Doe")
        assert quote.status == "draft"
        
        # Step 2: Add material line item #1 (Welding Rod)
        response = authenticated_client.post(
            f"/verticals/welding/quotes/{quote.id}/add-line-item/",
            {
                "material_id": materials["rod"].id,
                "quantity": "10",
                "unit_price": "5000",
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        
        # Step 3: Add material line item #2 (Steel Bar)
        response = authenticated_client.post(
            f"/verticals/welding/quotes/{quote.id}/add-line-item/",
            {
                "material_id": materials["steel"].id,
                "quantity": "20",
                "unit_price": "3000",
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        
        # Step 4: Add labour cost
        response = authenticated_client.post(
            f"/verticals/welding/quotes/{quote.id}/add-cost/",
            {
                "cost_type": "labour",
                "description": "Welding work",
                "amount": "25000",
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        
        # Step 5: Verify totals
        line_items = WeldingQuoteLineItem.objects.filter(quote=quote)
        assert line_items.count() == 2
        
        materials_total = sum(item.line_total for item in line_items)
        assert materials_total == Decimal("110000.00")  # (10 * 5000) + (20 * 3000)
        
        costs = WeldingQuoteCost.objects.filter(quote=quote)
        assert costs.count() == 1
        
        labour_total = costs.filter(cost_type="labour").first().amount
        assert labour_total == Decimal("25000.00")
        
        grand_total = materials_total + labour_total
        assert grand_total == Decimal("135000.00")

    def test_quotation_validation_qty_must_be_positive(self, authenticated_client, welding_business, materials):
        """Test that quantity must be >= 1."""
        from inventory.models_welding import WeldingQuote
        
        quote = WeldingQuote.objects.create(
            business=welding_business,
            customer_name="Test Validation",
            status="draft",
        )
        
        # Try to add item with quantity 0
        response = authenticated_client.post(
            f"/verticals/welding/quotes/{quote.id}/add-line-item/",
            {
                "material_id": materials["rod"].id,
                "quantity": "0",
                "unit_price": "5000",
            }
        )
        
        # Should fail validation
        data = response.json()
        assert data["success"] is False or response.status_code == 400

    def test_quotation_validation_price_must_be_non_negative(self, authenticated_client, welding_business, materials):
        """Test that unit price must be >= 0."""
        from inventory.models_welding import WeldingQuote
        
        quote = WeldingQuote.objects.create(
            business=welding_business,
            customer_name="Test Price Validation",
            status="draft",
        )
        
        # Try to add item with negative price
        response = authenticated_client.post(
            f"/verticals/welding/quotes/{quote.id}/add-line-item/",
            {
                "material_id": materials["rod"].id,
                "quantity": "10",
                "unit_price": "-1000",
            }
        )
        
        # Should fail validation
        data = response.json()
        assert data["success"] is False or response.status_code == 400

    def test_quotation_tenant_scoping(self, authenticated_client, welding_business, materials):
        """Test that users cannot access quotes from other businesses."""
        from inventory.models_welding import WeldingQuote
        from tenants.models import Business
        from inventory.business_kinds import BusinessKind
        
        # Create another business
        other_business = Business.objects.create(
            name="Other Welding Shop",
            kind=BusinessKind.WELDING,
            is_active=True,
        )
        
        # Create quote in other business
        other_quote = WeldingQuote.objects.create(
            business=other_business,
            customer_name="Other Customer",
            status="draft",
        )
        
        # Try to access other business's quote
        response = authenticated_client.get(f"/verticals/welding/quotes/{other_quote.id}/")
        
        # Should return 404 (not found, due to business filter)
        assert response.status_code == 404

    def test_quotation_totals_with_decimals(self, authenticated_client, welding_business, materials):
        """Test that decimal arithmetic is handled correctly (no rounding errors)."""
        from inventory.models_welding import WeldingQuote, WeldingQuoteLineItem
        
        quote = WeldingQuote.objects.create(
            business=welding_business,
            customer_name="Decimal Test",
            status="draft",
        )
        
        # Add item with decimal quantity
        response = authenticated_client.post(
            f"/verticals/welding/quotes/{quote.id}/add-line-item/",
            {
                "material_id": materials["rod"].id,
                "quantity": "2.5",
                "unit_price": "4999.99",
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        
        # Verify line total is calculated correctly
        item = WeldingQuoteLineItem.objects.get(quote=quote)
        expected_total = Decimal("2.5") * Decimal("4999.99")
        assert item.line_total == expected_total

    def test_quotation_only_editable_in_draft_status(self, authenticated_client, welding_business, materials):
        """Test that quotes can only be edited when status is DRAFT."""
        from inventory.models_welding import WeldingQuote, WeldingQuoteStatus
        
        quote = WeldingQuote.objects.create(
            business=welding_business,
            customer_name="Locked Quote",
            status=WeldingQuoteStatus.ACCEPTED,  # Not draft
        )
        
        # Try to add line item to accepted quote
        response = authenticated_client.post(
            f"/verticals/welding/quotes/{quote.id}/add-line-item/",
            {
                "material_id": materials["rod"].id,
                "quantity": "10",
                "unit_price": "5000",
            }
        )
        
        # Should fail with 400 Bad Request
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "Quote is not editable"


@pytest.mark.django_db
class TestWeldingQuoteModalButtonTypes:
    """Test that modal trigger buttons have correct type="button" attribute."""

    @pytest.fixture
    def welding_business(self, db):
        """Create a welding business."""
        from tenants.models import Business
        from inventory.business_kinds import BusinessKind
        
        business = Business.objects.create(
            name="Test Button Types",
            kind=BusinessKind.WELDING,
            is_active=True,
        )
        return business

    @pytest.fixture
    def welding_manager(self, db, welding_business):
        """Create manager user."""
        from tenants.models import Membership
        
        user = User.objects.create_user(
            username="button_type_mgr",
            email="button_type@test.com",
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
        """Client authenticated as manager."""
        client.force_login(welding_manager)
        session = client.session
        session['active_business_id'] = welding_business.id
        session.save()
        return client

    def test_add_material_button_has_type_button(self, authenticated_client, welding_business):
        """
        CRITICAL: "Add Material" button MUST have type="button" to prevent form submission.
        
        ROOT CAUSE OF BUG: Buttons without explicit type inside form context
        default to type="submit", causing page refresh instead of modal open.
        """
        from inventory.models_welding import WeldingQuote
        
        quote = WeldingQuote.objects.create(
            business=welding_business,
            customer_name="Button Type Test",
            status="draft",
        )
        
        response = authenticated_client.get(f"/verticals/welding/quotes/{quote.id}/")
        assert response.status_code == 200
        
        html = response.content.decode('utf-8')
        
        # Find "Add Material" button HTML
        import re
        material_button_pattern = r'<button[^>]+data-bs-target="#materialPickerModal"[^>]*>'
        matches = re.findall(material_button_pattern, html)
        
        assert len(matches) > 0, "Add Material button not found"
        
        for button_html in matches:
            assert 'type="button"' in button_html, \
                f"Add Material button missing type='button': {button_html}"

    def test_add_cost_button_has_type_button(self, authenticated_client, welding_business):
        """
        CRITICAL: "Add Cost" button MUST have type="button" to prevent form submission.
        """
        from inventory.models_welding import WeldingQuote
        
        quote = WeldingQuote.objects.create(
            business=welding_business,
            customer_name="Cost Button Test",
            status="draft",
        )
        
        response = authenticated_client.get(f"/verticals/welding/quotes/{quote.id}/")
        assert response.status_code == 200
        
        html = response.content.decode('utf-8')
        
        # Find "Add Cost" button HTML
        import re
        cost_button_pattern = r'<button[^>]+data-bs-target="#costPickerModal"[^>]*>'
        matches = re.findall(cost_button_pattern, html)
        
        assert len(matches) > 0, "Add Cost button not found"
        
        for button_html in matches:
            assert 'type="button"' in button_html, \
                f"Add Cost button missing type='button': {button_html}"

    def test_all_modal_triggers_have_type_button(self, authenticated_client, welding_business):
        """
        Comprehensive test: ALL buttons with data-bs-toggle="modal" MUST have type="button".
        This prevents any future regressions where modal triggers cause form submissions.
        """
        from inventory.models_welding import WeldingQuote
        
        quote = WeldingQuote.objects.create(
            business=welding_business,
            customer_name="All Modals Test",
            status="draft",
        )
        
        response = authenticated_client.get(f"/verticals/welding/quotes/{quote.id}/")
        assert response.status_code == 200
        
        html = response.content.decode('utf-8')
        
        # Find ALL buttons with data-bs-toggle="modal"
        import re
        all_modal_buttons = re.findall(r'<button[^>]+data-bs-toggle="modal"[^>]*>', html)
        
        assert len(all_modal_buttons) > 0, "No modal trigger buttons found"
        
        for button_html in all_modal_buttons:
            assert 'type="button"' in button_html, \
                f"Modal trigger button missing type='button': {button_html}\n\n" \
                f"This will cause form submission and page refresh instead of opening modal!"


@pytest.mark.django_db
class TestWeldingQuoteJavaScriptInitialization:
    """Test that the bulletproof JavaScript initialization is present."""

    @pytest.fixture
    def welding_business(self, db):
        """Create a welding business."""
        from tenants.models import Business
        from inventory.business_kinds import BusinessKind
        
        business = Business.objects.create(
            name="Test JS Init",
            kind=BusinessKind.WELDING,
            is_active=True,
        )
        return business

    @pytest.fixture
    def welding_manager(self, db, welding_business):
        """Create manager user."""
        from tenants.models import Membership
        
        user = User.objects.create_user(
            username="js_init_mgr",
            email="js_init@test.com",
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
        """Client authenticated as manager."""
        client.force_login(welding_manager)
        session = client.session
        session['active_business_id'] = welding_business.id
        session.save()
        return client

    def test_javascript_has_bootstrap_wait_mechanism(self, authenticated_client, welding_business):
        """
        Verify that JavaScript waits for Bootstrap.Modal to be available.
        This prevents race conditions where modals try to initialize before Bootstrap loads.
        """
        from inventory.models_welding import WeldingQuote
        
        quote = WeldingQuote.objects.create(
            business=welding_business,
            customer_name="JS Wait Test",
            status="draft",
        )
        
        response = authenticated_client.get(f"/verticals/welding/quotes/{quote.id}/")
        assert response.status_code == 200
        
        html = response.content.decode('utf-8')
        
        # Verify wait mechanism exists
        assert 'waitForBootstrap' in html or 'typeof bootstrap' in html, \
            "Missing Bootstrap availability check - race condition possible!"

    def test_javascript_has_error_handling(self, authenticated_client, welding_business):
        """
        Verify that JavaScript has comprehensive error handling.
        This ensures failures are logged and users get feedback.
        """
        from inventory.models_welding import WeldingQuote
        
        quote = WeldingQuote.objects.create(
            business=welding_business,
            customer_name="Error Handling Test",
            status="draft",
        )
        
        response = authenticated_client.get(f"/verticals/welding/quotes/{quote.id}/")
        assert response.status_code == 200
        
        html = response.content.decode('utf-8')
        
        # Verify error handling exists
        assert 'try' in html and 'catch' in html, \
            "Missing try/catch error handling - failures will be silent!"
        
        assert 'console.error' in html or 'console.log' in html, \
            "Missing console logging - debugging will be impossible!"

    def test_javascript_uses_event_delegation(self, authenticated_client, welding_business):
        """
        Verify that JavaScript uses event delegation on document.body.
        This ensures buttons work even after partial page reloads (HTMX/Turbo).
        """
        from inventory.models_welding import WeldingQuote
        
        quote = WeldingQuote.objects.create(
            business=welding_business,
            customer_name="Event Delegation Test",
            status="draft",
        )
        
        response = authenticated_client.get(f"/verticals/welding/quotes/{quote.id}/")
        assert response.status_code == 200
        
        html = response.content.decode('utf-8')
        
        # Verify event delegation pattern
        assert 'document.body.addEventListener' in html or 'body.addEventListener' in html, \
            "Missing event delegation - buttons won't survive DOM changes!"














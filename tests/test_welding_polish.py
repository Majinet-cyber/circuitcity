# tests/test_welding_polish.py
"""
Regression tests for Welding vertical polish:
1. Dashboard chart scale fix (MWK 50k/100k/150k ticks)
2. Manual quote creation (no prefill prices)
3. Professional PDF quote template
4. Zero regressions across verticals
"""
import pytest
from decimal import Decimal
from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()


# ==============================================================================
# PART 1: CHART SCALE TESTS
# ==============================================================================


@pytest.mark.django_db
class TestWeldingDashboardChartScale:
    """Test dashboard chart data uses proper integer MWK amounts."""

    @pytest.fixture
    def welding_business(self, db):
        """Create a welding business."""
        from tenants.models import Business
        from inventory.business_kinds import BusinessKind
        
        business = Business.objects.create(
            name="Test Welding Shop",
            kind=BusinessKind.WELDING,
            is_active=True,
        )
        return business

    @pytest.fixture
    def welding_manager(self, db, welding_business):
        """Create manager user."""
        from tenants.models import Membership
        
        user = User.objects.create_user(
            username="weld_mgr_scale",
            email="weld_mgr_scale@test.com",
            password="testpass123",
        )
        Membership.objects.create(
            user=user,
            business=welding_business,
            role="manager",
        )
        return user

    @pytest.fixture
    def authenticated_client(self, welding_manager, welding_business):
        """Create authenticated client."""
        client = Client()
        client.force_login(welding_manager)
        session = client.session
        session["active_business_id"] = welding_business.id
        session.save()
        return client

    def test_dashboard_returns_200(self, authenticated_client):
        """Dashboard renders without error."""
        response = authenticated_client.get("/verticals/welding/dashboard/")
        assert response.status_code == 200

    def test_dashboard_revenue_context_has_integer_values(self, authenticated_client, welding_business):
        """Revenue trend data uses integers (not tiny floats)."""
        from inventory.models_welding import WeldingJob, WeldingJobStatus
        from django.utils import timezone
        
        # Create a delivered job with revenue
        job = WeldingJob.objects.create(
            business=welding_business,
            customer_name="Test Customer",
            job_number="WJ-TEST-001",
            status=WeldingJobStatus.DELIVERED,
            quoted_price=Decimal("150000"),
            final_price=Decimal("150000"),
            delivered_at=timezone.now(),
        )
        
        response = authenticated_client.get("/verticals/welding/dashboard/")
        assert response.status_code == 200
        
        # Check context has revenue_trend_json
        assert "revenue_trend_json" in response.context
        
        # Parse JSON and verify values are integers (not 0.15 or similar)
        import json
        revenue_data = json.loads(response.context["revenue_trend_json"])
        
        # At least one data point should exist
        assert len(revenue_data) > 0
        
        # Check that revenue values are reasonable integers
        for data_point in revenue_data:
            revenue = data_point["revenue"]
            # Revenue should be integer (not tiny float like 0.15)
            assert isinstance(revenue, (int, float))
            # If there's actual revenue, it should be >= 1000 (reasonable MWK)
            if revenue > 0:
                assert revenue >= 1000, f"Revenue {revenue} is too small for MWK"

    def test_dashboard_template_has_chart_config(self):
        """Dashboard template has chart configuration."""
        import os
        template_path = "templates/verticals/welding/dashboard.html"
        assert os.path.exists(template_path)
        
        with open(template_path, encoding="utf-8") as f:
            content = f.read()
        
        # Check for chart canvas
        assert "revenueTrendChart" in content
        
        # Check for step size or tick configuration
        assert "stepSize" in content or "ticks" in content
        
        # Check for beginAtZero
        assert "beginAtZero" in content


# ==============================================================================
# PART 2: QUOTE PDF TESTS
# ==============================================================================


@pytest.mark.django_db
class TestWeldingQuotePDF:
    """Test professional PDF generation."""

    @pytest.fixture
    def welding_business(self, db):
        """Create a welding business."""
        from tenants.models import Business
        from inventory.business_kinds import BusinessKind
        
        business = Business.objects.create(
            name="Premium Welding Ltd",
            kind=BusinessKind.WELDING,
            is_active=True,
        )
        return business

    @pytest.fixture
    def welding_manager(self, db, welding_business):
        """Create manager user."""
        from tenants.models import Membership
        
        user = User.objects.create_user(
            username="weld_mgr_pdf",
            email="weld_mgr_pdf@test.com",
            password="testpass123",
        )
        Membership.objects.create(
            user=user,
            business=welding_business,
            role="manager",
        )
        return user

    @pytest.fixture
    def test_quote(self, db, welding_business, welding_manager):
        """Create a test quote with materials."""
        from inventory.models_welding import WeldingQuote, WeldingQuoteStatus
        
        quote = WeldingQuote.objects.create(
            business=welding_business,
            quote_number="WQ-TEST-001",
            customer_name="John Doe",
            customer_phone="+265991234567",
            customer_email="john@example.com",
            materials_cost=Decimal("80000"),
            labour_cost=Decimal("25000"),
            overhead_cost=Decimal("10500"),
            subtotal=Decimal("115500"),
            total=Decimal("144375"),
            min_price=Decimal("115500"),
            status=WeldingQuoteStatus.DRAFT,
            bom=[
                {
                    "material_code": "TUBE_40x40",
                    "material_name": "Square Tube 40x40mm (5.8m)",
                    "category": "tube",
                    "quantity": "2",
                    "unit": "length_5_8m",
                    "unit_price_mwk": "28000",
                    "line_total_mwk": "56000",
                },
                {
                    "material_code": "PAINT_GLOSS_1L",
                    "material_name": "Gloss Paint 1L",
                    "category": "paint",
                    "quantity": "0.5",
                    "unit": "litre",
                    "unit_price_mwk": "5000",
                    "line_total_mwk": "2500",
                },
            ],
            created_by=welding_manager,
        )
        return quote

    @pytest.fixture
    def authenticated_client(self, welding_manager, welding_business):
        """Create authenticated client."""
        client = Client()
        client.force_login(welding_manager)
        session = client.session
        session["active_business_id"] = welding_business.id
        session.save()
        return client

    def test_quote_pdf_endpoint_exists(self, authenticated_client, test_quote):
        """PDF endpoint exists and returns 200."""
        response = authenticated_client.get(f"/verticals/welding/quotes/{test_quote.id}/pdf/")
        assert response.status_code == 200

    def test_quote_pdf_returns_pdf_content_type(self, authenticated_client, test_quote):
        """PDF endpoint returns application/pdf."""
        response = authenticated_client.get(f"/verticals/welding/quotes/{test_quote.id}/pdf/")
        assert response["Content-Type"] == "application/pdf"

    def test_quote_pdf_not_empty(self, authenticated_client, test_quote):
        """PDF has content (not empty)."""
        response = authenticated_client.get(f"/verticals/welding/quotes/{test_quote.id}/pdf/")
        content = response.content
        assert len(content) > 1000, "PDF should be at least 1KB"

    def test_pdf_generation_function(self, test_quote, welding_business):
        """Direct test of PDF generation function."""
        from inventory.services.welding_pdf import generate_quote_pdf
        
        pdf_bytes = generate_quote_pdf(test_quote, welding_business)
        
        # Should return bytes
        assert pdf_bytes is not None
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1000

    def test_pdf_generation_with_missing_logo(self, test_quote, welding_business):
        """PDF generation works even without logo."""
        from inventory.services.welding_pdf import generate_quote_pdf
        
        # Business has no logo - should still generate
        pdf_bytes = generate_quote_pdf(test_quote, welding_business)
        
        assert pdf_bytes is not None
        assert len(pdf_bytes) > 1000

    def test_pdf_generation_with_missing_customer_email(self, test_quote, welding_business):
        """PDF generation works without customer email."""
        from inventory.services.welding_pdf import generate_quote_pdf
        
        # Remove customer email
        test_quote.customer_email = ""
        test_quote.save()
        
        pdf_bytes = generate_quote_pdf(test_quote, welding_business)
        
        assert pdf_bytes is not None
        assert len(pdf_bytes) > 1000

    def test_pdf_generation_with_decimal_quantities(self, test_quote, welding_business):
        """PDF handles decimal quantities (e.g., 0.5 litres)."""
        from inventory.services.welding_pdf import generate_quote_pdf
        
        # Quote already has 0.5 litre of paint
        pdf_bytes = generate_quote_pdf(test_quote, welding_business)
        
        assert pdf_bytes is not None
        assert len(pdf_bytes) > 1000


# ==============================================================================
# PART 3: NO REGRESSIONS - OTHER VERTICALS
# ==============================================================================


class TestNoRegressionsOtherVerticals:
    """Ensure changes don't break other verticals."""

    def test_gym_sidebar_unchanged(self):
        """Gym sidebar still has expected items."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        sidebar_items = get_vertical_sidebar_items("gym")
        item_keys = [item["key"] for item in sidebar_items]
        
        assert "dashboard" in item_keys
        assert "members" in item_keys

    def test_clothing_sidebar_unchanged(self):
        """Clothing sidebar still has expected items."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        sidebar_items = get_vertical_sidebar_items("clothing")
        item_keys = [item["key"] for item in sidebar_items]
        
        assert "dashboard" in item_keys
        assert "hub" in item_keys

    def test_welding_sidebar_has_sales(self):
        """Welding sidebar includes Sales link."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        sidebar_items = get_vertical_sidebar_items("welding")
        item_keys = [item["key"] for item in sidebar_items]
        
        assert "sales" in item_keys
        assert "dashboard" in item_keys
        assert "quotes" in item_keys

    def test_farm_dashboard_template_exists(self):
        """Farm dashboard template still exists."""
        import os
        assert os.path.exists("templates/verticals/farm/dashboard.html")


# ==============================================================================
# PART 4: MATERIALS AND ESTIMATOR
# ==============================================================================


class TestWeldingEstimatorFunctions:
    """Test estimator pure functions."""

    def test_seed_default_materials_returns_list(self):
        """Seeding function returns list of materials to create."""
        from inventory.services.welding_estimator import seed_default_materials
        
        existing_codes = ["TUBE_20x20", "PAINT_GLOSS_5L"]
        to_seed = seed_default_materials(existing_codes)
        
        # Should return list
        assert isinstance(to_seed, list)
        
        # Should not include existing codes
        codes = [m["code"] for m in to_seed]
        assert "TUBE_20x20" not in codes
        assert "PAINT_GLOSS_5L" not in codes
        
        # Should include other materials
        assert len(to_seed) > 0

    def test_compute_cost_function(self):
        """Cost computation is deterministic."""
        from inventory.services.welding_estimator import compute_cost
        from decimal import Decimal
        
        bom_items = [
            {
                "material_code": "TUBE_40x40",
                "material_name": "Square Tube 40x40mm",
                "category": "tube",
                "quantity": Decimal("2"),
                "unit": "length_5_8m",
                "unit_price_mwk": Decimal("28000"),
                "line_total_mwk": Decimal("56000"),
            }
        ]
        
        cost_breakdown = compute_cost(
            bom_items=bom_items,
            labour_hours=Decimal("4"),
            labour_rate_per_hour=Decimal("5000"),
            overhead_pct=Decimal("10"),
            margin_pct=Decimal("25"),
        )
        
        # Materials cost should be 56000
        assert cost_breakdown["materials_cost"] == Decimal("56000")
        
        # Labour cost should be 4 * 5000 = 20000
        assert cost_breakdown["labour_cost"] == Decimal("20000")
        
        # Overhead should be 10% of (56000 + 20000) = 7600
        assert cost_breakdown["overhead_cost"] == Decimal("7600")
        
        # Subtotal before margin = 56000 + 20000 + 7600 = 83600
        assert cost_breakdown["subtotal_before_margin"] == Decimal("83600")
        
        # Total should have margin added
        assert cost_breakdown["total"] > cost_breakdown["subtotal_before_margin"]


# ==============================================================================
# PART 5: URL ROUTING
# ==============================================================================


class TestWeldingURLs:
    """Test welding URL patterns are stable."""

    def test_welding_dashboard_url_resolves(self):
        """Welding dashboard URL resolves."""
        from django.urls import reverse
        url = reverse("verticals:welding_dashboard")
        assert "/welding/dashboard/" in url

    def test_welding_sales_url_resolves(self):
        """Welding sales URL resolves."""
        from django.urls import reverse
        url = reverse("verticals:welding_sales")
        assert "/welding/sales/" in url

    def test_welding_quotes_list_url_resolves(self):
        """Welding quotes list URL resolves."""
        from django.urls import reverse
        url = reverse("verticals:welding_quotes_list")
        assert "/welding/quotes/" in url

    def test_welding_quote_create_url_resolves(self):
        """Welding quote create URL resolves."""
        from django.urls import reverse
        url = reverse("verticals:welding_quote_create")
        assert "/welding/quotes/create/" in url


# ==============================================================================
# PART 6: NO AUTO-FILL REGRESSION TESTS
# ==============================================================================


@pytest.mark.django_db
class TestWeldingQuoteNoAutoFill:
    """
    Critical regression tests: ensure NO auto-fill behavior.
    Quotes must start empty, manager must add materials manually.
    """

    @pytest.fixture
    def welding_business(self, db):
        """Create a welding business."""
        from tenants.models import Business
        from inventory.business_kinds import BusinessKind
        
        business = Business.objects.create(
            name="Manual Quote Shop",
            kind=BusinessKind.WELDING,
            is_active=True,
        )
        return business

    @pytest.fixture
    def welding_manager(self, db, welding_business):
        """Create manager user."""
        from tenants.models import Membership
        
        user = User.objects.create_user(
            username="weld_mgr_manual",
            email="weld_mgr_manual@test.com",
            password="testpass123",
        )
        Membership.objects.create(
            user=user,
            business=welding_business,
            role="manager",
        )
        return user

    @pytest.fixture
    def authenticated_client(self, welding_manager, welding_business):
        """Create authenticated client."""
        client = Client()
        client.force_login(welding_manager)
        session = client.session
        session["active_business_id"] = welding_business.id
        session.save()
        return client

    @pytest.fixture
    def job_template(self, db):
        """Create a job template (BED_3x4)."""
        from inventory.models_welding import WeldingTemplate
        
        template = WeldingTemplate.objects.create(
            code="BED_3x4",
            name="Bed Frame 3ft x 4ft",
            base_bom={"TUBE_40x40": {"qty_formula": "frame", "base_qty": 2}},
            default_labour_hours=Decimal("3"),
        )
        return template

    def test_quote_create_with_template_has_zero_line_items(
        self, authenticated_client, welding_business, job_template
    ):
        """
        CRITICAL: Creating a quote with a template must NOT auto-add materials.
        """
        from inventory.models_welding import WeldingQuote
        
        # Create quote via POST
        response = authenticated_client.post(
            "/verticals/welding/quotes/create/",
            {
                "customer_name": "John Doe",
                "customer_phone": "+265991234567",
                "template_id": job_template.id,
            },
        )
        
        # Should redirect on success
        assert response.status_code == 302
        
        # Get the created quote
        quote = WeldingQuote.objects.filter(business=welding_business).first()
        assert quote is not None
        assert quote.customer_name == "John Doe"
        assert quote.template == job_template
        
        # CRITICAL: Quote must have ZERO line items
        assert quote.line_items.count() == 0, "Quote must start with zero line items"

    def test_quote_line_item_unit_price_starts_null(self, authenticated_client, welding_business):
        """
        CRITICAL: When adding a line item, unit_price must be NULL/blank by default.
        """
        from inventory.models_welding import WeldingQuote, WeldingMaterial, WeldingQuoteLineItem
        
        # Create a material
        material = WeldingMaterial.objects.create(
            business=welding_business,
            name="Square Tube 40x40",
            code="TUBE_40x40",
            category="tube",
            unit="length_5_8m",
            price_mwk=Decimal("28000"),  # Has a price in catalog
        )
        
        # Create a quote
        quote = WeldingQuote.objects.create(
            business=welding_business,
            customer_name="Test Customer",
        )
        
        # Add line item WITHOUT specifying unit_price
        line_item = WeldingQuoteLineItem.objects.create(
            quote=quote,
            material=material,
            material_name=material.name,
            material_unit=material.unit,
            quantity=Decimal("2"),
            # unit_price deliberately NOT set
        )
        
        # CRITICAL: unit_price must be NULL
        assert line_item.unit_price is None, "Unit price must NOT be pre-filled"
        assert line_item.line_total == Decimal("0"), "Line total must be 0 when price is null"

    def test_quote_detail_editable_when_draft(self, authenticated_client, welding_business):
        """Draft quotes must be editable."""
        from inventory.models_welding import WeldingQuote, WeldingQuoteStatus
        
        quote = WeldingQuote.objects.create(
            business=welding_business,
            customer_name="Test Customer",
            status=WeldingQuoteStatus.DRAFT,
        )
        
        response = authenticated_client.get(f"/verticals/welding/quotes/{quote.id}/")
        assert response.status_code == 200
        assert response.context["is_editable"] is True

    def test_quote_detail_not_editable_when_sent(self, authenticated_client, welding_business):
        """Sent quotes must NOT be editable."""
        from inventory.models_welding import WeldingQuote, WeldingQuoteStatus
        
        quote = WeldingQuote.objects.create(
            business=welding_business,
            customer_name="Test Customer",
            status=WeldingQuoteStatus.SENT,
        )
        
        response = authenticated_client.get(f"/verticals/welding/quotes/{quote.id}/")
        assert response.status_code == 200
        assert response.context["is_editable"] is False

    def test_add_line_item_ajax_creates_item(self, authenticated_client, welding_business):
        """AJAX endpoint for adding line item works."""
        from inventory.models_welding import WeldingQuote, WeldingMaterial
        
        material = WeldingMaterial.objects.create(
            business=welding_business,
            name="Square Tube 40x40",
            code="TUBE_40x40",
            category="tube",
            unit="length_5_8m",
            price_mwk=Decimal("28000"),
        )
        
        quote = WeldingQuote.objects.create(
            business=welding_business,
            customer_name="Test Customer",
        )
        
        response = authenticated_client.post(
            f"/verticals/welding/quotes/{quote.id}/add-line-item/",
            {
                "material_id": material.id,
                "quantity": "2",
                # Deliberately NOT providing unit_price
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        
        # Verify line item was created
        assert quote.line_items.count() == 1
        line_item = quote.line_items.first()
        assert line_item.quantity == Decimal("2")
        assert line_item.unit_price is None

    def test_business_scoping_on_quotes(self, authenticated_client, welding_business):
        """Quotes from other businesses must not be accessible."""
        from tenants.models import Business
        from inventory.business_kinds import BusinessKind
        from inventory.models_welding import WeldingQuote
        
        # Create another business
        other_business = Business.objects.create(
            name="Other Welding Shop",
            kind=BusinessKind.WELDING,
            is_active=True,
        )
        
        # Create quote for OTHER business
        other_quote = WeldingQuote.objects.create(
            business=other_business,
            customer_name="Other Customer",
        )
        
        # Try to access it from our session (welding_business)
        response = authenticated_client.get(f"/verticals/welding/quotes/{other_quote.id}/")
        
        # Should get 404
        assert response.status_code == 404


# ==============================================================================
# PART 5: MODAL Z-INDEX & CLICKABILITY REGRESSION TESTS (2026-01-17)
# ==============================================================================


@pytest.mark.django_db
class TestModalStructureRegression:
    """
    Regression tests for modal overlay z-index/pointer-events fix.
    
    ROOT CAUSE: Modals rendered inside .cc-main (which has z-index:0) were
    trapped in a stacking context, causing them to appear below sidebar/backdrop.
    
    FIX: Modal portal (#cc-modal-root) at body level + proper z-index ordering.
    """

    @pytest.fixture
    def welding_business(self, db):
        """Create a welding business."""
        from tenants.models import Business
        from inventory.business_kinds import BusinessKind
        
        business = Business.objects.create(
            name="Test Welding Shop Modal",
            kind=BusinessKind.WELDING,
            is_active=True,
        )
        return business

    @pytest.fixture
    def welding_manager(self, db, welding_business):
        """Create manager user."""
        from tenants.models import Membership
        
        user = User.objects.create_user(
            username="weld_mgr_modal",
            email="weld_mgr_modal@test.com",
            password="testpass123",
        )
        Membership.objects.create(
            user=user,
            business=welding_business,
            role="manager",
        )
        return user

    @pytest.fixture
    def authenticated_client(self, welding_manager, welding_business):
        """Create authenticated client."""
        client = Client()
        client.force_login(welding_manager)
        session = client.session
        session["active_business_id"] = welding_business.id
        session.save()
        return client

    def test_base_html_includes_modal_root(self, authenticated_client):
        """
        base.html must include #cc-modal-root at the end of body (outside .cc-shell).
        This ensures modals escape the stacking context trap of .cc-main.
        """
        response = authenticated_client.get("/verticals/welding/dashboard/")
        assert response.status_code == 200
        
        html = response.content.decode('utf-8')
        
        # Modal root must exist
        assert 'id="cc-modal-root"' in html, "Modal root container missing from base.html"
        
        # Modal root should be after the closing .cc-shell div
        # (Simple check: it appears after </div> that closes cc-main)
        shell_end_pos = html.rfind('</div><!-- close cc-shell or cc-main -->')
        if shell_end_pos == -1:
            # Fallback: find last occurrence of cc-main or cc-shell
            shell_end_pos = max(html.rfind('class="cc-main"'), html.rfind('class="cc-shell"'))
        
        modal_root_pos = html.find('id="cc-modal-root"')
        
        # If both exist, modal root should come after (or at least not deeply nested)
        if shell_end_pos > 0 and modal_root_pos > 0:
            # Modal root should be relatively close to end of body
            body_end_pos = html.rfind('</body>')
            assert body_end_pos - modal_root_pos < 10000, \
                "Modal root should be near end of body, not deeply nested"

    def test_welding_quote_detail_renders_modals(self, authenticated_client, welding_business):
        """
        Welding quote detail page must render modal triggers and modal markup.
        """
        from inventory.models_welding import WeldingQuote
        
        quote = WeldingQuote.objects.create(
            business=welding_business,
            customer_name="Test Customer Modal",
        )
        
        response = authenticated_client.get(f"/verticals/welding/quotes/{quote.id}/")
        assert response.status_code == 200
        
        html = response.content.decode('utf-8')
        
        # Material picker modal must exist
        assert 'id="materialPickerModal"' in html, "Material picker modal missing"
        
        # Cost picker modal must exist
        assert 'id="costPickerModal"' in html, "Cost picker modal missing"
        
        # Modal trigger buttons must exist
        assert 'data-bs-target="#materialPickerModal"' in html, "Material picker trigger missing"
        assert 'data-bs-target="#costPickerModal"' in html, "Cost picker trigger missing"

    def test_modal_css_ensures_proper_z_index(self, authenticated_client):
        """
        CSS must define proper z-index ordering:
        - modal (20050) > modal-backdrop (20040) > sidebar (2000) > sidebar-backdrop (1990)
        """
        # We can't directly test CSS parsing in pytest without selenium,
        # but we can verify the CSS file contains the critical rules
        import os
        from django.conf import settings
        
        css_path = os.path.join(settings.BASE_DIR, 'static', 'css', 'v2-overrides.2025-09-25.css')
        
        if os.path.exists(css_path):
            with open(css_path, 'r', encoding='utf-8') as f:
                css_content = f.read()
            
            # Check for modal z-index
            assert 'z-index: 20050' in css_content or 'z-index:20050' in css_content, \
                "Modal z-index (20050) not found in CSS"
            
            # Check for modal-backdrop z-index
            assert 'z-index: 20040' in css_content or 'z-index:20040' in css_content, \
                "Modal backdrop z-index (20040) not found in CSS"
            
            # Check for pointer-events on modal
            assert 'pointer-events: auto' in css_content or 'pointer-events:auto' in css_content, \
                "Modal pointer-events:auto not found in CSS"
        else:
            pytest.skip(f"CSS file not found: {css_path}")

    def test_modal_portal_script_exists(self, authenticated_client):
        """
        base.html must include the modal portal configuration script
        that moves modals to #cc-modal-root.
        """
        response = authenticated_client.get("/verticals/welding/dashboard/")
        assert response.status_code == 200
        
        html = response.content.decode('utf-8')
        
        # Script must exist
        assert 'cc-modal-root' in html, "Modal root not referenced in HTML"
        
        # Check for portal configuration logic (even if minified/compressed)
        # We look for key function names or comments
        assert 'Modal Portal' in html or 'modal-root' in html.lower(), \
            "Modal portal configuration missing from base.html"

    def test_quote_detail_modals_have_proper_bootstrap_structure(self, authenticated_client, welding_business):
        """
        Modals must have proper Bootstrap structure:
        - .modal.fade with tabindex="-1"
        - .modal-dialog > .modal-content > .modal-header/.modal-body
        """
        from inventory.models_welding import WeldingQuote
        
        quote = WeldingQuote.objects.create(
            business=welding_business,
            customer_name="Test Customer Structure",
        )
        
        response = authenticated_client.get(f"/verticals/welding/quotes/{quote.id}/")
        assert response.status_code == 200
        
        html = response.content.decode('utf-8')
        
        # Material modal structure
        assert 'class="modal fade"' in html, "Modal must have 'modal fade' classes"
        assert 'tabindex="-1"' in html, "Modal must have tabindex=-1"
        assert 'modal-dialog' in html, "Modal must have .modal-dialog"
        assert 'modal-content' in html, "Modal must have .modal-content"
        assert 'modal-header' in html, "Modal must have .modal-header"
        assert 'modal-body' in html, "Modal must have .modal-body"
        
        # Close button with proper data attribute
        assert 'data-bs-dismiss="modal"' in html, "Modal must have close button with data-bs-dismiss"


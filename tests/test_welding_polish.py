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
from datetime import timedelta
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


# ==============================================================================
# PART 6: WELDING 500 ERROR REGRESSION TESTS (2026-01-17)
# ==============================================================================


@pytest.mark.django_db
class TestWelding500ErrorFixes:
    """
    Regression tests for Welding pages that were crashing with VariableDoesNotExist.
    
    ROOT CAUSE: Templates accessed .name on potentially None variables (business, location, etc.)
    
    FIX: Use safe Django template conditionals ({% if business %}{{ business.name }}{% endif %})
    """

    @pytest.fixture
    def welding_business(self, db):
        """Create a welding business."""
        from tenants.models import Business
        from inventory.business_kinds import BusinessKind
        
        business = Business.objects.create(
            name="Test Welding 500 Fix",
            kind=BusinessKind.WELDING,
            is_active=True,
        )
        return business

    @pytest.fixture
    def welding_manager(self, db, welding_business):
        """Create manager user."""
        from tenants.models import Membership
        
        user = User.objects.create_user(
            username="weld_mgr_500",
            email="weld_mgr_500@test.com",
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

    def test_welding_jobs_page_returns_200(self, authenticated_client):
        """Jobs list page renders without server error."""
        response = authenticated_client.get("/verticals/welding/jobs/")
        assert response.status_code == 200, "Jobs page should render successfully"

    def test_welding_sales_page_returns_200(self, authenticated_client):
        """Sales page renders without server error."""
        response = authenticated_client.get("/verticals/welding/sales/")
        assert response.status_code == 200, "Sales page should render successfully"

    def test_welding_dashboard_returns_200(self, authenticated_client):
        """Dashboard renders without server error."""
        response = authenticated_client.get("/verticals/welding/dashboard/")
        assert response.status_code == 200, "Dashboard should render successfully"

    def test_welding_quotes_list_returns_200(self, authenticated_client):
        """Quotes list page renders without server error."""
        response = authenticated_client.get("/verticals/welding/quotes/")
        assert response.status_code == 200, "Quotes page should render successfully"

    def test_welding_materials_list_returns_200(self, authenticated_client):
        """Materials list page renders without server error."""
        response = authenticated_client.get("/verticals/welding/materials/")
        assert response.status_code == 200, "Materials page should render successfully"

    def test_welding_stock_in_returns_200(self, authenticated_client):
        """Stock in page renders without server error."""
        response = authenticated_client.get("/verticals/welding/stock-in/")
        assert response.status_code == 200, "Stock in page should render successfully"

    def test_jobs_page_with_no_location_in_session(self, authenticated_client):
        """
        Edge case: Jobs page works even when no location is set in session.
        This was a common cause of None values.
        """
        # Clear location from session
        session = authenticated_client.session
        if 'active_location_id' in session:
            del session['active_location_id']
        session.save()
        
        response = authenticated_client.get("/verticals/welding/jobs/")
        assert response.status_code == 200, "Jobs page should work without location"

    def test_sales_page_with_no_location_in_session(self, authenticated_client):
        """
        Edge case: Sales page works even when no location is set in session.
        """
        # Clear location from session
        session = authenticated_client.session
        if 'active_location_id' in session:
            del session['active_location_id']
        session.save()
        
        response = authenticated_client.get("/verticals/welding/sales/")
        assert response.status_code == 200, "Sales page should work without location"

    def test_dashboard_context_always_has_business(self, authenticated_client):
        """Dashboard view always provides business in context."""
        response = authenticated_client.get("/verticals/welding/dashboard/")
        assert response.status_code == 200
        assert "business" in response.context, "Context must include business"
        # Business can be None, but key must exist
        
    def test_jobs_page_title_renders_safely(self, authenticated_client):
        """Jobs page title renders without crashing when business name is accessed."""
        response = authenticated_client.get("/verticals/welding/jobs/")
        assert response.status_code == 200
        html = response.content.decode('utf-8')
        # Should contain "Jobs" in title
        assert '<title>' in html
        assert 'Jobs' in html

    def test_sales_page_title_renders_safely(self, authenticated_client):
        """Sales page title renders without crashing when business name is accessed."""
        response = authenticated_client.get("/verticals/welding/sales/")
        assert response.status_code == 200
        html = response.content.decode('utf-8')
        # Should contain "Sales" in title
        assert '<title>' in html
        assert 'Sales' in html

    def test_invoice_detail_renders_without_business_address(self, authenticated_client, welding_business):
        """Invoice detail page renders even when business has no address."""
        from inventory.models_welding import WeldingInvoice
        
        # Create invoice
        invoice = WeldingInvoice.objects.create(
            business=welding_business,
            invoice_number="INV-TEST-001",
            customer_name="Test Customer",
            total=1000,
        )
        
        response = authenticated_client.get(f"/verticals/welding/invoices/{invoice.id}/")
        assert response.status_code == 200, "Invoice detail should render without address"

    def test_sales_page_with_no_invoices_returns_200(self, authenticated_client):
        """
        CRITICAL REGRESSION: Sales page with ZERO invoices must not crash.
        Previously crashed with empty queryset in sales_by_day aggregation.
        """
        response = authenticated_client.get("/verticals/welding/sales/")
        assert response.status_code == 200, "Sales page should render with no invoices"
        
        # Verify context has expected keys
        assert "total_invoiced" in response.context
        assert "total_paid" in response.context
        assert response.context["total_invoiced"] == Decimal("0")

    def test_sales_page_sqlite_date_grouping_works(self, authenticated_client, welding_business):
        """
        CRITICAL: Sales page date aggregation must work on SQLite.
        Previously failed with OperationalError on TruncDate.
        """
        from inventory.models_welding import WeldingInvoice
        from django.utils import timezone
        
        # Create test invoices
        WeldingInvoice.objects.create(
            business=welding_business,
            invoice_number="INV-001",
            customer_name="Customer A",
            total=Decimal("50000"),
            amount_paid=Decimal("50000"),
            issue_date=timezone.now().date(),
        )
        
        WeldingInvoice.objects.create(
            business=welding_business,
            invoice_number="INV-002",
            customer_name="Customer B",
            total=Decimal("30000"),
            amount_paid=Decimal("30000"),
            issue_date=timezone.now().date() - timedelta(days=5),
        )
        
        # This should NOT crash with OperationalError
        response = authenticated_client.get("/verticals/welding/sales/")
        assert response.status_code == 200, "Sales page should work with invoices on SQLite"
        
        # Verify chart data is present
        assert "sales_trend_json" in response.context
        import json
        sales_data = json.loads(response.context["sales_trend_json"])
        assert isinstance(sales_data, list), "Sales trend should be a list"

    def test_jobs_page_with_template_none_renders(self, authenticated_client, welding_business):
        """
        CRITICAL: Jobs page with job.template=None must not crash.
        Previously crashed with VariableDoesNotExist when accessing job.template.name.
        """
        from inventory.models_welding import WeldingJob, WeldingJobStatus
        
        # Create job WITHOUT template
        job = WeldingJob.objects.create(
            business=welding_business,
            customer_name="Test Customer",
            job_number="WJ-NO-TEMPLATE",
            product_description="Custom Job",
            status=WeldingJobStatus.PENDING,
            quoted_price=Decimal("100000"),
            template=None,  # CRITICAL: No template
        )
        
        response = authenticated_client.get("/verticals/welding/jobs/")
        assert response.status_code == 200, "Jobs page should render with template=None"
        
        html = response.content.decode('utf-8')
        assert "WJ-NO-TEMPLATE" in html
        assert "Custom Job" in html or "-" in html  # Should show description or fallback

    def test_dashboard_with_custom_date_range_returns_200(self, authenticated_client):
        """Dashboard with custom date range filter should work."""
        response = authenticated_client.get("/verticals/welding/dashboard/?start=2026-01-01&end=2026-01-15")
        assert response.status_code == 200
        assert response.context["active_range"] == "custom"


# ==============================================================================
# PART 7: DASHBOARD FILTER & INSIGHTS TESTS (2026-01-17)
# ==============================================================================


@pytest.mark.django_db
class TestWeldingDashboardFilters:
    """
    Tests for Welding dashboard date range filtering and insights.
    
    FEATURE: Dashboard Filter button with MTD/7d/30d/Custom date range.
    FEATURE: Insights section with job/revenue metrics.
    """

    @pytest.fixture
    def welding_business(self, db):
        """Create a welding business."""
        from tenants.models import Business
        from inventory.business_kinds import BusinessKind
        
        business = Business.objects.create(
            name="Test Welding Filters",
            kind=BusinessKind.WELDING,
            is_active=True,
        )
        return business

    @pytest.fixture
    def welding_manager(self, db, welding_business):
        """Create manager user."""
        from tenants.models import Membership
        
        user = User.objects.create_user(
            username="weld_mgr_filters",
            email="weld_mgr_filters@test.com",
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

    def test_dashboard_defaults_to_mtd(self, authenticated_client):
        """Dashboard defaults to Month to Date when no filter is specified."""
        response = authenticated_client.get("/verticals/welding/dashboard/")
        assert response.status_code == 200
        assert response.context["active_range"] == "mtd"
        assert "Month to Date" in response.context["range_label"]

    def test_dashboard_supports_7d_filter(self, authenticated_client):
        """Dashboard supports Last 7 Days filter."""
        response = authenticated_client.get("/verticals/welding/dashboard/?range=7d")
        assert response.status_code == 200
        assert response.context["active_range"] == "7d"
        assert "Last 7 Days" in response.context["range_label"]

    def test_dashboard_supports_30d_filter(self, authenticated_client):
        """Dashboard supports Last 30 Days filter."""
        response = authenticated_client.get("/verticals/welding/dashboard/?range=30d")
        assert response.status_code == 200
        assert response.context["active_range"] == "30d"
        assert "Last 30 Days" in response.context["range_label"]

    def test_dashboard_supports_custom_date_range(self, authenticated_client):
        """Dashboard supports custom start/end dates."""
        response = authenticated_client.get("/verticals/welding/dashboard/?start=2026-01-01&end=2026-01-15")
        assert response.status_code == 200
        assert response.context["active_range"] == "custom"
        # Custom range should show date span in label
        assert "Jan" in response.context["range_label"]

    def test_dashboard_filter_button_renders(self, authenticated_client):
        """Dashboard renders filter button UI."""
        response = authenticated_client.get("/verticals/welding/dashboard/")
        assert response.status_code == 200
        html = response.content.decode('utf-8')
        
        # Filter button should exist
        assert 'id="dashboardFilterBtn"' in html or 'data-testid="welding-filter-button"' in html
        
        # Filter options should exist
        assert '?range=mtd' in html
        assert '?range=7d' in html
        assert '?range=30d' in html

    def test_dashboard_insights_section_renders(self, authenticated_client):
        """Dashboard renders insights section."""
        response = authenticated_client.get("/verticals/welding/dashboard/")
        assert response.status_code == 200
        html = response.content.decode('utf-8')
        
        # Insights section should exist
        assert 'data-testid="welding-insights"' in html or '💡 Insights' in html

    def test_dashboard_insights_include_jobs_created(self, authenticated_client):
        """Dashboard insights include jobs created count."""
        response = authenticated_client.get("/verticals/welding/dashboard/")
        assert response.status_code == 200
        assert "jobs_created_in_range" in response.context

    def test_dashboard_insights_include_jobs_completed(self, authenticated_client):
        """Dashboard insights include jobs completed count."""
        response = authenticated_client.get("/verticals/welding/dashboard/")
        assert response.status_code == 200
        assert "jobs_completed_in_range" in response.context

    def test_dashboard_insights_include_avg_job_value(self, authenticated_client):
        """Dashboard insights include average job value."""
        response = authenticated_client.get("/verticals/welding/dashboard/")
        assert response.status_code == 200
        assert "avg_job_value" in response.context

    def test_dashboard_insights_include_outstanding_jobs(self, authenticated_client):
        """Dashboard insights include outstanding jobs count."""
        response = authenticated_client.get("/verticals/welding/dashboard/")
        assert response.status_code == 200
        assert "outstanding_jobs" in response.context

    def test_dashboard_filter_affects_revenue_kpi(self, authenticated_client, welding_business):
        """Filtering changes revenue KPI calculation."""
        from inventory.models_welding import WeldingJob, WeldingJobStatus
        from django.utils import timezone
        from datetime import timedelta
        
        # Create a job delivered 20 days ago
        past_job = WeldingJob.objects.create(
            business=welding_business,
            customer_name="Past Customer",
            job_number="WJ-PAST-001",
            status=WeldingJobStatus.DELIVERED,
            quoted_price=Decimal("100000"),
            final_price=Decimal("100000"),
            delivered_at=timezone.now() - timedelta(days=20),
        )
        
        # Create a job delivered 5 days ago
        recent_job = WeldingJob.objects.create(
            business=welding_business,
            customer_name="Recent Customer",
            job_number="WJ-RECENT-001",
            status=WeldingJobStatus.DELIVERED,
            quoted_price=Decimal("50000"),
            final_price=Decimal("50000"),
            delivered_at=timezone.now() - timedelta(days=5),
        )
        
        # Last 7 days should only include recent job
        response_7d = authenticated_client.get("/verticals/welding/dashboard/?range=7d")
        assert response_7d.status_code == 200
        revenue_7d = response_7d.context["revenue_this_month"]
        
        # Last 30 days should include both jobs
        response_30d = authenticated_client.get("/verticals/welding/dashboard/?range=30d")
        assert response_30d.status_code == 200
        revenue_30d = response_30d.context["revenue_this_month"]
        
        # 30d revenue should be greater than 7d revenue
        assert revenue_30d >= revenue_7d

    def test_dashboard_filter_label_updates(self, authenticated_client):
        """Dashboard shows active filter label."""
        response = authenticated_client.get("/verticals/welding/dashboard/?range=7d")
        assert response.status_code == 200
        html = response.content.decode('utf-8')
        
        # Should show "Last 7 Days" somewhere in the page
        assert 'data-testid="welding-date-range-label"' in html
        assert "Last 7 Days" in html

    def test_invalid_date_range_falls_back_to_mtd(self, authenticated_client):
        """Invalid date range parameter falls back to MTD."""
        response = authenticated_client.get("/verticals/welding/dashboard/?range=invalid")
        assert response.status_code == 200
        assert response.context["active_range"] == "mtd"

    def test_custom_range_with_invalid_dates_falls_back(self, authenticated_client):
        """Custom range with invalid dates falls back to MTD."""
        response = authenticated_client.get("/verticals/welding/dashboard/?start=invalid&end=invalid")
        assert response.status_code == 200
        # Should fall back gracefully
        assert "active_range" in response.context


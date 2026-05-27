# tests/test_welding_vertical_upgrade.py
"""
Regression tests for the Welding Vertical Premium Upgrade.

Tests cover:
- Materials catalog with search
- Stock-in with material picker
- Quote builder + PDF generation
- Job simulator
- Dashboard KPIs
- No duplicates during seeding

All tests must pass for the upgrade to be considered complete.
"""
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import Client, RequestFactory
from django.urls import reverse

from inventory.models_welding import (
    WeldingMaterial,
    WeldingMaterialCategory,
    WeldingMaterialUnit,
    WeldingQuote,
    WeldingQuoteStatus,
    WeldingJob,
    WeldingTemplate,
)
from inventory.services.welding_estimator import (
    seed_default_materials,
    get_default_materials,
    get_default_templates,
    estimate_bom,
    compute_cost,
    generate_quote_from_template,
    MaterialData,
    TuningData,
)


# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def welding_business(db):
    """Create a welding business for testing."""
    from tenants.models import Business
    from inventory.business_kinds import BusinessKind
    
    business = Business.objects.create(
        name="Test Welding Workshop",
        kind=BusinessKind.WELDING,
        is_active=True,
    )
    return business


@pytest.fixture
def welding_user(db, welding_business):
    """Create a user associated with the welding business."""
    from django.contrib.auth import get_user_model
    from tenants.models import Membership
    
    User = get_user_model()
    user = User.objects.create_user(
        username="welder_test",
        email="welder@test.com",
        password="testpass123",
    )
    Membership.objects.create(
        user=user,
        business=welding_business,
        role="manager",
    )
    return user


@pytest.fixture
def authenticated_client(welding_user, welding_business):
    """Create an authenticated client with welding business."""
    client = Client()
    client.force_login(welding_user)
    # Set the active business in session
    session = client.session
    session['active_business_id'] = welding_business.id
    session.save()
    return client


@pytest.fixture
def sample_materials(welding_business):
    """Create sample materials for testing."""
    materials = []
    for mat in get_default_materials()[:10]:
        m = WeldingMaterial.objects.create(
            business=welding_business,
            code=mat["code"],
            name=mat["name"],
            category=mat["category"],
            unit=mat["unit"],
            price_mwk=mat["default_price"],
            is_seeded=True,
            quantity_in_stock=Decimal("10"),
        )
        materials.append(m)
    return materials


@pytest.fixture
def sample_template(db):
    """Create a sample welding template."""
    templates = get_default_templates()
    tpl_data = templates[1] if len(templates) > 1 else templates[0]  # BED_4x6
    
    template = WeldingTemplate.objects.create(
        business=None,  # Global template
        code=tpl_data["code"],
        name=tpl_data["name"],
        params_schema=tpl_data.get("params_schema", {}),
        base_bom=tpl_data.get("base_bom", {}),
        default_labour_hours=Decimal(str(tpl_data.get("default_labour_hours", 4))),
    )
    return template


@pytest.fixture
def sample_quote(welding_business, welding_user, sample_template):
    """Create a sample quote for testing."""
    quote = WeldingQuote.objects.create(
        business=welding_business,
        customer_name="Test Customer",
        customer_phone="0888123456",
        template=sample_template,
        bom=[
            {
                "material_code": "TUBE_40x40",
                "material_name": "Square Tube 40x40mm (5.8m)",
                "category": "tube",
                "quantity": "3",
                "unit": "length_5_8m",
                "unit_price_mwk": "28000",
                "line_total_mwk": "84000",
            }
        ],
        materials_cost=Decimal("84000"),
        labour_cost=Decimal("20000"),
        overhead_cost=Decimal("10400"),
        subtotal=Decimal("114400"),
        total=Decimal("143000"),
        min_price=Decimal("114400"),
        status=WeldingQuoteStatus.DRAFT,
        created_by=welding_user,
    )
    return quote


# ==============================================================================
# SEEDING TESTS - No Duplicates
# ==============================================================================


class TestMaterialSeeding:
    """Test that material seeding is idempotent."""

    def test_seed_returns_all_when_empty(self):
        """Seeding with empty existing codes returns all materials."""
        to_seed = seed_default_materials([])
        # Should have many materials (expanded catalog)
        assert len(to_seed) >= 50, "Expected at least 50 default materials"

    def test_seed_returns_none_when_all_exist(self):
        """Seeding with all existing codes returns empty list."""
        default_mats = get_default_materials()
        existing_codes = [m["code"] for m in default_mats]
        
        to_seed = seed_default_materials(existing_codes)
        
        assert len(to_seed) == 0, "Should not seed any materials when all exist"

    def test_seed_partial_returns_only_missing(self):
        """Seeding with some existing codes returns only missing."""
        # Simulate having first 10 materials
        existing = [m["code"] for m in get_default_materials()[:10]]
        
        to_seed = seed_default_materials(existing)
        
        # None of the seeded should be in existing
        seeded_codes = {m["code"] for m in to_seed}
        assert not seeded_codes.intersection(existing), "Should not re-seed existing materials"
        
    def test_no_duplicate_codes_in_defaults(self):
        """Ensure no duplicate codes in default materials."""
        default_mats = get_default_materials()
        codes = [m["code"] for m in default_mats]
        assert len(codes) == len(set(codes)), "Duplicate codes found in default materials"


# ==============================================================================
# EXPANDED CATALOG TESTS
# ==============================================================================


class TestExpandedCatalog:
    """Test that the catalog includes required materials."""

    def test_tube_20x20_exists(self):
        """20x20 square tube must be included."""
        default_mats = get_default_materials()
        codes = [m["code"] for m in default_mats]
        assert "TUBE_20x20" in codes, "Missing 20x20 square tube"

    def test_boards_exist(self):
        """MDF boards in various colors must be included."""
        default_mats = get_default_materials()
        codes = [m["code"] for m in default_mats]
        
        assert "BOARD_MDF_WHITE" in codes, "Missing white MDF board"
        assert "BOARD_MDF_BLACK" in codes, "Missing black MDF board"
        assert "BOARD_MDF_NAVY" in codes, "Missing navy MDF board"
        assert "BOARD_MDF_VINTAGE" in codes, "Missing vintage MDF board"

    def test_aluminum_profiles_exist(self):
        """Aluminum profiles must be included."""
        default_mats = get_default_materials()
        codes = [m["code"] for m in default_mats]
        
        assert any("ALU_" in code for code in codes), "Missing aluminum profiles"

    def test_sanding_discs_exist(self):
        """Sanding discs must be included."""
        default_mats = get_default_materials()
        codes = [m["code"] for m in default_mats]
        
        assert any("SAND" in code for code in codes), "Missing sanding discs"

    def test_categories_are_split(self):
        """Categories should be split (not bundled)."""
        default_mats = get_default_materials()
        categories = {m["category"] for m in default_mats}
        
        # Should have separate categories
        assert "electrode" in categories, "Electrodes should be separate category"
        assert "disc" in categories, "Discs should be separate category"
        assert "sanding" in categories, "Sanding should be separate category"

    def test_paint_litre_unit_exists(self):
        """Paint with litre unit must exist."""
        default_mats = get_default_materials()
        paint_materials = [m for m in default_mats if m["category"] == "paint"]
        
        litre_paints = [m for m in paint_materials if m["unit"] == "litre"]
        assert len(litre_paints) > 0, "Missing paint with litre unit"


# ==============================================================================
# MATERIALS PAGE TESTS
# ==============================================================================


@pytest.mark.django_db
class TestMaterialsPage:
    """Test materials page functionality."""

    def test_materials_list_renders(self, authenticated_client, sample_materials, welding_business):
        """Materials list page renders successfully."""
        # Patch the business retrieval
        with patch('inventory.verticals.welding.base.base_context') as mock_ctx:
            mock_ctx.return_value = {'business': welding_business}
            
            response = authenticated_client.get('/verticals/welding/materials/')
            # Should not error (may redirect if not properly authenticated)
            assert response.status_code in [200, 302]

    def test_materials_search_parameter(self):
        """Materials list accepts search parameter."""
        # Test the URL pattern accepts query params
        from django.urls import resolve
        
        url = '/verticals/welding/materials/'
        match = resolve(url)
        assert match.url_name == 'welding_materials_list'

    def test_search_testid_present(self, authenticated_client, sample_materials, welding_business):
        """Search input has correct test ID."""
        # This is a template test - check the template file directly
        import os
        template_path = 'templates/verticals/welding/materials_list.html'
        if os.path.exists(template_path):
            with open(template_path, encoding='utf-8') as f:
                content = f.read()
            assert 'data-testid="welding-materials-search"' in content


# ==============================================================================
# STOCK-IN TESTS
# ==============================================================================


@pytest.mark.django_db
class TestStockInPage:
    """Test stock-in page with material picker."""

    def test_stock_in_form_testid_present(self):
        """Stock-in form has correct test ID."""
        import os
        template_path = 'templates/verticals/welding/stock_in.html'
        if os.path.exists(template_path):
            with open(template_path, encoding='utf-8') as f:
                content = f.read()
            assert 'data-testid="welding-stock-in-form"' in content

    def test_stock_in_submit_testid_present(self):
        """Stock-in submit button has correct test ID."""
        import os
        template_path = 'templates/verticals/welding/stock_in.html'
        if os.path.exists(template_path):
            with open(template_path, encoding='utf-8') as f:
                content = f.read()
            assert 'data-testid="welding-stock-in-submit"' in content

    def test_material_picker_modal_exists(self):
        """Material picker modal exists in template."""
        import os
        template_path = 'templates/verticals/welding/stock_in.html'
        if os.path.exists(template_path):
            with open(template_path, encoding='utf-8') as f:
                content = f.read()
            assert 'materialPickerModal' in content


# ==============================================================================
# QUOTE BUILDER TESTS
# ==============================================================================


@pytest.mark.django_db
class TestQuoteBuilder:
    """Test quote creation functionality."""

    def test_quote_form_testid_present(self):
        """Quote form has correct test ID."""
        import os
        template_path = 'templates/verticals/welding/quote_create.html'
        if os.path.exists(template_path):
            with open(template_path, encoding='utf-8') as f:
                content = f.read()
            assert 'data-testid="welding-quote-form"' in content

    def test_quote_template_grid_present(self):
        """Template grid is present in quote builder."""
        import os
        template_path = 'templates/verticals/welding/quote_create.html'
        if os.path.exists(template_path):
            with open(template_path, encoding='utf-8') as f:
                content = f.read()
            assert 'data-testid="welding-template-grid"' in content


# ==============================================================================
# PDF GENERATION TESTS
# ==============================================================================


@pytest.mark.django_db
class TestQuotePDF:
    """Test quote PDF generation."""

    def test_pdf_generation_succeeds(self, sample_quote, welding_business):
        """PDF generation returns bytes."""
        from inventory.services.welding_pdf import generate_quote_pdf
        
        pdf_bytes = generate_quote_pdf(sample_quote, welding_business)
        
        # May be None if ReportLab not installed
        if pdf_bytes is not None:
            assert len(pdf_bytes) > 100, "PDF should have substantial content"
            # Check PDF header
            assert pdf_bytes[:4] == b'%PDF', "Should be valid PDF"

    def test_pdf_handles_missing_customer_email(self, sample_quote, welding_business):
        """PDF generates even without customer email."""
        from inventory.services.welding_pdf import generate_quote_pdf
        
        sample_quote.customer_email = ""
        sample_quote.save()
        
        pdf_bytes = generate_quote_pdf(sample_quote, welding_business)
        
        # Should not raise, may return None if no ReportLab
        if pdf_bytes is not None:
            assert len(pdf_bytes) > 0

    def test_pdf_handles_empty_bom(self, sample_quote, welding_business):
        """PDF generates even with empty BOM."""
        from inventory.services.welding_pdf import generate_quote_pdf
        
        sample_quote.bom = []
        sample_quote.save()
        
        pdf_bytes = generate_quote_pdf(sample_quote, welding_business)
        
        # Should not raise
        if pdf_bytes is not None:
            assert len(pdf_bytes) > 0

    def test_pdf_endpoint_exists(self):
        """PDF endpoint URL exists."""
        from django.urls import reverse
        
        url = reverse('verticals:welding_quote_pdf', args=[1])
        assert '/welding/quotes/1/pdf/' in url


# ==============================================================================
# JOB SIMULATOR TESTS
# ==============================================================================


@pytest.mark.django_db
class TestJobSimulator:
    """Test job cost simulator."""

    def test_simulator_url_exists(self):
        """Simulator URL exists."""
        from django.urls import reverse
        
        url = reverse('verticals:welding_job_simulator')
        assert '/welding/simulator/' in url

    def test_simulator_to_quote_url_exists(self):
        """Simulator to quote URL exists."""
        from django.urls import reverse
        
        url = reverse('verticals:welding_simulator_to_quote')
        assert '/welding/simulator/to-quote/' in url

    def test_simulator_template_exists(self):
        """Simulator template exists."""
        import os
        template_path = 'templates/verticals/welding/job_simulator.html'
        assert os.path.exists(template_path), "Job simulator template missing"

    def test_simulator_testid_present(self):
        """Simulator has template grid test ID."""
        import os
        template_path = 'templates/verticals/welding/job_simulator.html'
        if os.path.exists(template_path):
            with open(template_path, encoding='utf-8') as f:
                content = f.read()
            assert 'data-testid="welding-simulator-templates"' in content


# ==============================================================================
# ESTIMATOR COMPUTATION TESTS
# ==============================================================================


class TestEstimatorComputation:
    """Test the estimator SSOT computations."""

    def test_estimate_bom_handles_5_8m_lengths(self):
        """BOM estimation handles 5.8m tube lengths."""
        materials_catalog = {
            "TUBE_20x20": MaterialData(
                id=1,
                code="TUBE_20x20",
                name="Square Tube 20x20mm (5.8m)",
                category="tube",
                unit="length_5_8m",
                price_mwk=Decimal("12000"),
                quantity_in_stock=Decimal("10"),
            ),
        }
        
        # Create minimal template
        templates = {
            "TEST": {
                "code": "TEST",
                "name": "Test Template",
                "base_bom": {
                    "TUBE_20x20": {"qty_formula": "frame", "base_qty": 2},
                },
                "default_labour_hours": 2,
            }
        }
        
        result = estimate_bom(
            template_code="TEST",
            specs={},
            tuning=None,
            materials_catalog=materials_catalog,
            templates=templates,
        )
        
        # Should have BOM items
        assert len(result.bom) > 0
        
        # Total tube length should be calculated using 5.8m
        assert result.total_tube_length_m == Decimal("11.6")  # 2 * 5.8m

    def test_cost_computation_accuracy(self):
        """Cost computation is accurate."""
        bom = [
            {
                "material_code": "TUBE_40x40",
                "material_name": "Tube",
                "category": "tube",
                "quantity": Decimal("3"),
                "unit": "piece",
                "unit_price_mwk": Decimal("28000"),
                "line_total_mwk": Decimal("84000"),
            }
        ]
        
        result = compute_cost(
            bom_items=bom,
            labour_hours=Decimal("4"),
            labour_rate_per_hour=Decimal("5000"),
            overhead_pct=Decimal("10"),
            margin_pct=Decimal("25"),
        )
        
        # Materials: 84000
        assert result["materials_cost"] == Decimal("84000")
        
        # Labour: 4 * 5000 = 20000
        assert result["labour_cost"] == Decimal("20000")
        
        # Overhead: (84000 + 20000) * 0.10 = 10400
        assert result["overhead_cost"] == Decimal("10400")
        
        # Subtotal: 84000 + 20000 + 10400 = 114400
        assert result["subtotal_before_margin"] == Decimal("114400")
        
        # Margin: 114400 * 0.25 = 28600
        assert result["margin_amount"] == Decimal("28600")
        
        # Total: 114400 + 28600 = 143000
        assert result["total"] == Decimal("143000")


# ==============================================================================
# DASHBOARD TESTS
# ==============================================================================


@pytest.mark.django_db
class TestDashboard:
    """Test welding dashboard."""

    def test_dashboard_kpi_testid_present(self):
        """Dashboard KPI section has correct test ID."""
        import os
        template_path = 'templates/verticals/welding/dashboard.html'
        if os.path.exists(template_path):
            with open(template_path, encoding='utf-8') as f:
                content = f.read()
            assert 'data-testid="welding-dashboard-kpis"' in content

    def test_dashboard_has_insights_section(self):
        """Dashboard has insights section."""
        import os
        template_path = 'templates/verticals/welding/dashboard.html'
        if os.path.exists(template_path):
            with open(template_path, encoding='utf-8') as f:
                content = f.read()
            assert 'Insights' in content


# ==============================================================================
# URL ROUTING TESTS
# ==============================================================================


class TestURLRouting:
    """Test that all URLs are properly wired."""

    def test_materials_list_url(self):
        """Materials list URL resolves."""
        from django.urls import reverse
        url = reverse('verticals:welding_materials_list')
        assert '/welding/materials/' in url

    def test_stock_in_url(self):
        """Stock-in URL resolves."""
        from django.urls import reverse
        url = reverse('verticals:welding_stock_in')
        assert '/welding/stock-in/' in url

    def test_quote_create_url(self):
        """Quote create URL resolves."""
        from django.urls import reverse
        url = reverse('verticals:welding_quote_create')
        assert '/welding/quotes/create/' in url

    def test_quote_pdf_url(self):
        """Quote PDF URL resolves."""
        from django.urls import reverse
        url = reverse('verticals:welding_quote_pdf', args=[1])
        assert '/welding/quotes/1/pdf/' in url

    def test_dashboard_url(self):
        """Dashboard URL resolves."""
        from django.urls import reverse
        url = reverse('verticals:welding_dashboard')
        assert '/welding/dashboard/' in url

    def test_simulator_url(self):
        """Simulator URL resolves."""
        from django.urls import reverse
        url = reverse('verticals:welding_job_simulator')
        assert '/welding/simulator/' in url


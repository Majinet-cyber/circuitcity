from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings


User = get_user_model()


def tiny_gif(name="logo.gif"):
    return SimpleUploadedFile(
        name,
        b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02L\x01\x00;",
        content_type="image/gif",
    )


@pytest.fixture
def welding_business(db):
    from inventory.business_kinds import BusinessKind
    from tenants.models import Business

    return Business.objects.create(
        name="Brand Welding Ltd",
        kind=BusinessKind.WELDING,
        is_active=True,
    )


@pytest.fixture
def other_business(db):
    from inventory.business_kinds import BusinessKind
    from tenants.models import Business

    return Business.objects.create(
        name="Other Welding Ltd",
        kind=BusinessKind.WELDING,
        is_active=True,
    )


@pytest.fixture
def welding_manager(db, welding_business):
    from tenants.models import Membership

    user = User.objects.create_user(
        username="welding_brand_mgr",
        email="welding_brand_mgr@example.com",
        password="testpass123",
    )
    Membership.objects.create(user=user, business=welding_business, role="manager")
    return user


@pytest.fixture
def authenticated_client(welding_manager, welding_business):
    client = Client()
    client.force_login(welding_manager)
    session = client.session
    session["active_business_id"] = welding_business.id
    session.save()
    return client


@pytest.fixture
def quote(welding_business, welding_manager):
    from inventory.models_welding import WeldingQuote, WeldingQuoteStatus

    return WeldingQuote.objects.create(
        business=welding_business,
        quote_number="WQ-BRAND-001",
        customer_name="Site Customer",
        customer_phone="+265991234567",
        materials_cost=Decimal("50000"),
        labour_cost=Decimal("25000"),
        overhead_cost=Decimal("0"),
        subtotal=Decimal("75000"),
        total=Decimal("75000"),
        min_price=Decimal("75000"),
        status=WeldingQuoteStatus.DRAFT,
        created_by=welding_manager,
        bom=[
            {
                "material_name": "Gate frame",
                "quantity": "1",
                "unit": "each",
                "unit_price_mwk": "50000",
                "line_total_mwk": "50000",
            }
        ],
    )


@pytest.mark.django_db
class TestWeldingBrandingSettings:
    def test_branding_page_is_linked_from_dashboard_and_quote_create(self, authenticated_client):
        dashboard = authenticated_client.get("/verticals/welding/dashboard/")
        quote_create = authenticated_client.get("/verticals/welding/quotes/create/")

        assert dashboard.status_code == 200
        assert quote_create.status_code == 200
        assert "/verticals/welding/branding/" in dashboard.content.decode()
        assert "/verticals/welding/branding/" in quote_create.content.decode()

    def test_save_branding_with_logo_is_business_scoped(self, authenticated_client, welding_business, other_business, tmp_path):
        from inventory.models_welding import WeldingBrandingSettings

        with override_settings(MEDIA_ROOT=tmp_path):
            response = authenticated_client.post(
                "/verticals/welding/branding/",
                {
                    "company_name": "Bright Arc Fabricators",
                    "business_phone": "+265 999 111 222",
                    "business_email": "quotes@brightarc.test",
                    "business_address": "Area 47 Workshop",
                    "city": "Lilongwe",
                    "payment_instructions": "Bank: Bright Arc, Account 123",
                    "default_terms": "Deposit required before fabrication.",
                    "authorized_signature_name": "Grace Banda",
                    "company_logo": tiny_gif(),
                    "signature_image": tiny_gif("signature.gif"),
                },
            )

            assert response.status_code == 302
            settings = WeldingBrandingSettings.objects.get(business=welding_business)
            assert settings.company_name == "Bright Arc Fabricators"
            assert settings.company_logo.name
            assert settings.signature_image.name

            other_settings = WeldingBrandingSettings.objects.create(
                business=other_business,
                company_name="Should Not Leak",
                payment_instructions="Other bank details",
            )
            page = authenticated_client.get("/verticals/welding/branding/")
            html = page.content.decode()
            assert page.status_code == 200
            assert "Bright Arc Fabricators" in html
            assert other_settings.company_name not in html
            assert "Other bank details" not in html

    def test_quote_create_prefills_default_payment_and_terms(self, authenticated_client, welding_business):
        from inventory.models_welding import WeldingBrandingSettings

        WeldingBrandingSettings.objects.update_or_create(
            business=welding_business,
            defaults={
                "company_name": "Bright Arc Fabricators",
                "payment_instructions": "Pay to TNM Mpamba 0888000000",
                "default_terms": "Custom branded welding terms.",
            },
        )

        response = authenticated_client.get("/verticals/welding/quotes/create/")
        html = response.content.decode()
        assert response.status_code == 200
        assert "Pay to TNM Mpamba 0888000000" in html
        assert "Custom branded welding terms." in html

    def test_new_quote_saves_branding_snapshot(self, authenticated_client, welding_business):
        from inventory.models_welding import WeldingBrandingSettings, WeldingQuote

        WeldingBrandingSettings.objects.update_or_create(
            business=welding_business,
            defaults={
                "company_name": "Snapshot Welding Co",
                "business_phone": "+265 888 222 333",
                "payment_instructions": "Snapshot bank details",
                "default_terms": "Snapshot terms.",
                "authorized_signature_name": "Authorized Welder",
            },
        )

        response = authenticated_client.post(
            "/verticals/welding/quotes/create/",
            {
                "customer_name": "New Customer",
                "payment_details": "Override payment details",
                "terms": "Override quote terms.",
            },
        )

        assert response.status_code == 302
        quote = WeldingQuote.objects.get(business=welding_business, customer_name="New Customer")
        assert quote.branding_snapshot["company_name"] == "Snapshot Welding Co"
        assert quote.branding_snapshot["payment_instructions"] == "Snapshot bank details"
        assert quote.terms == "Override quote terms."
        assert quote.cost_breakdown["payment_details"] == "Override payment details"

    def test_print_view_uses_default_branding_and_logo_without_broken_fallback(
        self,
        authenticated_client,
        welding_business,
        quote,
        tmp_path,
    ):
        from inventory.models_welding import WeldingBrandingSettings

        with override_settings(MEDIA_ROOT=tmp_path):
            settings = WeldingBrandingSettings.objects.create(
                business=welding_business,
                company_name="Print Logo Welding",
                business_phone="+265 111 000",
                payment_instructions="Print bank details",
                default_terms="Print terms.",
                authorized_signature_name="Print Signatory",
            )
            settings.company_logo.save("print-logo.gif", tiny_gif(), save=True)

            response = authenticated_client.get(f"/verticals/welding/quotes/{quote.id}/print/")
            html = response.content.decode()

            assert response.status_code == 200
            assert 'class="brand-logo"' in html
            assert settings.company_logo.url in html
            assert "Print Logo Welding" in html
            assert "Print bank details" in html
            assert "Print Signatory" in html
            assert "broken" not in html.lower()

    def test_print_view_without_logo_uses_clean_text_fallback(self, authenticated_client, welding_business, quote):
        from inventory.models_welding import WeldingBrandingSettings

        WeldingBrandingSettings.objects.create(
            business=welding_business,
            company_name="Fallback Welding",
            payment_instructions="Fallback bank details",
        )

        response = authenticated_client.get(f"/verticals/welding/quotes/{quote.id}/print/")
        html = response.content.decode()

        assert response.status_code == 200
        assert 'class="brand-logo"' not in html
        assert 'class="brand-fallback"' in html
        assert "Fallback Welding" in html

    def test_pdf_export_works_with_uploaded_default_logo(
        self,
        authenticated_client,
        welding_business,
        quote,
        tmp_path,
    ):
        from inventory.models_welding import WeldingBrandingSettings

        with override_settings(MEDIA_ROOT=tmp_path):
            settings = WeldingBrandingSettings.objects.create(
                business=welding_business,
                company_name="PDF Logo Welding",
                payment_instructions="PDF bank details",
            )
            settings.company_logo.save("pdf-logo.gif", tiny_gif(), save=True)

            response = authenticated_client.get(f"/verticals/welding/quotes/{quote.id}/pdf/")

            assert response.status_code == 200
            assert response["Content-Type"] == "application/pdf"
            assert len(response.content) > 1000

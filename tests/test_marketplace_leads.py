from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from billing.models import BusinessSubscription
from inventory.models_marketplace import (
    ListingStatus,
    MarketplaceCommissionStatus,
    MarketplaceEnquiry,
    MarketplaceLead,
    MarketplaceLeadSource,
    MarketplaceLeadStatus,
    MarketplaceListing,
)


User = get_user_model()


def test_welding_sidebar_has_dedicated_seller_marketplace_button():
    from inventory.utils_verticals import get_vertical_sidebar_items

    items = get_vertical_sidebar_items("welding")
    marketplace = next((item for item in items if item.get("key") == "marketplace"), None)

    assert marketplace is not None
    assert marketplace["label"] == "Marketplace"
    assert marketplace["url"] == "inventory:manage_listings"
    assert marketplace["icon"] in {"bi-shop", "bi-shop-window", "bi-cart"}
    assert marketplace["require_manager"] is True


@pytest.fixture
def seller_business(db):
    from inventory.business_kinds import BusinessKind
    from tenants.models import Business

    return Business.objects.create(
        name="Lead Seller",
        kind=BusinessKind.WELDING,
        is_active=True,
    )


@pytest.fixture
def other_business(db):
    from inventory.business_kinds import BusinessKind
    from tenants.models import Business

    return Business.objects.create(
        name="Other Seller",
        kind=BusinessKind.WELDING,
        is_active=True,
    )


@pytest.fixture
def seller_user(db, seller_business):
    from tenants.models import Membership

    user = User.objects.create_user("lead_seller", "seller@example.com", "testpass123")
    Membership.objects.create(user=user, business=seller_business, role="manager")
    return user


@pytest.fixture
def seller_client(seller_user, seller_business):
    client = Client()
    client.force_login(seller_user)
    session = client.session
    session["active_business_id"] = seller_business.id
    session.save()
    return client


@pytest.fixture
def hq_client(db):
    user = User.objects.create_superuser("hq_marketplace_leads", "hq@example.com", "testpass123")
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def listing(seller_business, seller_user):
    return MarketplaceListing.objects.create(
        business=seller_business,
        title="Custom Steel Gate",
        description="Made to measure.",
        price=Decimal("250000"),
        status=ListingStatus.LIVE,
        contact_phone="+265999111222",
        contact_email="sales@example.com",
        vertical="welding",
        created_by=seller_user,
    )


@pytest.mark.django_db
class TestMarketplaceLeadCapture:
    def test_request_quote_creates_enquiry_and_lead(self, listing):
        client = Client()
        response = client.post(
            reverse("inventory:submit_enquiry", args=[listing.pk]),
            {
                "name": "John Banda",
                "phone": "+265888000111",
                "email": "john@example.com",
                "message": "Please quote delivery.",
            },
            HTTP_REFERER=f"/marketplace/{listing.business.slug}/{listing.listing_slug}/",
        )

        assert response.status_code == 302
        assert MarketplaceEnquiry.objects.filter(listing=listing).count() == 1
        lead = MarketplaceLead.objects.get(listing=listing)
        assert lead.seller_business == listing.business
        assert lead.customer_name == "John Banda"
        assert lead.customer_phone == "+265888000111"
        assert lead.customer_email == "john@example.com"
        assert lead.customer_message == "Please quote delivery."
        assert lead.source_type == MarketplaceLeadSource.QUOTE_REQUEST
        assert lead.status == MarketplaceLeadStatus.NEW
        assert lead.commission_percentage == Decimal("5.00")

    def test_request_quote_does_not_create_business_or_subscription(self, listing):
        client = Client()
        business_count = listing.business.__class__.objects.count()
        subscription_count = BusinessSubscription.objects.count()

        response = client.post(
            reverse("inventory:submit_enquiry", args=[listing.pk]),
            {
                "name": "No Tenant",
                "phone": "+265888000222",
                "email": "no-tenant@example.com",
                "message": "Do not create a tenant business.",
            },
        )

        assert response.status_code == 302
        assert listing.business.__class__.objects.count() == business_count
        assert BusinessSubscription.objects.count() == subscription_count
        assert MarketplaceLead.objects.filter(customer_email="no-tenant@example.com").exists()

    def test_contact_click_creates_deduped_lead(self, listing):
        client = Client()
        url = reverse("inventory:marketplace_contact_click", args=[listing.pk, "whatsapp"])

        first = client.get(url)
        second = client.get(url)

        assert first.status_code == 302
        assert second.status_code == 302
        assert first["Location"].startswith("https://wa.me/")
        assert MarketplaceLead.objects.filter(
            listing=listing,
            source_type=MarketplaceLeadSource.WHATSAPP_CLICK,
        ).count() == 1

    @pytest.mark.parametrize(
        ("kind", "source_type", "redirect_prefix"),
        [
            ("phone", MarketplaceLeadSource.PHONE_CLICK, "tel:"),
            ("email", MarketplaceLeadSource.EMAIL_CLICK, "mailto:"),
        ],
    )
    def test_phone_and_email_clicks_create_leads(self, listing, kind, source_type, redirect_prefix):
        client = Client()

        response = client.get(reverse("inventory:marketplace_contact_click", args=[listing.pk, kind]))

        assert response.status_code == 302
        assert response["Location"].startswith(redirect_prefix)
        assert MarketplaceLead.objects.filter(listing=listing, source_type=source_type).count() == 1

    def test_placeholder_business_is_not_linked_as_seller(self, db, seller_user):
        from inventory.business_kinds import BusinessKind
        from tenants.models import Business

        fake_business = Business.objects.create(
            name="Marketplace Leads",
            slug="marketplace-leads",
            kind=BusinessKind.WELDING,
            is_active=True,
        )
        listing = MarketplaceListing.objects.create(
            business=fake_business,
            title="Placeholder Listing",
            status=ListingStatus.LIVE,
            vertical="welding",
            created_by=seller_user,
        )

        client = Client()
        response = client.post(
            reverse("inventory:submit_enquiry", args=[listing.pk]),
            {
                "name": "Safe Customer",
                "phone": "+265888000333",
                "email": "safe@example.com",
                "message": "Store without fake seller business.",
            },
        )

        assert response.status_code == 302
        lead = MarketplaceLead.objects.get(customer_email="safe@example.com")
        assert lead.seller_business is None


@pytest.mark.django_db
class TestSellerMarketplaceLeads:
    def test_seller_sees_only_own_business_leads(self, seller_client, listing, other_business):
        other_listing = MarketplaceListing.objects.create(
            business=other_business,
            title="Other Gate",
            status=ListingStatus.LIVE,
            vertical="welding",
        )
        MarketplaceLead.objects.create(
            listing=listing,
            seller_business=listing.business,
            customer_name="Visible Customer",
            source_type=MarketplaceLeadSource.QUOTE_REQUEST,
        )
        MarketplaceLead.objects.create(
            listing=other_listing,
            seller_business=other_business,
            customer_name="Hidden Customer",
            source_type=MarketplaceLeadSource.QUOTE_REQUEST,
        )

        response = seller_client.get(reverse("inventory:marketplace_leads"))
        html = response.content.decode()

        assert response.status_code == 200
        assert "Visible Customer" in html
        assert "Hidden Customer" not in html

    def test_seller_marks_lead_won_and_commission_is_calculated(self, seller_client, listing):
        lead = MarketplaceLead.objects.create(
            listing=listing,
            seller_business=listing.business,
            customer_name="Winning Customer",
            source_type=MarketplaceLeadSource.QUOTE_REQUEST,
        )

        response = seller_client.post(
            reverse("inventory:marketplace_lead_update", args=[lead.pk]),
            {
                "status": MarketplaceLeadStatus.WON,
                "deal_amount": "100000",
                "notes": "Closed by phone.",
            },
            HTTP_REFERER=reverse("inventory:marketplace_leads"),
        )

        assert response.status_code == 302
        lead.refresh_from_db()
        assert lead.status == MarketplaceLeadStatus.WON
        assert lead.deal_amount == Decimal("100000.00")
        assert lead.commission_percentage == Decimal("5.00")
        assert lead.commission_amount == Decimal("5000.00")
        assert lead.commission_status == MarketplaceCommissionStatus.DUE
        assert lead.converted_at is not None

    def test_seller_cannot_mark_commission_paid(self, seller_client, listing):
        lead = MarketplaceLead.objects.create(
            listing=listing,
            seller_business=listing.business,
            customer_name="Winning Customer",
            source_type=MarketplaceLeadSource.QUOTE_REQUEST,
            status=MarketplaceLeadStatus.WON,
            deal_amount=Decimal("100000"),
        )

        response = seller_client.post(
            reverse("inventory:marketplace_lead_update", args=[lead.pk]),
            {
                "status": MarketplaceLeadStatus.WON,
                "deal_amount": "100000",
                "commission_status": MarketplaceCommissionStatus.PAID,
                "commission_percentage": "1",
            },
            HTTP_REFERER=reverse("inventory:marketplace_leads"),
        )

        assert response.status_code == 302
        lead.refresh_from_db()
        assert lead.commission_percentage == Decimal("5.00")
        assert lead.commission_status == MarketplaceCommissionStatus.DUE

    def test_seller_cannot_override_won_deal_amount(self, seller_client, listing):
        lead = MarketplaceLead.objects.create(
            listing=listing,
            seller_business=listing.business,
            source_type=MarketplaceLeadSource.QUOTE_REQUEST,
            status=MarketplaceLeadStatus.WON,
            deal_amount=Decimal("100000"),
        )

        response = seller_client.post(
            reverse("inventory:marketplace_lead_update", args=[lead.pk]),
            {
                "status": MarketplaceLeadStatus.WON,
                "deal_amount": "120000",
            },
            HTTP_REFERER=reverse("inventory:marketplace_leads"),
        )

        assert response.status_code == 302
        lead.refresh_from_db()
        assert lead.deal_amount == Decimal("100000.00")
        assert lead.commission_amount == Decimal("5000.00")

    def test_won_requires_deal_amount(self, seller_client, listing):
        lead = MarketplaceLead.objects.create(
            listing=listing,
            seller_business=listing.business,
            source_type=MarketplaceLeadSource.QUOTE_REQUEST,
        )

        response = seller_client.post(
            reverse("inventory:marketplace_lead_update", args=[lead.pk]),
            {"status": MarketplaceLeadStatus.WON},
            HTTP_REFERER=reverse("inventory:marketplace_leads"),
        )

        assert response.status_code == 302
        lead.refresh_from_db()
        assert lead.status == MarketplaceLeadStatus.NEW
        assert lead.commission_status == MarketplaceCommissionStatus.NOT_APPLICABLE


@pytest.mark.django_db
class TestHQMarketplaceLeadDashboard:
    def test_hq_dashboard_shows_all_leads_and_metrics(self, hq_client, listing, other_business):
        other_listing = MarketplaceListing.objects.create(
            business=other_business,
            title="Other Listing",
            status=ListingStatus.LIVE,
            vertical="farm",
        )
        MarketplaceLead.objects.create(
            listing=listing,
            seller_business=listing.business,
            customer_name="Won Customer",
            source_type=MarketplaceLeadSource.QUOTE_REQUEST,
            status=MarketplaceLeadStatus.WON,
            deal_amount=Decimal("200000"),
        )
        MarketplaceLead.objects.create(
            listing=other_listing,
            seller_business=other_business,
            customer_name="Other Customer",
            source_type=MarketplaceLeadSource.PHONE_CLICK,
        )

        response = hq_client.get(reverse("hq:marketplace_leads"))
        html = response.content.decode()

        assert response.status_code == 200
        assert "Won Customer" in html
        assert "Other Customer" in html
        assert "MWK 200,000" in html
        assert "MWK 10,000" in html

    def test_hq_can_override_commission_and_mark_paid(self, hq_client, listing):
        lead = MarketplaceLead.objects.create(
            listing=listing,
            seller_business=listing.business,
            source_type=MarketplaceLeadSource.QUOTE_REQUEST,
            status=MarketplaceLeadStatus.WON,
            deal_amount=Decimal("100000"),
        )

        response = hq_client.post(
            reverse("hq:marketplace_lead_update", args=[lead.pk]),
            {
                "status": MarketplaceLeadStatus.WON,
                "deal_amount": "100000",
                "commission_percentage": "4",
                "commission_amount": "3000",
                "commission_status": MarketplaceCommissionStatus.PENDING,
                "hq_notes": "Promo override.",
            },
        )

        assert response.status_code == 302
        lead.refresh_from_db()
        assert lead.commission_percentage == Decimal("4.00")
        assert lead.commission_amount == Decimal("3000.00")
        assert lead.commission_amount_overridden is True
        assert lead.commission_status == MarketplaceCommissionStatus.PENDING

        paid = hq_client.post(reverse("hq:marketplace_lead_mark_paid", args=[lead.pk]))
        assert paid.status_code == 302
        lead.refresh_from_db()
        assert lead.commission_status == MarketplaceCommissionStatus.PAID
        assert lead.commission_paid_at is not None
        assert lead.commission_paid_by is not None

    def test_hq_cannot_mark_non_won_lead_paid(self, hq_client, listing):
        lead = MarketplaceLead.objects.create(
            listing=listing,
            seller_business=listing.business,
            source_type=MarketplaceLeadSource.QUOTE_REQUEST,
            status=MarketplaceLeadStatus.NEW,
        )

        response = hq_client.post(reverse("hq:marketplace_lead_mark_paid", args=[lead.pk]))

        assert response.status_code == 302
        lead.refresh_from_db()
        assert lead.commission_status == MarketplaceCommissionStatus.NOT_APPLICABLE

    def test_non_won_lead_cannot_keep_commission_override(self, hq_client, listing):
        lead = MarketplaceLead.objects.create(
            listing=listing,
            seller_business=listing.business,
            source_type=MarketplaceLeadSource.QUOTE_REQUEST,
            status=MarketplaceLeadStatus.NEW,
        )

        response = hq_client.post(
            reverse("hq:marketplace_lead_update", args=[lead.pk]),
            {
                "status": MarketplaceLeadStatus.CONTACTED,
                "commission_amount": "3000",
                "commission_status": MarketplaceCommissionStatus.PENDING,
            },
        )

        assert response.status_code == 302
        lead.refresh_from_db()
        assert lead.status == MarketplaceLeadStatus.CONTACTED
        assert lead.commission_amount == Decimal("0.00")
        assert lead.commission_amount_overridden is False
        assert lead.commission_status == MarketplaceCommissionStatus.NOT_APPLICABLE

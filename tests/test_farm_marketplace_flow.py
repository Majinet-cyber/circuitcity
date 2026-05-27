"""
Farm marketplace: subtypes, batch detail, publish sync, dashboard extras.
"""
from __future__ import annotations

import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from inventory.models_farm import (
    FarmLivestockBatch,
    FarmLivestockSubType,
    FarmAnimalType,
    subtype_choices_for_animal_type,
)
from inventory.models_marketplace import ListingStatus, MarketplaceListing
from inventory.services.farm_marketplace import build_livestock_listing_title, build_livestock_vertical_metadata
from tenants.models import Business, Membership


User = get_user_model()


@pytest.fixture
def farm_setup(db):
    user = User.objects.create_user(username="fmp1", email="fmp1@test.com", password="x" * 12)
    business = Business.objects.create(
        name="Farm Test Co",
        slug="farm-test-co-qq",
        business_kind="farm",
        status="ACTIVE",
        currency="MWK",
        created_by=user,
    )
    Membership.objects.create(user=user, business=business, role="MANAGER", status="ACTIVE")
    return user, business


@pytest.mark.django_db
def test_subtype_choices_chicken_includes_broilers():
    ch = {c[0] for c in subtype_choices_for_animal_type("chickens")}
    assert FarmLivestockSubType.CHICKEN_BROILERS in ch


@pytest.mark.django_db
def test_farm_batch_margin_band_risky(farm_setup):
    _, business = farm_setup
    b = FarmLivestockBatch.objects.create(
        business=business,
        name="Q",
        animal_type=FarmAnimalType.PIGS,
        animal_subtype=FarmLivestockSubType.PIG_LOCAL,
        count_current=5,
        cost_basis_per_head_mwk=Decimal("10000"),
        expected_sale_price_mwk=Decimal("5000"),
    )
    assert b.margin_band == "risky"


@pytest.mark.django_db
def test_farm_listing_title_and_metadata_keys(farm_setup):
    _, business = farm_setup
    b = FarmLivestockBatch.objects.create(
        business=business,
        name="B1",
        animal_type=FarmAnimalType.CHICKENS,
        animal_subtype=FarmLivestockSubType.CHICKEN_BROILERS,
        count_current=20,
    )
    t = build_livestock_listing_title(b)
    assert "B1" in t
    m = build_livestock_vertical_metadata(b)
    assert "quantity" in m
    assert m.get("unit") == "head"


@pytest.mark.django_db
def test_batch_detail_loads_farm(farm_setup):
    user, business = farm_setup
    b = FarmLivestockBatch.objects.create(
        business=business,
        name="B2",
        animal_type=FarmAnimalType.CATTLE,
        animal_subtype=FarmLivestockSubType.CATTLE_LOCAL,
    )
    client = Client()
    assert client.login(username="fmp1", password="x" * 12)
    s = client.session
    s["active_business_id"] = business.pk
    s.save()
    r = client.get(
        reverse("verticals:farm_livestock_detail", args=[b.pk]), HTTP_HOST="testserver", secure=False
    )
    assert r.status_code == 200
    assert b"marketplace" in r.content.lower() or b"Marketplace" in r.content


@pytest.mark.django_db
def test_sync_livestock_creates_listing(farm_setup):
    from inventory.services.farm_marketplace import sync_livestock_batch_to_marketplace

    user, business = farm_setup
    b = FarmLivestockBatch.objects.create(
        business=business,
        name="B3",
        animal_type=FarmAnimalType.PIGS,
        animal_subtype=FarmLivestockSubType.PIG_GROWERS,
        count_current=3,
        expected_sale_price_mwk=Decimal("50000"),
    )
    sync_livestock_batch_to_marketplace(b, user, business)
    b.refresh_from_db()
    assert b.marketplace_listing_id
    l = b.marketplace_listing
    assert l.status in (ListingStatus.LIVE, ListingStatus.DRAFT, ListingStatus.OUT_OF_STOCK)
    assert isinstance(l, MarketplaceListing)

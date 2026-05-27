import pytest
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct
from tenants.models import Business, Membership

User = get_user_model()


@pytest.mark.django_db
class TestCementBrandAndPaymentUI(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="cement_brand_ui", email="brandui@cement.test", password="test1234"
        )
        self.business = Business.objects.create(
            name="Cement UI Test",
            slug="cement-ui-test",
            business_kind=BusinessKind.CEMENT,
            status="ACTIVE",
        )
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER", status="ACTIVE")
        self.client = Client()
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_brand_step_deduplicates_and_human_labels(self):
        MerchProduct.objects.create(
            business=self.business,
            name="Dangote Cement BAG (50KG)",
            kind=BusinessKind.CEMENT,
            category="cement",
            spec_label="",
            base_unit="bag",
            cost_price=Decimal("25000"),
            selling_price=Decimal("30000"),
            quantity_in_stock=10,
            is_active=True,
            track_inventory=True,
        )
        MerchProduct.objects.create(
            business=self.business,
            name="Dangote",
            kind=BusinessKind.CEMENT,
            category="cement",
            spec_label="",
            base_unit="",
            cost_price=Decimal("0"),
            selling_price=Decimal("0"),
            quantity_in_stock=0,
            is_active=True,
            track_inventory=True,
        )

        response = self.client.get(reverse("cement:sell") + "?step=1")
        content = response.content.decode("utf-8")

        assert response.status_code == 200
        assert "Dangote" in content
        assert "Dangote Cement BAG (50KG)" not in content
        assert "dangote_cement_bag_(50kg)" not in content

    def test_products_page_renders_cards(self):
        MerchProduct.objects.create(
            business=self.business,
            name="Akshar Cement BAG (50KG)",
            kind=BusinessKind.CEMENT,
            category="cement",
            spec_label="",
            base_unit="bag",
            cost_price=Decimal("24000"),
            selling_price=Decimal("28000"),
            quantity_in_stock=6,
            is_active=True,
            track_inventory=True,
        )

        response = self.client.get(reverse("cement:stock_list"))
        content = response.content.decode("utf-8")

        assert response.status_code == 200
        assert "Warehouse Score" in content
        assert "card h-100" in content

    def test_payment_method_cards_render(self):
        product = MerchProduct.objects.create(
            business=self.business,
            name="Njati Cement BAG (50KG)",
            kind=BusinessKind.CEMENT,
            category="cement",
            spec_label="",
            base_unit="bag",
            cost_price=Decimal("23000"),
            selling_price=Decimal("27000"),
            quantity_in_stock=8,
            is_active=True,
            track_inventory=True,
        )

        session = self.client.session
        session["cement_sell_brand"] = "Njati"
        session["cement_sell_brand_label"] = "Njati"
        session["cement_sell_brand_key"] = "njati"
        session["cement_sell_product_id"] = product.id
        session.save()

        response = self.client.get(reverse("cement:sell") + "?step=3")
        content = response.content.decode("utf-8")

        assert response.status_code == 200
        assert 'name="payment_method"' in content
        assert "payment-card" in content
        assert "<select" not in content


# tests/test_car_dealer_vertical.py
"""
Tests for the Car Dealer vertical: models, views, and URLs.
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.models_car_dealer import CarMake, CarModel, CarDealerVehicle

User = get_user_model()


def _make_business(slug="test-dealer"):
    return Business.objects.create(
        name=f"Car Dealer {slug}",
        slug=slug,
        business_kind="car_dealer",
    )


def _make_user(username="dealer_mgr"):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="testpass123",
    )


def _make_membership(user, business, role="manager"):
    return Membership.objects.create(
        user=user,
        business=business,
        role=role,
        status="ACTIVE",
    )


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class CarMakeModelTests(TestCase):
    def test_create_make(self):
        make = CarMake.objects.create(name="Toyota")
        self.assertEqual(make.name, "Toyota")

    def test_slug_auto_generated(self):
        make = CarMake.objects.create(name="Land Rover")
        self.assertEqual(make.slug, "land-rover")

    def test_str_returns_name(self):
        make = CarMake.objects.create(name="Mazda")
        self.assertEqual(str(make), "Mazda")

    def test_unique_name(self):
        CarMake.objects.create(name="Honda")
        with self.assertRaises(Exception):
            CarMake.objects.create(name="Honda")


@pytest.mark.django_db
class CarModelModelTests(TestCase):
    def setUp(self):
        self.make = CarMake.objects.create(name="Toyota")

    def test_create_model(self):
        car_model = CarModel.objects.create(make=self.make, name="Corolla")
        self.assertEqual(car_model.name, "Corolla")
        self.assertEqual(car_model.make, self.make)

    def test_str_includes_make_and_model(self):
        car_model = CarModel.objects.create(make=self.make, name="Axio")
        self.assertIn("Toyota", str(car_model))
        self.assertIn("Axio", str(car_model))

    def test_slug_auto_generated(self):
        car_model = CarModel.objects.create(make=self.make, name="Hilux")
        self.assertEqual(car_model.slug, "hilux")

    def test_unique_together_make_name(self):
        CarModel.objects.create(make=self.make, name="Corolla")
        with self.assertRaises(Exception):
            CarModel.objects.create(make=self.make, name="Corolla")


@pytest.mark.django_db
class CarDealerVehicleModelTests(TestCase):
    def setUp(self):
        self.business = _make_business()
        self.make = CarMake.objects.create(name="Toyota")
        self.car_model = CarModel.objects.create(make=self.make, name="Corolla")

    def test_create_vehicle_with_catalog_refs(self):
        vehicle = CarDealerVehicle.objects.create(
            business=self.business,
            make=self.make,
            model=self.car_model,
            year=2018,
            selling_price=Decimal("3500000"),
        )
        self.assertEqual(vehicle.make, self.make)
        self.assertEqual(vehicle.model, self.car_model)
        self.assertEqual(vehicle.year, 2018)

    def test_create_vehicle_with_free_text(self):
        vehicle = CarDealerVehicle.objects.create(
            business=self.business,
            make_text="Mitsubishi",
            model_text="L200",
            year=2016,
        )
        self.assertEqual(vehicle.make_text, "Mitsubishi")
        self.assertIsNone(vehicle.make)

    def test_default_status_is_in_stock(self):
        vehicle = CarDealerVehicle.objects.create(business=self.business)
        self.assertEqual(vehicle.status, CarDealerVehicle.VehicleStatus.IN_STOCK)

    def test_display_name_with_catalog(self):
        vehicle = CarDealerVehicle.objects.create(
            business=self.business,
            make=self.make,
            model=self.car_model,
            year=2020,
            trim="GL",
        )
        name = vehicle.display_name
        self.assertIn("Toyota", name)
        self.assertIn("Corolla", name)
        self.assertIn("2020", name)

    def test_display_name_with_free_text(self):
        vehicle = CarDealerVehicle.objects.create(
            business=self.business,
            make_text="Ford",
            model_text="Ranger",
            year=2019,
        )
        name = vehicle.display_name
        self.assertIn("Ford", name)
        self.assertIn("Ranger", name)

    def test_is_available_true_when_in_stock(self):
        vehicle = CarDealerVehicle.objects.create(
            business=self.business,
            status=CarDealerVehicle.VehicleStatus.IN_STOCK,
        )
        self.assertTrue(vehicle.is_available)

    def test_is_available_false_when_sold(self):
        vehicle = CarDealerVehicle.objects.create(
            business=self.business,
            status=CarDealerVehicle.VehicleStatus.SOLD,
        )
        self.assertFalse(vehicle.is_available)

    def test_mark_sold_updates_status(self):
        vehicle = CarDealerVehicle.objects.create(
            business=self.business,
            selling_price=Decimal("4000000"),
        )
        vehicle.mark_sold(
            buyer_name="John Banda",
            buyer_phone="+265991234567",
            sale_price=Decimal("3800000"),
            payment_method="CASH",
        )
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.status, CarDealerVehicle.VehicleStatus.SOLD)
        self.assertEqual(vehicle.buyer_name, "John Banda")
        self.assertEqual(vehicle.sale_price, Decimal("3800000"))
        self.assertIsNotNone(vehicle.sold_at)

    def test_tenant_isolation(self):
        business2 = _make_business(slug="dealer-2")
        v1 = CarDealerVehicle.objects.create(business=self.business, make_text="Toyota")
        v2 = CarDealerVehicle.objects.create(business=business2, make_text="Honda")

        self.assertEqual(
            CarDealerVehicle.objects.filter(business=self.business).count(), 1
        )
        self.assertEqual(
            CarDealerVehicle.objects.filter(business=business2).count(), 1
        )


# ---------------------------------------------------------------------------
# View Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class CarDealerDashboardViewTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.business = _make_business()
        _make_membership(self.user, self.business)
        self.client = Client()
        self.client.login(username="dealer_mgr", password="testpass123")

    def test_dashboard_requires_auth(self):
        anon = Client()
        url = reverse("car_dealer:dashboard")
        response = anon.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url.lower())

    def test_dashboard_returns_200_for_manager(self):
        url = reverse("car_dealer:dashboard")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


@pytest.mark.django_db
class CarDealerVehicleListViewTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.business = _make_business()
        _make_membership(self.user, self.business)
        self.make = CarMake.objects.create(name="Toyota")
        self.car_model = CarModel.objects.create(make=self.make, name="Corolla")
        CarDealerVehicle.objects.create(
            business=self.business,
            make=self.make,
            model=self.car_model,
            year=2019,
            selling_price=Decimal("3500000"),
        )
        self.client = Client()
        self.client.login(username="dealer_mgr", password="testpass123")

    def test_vehicle_list_returns_200(self):
        url = reverse("car_dealer:vehicle_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_vehicle_list_shows_vehicles(self):
        url = reverse("car_dealer:vehicle_list")
        response = self.client.get(url)
        self.assertContains(response, "Corolla")

    def test_vehicle_list_requires_auth(self):
        anon = Client()
        url = reverse("car_dealer:vehicle_list")
        response = anon.get(url)
        self.assertEqual(response.status_code, 302)


@pytest.mark.django_db
class CarDealerStockInViewTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.business = _make_business()
        _make_membership(self.user, self.business)
        self.client = Client()
        self.client.login(username="dealer_mgr", password="testpass123")

    def test_stock_in_page_returns_200(self):
        url = reverse("car_dealer:stock_in")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_stock_in_requires_auth(self):
        anon = Client()
        url = reverse("car_dealer:stock_in")
        response = anon.get(url)
        self.assertEqual(response.status_code, 302)

    def test_stock_in_creates_vehicle(self):
        url = reverse("car_dealer:stock_in")
        data = {
            "make_text": "Toyota",
            "model_text": "Corolla",
            "year": "2019",
            "selling_price": "3500000",
            "condition": "used",
        }
        response = self.client.post(url, data, follow=True)
        self.assertEqual(CarDealerVehicle.objects.filter(business=self.business).count(), 1)


@pytest.mark.django_db
class CarDealerVehicleDetailViewTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.business = _make_business()
        _make_membership(self.user, self.business)
        self.vehicle = CarDealerVehicle.objects.create(
            business=self.business,
            make_text="Toyota",
            model_text="Hilux",
            year=2021,
            selling_price=Decimal("8000000"),
        )
        self.client = Client()
        self.client.login(username="dealer_mgr", password="testpass123")

    def test_vehicle_detail_returns_200(self):
        url = reverse("car_dealer:vehicle_detail", args=[self.vehicle.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_vehicle_detail_shows_vehicle_info(self):
        url = reverse("car_dealer:vehicle_detail", args=[self.vehicle.pk])
        response = self.client.get(url)
        self.assertContains(response, "Hilux")

    def test_vehicle_detail_404_for_other_business(self):
        other_user = _make_user("other_mgr")
        other_biz = _make_business("other-dealer")
        _make_membership(other_user, other_biz)
        other_client = Client()
        other_client.login(username="other_mgr", password="testpass123")

        url = reverse("car_dealer:vehicle_detail", args=[self.vehicle.pk])
        response = other_client.get(url)
        self.assertEqual(response.status_code, 404)


@pytest.mark.django_db
class CarDealerSellVehicleViewTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.business = _make_business()
        _make_membership(self.user, self.business)
        self.vehicle = CarDealerVehicle.objects.create(
            business=self.business,
            make_text="Toyota",
            model_text="Axio",
            year=2017,
            selling_price=Decimal("2800000"),
            status=CarDealerVehicle.VehicleStatus.IN_STOCK,
        )
        self.client = Client()
        self.client.login(username="dealer_mgr", password="testpass123")

    def test_sell_page_returns_200(self):
        url = reverse("car_dealer:sell_vehicle", args=[self.vehicle.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_sell_marks_vehicle_sold(self):
        url = reverse("car_dealer:sell_vehicle", args=[self.vehicle.pk])
        response = self.client.post(url, {
            "sale_price": "2700000",
            "buyer_name": "John Phiri",
            "buyer_phone": "+265991234567",
            "payment_method": "CASH",
        }, follow=True)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, CarDealerVehicle.VehicleStatus.SOLD)
        self.assertEqual(self.vehicle.buyer_name, "John Phiri")

    def test_sell_requires_auth(self):
        anon = Client()
        url = reverse("car_dealer:sell_vehicle", args=[self.vehicle.pk])
        response = anon.post(url, {"sale_price": "2700000"})
        self.assertEqual(response.status_code, 302)

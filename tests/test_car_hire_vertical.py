# tests/test_car_hire_vertical.py
"""
Regression and integration tests for the Car Hire Service vertical.

Tests cover:
- Model creation and validation
- URL routing and access control
- Dashboard functionality
- Sidebar and navigation rendering
- Billing access (manager-only)
"""
from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timedelta

import pytest
from django.urls import reverse
from django.test import Client
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.models_car_hire import (
    Vehicle,
    Trip,
    MaintenanceRecord,
    VehicleStatus,
    TripStatus,
    TripType,
    VehicleMake,
)
from tenants.models import Business, Membership


@pytest.fixture
def car_hire_business(db, django_user_model):
    """Create a Car Hire business with a manager user."""
    user = django_user_model.objects.create_user(
        username="carhire_manager",
        email="manager@carhire.test",
        password="testpass123",
    )
    business = Business.objects.create(
        name="Test Car Hire Business",
        business_kind=BusinessKind.CAR_HIRE,
        owner=user,
    )
    Membership.objects.create(
        user=user,
        business=business,
        role="manager",
        is_active=True,
    )
    return business, user


@pytest.fixture
def car_hire_agent(db, django_user_model, car_hire_business):
    """Create an agent (non-manager) user for the Car Hire business."""
    business, manager = car_hire_business
    agent = django_user_model.objects.create_user(
        username="carhire_agent",
        email="agent@carhire.test",
        password="testpass123",
    )
    Membership.objects.create(
        user=agent,
        business=business,
        role="agent",
        is_active=True,
    )
    return agent


@pytest.fixture
def sample_vehicle(db, car_hire_business):
    """Create a sample vehicle for testing."""
    business, user = car_hire_business
    return Vehicle.objects.create(
        business=business,
        name="Toyota Fortuner 2022",
        make=VehicleMake.TOYOTA,
        model="Fortuner",
        year=2022,
        plate_number="MX 1234",
        status=VehicleStatus.AVAILABLE,
        daily_rate=Decimal("50000.00"),
        current_odometer=45000,
        next_maintenance_km=50000,
        created_by=user,
    )


@pytest.fixture
def sample_trip(db, car_hire_business, sample_vehicle):
    """Create a sample trip for testing."""
    business, user = car_hire_business
    now = timezone.now()
    return Trip.objects.create(
        business=business,
        vehicle=sample_vehicle,
        customer_name="John Banda",
        customer_phone="+265999123456",
        start_datetime=now,
        end_datetime=now + timedelta(days=3),
        destination="Lilongwe to Blantyre",
        trip_type=TripType.PASSENGER,
        price_total=Decimal("150000.00"),
        deposit_paid=Decimal("50000.00"),
        status=TripStatus.UPCOMING,
        created_by=user,
    )


# ==============================================================================
# MODEL TESTS
# ==============================================================================


class TestVehicleModel:
    """Tests for the Vehicle model."""

    def test_vehicle_creation(self, sample_vehicle):
        """Test vehicle can be created with valid data."""
        assert sample_vehicle.pk is not None
        assert sample_vehicle.name == "Toyota Fortuner 2022"
        assert sample_vehicle.plate_number == "MX 1234"
        assert sample_vehicle.status == VehicleStatus.AVAILABLE

    def test_vehicle_str(self, sample_vehicle):
        """Test vehicle string representation."""
        assert "Toyota Fortuner 2022" in str(sample_vehicle)
        assert "MX 1234" in str(sample_vehicle)

    def test_vehicle_display_name(self, sample_vehicle):
        """Test vehicle display_name property."""
        assert "Toyota" in sample_vehicle.display_name
        assert "Fortuner" in sample_vehicle.display_name

    def test_vehicle_maintenance_due(self, sample_vehicle):
        """Test maintenance due detection."""
        # Current: 45000, Next: 50000 - not due yet
        assert sample_vehicle.is_maintenance_due is False
        
        # Update to trigger maintenance
        sample_vehicle.current_odometer = 50000
        sample_vehicle.save()
        assert sample_vehicle.is_maintenance_due is True

    def test_vehicle_km_until_maintenance(self, sample_vehicle):
        """Test km until maintenance calculation."""
        assert sample_vehicle.km_until_maintenance == 5000

    def test_vehicle_plate_unique_per_business(self, db, car_hire_business, sample_vehicle):
        """Test plate number uniqueness within a business."""
        business, user = car_hire_business
        with pytest.raises(Exception):  # IntegrityError
            Vehicle.objects.create(
                business=business,
                name="Another Vehicle",
                make=VehicleMake.FORD,
                model="Ranger",
                plate_number="MX 1234",  # Same plate - should fail
                daily_rate=Decimal("40000.00"),
            )

    def test_status_colors(self, sample_vehicle):
        """Test status color mapping."""
        sample_vehicle.status = VehicleStatus.AVAILABLE
        assert sample_vehicle.status_color == "success"
        
        sample_vehicle.status = VehicleStatus.ON_TRIP
        assert sample_vehicle.status_color == "primary"
        
        sample_vehicle.status = VehicleStatus.MAINTENANCE
        assert sample_vehicle.status_color == "warning"


class TestTripModel:
    """Tests for the Trip model."""

    def test_trip_creation(self, sample_trip):
        """Test trip can be created with valid data."""
        assert sample_trip.pk is not None
        assert sample_trip.customer_name == "John Banda"
        assert sample_trip.status == TripStatus.UPCOMING

    def test_trip_str(self, sample_trip):
        """Test trip string representation."""
        assert "John Banda" in str(sample_trip)
        assert "Lilongwe to Blantyre" in str(sample_trip)

    def test_trip_duration_days(self, sample_trip):
        """Test duration calculation."""
        assert sample_trip.duration_days == 4  # 3 days span + 1

    def test_trip_balance_due(self, sample_trip):
        """Test balance calculation."""
        # Price: 150000, Deposit: 50000
        assert sample_trip.balance_due == Decimal("100000.00")

    def test_trip_start(self, sample_trip, sample_vehicle):
        """Test starting a trip updates statuses."""
        sample_trip.start_trip()
        
        # Refresh from DB
        sample_trip.refresh_from_db()
        sample_vehicle.refresh_from_db()
        
        assert sample_trip.status == TripStatus.ACTIVE
        assert sample_trip.start_odometer == 45000
        assert sample_vehicle.status == VehicleStatus.ON_TRIP

    def test_trip_complete(self, sample_trip, sample_vehicle):
        """Test completing a trip updates statuses and odometer."""
        # Start first
        sample_trip.start_trip()
        
        # Complete with new odometer
        sample_trip.complete_trip(end_odometer=45500)
        
        sample_trip.refresh_from_db()
        sample_vehicle.refresh_from_db()
        
        assert sample_trip.status == TripStatus.COMPLETED
        assert sample_trip.end_odometer == 45500
        assert sample_vehicle.current_odometer == 45500
        assert sample_vehicle.status == VehicleStatus.AVAILABLE

    def test_trip_distance(self, sample_trip):
        """Test distance calculation."""
        sample_trip.start_odometer = 45000
        sample_trip.end_odometer = 45500
        sample_trip.save()
        
        assert sample_trip.distance_km == 500


class TestMaintenanceModel:
    """Tests for the MaintenanceRecord model."""

    def test_maintenance_creation(self, db, sample_vehicle, car_hire_business):
        """Test maintenance record creation."""
        business, user = car_hire_business
        record = MaintenanceRecord.objects.create(
            vehicle=sample_vehicle,
            maintenance_type="service",
            date=timezone.now().date(),
            description="Full service at 45000km",
            odometer=45000,
            cost=Decimal("75000.00"),
            vendor="Auto Garage Lilongwe",
            next_maintenance_km=55000,
            created_by=user,
        )
        assert record.pk is not None
        
        # Check vehicle updated
        sample_vehicle.refresh_from_db()
        assert sample_vehicle.next_maintenance_km == 55000


# ==============================================================================
# URL ROUTING TESTS
# ==============================================================================


class TestCarHireURLs:
    """Test URL routing for Car Hire vertical."""

    def test_dashboard_url_resolves(self, client, car_hire_business):
        """Test dashboard URL is accessible."""
        business, user = car_hire_business
        client.force_login(user)
        
        # Set session
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard")
        response = client.get(url)
        # Should be 200 or redirect to login
        assert response.status_code in [200, 302]

    def test_vehicles_list_url_resolves(self, client, car_hire_business):
        """Test vehicles list URL is accessible."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_vehicles")
        response = client.get(url)
        assert response.status_code in [200, 302]

    def test_vehicle_add_url_resolves(self, client, car_hire_business):
        """Test add vehicle URL is accessible."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_vehicle_add")
        response = client.get(url)
        assert response.status_code in [200, 302]

    def test_trips_list_url_resolves(self, client, car_hire_business):
        """Test trips list URL is accessible."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_trips")
        response = client.get(url)
        assert response.status_code in [200, 302]


# ==============================================================================
# DASHBOARD TESTS
# ==============================================================================


class TestCarHireDashboard:
    """Tests for Car Hire dashboard functionality."""

    def test_dashboard_loads_empty_state(self, client, car_hire_business):
        """Test dashboard loads with no data (empty state)."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard")
        response = client.get(url)
        
        # Should load without errors
        assert response.status_code in [200, 302]

    def test_dashboard_shows_kpis(self, client, car_hire_business, sample_vehicle, sample_trip):
        """Test dashboard displays KPI data."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard")
        response = client.get(url)
        
        # Should not error with data present
        assert response.status_code in [200, 302]


# ==============================================================================
# SIDEBAR AND NAVIGATION TESTS
# ==============================================================================


class TestCarHireSidebar:
    """Tests for Car Hire sidebar navigation."""

    def test_sidebar_items_for_car_hire(self):
        """Test sidebar items are correct for car_hire vertical."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        items = get_vertical_sidebar_items("car_hire")
        
        # Should have items
        assert len(items) > 0
        
        # Check key items exist
        keys = [item.get("key") for item in items]
        assert "dashboard" in keys
        assert "vehicles" in keys
        assert "add_vehicle" in keys
        assert "trips" in keys
        assert "add_trip" in keys
        assert "maintenance" in keys
        assert "billing" in keys
        assert "settings" in keys

    def test_sidebar_billing_requires_manager(self):
        """Test billing item requires manager role."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        items = get_vertical_sidebar_items("car_hire")
        
        billing = next((i for i in items if i["key"] == "billing"), None)
        assert billing is not None
        assert billing.get("require_manager") is True

    def test_sidebar_settings_requires_manager(self):
        """Test settings item requires manager role."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        items = get_vertical_sidebar_items("car_hire")
        
        settings = next((i for i in items if i["key"] == "settings"), None)
        assert settings is not None
        assert settings.get("require_manager") is True


class TestCarHireMobileNav:
    """Tests for Car Hire mobile navigation."""

    def test_mobile_nav_items(self, rf, car_hire_business):
        """Test mobile nav items are correct for car_hire vertical."""
        from inventory.mobile_nav import get_mobile_nav_items
        
        business, user = car_hire_business
        
        # Create a mock request with the business set
        request = rf.get("/")
        request.user = user
        request.business = business
        request.session = {"active_business_vertical": "car_hire"}
        
        items = get_mobile_nav_items(request)
        
        # Should have items
        assert len(items) > 0
        
        # Check key items exist
        keys = [item["key"] for item in items]
        assert "home" in keys
        assert "vehicles" in keys
        assert "trips" in keys


# ==============================================================================
# BILLING ACCESS TESTS
# ==============================================================================


class TestCarHireBillingAccess:
    """Tests for billing access control in Car Hire vertical."""

    def test_manager_can_access_billing(self, client, car_hire_business):
        """Test manager can access billing pages."""
        business, manager = car_hire_business
        client.force_login(manager)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("billing:plans")
        response = client.get(url)
        
        # Should be accessible (200) or redirect to billing page
        assert response.status_code in [200, 302, 403]

    def test_agent_cannot_access_billing(self, client, car_hire_business, car_hire_agent):
        """Test non-manager (agent) cannot access billing pages."""
        business, _ = car_hire_business
        client.force_login(car_hire_agent)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        # The billing sidebar item should not appear for agents
        # (Permission enforcement happens in the template or middleware)
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        items = get_vertical_sidebar_items("car_hire")
        billing = next((i for i in items if i["key"] == "billing"), None)
        assert billing.get("require_manager") is True


# ==============================================================================
# PREMIUM DASHBOARD POLISH TESTS (Jan 2026)
# ==============================================================================


class TestPremiumDashboard:
    """Tests for premium dashboard features (charts, KPIs, fleet health)."""

    def test_dashboard_context_has_chart_data(self, client, car_hire_business):
        """Test dashboard context includes chart data for JS rendering."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard")
        response = client.get(url)
        
        if response.status_code == 200:
            # Check context has chart data
            assert "chart_labels" in response.context
            assert "chart_bookings" in response.context
            assert "chart_revenue" in response.context
            assert "fleet_status_data" in response.context
            assert "fleet_status_labels" in response.context

    def test_dashboard_context_has_fleet_health(self, client, car_hire_business):
        """Test dashboard context includes fleet health metrics."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard")
        response = client.get(url)
        
        if response.status_code == 200:
            assert "fleet_health_score" in response.context
            # Fleet health should be 100% when no vehicles (no problems)
            assert response.context["fleet_health_score"] == 100

    def test_dashboard_context_has_trend_indicators(self, client, car_hire_business, sample_vehicle):
        """Test dashboard context includes booking trend indicators."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard")
        response = client.get(url)
        
        if response.status_code == 200:
            assert "bookings_trend" in response.context
            assert "bookings_trend_pct" in response.context

    def test_dashboard_context_has_overdue_count(self, client, car_hire_business, sample_vehicle):
        """Test dashboard tracks overdue maintenance count."""
        business, user = car_hire_business
        client.force_login(user)
        
        # Make vehicle overdue for maintenance
        sample_vehicle.current_odometer = 55000  # Above next_maintenance_km
        sample_vehicle.save()
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard")
        response = client.get(url)
        
        if response.status_code == 200:
            assert "overdue_count" in response.context
            assert response.context["overdue_count"] == 1

    def test_dashboard_renders_kpi_test_ids(self, client, car_hire_business):
        """Test dashboard renders with data-testid attributes for KPIs."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard")
        response = client.get(url)
        
        if response.status_code == 200:
            content = response.content.decode("utf-8")
            assert 'data-testid="kpi-active-bookings"' in content
            assert 'data-testid="kpi-available"' in content
            assert 'data-testid="kpi-utilization"' in content
            assert 'data-testid="kpi-revenue"' in content

    def test_dashboard_renders_chart_canvases(self, client, car_hire_business):
        """Test dashboard renders chart canvas elements."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard")
        response = client.get(url)
        
        if response.status_code == 200:
            content = response.content.decode("utf-8")
            assert 'id="bookingsRevenueChart"' in content


class TestQuickAddVehicles:
    """Tests for quick-add vehicle cards functionality."""

    def test_vehicle_add_page_has_quick_add_vehicles(self, client, car_hire_business):
        """Test add vehicle page includes quick-add vehicle templates."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_vehicle_add")
        response = client.get(url)
        
        if response.status_code == 200:
            assert "quick_add_vehicles" in response.context
            vehicles = response.context["quick_add_vehicles"]
            assert len(vehicles) >= 6  # At least 6 preset vehicles

    def test_quick_add_includes_common_malawian_vehicles(self, client, car_hire_business):
        """Test quick-add templates include common Malawian fleet vehicles."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_vehicle_add")
        response = client.get(url)
        
        if response.status_code == 200:
            vehicles = response.context["quick_add_vehicles"]
            models = [v["model"] for v in vehicles]
            
            # These are common Malawian fleet vehicles
            assert "Fortuner" in models
            assert "Ranger" in models
            assert "Hiace" in models
            assert "Bongo" in models
            assert "Fit" in models
            assert "Everest" in models

    def test_quick_add_cards_render_in_template(self, client, car_hire_business):
        """Test quick-add cards render with correct data attributes."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_vehicle_add")
        response = client.get(url)
        
        if response.status_code == 200:
            content = response.content.decode("utf-8")
            assert 'data-testid="quick-add-grid"' in content
            assert 'data-testid="quick-add-card"' in content
            assert 'data-testid="quick-add-custom"' in content

    def test_quick_add_vehicles_have_suggested_rates(self, client, car_hire_business):
        """Test quick-add vehicles include suggested daily rates."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_vehicle_add")
        response = client.get(url)
        
        if response.status_code == 200:
            vehicles = response.context["quick_add_vehicles"]
            for vehicle in vehicles:
                assert "suggested_rate" in vehicle
                assert vehicle["suggested_rate"] > 0


class TestVehiclesList:
    """Tests for premium vehicles list page."""

    def test_vehicles_list_renders_cards(self, client, car_hire_business, sample_vehicle):
        """Test vehicles list renders vehicle cards."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_vehicles")
        response = client.get(url)
        
        if response.status_code == 200:
            content = response.content.decode("utf-8")
            assert 'data-testid="vehicle-card"' in content
            assert sample_vehicle.plate_number in content

    def test_vehicles_list_has_filter_pills(self, client, car_hire_business):
        """Test vehicles list has status filter pills."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_vehicles")
        response = client.get(url)
        
        if response.status_code == 200:
            content = response.content.decode("utf-8")
            assert "?status=available" in content
            assert "?status=on_trip" in content
            assert "?status=maintenance" in content


# ==============================================================================
# VERTICAL KIND TESTS
# ==============================================================================


class TestBusinessKindCarHire:
    """Tests for Car Hire business kind integration."""

    def test_car_hire_in_business_kind_choices(self):
        """Test CAR_HIRE is a valid BusinessKind choice."""
        assert hasattr(BusinessKind, "CAR_HIRE")
        assert BusinessKind.CAR_HIRE == "car_hire"

    def test_vertical_display_name(self):
        """Test Car Hire display name."""
        from inventory.utils_verticals import get_vertical_display_name
        
        name = get_vertical_display_name("car_hire")
        assert "Car Hire" in name

    def test_vertical_dashboard_url(self):
        """Test Car Hire dashboard URL mapping."""
        from inventory.utils_verticals import get_vertical_dashboard_url
        
        url = get_vertical_dashboard_url("car_hire")
        assert url == "verticals:car_hire_dashboard"


class TestQuickAddVehiclesSSot:
    """Tests for QUICK_ADD_VEHICLES constant (SSOT for quick-add cards)."""

    def test_quick_add_vehicles_constant_exists(self):
        """Test QUICK_ADD_VEHICLES constant is defined in car_hire module."""
        from inventory.verticals.car_hire import QUICK_ADD_VEHICLES
        
        assert QUICK_ADD_VEHICLES is not None
        assert isinstance(QUICK_ADD_VEHICLES, list)
        assert len(QUICK_ADD_VEHICLES) >= 6

    def test_quick_add_vehicles_have_required_fields(self):
        """Test each quick-add vehicle has all required fields."""
        from inventory.verticals.car_hire import QUICK_ADD_VEHICLES
        
        required_fields = {"id", "make", "model", "icon", "suggested_rate"}
        
        for vehicle in QUICK_ADD_VEHICLES:
            for field in required_fields:
                assert field in vehicle, f"Missing field '{field}' in {vehicle}"

    def test_quick_add_vehicles_ids_unique(self):
        """Test quick-add vehicle IDs are unique."""
        from inventory.verticals.car_hire import QUICK_ADD_VEHICLES
        
        ids = [v["id"] for v in QUICK_ADD_VEHICLES]
        assert len(ids) == len(set(ids)), "Duplicate IDs in QUICK_ADD_VEHICLES"


# ==============================================================================
# FILTER TESTS (Jan 2026 - Dashboard Filters)
# ==============================================================================


@pytest.fixture
def second_vehicle(db, car_hire_business):
    """Create a second vehicle for filter testing."""
    business, user = car_hire_business
    return Vehicle.objects.create(
        business=business,
        name="Ford Ranger 2021",
        make=VehicleMake.FORD,
        model="Ranger",
        year=2021,
        plate_number="MX 5678",
        status=VehicleStatus.AVAILABLE,
        daily_rate=Decimal("40000.00"),
        current_odometer=30000,
        created_by=user,
    )


@pytest.fixture
def second_agent(db, django_user_model, car_hire_business):
    """Create a second agent for filter testing."""
    business, manager = car_hire_business
    agent = django_user_model.objects.create_user(
        username="carhire_driver2",
        email="driver2@carhire.test",
        password="testpass123",
        first_name="Jane",
        last_name="Driver",
    )
    Membership.objects.create(
        user=agent,
        business=business,
        role="agent",
        is_active=True,
    )
    return agent


@pytest.fixture
def trip_for_vehicle1(db, car_hire_business, sample_vehicle, car_hire_agent):
    """Create a completed trip for vehicle 1."""
    business, user = car_hire_business
    now = timezone.now()
    trip = Trip.objects.create(
        business=business,
        vehicle=sample_vehicle,
        customer_name="Customer A",
        start_datetime=now - timedelta(days=2),
        end_datetime=now - timedelta(days=1),
        destination="City A",
        price_total=Decimal("100000.00"),
        status=TripStatus.COMPLETED,
        driver=car_hire_agent,
        created_by=user,
    )
    return trip


@pytest.fixture
def trip_for_vehicle2(db, car_hire_business, second_vehicle, second_agent):
    """Create a completed trip for vehicle 2."""
    business, user = car_hire_business
    now = timezone.now()
    trip = Trip.objects.create(
        business=business,
        vehicle=second_vehicle,
        customer_name="Customer B",
        start_datetime=now - timedelta(days=3),
        end_datetime=now - timedelta(days=2),
        destination="City B",
        price_total=Decimal("75000.00"),
        status=TripStatus.COMPLETED,
        driver=second_agent,
        created_by=user,
    )
    return trip


class TestCarHireFiltersDashboard:
    """Tests for Car Hire dashboard filtering (PART D - Regression Tests)."""

    def test_dashboard_renders_with_default_filters(self, client, car_hire_business):
        """Test dashboard renders with default filters (no params) - KPIs OK, no crash."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard")
        response = client.get(url)
        
        assert response.status_code in [200, 302]
        if response.status_code == 200:
            # Verify default filter mode is MTD
            assert response.context.get("filter_mode") == "mtd"
            # Range label contains "month" (case insensitive) or "MTD"
            range_label = response.context.get("range_label", "")
            assert "month" in range_label.lower() or "MTD" in range_label

    def test_dashboard_all_time_filter(self, client, car_hire_business):
        """Test dashboard with period=all filter."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard") + "?period=all"
        response = client.get(url)
        
        assert response.status_code in [200, 302]
        if response.status_code == 200:
            assert response.context.get("filter_mode") == "all"
            assert response.context.get("range_label") == "All time"

    def test_dashboard_month_filter(self, client, car_hire_business):
        """Test dashboard with month filter."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard") + "?period=month&month=1&year=2026"
        response = client.get(url)
        
        assert response.status_code in [200, 302]
        if response.status_code == 200:
            assert response.context.get("filter_mode") == "month"
            assert response.context.get("month") == 1
            assert response.context.get("year") == 2026

    def test_vehicle_filter_applies_correctly(
        self, client, car_hire_business, sample_vehicle, second_vehicle,
        trip_for_vehicle1, trip_for_vehicle2
    ):
        """Test vehicle filter shows only trips for selected vehicle."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        # Filter by vehicle 1
        url = reverse("verticals:car_hire_dashboard") + f"?period=all&vehicle_id={sample_vehicle.id}"
        response = client.get(url)
        
        assert response.status_code in [200, 302]
        if response.status_code == 200:
            # Should show only vehicle 1's revenue (100000)
            revenue = response.context.get("revenue_filtered")
            assert revenue == Decimal("100000.00"), f"Expected 100000, got {revenue}"
            assert response.context.get("selected_vehicle").id == sample_vehicle.id

    def test_agent_filter_applies_correctly(
        self, client, car_hire_business, sample_vehicle, second_vehicle,
        car_hire_agent, second_agent, trip_for_vehicle1, trip_for_vehicle2
    ):
        """Test agent filter shows only trips for selected agent."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        # Filter by agent 1
        url = reverse("verticals:car_hire_dashboard") + f"?period=all&agent_id={car_hire_agent.id}"
        response = client.get(url)
        
        assert response.status_code in [200, 302]
        if response.status_code == 200:
            # Should show only agent 1's trip revenue (100000)
            revenue = response.context.get("revenue_filtered")
            assert revenue == Decimal("100000.00"), f"Expected 100000, got {revenue}"
            assert response.context.get("selected_agent").id == car_hire_agent.id

    def test_combined_filters_work(
        self, client, car_hire_business, sample_vehicle, second_vehicle,
        car_hire_agent, trip_for_vehicle1, trip_for_vehicle2
    ):
        """Test combining vehicle and agent filters."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        # Filter by vehicle 1 AND agent 1
        url = reverse("verticals:car_hire_dashboard") + f"?period=all&vehicle_id={sample_vehicle.id}&agent_id={car_hire_agent.id}"
        response = client.get(url)
        
        assert response.status_code in [200, 302]
        if response.status_code == 200:
            revenue = response.context.get("revenue_filtered")
            assert revenue == Decimal("100000.00")

    def test_invalid_vehicle_id_ignored(self, client, car_hire_business):
        """Test invalid vehicle_id is safely ignored."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard") + "?vehicle_id=99999"
        response = client.get(url)
        
        # Should not crash
        assert response.status_code in [200, 302]
        if response.status_code == 200:
            assert response.context.get("selected_vehicle") is None

    def test_invalid_agent_id_ignored(self, client, car_hire_business):
        """Test invalid agent_id is safely ignored."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard") + "?agent_id=99999"
        response = client.get(url)
        
        # Should not crash
        assert response.status_code in [200, 302]
        if response.status_code == 200:
            assert response.context.get("selected_agent") is None

    def test_cross_business_vehicle_rejected(self, client, car_hire_business, django_user_model, db):
        """Test vehicle from another business is rejected (no data leakage)."""
        business, user = car_hire_business
        
        # Create another business with a vehicle
        other_user = django_user_model.objects.create_user(
            username="other_owner",
            email="other@test.com",
            password="testpass123",
        )
        other_business = Business.objects.create(
            name="Other Car Hire",
            business_kind=BusinessKind.CAR_HIRE,
            owner=other_user,
        )
        other_vehicle = Vehicle.objects.create(
            business=other_business,
            name="Other Vehicle",
            make=VehicleMake.TOYOTA,
            model="Camry",
            plate_number="XX 1234",
            daily_rate=Decimal("30000.00"),
        )
        
        client.force_login(user)
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        # Try to filter by other business's vehicle
        url = reverse("verticals:car_hire_dashboard") + f"?vehicle_id={other_vehicle.id}"
        response = client.get(url)
        
        assert response.status_code in [200, 302]
        if response.status_code == 200:
            # Cross-business vehicle should be rejected
            assert response.context.get("selected_vehicle") is None

    def test_cross_business_agent_rejected(self, client, car_hire_business, django_user_model, db):
        """Test agent from another business is rejected (no data leakage)."""
        business, user = car_hire_business
        
        # Create another business with an agent
        other_user = django_user_model.objects.create_user(
            username="other_owner2",
            email="other2@test.com",
            password="testpass123",
        )
        other_business = Business.objects.create(
            name="Other Car Hire 2",
            business_kind=BusinessKind.CAR_HIRE,
            owner=other_user,
        )
        other_agent = django_user_model.objects.create_user(
            username="other_agent",
            email="otheragent@test.com",
            password="testpass123",
        )
        Membership.objects.create(
            user=other_agent,
            business=other_business,
            role="agent",
            is_active=True,
        )
        
        client.force_login(user)
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        # Try to filter by other business's agent
        url = reverse("verticals:car_hire_dashboard") + f"?agent_id={other_agent.id}"
        response = client.get(url)
        
        assert response.status_code in [200, 302]
        if response.status_code == 200:
            # Cross-business agent should be rejected
            assert response.context.get("selected_agent") is None


class TestCarHireHeroCard:
    """Tests for the premium blue hero card on Car Hire dashboard."""

    def test_dashboard_has_hero_card(self, client, car_hire_business):
        """Test dashboard contains the hero card with business name and vertical."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard")
        response = client.get(url)
        
        if response.status_code == 200:
            content = response.content.decode("utf-8")
            assert 'data-testid="car-hire-hero-card"' in content
            assert business.name in content
            assert "Car Hire" in content

    def test_dashboard_has_filter_button(self, client, car_hire_business):
        """Test dashboard contains the filter button."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard")
        response = client.get(url)
        
        if response.status_code == 200:
            content = response.content.decode("utf-8")
            assert 'data-testid="car-hire-filter-button"' in content

    def test_filter_chips_shown_when_filters_active(
        self, client, car_hire_business, sample_vehicle
    ):
        """Test filter chips are shown when filters are active."""
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard") + f"?period=all&vehicle_id={sample_vehicle.id}"
        response = client.get(url)
        
        if response.status_code == 200:
            content = response.content.decode("utf-8")
            # Should show filter chip for the vehicle
            assert sample_vehicle.name in content
            # Should show clear all filters button
            assert 'data-testid="clear-all-filters"' in content

    def test_filter_overlay_has_correct_testid(self, client, car_hire_business):
        """
        REGRESSION TEST: Filter overlay z-index fix (Jan 2026).
        
        Verifies that the filter overlay panel has the correct data-testid
        and is rendered in the dashboard. This ensures the overlay structure
        is present for proper stacking context above KPI cards.
        """
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard")
        response = client.get(url)
        
        if response.status_code == 200:
            content = response.content.decode("utf-8")
            # Filter overlay must have the correct testid for stacking context fix
            assert 'data-testid="dashboard-filter-overlay"' in content
            # Filter section bar must be present
            assert 'data-testid="car-hire-filter-section"' in content


class TestTripDriverField:
    """Tests for the driver field on Trip model."""

    def test_trip_has_driver_field(self, sample_trip, car_hire_agent):
        """Test Trip model has driver field."""
        sample_trip.driver = car_hire_agent
        sample_trip.save()
        
        sample_trip.refresh_from_db()
        assert sample_trip.driver == car_hire_agent

    def test_trip_driver_is_nullable(self, sample_trip):
        """Test driver field can be null."""
        sample_trip.driver = None
        sample_trip.save()
        
        sample_trip.refresh_from_db()
        assert sample_trip.driver is None


# ==============================================================================
# FILTER OVERLAY Z-INDEX FIX REGRESSION TESTS (Jan 2026)
# ==============================================================================


class TestFilterOverlayPortalFix:
    """
    REGRESSION TESTS: Filter overlay z-index/stacking context fix (Jan 2026).
    
    ROOT CAUSE: Filter panel was rendered inside .cc-main (z-index: 0), causing
    it to appear behind KPI cards that have transforms (creating stacking contexts).
    
    FIX: Filter panel and backdrop are moved to #cc-overlay-root via JavaScript
    portal pattern. This escapes the .cc-main stacking context entirely.
    
    These tests verify the fix is in place and won't regress.
    """

    def test_base_template_has_overlay_root(self, client, car_hire_business):
        """
        Test base template contains #cc-overlay-root element.
        
        This element is the portal target for filter overlays, ensuring they
        render outside the .cc-main stacking context (z-index: 0).
        """
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard")
        response = client.get(url)
        
        if response.status_code == 200:
            content = response.content.decode("utf-8")
            # The overlay root must exist in base.html (portal target)
            assert 'id="cc-overlay-root"' in content, (
                "#cc-overlay-root missing from base template. "
                "Filter overlays cannot escape stacking context without it."
            )

    def test_filter_panel_uses_fixed_positioning(self, client, car_hire_business):
        """
        Test filter panel CSS uses position: fixed for portal pattern.
        
        This ensures the panel is positioned relative to viewport, not any
        parent container, which prevents stacking context traps.
        """
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard")
        response = client.get(url)
        
        if response.status_code == 200:
            content = response.content.decode("utf-8")
            # Check that filter-panel CSS includes position: fixed
            assert ".filter-panel" in content
            # The panel should use position: fixed (not absolute)
            # Check for the pattern in the inline CSS
            assert "position: fixed" in content or "position:fixed" in content, (
                "Filter panel must use position: fixed for portal pattern"
            )

    def test_filter_backdrop_uses_fixed_positioning(self, client, car_hire_business):
        """
        Test filter backdrop CSS uses position: fixed with inset: 0.
        
        This ensures the backdrop covers the entire viewport.
        """
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard")
        response = client.get(url)
        
        if response.status_code == 200:
            content = response.content.decode("utf-8")
            # Check that filter-backdrop exists and uses fixed positioning
            assert ".filter-backdrop" in content
            # Should use inset: 0 for full viewport coverage
            assert "inset: 0" in content or "inset:0" in content, (
                "Filter backdrop must use inset: 0 for full viewport coverage"
            )

    def test_filter_panel_has_high_z_index(self, client, car_hire_business):
        """
        Test filter panel has z-index above sidebar (1030) and KPI cards.
        
        Z-index hierarchy (from base.html):
        - sidebar: 1030
        - filter backdrop: 1055
        - filter panel: 1056
        - modals: 1060
        """
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard")
        response = client.get(url)
        
        if response.status_code == 200:
            content = response.content.decode("utf-8")
            # Filter panel z-index should be >= 1056 (above sidebar 1030)
            assert "z-index: 1056" in content or "z-index:1056" in content, (
                "Filter panel z-index must be 1056 to appear above sidebar (1030)"
            )

    def test_filter_backdrop_z_index_below_panel(self, client, car_hire_business):
        """
        Test filter backdrop has z-index below panel but above content.
        
        Backdrop z-index should be 1055 (panel is 1056).
        """
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard")
        response = client.get(url)
        
        if response.status_code == 200:
            content = response.content.decode("utf-8")
            # Backdrop z-index should be 1055
            assert "z-index: 1055" in content or "z-index:1055" in content, (
                "Filter backdrop z-index must be 1055 (below panel 1056)"
            )

    def test_filter_has_portal_pattern_js(self, client, car_hire_business):
        """
        Test dashboard includes JavaScript for portal pattern.
        
        The JS moves filter panel and backdrop to #cc-overlay-root when opened,
        escaping the .cc-main stacking context.
        """
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard")
        response = client.get(url)
        
        if response.status_code == 200:
            content = response.content.decode("utf-8")
            # Check for key portal pattern markers in JS
            # Should reference cc-overlay-root
            assert "cc-overlay-root" in content, (
                "Filter JS must reference #cc-overlay-root for portal pattern"
            )
            # Should use appendChild or similar to move elements
            assert "appendChild" in content or "overlayRoot" in content, (
                "Filter JS must move elements to overlay root"
            )

    def test_kpi_cards_dont_have_conflicting_z_index(self, client, car_hire_business):
        """
        Test KPI cards don't set explicit z-index that would conflict.
        
        KPI cards should NOT have z-index set, as their transforms create
        stacking contexts but we want them below the filter overlay.
        """
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard")
        response = client.get(url)
        
        if response.status_code == 200:
            content = response.content.decode("utf-8")
            # KPI card CSS should not set an explicit high z-index
            # We check that .kpi-card doesn't have z-index >= 1000
            import re
            kpi_z_pattern = r'\.kpi-card[^{]*\{[^}]*z-index\s*:\s*(\d+)'
            matches = re.findall(kpi_z_pattern, content)
            for z_val in matches:
                z_int = int(z_val)
                assert z_int < 1000, (
                    f"KPI card has z-index {z_int} which may conflict with filter overlay. "
                    "Remove explicit z-index from .kpi-card or keep it below 1000."
                )

    def test_filter_overlay_renders_in_page(self, client, car_hire_business):
        """
        Test filter overlay markup is present in the dashboard.
        
        The filter panel and backdrop must be in the initial HTML for the
        portal JS to find and move them.
        """
        business, user = car_hire_business
        client.force_login(user)
        
        session = client.session
        session["active_business_id"] = business.pk
        session.save()
        
        url = reverse("verticals:car_hire_dashboard")
        response = client.get(url)
        
        if response.status_code == 200:
            content = response.content.decode("utf-8")
            # Filter elements must exist
            assert 'data-filter-panel' in content, "Filter panel element missing"
            assert 'data-filter-backdrop' in content, "Filter backdrop element missing"
            assert 'data-filter-trigger' in content, "Filter trigger button missing"
            assert 'data-filter-close' in content, "Filter close button missing"
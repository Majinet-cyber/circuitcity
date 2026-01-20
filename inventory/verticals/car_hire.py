# inventory/verticals/car_hire.py
"""
Car Hire Service vertical adapter.
Provides dashboard and view functions for fleet management and trip bookings.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.models_car_hire import (
    MaintenanceRecord,
    MaintenanceType,
    Trip,
    TripStatus,
    TripType,
    Vehicle,
    VehicleMake,
    VehicleStatus,
)
from inventory.verticals import base
from inventory.verticals.base import parse_date_range_from_request
from tenants.models import Membership
from tenants.utils import require_business

User = get_user_model()


# ==============================================================================
# DASHBOARD
# ==============================================================================


def _get_business_agents(business) -> list:
    """Get all agents/staff in the business who can be drivers."""
    memberships = Membership.objects.filter(
        business=business,
        is_active=True,
    ).select_related("user")
    return [m.user for m in memberships]


def _parse_car_hire_filters(request, business) -> dict:
    """
    Parse all Car Hire dashboard filters from request.
    Returns a dict with filter_mode, date range, vehicle, agent, etc.
    Uses SSOT parse_date_range_from_request for date filters.
    """
    # Parse date filters using SSOT
    date_ctx = parse_date_range_from_request(request)
    
    # Parse vehicle filter
    vehicle_id = request.GET.get("vehicle_id", "")
    selected_vehicle = None
    if vehicle_id:
        try:
            selected_vehicle = Vehicle.objects.filter(
                id=int(vehicle_id),
                business=business,
                is_active=True,
            ).first()
        except (ValueError, TypeError):
            pass  # Invalid vehicle_id, ignore
    
    # Parse agent/driver filter
    agent_id = request.GET.get("agent_id", "")
    selected_agent = None
    if agent_id:
        try:
            # Verify agent belongs to this business
            membership = Membership.objects.filter(
                user_id=int(agent_id),
                business=business,
                is_active=True,
            ).select_related("user").first()
            if membership:
                selected_agent = membership.user
        except (ValueError, TypeError):
            pass  # Invalid agent_id, ignore
    
    return {
        **date_ctx,
        "selected_vehicle": selected_vehicle,
        "selected_agent": selected_agent,
    }


def _build_trip_queryset(
    business,
    *,
    start_date=None,
    end_date=None,
    vehicle=None,
    agent=None,
    statuses=None,
) -> "QuerySet[Trip]":
    """
    Build a Trip queryset with optional filters.
    Used for KPIs, charts, and lists.
    """
    qs = Trip.objects.filter(business=business)
    
    if statuses:
        qs = qs.filter(status__in=statuses)
    
    # Apply date filter (if provided)
    if start_date is not None and end_date is not None:
        # Convert date to datetime if needed
        if isinstance(start_date, datetime):
            qs = qs.filter(start_datetime__gte=start_date, start_datetime__lt=end_date)
        else:
            qs = qs.filter(start_datetime__date__gte=start_date, start_datetime__date__lt=end_date)
    
    # Apply vehicle filter
    if vehicle:
        qs = qs.filter(vehicle=vehicle)
    
    # Apply agent/driver filter
    if agent:
        qs = qs.filter(driver=agent)
    
    return qs


@login_required
@require_business
@require_business_kind(BusinessKind.CAR_HIRE)
def dashboard(request: HttpRequest) -> HttpResponse:
    """Car Hire dashboard with premium KPIs, charts, fleet overview, and upcoming trips."""
    import json
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    if not business:
        return redirect("verticals:no_business")
    
    today = timezone.now().date()
    now = timezone.now()
    
    # ===== PARSE FILTERS (SSOT) =====
    filter_ctx = _parse_car_hire_filters(request, business)
    filter_mode = filter_ctx.get("filter_mode", "mtd")
    start_date = filter_ctx.get("start_date")
    end_date = filter_ctx.get("end_date")
    range_label = filter_ctx.get("range_label", "Month to Date")
    selected_vehicle = filter_ctx.get("selected_vehicle")
    selected_agent = filter_ctx.get("selected_agent")
    month = filter_ctx.get("month")
    year = filter_ctx.get("year")
    
    # Short label for KPI cards
    range_label_short = "MTD"
    if filter_mode == "all":
        range_label_short = "All"
    elif filter_mode == "month":
        range_label_short = range_label[:3] if len(range_label) > 3 else range_label
    elif filter_mode == "last7":
        range_label_short = "7D"
    elif filter_mode == "today":
        range_label_short = "Today"
    
    # Get all vehicles for filter dropdown
    all_vehicles = Vehicle.objects.filter(business=business, is_active=True).order_by("name")
    
    # Get all agents for filter dropdown
    all_agents = _get_business_agents(business)
    
    # ===== FLEET KPIs (not affected by date filter - current snapshot) =====
    vehicles = Vehicle.objects.filter(business=business, is_active=True)
    total_vehicles = vehicles.count()
    
    # Vehicle status counts
    available_count = vehicles.filter(status=VehicleStatus.AVAILABLE).count()
    on_trip_count = vehicles.filter(status=VehicleStatus.ON_TRIP).count()
    maintenance_count = vehicles.filter(status=VehicleStatus.MAINTENANCE).count()
    
    # Apply vehicle filter to vehicle status if selected
    if selected_vehicle:
        # When filtering by vehicle, show that specific vehicle's status
        single_vehicle = vehicles.filter(id=selected_vehicle.id).first()
        if single_vehicle:
            if single_vehicle.status == VehicleStatus.AVAILABLE:
                available_count = 1
                on_trip_count = 0
                maintenance_count = 0
            elif single_vehicle.status == VehicleStatus.ON_TRIP:
                available_count = 0
                on_trip_count = 1
                maintenance_count = 0
            else:
                available_count = 0
                on_trip_count = 0
                maintenance_count = 1
            total_vehicles = 1
    
    # ===== BOOKING KPIs (affected by date + vehicle + agent filters) =====
    
    # Active bookings (upcoming + active trips) - may be filtered
    active_trips_qs = _build_trip_queryset(
        business,
        vehicle=selected_vehicle,
        agent=selected_agent,
        statuses=[TripStatus.UPCOMING, TripStatus.ACTIVE],
    )
    active_bookings_count = active_trips_qs.count()
    
    # Utilization rate
    if total_vehicles > 0:
        utilization_rate = int((on_trip_count / total_vehicles) * 100)
    else:
        utilization_rate = 0
    
    # ===== REVENUE KPIs (affected by all filters) =====
    
    # Revenue for filtered period (completed trips)
    completed_trips_filtered = _build_trip_queryset(
        business,
        start_date=start_date,
        end_date=end_date,
        vehicle=selected_vehicle,
        agent=selected_agent,
        statuses=[TripStatus.COMPLETED],
    )
    revenue_filtered = completed_trips_filtered.aggregate(
        total=Coalesce(Sum("price_total"), Decimal("0.00"))
    )["total"]
    
    # Revenue this month (for comparison, unfiltered by vehicle/agent)
    month_start = today.replace(day=1)
    completed_trips_this_month = Trip.objects.filter(
        business=business,
        status=TripStatus.COMPLETED,
        start_datetime__date__gte=month_start,
    )
    revenue_this_month = completed_trips_this_month.aggregate(
        total=Coalesce(Sum("price_total"), Decimal("0.00"))
    )["total"]
    
    # Revenue today
    completed_trips_today = Trip.objects.filter(
        business=business,
        status=TripStatus.COMPLETED,
        start_datetime__date=today,
    )
    if selected_vehicle:
        completed_trips_today = completed_trips_today.filter(vehicle=selected_vehicle)
    if selected_agent:
        completed_trips_today = completed_trips_today.filter(driver=selected_agent)
    revenue_today = completed_trips_today.aggregate(
        total=Coalesce(Sum("price_total"), Decimal("0.00"))
    )["total"]
    
    # ===== TREND INDICATORS =====
    last_week_start = today - timedelta(days=7)
    last_week_end = today - timedelta(days=1)
    last_week_trips = _build_trip_queryset(
        business,
        vehicle=selected_vehicle,
        agent=selected_agent,
        statuses=[TripStatus.COMPLETED],
    ).filter(
        start_datetime__date__gte=last_week_start,
        start_datetime__date__lte=last_week_end,
    ).count()
    
    this_week_start = today - timedelta(days=6)
    this_week_trips = _build_trip_queryset(
        business,
        vehicle=selected_vehicle,
        agent=selected_agent,
        statuses=[TripStatus.COMPLETED],
    ).filter(
        start_datetime__date__gte=this_week_start,
    ).count()
    
    if last_week_trips > 0:
        bookings_trend = this_week_trips - last_week_trips
        bookings_trend_pct = int((bookings_trend / last_week_trips) * 100)
    else:
        bookings_trend = this_week_trips
        bookings_trend_pct = 0 if this_week_trips == 0 else 100
    
    # ===== FLEET DATA =====
    
    # Recent vehicles (for fleet cards) - may be filtered by selected_vehicle
    if selected_vehicle:
        recent_vehicles = [selected_vehicle]
    else:
        recent_vehicles = list(vehicles.order_by("-created_at")[:6])
    
    # Upcoming trips (next 5) - may be filtered
    upcoming_trips = _build_trip_queryset(
        business,
        vehicle=selected_vehicle,
        agent=selected_agent,
        statuses=[TripStatus.UPCOMING, TripStatus.ACTIVE],
    ).select_related("vehicle").order_by("start_datetime")[:5]
    
    # Vehicles needing maintenance (may be filtered by selected_vehicle)
    maintenance_due = []
    overdue_count = 0
    check_vehicles = [selected_vehicle] if selected_vehicle else vehicles
    for vehicle in check_vehicles:
        if vehicle.is_maintenance_due:
            maintenance_due.append({
                "vehicle": vehicle,
                "overdue": True,
                "km_over": vehicle.current_odometer - vehicle.next_maintenance_km,
            })
            overdue_count += 1
        elif vehicle.km_until_maintenance is not None and vehicle.km_until_maintenance < 500:
            maintenance_due.append({
                "vehicle": vehicle,
                "overdue": False,
                "km_until": vehicle.km_until_maintenance,
            })
    maintenance_due.sort(key=lambda x: (not x["overdue"], x.get("km_over", 0)), reverse=True)
    
    # Fleet health score
    if total_vehicles > 0:
        healthy_vehicles = total_vehicles - overdue_count
        fleet_health_score = int((healthy_vehicles / total_vehicles) * 100)
    else:
        fleet_health_score = 100
    
    # ===== CHART DATA: Last 14 days (or filtered period) =====
    chart_labels = []
    chart_bookings = []
    chart_revenue = []
    
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        chart_labels.append(day.strftime("%b %d"))
        
        # Bookings that started on this day (filtered)
        day_trips_qs = _build_trip_queryset(
            business,
            vehicle=selected_vehicle,
            agent=selected_agent,
            statuses=[TripStatus.COMPLETED, TripStatus.ACTIVE, TripStatus.UPCOMING],
        ).filter(start_datetime__date=day)
        chart_bookings.append(day_trips_qs.count())
        
        # Revenue from completed trips that started on this day (filtered)
        day_revenue_qs = _build_trip_queryset(
            business,
            vehicle=selected_vehicle,
            agent=selected_agent,
            statuses=[TripStatus.COMPLETED],
        ).filter(start_datetime__date=day)
        day_revenue = day_revenue_qs.aggregate(
            total=Coalesce(Sum("price_total"), Decimal("0.00"))
        )["total"]
        chart_revenue.append(float(day_revenue))
    
    # Fleet status breakdown for donut chart
    fleet_status_data = [available_count, on_trip_count, maintenance_count]
    fleet_status_labels = ["Available", "On Trip", "Maintenance"]
    
    # Availability streak
    availability_streak = 0
    if available_count == total_vehicles and total_vehicles > 0:
        for i in range(30):
            check_day = today - timedelta(days=i)
            had_trips = Trip.objects.filter(
                business=business,
                start_datetime__date__lte=check_day,
                status__in=[TripStatus.ACTIVE, TripStatus.COMPLETED],
            ).filter(
                Q(end_datetime__isnull=True) | Q(end_datetime__date__gte=check_day)
            ).exists()
            if not had_trips:
                availability_streak += 1
            else:
                break
    
    ctx.update({
        "active_tab": "dashboard",
        "hero_title": "Car Hire Dashboard",
        "hero_blurb": "Manage your fleet and track bookings in one place.",
        
        # Filter context (for template)
        "filter_mode": filter_mode,
        "range_label": range_label,
        "range_label_short": range_label_short,
        "month": month,
        "year": year,
        "selected_vehicle": selected_vehicle,
        "selected_agent": selected_agent,
        "all_vehicles": all_vehicles,
        "all_agents": all_agents,
        
        # KPIs
        "total_vehicles": total_vehicles,
        "available_count": available_count,
        "on_trip_count": on_trip_count,
        "maintenance_count": maintenance_count,
        "active_bookings_count": active_bookings_count,
        "utilization_rate": utilization_rate,
        "revenue_filtered": revenue_filtered,
        "revenue_this_month": revenue_this_month,
        "revenue_today": revenue_today,
        
        # Trend indicators
        "bookings_trend": bookings_trend,
        "bookings_trend_pct": bookings_trend_pct,
        
        # Fleet data
        "vehicles": recent_vehicles,
        "upcoming_trips": upcoming_trips,
        "maintenance_due": maintenance_due,
        "overdue_count": overdue_count,
        
        # Fleet health
        "fleet_health_score": fleet_health_score,
        "availability_streak": availability_streak if availability_streak > 0 else None,
        
        # Chart data (JSON for JS)
        "chart_labels": json.dumps(chart_labels),
        "chart_bookings": json.dumps(chart_bookings),
        "chart_revenue": json.dumps(chart_revenue),
        "fleet_status_data": json.dumps(fleet_status_data),
        "fleet_status_labels": json.dumps(fleet_status_labels),
        
        # Status choices for badges
        "VehicleStatus": VehicleStatus,
        "TripStatus": TripStatus,
    })
    
    return render(request, "verticals/car_hire/dashboard.html", ctx)


# ==============================================================================
# VEHICLES
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.CAR_HIRE)
def vehicles_list(request: HttpRequest) -> HttpResponse:
    """List all vehicles in the fleet."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    # Filter parameters
    status_filter = request.GET.get("status", "")
    make_filter = request.GET.get("make", "")
    
    vehicles = Vehicle.objects.filter(business=business, is_active=True)
    
    if status_filter:
        vehicles = vehicles.filter(status=status_filter)
    if make_filter:
        vehicles = vehicles.filter(make=make_filter)
    
    vehicles = vehicles.order_by("-created_at")
    
    # Statistics
    stats = vehicles.aggregate(
        total_value=Coalesce(Sum("daily_rate"), Decimal("0.00")),
    )
    
    ctx.update({
        "active_tab": "vehicles",
        "vehicles": vehicles,
        "total_vehicles": vehicles.count(),
        "status_filter": status_filter,
        "make_filter": make_filter,
        "VehicleStatus": VehicleStatus,
        "VehicleMake": VehicleMake,
    })
    
    return render(request, "verticals/car_hire/vehicles_list.html", ctx)


# Common Malawian fleet vehicle templates (SSOT for quick-add cards)
QUICK_ADD_VEHICLES = [
    {
        "id": "fortuner",
        "make": VehicleMake.TOYOTA,
        "model": "Fortuner",
        "icon": "🚙",
        "color": "emerald",
        "seats": 7,
        "fuel": "diesel",
        "suggested_rate": 45000,
        "description": "Premium SUV, great for family trips",
    },
    {
        "id": "ranger",
        "make": VehicleMake.FORD,
        "model": "Ranger",
        "icon": "🛻",
        "color": "blue",
        "seats": 5,
        "fuel": "diesel",
        "suggested_rate": 40000,
        "description": "Double cab pickup, perfect for cargo & passengers",
    },
    {
        "id": "hiace",
        "make": VehicleMake.TOYOTA,
        "model": "Hiace",
        "icon": "🚐",
        "color": "amber",
        "seats": 14,
        "fuel": "diesel",
        "suggested_rate": 55000,
        "description": "Minibus, ideal for group travel",
    },
    {
        "id": "bongo",
        "make": VehicleMake.MAZDA,
        "model": "Bongo",
        "icon": "🚚",
        "color": "orange",
        "seats": 3,
        "fuel": "diesel",
        "suggested_rate": 35000,
        "description": "Cargo van, reliable for deliveries",
    },
    {
        "id": "fit",
        "make": VehicleMake.HONDA,
        "model": "Fit",
        "icon": "🚗",
        "color": "teal",
        "seats": 5,
        "fuel": "petrol",
        "suggested_rate": 25000,
        "description": "Compact hatchback, fuel-efficient city car",
    },
    {
        "id": "everest",
        "make": VehicleMake.FORD,
        "model": "Everest",
        "icon": "🚙",
        "color": "indigo",
        "seats": 7,
        "fuel": "diesel",
        "suggested_rate": 50000,
        "description": "Full-size SUV, luxury & power",
    },
]


@login_required
@require_business
@require_business_kind(BusinessKind.CAR_HIRE)
@require_http_methods(["GET", "POST"])
def vehicle_add(request: HttpRequest) -> HttpResponse:
    """Add a new vehicle to the fleet with gamified quick-add cards."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    if request.method == "POST":
        try:
            # Build name from make/model/year if not provided
            name = request.POST.get("name", "").strip()
            make = request.POST.get("make", VehicleMake.TOYOTA)
            model = request.POST.get("model", "")
            year = request.POST.get("year") or None
            
            if not name:
                name_parts = [dict(VehicleMake.choices).get(make, make), model]
                if year:
                    name_parts.append(str(year))
                name = " ".join(filter(None, name_parts))
            
            vehicle = Vehicle.objects.create(
                business=business,
                name=name,
                make=make,
                model=model,
                year=int(year) if year else None,
                plate_number=request.POST.get("plate_number", "").upper().strip(),
                daily_rate=Decimal(request.POST.get("daily_rate", "0")),
                current_odometer=int(request.POST.get("current_odometer", 0)),
                next_maintenance_km=int(request.POST.get("next_maintenance_km")) if request.POST.get("next_maintenance_km") else None,
                color=request.POST.get("color", ""),
                seats=int(request.POST.get("seats")) if request.POST.get("seats") else None,
                fuel_type=request.POST.get("fuel_type", "petrol"),
                notes=request.POST.get("notes", ""),
                created_by=request.user,
            )
            
            messages.success(request, f"Vehicle '{vehicle.name}' added successfully! 🚗")
            return redirect("/verticals/car_hire/vehicles/")
        except Exception as e:
            messages.error(request, f"Error adding vehicle: {e}")
    
    ctx.update({
        "active_tab": "vehicles",
        "VehicleMake": VehicleMake,
        "quick_add_vehicles": QUICK_ADD_VEHICLES,  # For gamified cards
    })
    
    return render(request, "verticals/car_hire/vehicle_add.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.CAR_HIRE)
def vehicle_detail(request: HttpRequest, vehicle_id: int) -> HttpResponse:
    """View vehicle details and trip history."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    vehicle = get_object_or_404(Vehicle, id=vehicle_id, business=business)
    
    # Get trip history
    trips = Trip.objects.filter(vehicle=vehicle).order_by("-start_datetime")[:20]
    
    # Get maintenance history
    maintenance = MaintenanceRecord.objects.filter(vehicle=vehicle).order_by("-date")[:10]
    
    # Stats
    total_trips = Trip.objects.filter(vehicle=vehicle, status=TripStatus.COMPLETED).count()
    total_revenue = Trip.objects.filter(
        vehicle=vehicle, status=TripStatus.COMPLETED
    ).aggregate(total=Coalesce(Sum("price_total"), Decimal("0.00")))["total"]
    
    ctx.update({
        "active_tab": "vehicles",
        "vehicle": vehicle,
        "trips": trips,
        "maintenance": maintenance,
        "total_trips": total_trips,
        "total_revenue": total_revenue,
        "VehicleStatus": VehicleStatus,
        "TripStatus": TripStatus,
    })
    
    return render(request, "verticals/car_hire/vehicle_detail.html", ctx)


# ==============================================================================
# TRIPS / BOOKINGS
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.CAR_HIRE)
def trips_list(request: HttpRequest) -> HttpResponse:
    """List all trips/bookings."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    # Filter parameters
    status_filter = request.GET.get("status", "")
    
    trips = Trip.objects.filter(business=business).select_related("vehicle")
    
    if status_filter:
        trips = trips.filter(status=status_filter)
    
    trips = trips.order_by("-start_datetime")
    
    ctx.update({
        "active_tab": "trips",
        "trips": trips[:50],
        "total_trips": trips.count(),
        "status_filter": status_filter,
        "TripStatus": TripStatus,
    })
    
    return render(request, "verticals/car_hire/trips_list.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.CAR_HIRE)
@require_http_methods(["GET", "POST"])
def trip_add(request: HttpRequest) -> HttpResponse:
    """Add a new trip/booking."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    if request.method == "POST":
        try:
            vehicle_id = request.POST.get("vehicle_id")
            vehicle = get_object_or_404(Vehicle, id=vehicle_id, business=business)
            
            # Parse dates
            start_date = request.POST.get("start_date")
            start_time = request.POST.get("start_time", "08:00")
            start_datetime = timezone.make_aware(
                timezone.datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
            )
            
            end_date = request.POST.get("end_date")
            end_datetime = None
            if end_date:
                end_time = request.POST.get("end_time", "18:00")
                end_datetime = timezone.make_aware(
                    timezone.datetime.strptime(f"{end_date} {end_time}", "%Y-%m-%d %H:%M")
                )
            
            trip = Trip.objects.create(
                business=business,
                vehicle=vehicle,
                customer_name=request.POST.get("customer_name", "").strip(),
                customer_phone=request.POST.get("customer_phone", "").strip(),
                customer_id_number=request.POST.get("customer_id_number", "").strip(),
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                destination=request.POST.get("destination", "").strip(),
                trip_type=request.POST.get("trip_type", TripType.PASSENGER),
                price_total=Decimal(request.POST.get("price_total", "0")),
                deposit_paid=Decimal(request.POST.get("deposit_paid", "0")),
                notes=request.POST.get("notes", ""),
                created_by=request.user,
            )
            
            messages.success(request, f"Trip for {trip.customer_name} booked successfully.")
            return redirect("/verticals/car_hire/trips/")
        except Exception as e:
            messages.error(request, f"Error creating trip: {e}")
    
    # Get available vehicles
    available_vehicles = Vehicle.objects.filter(
        business=business,
        is_active=True,
        status=VehicleStatus.AVAILABLE,
    )
    
    ctx.update({
        "active_tab": "trips",
        "available_vehicles": available_vehicles,
        "TripType": TripType,
    })
    
    return render(request, "verticals/car_hire/trip_add.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.CAR_HIRE)
def trip_detail(request: HttpRequest, trip_id: int) -> HttpResponse:
    """View trip details."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    trip = get_object_or_404(Trip, id=trip_id, business=business)
    
    ctx.update({
        "active_tab": "trips",
        "trip": trip,
        "TripStatus": TripStatus,
    })
    
    return render(request, "verticals/car_hire/trip_detail.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.CAR_HIRE)
@require_http_methods(["POST"])
def trip_start(request: HttpRequest, trip_id: int) -> HttpResponse:
    """Mark a trip as active/started."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    trip = get_object_or_404(Trip, id=trip_id, business=business)
    
    if trip.status == TripStatus.UPCOMING:
        trip.start_trip()
        messages.success(request, f"Trip started for {trip.customer_name}.")
    else:
        messages.warning(request, "Trip cannot be started from current status.")
    
    return redirect(f"/verticals/car_hire/trips/{trip_id}/")


@login_required
@require_business
@require_business_kind(BusinessKind.CAR_HIRE)
@require_http_methods(["POST"])
def trip_complete(request: HttpRequest, trip_id: int) -> HttpResponse:
    """Mark a trip as completed."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    trip = get_object_or_404(Trip, id=trip_id, business=business)
    
    if trip.status == TripStatus.ACTIVE:
        end_odometer = request.POST.get("end_odometer")
        trip.complete_trip(int(end_odometer) if end_odometer else None)
        messages.success(request, f"Trip completed for {trip.customer_name}.")
    else:
        messages.warning(request, "Trip cannot be completed from current status.")
    
    return redirect(f"/verticals/car_hire/trips/{trip_id}/")


# ==============================================================================
# MAINTENANCE
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.CAR_HIRE)
def maintenance_list(request: HttpRequest) -> HttpResponse:
    """List maintenance records and vehicles due for service."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    # Get vehicles
    vehicles = Vehicle.objects.filter(business=business, is_active=True)
    
    # Vehicles due for maintenance
    maintenance_due = []
    for vehicle in vehicles:
        if vehicle.is_maintenance_due:
            maintenance_due.append({
                "vehicle": vehicle,
                "status": "overdue",
                "badge_class": "danger",
            })
        elif vehicle.km_until_maintenance is not None and vehicle.km_until_maintenance < 500:
            maintenance_due.append({
                "vehicle": vehicle,
                "status": "due_soon",
                "badge_class": "warning",
            })
    
    # Recent maintenance records
    recent_maintenance = MaintenanceRecord.objects.filter(
        vehicle__business=business
    ).select_related("vehicle").order_by("-date")[:20]
    
    ctx.update({
        "active_tab": "maintenance",
        "maintenance_due": maintenance_due,
        "recent_maintenance": recent_maintenance,
        "vehicles": vehicles,
        "MaintenanceType": MaintenanceType,
    })
    
    return render(request, "verticals/car_hire/maintenance_list.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.CAR_HIRE)
@require_http_methods(["GET", "POST"])
def maintenance_add(request: HttpRequest) -> HttpResponse:
    """Add a maintenance record."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    if request.method == "POST":
        try:
            vehicle_id = request.POST.get("vehicle_id")
            vehicle = get_object_or_404(Vehicle, id=vehicle_id, business=business)
            
            record = MaintenanceRecord.objects.create(
                vehicle=vehicle,
                maintenance_type=request.POST.get("maintenance_type", MaintenanceType.SERVICE),
                date=request.POST.get("date") or timezone.now().date(),
                description=request.POST.get("description", ""),
                odometer=int(request.POST.get("odometer")) if request.POST.get("odometer") else None,
                cost=Decimal(request.POST.get("cost", "0")),
                vendor=request.POST.get("vendor", ""),
                next_maintenance_km=int(request.POST.get("next_maintenance_km")) if request.POST.get("next_maintenance_km") else None,
                created_by=request.user,
            )
            
            # Update vehicle odometer and status
            if record.odometer:
                vehicle.current_odometer = record.odometer
            vehicle.status = VehicleStatus.AVAILABLE  # Return from maintenance
            vehicle.save(update_fields=["current_odometer", "status"])
            
            messages.success(request, f"Maintenance record added for {vehicle.name}.")
            return redirect("/verticals/car_hire/maintenance/")
        except Exception as e:
            messages.error(request, f"Error adding maintenance record: {e}")
    
    vehicles = Vehicle.objects.filter(business=business, is_active=True)
    
    ctx.update({
        "active_tab": "maintenance",
        "vehicles": vehicles,
        "MaintenanceType": MaintenanceType,
    })
    
    return render(request, "verticals/car_hire/maintenance_add.html", ctx)


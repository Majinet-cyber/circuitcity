# inventory/verticals/car_dealer.py
"""
Car Dealer vertical: views for dashboard, stock in, sell, inventory list, vehicle detail.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from tenants.utils import require_business, get_active_business
from tenants.utils_roles import is_manager

log = logging.getLogger(__name__)


def _get_car_models():
    try:
        from inventory.models_car_dealer import CarMake, CarModel, CarDealerVehicle
        return CarMake, CarModel, CarDealerVehicle
    except ImportError:
        return None, None, None


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
@require_business
def car_dealer_dashboard(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    CarMake, CarModel, CarDealerVehicle = _get_car_models()

    now = timezone.now()
    today = now.date()

    stats = {
        "total": 0,
        "in_stock": 0,
        "sold_this_month": 0,
        "reserved": 0,
        "revenue_this_month": Decimal("0"),
        "cost_this_month": Decimal("0"),
        "profit_this_month": Decimal("0"),
        "avg_selling_price": Decimal("0"),
        "inventory_value": Decimal("0"),
        "inventory_cost_basis": Decimal("0"),
        "aging_30": 0,
        "aging_60": 0,
        "aging_90_plus": 0,
    }
    recent_vehicles = []
    vehicles_by_make = []
    vehicles_by_fuel = []
    recent_sold = []

    if CarDealerVehicle:
        from django.db.models import Count, Sum

        qs = CarDealerVehicle.objects.filter(business=biz)
        stats["total"] = qs.count()

        in_stock_qs = qs.filter(status="in_stock")
        stats["in_stock"] = in_stock_qs.count()
        stats["reserved"] = qs.filter(status="reserved").count()

        # Revenue and sales this month
        sold_this_month = qs.filter(
            status="sold",
            sold_at__year=now.year,
            sold_at__month=now.month,
        )
        stats["sold_this_month"] = sold_this_month.count()
        stats["revenue_this_month"] = sum(
            (v.sale_price or v.selling_price or Decimal("0"))
            for v in sold_this_month
        )

        # Average selling price on current stock
        in_stock_prices = [v.selling_price for v in in_stock_qs if v.selling_price]
        if in_stock_prices:
            stats["avg_selling_price"] = sum(in_stock_prices) / len(in_stock_prices)

        # Total inventory value (sum of selling prices in stock)
        stats["inventory_value"] = sum(in_stock_prices)

        # Inventory cost basis (sum of buying prices in stock)
        in_stock_costs = [v.buying_price for v in in_stock_qs if v.buying_price]
        stats["inventory_cost_basis"] = sum(in_stock_costs) if in_stock_costs else Decimal("0")

        # Profit this month (revenue - buying_price of sold units this month)
        cost_this_month = sum(
            (v.buying_price or Decimal("0")) for v in sold_this_month
        )
        stats["cost_this_month"] = cost_this_month
        stats["profit_this_month"] = stats["revenue_this_month"] - cost_this_month

        # Stock aging (days since created_at)
        from datetime import timedelta
        cutoff_30 = today - timedelta(days=30)
        cutoff_60 = today - timedelta(days=60)
        cutoff_90 = today - timedelta(days=90)
        stats["aging_30"] = in_stock_qs.filter(created_at__date__lte=cutoff_30, created_at__date__gt=cutoff_60).count()
        stats["aging_60"] = in_stock_qs.filter(created_at__date__lte=cutoff_60, created_at__date__gt=cutoff_90).count()
        stats["aging_90_plus"] = in_stock_qs.filter(created_at__date__lte=cutoff_90).count()

        # Vehicles by make (top 6); include free-text fallback via make_text
        vehicles_by_make = (
            in_stock_qs
            .values("model__make__name", "make_text")
            .annotate(count=Count("id"))
            .order_by("-count")[:6]
        )

        # Vehicles by fuel type
        vehicles_by_fuel = (
            in_stock_qs
            .exclude(fuel_type="")
            .values("fuel_type")
            .annotate(count=Count("id"))
            .order_by("-count")[:5]
        )

        # Recent 12 in-stock vehicles
        recent_vehicles = in_stock_qs.select_related("model__make", "make").order_by("-created_at")[:12]

        # 5 most recent sales
        recent_sold = (
            qs.filter(status="sold")
            .select_related("model__make", "make")
            .order_by("-sold_at")[:5]
        )

        # Total profit (sold vehicles: sale_price - buying_price)
        total_profit = Decimal("0")
        for v in qs.filter(status="sold"):
            sp = v.sale_price or v.selling_price or Decimal("0")
            bp = v.buying_price or Decimal("0")
            total_profit += (sp - bp)

        # Month-over-month revenue (last 6 months) for chart
        import json as _json
        from datetime import timedelta
        monthly_revenue = []
        monthly_labels = []
        for months_ago in range(5, -1, -1):
            m_date = today.replace(day=1)
            # step back months_ago months
            for _ in range(months_ago):
                m_date = (m_date - timedelta(days=1)).replace(day=1)
            sold_in_month = qs.filter(
                status="sold",
                sold_at__year=m_date.year,
                sold_at__month=m_date.month,
            )
            rev = sum((v.sale_price or v.selling_price or Decimal("0")) for v in sold_in_month)
            monthly_revenue.append(float(rev))
            monthly_labels.append(m_date.strftime("%b %Y"))

        stats["total_profit"] = total_profit

        # Vehicles by body type
        vehicles_by_body = (
            in_stock_qs
            .exclude(body_type="")
            .values("body_type")
            .annotate(count=Count("id"))
            .order_by("-count")[:6]
        )

        # Aged vehicles needing action (90+ days)
        aged_vehicles = (
            in_stock_qs.filter(created_at__date__lte=cutoff_90)
            .select_related("model__make", "make")
            .order_by("created_at")[:5]
        )

    else:
        import json as _json
        monthly_revenue = []
        monthly_labels = []
        vehicles_by_body = []
        aged_vehicles = []
        stats["total_profit"] = Decimal("0")

    return render(
        request,
        "car_dealer/dashboard.html",
        {
            "stats": stats,
            "recent_vehicles": recent_vehicles,
            "recent_sold": recent_sold,
            "vehicles_by_make": vehicles_by_make,
            "vehicles_by_fuel": vehicles_by_fuel,
            "vehicles_by_body": vehicles_by_body,
            "aged_vehicles": aged_vehicles,
            "monthly_revenue_json": _json.dumps(monthly_revenue),
            "monthly_labels_json": _json.dumps(monthly_labels),
            "business": biz,
            "BUSINESS_VERTICAL": "car_dealer",
        },
    )


# ---------------------------------------------------------------------------
# Vehicle list / inventory
# ---------------------------------------------------------------------------

@login_required
@require_business
def vehicle_list(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    CarMake, CarModel, CarDealerVehicle = _get_car_models()

    status_filter = request.GET.get("status", "")
    search_q = request.GET.get("q", "").strip()

    vehicles = []
    counts = {}
    if CarDealerVehicle:
        qs = CarDealerVehicle.objects.filter(business=biz).select_related("make", "model")
        counts = {
            "all": qs.count(),
            "in_stock": qs.filter(status="in_stock").count(),
            "sold": qs.filter(status="sold").count(),
            "reserved": qs.filter(status="reserved").count(),
        }
        if status_filter and status_filter != "all":
            qs = qs.filter(status=status_filter)
        if search_q:
            from django.db.models import Q
            qs = qs.filter(
                Q(make__name__icontains=search_q)
                | Q(model__name__icontains=search_q)
                | Q(make_text__icontains=search_q)
                | Q(model_text__icontains=search_q)
                | Q(color__icontains=search_q)
                | Q(stock_ref__icontains=search_q)
                | Q(chassis_no__icontains=search_q)
            )
        vehicles = qs.order_by("-created_at")

    return render(
        request,
        "car_dealer/vehicle_list.html",
        {
            "vehicles": vehicles,
            "counts": counts,
            "status_filter": status_filter,
            "search_q": search_q,
            "business": biz,
            "BUSINESS_VERTICAL": "car_dealer",
        },
    )


# ---------------------------------------------------------------------------
# Stock In / Add Vehicle
# ---------------------------------------------------------------------------

@login_required
@require_business
def stock_in_vehicle(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    if not is_manager(request.user, biz):
        messages.error(request, "Only managers can add vehicles.")
        return redirect("car_dealer:vehicle_list")

    CarMake, CarModel, CarDealerVehicle = _get_car_models()
    makes = CarMake.objects.order_by("sort_order", "name") if CarMake else []
    popular_makes = CarMake.objects.filter(is_popular=True).order_by("sort_order", "name") if CarMake else []
    car_models = CarModel.objects.select_related("make").order_by("make__name", "name") if CarModel else []

    if request.method == "POST":
        data = request.POST
        try:
            make_id = data.get("make_id")
            model_id = data.get("model_id")
            make_obj = CarMake.objects.get(pk=make_id) if make_id and CarMake else None
            model_obj = CarModel.objects.get(pk=model_id) if model_id and CarModel else None

            buying_price = None
            selling_price = None
            try:
                bp = data.get("buying_price", "").strip()
                if bp:
                    buying_price = Decimal(bp)
            except (InvalidOperation, ValueError):
                pass
            try:
                sp = data.get("selling_price", "").strip()
                if sp:
                    selling_price = Decimal(sp)
            except (InvalidOperation, ValueError):
                pass

            year_str = data.get("year", "").strip()
            year = int(year_str) if year_str.isdigit() else None

            mileage_str = data.get("mileage", "").strip()
            mileage = int(mileage_str) if mileage_str.isdigit() else None

            vehicle = CarDealerVehicle.objects.create(
                business=biz,
                make=make_obj,
                model=model_obj,
                make_text=data.get("make_text", "").strip(),
                model_text=data.get("model_text", "").strip(),
                year=year,
                trim=data.get("trim", "").strip(),
                body_type=data.get("body_type", "").strip(),
                transmission=data.get("transmission", "").strip(),
                fuel_type=data.get("fuel_type", "").strip(),
                drivetrain=data.get("drivetrain", "").strip(),
                engine_size=data.get("engine_size", "").strip(),
                mileage=mileage,
                color=data.get("color", "").strip(),
                interior_color=data.get("interior_color", "").strip(),
                chassis_no=data.get("chassis_no", "").strip(),
                stock_ref=data.get("stock_ref", "").strip(),
                buying_price=buying_price,
                selling_price=selling_price,
                condition=data.get("condition", "used"),
                location_text=data.get("location_text", "").strip(),
                description=data.get("description", "").strip(),
                features_notes=data.get("features_notes", "").strip(),
                import_source_notes=data.get("import_source_notes", "").strip(),
                stocked_by=request.user,
                status="in_stock",
            )

            messages.success(request, f"Vehicle '{vehicle.display_name}' added to inventory.")
            return redirect("car_dealer:vehicle_detail", pk=vehicle.pk)

        except Exception as e:
            log.exception("Error adding vehicle: %s", e)
            messages.error(request, f"Could not add vehicle: {e}")

    # Build car models JSON for JS
    import json
    car_models_by_make: dict[str, list] = {}
    for cm in car_models:
        key = str(cm.make_id)
        if key not in car_models_by_make:
            car_models_by_make[key] = []
        car_models_by_make[key].append({"id": cm.pk, "name": cm.name, "body_type": cm.body_type})

    return render(
        request,
        "car_dealer/stock_in.html",
        {
            "makes": makes,
            "popular_makes": popular_makes,
            "car_models_json": json.dumps(car_models_by_make),
            "business": biz,
            "BUSINESS_VERTICAL": "car_dealer",
            "current_year": timezone.now().year,
        },
    )


# ---------------------------------------------------------------------------
# Vehicle detail / quick edit
# ---------------------------------------------------------------------------

@login_required
@require_business
def vehicle_detail(request: HttpRequest, pk: int) -> HttpResponse:
    biz = get_active_business(request)
    CarMake, CarModel, CarDealerVehicle = _get_car_models()
    vehicle = get_object_or_404(CarDealerVehicle, pk=pk, business=biz)

    if request.method == "POST" and is_manager(request.user, biz):
        # Quick field updates
        for field in ["selling_price", "status", "location_text", "description", "features_notes"]:
            val = request.POST.get(field)
            if val is not None:
                if field == "selling_price":
                    try:
                        val = Decimal(val.strip()) if val.strip() else None
                    except (InvalidOperation, ValueError):
                        val = vehicle.selling_price
                setattr(vehicle, field, val)
        vehicle.save()
        messages.success(request, "Vehicle updated.")
        return redirect("car_dealer:vehicle_detail", pk=pk)

    return render(
        request,
        "car_dealer/vehicle_detail.html",
        {
            "vehicle": vehicle,
            "business": biz,
            "BUSINESS_VERTICAL": "car_dealer",
            "is_manager": is_manager(request.user, biz),
        },
    )


# ---------------------------------------------------------------------------
# Sell Vehicle
# ---------------------------------------------------------------------------

@login_required
@require_business
def sell_vehicle(request: HttpRequest, pk: int) -> HttpResponse:
    biz = get_active_business(request)
    if not is_manager(request.user, biz):
        messages.error(request, "Only managers can process vehicle sales.")
        return redirect("car_dealer:vehicle_detail", pk=pk)

    CarMake, CarModel, CarDealerVehicle = _get_car_models()
    vehicle = get_object_or_404(CarDealerVehicle, pk=pk, business=biz)

    if vehicle.status == "sold":
        messages.info(request, "This vehicle has already been sold.")
        return redirect("car_dealer:vehicle_detail", pk=pk)

    if request.method == "POST":
        buyer_name = request.POST.get("buyer_name", "").strip()
        buyer_phone = request.POST.get("buyer_phone", "").strip()
        payment_method = request.POST.get("payment_method", "CASH").strip()
        sale_price_raw = request.POST.get("sale_price", "").strip()

        sale_price = vehicle.selling_price
        if sale_price_raw:
            try:
                sale_price = Decimal(sale_price_raw)
            except (InvalidOperation, ValueError):
                pass

        try:
            vehicle.mark_sold(
                buyer_name=buyer_name,
                buyer_phone=buyer_phone,
                sale_price=sale_price,
                payment_method=payment_method,
                sold_by=request.user,
            )
            messages.success(
                request,
                f"Vehicle '{vehicle.display_name}' sold successfully. "
                f"Sale price: {biz.currency} {sale_price}.",
            )
            return redirect("car_dealer:vehicle_detail", pk=pk)
        except Exception as e:
            log.exception("Error processing vehicle sale: %s", e)
            messages.error(request, f"Could not process sale: {e}")

    return render(
        request,
        "car_dealer/sell_vehicle.html",
        {
            "vehicle": vehicle,
            "business": biz,
            "BUSINESS_VERTICAL": "car_dealer",
        },
    )


# ---------------------------------------------------------------------------
# Seed reference data
# ---------------------------------------------------------------------------

@login_required
@require_business
def seed_car_data(request: HttpRequest) -> HttpResponse:
    """
    One-click seed of CarMake / CarModel reference catalog.
    Safe to run multiple times (idempotent).  Manager-only.
    """
    from tenants.utils_roles import is_manager as _is_manager
    biz = get_active_business(request)

    if not _is_manager(request.user, biz):
        messages.error(request, "Only managers can seed reference data.")
        return redirect("car_dealer:dashboard")

    try:
        from inventory.management.commands.seed_car_dealer_data import CAR_DATA
        from inventory.models_car_dealer import CarMake, CarModel

        created_makes  = 0
        created_models = 0

        for entry in CAR_DATA:
            make_obj, make_new = CarMake.objects.get_or_create(
                name=entry["make"],
                defaults={
                    "slug": entry["make"].lower().replace(" ", "-").replace("-benz", "benz"),
                    "sort_order": entry.get("sort_order", 99),
                    "is_popular": entry.get("popular", False),
                },
            )
            if make_new:
                created_makes += 1

            for m in entry.get("models", []):
                _, model_new = CarModel.objects.get_or_create(
                    make=make_obj,
                    name=m["name"],
                    defaults={
                        "slug": (make_obj.slug + "-" + m["name"].lower().replace(" ", "-"))[:80],
                        "body_type": m.get("body_type", ""),
                        "common_years": m.get("common_years", ""),
                    },
                )
                if model_new:
                    created_models += 1

        if created_makes or created_models:
            messages.success(
                request,
                f"Seeded {created_makes} make(s) and {created_models} model(s). "
                "Data is ready for use.",
            )
        else:
            messages.info(request, "Reference catalog already up to date — nothing new to add.")
    except Exception as e:
        log.exception("Car data seeding failed: %s", e)
        messages.error(request, f"Seeding failed: {e}")

    return redirect("car_dealer:stock_in")

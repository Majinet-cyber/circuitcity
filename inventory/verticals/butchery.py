# inventory/verticals/butchery.py
"""
Butchery vertical — views.

Workflow:
  Intake → Processing/Cutting → Cuts/Products → Daily Sales → Reports → Export

Supports pork centres, abattoirs, and meat shops that buy carcasses and sell
named cuts by kg, piece, pack, bottle, etc.
"""
from __future__ import annotations

import csv
import uuid
from calendar import monthrange
from datetime import date as dt_date, timedelta
from decimal import Decimal
from io import BytesIO, StringIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction as db_transaction
from django.db.models import (
    Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value,
)
from django.db.models.functions import Coalesce, TruncDate
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from inventory.helpers import get_active_business
from inventory.models_butchery import (
    ButcheryCategory,
    ButcheryDailyLedger,
    ButcheryExpense,
    ButcheryIntake,
    ButcheryIntakeAllocation,
    ButcheryPaymentMethod,
    ButcheryProcessingBatch,
    ButcheryProcessingLine,
    ButcheryProduct,
    ButcherySale,
    MeatType,
)
from tenants.utils import require_business

_DEC = DecimalField(max_digits=16, decimal_places=2)
_ZERO = Decimal("0.00")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _coalesce(qs, field: str) -> Decimal:
    val = qs.aggregate(total=Coalesce(Sum(field), Value(0), output_field=_DEC))["total"]
    return Decimal(str(val or 0))


def _rev_expr():
    return ExpressionWrapper(
        F("quantity") * F("unit_price") - F("discount_amount"),
        output_field=_DEC,
    )


def _prof_expr():
    return ExpressionWrapper(
        F("quantity") * F("unit_price") - F("discount_amount") - F("quantity") * F("cost_price_snapshot"),
        output_field=_DEC,
    )


def _agg_sales(qs):
    """Return (revenue, profit, kg_sold) for the given ButcherySale queryset."""
    revenue = Decimal(str(
        qs.aggregate(r=Coalesce(Sum(_rev_expr()), Value(0), output_field=_DEC))["r"] or 0
    ))
    profit = Decimal(str(
        qs.aggregate(p=Coalesce(Sum(_prof_expr()), Value(0), output_field=_DEC))["p"] or 0
    ))
    kg_sold = Decimal(str(
        qs.filter(product__unit="kg").aggregate(
            kg=Coalesce(Sum("quantity"), Value(0), output_field=_DEC)
        )["kg"] or 0
    ))
    return revenue, profit, kg_sold


def _week_bounds(year: int, month: int, week_num: int):
    """Return (start_date, end_date) for week 1–5 of a month."""
    first_day = dt_date(year, month, 1)
    last_day = dt_date(year, month, monthrange(year, month)[1])
    start = first_day + timedelta(days=(week_num - 1) * 7)
    end = min(start + timedelta(days=6), last_day)
    return start, end


def _parse_period(request, today: dt_date):
    """
    Parse period from ?period= query param.
    Returns (label, start_date, end_date).
    Values: month (default), w1, w2, w3, w4, w5
    """
    period = request.GET.get("period", "month")
    year = today.year
    month = today.month

    if period in ("w1", "w2", "w3", "w4", "w5"):
        wn = int(period[1])
        start, end = _week_bounds(year, month, wn)
        label = f"Week {wn} ({start.strftime('%d %b')} – {end.strftime('%d %b %Y')})"
        return period, label, start, end

    # Consolidated month
    month_start = today.replace(day=1)
    month_end = today.replace(day=monthrange(year, month)[1])
    label = f"Consolidated Month ({month_start.strftime('%d %b')} – {month_end.strftime('%d %b %Y')})"
    return "month", label, month_start, month_end


def _generate_insights(products_qs, low_stock_count, out_of_stock_count,
                        today_revenue, today_profit, month_revenue) -> list[str]:
    insights = []
    if not products_qs.exists():
        insights.append("No cuts or products added yet. Add products to start recording sales.")
    if today_revenue == 0:
        insights.append("No sales recorded today. Start with Record Daily Sales or Quick Sell.")
    if low_stock_count:
        insights.append(f"{low_stock_count} cut(s) are running low — restock from intake soon.")
    if out_of_stock_count:
        insights.append(f"{out_of_stock_count} cut(s) are out of stock. Record intake to replenish.")
    if today_revenue > 0 and today_profit > 0:
        margin = float(today_profit / today_revenue * 100)
        if margin < 10:
            insights.append(f"Today's margin is low ({margin:.0f}%). Review cost allocation or selling prices.")
    if month_revenue == 0:
        insights.append("No sales this month yet. Record intake costs to unlock accurate profit tracking.")
    if products_qs.filter(cost_price=0).exists():
        insights.append("Some products have no cost price set. Add cost prices for accurate profit calculation.")
    return insights


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
@require_business
def dashboard(request):
    business = get_active_business(request)
    today = timezone.localdate()

    period_key, period_label, period_start, period_end = _parse_period(request, today)
    month_start = today.replace(day=1)

    live_sales = ButcherySale.objects.filter(business=business, is_rolled_back=False)

    today_qs = live_sales.filter(sold_at__date=today)
    month_qs = live_sales.filter(sold_at__date__gte=month_start)
    period_qs = live_sales.filter(sold_at__date__gte=period_start, sold_at__date__lte=period_end)

    today_revenue, today_profit, kg_today = _agg_sales(today_qs)
    month_revenue, month_profit, month_kg = _agg_sales(month_qs)
    period_revenue, period_profit, period_kg = _agg_sales(period_qs)

    today_count = today_qs.count()

    # Days tracked this month
    days_tracked = live_sales.filter(
        sold_at__date__gte=month_start
    ).annotate(d=TruncDate("sold_at")).values("d").distinct().count()

    # Active intakes this month
    current_intakes = ButcheryIntake.objects.filter(
        business=business, intake_date__gte=month_start
    ).count()

    # Stock health
    products_qs = ButcheryProduct.objects.filter(business=business, is_active=True)
    total_products = products_qs.count()
    low_stock_count = products_qs.filter(stock_quantity__gt=0, stock_quantity__lte=F("reorder_level")).count()
    out_of_stock_count = products_qs.filter(stock_quantity__lte=0).count()

    stock_value = Decimal(str(
        products_qs.aggregate(
            val=Coalesce(
                Sum(ExpressionWrapper(F("cost_price") * F("stock_quantity"), output_field=_DEC)),
                Value(0), output_field=_DEC,
            )
        )["val"] or 0
    ))

    # Top cuts for period
    top_cuts = (
        period_qs.values("product__name", "product__category", "product__unit")
        .annotate(
            revenue=Coalesce(Sum(_rev_expr()), Value(0), output_field=_DEC),
            qty=Coalesce(Sum("quantity"), Value(0), output_field=_DEC),
            profit=Coalesce(Sum(_prof_expr()), Value(0), output_field=_DEC),
        )
        .order_by("-revenue")[:6]
    )

    # Recent intakes
    recent_intakes = ButcheryIntake.objects.filter(business=business).order_by("-intake_date")[:5]

    # Ledger status today
    ledger_today = ButcheryDailyLedger.objects.filter(business=business, date=today).first()

    insights = _generate_insights(
        products_qs, low_stock_count, out_of_stock_count,
        today_revenue, today_profit, month_revenue,
    )

    ctx = {
        "business": business,
        "active_tab": "dashboard",
        "today": today,
        "period_key": period_key,
        "period_label": period_label,
        "period_start": period_start,
        "period_end": period_end,
        "today_revenue": today_revenue,
        "today_profit": today_profit,
        "today_count": today_count,
        "kg_today": kg_today,
        "month_revenue": month_revenue,
        "month_profit": month_profit,
        "month_kg": month_kg,
        "period_revenue": period_revenue,
        "period_profit": period_profit,
        "period_kg": period_kg,
        "days_tracked": days_tracked,
        "current_intakes": current_intakes,
        "total_products": total_products,
        "low_stock_count": low_stock_count,
        "out_of_stock_count": out_of_stock_count,
        "stock_value": stock_value,
        "top_cuts": list(top_cuts),
        "recent_intakes": recent_intakes,
        "ledger_today": ledger_today,
        "insights": insights,
        "meat_types": MeatType.choices,
        "category_map": dict(ButcheryCategory.choices),
    }
    return render(request, "verticals/butchery/dashboard.html", ctx)


# ---------------------------------------------------------------------------
# Products / Cuts
# ---------------------------------------------------------------------------

@login_required
@require_business
def products(request):
    business = get_active_business(request)
    search = request.GET.get("q", "").strip()
    cat_filter = request.GET.get("cat", "")
    meat_filter = request.GET.get("meat", "")
    show_inactive = request.GET.get("inactive", "") == "1"

    qs = ButcheryProduct.objects.filter(business=business)
    if not show_inactive:
        qs = qs.filter(is_active=True)
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))
    if cat_filter:
        qs = qs.filter(category=cat_filter)
    if meat_filter:
        qs = qs.filter(meat_type=meat_filter)

    # Stock value per product
    products_list = qs.order_by("category", "name")

    total_stock_value = Decimal(str(
        products_list.aggregate(
            val=Coalesce(
                Sum(ExpressionWrapper(F("cost_price") * F("stock_quantity"), output_field=_DEC)),
                Value(0), output_field=_DEC,
            )
        )["val"] or 0
    ))

    ctx = {
        "business": business,
        "active_tab": "products",
        "products": products_list,
        "meat_types": MeatType.choices,
        "categories": ButcheryCategory.choices,
        "search": search,
        "cat_filter": cat_filter,
        "meat_filter": meat_filter,
        "show_inactive": show_inactive,
        "total_stock_value": total_stock_value,
    }
    return render(request, "verticals/butchery/products.html", ctx)


@login_required
@require_business
def product_add(request):
    business = get_active_business(request)

    if request.method == "POST":
        try:
            name = request.POST.get("name", "").strip()
            if not name:
                messages.error(request, "Product name is required.")
                return redirect("butchery:product_add")

            ButcheryProduct.objects.create(
                business=business,
                name=name,
                category=request.POST.get("category", "other"),
                meat_type=request.POST.get("meat_type", "beef"),
                description=request.POST.get("description", "").strip(),
                cost_price=Decimal(request.POST.get("cost_price", "0").replace(",", "") or "0"),
                selling_price=Decimal(request.POST.get("selling_price", "0").replace(",", "") or "0"),
                unit=request.POST.get("unit", "kg"),
                stock_quantity=Decimal(request.POST.get("stock_quantity", "0").replace(",", "") or "0"),
                reorder_level=Decimal(request.POST.get("reorder_level", "2").replace(",", "") or "2"),
                created_by=request.user,
            )
            messages.success(request, f"Product '{name}' added.")
            return redirect("butchery:products")
        except Exception as exc:
            messages.error(request, f"Error: {exc}")

    ctx = {
        "business": business,
        "active_tab": "products",
        "meat_types": MeatType.choices,
        "categories": ButcheryCategory.choices,
        "unit_choices": ButcheryProduct.UNIT_CHOICES,
    }
    return render(request, "verticals/butchery/product_add.html", ctx)


@login_required
@require_business
def product_edit(request, product_id):
    business = get_active_business(request)
    product = get_object_or_404(ButcheryProduct, pk=product_id, business=business)

    if request.method == "POST":
        try:
            product.name = request.POST.get("name", product.name).strip()
            product.category = request.POST.get("category", product.category)
            product.meat_type = request.POST.get("meat_type", product.meat_type)
            product.description = request.POST.get("description", product.description).strip()
            product.cost_price = Decimal(request.POST.get("cost_price", str(product.cost_price)).replace(",", ""))
            product.selling_price = Decimal(request.POST.get("selling_price", str(product.selling_price)).replace(",", ""))
            product.unit = request.POST.get("unit", product.unit)
            product.stock_quantity = Decimal(request.POST.get("stock_quantity", str(product.stock_quantity)).replace(",", ""))
            product.reorder_level = Decimal(request.POST.get("reorder_level", str(product.reorder_level)).replace(",", ""))
            product.is_active = request.POST.get("is_active") == "1"
            product.save()
            messages.success(request, f"'{product.name}' updated.")
            return redirect("butchery:products")
        except Exception as exc:
            messages.error(request, f"Error: {exc}")

    ctx = {
        "business": business,
        "product": product,
        "active_tab": "products",
        "meat_types": MeatType.choices,
        "categories": ButcheryCategory.choices,
        "unit_choices": ButcheryProduct.UNIT_CHOICES,
    }
    return render(request, "verticals/butchery/product_edit.html", ctx)


# ---------------------------------------------------------------------------
# Intake
# ---------------------------------------------------------------------------

@login_required
@require_business
def intake(request):
    """Record a carcass / bulk meat intake from supplier."""
    business = get_active_business(request)

    if request.method == "POST":
        action = request.POST.get("action", "record_intake")

        if action == "record_intake":
            try:
                intake_weight = Decimal(request.POST.get("intake_weight_kg", "0").replace(",", "") or "0")
                total_cost = Decimal(request.POST.get("total_cost", "0").replace(",", "") or "0")
                if intake_weight <= 0:
                    messages.error(request, "Intake weight must be greater than 0.")
                else:
                    new_intake = ButcheryIntake.objects.create(
                        business=business,
                        intake_date=request.POST.get("intake_date") or timezone.localdate(),
                        meat_type=request.POST.get("meat_type", "beef"),
                        description=request.POST.get("description", "").strip(),
                        supplier_name=request.POST.get("supplier_name", "").strip(),
                        batch_ref=request.POST.get("batch_ref", "").strip(),
                        storage_location=request.POST.get("storage_location", "").strip(),
                        intake_weight_kg=intake_weight,
                        total_cost=total_cost,
                        notes=request.POST.get("notes", "").strip(),
                        created_by=request.user,
                    )
                    messages.success(
                        request,
                        f"Intake recorded: {intake_weight} kg {new_intake.get_meat_type_display()} "
                        f"from {new_intake.supplier_name or 'supplier'}. "
                        f"Cost/kg: MWK {new_intake.cost_per_kg:,.2f}."
                    )
            except Exception as exc:
                messages.error(request, f"Error recording intake: {exc}")

        elif action == "allocate":
            try:
                intake_id = request.POST.get("intake_id")
                intake_obj = get_object_or_404(ButcheryIntake, pk=intake_id, business=business)
                product_ids = request.POST.getlist("product_id")
                alloc_kgs = request.POST.getlist("alloc_kg")

                with db_transaction.atomic():
                    for pid, kg_str in zip(product_ids, alloc_kgs):
                        kg = Decimal(kg_str.replace(",", "") or "0")
                        if kg <= 0:
                            continue
                        prod = get_object_or_404(ButcheryProduct, pk=pid, business=business)
                        ButcheryIntakeAllocation.objects.create(
                            intake=intake_obj,
                            product=prod,
                            allocated_kg=kg,
                        )
                        prod.stock_quantity += kg
                        if intake_obj.cost_per_kg > 0:
                            prod.cost_price = intake_obj.cost_per_kg
                        prod.save(update_fields=["stock_quantity", "cost_price"])

                messages.success(request, "Allocation saved. Stock updated.")
            except Exception as exc:
                messages.error(request, f"Error allocating: {exc}")

        return redirect("butchery:intake")

    today = timezone.localdate()
    month_start = today.replace(day=1)
    intakes = ButcheryIntake.objects.filter(business=business).order_by("-intake_date")[:50]
    products_qs = ButcheryProduct.objects.filter(business=business, is_active=True).order_by("category", "name")

    month_intake_kg = Decimal(str(
        ButcheryIntake.objects.filter(business=business, intake_date__gte=month_start).aggregate(
            kg=Coalesce(Sum("intake_weight_kg"), Value(0), output_field=_DEC)
        )["kg"] or 0
    ))
    month_intake_cost = Decimal(str(
        ButcheryIntake.objects.filter(business=business, intake_date__gte=month_start).aggregate(
            c=Coalesce(Sum("total_cost"), Value(0), output_field=_DEC)
        )["c"] or 0
    ))

    ctx = {
        "business": business,
        "active_tab": "intake",
        "intakes": intakes,
        "products": products_qs,
        "meat_types": MeatType.choices,
        "today": today,
        "month_intake_kg": month_intake_kg,
        "month_intake_cost": month_intake_cost,
    }
    return render(request, "verticals/butchery/intake.html", ctx)


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------

@login_required
@require_business
def processing(request):
    """Processing/cutting flow: select intake, split into named cuts, update stock."""
    business = get_active_business(request)

    if request.method == "POST":
        action = request.POST.get("action", "create_batch")

        if action == "create_batch":
            try:
                input_kg = Decimal(request.POST.get("input_kg", "0").replace(",", "") or "0")
                if input_kg <= 0:
                    messages.error(request, "Input weight must be greater than 0.")
                    return redirect("butchery:processing")

                intake_id = request.POST.get("intake_id") or None
                waste_kg = Decimal(request.POST.get("waste_kg", "0").replace(",", "") or "0")

                intake_obj = None
                if intake_id:
                    intake_obj = get_object_or_404(ButcheryIntake, pk=intake_id, business=business)

                batch = ButcheryProcessingBatch.objects.create(
                    business=business,
                    batch_date=request.POST.get("batch_date") or timezone.localdate(),
                    meat_type=request.POST.get("meat_type", "beef"),
                    intake=intake_obj,
                    input_kg=input_kg,
                    waste_kg=waste_kg,
                    notes=request.POST.get("notes", "").strip(),
                    created_by=request.user,
                )

                # Process lines
                product_ids = request.POST.getlist("product_id")
                output_kgs = request.POST.getlist("output_kg")
                cost_per_kgs = request.POST.getlist("cost_per_kg")

                with db_transaction.atomic():
                    for pid, okg_str, cpkg_str in zip(product_ids, output_kgs, cost_per_kgs):
                        okg = Decimal(okg_str.replace(",", "") or "0")
                        cpkg = Decimal(cpkg_str.replace(",", "") or "0")
                        if okg <= 0:
                            continue
                        prod = get_object_or_404(ButcheryProduct, pk=pid, business=business)
                        ButcheryProcessingLine.objects.create(
                            batch=batch,
                            product=prod,
                            output_kg=okg,
                            cost_per_kg=cpkg,
                        )
                        prod.stock_quantity += okg
                        if cpkg > 0:
                            prod.cost_price = cpkg
                        prod.save(update_fields=["stock_quantity", "cost_price"])

                    batch.status = ButcheryProcessingBatch.STATUS_COMPLETE
                    batch.completed_at = timezone.now()
                    batch.save(update_fields=["status", "completed_at"])

                messages.success(
                    request,
                    f"Processing batch saved: {batch.input_kg} kg {batch.get_meat_type_display()} "
                    f"→ {batch.output_kg} kg cuts. Yield: {batch.yield_pct:.1f}%"
                )
            except Exception as exc:
                messages.error(request, f"Error: {exc}")

        return redirect("butchery:processing")

    today = timezone.localdate()
    batches = ButcheryProcessingBatch.objects.filter(business=business).prefetch_related("lines__product").order_by("-batch_date")[:30]
    intakes = ButcheryIntake.objects.filter(business=business).order_by("-intake_date")[:30]
    products_qs = ButcheryProduct.objects.filter(business=business, is_active=True).order_by("category", "name")

    ctx = {
        "business": business,
        "active_tab": "processing",
        "batches": batches,
        "intakes": intakes,
        "products": products_qs,
        "meat_types": MeatType.choices,
        "today": today,
    }
    return render(request, "verticals/butchery/processing.html", ctx)


# ---------------------------------------------------------------------------
# Daily Sales
# ---------------------------------------------------------------------------

@login_required
@require_business
def daily_sales(request):
    """
    Daily sales recorder.
    User selects date, enters MWK sales per product, system calculates quantity.
    Supports draft save and ledger locking.
    """
    business = get_active_business(request)
    today = timezone.localdate()

    if request.method == "POST":
        action = request.POST.get("action", "save_draft")
        sale_date_str = request.POST.get("sale_date", str(today))
        try:
            sale_date = dt_date.fromisoformat(sale_date_str)
        except ValueError:
            sale_date = today

        # Check if ledger is locked
        ledger = ButcheryDailyLedger.objects.filter(business=business, date=sale_date).first()
        if ledger and ledger.is_locked and action != "unlock":
            messages.error(request, f"Ledger for {sale_date} is locked. Unlock before editing.")
            return redirect(f"{request.path}?date={sale_date}")

        if action == "unlock":
            if ledger and ledger.is_locked:
                ledger.status = ButcheryDailyLedger.STATUS_DRAFT
                ledger.locked_by = None
                ledger.locked_at = None
                ledger.save(update_fields=["status", "locked_by", "locked_at"])
                messages.success(request, f"Ledger for {sale_date} unlocked.")
            return redirect(f"{request.path}?date={sale_date}")

        if action in ("save_draft", "save_lock"):
            product_ids = request.POST.getlist("product_id")
            mwk_sales_list = request.POST.getlist("mwk_sales")
            unit_prices = request.POST.getlist("unit_price")
            notes_list = request.POST.getlist("line_notes")
            payment_method = request.POST.get("payment_method", "cash")

            with db_transaction.atomic():
                # Remove previous draft entries for this date (allow re-submission)
                ButcherySale.objects.filter(
                    business=business,
                    sale_date=sale_date,
                    is_rolled_back=False,
                ).delete()

                receipt_ref = f"DL-{sale_date.strftime('%Y%m%d')}"
                saved_count = 0

                for pid, mwk_str, price_str, note in zip(
                    product_ids, mwk_sales_list, unit_prices, notes_list or [""] * len(product_ids)
                ):
                    try:
                        mwk_amount = Decimal(mwk_str.replace(",", "") or "0")
                        unit_price = Decimal(price_str.replace(",", "") or "0")
                    except Exception:
                        continue

                    if mwk_amount <= 0 or unit_price <= 0:
                        continue

                    try:
                        product = ButcheryProduct.objects.get(pk=pid, business=business)
                    except ButcheryProduct.DoesNotExist:
                        continue

                    # Calculate quantity from MWK amount / price per unit
                    quantity = (mwk_amount / unit_price).quantize(Decimal("0.001"))

                    ButcherySale.objects.create(
                        business=business,
                        product=product,
                        sold_at=timezone.make_aware(
                            timezone.datetime.combine(sale_date, timezone.datetime.min.time())
                        ),
                        sale_date=sale_date,
                        quantity=quantity,
                        unit_price=unit_price,
                        cost_price_snapshot=product.cost_price,
                        payment_method=payment_method,
                        receipt_ref=receipt_ref,
                        notes=note.strip(),
                        created_by=request.user,
                    )
                    saved_count += 1

                # Update or create ledger status
                status = (
                    ButcheryDailyLedger.STATUS_LOCKED
                    if action == "save_lock"
                    else ButcheryDailyLedger.STATUS_DRAFT
                )
                obj, _ = ButcheryDailyLedger.objects.get_or_create(
                    business=business, date=sale_date,
                    defaults={"status": status},
                )
                if action == "save_lock":
                    obj.status = ButcheryDailyLedger.STATUS_LOCKED
                    obj.locked_by = request.user
                    obj.locked_at = timezone.now()
                else:
                    obj.status = ButcheryDailyLedger.STATUS_DRAFT
                obj.save(update_fields=["status", "locked_by", "locked_at"])

                verb = "locked" if action == "save_lock" else "saved as draft"
                messages.success(
                    request,
                    f"{saved_count} sales entries {verb} for {sale_date.strftime('%d %b %Y')}."
                )

            return redirect(f"{request.path}?date={sale_date}")

    # --- GET ---
    sale_date_str = request.GET.get("date", str(today))
    try:
        sale_date = dt_date.fromisoformat(sale_date_str)
    except ValueError:
        sale_date = today

    # Existing sales for this date
    existing_sales = ButcherySale.objects.filter(
        business=business,
        sale_date=sale_date,
        is_rolled_back=False,
    ).select_related("product")

    existing_map = {s.product_id: s for s in existing_sales}
    ledger = ButcheryDailyLedger.objects.filter(business=business, date=sale_date).first()

    # All active products grouped by category for display
    products_qs = ButcheryProduct.objects.filter(
        business=business, is_active=True
    ).order_by("category", "name")

    # Group by category
    from collections import defaultdict
    category_groups = defaultdict(list)
    for p in products_qs:
        cat_label = p.get_category_display()
        entry = {
            "product": p,
            "existing_sale": existing_map.get(p.pk),
            "mwk_sales": existing_map[p.pk].total_amount if p.pk in existing_map else "",
            "qty_calc": existing_map[p.pk].quantity if p.pk in existing_map else "",
        }
        category_groups[cat_label].append(entry)

    # Summary for this date
    today_qs = ButcherySale.objects.filter(
        business=business, sale_date=sale_date, is_rolled_back=False
    )
    date_revenue, date_profit, date_kg = _agg_sales(today_qs)

    # Recent ledger statuses for the month
    month_start = today.replace(day=1)
    ledger_history = ButcheryDailyLedger.objects.filter(
        business=business, date__gte=month_start
    ).order_by("-date")[:31]

    ctx = {
        "business": business,
        "active_tab": "daily_sales",
        "today": today,
        "sale_date": sale_date,
        "category_groups": dict(category_groups),
        "ledger": ledger,
        "ledger_history": ledger_history,
        "date_revenue": date_revenue,
        "date_profit": date_profit,
        "date_kg": date_kg,
        "payment_methods": ButcheryPaymentMethod.choices,
        "categories": ButcheryCategory.choices,
    }
    return render(request, "verticals/butchery/daily_sales.html", ctx)


# ---------------------------------------------------------------------------
# Quick Sell
# ---------------------------------------------------------------------------

@login_required
@require_business
def sell(request):
    """Quick sell — record a sale of cut(s) with direct quantity input."""
    business = get_active_business(request)

    if request.method == "POST":
        try:
            with db_transaction.atomic():
                receipt_ref = request.POST.get("receipt_ref") or str(uuid.uuid4())[:8].upper()
                product_ids = request.POST.getlist("product_id")
                quantities = request.POST.getlist("quantity")
                unit_prices = request.POST.getlist("unit_price")
                payment_method = request.POST.get("payment_method", "cash")
                customer_name = request.POST.get("customer_name", "").strip()
                customer_phone = request.POST.get("customer_phone", "").strip()
                notes = request.POST.get("notes", "").strip()
                sale_date = timezone.localdate()

                if not product_ids:
                    messages.error(request, "Add at least one product to the sale.")
                    return redirect("butchery:sell")

                total_created = 0
                for pid, qty_str, price_str in zip(product_ids, quantities, unit_prices):
                    product = get_object_or_404(ButcheryProduct, pk=pid, business=business)
                    qty = Decimal(qty_str.replace(",", "") or "1")
                    price = Decimal(price_str.replace(",", "") or str(product.selling_price))
                    if qty <= 0:
                        continue

                    product.stock_quantity = max(Decimal("0"), product.stock_quantity - qty)
                    product.save(update_fields=["stock_quantity"])

                    ButcherySale.objects.create(
                        business=business,
                        product=product,
                        sale_date=sale_date,
                        quantity=qty,
                        unit_price=price,
                        cost_price_snapshot=product.cost_price,
                        payment_method=payment_method,
                        receipt_ref=receipt_ref,
                        customer_name=customer_name,
                        customer_phone=customer_phone,
                        notes=notes,
                        created_by=request.user,
                    )
                    total_created += 1

                messages.success(
                    request, f"Sale recorded — {total_created} item(s). Receipt: {receipt_ref}"
                )
                return redirect("butchery:sell")
        except Exception as exc:
            messages.error(request, f"Error: {exc}")

    products_qs = ButcheryProduct.objects.filter(
        business=business, is_active=True, stock_quantity__gt=0
    ).order_by("category", "name")

    ctx = {
        "business": business,
        "active_tab": "sell",
        "products": products_qs,
        "payment_methods": ButcheryPaymentMethod.choices,
        "today": timezone.localdate(),
    }
    return render(request, "verticals/butchery/sell.html", ctx)


# ---------------------------------------------------------------------------
# Sales History
# ---------------------------------------------------------------------------

@login_required
@require_business
def sales(request):
    business = get_active_business(request)
    today = timezone.localdate()

    date_from_str = request.GET.get("from", str(today - timedelta(days=30)))
    date_to_str = request.GET.get("to", str(today))
    try:
        date_from = dt_date.fromisoformat(date_from_str)
        date_to = dt_date.fromisoformat(date_to_str)
    except ValueError:
        date_from = today - timedelta(days=30)
        date_to = today

    qs = ButcherySale.objects.filter(
        business=business,
        is_rolled_back=False,
        sold_at__date__gte=date_from,
        sold_at__date__lte=date_to,
    ).select_related("product", "created_by")

    total_revenue, total_profit, total_kg = _agg_sales(qs)

    ctx = {
        "business": business,
        "active_tab": "sales",
        "sales": qs.order_by("-sold_at")[:200],
        "total_revenue": total_revenue,
        "total_profit": total_profit,
        "total_kg": total_kg,
        "count": qs.count(),
        "date_from": date_from,
        "date_to": date_to,
    }
    return render(request, "verticals/butchery/sales.html", ctx)


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------

@login_required
@require_business
def expenses(request):
    business = get_active_business(request)

    if request.method == "POST":
        try:
            ButcheryExpense.objects.create(
                business=business,
                description=request.POST.get("description", "").strip(),
                amount=Decimal(request.POST.get("amount", "0").replace(",", "") or "0"),
                category=request.POST.get("category", "other"),
                expense_date=request.POST.get("expense_date") or timezone.localdate(),
                notes=request.POST.get("notes", "").strip(),
                created_by=request.user,
            )
            messages.success(request, "Expense recorded.")
            return redirect("butchery:expenses")
        except Exception as exc:
            messages.error(request, f"Error: {exc}")

    expense_qs = ButcheryExpense.objects.filter(business=business)
    total_expenses = _coalesce(expense_qs, "amount")

    ctx = {
        "business": business,
        "active_tab": "expenses",
        "expenses": expense_qs.order_by("-expense_date")[:100],
        "total_expenses": total_expenses,
        "category_choices": ButcheryExpense.CATEGORY_CHOICES,
        "today": timezone.localdate(),
    }
    return render(request, "verticals/butchery/expenses.html", ctx)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@login_required
@require_business
def reports(request):
    business = get_active_business(request)
    today = timezone.localdate()
    month_start = today.replace(day=1)

    period_key, period_label, period_start, period_end = _parse_period(request, today)

    # Use period as date range
    date_from_str = request.GET.get("from", str(period_start))
    date_to_str = request.GET.get("to", str(period_end))

    if request.GET.get("period"):
        date_from = period_start
        date_to = period_end
    else:
        try:
            date_from = dt_date.fromisoformat(date_from_str)
            date_to = dt_date.fromisoformat(date_to_str)
        except ValueError:
            date_from = period_start
            date_to = period_end

    range_qs = ButcherySale.objects.filter(
        business=business, is_rolled_back=False,
        sold_at__date__gte=date_from, sold_at__date__lte=date_to,
    )
    month_qs = ButcherySale.objects.filter(
        business=business, is_rolled_back=False, sold_at__date__gte=month_start,
    )

    range_rev, range_prof, range_kg = _agg_sales(range_qs)
    month_rev, month_prof, _ = _agg_sales(month_qs)

    total_count = range_qs.count()
    margin_pct = float(range_prof / range_rev * 100) if range_rev > 0 else 0.0

    top_cuts = (
        range_qs.values("product__name", "product__category", "product__unit")
        .annotate(
            revenue=Coalesce(Sum(_rev_expr()), Value(0), output_field=_DEC),
            qty=Coalesce(Sum("quantity"), Value(0), output_field=_DEC),
            profit=Coalesce(Sum(_prof_expr()), Value(0), output_field=_DEC),
        )
        .order_by("-revenue")[:10]
    )

    by_category = (
        range_qs.values("product__category")
        .annotate(
            revenue=Coalesce(Sum(_rev_expr()), Value(0), output_field=_DEC),
            profit=Coalesce(Sum(_prof_expr()), Value(0), output_field=_DEC),
            count=Count("id"),
        )
        .order_by("-revenue")
    )

    by_meat_type = (
        range_qs.values("product__meat_type")
        .annotate(
            revenue=Coalesce(Sum(_rev_expr()), Value(0), output_field=_DEC),
            profit=Coalesce(Sum(_prof_expr()), Value(0), output_field=_DEC),
            count=Count("id"),
        )
        .order_by("-revenue")
    )

    # Daily summary
    daily_summary = (
        range_qs.annotate(d=TruncDate("sold_at"))
        .values("d")
        .annotate(
            revenue=Coalesce(Sum(_rev_expr()), Value(0), output_field=_DEC),
            profit=Coalesce(Sum(_prof_expr()), Value(0), output_field=_DEC),
            count=Count("id"),
        )
        .order_by("d")
    )

    expense_qs = ButcheryExpense.objects.filter(
        business=business, expense_date__gte=date_from, expense_date__lte=date_to,
    )
    total_expenses = _coalesce(expense_qs, "amount")
    net_profit = range_prof - total_expenses

    intake_qs = ButcheryIntake.objects.filter(
        business=business, intake_date__gte=date_from, intake_date__lte=date_to,
    )
    total_intake_kg = Decimal(str(
        intake_qs.aggregate(kg=Coalesce(Sum("intake_weight_kg"), Value(0), output_field=_DEC))["kg"] or 0
    ))
    total_intake_cost = _coalesce(intake_qs, "total_cost")

    # Ledger status for period
    ledgers = ButcheryDailyLedger.objects.filter(
        business=business, date__gte=date_from, date__lte=date_to
    ).order_by("-date")

    category_map = dict(ButcheryCategory.choices)
    meat_type_map = dict(MeatType.choices)

    ctx = {
        "business": business,
        "active_tab": "reports",
        "today": today,
        "period_key": period_key,
        "period_label": period_label,
        "date_from": date_from,
        "date_to": date_to,
        "range_revenue": range_rev,
        "range_profit": range_prof,
        "range_kg": range_kg,
        "total_count": total_count,
        "margin_pct": margin_pct,
        "month_revenue": month_rev,
        "month_profit": month_prof,
        "top_cuts": list(top_cuts),
        "by_category": list(by_category),
        "by_meat_type": list(by_meat_type),
        "daily_summary": list(daily_summary),
        "total_expenses": total_expenses,
        "net_profit": net_profit,
        "total_intake_kg": total_intake_kg,
        "total_intake_cost": total_intake_cost,
        "ledgers": ledgers,
        "category_map": category_map,
        "meat_type_map": meat_type_map,
    }
    return render(request, "verticals/butchery/reports.html", ctx)


# ---------------------------------------------------------------------------
# CSV Export
# ---------------------------------------------------------------------------

@login_required
@require_business
def reports_export_csv(request):
    """Export butchery sales as CSV for a period."""
    business = get_active_business(request)
    today = timezone.localdate()

    period_key, period_label, period_start, period_end = _parse_period(request, today)

    date_from_str = request.GET.get("from", str(period_start))
    date_to_str = request.GET.get("to", str(period_end))
    if request.GET.get("period"):
        date_from = period_start
        date_to = period_end
    else:
        try:
            date_from = dt_date.fromisoformat(date_from_str)
            date_to = dt_date.fromisoformat(date_to_str)
        except ValueError:
            date_from = period_start
            date_to = period_end

    qs = ButcherySale.objects.filter(
        business=business,
        is_rolled_back=False,
        sold_at__date__gte=date_from,
        sold_at__date__lte=date_to,
    ).select_related("product").order_by("sold_at")

    filename = f"butchery_sales_{date_from.strftime('%Y%m%d')}_{date_to.strftime('%Y%m%d')}.csv"
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        "Date", "Period", "Receipt Ref", "Category", "Product", "Unit",
        "Price/Unit (MWK)", "Quantity", "MWK Sales", "Cost (MWK)",
        "Gross Profit (MWK)", "Payment Method", "Customer", "Notes",
        "Ledger Status", "Business",
    ])

    # Ledger lookup
    ledger_map = {
        lv.date: lv.get_status_display()
        for lv in ButcheryDailyLedger.objects.filter(
            business=business, date__gte=date_from, date__lte=date_to
        )
    }
    cat_map = dict(ButcheryCategory.choices)

    for sale in qs:
        sale_date_obj = sale.sale_date or (sale.sold_at.date() if sale.sold_at else None)
        writer.writerow([
            sale_date_obj.strftime("%Y-%m-%d") if sale_date_obj else "",
            period_label,
            sale.receipt_ref,
            cat_map.get(sale.product.category, sale.product.category),
            sale.product.name,
            sale.product.get_unit_display(),
            str(sale.unit_price),
            str(sale.quantity),
            str(sale.total_amount),
            str((sale.quantity * sale.cost_price_snapshot).quantize(Decimal("0.01"))),
            str(sale.profit),
            sale.get_payment_method_display(),
            sale.customer_name,
            sale.notes,
            ledger_map.get(sale_date_obj, ""),
            business.name,
        ])

    return response


# ---------------------------------------------------------------------------
# PDF Export
# ---------------------------------------------------------------------------

@login_required
@require_business
def reports_export_pdf(request):
    """Export butchery sales summary as PDF using ReportLab."""
    business = get_active_business(request)
    today = timezone.localdate()

    period_key, period_label, period_start, period_end = _parse_period(request, today)
    date_from_str = request.GET.get("from", str(period_start))
    date_to_str = request.GET.get("to", str(period_end))
    if request.GET.get("period"):
        date_from = period_start
        date_to = period_end
    else:
        try:
            date_from = dt_date.fromisoformat(date_from_str)
            date_to = dt_date.fromisoformat(date_to_str)
        except ValueError:
            date_from = period_start
            date_to = period_end

    qs = ButcherySale.objects.filter(
        business=business,
        is_rolled_back=False,
        sold_at__date__gte=date_from,
        sold_at__date__lte=date_to,
    ).select_related("product").order_by("sold_at")

    range_rev, range_prof, range_kg = _agg_sales(qs)
    total_expenses = _coalesce(
        ButcheryExpense.objects.filter(
            business=business, expense_date__gte=date_from, expense_date__lte=date_to
        ),
        "amount"
    )
    net_profit = range_prof - total_expenses

    top_cuts = (
        qs.values("product__name", "product__category")
        .annotate(
            revenue=Coalesce(Sum(_rev_expr()), Value(0), output_field=_DEC),
            qty=Coalesce(Sum("quantity"), Value(0), output_field=_DEC),
            profit=Coalesce(Sum(_prof_expr()), Value(0), output_field=_DEC),
        )
        .order_by("-revenue")[:15]
    )

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
        )
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            rightMargin=15 * mm, leftMargin=15 * mm,
            topMargin=15 * mm, bottomMargin=15 * mm,
        )
        styles = getSampleStyleSheet()
        GREEN = colors.HexColor("#10b981")
        DARK = colors.HexColor("#0f172a")
        LIGHT_GREEN = colors.HexColor("#dcfce7")
        SLATE = colors.HexColor("#64748b")

        title_style = ParagraphStyle("title", parent=styles["Heading1"], fontSize=18, textColor=DARK, spaceAfter=4)
        sub_style = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9, textColor=SLATE, spaceAfter=2)
        section_style = ParagraphStyle("section", parent=styles["Heading2"], fontSize=11, textColor=GREEN, spaceBefore=12, spaceAfter=4)
        normal_style = ParagraphStyle("norm", parent=styles["Normal"], fontSize=9)

        story = []

        # Header
        story.append(Paragraph("Emajinet", ParagraphStyle("brand", parent=styles["Normal"], fontSize=10, textColor=GREEN, spaceAfter=2)))
        story.append(Paragraph(business.name, title_style))
        story.append(Paragraph("Butchery Sales Report", sub_style))
        story.append(Paragraph(period_label, sub_style))
        story.append(Paragraph(f"Generated: {today.strftime('%d %B %Y')}", sub_style))
        story.append(HRFlowable(width="100%", thickness=1, color=GREEN, spaceAfter=12))

        # KPI summary
        story.append(Paragraph("Summary", section_style))
        kpi_data = [
            ["Metric", "Value"],
            ["Period", period_label],
            ["Total Revenue", f"MWK {range_rev:,.2f}"],
            ["Gross Profit", f"MWK {range_prof:,.2f}"],
            ["Total Expenses", f"MWK {total_expenses:,.2f}"],
            ["Net Profit", f"MWK {net_profit:,.2f}"],
            ["KG Sold", f"{range_kg:,.2f} kg"],
            ["Transactions", str(qs.count())],
        ]
        kpi_table = Table(kpi_data, colWidths=[90 * mm, 80 * mm])
        kpi_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), GREEN),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 1), (-1, -1), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ]))
        story.append(kpi_table)
        story.append(Spacer(1, 8 * mm))

        # Top cuts
        if top_cuts:
            story.append(Paragraph("Top Cuts / Products", section_style))
            cut_data = [["Product", "Category", "Revenue (MWK)", "Quantity", "Profit (MWK)"]]
            cat_map = dict(ButcheryCategory.choices)
            for row in top_cuts:
                cut_data.append([
                    row["product__name"],
                    cat_map.get(row["product__category"], row["product__category"]),
                    f"{row['revenue']:,.2f}",
                    f"{row['qty']:,.3f}",
                    f"{row['profit']:,.2f}",
                ])
            cut_table = Table(cut_data, colWidths=[55 * mm, 35 * mm, 38 * mm, 28 * mm, 38 * mm])
            cut_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), GREEN),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.append(cut_table)

        story.append(Spacer(1, 10 * mm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=SLATE, spaceAfter=6))
        story.append(Paragraph(f"Emajinet — Butchery Management System — {business.name}", sub_style))
        story.append(Paragraph("Authorised by: ___________________________   Date: ___________", sub_style))

        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()

        filename = f"butchery_report_{date_from.strftime('%Y%m%d')}_{date_to.strftime('%Y%m%d')}.pdf"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    except ImportError:
        messages.error(request, "PDF generation requires ReportLab. Please install it: pip install reportlab")
        return redirect("butchery:reports")

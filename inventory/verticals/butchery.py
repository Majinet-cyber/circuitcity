# inventory/verticals/butchery.py
"""
Butchery vertical — views.

Supports butcheries that buy meat/carcasses and sell named cuts by kg or piece.

Workflow:
  Intake (carcass) → Optional allocation to cuts → Sell cuts → Track profit
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction as db_transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from inventory.helpers import get_active_business
from inventory.models_butchery import (
    ButcheryExpense,
    ButcheryIntake,
    ButcheryIntakeAllocation,
    ButcheryPaymentMethod,
    ButcheryProduct,
    ButcherySale,
    MeatType,
)
from tenants.utils import require_business

_DEC = DecimalField(max_digits=16, decimal_places=2)
_ZERO = Decimal("0.00")


def _coalesce(qs, field: str) -> Decimal:
    val = qs.aggregate(total=Coalesce(Sum(field), Value(0), output_field=_DEC))["total"]
    return Decimal(str(val or 0))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
@require_business
def dashboard(request):
    business = get_active_business(request)
    today = timezone.localdate()
    month_start = today.replace(day=1)

    live_sales = ButcherySale.objects.filter(business=business, is_rolled_back=False)

    today_qs = live_sales.filter(sold_at__date=today)
    month_qs = live_sales.filter(sold_at__date__gte=month_start)

    today_revenue = _coalesce(today_qs, "unit_price")  # will use property below
    # Aggregate revenue manually since it's a calculated property
    from django.db.models import F as _F, ExpressionWrapper as _EW
    today_revenue = Decimal(str(
        today_qs.aggregate(
            rev=Coalesce(
                Sum(_EW(_F("quantity") * _F("unit_price") - _F("discount_amount"), output_field=_DEC)),
                Value(0), output_field=_DEC,
            )
        )["rev"] or 0
    ))
    today_profit = Decimal(str(
        today_qs.aggregate(
            prof=Coalesce(
                Sum(_EW(
                    _F("quantity") * _F("unit_price") - _F("discount_amount") - _F("quantity") * _F("cost_price_snapshot"),
                    output_field=_DEC,
                )),
                Value(0), output_field=_DEC,
            )
        )["prof"] or 0
    ))
    today_count = today_qs.count()

    month_revenue = Decimal(str(
        month_qs.aggregate(
            rev=Coalesce(
                Sum(_EW(_F("quantity") * _F("unit_price") - _F("discount_amount"), output_field=_DEC)),
                Value(0), output_field=_DEC,
            )
        )["rev"] or 0
    ))
    month_profit = Decimal(str(
        month_qs.aggregate(
            prof=Coalesce(
                Sum(_EW(
                    _F("quantity") * _F("unit_price") - _F("discount_amount") - _F("quantity") * _F("cost_price_snapshot"),
                    output_field=_DEC,
                )),
                Value(0), output_field=_DEC,
            )
        )["prof"] or 0
    ))

    # kg sold today
    kg_today = Decimal(str(
        today_qs.filter(product__unit="kg").aggregate(
            kg=Coalesce(Sum("quantity"), Value(0), output_field=_DEC)
        )["kg"] or 0
    ))

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

    # Top cuts today
    top_cuts = (
        today_qs.values("product__name", "product__meat_type")
        .annotate(
            revenue=Coalesce(
                Sum(ExpressionWrapper(_F("quantity") * _F("unit_price") - _F("discount_amount"), output_field=_DEC)),
                Value(0), output_field=_DEC,
            ),
            qty=Coalesce(Sum("quantity"), Value(0), output_field=_DEC),
        )
        .order_by("-revenue")[:5]
    )

    # Recent intakes
    recent_intakes = ButcheryIntake.objects.filter(business=business).order_by("-intake_date")[:5]

    # Insights
    insights = _generate_insights(
        products_qs, low_stock_count, out_of_stock_count,
        today_revenue, today_profit, month_revenue,
    )

    ctx = {
        "business": business,
        "active_tab": "dashboard",
        "today": today,
        "today_revenue": today_revenue,
        "today_profit": today_profit,
        "today_count": today_count,
        "kg_today": kg_today,
        "month_revenue": month_revenue,
        "month_profit": month_profit,
        "total_products": total_products,
        "low_stock_count": low_stock_count,
        "out_of_stock_count": out_of_stock_count,
        "stock_value": stock_value,
        "top_cuts": list(top_cuts),
        "recent_intakes": recent_intakes,
        "insights": insights,
        "meat_types": MeatType.choices,
    }
    return render(request, "verticals/butchery/dashboard.html", ctx)


def _generate_insights(products_qs, low_stock_count, out_of_stock_count, today_revenue, today_profit, month_revenue) -> list[str]:
    insights = []
    if not products_qs.exists():
        insights.append("No cuts or products added yet. Add products to start selling.")
    if low_stock_count:
        insights.append(f"{low_stock_count} cut(s) are running low — restock from intake soon.")
    if out_of_stock_count:
        insights.append(f"{out_of_stock_count} cut(s) are out of stock. Record intake to replenish.")
    if today_revenue > 0 and today_profit > 0:
        margin = float(today_profit / today_revenue * 100)
        if margin < 10:
            insights.append(f"Today's margin is low ({margin:.0f}%). Review cost allocation or selling price.")
    if month_revenue == 0:
        insights.append("No sales this month yet. Use Quick Sell to record sales.")
    return insights


# ---------------------------------------------------------------------------
# Products / Cuts
# ---------------------------------------------------------------------------

@login_required
@require_business
def products(request):
    business = get_active_business(request)
    search = request.GET.get("q", "").strip()
    meat_filter = request.GET.get("meat", "")

    qs = ButcheryProduct.objects.filter(business=business, is_active=True)
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))
    if meat_filter:
        qs = qs.filter(meat_type=meat_filter)

    ctx = {
        "business": business,
        "active_tab": "products",
        "products": qs.order_by("meat_type", "name"),
        "meat_types": MeatType.choices,
        "search": search,
        "meat_filter": meat_filter,
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
            product.meat_type = request.POST.get("meat_type", product.meat_type)
            product.description = request.POST.get("description", product.description).strip()
            product.cost_price = Decimal(request.POST.get("cost_price", str(product.cost_price)).replace(",", ""))
            product.selling_price = Decimal(request.POST.get("selling_price", str(product.selling_price)).replace(",", ""))
            product.unit = request.POST.get("unit", product.unit)
            product.stock_quantity = Decimal(request.POST.get("stock_quantity", str(product.stock_quantity)).replace(",", ""))
            product.reorder_level = Decimal(request.POST.get("reorder_level", str(product.reorder_level)).replace(",", ""))
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
                        intake_weight_kg=intake_weight,
                        total_cost=total_cost,
                        notes=request.POST.get("notes", "").strip(),
                        created_by=request.user,
                    )
                    messages.success(
                        request,
                        f"Intake recorded: {intake_weight}kg {new_intake.get_meat_type_display()} "
                        f"from {new_intake.supplier_name or 'supplier'}."
                    )
            except Exception as exc:
                messages.error(request, f"Error recording intake: {exc}")

        elif action == "allocate":
            # Allocate intake to named cuts and add stock
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
                        # Update cost_price based on intake cost-per-kg
                        if intake_obj.cost_per_kg > 0:
                            prod.cost_price = intake_obj.cost_per_kg
                        prod.save(update_fields=["stock_quantity", "cost_price"])

                messages.success(request, "Allocation saved. Stock updated.")
            except Exception as exc:
                messages.error(request, f"Error allocating: {exc}")

        return redirect("butchery:intake")

    # GET
    intakes = ButcheryIntake.objects.filter(business=business).order_by("-intake_date")[:50]
    products_qs = ButcheryProduct.objects.filter(business=business, is_active=True).order_by("meat_type", "name")

    ctx = {
        "business": business,
        "active_tab": "intake",
        "intakes": intakes,
        "products": products_qs,
        "meat_types": MeatType.choices,
        "today": timezone.localdate(),
    }
    return render(request, "verticals/butchery/intake.html", ctx)


# ---------------------------------------------------------------------------
# Quick Sell
# ---------------------------------------------------------------------------

@login_required
@require_business
def sell(request):
    """Quick sell — record a sale of cut(s)."""
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
    ).order_by("meat_type", "name")

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
        from datetime import date as dt_date
        date_from = dt_date.fromisoformat(date_from_str)
        date_to = dt_date.fromisoformat(date_to_str)
    except ValueError:
        date_from = today - timedelta(days=30)
        date_to = today

    from django.db.models import F as _F, ExpressionWrapper as _EW
    qs = ButcherySale.objects.filter(
        business=business,
        is_rolled_back=False,
        sold_at__date__gte=date_from,
        sold_at__date__lte=date_to,
    ).select_related("product", "created_by")

    total_revenue = Decimal(str(
        qs.aggregate(
            rev=Coalesce(
                Sum(_EW(_F("quantity") * _F("unit_price") - _F("discount_amount"), output_field=_DEC)),
                Value(0), output_field=_DEC,
            )
        )["rev"] or 0
    ))
    total_profit = Decimal(str(
        qs.aggregate(
            prof=Coalesce(
                Sum(_EW(
                    _F("quantity") * _F("unit_price") - _F("discount_amount") - _F("quantity") * _F("cost_price_snapshot"),
                    output_field=_DEC,
                )),
                Value(0), output_field=_DEC,
            )
        )["prof"] or 0
    ))

    ctx = {
        "business": business,
        "active_tab": "sales",
        "sales": qs.order_by("-sold_at")[:200],
        "total_revenue": total_revenue,
        "total_profit": total_profit,
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

    date_from_str = request.GET.get("from", str(today - timedelta(days=30)))
    date_to_str = request.GET.get("to", str(today))
    try:
        from datetime import date as dt_date
        date_from = dt_date.fromisoformat(date_from_str)
        date_to = dt_date.fromisoformat(date_to_str)
    except ValueError:
        date_from = today - timedelta(days=30)
        date_to = today

    from django.db.models import F as _F, ExpressionWrapper as _EW
    range_qs = ButcherySale.objects.filter(
        business=business, is_rolled_back=False,
        sold_at__date__gte=date_from, sold_at__date__lte=date_to,
    )
    month_qs = ButcherySale.objects.filter(
        business=business, is_rolled_back=False, sold_at__date__gte=month_start,
    )

    rev_expr = _EW(_F("quantity") * _F("unit_price") - _F("discount_amount"), output_field=_DEC)
    prof_expr = _EW(
        _F("quantity") * _F("unit_price") - _F("discount_amount") - _F("quantity") * _F("cost_price_snapshot"),
        output_field=_DEC,
    )

    total_revenue = Decimal(str(range_qs.aggregate(r=Coalesce(Sum(rev_expr), Value(0), output_field=_DEC))["r"] or 0))
    total_profit = Decimal(str(range_qs.aggregate(p=Coalesce(Sum(prof_expr), Value(0), output_field=_DEC))["p"] or 0))
    total_count = range_qs.count()
    margin_pct = float(total_profit / total_revenue * 100) if total_revenue > 0 else 0.0

    month_revenue = Decimal(str(month_qs.aggregate(r=Coalesce(Sum(rev_expr), Value(0), output_field=_DEC))["r"] or 0))
    month_profit = Decimal(str(month_qs.aggregate(p=Coalesce(Sum(prof_expr), Value(0), output_field=_DEC))["p"] or 0))

    top_cuts = (
        range_qs.values("product__name", "product__meat_type", "product__unit")
        .annotate(
            revenue=Coalesce(Sum(rev_expr), Value(0), output_field=_DEC),
            qty=Coalesce(Sum("quantity"), Value(0), output_field=_DEC),
            profit=Coalesce(Sum(prof_expr), Value(0), output_field=_DEC),
        )
        .order_by("-revenue")[:10]
    )

    by_meat_type = (
        range_qs.values("product__meat_type")
        .annotate(
            revenue=Coalesce(Sum(rev_expr), Value(0), output_field=_DEC),
            profit=Coalesce(Sum(prof_expr), Value(0), output_field=_DEC),
            count=Count("id"),
        )
        .order_by("-revenue")
    )

    expense_qs = ButcheryExpense.objects.filter(
        business=business, expense_date__gte=date_from, expense_date__lte=date_to,
    )
    total_expenses = _coalesce(expense_qs, "amount")
    net_profit = total_profit - total_expenses

    intake_qs = ButcheryIntake.objects.filter(
        business=business, intake_date__gte=date_from, intake_date__lte=date_to,
    )
    total_intake_kg = Decimal(str(
        intake_qs.aggregate(kg=Coalesce(Sum("intake_weight_kg"), Value(0), output_field=_DEC))["kg"] or 0
    ))
    total_intake_cost = _coalesce(intake_qs, "total_cost")

    ctx = {
        "business": business,
        "active_tab": "reports",
        "today": today,
        "date_from": date_from,
        "date_to": date_to,
        "total_revenue": total_revenue,
        "total_profit": total_profit,
        "total_count": total_count,
        "margin_pct": margin_pct,
        "month_revenue": month_revenue,
        "month_profit": month_profit,
        "top_cuts": list(top_cuts),
        "by_meat_type": list(by_meat_type),
        "total_expenses": total_expenses,
        "net_profit": net_profit,
        "total_intake_kg": total_intake_kg,
        "total_intake_cost": total_intake_cost,
        "meat_type_labels": dict(MeatType.choices),
    }
    return render(request, "verticals/butchery/reports.html", ctx)

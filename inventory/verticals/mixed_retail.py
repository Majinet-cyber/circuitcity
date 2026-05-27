# inventory/verticals/mixed_retail.py
"""
Mixed Retail vertical — views.

Supports businesses selling multiple product types:
  clothing + electronics + furniture + appliances + cosmetics + groceries, etc.

Hierarchy: Department → Category → Product → Sale
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
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from inventory.helpers import get_active_business
from inventory.mixed_retail_seed import (
    get_all_departments_with_status,
    get_categories_for_department,
    get_departments_for_business,
    get_product_templates_for_department,
)
from inventory.models_mixed_retail import (
    RetailBusinessDepartment,
    RetailCategory,
    RetailDepartment,
    RetailExpense,
    RetailPaymentMethod,
    RetailProduct,
    RetailProductTemplate,
    RetailSale,
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
    week_start = today - timedelta(days=today.weekday())

    live_qs = RetailSale.objects.filter(business=business, is_rolled_back=False)

    # Today's metrics
    today_qs = live_qs.filter(sold_at__date=today)
    today_sales = _coalesce(today_qs, "total_amount")
    today_profit = _coalesce(today_qs, "profit")
    today_count = today_qs.count()

    # Month metrics
    month_qs = live_qs.filter(sold_at__date__gte=month_start)
    month_sales = _coalesce(month_qs, "total_amount")
    month_profit = _coalesce(month_qs, "profit")

    # Stock health
    products_qs = RetailProduct.objects.filter(business=business, is_active=True)
    total_products = products_qs.count()
    low_stock_items = products_qs.filter(
        stock_quantity__gt=0,
        stock_quantity__lte=F("reorder_level"),
    )
    low_stock_count = low_stock_items.count()
    out_of_stock_count = products_qs.filter(stock_quantity__lte=0).count()

    # Stock value
    stock_value = Decimal(str(
        products_qs.aggregate(
            val=Coalesce(
                Sum(
                    ExpressionWrapper(
                        F("cost_price") * F("stock_quantity"),
                        output_field=_DEC,
                    )
                ),
                Value(0),
                output_field=_DEC,
            )
        )["val"] or 0
    ))

    # Top 5 products today
    top_products = (
        today_qs.values("product__name", "product__department__name")
        .annotate(
            total_revenue=Coalesce(Sum("total_amount"), Value(0), output_field=_DEC),
            total_qty=Coalesce(Sum("quantity"), Value(0), output_field=_DEC),
        )
        .order_by("-total_revenue")[:5]
    )

    # Sales by payment method today
    payment_mix = (
        today_qs.values("payment_method")
        .annotate(total=Coalesce(Sum("total_amount"), Value(0), output_field=_DEC))
        .order_by("-total")
    )

    # Department performance (month)
    dept_perf = (
        month_qs.values("product__department__name")
        .annotate(
            revenue=Coalesce(Sum("total_amount"), Value(0), output_field=_DEC),
            profit=Coalesce(Sum("profit"), Value(0), output_field=_DEC),
        )
        .order_by("-revenue")[:6]
    )

    # Gamification badges
    badges = _compute_badges(business, today, week_start, products_qs, live_qs)

    # Departments for quick navigation
    departments = get_departments_for_business(business)

    # Insights
    insights = _generate_insights(
        business=business,
        today_profit=today_profit,
        today_sales=today_sales,
        low_stock_count=low_stock_count,
        out_of_stock_count=out_of_stock_count,
        month_profit=month_profit,
        month_sales=month_sales,
    )

    ctx = {
        "business": business,
        "active_tab": "dashboard",
        "today": today,
        # Today
        "today_sales": today_sales,
        "today_profit": today_profit,
        "today_count": today_count,
        # Month
        "month_sales": month_sales,
        "month_profit": month_profit,
        # Stock
        "total_products": total_products,
        "low_stock_count": low_stock_count,
        "out_of_stock_count": out_of_stock_count,
        "stock_value": stock_value,
        # Lists
        "top_products": list(top_products),
        "payment_mix": list(payment_mix),
        "dept_perf": list(dept_perf),
        "departments": departments,
        "badges": badges,
        "insights": insights,
    }
    return render(request, "verticals/mixed_retail/dashboard.html", ctx)


def _compute_badges(business, today, week_start, products_qs, live_qs) -> list[dict]:
    """Compute gamification badges for the mixed retail dashboard."""
    badges = []
    week_qs = live_qs.filter(sold_at__date__gte=week_start)

    # Stock Master: no out-of-stock this week (i.e. all active products have qty > 0)
    if products_qs.filter(stock_quantity__lte=0).count() == 0 and products_qs.exists():
        badges.append({
            "name": "Stock Master",
            "icon": "bi-archive-fill",
            "color": "success",
            "description": "All products in stock this week",
        })

    # Profit Hunter: gross margin > 20% today
    today_qs = live_qs.filter(sold_at__date=today)
    today_revenue = _coalesce(today_qs, "total_amount")
    today_profit_val = _coalesce(today_qs, "profit")
    if today_revenue > 0:
        margin = float(today_profit_val / today_revenue * 100)
        if margin >= 20:
            badges.append({
                "name": "Profit Hunter",
                "icon": "bi-graph-up-arrow",
                "color": "warning",
                "description": f"{margin:.0f}% gross margin today",
            })

    # Cash Discipline: less than 20% credit sales today
    credit_sales = _coalesce(today_qs.filter(payment_method="credit"), "total_amount")
    if today_revenue > 0:
        credit_pct = float(credit_sales / today_revenue * 100)
        if credit_pct < 20:
            badges.append({
                "name": "Cash Discipline",
                "icon": "bi-cash-stack",
                "color": "info",
                "description": f"Only {credit_pct:.0f}% credit sales today",
            })

    # Restock Genius: someone restocked this week (stock_quantity increased)
    # We approximate this by checking if any sales happened at all this week
    if week_qs.count() >= 5:
        badges.append({
            "name": "Active Seller",
            "icon": "bi-lightning-charge-fill",
            "color": "primary",
            "description": f"{week_qs.count()} sales this week",
        })

    return badges


def _generate_insights(
    business, today_profit, today_sales, low_stock_count, out_of_stock_count,
    month_profit, month_sales,
) -> list[str]:
    insights = []
    if low_stock_count:
        insights.append(f"{low_stock_count} product(s) are running low — restock soon to avoid lost sales")
    if out_of_stock_count:
        insights.append(f"{out_of_stock_count} product(s) are out of stock")
    if today_sales > 0 and today_profit > 0:
        margin = float(today_profit / today_sales * 100)
        if margin < 10:
            insights.append(f"Today's margin is low ({margin:.0f}%). Review pricing or reduce costs")
    if month_sales == 0:
        insights.append("No sales recorded this month yet. Start selling to see your performance.")
    return insights


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

@login_required
@require_business
def products_list(request):
    business = get_active_business(request)

    dept_id = request.GET.get("dept")
    cat_id = request.GET.get("cat")
    search = request.GET.get("q", "").strip()

    qs = RetailProduct.objects.filter(business=business, is_active=True).select_related(
        "department", "category"
    )

    if dept_id:
        qs = qs.filter(department_id=dept_id)
    if cat_id:
        qs = qs.filter(category_id=cat_id)
    if search:
        qs = qs.filter(
            Q(name__icontains=search)
            | Q(sku__icontains=search)
            | Q(brand__icontains=search)
        )

    low_stock_ids = set(
        RetailProduct.objects.filter(
            business=business, is_active=True, stock_quantity__gt=0,
            stock_quantity__lte=F("reorder_level"),
        ).values_list("id", flat=True)
    )

    departments = get_departments_for_business(business)
    selected_dept = None
    categories = []
    if dept_id:
        try:
            selected_dept = RetailDepartment.objects.get(pk=dept_id)
            categories = get_categories_for_department(selected_dept, business)
        except RetailDepartment.DoesNotExist:
            pass

    ctx = {
        "business": business,
        "active_tab": "products",
        "products": qs.order_by("department__sort_order", "category__sort_order", "name"),
        "departments": departments,
        "selected_dept": selected_dept,
        "categories": categories,
        "search": search,
        "low_stock_ids": low_stock_ids,
        "dept_id": dept_id,
        "cat_id": cat_id,
        "total_count": qs.count(),
    }
    return render(request, "verticals/mixed_retail/products_list.html", ctx)


@login_required
@require_business
def product_add(request):
    business = get_active_business(request)

    departments = get_departments_for_business(business)

    if request.method == "POST":
        try:
            name = request.POST.get("name", "").strip()
            if not name:
                messages.error(request, "Product name is required.")
                return redirect("mixed_retail:product_add")

            dept_id = request.POST.get("department_id") or None
            cat_id = request.POST.get("category_id") or None
            department = RetailDepartment.objects.get(pk=dept_id) if dept_id else None
            category = RetailCategory.objects.get(pk=cat_id) if cat_id else None

            product = RetailProduct.objects.create(
                business=business,
                name=name,
                department=department,
                category=category,
                sku=request.POST.get("sku", "").strip(),
                brand=request.POST.get("brand", "").strip(),
                model_number=request.POST.get("model_number", "").strip(),
                cost_price=Decimal(request.POST.get("cost_price", "0").replace(",", "") or "0"),
                selling_price=Decimal(request.POST.get("selling_price", "0").replace(",", "") or "0"),
                stock_quantity=Decimal(request.POST.get("stock_quantity", "0").replace(",", "") or "0"),
                reorder_level=Decimal(request.POST.get("reorder_level", "5").replace(",", "") or "5"),
                unit=request.POST.get("unit", "pcs"),
                # Optional attributes
                size=request.POST.get("size", "").strip(),
                color=request.POST.get("color", "").strip(),
                material=request.POST.get("material", "").strip(),
                condition=request.POST.get("condition", "new"),
                serial_number=request.POST.get("serial_number", "").strip(),
                imei=request.POST.get("imei", "").strip(),
                warranty_months=int(request.POST.get("warranty_months") or 0) or None,
                supplier_name=request.POST.get("supplier_name", "").strip(),
                notes=request.POST.get("notes", "").strip(),
                created_by=request.user,
            )
            messages.success(request, f"Product '{product.name}' added successfully.")
            return redirect("mixed_retail:products")
        except Exception as exc:
            messages.error(request, f"Error adding product: {exc}")

    # Pre-fill department if provided in URL
    preselect_dept_id = request.GET.get("dept")
    preselect_dept = None
    preselect_cats = []
    preselect_templates = []
    if preselect_dept_id:
        try:
            preselect_dept = RetailDepartment.objects.get(pk=preselect_dept_id)
            preselect_cats = get_categories_for_department(preselect_dept, business)
            preselect_templates = get_product_templates_for_department(preselect_dept)
        except RetailDepartment.DoesNotExist:
            pass

    # Departments with no enabled depts → show setup prompt
    no_departments = not departments

    ctx = {
        "business": business,
        "active_tab": "products",
        "departments": departments,
        "preselect_dept": preselect_dept,
        "preselect_cats": preselect_cats,
        "preselect_templates": preselect_templates,
        "unit_choices": RetailProduct.UNIT_CHOICES,
        "condition_choices": RetailProduct.CONDITION_CHOICES,
        "no_departments": no_departments,
    }
    return render(request, "verticals/mixed_retail/product_add.html", ctx)


@login_required
@require_business
def product_edit(request, product_id):
    business = get_active_business(request)
    product = get_object_or_404(RetailProduct, pk=product_id, business=business)

    departments = get_departments_for_business(business)
    categories = (
        get_categories_for_department(product.department, business)
        if product.department else []
    )

    if request.method == "POST":
        try:
            dept_id = request.POST.get("department_id") or None
            cat_id = request.POST.get("category_id") or None
            product.name = request.POST.get("name", product.name).strip()
            product.department = RetailDepartment.objects.get(pk=dept_id) if dept_id else None
            product.category = RetailCategory.objects.get(pk=cat_id) if cat_id else None
            product.sku = request.POST.get("sku", product.sku).strip()
            product.brand = request.POST.get("brand", product.brand).strip()
            product.cost_price = Decimal(request.POST.get("cost_price", str(product.cost_price)).replace(",", ""))
            product.selling_price = Decimal(request.POST.get("selling_price", str(product.selling_price)).replace(",", ""))
            product.stock_quantity = Decimal(request.POST.get("stock_quantity", str(product.stock_quantity)).replace(",", ""))
            product.reorder_level = Decimal(request.POST.get("reorder_level", str(product.reorder_level)).replace(",", ""))
            product.unit = request.POST.get("unit", product.unit)
            product.size = request.POST.get("size", product.size).strip()
            product.color = request.POST.get("color", product.color).strip()
            product.material = request.POST.get("material", product.material).strip()
            product.condition = request.POST.get("condition", product.condition)
            product.serial_number = request.POST.get("serial_number", product.serial_number).strip()
            product.imei = request.POST.get("imei", product.imei).strip()
            wm = request.POST.get("warranty_months", "")
            product.warranty_months = int(wm) if wm.strip() else None
            product.supplier_name = request.POST.get("supplier_name", product.supplier_name).strip()
            product.notes = request.POST.get("notes", product.notes).strip()
            product.save()
            messages.success(request, f"'{product.name}' updated.")
            return redirect("mixed_retail:products")
        except Exception as exc:
            messages.error(request, f"Error: {exc}")

    ctx = {
        "business": business,
        "product": product,
        "active_tab": "products",
        "departments": departments,
        "categories": categories,
        "unit_choices": RetailProduct.UNIT_CHOICES,
        "condition_choices": RetailProduct.CONDITION_CHOICES,
    }
    return render(request, "verticals/mixed_retail/product_edit.html", ctx)


# ---------------------------------------------------------------------------
# Stock In
# ---------------------------------------------------------------------------

@login_required
@require_business
def stock_in(request):
    """Record a stock-in (restock) for a product."""
    business = get_active_business(request)

    if request.method == "POST":
        try:
            product_id = request.POST.get("product_id")
            product = get_object_or_404(RetailProduct, pk=product_id, business=business)
            qty = Decimal(request.POST.get("quantity", "0").replace(",", ""))
            new_cost = request.POST.get("new_cost_price", "").replace(",", "").strip()
            if qty <= 0:
                messages.error(request, "Quantity must be greater than 0.")
                return redirect("mixed_retail:stock_in")
            product.stock_quantity += qty
            if new_cost:
                product.cost_price = Decimal(new_cost)
            product.save(update_fields=["stock_quantity", "cost_price"])
            messages.success(request, f"Restocked {qty} × {product.name}. New stock: {product.stock_quantity}")
            return redirect("mixed_retail:stock_in")
        except Exception as exc:
            messages.error(request, f"Error: {exc}")

    products = RetailProduct.objects.filter(
        business=business, is_active=True
    ).select_related("department", "category").order_by("department__sort_order", "name")

    ctx = {
        "business": business,
        "active_tab": "stock_in",
        "products": products,
    }
    return render(request, "verticals/mixed_retail/stock_in.html", ctx)


# ---------------------------------------------------------------------------
# Sell
# ---------------------------------------------------------------------------

@login_required
@require_business
def sell(request):
    """Quick sales entry page."""
    business = get_active_business(request)

    if request.method == "POST":
        try:
            with db_transaction.atomic():
                # Support single item or basket (multiple items same receipt)
                receipt_ref = request.POST.get("receipt_ref") or str(uuid.uuid4())[:8].upper()
                product_ids = request.POST.getlist("product_id")
                quantities = request.POST.getlist("quantity")
                unit_prices = request.POST.getlist("unit_price")
                payment_method = request.POST.get("payment_method", "cash")
                customer_name = request.POST.get("customer_name", "").strip()
                customer_phone = request.POST.get("customer_phone", "").strip()
                amount_paid_str = request.POST.get("amount_paid", "").replace(",", "").strip()
                credit_due_date_str = request.POST.get("credit_due_date", "").strip()
                notes = request.POST.get("notes", "").strip()

                if not product_ids:
                    messages.error(request, "Please add at least one product.")
                    return redirect("mixed_retail:sell")

                total_created = 0
                for pid, qty_str, price_str in zip(product_ids, quantities, unit_prices):
                    product = get_object_or_404(RetailProduct, pk=pid, business=business)
                    qty = Decimal(qty_str.replace(",", "") or "1")
                    price = Decimal(price_str.replace(",", "") or str(product.selling_price))

                    if qty <= 0:
                        continue

                    # Deduct stock
                    product.stock_quantity = max(Decimal("0"), product.stock_quantity - qty)
                    product.save(update_fields=["stock_quantity"])

                    amount_paid = None
                    if amount_paid_str and payment_method == "credit":
                        amount_paid = Decimal(amount_paid_str)

                    credit_due_date = None
                    if credit_due_date_str:
                        from datetime import date as dt_date
                        try:
                            credit_due_date = dt_date.fromisoformat(credit_due_date_str)
                        except ValueError:
                            pass

                    RetailSale.objects.create(
                        business=business,
                        product=product,
                        quantity=qty,
                        unit_price=price,
                        cost_price_snapshot=product.cost_price,
                        payment_method=payment_method,
                        receipt_ref=receipt_ref,
                        customer_name=customer_name,
                        customer_phone=customer_phone,
                        amount_paid=amount_paid,
                        credit_due_date=credit_due_date,
                        notes=notes,
                        created_by=request.user,
                    )
                    total_created += 1

                messages.success(
                    request,
                    f"Sale recorded — {total_created} item(s). Receipt: {receipt_ref}"
                )
                return redirect("mixed_retail:sell")

        except Exception as exc:
            messages.error(request, f"Error recording sale: {exc}")

    products = RetailProduct.objects.filter(
        business=business, is_active=True, stock_quantity__gt=0
    ).select_related("department", "category").order_by("department__sort_order", "name")

    departments = get_departments_for_business(business)

    total_products = RetailProduct.objects.filter(business=business, is_active=True).count()

    ctx = {
        "business": business,
        "active_tab": "sell",
        "products": products,
        "departments": departments,
        "payment_methods": RetailPaymentMethod.choices,
        "today": timezone.localdate(),
        "has_any_products": total_products > 0,
        "has_stocked_products": products.count() > 0,
    }
    return render(request, "verticals/mixed_retail/sell.html", ctx)


# ---------------------------------------------------------------------------
# Sales History
# ---------------------------------------------------------------------------

@login_required
@require_business
def sales_history(request):
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

    qs = RetailSale.objects.filter(
        business=business,
        is_rolled_back=False,
        sold_at__date__gte=date_from,
        sold_at__date__lte=date_to,
    ).select_related("product", "product__department", "product__category", "created_by")

    total_revenue = _coalesce(qs, "total_amount")
    total_profit = _coalesce(qs, "profit")

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
    return render(request, "verticals/mixed_retail/sales_history.html", ctx)


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------

@login_required
@require_business
def expenses(request):
    business = get_active_business(request)

    if request.method == "POST":
        try:
            expense_date_str = request.POST.get("expense_date", "").strip()
            RetailExpense.objects.create(
                business=business,
                description=request.POST.get("description", "").strip(),
                amount=Decimal(request.POST.get("amount", "0").replace(",", "")),
                category=request.POST.get("category", "other"),
                expense_date=expense_date_str or timezone.localdate(),
                notes=request.POST.get("notes", "").strip(),
                created_by=request.user,
            )
            messages.success(request, "Expense recorded.")
            return redirect("mixed_retail:expenses")
        except Exception as exc:
            messages.error(request, f"Error: {exc}")

    expense_qs = RetailExpense.objects.filter(business=business)
    total_expenses = _coalesce(expense_qs, "amount")
    expense_list = expense_qs.order_by("-expense_date")[:100]

    ctx = {
        "business": business,
        "active_tab": "expenses",
        "expenses": expense_list,
        "total_expenses": total_expenses,
        "category_choices": RetailExpense.CATEGORY_CHOICES,
        "today": timezone.localdate(),
    }
    return render(request, "verticals/mixed_retail/expenses.html", ctx)


# ---------------------------------------------------------------------------
# API: Product lookup for sell page
# ---------------------------------------------------------------------------

@login_required
@require_business
def api_product_lookup(request):
    business = get_active_business(request)
    q = request.GET.get("q", "").strip()

    if not q or len(q) < 2:
        return JsonResponse({"results": []})

    qs = RetailProduct.objects.filter(
        business=business,
        is_active=True,
    ).filter(
        Q(name__icontains=q)
        | Q(sku__icontains=q)
        | Q(brand__icontains=q)
    ).select_related("department", "category")[:20]

    results = [
        {
            "id": p.id,
            "name": p.name,
            "sku": p.sku,
            "brand": p.brand,
            "department": p.department.name if p.department else "",
            "category": p.category.name if p.category else "",
            "selling_price": str(p.selling_price),
            "cost_price": str(p.cost_price),
            "stock_quantity": str(p.stock_quantity),
            "unit": p.unit,
            "is_low_stock": p.is_low_stock,
            "is_out_of_stock": p.is_out_of_stock,
        }
        for p in qs
    ]
    return JsonResponse({"results": results})


# ---------------------------------------------------------------------------
# API: Categories for a department
# ---------------------------------------------------------------------------

@login_required
@require_business
def api_categories(request):
    business = get_active_business(request)
    dept_id = request.GET.get("dept_id")

    if not dept_id:
        return JsonResponse({"categories": []})

    from django.db.models import Q as DQ
    cats = RetailCategory.objects.filter(
        department_id=dept_id,
        is_enabled=True,
    ).filter(DQ(business=None) | DQ(business=business)).order_by("sort_order", "name")

    return JsonResponse({
        "categories": [
            {"id": c.id, "name": c.name}
            for c in cats
        ]
    })


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@login_required
@require_business
def reports(request):
    """Mixed Retail reports and analytics overview."""
    business = get_active_business(request)
    today = timezone.localdate()
    month_start = today.replace(day=1)

    live_qs = RetailSale.objects.filter(business=business, is_rolled_back=False)

    # Date range filter
    date_from_str = request.GET.get("from", str(today - timedelta(days=30)))
    date_to_str = request.GET.get("to", str(today))
    try:
        from datetime import date as dt_date
        date_from = dt_date.fromisoformat(date_from_str)
        date_to = dt_date.fromisoformat(date_to_str)
    except ValueError:
        date_from = today - timedelta(days=30)
        date_to = today

    range_qs = live_qs.filter(sold_at__date__gte=date_from, sold_at__date__lte=date_to)
    month_qs = live_qs.filter(sold_at__date__gte=month_start)

    total_revenue = _coalesce(range_qs, "total_amount")
    total_profit = _coalesce(range_qs, "profit")
    total_count = range_qs.count()
    margin_pct = float(total_profit / total_revenue * 100) if total_revenue > 0 else 0.0

    month_revenue = _coalesce(month_qs, "total_amount")
    month_profit_val = _coalesce(month_qs, "profit")

    # Top products in range
    top_products = (
        range_qs.values("product__name", "product__department__name")
        .annotate(
            revenue=Coalesce(Sum("total_amount"), Value(0), output_field=_DEC),
            qty=Coalesce(Sum("quantity"), Value(0), output_field=_DEC),
            profit=Coalesce(Sum("profit"), Value(0), output_field=_DEC),
        )
        .order_by("-revenue")[:10]
    )

    # Department breakdown
    dept_breakdown = (
        range_qs.values("product__department__name")
        .annotate(
            revenue=Coalesce(Sum("total_amount"), Value(0), output_field=_DEC),
            profit=Coalesce(Sum("profit"), Value(0), output_field=_DEC),
            count=Count("id"),
        )
        .order_by("-revenue")
    )

    # Daily sales trend for range
    daily_trend = (
        range_qs
        .annotate(day=TruncDate("sold_at"))
        .values("day")
        .annotate(
            revenue=Coalesce(Sum("total_amount"), Value(0), output_field=_DEC),
            profit=Coalesce(Sum("profit"), Value(0), output_field=_DEC),
        )
        .order_by("day")
    )

    # Expenses in range
    expense_qs = RetailExpense.objects.filter(
        business=business,
        expense_date__gte=date_from,
        expense_date__lte=date_to,
    )
    total_expenses = _coalesce(expense_qs, "amount")
    net_profit = total_profit - total_expenses

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
        "month_profit": month_profit_val,
        "top_products": list(top_products),
        "dept_breakdown": list(dept_breakdown),
        "daily_trend": list(daily_trend),
        "total_expenses": total_expenses,
        "net_profit": net_profit,
    }
    return render(request, "verticals/mixed_retail/reports.html", ctx)


# ---------------------------------------------------------------------------
# Departments management
# ---------------------------------------------------------------------------

@login_required
@require_business
def departments(request):
    """View/manage departments for this business."""
    from django.utils.text import slugify
    from inventory.mixed_retail_seed import (
        ensure_mixed_retail_defaults, get_all_departments_with_status,
        DEFAULT_ENABLED_DEPT_SLUGS,
    )

    business = get_active_business(request)

    # Ensure enrollment records exist (no-op if already set up)
    try:
        ensure_mixed_retail_defaults(business)
    except Exception:
        pass

    if request.method == "POST":
        action = request.POST.get("action", "add")

        if action == "add":
            try:
                name = request.POST.get("name", "").strip()
                if not name:
                    messages.error(request, "Department name is required.")
                else:
                    RetailDepartment.objects.create(
                        business=business,
                        name=name,
                        slug=slugify(name),
                        icon=request.POST.get("icon", "bi-bag"),
                        description=request.POST.get("description", "").strip(),
                        is_seeded=False,
                        is_enabled=True,
                    )
                    messages.success(request, f"Department '{name}' added.")
            except Exception as exc:
                messages.error(request, f"Error: {exc}")

        elif action == "toggle":
            dept_id = request.POST.get("dept_id")
            try:
                dept = RetailDepartment.objects.get(pk=dept_id)
                if dept.business is None and dept.is_seeded:
                    # Per-business toggle via enrollment record
                    enrollment, _ = RetailBusinessDepartment.objects.get_or_create(
                        business=business, department=dept,
                        defaults={"is_enabled": False},
                    )
                    enrollment.is_enabled = not enrollment.is_enabled
                    enrollment.save(update_fields=["is_enabled", "updated_at"])
                    state = "enabled" if enrollment.is_enabled else "disabled"
                else:
                    # Custom dept — toggle directly
                    if dept.business != business:
                        raise RetailDepartment.DoesNotExist
                    dept.is_enabled = not dept.is_enabled
                    dept.save(update_fields=["is_enabled"])
                    state = "enabled" if dept.is_enabled else "disabled"
                messages.success(request, f"'{dept.name}' {state}.")
            except RetailDepartment.DoesNotExist:
                messages.error(request, "Department not found.")

        elif action == "enable_defaults":
            # Bulk-enable the default common departments
            from inventory.models_mixed_retail import RetailDepartment as RD
            enabled = 0
            for slug in DEFAULT_ENABLED_DEPT_SLUGS:
                dept = RD.objects.filter(business=None, slug=slug).first()
                if dept:
                    enrollment, _ = RetailBusinessDepartment.objects.get_or_create(
                        business=business, department=dept,
                        defaults={"is_enabled": True},
                    )
                    if not enrollment.is_enabled:
                        enrollment.is_enabled = True
                        enrollment.save(update_fields=["is_enabled", "updated_at"])
                    enabled += 1
            messages.success(request, f"{enabled} common departments enabled. Add more as needed.")

        return redirect("mixed_retail:departments")

    # Build context
    dept_list = get_all_departments_with_status(business)
    enabled_count = sum(1 for d in dept_list if d["is_enabled"])
    seeded_count = sum(1 for d in dept_list if not d["is_custom"])
    custom_count = sum(1 for d in dept_list if d["is_custom"])
    total_templates = sum(d["template_count"] for d in dept_list if not d["is_custom"])

    icons_list = [
        "bi-bag", "bi-shop", "bi-cart", "bi-box-seam", "bi-tools",
        "bi-phone", "bi-truck", "bi-house-gear", "bi-scissors", "bi-cup-hot",
        "bi-book", "bi-bicycle", "bi-palette", "bi-camera", "bi-music-note",
        "bi-wrench", "bi-globe", "bi-heart-pulse", "bi-tree", "bi-stars",
        "bi-car-front", "bi-bricks", "bi-boot", "bi-handbag", "bi-capsule",
        "bi-balloon-heart", "bi-flower2", "bi-trophy", "bi-cash-coin", "bi-three-dots",
    ]

    ctx = {
        "business": business,
        "active_tab": "departments",
        "dept_list": dept_list,
        "enabled_count": enabled_count,
        "seeded_count": seeded_count,
        "custom_count": custom_count,
        "total_templates": total_templates,
        "icons_list": icons_list,
    }
    return render(request, "verticals/mixed_retail/departments.html", ctx)


# ---------------------------------------------------------------------------
# API: Product templates for a department
# ---------------------------------------------------------------------------

@login_required
@require_business
def api_product_templates(request):
    """Return product templates for a department (for Add Product page)."""
    business = get_active_business(request)
    dept_id = request.GET.get("dept_id")

    if not dept_id:
        return JsonResponse({"templates": []})

    try:
        dept = RetailDepartment.objects.get(pk=dept_id)
    except RetailDepartment.DoesNotExist:
        return JsonResponse({"templates": []})

    templates = RetailProductTemplate.objects.filter(
        department=dept, is_active=True
    ).order_by("sort_order", "name")

    return JsonResponse({
        "templates": [
            {"id": t.id, "name": t.name, "unit": t.suggested_unit}
            for t in templates
        ]
    })

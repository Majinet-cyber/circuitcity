# inventory/views_clothing.py
"""
Views for clothing store operations: product management, sales, dashboard.
"""
from __future__ import annotations

from decimal import Decimal
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum, Count, Q, F
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from inventory.authz import require_business_kind, manager_required
from inventory.business_kinds import BusinessKind
from inventory.helpers import get_active_business
from inventory.models import MerchProduct
from inventory.models_verticals import ClothingSale, ClothingProductLog, ClothingProductAction
from tenants.utils import require_business


# ==============================================================================
# CLOTHING PRODUCT MANAGEMENT (Manager only)
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
@manager_required
@require_POST
def archive_product(request, product_id):
    """Archive a clothing product (soft delete)"""
    business = get_active_business(request)
    product = get_object_or_404(MerchProduct, pk=product_id, business=business, kind=BusinessKind.CLOTHING)

    if product.is_archived:
        messages.warning(request, f"'{product.name}' is already archived.")
        return redirect("inventory:clothing_stock_list")

    with transaction.atomic():
        product.is_archived = True
        product.is_active = False
        product.archived_at = timezone.now()
        product.archived_by = request.user
        product.save(update_fields=["is_archived", "is_active", "archived_at", "archived_by"])

        # Log the action
        ClothingProductLog.objects.create(
            product=product,
            action=ClothingProductAction.ARCHIVED,
            changes={"archived_at": str(timezone.now())},
            performed_by=request.user,
        )

    messages.success(request, f"Product '{product.name}' archived.")
    return redirect("inventory:clothing_stock_list")


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
@manager_required
@require_POST
def restore_product(request, product_id):
    """Restore an archived product"""
    business = get_active_business(request)
    product = get_object_or_404(MerchProduct, pk=product_id, business=business, kind=BusinessKind.CLOTHING)

    if not product.is_archived:
        messages.warning(request, f"'{product.name}' is not archived.")
        return redirect("inventory:clothing_stock_list")

    with transaction.atomic():
        product.is_archived = False
        product.is_active = True
        product.archived_at = None
        product.archived_by = None
        product.save(update_fields=["is_archived", "is_active", "archived_at", "archived_by"])

        # Log the action
        ClothingProductLog.objects.create(
            product=product,
            action=ClothingProductAction.RESTORED,
            changes={"restored_at": str(timezone.now())},
            performed_by=request.user,
        )

    messages.success(request, f"Product '{product.name}' restored.")
    return redirect("inventory:clothing_stock_list")


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def stock_list(request):
    """List clothing stock with archive filter"""
    business = get_active_business(request)

    # Filter: active, archived, or all
    filter_type = request.GET.get("filter", "active")
    products = MerchProduct.objects.filter(business=business, kind=BusinessKind.CLOTHING)

    if filter_type == "active":
        products = products.filter(is_archived=False, is_active=True)
    elif filter_type == "archived":
        products = products.filter(is_archived=True)
    # else: show all

    products = products.order_by("-id")

    return render(
        request,
        "inventory/clothing/stock_list.html",
        {
            "products": products,
            "business": business,
            "filter_type": filter_type,
        },
    )


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
@manager_required
def archived_products(request):
    """View all archived products"""
    business = get_active_business(request)
    products = (
        MerchProduct.objects.filter(business=business, kind=BusinessKind.CLOTHING, is_archived=True)
        .select_related("archived_by")
        .order_by("-archived_at")
    )

    return render(
        request,
        "inventory/clothing/archived_products.html",
        {
            "products": products,
            "business": business,
        },
    )


# ==============================================================================
# CLOTHING SALES
# ==============================================================================


class ClothingSellForm(forms.Form):
    """Form for selling clothing"""

    product = forms.ModelChoiceField(
        queryset=MerchProduct.objects.none(), widget=forms.Select(attrs={"class": "form-control"})
    )
    quantity = forms.IntegerField(min_value=1, initial=1, widget=forms.NumberInput(attrs={"class": "form-control"}))
    unit_price = forms.DecimalField(
        max_digits=10, decimal_places=2, widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"})
    )
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}))

    def __init__(self, business=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if business:
            self.fields["product"].queryset = MerchProduct.objects.filter(
                business=business, kind=BusinessKind.CLOTHING, is_active=True, is_archived=False
            ).order_by("name")


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def sell_clothing(request):
    """Record a clothing sale - STRICT STOCK VALIDATION"""
    business = get_active_business(request)

    if request.method == "POST":
        form = ClothingSellForm(business, request.POST)
        if form.is_valid():
            data = form.cleaned_data
            product = data["product"]
            quantity = data["quantity"]

            # CRITICAL: Enforce stock validation - NEVER allow selling more than available
            current_stock = product.quantity_in_stock or 0
            if current_stock < quantity:
                messages.error(
                    request,
                    f"❌ Insufficient stock! Available: {current_stock}, Requested: {quantity}. Cannot complete sale.",
                )
                return redirect("inventory:clothing_sales_list")

            # Calculate total
            total = Decimal(quantity) * data["unit_price"]

            with transaction.atomic():
                # Reduce stock (guaranteed to not go negative due to validation above)
                product.quantity_in_stock = current_stock - quantity
                product.save(update_fields=["quantity_in_stock"])

                # Create sale
                sale = ClothingSale.objects.create(
                    business=business,
                    product=product,
                    quantity=quantity,
                    unit_price=data["unit_price"],
                    total_price=total,
                    sold_by=request.user,
                    notes=data.get("notes", ""),
                )

                # Log the sale
                ClothingProductLog.objects.create(
                    product=product,
                    action=ClothingProductAction.SOLD,
                    changes={
                        "quantity_sold": quantity,
                        "stock_after_sale": product.quantity_in_stock,
                        "stock_validated": True,
                    },
                    performed_by=request.user,
                )

                messages.success(
                    request,
                    f"✅ Sale recorded: {quantity} × {product.name} (Stock remaining: {product.quantity_in_stock})",
                )

            return redirect("inventory:clothing_sales_list")
    else:
        form = ClothingSellForm(business)

    recent_sales = (
        ClothingSale.objects.filter(business=business).select_related("product", "sold_by").order_by("-sold_at")[:10]
    )

    return render(
        request,
        "inventory/clothing/sell.html",
        {
            "form": form,
            "recent_sales": recent_sales,
            "business": business,
        },
    )


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def sales_list(request):
    """List all clothing sales"""
    business = get_active_business(request)
    sales = ClothingSale.objects.filter(business=business).select_related("product", "sold_by").order_by("-sold_at")

    return render(
        request,
        "inventory/clothing/sales_list.html",
        {
            "sales": sales,
            "business": business,
        },
    )


# ==============================================================================
# CLOTHING DASHBOARD (Polished Business View)
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def clothing_dashboard(request):
    """Polished business dashboard for clothing store"""
    business = get_active_business(request)
    now = timezone.now()

    # Active products
    products = MerchProduct.objects.filter(
        business=business, kind=BusinessKind.CLOTHING, is_active=True, is_archived=False
    )

    # Sales metrics
    all_sales = ClothingSale.objects.filter(business=business)
    today_sales = all_sales.filter(sold_at__date=now.date())
    last_7_days_sales = all_sales.filter(sold_at__gte=now - timedelta(days=7))
    last_30_days_sales = all_sales.filter(sold_at__gte=now - timedelta(days=30))

    # Calculate totals
    total_stock_value = products.aggregate(total=Sum(F("price_per_bottle") or Decimal("0.00")))["total"] or Decimal(
        "0.00"
    )

    total_items_in_stock = products.count()

    today_sales_total = today_sales.aggregate(Sum("total_price"))["total_price__sum"] or Decimal("0.00")
    today_sales_count = today_sales.count()

    last_7_days_total = last_7_days_sales.aggregate(Sum("total_price"))["total_price__sum"] or Decimal("0.00")
    last_7_days_count = last_7_days_sales.count()

    last_30_days_total = last_30_days_sales.aggregate(Sum("total_price"))["total_price__sum"] or Decimal("0.00")
    last_30_days_count = last_30_days_sales.count()

    # Best selling items (top 5 by quantity sold)
    best_sellers = (
        all_sales.values("product__name")
        .annotate(total_qty=Sum("quantity"), total_amount=Sum("total_price"))
        .order_by("-total_qty")[:5]
    )

    # Low stock alerts (products with quantity < threshold, if quantity field exists)
    low_stock_threshold = 5
    low_stock_products = []
    # Note: MerchProduct doesn't have a direct quantity field in this implementation
    # You may need to add this field or track it via MerchUnitPrice

    # Recent sales for quick view
    recent_sales = all_sales.select_related("product", "sold_by").order_by("-sold_at")[:10]

    # Sales by day (last 7 days) for chart
    sales_by_day = []
    for i in range(6, -1, -1):
        day = now.date() - timedelta(days=i)
        day_sales = all_sales.filter(sold_at__date=day)
        day_revenue = day_sales.aggregate(Sum("total_price"))["total_price__sum"] or Decimal("0.00")
        day_cost = day_sales.aggregate(Sum("total_cost"))["total_cost__sum"] or Decimal("0.00")
        day_profit = day_revenue - day_cost
        day_count = day_sales.count()
        sales_by_day.append(
            {
                "date": day.strftime("%Y-%m-%d"),
                "date_short": day.strftime("%b %d"),
                "revenue": float(day_revenue),
                "profit": float(day_profit),
                "count": day_count,
            }
        )

    return render(
        request,
        "inventory/clothing/dashboard.html",
        {
            "business": business,
            # Stock metrics
            "total_stock_value": total_stock_value,
            "total_items_in_stock": total_items_in_stock,
            # Sales metrics
            "today_sales_total": today_sales_total,
            "today_sales_count": today_sales_count,
            "last_7_days_total": last_7_days_total,
            "last_7_days_count": last_7_days_count,
            "last_30_days_total": last_30_days_total,
            "last_30_days_count": last_30_days_count,
            # Best sellers
            "best_sellers": best_sellers,
            # Low stock (placeholder)
            "low_stock_products": low_stock_products,
            # Recent activity
            "recent_sales": recent_sales,
            # Chart data
            "sales_by_day": sales_by_day,
        },
    )


# ==============================================================================
# PRODUCT LOGS (Audit Trail)
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
@manager_required
def product_logs(request, product_id):
    """View audit logs for a specific product"""
    business = get_active_business(request)
    product = get_object_or_404(MerchProduct, pk=product_id, business=business, kind=BusinessKind.CLOTHING)
    logs = ClothingProductLog.objects.filter(product=product).select_related("performed_by").order_by("-created_at")

    return render(
        request,
        "inventory/clothing/product_logs.html",
        {
            "product": product,
            "logs": logs,
            "business": business,
        },
    )

# inventory/verticals/clothing_v2.py
"""
CLOTHING VERTICAL V2 - Premium "WOW" Experience
Implements:
- Gamified dashboard with KPIs, streaks, badges
- 2-step Quick Add (category tiles + minimal form)
- Fast Stock In / Sell (search + top items)
- Smart filters + summaries
- Auto-generated labels/QR with printing
- Barcode optional everywhere
- Strict multi-tenant + vertical gating
"""
from __future__ import annotations

from decimal import Decimal
from datetime import timedelta
from typing import Dict, Any

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum, Count, Q, F
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.core.paginator import Paginator

from tenants.utils import require_business
from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct
from inventory.models_verticals import (
    ClothingSale,
    ClothingVariant,
    ClothingProductLog,
    ClothingProductAction,
    PaymentMethod,
)
from inventory.clothing_config import (
    CLOTHING_CATEGORIES,
    get_category_display,
    get_category_icon,
    get_sizes_for_category,
    CLOTHING_COLORS,
    BADGES,
    check_badges_earned,
    DEFAULT_DAILY_SALES_TARGET,
    DEFAULT_DAILY_REVENUE_TARGET,
    get_stock_status,
    get_price_tier,
    PRICE_TIER_LABELS,
)
from inventory.services.clothing_service import (
    stock_in_clothing,
    sell_clothing,
    get_top_sellers,
    get_slow_movers,
    get_low_stock_products,
)
from inventory.verticals import base


# ============================================================================
# GAMIFIED DASHBOARD
# ============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def dashboard_v2(request):
    """
    Gamified clothing dashboard with KPIs, streaks, and badges.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")

    # Date range parsing
    date_range_ctx = base.parse_date_range_from_request(request)
    range_param = date_range_ctx["active_range"]
    start_date = date_range_ctx["start_date"]
    end_date = date_range_ctx["end_date"]

    # Today's metrics (for gamification)
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_sales = ClothingSale.objects.filter(
        business=business,
        sold_at__gte=today_start,
    )

    today_stats = today_sales.aggregate(
        sales_count=Count("id"),
        items_sold=Sum("quantity"),
        revenue=Sum("total_price"),
        profit=Sum(F("total_price") - F("total_cost")),
    )

    today_sales_count = today_stats["sales_count"] or 0
    today_items_sold = today_stats["items_sold"] or 0
    today_revenue = today_stats["revenue"] or Decimal("0.00")
    today_profit = today_stats["profit"] or Decimal("0.00")

    # Calculate sales streak (consecutive days with sales)
    streak_days = _calculate_sales_streak(business)

    # Check badges earned
    badges_earned = check_badges_earned(
        sales_count=today_items_sold,
        revenue=today_revenue,
        profit=today_profit,
        streak_days=streak_days,
    )

    badges_display = [BADGES[key] for key in badges_earned]

    # Daily targets progress
    sales_target_pct = min(100, int((today_items_sold / DEFAULT_DAILY_SALES_TARGET) * 100))
    revenue_target_pct = min(100, int((today_revenue / DEFAULT_DAILY_REVENUE_TARGET) * 100))

    # Period metrics (for selected range)
    period_sales = ClothingSale.objects.filter(
        business=business,
        sold_at__gte=start_date,
        sold_at__lt=end_date,
    )

    period_stats = period_sales.aggregate(
        sales_count=Count("id"),
        items_sold=Sum("quantity"),
        revenue=Sum("total_price"),
        cost=Sum("total_cost"),
    )

    period_revenue = period_stats["revenue"] or Decimal("0.00")
    period_cost = period_stats["cost"] or Decimal("0.00")
    period_profit = period_revenue - period_cost
    period_items_sold = period_stats["items_sold"] or 0

    # Inventory metrics
    total_products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.CLOTHING,
        is_active=True,
        is_archived=False,
    ).count()

    low_stock_count = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.CLOTHING,
        is_active=True,
        is_archived=False,
        quantity_in_stock__gt=0,
        quantity_in_stock__lte=3,
    ).count()

    out_of_stock_count = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.CLOTHING,
        is_active=True,
        is_archived=False,
        quantity_in_stock=0,
    ).count()

    # Top sellers (7 days)
    top_sellers = get_top_sellers(business, location=location, days=7, limit=5)

    # Slow movers (30 days)
    slow_movers = get_slow_movers(business, location=location, days=30, limit=5)

    ctx.update(
        {
            # Today's gamification
            "today_sales_count": today_sales_count,
            "today_items_sold": today_items_sold,
            "today_revenue": today_revenue,
            "today_profit": today_profit,
            "streak_days": streak_days,
            "badges_earned": badges_display,
            "sales_target_pct": sales_target_pct,
            "revenue_target_pct": revenue_target_pct,
            "daily_sales_target": DEFAULT_DAILY_SALES_TARGET,
            "daily_revenue_target": DEFAULT_DAILY_REVENUE_TARGET,
            # Period metrics
            "period_revenue": period_revenue,
            "period_cost": period_cost,
            "period_profit": period_profit,
            "period_items_sold": period_items_sold,
            "active_range": range_param,
            # Inventory
            "total_products": total_products,
            "low_stock_count": low_stock_count,
            "out_of_stock_count": out_of_stock_count,
            # Smart lists
            "top_sellers": top_sellers,
            "slow_movers": slow_movers,
        }
    )

    return render(request, "verticals/clothing/dashboard_v2.html", ctx)


def _calculate_sales_streak(business) -> int:
    """Calculate consecutive days with sales (going backwards from today)"""
    today = timezone.now().date()
    streak = 0

    for i in range(30):  # Check last 30 days max
        check_date = today - timedelta(days=i)
        has_sales = ClothingSale.objects.filter(
            business=business,
            sold_at__date=check_date,
        ).exists()

        if has_sales:
            streak += 1
        else:
            break

    return streak


# ============================================================================
# 2-STEP QUICK ADD
# ============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def quick_add_step1(request):
    """
    Step 1: Category selection with big tiles.
    """
    ctx = base.base_context(request)

    # Group categories by item type for better UX
    categories_by_type = {}
    for cat_value, cat_display, cat_icon, item_type in CLOTHING_CATEGORIES:
        if item_type not in categories_by_type:
            categories_by_type[item_type] = []
        categories_by_type[item_type].append(
            {
                "value": cat_value,
                "display": cat_display,
                "icon": cat_icon,
            }
        )

    ctx.update(
        {
            "categories_by_type": categories_by_type,
            "page_title": "Add Product - Choose Category",
        }
    )

    return render(request, "verticals/clothing/quick_add_step1.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def quick_add_step2(request, category):
    """
    Step 2: Gamified card-based product creation.
    Now uses clickable cards instead of dropdowns for premium UX.
    """
    import json
    from django import forms
    from inventory.clothing_config import (
        CLOTHING_BRANDS,
        get_subtypes_for_category,
    )

    ctx = base.base_context(request)
    business = ctx.get("business")

    # Get category display
    category_display = get_category_display(category)
    category_icon = get_category_icon(category)

    # Get appropriate sizes for this category
    size_choices = get_sizes_for_category(category)
    
    # Get subtypes for this category
    subtypes = get_subtypes_for_category(category)

    # Build form dynamically (for validation only - UI uses cards)
    class QuickAddForm(forms.Form):
        brand = forms.CharField(
            max_length=100,
            required=False,
            widget=forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g., Nike, Balenciaga (optional)",
                }
            ),
            label="Brand",
        )
        name = forms.CharField(
            max_length=160,
            required=True,
            widget=forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": f"e.g., {category_display} name",
                }
            ),
            label="Product Name",
        )

        if size_choices:
            size = forms.ChoiceField(
                choices=[("", "-- No size --")] + [(s, s) for s in size_choices],
                required=False,
                widget=forms.Select(attrs={"class": "form-control"}),
                label="Size (optional)",
            )

        color = forms.ChoiceField(
            choices=[("", "-- No color --")] + [(c, c) for c in CLOTHING_COLORS],
            required=False,
            widget=forms.Select(attrs={"class": "form-control"}),
            label="Color (optional)",
        )

        selling_price = forms.DecimalField(
            max_digits=10,
            decimal_places=2,
            min_value=Decimal("0.01"),
            required=True,
            widget=forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "placeholder": "0.00",
                }
            ),
            label="Selling Price",
        )

        cost_price = forms.DecimalField(
            max_digits=10,
            decimal_places=2,
            min_value=Decimal("0"),
            required=True,
            widget=forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "placeholder": "0.00",
                }
            ),
            label="Cost Price",
        )

        quantity = forms.IntegerField(
            min_value=0,
            initial=0,
            required=False,
            widget=forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "0 (stock now, optional)",
                }
            ),
            label="Stock Now (optional)",
        )

        barcode = forms.CharField(
            max_length=100,
            required=False,
            widget=forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Barcode (optional)",
                }
            ),
            label="Barcode (optional)",
        )

    if request.method == "POST":
        form = QuickAddForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data

            try:
                result = stock_in_clothing(
                    business=business,
                    user=request.user,
                    category=category,
                    name=data["name"],
                    quantity=data.get("quantity") or 0,
                    cost_price=data["cost_price"],
                    selling_price=data["selling_price"],
                    brand=data.get("brand") or None,
                    size=data.get("size") or None,
                    color=data.get("color") or None,
                    barcode=data.get("barcode") or None,
                    location=ctx.get("location"),
                )

                messages.success(request, result["message"])

                # Show action buttons
                request.session["last_added_product_id"] = result["product"].id

                return redirect("verticals:clothing_quick_add_success")

            except Exception as e:
                messages.error(request, f"Error: {str(e)}")
    else:
        form = QuickAddForm()

    ctx.update(
        {
            "form": form,
            "category": category,
            "category_display": category_display,
            "category_icon": category_icon,
            "page_title": f"Add {category_display}",
            # Gamified UI context
            "brands": CLOTHING_BRANDS,
            "subtypes": subtypes,
            "sizes": size_choices,
            "colors": CLOTHING_COLORS,
            # JSON-serialized for JavaScript
            "brands_json": json.dumps(CLOTHING_BRANDS),
            "subtypes_json": json.dumps(subtypes),
            "sizes_json": json.dumps(size_choices),
        }
    )

    return render(request, "verticals/clothing/quick_add_step2_gamified.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def quick_add_success(request):
    """
    Success page with action buttons: Add Another / Stock In / Sell / Print Tag
    """
    ctx = base.base_context(request)

    product_id = request.session.get("last_added_product_id")
    product = None

    if product_id:
        try:
            product = MerchProduct.objects.get(
                id=product_id,
                business=ctx["business"],
                kind=BusinessKind.CLOTHING,
            )
        except MerchProduct.DoesNotExist:
            pass

    ctx.update(
        {
            "product": product,
            "page_title": "Product Added",
        }
    )

    return render(request, "verticals/clothing/quick_add_success.html", ctx)


# ============================================================================
# FAST STOCK IN
# ============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def fast_stock_in(request):
    """
    Fast stock-in page: search box + top items grid for one-tap stock.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")

    # Get recent/top products for quick access
    recent_products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.CLOTHING,
        is_active=True,
        is_archived=False,
    ).order_by("-id")[:20]

    # Get top sellers (for quick restock)
    top_sellers = get_top_sellers(business, days=7, limit=10)
    top_seller_ids = [item["product"].id for item in top_sellers]

    ctx.update(
        {
            "recent_products": recent_products,
            "top_seller_ids": top_seller_ids,
            "page_title": "Stock In",
        }
    )

    return render(request, "verticals/clothing/fast_stock_in.html", ctx)


# ============================================================================
# FAST SELL
# ============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def fast_sell(request):
    """
    Fast sell page: scanner-first UX for barcoded clothing items.
    
    CRITICAL: Fast Sell is ONLY for barcoded items (ClothingBarcodeUnit).
    For common stock (non-barcoded), users should use Manual Sell instead.
    """
    from inventory.models_clothing_barcode import ClothingBarcodeUnit
    
    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")

    # Get in-stock barcode units (authoritative source for Fast Sell)
    barcode_units_query = ClothingBarcodeUnit.objects.filter(
        business=business,
        status="IN_STOCK",
        is_active=True,
    )
    
    # Apply location filter if available
    if location:
        barcode_units_query = barcode_units_query.filter(location=location)
    
    # Get distinct products that have barcoded units in stock
    # Group by product attributes for display
    barcode_units = barcode_units_query.select_related("product").order_by("-created_at")[:50]
    
    # Build available items list (one entry per unique product/size combo)
    available_items = []
    seen_combos = set()
    
    for unit in barcode_units:
        # Create unique key for product + size combination
        combo_key = (
            unit.product.id if unit.product else None,
            unit.size,
            unit.category,
            unit.brand,
        )
        
        if combo_key not in seen_combos:
            seen_combos.add(combo_key)
            
            # Count how many units of this combo are in stock
            units_count = barcode_units_query.filter(
                product=unit.product if unit.product else None,
                size=unit.size,
                category=unit.category,
                brand=unit.brand,
            ).count()
            
            available_items.append({
                "product": unit.product,
                "size": unit.size,
                "category": unit.category,
                "brand": unit.brand,
                "color": unit.color,
                "selling_price": unit.selling_price,
                "units_in_stock": units_count,
                "display_name": f"{unit.brand} {unit.category} - Size {unit.size}" if unit.brand else f"{unit.category} - Size {unit.size}",
            })
    
    # Calculate total barcoded units available
    total_barcoded_units = barcode_units_query.count()

    ctx.update(
        {
            "available_items": available_items,
            "total_barcoded_units": total_barcoded_units,
            "page_title": "Fast Sell",
            "vertical": "clothing",
        }
    )

    return render(request, "verticals/clothing/fast_sell.html", ctx)


# ============================================================================
# SMART FILTERS & SUMMARIES
# ============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def products_list(request):
    """
    Products list with smart filters and summaries.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")

    # Base queryset
    products_qs = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.CLOTHING,
        is_active=True,
        is_archived=False,
    )

    # Apply filters
    category_filter = request.GET.get("category", "")
    brand_filter = request.GET.get("brand", "")
    stock_filter = request.GET.get("stock", "")  # in, low, out
    price_tier_filter = request.GET.get("price_tier", "")
    search_query = request.GET.get("q", "")

    if category_filter:
        products_qs = products_qs.filter(category=category_filter)

    if brand_filter:
        products_qs = products_qs.filter(brand__icontains=brand_filter)

    if stock_filter == "out":
        products_qs = products_qs.filter(quantity_in_stock=0)
    elif stock_filter == "low":
        products_qs = products_qs.filter(quantity_in_stock__gt=0, quantity_in_stock__lte=3)
    elif stock_filter == "in":
        products_qs = products_qs.filter(quantity_in_stock__gt=3)

    if price_tier_filter:
        # Filter by price tier (requires calculation)
        pass  # TODO: implement price tier filtering

    if search_query:
        products_qs = products_qs.filter(
            Q(name__icontains=search_query)
            | Q(brand__icontains=search_query)
            | Q(internal_sku__icontains=search_query)
            | Q(barcode__icontains=search_query)
        )

    # Pagination
    paginator = Paginator(products_qs, 50)
    page = request.GET.get("page", 1)
    products_page = paginator.get_page(page)

    # Get filter options (for UI)
    all_categories = products_qs.values_list("category", flat=True).distinct()
    all_brands = products_qs.exclude(brand="").values_list("brand", flat=True).distinct()

    ctx.update(
        {
            "products": products_page,
            "all_categories": all_categories,
            "all_brands": all_brands,
            "category_filter": category_filter,
            "brand_filter": brand_filter,
            "stock_filter": stock_filter,
            "price_tier_filter": price_tier_filter,
            "search_query": search_query,
            "page_title": "Products",
        }
    )

    return render(request, "verticals/clothing/products_list.html", ctx)


# ============================================================================
# LABEL/QR PRINTING
# ============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def print_labels(request, product_id):
    """
    Generate and download product labels as PDF.
    """
    from inventory.labels.clothing_labels import generate_product_labels

    ctx = base.base_context(request)
    business = ctx.get("business")

    # Get product
    product = get_object_or_404(
        MerchProduct,
        id=product_id,
        business=business,
        kind=BusinessKind.CLOTHING,
    )

    # Get parameters
    quantity = int(request.GET.get("qty", 1))
    show_price = request.GET.get("show_price", "yes") == "yes"
    label_size = request.GET.get("size", "medium")  # small, medium, large

    # Generate PDF
    try:
        pdf_buffer = generate_product_labels(
            product=product,
            quantity=quantity,
            show_price=show_price,
            label_size=label_size,
        )

        # Return as download
        response = HttpResponse(pdf_buffer.read(), content_type="application/pdf")
        filename = f"labels_{product.internal_sku or product.id}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        return response

    except Exception as e:
        messages.error(request, f"Error generating labels: {str(e)}")
        return redirect("verticals:clothing_dashboard_v2")


# ============================================================================
# QR SCAN ENDPOINT
# ============================================================================


@login_required
@require_business
def scan_qr(request, token):
    """
    QR scan endpoint: validates token and redirects to quick sell page.
    """
    from inventory.clothing_config import verify_product_qr_token

    ctx = base.base_context(request)
    business = ctx.get("business")

    # Verify token
    token_data = verify_product_qr_token(token)

    if not token_data:
        messages.error(request, "Invalid or expired QR code")
        return redirect("verticals:clothing_dashboard_v2")

    # Check business match (prevent cross-business leakage)
    if token_data["business_id"] != business.id:
        messages.error(request, "This QR code belongs to a different business")
        return redirect("verticals:clothing_dashboard_v2")

    # Get product
    try:
        product = MerchProduct.objects.get(
            id=token_data["product_id"],
            business=business,
            kind=BusinessKind.CLOTHING,
        )
    except MerchProduct.DoesNotExist:
        messages.error(request, "Product not found")
        return redirect("verticals:clothing_dashboard_v2")

    # Redirect to fast sell with product pre-selected
    return redirect(f"/verticals/clothing/fast-sell/?product_id={product.id}")


__all__ = [
    "dashboard_v2",
    "quick_add_step1",
    "quick_add_step2",
    "quick_add_success",
    "fast_stock_in",
    "fast_sell",
    "products_list",
    "print_labels",
    "scan_qr",
]

from __future__ import annotations

from decimal import Decimal
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, F, Q
from django.db.models.functions import Coalesce
from django.shortcuts import render
from django.utils import timezone

from tenants.utils import require_business

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct
from inventory.models_verticals import ClothingSale

from . import base

# ============================================================================
# COMPATIBILITY: Re-export CLOTHING_CATEGORIES from SSOT
# ============================================================================
# The single source of truth is inventory.clothing_config.CLOTHING_CATEGORIES
# This re-export maintains backward compatibility for existing imports:
#   from inventory.verticals.clothing import CLOTHING_CATEGORIES
from inventory.clothing_config import CLOTHING_CATEGORIES  # noqa: F401


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def dashboard(request):
    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")

    # Get product metrics (unchanged)
    metrics = base.merch_metrics(business, BusinessKind.CLOTHING)

    # ===== DATE FILTER PARAMS (ALL OPTIONS RESTORED) =====
    # Use shared date range parser with ALL filter support
    date_range_ctx = base.parse_date_range_from_request(request)
    
    # Extract all values for context
    filter_mode = date_range_ctx.get("filter_mode")
    period = date_range_ctx.get("period")
    month = date_range_ctx.get("month")
    year = date_range_ctx.get("year")
    start_date = date_range_ctx["start_date"]
    end_date = date_range_ctx["end_date"]
    range_label = date_range_ctx["range_label"]
    custom_start = date_range_ctx.get("custom_start")
    custom_end = date_range_ctx.get("custom_end")

    # ===== SALES METRICS WITH DATE FILTERING =====
    # Pass explicit start/end dates (None for all-time)
    sales_data = base.clothing_sales_metrics(
        business, 
        location=location, 
        start_date=start_date,
        end_date=end_date,
    )

    # ===== INVENTORY VALUE METRICS (Current Stock) =====
    inventory_data = base.clothing_inventory_metrics(business, location=location)

    # ===== RECENT SALES (Last 10 sales for display) =====
    recent_sales = (
        ClothingSale.objects.filter(business=business)
        .select_related("product", "sold_by")
        .order_by("-sold_at")[:10]
    )

    # Extract metrics from sales_data
    revenue_mtd = sales_data["revenue"]
    cost_mtd = sales_data["cost_of_goods"]
    overhead_costs = sales_data["overhead_costs"]
    profit_mtd = sales_data["profit"]
    total_sales_mtd = sales_data["total_sales"]
    payment_mix_data = sales_data["payment_mix_data"]
    top_models = sales_data["top_models"]
    top_model = sales_data["top_model"]
    sales_trend = sales_data["sales_trend"]

    # Calculate total costs (COGS + Overhead)
    total_costs_mtd = cost_mtd + overhead_costs

    # Extract inventory metrics
    inventory_value = inventory_data["inventory_value"]
    retail_value = inventory_data["retail_value"]
    expected_margin = inventory_data["expected_margin"]

    # ===== STOCK SUMMARY BY CATEGORY =====
    # FIXED: Aggregate BOTH tracked units (ClothingBarcodeUnit) AND common stock (MerchProduct.quantity_in_stock)
    from inventory.models_clothing_barcode import ClothingBarcodeUnit
    from collections import defaultdict
    
    # Initialize category aggregation storage
    category_data = defaultdict(lambda: {"tracked_units": 0, "tracked_styles": set(), "common_units": 0, "common_styles": set()})
    
    # 1. Aggregate tracked units (barcoded items) by category
    tracked_query = ClothingBarcodeUnit.objects.filter(
        business=business,
        status="IN_STOCK",
        is_active=True,
    )
    
    # Apply location filter if available
    if location:
        tracked_query = tracked_query.filter(location=location)
    
    # Group by category and count units and distinct products
    tracked_summary = tracked_query.values("category").annotate(
        unit_count=Count("id"),
        style_count=Count("product_id", distinct=True)
    )
    
    for item in tracked_summary:
        category = (item["category"] or "other").lower()
        category_data[category]["tracked_units"] = item["unit_count"]
        # Note: we can't get the set of product_ids from aggregation, so we use the count directly
        category_data[category]["tracked_styles_count"] = item["style_count"]
    
    # 2. Aggregate common stock (non-tracked products with quantity_in_stock) by category
    common_query = MerchProduct.objects.filter(
        business=business, 
        kind=BusinessKind.CLOTHING, 
        is_active=True, 
        is_archived=False,
        quantity_in_stock__gt=0,
    )
    
    # Apply location filter if MerchProduct has location field (currently it doesn't, so this is future-proof)
    if location and hasattr(MerchProduct, 'location'):
        common_query = common_query.filter(location=location)
    
    # Exclude products that have tracked units (to avoid double counting)
    # Products with tracked units should only be counted in tracked_units
    products_with_tracked_units = tracked_query.values_list("product_id", flat=True).distinct()
    common_query = common_query.exclude(id__in=products_with_tracked_units)
    
    # Group by category and sum quantities
    common_summary = common_query.values("category").annotate(
        quantity_sum=Sum("quantity_in_stock"),
        style_count=Count("id")
    )
    
    for item in common_summary:
        category = (item["category"] or "other").lower()
        category_data[category]["common_units"] = item["quantity_sum"] or 0
        category_data[category]["common_styles_count"] = item["style_count"]
    
    # 3. Merge and format for display
    stock_summary_display = []
    category_icons = {
        "shoes": "👞",
        "shirt": "👔",
        "dress": "👗",
        "suit": "🤵",
        "trousers": "👖",
        "jeans": "👖",
        "shorts": "🩳",
        "jacket": "🧥",
        "skirt": "🩱",
        "belts": "🔗",
        "perfumes": "🌸",
        "handbags": "👜",
        "schoolbags": "🎒",
    }
    
    # Sort categories by total stock (tracked + common) descending
    sorted_categories = sorted(
        category_data.items(),
        key=lambda x: x[1]["tracked_units"] + x[1]["common_units"],
        reverse=True
    )
    
    for category, data in sorted_categories:
        # Calculate totals
        total_units = data["tracked_units"] + data["common_units"]
        total_styles = data.get("tracked_styles_count", 0) + data.get("common_styles_count", 0)
        
        # Skip categories with zero stock
        if total_units == 0:
            continue
        
        icon = category_icons.get(category, "👕")
        stock_summary_display.append(
            {
                "category": category.title(),
                "icon": icon,
                "total_items": total_styles,  # Total number of distinct product styles
                "total_quantity": total_units,  # Total units in stock (tracked + common)
                "tracked_quantity": data["tracked_units"],  # Barcoded units
                "common_quantity": data["common_units"],  # Common stock units
            }
        )

    # ===== NEW: Personalized dashboard enhancements (quotes & greetings) =====
    ctx_enhancements = {}
    try:
        from dashboard.helpers_greetings import get_personalized_greeting
        from dashboard.helpers_quotes import get_todays_quotes
        import json as json_lib

        # Personalized greeting (changes 3x daily: morning, afternoon, evening)
        greeting_ctx = get_personalized_greeting(request.user, business)

        # Brand header context
        brand_logo_url = None
        if business and hasattr(business, "logo") and business.logo:
            brand_logo_url = business.logo.url

        # Hourly quotes (rotates every hour)
        daily_quotes = get_todays_quotes(request.user, count=10)

        # Extract quote texts for JavaScript rotation
        quote_texts = [q.get("text", "") for q in daily_quotes.get("quotes", []) if q.get("text")]
        quotes_json_data = json_lib.dumps(quote_texts)

        ctx_enhancements.update(
            {
                "DASHBOARD_GREETING": greeting_ctx.get("greeting"),
                "DASHBOARD_USER_NAME": greeting_ctx.get("user_name"),
                "DASHBOARD_SHOW_WELCOME": greeting_ctx.get("show_welcome"),
                "DASHBOARD_MILESTONE_MESSAGE": greeting_ctx.get("milestone"),
                "DASHBOARD_BRAND_LOGO_URL": brand_logo_url,
                "DASHBOARD_BRAND_TITLE": business.name if business else "Clothing Dashboard",
                "DASHBOARD_QUOTES": daily_quotes,
                "quotes_json": quotes_json_data,
            }
        )
    except Exception:
        # Gracefully degrade if helpers not available
        pass

    ctx.update(
        {
            "hero_title": "Clothing & Fashion",
            "hero_blurb": "Track outfits, sizes, and curated drops for each location.",
            "product_count": metrics["total"],
            "active_product_count": metrics["active"],
            "scan_required_count": metrics["scan_required"],
            "inventory_tracked_count": metrics["inventory_tracked"],
            "recent_products": metrics["recent"],
            # Recent Sales List (Last 10 transactions)
            "recent_sales": recent_sales,
            # KPI Panels (Sales Metrics)
            "revenue_mtd": revenue_mtd,
            "cost_mtd": cost_mtd,
            "overhead_costs": overhead_costs,
            "total_costs_mtd": total_costs_mtd,
            "profit_mtd": profit_mtd,
            "total_sales_mtd": total_sales_mtd,
            # Inventory Value KPIs (Current Stock)
            "inventory_value": inventory_value,
            "retail_value": retail_value,
            "expected_margin": expected_margin,
            # Payment Mix
            "payment_mix_data": payment_mix_data,
            # Top Model & Trends
            "top_model": top_model,
            "top_models": top_models,
            "sales_trend": sales_trend,
            # Stock Summary
            "stock_summary": stock_summary_display,
            # Date Filter State (ALL OPTIONS RESTORED)
            "filter_mode": filter_mode,
            "period": period,
            "month": month,
            "year": year,
            "start_date": start_date,
            "end_date": end_date,
            "range_label": range_label,
            "custom_start": custom_start,
            "custom_end": custom_end,
            **ctx_enhancements,  # Merge dashboard enhancements
        }
    )

    # Inject dashboard enhancements and normalize context
    from core.dashboard_context import normalize_dashboard_context

    ctx = normalize_dashboard_context(request, ctx)

    return render(request, "verticals/clothing/dashboard.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def hub(request):
    """
    Clothing Hub - Premium Inventory Cockpit.
    
    Shows:
    - Top KPI cards (total products, in stock, low stock, barcoded units)
    - Product cards with stock battery, badges (Tracked/Common), quick actions
    - Filter chips: All / Common / Barcoded / Low Stock
    """
    from inventory.models_verticals import ClothingProductLog, ClothingProductAction
    from inventory.models_clothing_barcode import ClothingBarcodeUnit

    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")

    # Get filter from query params
    filter_type = request.GET.get("filter", "all")  # all, common, barcoded, low_stock

    # === TOP KPI CARDS ===
    # Total products
    total_products = MerchProduct.objects.filter(
        business=business, kind=BusinessKind.CLOTHING, is_active=True, is_archived=False
    ).count()

    # In stock (common stock qty)
    in_stock_common = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.CLOTHING,
        is_active=True,
        is_archived=False,
        quantity_in_stock__gt=0,
    ).count()

    # Barcoded units in stock
    barcode_query = ClothingBarcodeUnit.objects.filter(
        business=business,
        status="IN_STOCK",
        is_active=True,
    )
    if location:
        barcode_query = barcode_query.filter(location=location)
    
    barcoded_units_count = barcode_query.count()

    # Low stock count (products with quantity < 3)
    low_stock_count = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.CLOTHING,
        is_active=True,
        is_archived=False,
        quantity_in_stock__lt=3,
        quantity_in_stock__gt=0,
    ).count()

    # Get all active clothing products
    products_query = MerchProduct.objects.filter(
        business=business, kind=BusinessKind.CLOTHING, is_active=True, is_archived=False
    )

    # Apply filters
    if filter_type == "low_stock":
        products_query = products_query.filter(quantity_in_stock__lt=3, quantity_in_stock__gt=0)
    elif filter_type == "common":
        # Products with common stock (quantity_in_stock > 0) and no barcoded units
        # We'll filter this after building panels
        pass
    elif filter_type == "barcoded":
        # Products that have barcoded units
        # We'll filter this after building panels
        pass

    products = products_query.order_by("-id")

    # Build product panel data
    product_panels = []
    for product in products:
        # Check if product has barcoded units
        product_barcode_units = ClothingBarcodeUnit.objects.filter(
            business=business,
            product=product,
            status="IN_STOCK",
            is_active=True,
        )
        if location:
            product_barcode_units = product_barcode_units.filter(location=location)
        
        barcode_units_count = product_barcode_units.count()
        is_tracked = barcode_units_count > 0
        is_common = (product.quantity_in_stock or 0) > 0

        # Apply "barcoded" filter
        if filter_type == "barcoded" and not is_tracked:
            continue
        
        # Apply "common" filter
        if filter_type == "common" and not is_common:
            continue

        # Calculate stock IN quantities from logs
        stock_in_logs = ClothingProductLog.objects.filter(product=product, action=ClothingProductAction.STOCK_IN)

        stock_in_qty = 0
        total_stock_in_cost = Decimal("0.00")
        for log in stock_in_logs:
            qty_added = log.changes.get("quantity_added", 0)
            cost_price_str = log.changes.get("cost_price", "0")
            try:
                cost_price = Decimal(str(cost_price_str))
            except:
                cost_price = Decimal("0.00")

            stock_in_qty += qty_added
            total_stock_in_cost += Decimal(qty_added) * cost_price

        # Calculate sales stats
        sales = ClothingSale.objects.filter(business=business, product=product).aggregate(
            total_sold=Sum("quantity"), total_revenue=Sum("total_price"), total_cost=Sum("total_cost")
        )

        stock_sold_qty = sales["total_sold"] or 0
        revenue_total = sales["total_revenue"] or Decimal("0.00")
        cost_of_goods_sold = sales["total_cost"] or Decimal("0.00")

        # Calculate available stock (common + barcoded)
        available_qty = (product.quantity_in_stock or 0) + barcode_units_count

        # Calculate inventory cost (cost of remaining stock)
        # Use current product cost_price or calculate average cost
        unit_cost = product.cost_price or Decimal("0.00")
        if unit_cost == 0 and stock_in_qty > 0 and total_stock_in_cost > 0:
            # Calculate average cost from stock-in logs
            unit_cost = total_stock_in_cost / Decimal(stock_in_qty)

        inventory_cost_total = Decimal(available_qty) * unit_cost

        # Calculate profit
        profit_total = revenue_total - cost_of_goods_sold

        # Stock battery calculation
        initial_capacity = stock_in_qty or (available_qty + stock_sold_qty)
        battery_percentage = 0
        if initial_capacity > 0:
            battery_percentage = int((available_qty / initial_capacity) * 100)

        # Status heuristics
        status = "Normal"
        status_class = "normal"

        if stock_sold_qty > 10:
            status = "🔥 Hot Selling"
            status_class = "hot"
        elif available_qty < 3 and available_qty > 0:
            status = "⚠️ Low Stock"
            status_class = "low"
        elif available_qty == 0:
            status = "❌ Out of Stock"
            status_class = "out"
        elif stock_sold_qty == 0 and stock_in_qty > 0:
            status = "✨ New Drop"
            status_class = "new"

        product_panels.append(
            {
                "product": product,
                "available_stock": available_qty,
                "common_stock": product.quantity_in_stock or 0,
                "barcode_units": barcode_units_count,
                "is_tracked": is_tracked,
                "is_common": is_common,
                "stock_in_qty": stock_in_qty,
                "total_sold": stock_sold_qty,
                "revenue": revenue_total,
                "inventory_cost": inventory_cost_total,
                "cost_of_goods_sold": cost_of_goods_sold,
                "profit": profit_total,
                "battery_percentage": battery_percentage,
                "status": status,
                "status_class": status_class,
            }
        )

    ctx.update(
        {
            "product_panels": product_panels,
            "page_title": "Clothing Hub",
            "active_tab": "hub",
            # KPI cards
            "total_products": total_products,
            "in_stock_common": in_stock_common,
            "barcoded_units_count": barcoded_units_count,
            "low_stock_count": low_stock_count,
            # Filters
            "filter_type": filter_type,
        }
    )

    return render(request, "verticals/clothing/hub.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def scan_in(request):
    """
    Gamified clothing stock-in flow.
    Step-by-step process: Category → Size → Color → Quantity/Cost
    """
    from django import forms
    from django.db import transaction
    from django.contrib import messages
    from django.shortcuts import redirect

    business = base.base_context(request).get("business")

    # Define clothing categories (expanded with more product types)
    CLOTHING_CATEGORIES = [
        ("suit", "Suit", "🤵"),
        ("dress", "Dress", "👗"),
        ("shirt", "Shirt", "👔"),
        ("trousers", "Trousers", "👖"),
        ("jeans", "Jeans", "👖"),
        ("shorts", "Shorts", "🩳"),
        ("shoes", "Shoes", "👞"),
        ("jacket", "Jacket", "🧥"),
        ("skirt", "Skirt", "🩱"),
        ("belts", "Belts", "🔗"),
        ("perfumes", "Perfumes", "🌸"),
        ("handbags", "Hand Bags", "👜"),
        ("schoolbags", "School Bags", "🎒"),
        ("other", "Other", "👕"),
    ]

    # Define sizes
    SIZES = ["XS", "S", "M", "L", "XL", "XXL", "28", "30", "32", "34", "36", "38", "40", "42", "44"]

    # Define colors
    COLORS = ["Black", "Navy", "Grey", "White", "Beige", "Brown", "Blue", "Red", "Green", "Other"]

    class ClothingStockInForm(forms.Form):
        category = forms.ChoiceField(
            choices=[(cat[0], cat[1]) for cat in CLOTHING_CATEGORIES],
            widget=forms.Select(attrs={"class": "form-control form-select"}),
        )
        size = forms.ChoiceField(
            choices=[(s, s) for s in SIZES], widget=forms.Select(attrs={"class": "form-control form-select"})
        )
        color = forms.ChoiceField(
            choices=[(c, c) for c in COLORS], widget=forms.Select(attrs={"class": "form-control form-select"})
        )
        quantity = forms.IntegerField(
            min_value=1, initial=1, widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "Quantity"})
        )
        cost_price = forms.DecimalField(
            max_digits=10,
            decimal_places=2,
            min_value=0,
            widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "Cost per unit"}),
        )
        selling_price = forms.DecimalField(
            max_digits=10,
            decimal_places=2,
            min_value=0,
            required=False,
            widget=forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "placeholder": "Selling price (optional)"}
            ),
        )

    if request.method == "POST":
        # NEW: Barcode workflow
        has_barcode = request.POST.get("has_barcode", "no").strip()
        barcode_value = request.POST.get("barcode", "").strip()

        # NEW: Barcode validation (conditional)
        if has_barcode == "yes":
            if not barcode_value:
                messages.error(request, "Barcode is required when 'Has Barcode' is Yes.")
                form = ClothingStockInForm(request.POST)
                recent_logs = []
                try:
                    from inventory.models_verticals import ClothingProductLog, ClothingProductAction

                    recent_logs = (
                        ClothingProductLog.objects.filter(
                            product__business=business, action=ClothingProductAction.STOCK_IN
                        )
                        .select_related("product", "performed_by")
                        .order_by("-created_at")[:10]
                    )
                except:
                    pass
                ctx = {
                    "business": business,
                    "form": form,
                    "categories": CLOTHING_CATEGORIES,
                    "recent_logs": recent_logs,
                }
                return render(request, "verticals/clothing/scan_in.html", ctx)

            from inventory.utils_barcodes import validate_barcode, normalize_barcode, find_by_barcode

            is_valid, error_msg = validate_barcode(barcode_value)
            if not is_valid:
                messages.error(request, f"Invalid barcode: {error_msg}")
                form = ClothingStockInForm(request.POST)
                recent_logs = []
                try:
                    from inventory.models_verticals import ClothingProductLog, ClothingProductAction

                    recent_logs = (
                        ClothingProductLog.objects.filter(
                            product__business=business, action=ClothingProductAction.STOCK_IN
                        )
                        .select_related("product", "performed_by")
                        .order_by("-created_at")[:10]
                    )
                except:
                    pass
                ctx = {
                    "business": business,
                    "form": form,
                    "categories": CLOTHING_CATEGORIES,
                    "recent_logs": recent_logs,
                }
                return render(request, "verticals/clothing/scan_in.html", ctx)

            barcode_value = normalize_barcode(barcode_value)

            # Check for duplicate barcode in this business
            existing_products = find_by_barcode(barcode_value, business=business)
            if existing_products.exists():
                messages.error(
                    request,
                    f"Barcode {barcode_value} is already used by another product in your business. "
                    "Each barcode must be unique.",
                )
                form = ClothingStockInForm(request.POST)
                recent_logs = []
                try:
                    from inventory.models_verticals import ClothingProductLog, ClothingProductAction

                    recent_logs = (
                        ClothingProductLog.objects.filter(
                            product__business=business, action=ClothingProductAction.STOCK_IN
                        )
                        .select_related("product", "performed_by")
                        .order_by("-created_at")[:10]
                    )
                except:
                    pass
                ctx = {
                    "business": business,
                    "form": form,
                    "categories": CLOTHING_CATEGORIES,
                    "recent_logs": recent_logs,
                }
                return render(request, "verticals/clothing/scan_in.html", ctx)

        form = ClothingStockInForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data

            # Create product name from category, size, and color
            product_name = f"{data['category'].title()} - {data['size']} - {data['color']}"

            # Prepare barcode value (None if not provided or if "no barcode" selected)
            final_barcode = barcode_value if (has_barcode == "yes" and barcode_value) else None

            with transaction.atomic():
                # Check if product exists
                # CRITICAL FIX: Set spec_label for clothing (use size, prevents NULL constraint)
                spec_label_value = data.get("size", "") or ""
                if spec_label_value and not spec_label_value.startswith("Size "):
                    spec_label_value = f"Size {spec_label_value}"

                product, created = MerchProduct.objects.get_or_create(
                    business=business,
                    name=product_name,
                    defaults={
                        "kind": BusinessKind.CLOTHING,
                        "category": data["category"],
                        "size": data["size"],
                        "color": data["color"],
                        "spec_label": spec_label_value,  # CRITICAL: Always set spec_label (prevents NULL constraint)
                        "cost_price": data["cost_price"],
                        "selling_price": data.get("selling_price"),
                        "quantity_in_stock": data["quantity"],
                        "is_active": True,
                        "track_inventory": True,
                        "barcode": final_barcode,  # CRITICAL: Explicitly set barcode (None if not provided)
                    },
                )

                # NEW: Store barcode if provided
                if final_barcode and created:
                    # Barcode already set in defaults, no need to set again
                    pass

                if not created:
                    # Update existing product stock
                    product.quantity_in_stock += data["quantity"]
                    product.cost_price = data["cost_price"]
                    if data.get("selling_price"):
                        product.selling_price = data["selling_price"]

                    # Update barcode if provided for existing product (only if has_barcode is yes)
                    if has_barcode == "yes" and final_barcode:
                        product.barcode = final_barcode
                    # If has_barcode is "no", don't change existing barcode (may have been set before)

                    update_fields = ["quantity_in_stock", "cost_price", "selling_price"]
                    if has_barcode == "yes" and final_barcode:
                        update_fields.append("barcode")
                    product.save(update_fields=update_fields)

                # Log the stock-in action
                from inventory.models_verticals import ClothingProductLog, ClothingProductAction

                ClothingProductLog.objects.create(
                    product=product,
                    action=ClothingProductAction.STOCK_IN,
                    changes={
                        "quantity_added": data["quantity"],
                        "cost_price": str(data["cost_price"]),
                        "new_stock": product.quantity_in_stock,
                    },
                    performed_by=request.user,
                )

            messages.success(
                request, f"✅ Stock added: {data['quantity']} × {product_name} (K {data['cost_price']} each)"
            )
            return redirect("verticals:clothing_scan_in")
        else:
            # Form validation failed - show errors
            messages.error(request, "Please correct the errors below.")
    else:
        form = ClothingStockInForm()

    # Recent stock-ins
    recent_logs = []
    try:
        from inventory.models_verticals import ClothingProductLog, ClothingProductAction

        recent_logs = (
            ClothingProductLog.objects.filter(product__business=business, action=ClothingProductAction.STOCK_IN)
            .select_related("product", "performed_by")
            .order_by("-created_at")[:10]
        )
    except:
        pass

    ctx = {
        "business": business,
        "form": form,
        "categories": CLOTHING_CATEGORIES,
        "recent_logs": recent_logs,
    }

    return render(request, "verticals/clothing/scan_in.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def sell(request):
    """
    Gamified clothing sell flow.
    Pick product → size → color → confirm sale
    """
    from django import forms
    from django.db import transaction
    from django.contrib import messages
    from django.shortcuts import redirect
    from inventory.models_verticals import PaymentMethod

    business = base.base_context(request).get("business")

    class ClothingSellForm(forms.Form):
        product = forms.ModelChoiceField(
            queryset=MerchProduct.objects.none(),
            widget=forms.Select(attrs={"class": "form-control form-select"}),
            label="Product/Model",
        )
        quantity = forms.IntegerField(
            min_value=1,
            initial=1,
            widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "Quantity"}),
            label="Quantity",
        )
        selling_price = forms.DecimalField(
            max_digits=10,
            decimal_places=2,
            min_value=0,
            widget=forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "placeholder": "Selling price per unit"}
            ),
            label="Selling Price (per unit)",
        )
        payment_method = forms.ChoiceField(
            choices=PaymentMethod.choices,
            initial=PaymentMethod.CASH,
            widget=forms.Select(attrs={"class": "form-control form-select"}),
            label="Payment Method",
        )
        notes = forms.CharField(
            required=False,
            widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Optional notes"}),
            label="Notes",
        )

        def __init__(self, business=None, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if business:
                # CRITICAL FIX: Exclude products that have unique barcode units
                # Those can ONLY be sold via Fast Sell (barcode scan)
                from inventory.models_clothing_barcode import ClothingBarcodeUnit
                
                # Get product IDs that have barcode units in stock
                products_with_barcode_units = ClothingBarcodeUnit.objects.filter(
                    business=business,
                    status="IN_STOCK",
                    is_active=True
                ).values_list("product_id", flat=True).distinct()
                
                # Show only clothing products with available stock, EXCLUDING unique-barcode products
                self.fields["product"].queryset = MerchProduct.objects.filter(
                    business=business,
                    kind=BusinessKind.CLOTHING,
                    is_active=True,
                    is_archived=False,
                    quantity_in_stock__gt=0,
                ).exclude(
                    id__in=products_with_barcode_units  # Exclude products with barcode units
                ).order_by("name")

        def clean_payment_method(self):
            """Normalize legacy payment method values for backward compatibility."""
            value = self.cleaned_data.get("payment_method", "")
            if not value:
                return PaymentMethod.CASH
            # Map legacy uppercase values to correct lowercase values
            mapping = {
                "CASH": PaymentMethod.CASH,
                "cash": PaymentMethod.CASH,
                "BANK": PaymentMethod.BANK,
                "BANK_TRANSFER": PaymentMethod.BANK,
                "bank": PaymentMethod.BANK,
                "bank_transfer": PaymentMethod.BANK,
                "MOBILE_MONEY": PaymentMethod.MOBILE_MONEY,
                "MOBILE": PaymentMethod.MOBILE_MONEY,
                "MOMO": PaymentMethod.MOBILE_MONEY,
                "mobile_money": PaymentMethod.MOBILE_MONEY,
                "mobile": PaymentMethod.MOBILE_MONEY,
                "momo": PaymentMethod.MOBILE_MONEY,
            }
            return mapping.get(value, PaymentMethod.CASH)

    if request.method == "POST":
        form = ClothingSellForm(business, request.POST)
        if form.is_valid():
            data = form.cleaned_data
            product = data["product"]
            quantity = data["quantity"]

            # CRITICAL FIX: Server-side validation - prevent selling unique-barcode items via normal sell
            from inventory.models_clothing_barcode import ClothingBarcodeUnit
            has_barcode_units = ClothingBarcodeUnit.objects.filter(
                business=business,
                product=product,
                status="IN_STOCK",
                is_active=True
            ).exists()
            
            if has_barcode_units:
                messages.error(
                    request, 
                    f"❌ {product.name} has unique barcoded items and can ONLY be sold via Fast Sell (barcode scan). "
                    "Please use the Fast Sell page to scan and sell these items."
                )
                return redirect("verticals:clothing_sell")

            # CRITICAL: Enforce stock validation - NEVER allow negative stock
            current_stock = product.quantity_in_stock or 0
            if current_stock < quantity:
                messages.error(
                    request, f"❌ Insufficient stock! Only {current_stock} available. Cannot sell {quantity} units."
                )
                return redirect("verticals:clothing_sell")

            with transaction.atomic():
                # Reduce stock (will never go negative due to validation above)
                product.quantity_in_stock = current_stock - quantity
                product.save(update_fields=["quantity_in_stock"])

                # Create sale
                unit_price = data["selling_price"]
                total_price = Decimal(quantity) * unit_price
                unit_cost = product.cost_price or Decimal("0.00")
                total_cost = Decimal(quantity) * unit_cost

                sale = ClothingSale.objects.create(
                    business=business,
                    product=product,
                    quantity=quantity,
                    unit_price=unit_price,
                    total_price=total_price,
                    unit_cost=unit_cost,
                    total_cost=total_cost,
                    payment_method=data["payment_method"],
                    sold_by=request.user,
                    notes=data.get("notes", ""),
                )

                # Log the sale
                from inventory.models_verticals import ClothingProductLog, ClothingProductAction

                ClothingProductLog.objects.create(
                    product=product,
                    action=ClothingProductAction.SOLD,
                    changes={
                        "quantity_sold": quantity,
                        "selling_price": str(unit_price),
                        "total_revenue": str(total_price),
                        "remaining_stock": product.quantity_in_stock,
                    },
                    performed_by=request.user,
                )

                profit = total_price - total_cost
                # Gamified success message
                messages.success(
                    request,
                    f"🟢 Sale recorded 🎉\n"
                    f"Stock updated · Revenue added · Well done!\n"
                    f"{quantity} × {product.name} | Revenue: K {total_price:,.2f} | Profit: K {profit:,.2f}\n"
                    f"Remaining stock: {product.quantity_in_stock}",
                )
                # FIXED: Redirect to clothing dashboard (not sell page)
                return redirect("verticals:clothing_dashboard")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ClothingSellForm(business)

    # Recent sales
    recent_sales = (
        ClothingSale.objects.filter(business=business).select_related("product", "sold_by").order_by("-sold_at")[:10]
    )

    ctx = {
        "business": business,
        "form": form,
        "recent_sales": recent_sales,
    }

    return render(request, "verticals/clothing/sell.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def sales_history(request):
    """
    Sales History page with filters, pagination, and export.
    Shows all clothing sales with date range filtering and search.
    """
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    from django.db.models import Q

    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")

    # Build base queryset
    sales_qs = ClothingSale.objects.filter(business=business).select_related("product", "sold_by")

    if location:
        # If ClothingSale has location field, filter by it
        if hasattr(ClothingSale, "location"):
            sales_qs = sales_qs.filter(location=location)

    # Parse filter parameters
    start_date = request.GET.get("start", "")
    end_date = request.GET.get("end", "")
    search_query = request.GET.get("q", "")
    sale_id = request.GET.get("sale_id", "")

    # Apply date filters
    if start_date:
        try:
            from datetime import datetime

            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            sales_qs = sales_qs.filter(sold_at__date__gte=start_dt)
        except ValueError:
            pass

    if end_date:
        try:
            from datetime import datetime

            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            sales_qs = sales_qs.filter(sold_at__date__lte=end_dt)
        except ValueError:
            pass

    # Apply search filter (search across product name, notes, payment method)
    if search_query:
        sales_qs = sales_qs.filter(
            Q(product__name__icontains=search_query)
            | Q(product__category__icontains=search_query)
            | Q(notes__icontains=search_query)
            | Q(sold_by__username__icontains=search_query)
        )

    # Highlight specific sale if sale_id provided
    highlighted_sale_id = None
    if sale_id:
        try:
            highlighted_sale_id = int(sale_id)
            # Ensure the sale exists in the filtered queryset
            if not sales_qs.filter(id=highlighted_sale_id).exists():
                highlighted_sale_id = None
        except ValueError:
            pass

    # Order by most recent first
    sales_qs = sales_qs.order_by("-sold_at")

    # Pagination
    page = request.GET.get("page", 1)
    paginator = Paginator(sales_qs, 50)  # 50 sales per page

    try:
        sales_page = paginator.page(page)
    except PageNotAnInteger:
        sales_page = paginator.page(1)
    except EmptyPage:
        sales_page = paginator.page(paginator.num_pages)

    # Summary stats for filtered results
    summary = sales_qs.aggregate(
        total_revenue=Sum("total_price"),
        total_cost=Sum("total_cost"),
        total_sales=Count("id"),
        total_items=Sum("quantity"),
    )

    ctx.update(
        {
            "sales": sales_page,
            "start_date": start_date,
            "end_date": end_date,
            "search_query": search_query,
            "highlighted_sale_id": highlighted_sale_id,
            "summary": summary,
            "page_title": "Sales History",
        }
    )

    return render(request, "verticals/clothing/sales_history.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def sales_export_csv(request):
    """
    Export filtered sales to CSV.
    Respects all the same filters as sales_history view.
    """
    import csv
    from django.http import HttpResponse
    from django.db.models import Q

    business = base.base_context(request).get("business")
    location = base.base_context(request).get("location")

    # Build queryset with same filters as sales_history
    sales_qs = ClothingSale.objects.filter(business=business).select_related("product", "sold_by")

    if location:
        if hasattr(ClothingSale, "location"):
            sales_qs = sales_qs.filter(location=location)

    # Apply filters
    start_date = request.GET.get("start", "")
    end_date = request.GET.get("end", "")
    search_query = request.GET.get("q", "")

    if start_date:
        try:
            from datetime import datetime

            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            sales_qs = sales_qs.filter(sold_at__date__gte=start_dt)
        except ValueError:
            pass

    if end_date:
        try:
            from datetime import datetime

            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            sales_qs = sales_qs.filter(sold_at__date__lte=end_dt)
        except ValueError:
            pass

    if search_query:
        sales_qs = sales_qs.filter(
            Q(product__name__icontains=search_query)
            | Q(product__category__icontains=search_query)
            | Q(notes__icontains=search_query)
            | Q(sold_by__username__icontains=search_query)
        )

    sales_qs = sales_qs.order_by("-sold_at")

    # Create CSV response
    response = HttpResponse(content_type="text/csv")
    response[
        "Content-Disposition"
    ] = f'attachment; filename="clothing_sales_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'

    writer = csv.writer(response)

    # Write header
    writer.writerow(
        [
            "Timestamp",
            "Date",
            "Time",
            "Item",
            "Category",
            "Size",
            "Color",
            "Qty",
            "Unit Price",
            "Total",
            "Payment Method",
            "Cashier",
            "Notes",
        ]
    )

    # Write data rows
    for sale in sales_qs:
        product = sale.product
        timestamp = timezone.localtime(sale.sold_at)

        writer.writerow(
            [
                timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                timestamp.strftime("%Y-%m-%d"),
                timestamp.strftime("%H:%M:%S"),
                product.name or "",
                getattr(product, "category", "") or "",
                getattr(product, "size", "") or "",
                getattr(product, "color", "") or "",
                sale.quantity,
                f"{sale.unit_price:.2f}",
                f"{sale.total_price:.2f}",
                sale.get_payment_method_display()
                if hasattr(sale, "get_payment_method_display")
                else sale.payment_method,
                sale.sold_by.username if sale.sold_by else "System",
                sale.notes or "",
            ]
        )

    return response


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def fast_sell(request):
    """
    Fast Sell page for clothing - barcode scanner + instant sell.
    Supports BOTH tracked (barcoded) units AND common stock.
    
    FIXED: Now queries and displays barcoded items in stock correctly.
    """
    from inventory.models_clothing_barcode import ClothingBarcodeUnit
    
    # Use base_context which provides role flags, business, and all standard context
    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")

    # ========================================================================
    # TRACKED UNITS: Get in-stock barcode units (authoritative source)
    # ========================================================================
    barcode_units_query = ClothingBarcodeUnit.objects.filter(
        business=business,
        status="IN_STOCK",  # CRITICAL: Must be IN_STOCK (not SOLD)
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
                "kind": "tracked",  # Mark as tracked for template
            })
    
    # Calculate total barcoded units available
    total_barcoded_units = barcode_units_query.count()
    
    # ========================================================================
    # COMMON STOCK: Get common stock products with quantity > 0
    # ========================================================================
    # Build base queryset WITHOUT slicing first
    common_products_query = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.CLOTHING,
        is_active=True,
        is_archived=False,
        quantity_in_stock__gt=0,
    )
    
    # Filter out products that have tracked units (to avoid confusion)
    # Products with tracked units should only be sold via tracked units
    products_with_tracked_units = barcode_units_query.values_list("product_id", flat=True).distinct()
    
    # Apply exclusion BEFORE slicing
    common_products_query = common_products_query.exclude(id__in=products_with_tracked_units)
    
    # Apply ordering and slicing at the very end
    common_products = common_products_query.order_by("-quantity_in_stock", "name")[:50]
    
    # Build common stock items list
    common_items = []
    for product in common_products:
        display_name = product.name
        if product.size:
            display_name = f"{display_name} - {product.size}"
        if product.color:
            display_name = f"{display_name} ({product.color})"
        
        common_items.append({
            "product": product,
            "product_id": product.id,
            "name": display_name,
            "category": product.category or "",
            "size": product.size or "",
            "color": product.color or "",
            "selling_price": product.selling_price or Decimal("0.00"),
            "quantity_in_stock": product.quantity_in_stock or 0,
            "kind": "common",  # Mark as common for template
        })

    # Defensively ensure all required context variables exist
    # This prevents template errors from missing variables in partials
    ctx.setdefault("IS_MANAGER", ctx.get("is_manager", False))
    ctx.setdefault("IS_AGENT", ctx.get("is_agent", False))
    ctx.setdefault("SHOW_BILLING", ctx.get("show_billing", False))
    ctx.setdefault(
        "ROLE_FLAGS",
        {
            "is_manager": ctx.get("is_manager", False),
            "is_agent": ctx.get("is_agent", False),
            "show_billing": ctx.get("show_billing", False),
        },
    )

    # Page-specific context
    ctx.update(
        {
            "page_title": "Fast Sell",
            "vertical": "clothing",
            "vertical_name": "Clothing",
            "available_items": available_items,  # Tracked units
            "common_items": common_items,  # Common stock
            "total_barcoded_units": total_barcoded_units,
            "total_common_items": len(common_items),
        }
    )

    return render(request, "verticals/clothing/fast_sell.html", ctx)


# Fast Sell API endpoints
@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def fast_sell_lookup_api(request):
    """API: Look up product by barcode"""
    from django.http import JsonResponse
    from inventory.services.fast_sell import lookup_product_by_barcode

    business = base.base_context(request).get("business")
    barcode = request.GET.get("barcode", "").strip()

    if not barcode:
        return JsonResponse({"ok": False, "error": "Barcode required"}, status=400)

    result = lookup_product_by_barcode(business=business, vertical="clothing", barcode=barcode)

    return JsonResponse(result)


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def fast_sell_create_api(request):
    """API: Create a fast sale - supports both product_id and barcode"""
    from django.http import JsonResponse
    from django.db import transaction
    from inventory.services.fast_sell import create_fast_sell
    from inventory.models_verticals import PaymentMethod
    import json

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    business = base.base_context(request).get("business")

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    # Support both product_id (from cart) and barcode (from scanner)
    product_id = data.get("product_id")
    barcode = data.get("barcode", "").strip()
    quantity = int(data.get("quantity", 1))
    payment_method = data.get("payment_method", "cash")
    selling_price_str = data.get("selling_price")

    selling_price = None
    if selling_price_str:
        try:
            selling_price = Decimal(str(selling_price_str))
        except:
            return JsonResponse({"ok": False, "error": "Invalid price"}, status=400)

    # If product_id is provided, create sale directly (fast cart checkout)
    if product_id:
        try:
            with transaction.atomic():
                product = MerchProduct.objects.select_for_update().get(
                    pk=product_id,
                    business=business,
                    kind=BusinessKind.CLOTHING,
                    is_active=True,
                )
                
                current_stock = product.quantity_in_stock or 0
                if current_stock < quantity:
                    return JsonResponse({
                        "ok": False,
                        "error": f"Insufficient stock. Only {current_stock} available."
                    }, status=400)
                
                # Use selling price from request or product default
                unit_price = selling_price if selling_price else (product.selling_price or Decimal("0.00"))
                unit_cost = product.cost_price or Decimal("0.00")
                total_price = unit_price * quantity
                total_cost = unit_cost * quantity
                
                # Decrease stock
                product.quantity_in_stock = current_stock - quantity
                product.save(update_fields=["quantity_in_stock"])
                
                # Normalize payment method
                payment_map = {
                    "cash": PaymentMethod.CASH,
                    "bank": PaymentMethod.BANK,
                    "mobile_money": PaymentMethod.MOBILE_MONEY,
                    "mobile": PaymentMethod.MOBILE_MONEY,
                }
                pm = payment_map.get(payment_method.lower(), PaymentMethod.CASH)
                
                # Create sale record
                sale = ClothingSale.objects.create(
                    business=business,
                    product=product,
                    quantity=quantity,
                    unit_price=unit_price,
                    total_price=total_price,
                    unit_cost=unit_cost,
                    total_cost=total_cost,
                    payment_method=pm,
                    sold_by=request.user,
                    notes="Fast Sell checkout",
                )
                
                profit = total_price - total_cost
                return JsonResponse({
                    "ok": True,
                    "sale_id": sale.id,
                    "message": f"Sold {quantity} × {product.name}",
                    "revenue": float(total_price),
                    "profit": float(profit),
                })
                
        except MerchProduct.DoesNotExist:
            return JsonResponse({"ok": False, "error": "Product not found"}, status=404)
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=500)
    
    # Otherwise use barcode flow (original behavior)
    if not barcode:
        return JsonResponse({"ok": False, "error": "Product ID or barcode required"}, status=400)

    result = create_fast_sell(
        business=business,
        vertical="clothing",
        user=request.user,
        barcode=barcode,
        quantity=quantity,
        payment_method=payment_method,
        selling_price=selling_price,
    )

    return JsonResponse(result)


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def fast_sell_create_product_api(request):
    """API: Create a product from fast sell (when barcode not found)"""
    from django.http import JsonResponse
    from inventory.services.products import create_or_update_clothing_product
    from django.core.exceptions import ValidationError
    import json

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    business = base.base_context(request).get("business")

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    # Extract product data
    name = data.get("name", "").strip()
    barcode = data.get("barcode", "").strip() or None  # None if empty
    category = data.get("category", "").strip() or None
    size = data.get("size", "").strip() or None
    color = data.get("color", "").strip() or None
    cost_price_str = data.get("cost_price", "")
    selling_price_str = data.get("selling_price", "")
    quantity = int(data.get("quantity", 1))

    # Validation
    if not name:
        return JsonResponse({"ok": False, "error": "Product name is required"}, status=400)

    if not selling_price_str:
        return JsonResponse({"ok": False, "error": "Selling price is required"}, status=400)

    # Parse prices
    try:
        selling_price = Decimal(str(selling_price_str))
        if selling_price <= 0:
            return JsonResponse({"ok": False, "error": "Selling price must be greater than 0"}, status=400)
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Invalid selling price"}, status=400)

    cost_price = None
    if cost_price_str:
        try:
            cost_price = Decimal(str(cost_price_str))
            if cost_price < 0:
                return JsonResponse({"ok": False, "error": "Cost price cannot be negative"}, status=400)
        except (ValueError, TypeError):
            return JsonResponse({"ok": False, "error": "Invalid cost price"}, status=400)

    # Create product
    try:
        product = create_or_update_clothing_product(
            business=business,
            name=name,
            barcode=barcode,  # None if not provided (allows products without barcode)
            category=category,
            size=size,
            color=color,
            cost_price=cost_price,
            selling_price=selling_price,
            quantity=quantity,
        )

        return JsonResponse(
            {
                "ok": True,
                "product": {
                    "id": product.id,
                    "name": product.name,
                    "barcode": product.barcode or "",
                    "category": product.category or "",
                    "size": getattr(product, "size", "") or "",
                    "color": getattr(product, "color", "") or "",
                },
                "stock_qty": product.quantity_in_stock or 0,
                "selling_price": float(selling_price),
                "message": f"Product '{name}' created successfully",
            }
        )

    except ValidationError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.exception(f"Error creating product in fast sell: {e}")
        return JsonResponse({"ok": False, "error": f"Error creating product: {str(e)}"}, status=500)


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def fast_sell_kpis_api(request):
    """API: Get Fast Sell KPIs"""
    from django.http import JsonResponse
    from inventory.services.fast_sell import get_fast_sell_kpis

    business = base.base_context(request).get("business")
    date_range = request.GET.get("range", "today")

    result = get_fast_sell_kpis(
        business=business,
        vertical="clothing",
        date_range=date_range,
    )

    return JsonResponse(result)


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def fast_sell_lookup_unified_api(request):
    """
    API: Unified lookup for Fast Sell - supports BOTH tracked units AND common stock.
    
    GET /verticals/clothing/api/fast-sell/lookup-unified/?code=XXXX
    
    Returns:
        - found: bool
        - kind: "tracked_unit" OR "common_item"
        - item: dict with product/unit details
        - error: str (if not found)
    """
    from django.http import JsonResponse
    from inventory.services.clothing_barcode_service import lookup_for_fast_sell_unified
    
    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")
    
    code = request.GET.get("code", "").strip()
    
    if not code:
        return JsonResponse({"ok": False, "found": False, "error": "Code required"}, status=400)
    
    result = lookup_for_fast_sell_unified(business=business, code=code, location=location)
    
    return JsonResponse({"ok": True, **result})


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def fast_sell_sell_unified_api(request):
    """
    API: Unified sell endpoint for Fast Sell - handles BOTH tracked units AND common stock.
    
    POST /verticals/clothing/api/fast-sell/sell-unified/
    
    Payload:
        - kind: "tracked_unit" OR "common_item"
        - tracked_unit_id: int (required if kind="tracked_unit")
        - product_id: int (required if kind="common_item")
        - quantity: int (optional, default 1, only used for common items)
        - payment_method: str (optional, default "cash")
    
    Returns:
        - ok: bool
        - sale_id: int (if ok)
        - message: str
        - error: str (if not ok)
    """
    from django.http import JsonResponse
    from django.db import transaction
    from inventory.services.clothing_barcode_service import create_fast_sell_unified
    import json
    
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)
    
    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")
    
    if not location:
        # Try to get default location
        from inventory.models import Location
        location = (
            Location.objects.filter(business=business, is_default=True).first()
            or Location.objects.filter(business=business).first()
        )
        if not location:
            return JsonResponse({"ok": False, "error": "No location found for this business"}, status=400)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
    
    kind = data.get("kind", "").strip()
    tracked_unit_id = data.get("tracked_unit_id")
    product_id = data.get("product_id")
    quantity = int(data.get("quantity", 1))
    payment_method = data.get("payment_method", "cash")
    
    # Validation
    if kind not in ("tracked_unit", "common_item"):
        return JsonResponse({"ok": False, "error": "Invalid kind. Must be 'tracked_unit' or 'common_item'"}, status=400)
    
    if kind == "tracked_unit" and not tracked_unit_id:
        return JsonResponse({"ok": False, "error": "tracked_unit_id required for tracked unit sale"}, status=400)
    
    if kind == "common_item" and not product_id:
        return JsonResponse({"ok": False, "error": "product_id required for common item sale"}, status=400)
    
    # Create sale
    result = create_fast_sell_unified(
        business=business,
        location=location,
        user=request.user,
        kind=kind,
        tracked_unit_id=tracked_unit_id,
        product_id=product_id,
        quantity=quantity,
        payment_method=payment_method,
    )
    
    if not result.get("ok"):
        return JsonResponse(result, status=400)
    
    return JsonResponse(result)


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def fast_sell_resolve_product_api(request):
    """
    API: Resolve next available tracked unit for a product (used when clicking product cards).
    
    GET /verticals/clothing/api/fast-sell/resolve-product/?product_id=X&size=Y&category=Z&brand=W
    
    Returns:
        - found: bool
        - unit: dict with tracked unit details (tracked_unit_id, barcode, etc.)
        - error: str (if not found)
    """
    from django.http import JsonResponse
    from inventory.models_clothing_barcode import ClothingBarcodeUnit
    
    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")
    
    product_id = request.GET.get("product_id", "").strip()
    size = request.GET.get("size", "").strip()
    category = request.GET.get("category", "").strip()
    brand = request.GET.get("brand", "").strip()
    
    if not product_id:
        return JsonResponse({"ok": False, "found": False, "error": "product_id required"}, status=400)
    
    # Build query for available tracked units matching the criteria
    query = ClothingBarcodeUnit.objects.filter(
        business=business,
        status="IN_STOCK",
        is_active=True,
    )
    
    # Filter by product if we have a valid product_id
    if product_id and product_id != "None":
        try:
            query = query.filter(product_id=int(product_id))
        except (ValueError, TypeError):
            pass
    
    # Additional filters for product attributes
    if size:
        query = query.filter(size=size)
    if category:
        query = query.filter(category=category)
    if brand:
        query = query.filter(brand=brand)
    
    # Apply location filter if available
    if location:
        query = query.filter(location=location)
    
    # Get next available unit (oldest first = FIFO)
    unit = query.order_by("created_at", "id").first()
    
    if not unit:
        return JsonResponse({
            "ok": True,
            "found": False,
            "error": "No available units found for this product"
        })
    
    # Build display name
    display_name = f"{unit.category.title() if unit.category else 'Item'} - Size {unit.size}"
    if unit.brand:
        display_name = f"{unit.brand} {display_name}"
    if unit.color:
        display_name = f"{display_name} ({unit.color})"
    
    return JsonResponse({
        "ok": True,
        "found": True,
        "unit": {
            "tracked_unit_id": unit.id,
            "barcode": unit.barcode,
            "name": display_name,
            "size": unit.size,
            "category": unit.category,
            "color": unit.color or "",
            "brand": unit.brand or "",
            "selling_price": float(unit.selling_price),
            "cost_price": float(unit.cost_price),
        }
    })


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def tracked_units_list(request, product_id):
    """
    Show tracked/barcoded units for a specific product.
    Accessible from Hub page when user clicks "Tracked (X units)" pill.
    """
    from inventory.models_clothing_barcode import ClothingBarcodeUnit
    
    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")
    
    # Get product
    try:
        product = MerchProduct.objects.get(
            pk=product_id,
            business=business,
            kind=BusinessKind.CLOTHING,
            is_active=True,
        )
    except MerchProduct.DoesNotExist:
        messages.error(request, "Product not found")
        return redirect("verticals:clothing_hub")
    
    # Filter by status (default: AVAILABLE)
    status_filter = request.GET.get("status", "available").lower()
    
    # Get tracked units
    units_query = ClothingBarcodeUnit.objects.filter(
        business=business,
        product=product,
        is_active=True,
    )
    
    if location:
        units_query = units_query.filter(location=location)
    
    if status_filter == "available":
        units_query = units_query.filter(status="IN_STOCK")
    elif status_filter == "sold":
        units_query = units_query.filter(status="SOLD")
    # "all" = no filter
    
    units = units_query.order_by("-created_at")
    
    # Stats
    total_units = ClothingBarcodeUnit.objects.filter(
        business=business,
        product=product,
        is_active=True,
    ).count()
    
    available_count = ClothingBarcodeUnit.objects.filter(
        business=business,
        product=product,
        status="IN_STOCK",
        is_active=True,
    ).count()
    
    sold_count = ClothingBarcodeUnit.objects.filter(
        business=business,
        product=product,
        status="SOLD",
        is_active=True,
    ).count()
    
    ctx.update({
        "product": product,
        "units": units,
        "status_filter": status_filter,
        "total_units": total_units,
        "available_count": available_count,
        "sold_count": sold_count,
        "page_title": f"Tracked Units - {product.name}",
        "active_tab": "hub",
    })
    
    return render(request, "verticals/clothing/tracked_units_list.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def sales_trend_json(request):
    """
    JSON endpoint for sales trend data.
    Respects dashboard date filters if provided.
    Returns data suitable for Chart.js or similar libraries.

    Uses the same queryset logic as clothing_sales_metrics to ensure consistency.
    """
    from django.http import JsonResponse
    from django.db.models.functions import TruncDate
    from django.db.models import Count, Sum

    business = base.base_context(request).get("business")
    location = base.base_context(request).get("location")

    # Parse date range from request
    date_range_ctx = base.parse_date_range_from_request(request)
    start_date = date_range_ctx["start_date"]
    end_date = date_range_ctx["end_date"]
    range_param = date_range_ctx["active_range"]

    # Build sales queryset using unified helper (same as clothing_sales_metrics)
    sales_qs = base.clothing_sales_queryset(
        business=business,
        location=location,
        start_date=start_date,
        end_date=end_date,
    )

    # DB-grouped-by-day using TruncDate (same logic as clothing_sales_metrics)
    from django.db.models.functions import TruncDate
    from django.db.models.functions import Coalesce

    daily_sales = (
        sales_qs.annotate(sale_date=TruncDate("sold_at"))
        .values("sale_date")
        .annotate(
            revenue=Coalesce(Sum("total_price"), base.DECIMAL_ZERO, output_field=base.DECIMAL_FIELD), count=Count("id")
        )
        .order_by("sale_date")
    )

    # Build dictionary for quick lookup
    sales_by_date = {}
    for day_data in daily_sales:
        sale_date = day_data["sale_date"]
        if sale_date:
            # Normalize to date for consistent key format across SQLite/Postgres
            if hasattr(sale_date, "date"):
                sale_date = sale_date.date()
            # Convert Decimal to float for JSON serialization
            revenue_value = float(day_data["revenue"] or Decimal("0.00"))
            sales_by_date[sale_date.isoformat()] = {"revenue": revenue_value, "count": day_data["count"] or 0}

    # Fill missing days in Python
    labels = []
    revenue_values = []
    count_values = []

    current_date = start_date
    while current_date < end_date:
        # Use strftime to get consistent date-only key (TruncDate returns date, not datetime)
        date_key = current_date.strftime("%Y-%m-%d")
        day_data = sales_by_date.get(date_key, {"revenue": 0.0, "count": 0})

        labels.append(current_date.strftime("%b %d"))
        revenue_values.append(day_data["revenue"])
        count_values.append(day_data["count"])

        current_date += timedelta(days=1)

    # Check if there's actual data (non-zero revenue or count)
    has_data = any(r > 0 for r in revenue_values) or any(c > 0 for c in count_values)

    # Return response with cache-busting metadata
    return JsonResponse(
        {
            "labels": labels,
            "revenue": revenue_values,
            "count": count_values,
            "has_data": has_data,
            "period": range_param,
            "start_date": start_date.isoformat(),
            "end_date": (end_date - timedelta(days=1)).isoformat(),
            "timestamp": timezone.now().isoformat(),
        }
    )


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def rollback_sale(request, sale_id):
    """
    Rollback/cancel a clothing sale and restore product inventory.
    Manager-only feature for correcting mistakes.
    """
    from django.http import JsonResponse
    from django.contrib import messages
    from django.shortcuts import redirect
    from django.db import transaction
    from core.context import _extract_roles_for

    ctx = base.base_context(request)
    business = ctx.get("business")

    # Check if user is manager
    roles = _extract_roles_for(request.user, business)
    if not roles.is_manager:
        if request.method == "POST":
            return JsonResponse({"ok": False, "error": "Only managers can rollback sales"}, status=403)
        messages.error(request, "Only managers can rollback sales")
        return redirect("verticals:clothing_sales_history")

    # Get the sale
    try:
        sale = ClothingSale.objects.get(id=sale_id, business=business)
    except ClothingSale.DoesNotExist:
        if request.method == "POST":
            return JsonResponse({"ok": False, "error": "Sale not found"}, status=404)
        messages.error(request, "Sale not found")
        return redirect("verticals:clothing_sales_history")

    # Check if already cancelled (if field exists)
    if hasattr(sale, "is_cancelled") and sale.is_cancelled:
        if request.method == "POST":
            return JsonResponse({"ok": False, "error": "Sale already cancelled"}, status=400)
        messages.error(request, "Sale already cancelled")
        return redirect("verticals:clothing_sales_history")

    if request.method == "POST":
        with transaction.atomic():
            # Restore product inventory
            product = sale.product
            product.quantity_in_stock += sale.quantity
            product.save(update_fields=["quantity_in_stock"])

            # Mark sale as cancelled (if field exists) or add note
            if hasattr(sale, "is_cancelled"):
                sale.is_cancelled = True
                sale.cancelled_at = timezone.now()
                sale.cancelled_by = request.user
                sale.save(update_fields=["is_cancelled", "cancelled_at", "cancelled_by"])
            else:
                # Fallback: soft delete by adding notes
                sale.notes = f"[CANCELLED by {request.user.username} on {timezone.now()}] {sale.notes}"
                sale.save(update_fields=["notes"])

        return JsonResponse({"ok": True, "message": f"Sale #{sale_id} rolled back successfully. Inventory restored."})

    # GET request: show confirmation
    messages.error(request, "Invalid request method")
    return redirect("verticals:clothing_sales_history")

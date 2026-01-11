# inventory/verticals/cement.py
"""
Cement / Hardware Vertical - Building materials and hardware store

SSOT: All product definitions come from inventory/catalog/construction_materials.py
"""
from __future__ import annotations

from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.catalog.construction_materials import (
    get_all_products,
    get_categories,
    get_cement_brands,
    get_paint_sizes,
    get_product_by_slug,
    build_product_name,
    normalize_paint_size,
    is_valid_paint_size,
)
from inventory.catalog.registry import (
    get_all_stock_in_categories,
    get_category_by_key,
    get_category_handler,
)
from inventory.catalog.hardware import (
    HARDWARE_CATEGORIES,
    get_catalog_products,
    get_popular_products,
    get_product_by_slug as get_hardware_product,
    get_products_by_category,
    search_products,
)
from inventory.cement_seed import get_cement_brands_list, seed_cement_defaults
from inventory.date_ranges import get_date_range_label, get_preset_options, parse_date_range
from inventory.helpers import get_active_business
from inventory.models import MerchProduct
from inventory.models_verticals import CementCost, CementSale, CementSaleUndo
from inventory.utils_product_variations import (
    get_unique_variations,
    group_products_by_base_name,
    should_use_variation_picker,
)
from tenants.utils import manager_required, require_business


@login_required
@require_business
@require_business_kind(BusinessKind.CEMENT)
def dashboard(request):
    """Cement/Hardware dashboard with KPIs, filters, payment mix, and top products"""
    business = get_active_business(request)

    # Seed default cement brands if this is first visit (idempotent)
    seed_result = seed_cement_defaults(business)

    # Get date range filters
    preset = request.GET.get("preset", "today")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    start_dt, end_dt = parse_date_range(preset, start_date, end_date)
    date_label = get_date_range_label(preset, start_date, end_date)

    # Get all cement/hardware products
    products = MerchProduct.objects.filter(business=business, kind=BusinessKind.CEMENT, is_active=True)

    # Calculate KPIs
    total_products = products.count()
    total_stock_value = sum((p.quantity_in_stock or 0) * (p.cost_price or Decimal("0")) for p in products)
    items_in_stock = sum(p.quantity_in_stock or 0 for p in products)

    # Sales data (exclude voided sales) - filter by date range
    sales_qs = CementSale.objects.filter(business=business, is_void=False)
    if start_dt and end_dt:
        sales_qs = sales_qs.filter(sold_at__gte=start_dt, sold_at__lte=end_dt)

    # Aggregate totals in database instead of Python iteration
    sales_aggregates = sales_qs.aggregate(
        total_revenue=Sum("total_price"),
        total_cost=Sum("total_cost"),
        total_count=Count("id"),
    )
    total_revenue = sales_aggregates["total_revenue"] or Decimal("0")
    total_profit = (sales_aggregates["total_revenue"] or Decimal("0")) - (
        sales_aggregates["total_cost"] or Decimal("0")
    )
    total_sales_count = sales_aggregates["total_count"] or 0

    # Payment mix (group by payment method)
    payment_mix = (
        sales_qs.values("payment_method")
        .annotate(
            total=Sum("total_price"),
            count=Count("id"),
        )
        .order_by("-total")
    )

    # Top products by revenue
    top_products_revenue = (
        sales_qs.values("product__name", "product__base_unit")
        .annotate(
            total_revenue=Sum("total_price"),
            total_quantity=Sum("quantity"),
        )
        .order_by("-total_revenue")[:10]
    )

    # Top products by quantity
    top_products_qty = (
        sales_qs.values("product__name", "product__base_unit")
        .annotate(
            total_quantity=Sum("quantity"),
            total_revenue=Sum("total_price"),
        )
        .order_by("-total_quantity")[:10]
    )

    # Costs data - filter by date range
    costs_qs = CementCost.objects.filter(business=business)
    if start_dt and end_dt:
        costs_qs = costs_qs.filter(cost_date__gte=start_dt.date(), cost_date__lte=end_dt.date())

    total_costs = costs_qs.aggregate(total=Coalesce(Sum("amount"), Decimal("0")))["total"]

    # Low stock items (less than 5 bags/units)
    low_stock_items = products.filter(quantity_in_stock__lt=5, quantity_in_stock__gt=0).order_by("quantity_in_stock")[
        :10
    ]

    # Recent sales (last 10)
    recent_sales = sales_qs.select_related("product", "sold_by").order_by("-sold_at")[:10]

    context = {
        "business": business,
        "total_revenue": total_revenue,
        "total_profit": total_profit,
        "total_costs": total_costs,
        "stock_value": total_stock_value,
        "total_sales_count": total_sales_count,
        "items_in_stock": items_in_stock,
        "total_products": total_products,
        "low_stock_items": low_stock_items,
        "recent_sales": recent_sales,
        "payment_mix": payment_mix,
        "top_products_revenue": top_products_revenue,
        "top_products_qty": top_products_qty,
        "active_tab": "dashboard",
        # Date filter context
        "preset": preset,
        "start_date": start_date,
        "end_date": end_date,
        "date_label": date_label,
        "preset_options": get_preset_options(),
    }

    # ===== PREMIUM: Personalized dashboard enhancements (quotes & greetings) =====
    ctx_enhancements = {}
    try:
        import json as json_lib

        from dashboard.helpers_greetings import get_personalized_greeting
        from dashboard.helpers_quotes import get_todays_quotes

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
                "DASHBOARD_BRAND_TITLE": business.name if business else "Cement Dashboard",
                "DASHBOARD_QUOTES": daily_quotes,
                "quotes_json": quotes_json_data,
            }
        )
    except Exception:
        # Gracefully degrade if helpers not available
        pass

    context.update(ctx_enhancements)

    # ===========================================================================
    # DASHBOARD SHELL CONFIG (migrated to shared template 2026-01-08)
    # ===========================================================================
    dashboard_config = {
        'vertical_title': 'Hardware & General Dealers',
        'vertical_subtitle': 'Track sales, inventory, and profits',
        'eyebrow_text': f'{business.name} · {date_label}',
        'hero_gradient_classes': 'linear-gradient(120deg,#92400e,#d97706)',  # Brown/amber gradient
        'hero_gradient_shadow': 'rgba(217,119,6,0.3)',
        'hero_primary_text_color': '#92400e',
        'primary_actions': [
            {
                'label': 'Stock In',
                'url': reverse('cement:stock_in'),
                'icon': 'bi-box-arrow-in-down',
                'style': 'primary'
            },
            {
                'label': 'Sell',
                'url': reverse('cement:sell'),
                'icon': 'bi-bag-check',
                'style': 'primary'
            },
            {
                'label': 'Products',
                'url': reverse('cement:products_catalog'),
                'icon': 'bi-box-seam',
                'style': 'ghost'
            },
        ],
        'show_date_filter': True,
        'date_filter_data': {
            'range_key': preset,
            'start_date': start_date,
            'end_date': end_date,
            'range_label': date_label,
        },
        'show_more_dropdown': True,
        'kpis': [
            {
                'title': 'Revenue',
                'icon': 'bi-cash-stack',
                'value': f'MK {total_revenue:,.0f}',
                'subtitle': f'{total_sales_count} sales',
                'color': '#3b82f6'
            },
            {
                'title': 'Profit',
                'icon': 'bi-graph-up',
                'value': f'MK {total_profit:,.0f}',
                'subtitle': f'{int((total_profit / total_revenue * 100) if total_revenue > 0 else 0)}% margin',
                'color': '#16a34a'
            },
            {
                'title': 'Stock Value',
                'icon': 'bi-box-seam',
                'value': f'MK {total_stock_value:,.0f}',
                'subtitle': f'{items_in_stock:,.0f} items',
                'color': '#f59e0b'
            },
            {
                'title': 'Costs',
                'icon': 'bi-receipt',
                'value': f'MK {total_costs:,.0f}',
                'subtitle': 'Operating expenses',
                'color': '#06b6d4'
            },
        ],
    }
    
    context['dashboard_config'] = dashboard_config

    # Normalize dashboard context: add lowercase aliases for UPPERCASE keys
    # and inject safe defaults for optional dashboard widgets
    try:
        from core.dashboard_context import normalize_dashboard_context
        context = normalize_dashboard_context(request, context)
    except Exception:
        pass  # Gracefully degrade if normalizer not available

    # FORENSIC: Add debug info for Phase A verification
    response = render(request, "verticals/cement/dashboard.html", context)

    # Add response headers for instant DevTools verification
    response["X-Template"] = "verticals/cement/dashboard.html"
    response["X-Cement-Premium"] = "v1"
    response["X-Business-Kind"] = getattr(business, "business_kind", "UNKNOWN")

    return response


@login_required
@require_business
@require_business_kind(BusinessKind.CEMENT)
def stock_list(request):
    """List all cement/hardware products"""
    business = get_active_business(request)

    products = MerchProduct.objects.filter(business=business, kind=BusinessKind.CEMENT, is_active=True).order_by("name")

    context = {
        "business": business,
        "products": products,
        "active_tab": "stock",
    }

    return render(request, "verticals/cement/stock_list.html", context)


@login_required
@require_business
@require_business_kind(BusinessKind.CEMENT)
def stock_in(request):
    """
    Card-based Stock-In wizard for cement/construction materials.
    
    Flow:
    Step 1: Category cards (Construction Materials, Welding Materials, Car Spares, etc.) - from catalog registry
    Step 2: Product cards (Cement, Paint, Iron Sheets, etc.)
    Step 3: Variant selection (Brand → Size → Finish/Color based on product)
    Step 4: Quantity & Pricing
    
    All product definitions come from SSOT: inventory/catalog/construction_materials.py
    All categories come from SSOT: inventory/catalog/registry.py
    """
    business = get_active_business(request)

    # Seed default cement brands if not already seeded (idempotent)
    seed_cement_defaults(business)

    # Step tracking
    step = request.GET.get("step", "1")

    if request.method == "POST":
        try:
            # Step 1: Category selection
            if step == "1":
                category = request.POST.get("category", "").strip()
                if not category:
                    messages.error(request, "Please select a category")
                    return redirect(f"{reverse('cement:stock_in')}?step=1")
                
                # Validate category exists in registry
                category_def = get_category_by_key(category)
                if not category_def:
                    messages.error(request, "Invalid category selected")
                    return redirect(f"{reverse('cement:stock_in')}?step=1")
                
                # Check if category handler is implemented
                handler = get_category_handler(category)
                if handler == "coming_soon":
                    messages.warning(
                        request,
                        f"⚠️ {category_def['label']} is coming soon! Stock-In flow not yet implemented."
                    )
                    return redirect(f"{reverse('cement:stock_in')}?step=1")
                
                # Store category in session for next step
                request.session["cement_stock_in_category"] = category
                return redirect(f"{reverse('cement:stock_in')}?step=2")

            # Step 2: Product selection
            elif step == "2":
                product_slug = request.POST.get("product", "").strip()
                if not product_slug:
                    messages.error(request, "Please select a product")
                    return redirect(f"{reverse('cement:stock_in')}?step=2")
                
                # Validate product exists in catalog
                product_def = get_product_by_slug(product_slug)
                if not product_def:
                    messages.error(request, "Invalid product selected")
                    return redirect(f"{reverse('cement:stock_in')}?step=2")
                
                # Store product slug in session
                request.session["cement_stock_in_product_slug"] = product_slug
                return redirect(f"{reverse('cement:stock_in')}?step=3")

            # Step 3: Variant selection (Brand → Size → Finish/Color)
            elif step == "3":
                product_slug = request.session.get("cement_stock_in_product_slug", "")
                product_def = get_product_by_slug(product_slug)
                
                if not product_def:
                    messages.error(request, "Product not found. Please start from Step 1.")
                    return redirect("cement:stock_in")
                
                # Extract variant selections
                brand = request.POST.get("brand", "").strip()
                size = request.POST.get("size", "").strip()
                finish = request.POST.get("finish", "").strip()
                color = request.POST.get("color", "").strip()
                gauge = request.POST.get("gauge", "").strip()
                dimension = request.POST.get("dimension", "").strip()
                
                # Validate required variants based on product
                if product_def.get("brands") and not brand:
                    messages.error(request, "Please select a brand")
                    return redirect(f"{reverse('cement:stock_in')}?step=3")
                
                if product_def.get("sizes") and not size:
                    messages.error(request, "Please select a size")
                    return redirect(f"{reverse('cement:stock_in')}?step=3")
                
                # Normalize paint size if needed (handles legacy 4L)
                if product_slug == "paint" and size:
                    size = normalize_paint_size(size)
                
                # Store variants in session
                request.session["cement_stock_in_brand"] = brand
                request.session["cement_stock_in_size"] = size
                request.session["cement_stock_in_finish"] = finish
                request.session["cement_stock_in_color"] = color
                request.session["cement_stock_in_gauge"] = gauge
                request.session["cement_stock_in_dimension"] = dimension
                
                return redirect(f"{reverse('cement:stock_in')}?step=4")

            # Step 4: Quantity and pricing
            elif step == "4":
                product_slug = request.session.get("cement_stock_in_product_slug", "")
                brand = request.session.get("cement_stock_in_brand", "")
                size = request.session.get("cement_stock_in_size", "")
                finish = request.session.get("cement_stock_in_finish", "")
                color = request.session.get("cement_stock_in_color", "")
                gauge = request.session.get("cement_stock_in_gauge", "")
                dimension = request.session.get("cement_stock_in_dimension", "")
                
                product_def = get_product_by_slug(product_slug)
                if not product_def:
                    messages.error(request, "Product not found. Please start from Step 1.")
                    return redirect("cement:stock_in")
                
                quantity = int(request.POST.get("quantity", 0))
                cost_price = Decimal(request.POST.get("cost_price", "0"))
                selling_price = Decimal(request.POST.get("selling_price", "0"))

                if quantity <= 0:
                    messages.error(request, "Quantity must be greater than 0")
                    return redirect(f"{reverse('cement:stock_in')}?step=4")

                if cost_price <= 0 or selling_price <= 0:
                    messages.error(request, "Cost and selling prices must be greater than 0")
                    return redirect(f"{reverse('cement:stock_in')}?step=4")

                with transaction.atomic():
                    # Build product name using SSOT
                    product_name = build_product_name(
                        product_slug,
                        brand=brand,
                        size=size,
                        finish=finish,
                        color=color,
                        gauge=gauge,
                        dimension=dimension,
                    )
                    
                    # Get or create product
                    product, created = MerchProduct.objects.get_or_create(
                        business=business,
                        name=product_name,
                        kind=BusinessKind.CEMENT,
                        defaults={
                            "category": product_def["category"],
                            "spec_label": "",  # CRITICAL: Always set spec_label (prevents NULL constraint)
                            "cost_price": cost_price,
                            "selling_price": selling_price,
                            "quantity_in_stock": quantity,
                            "base_unit": product_def["default_unit"],
                            "is_active": True,
                            "track_inventory": True,
                        },
                    )

                    if not created:
                        # Update existing product
                        product.quantity_in_stock += quantity
                        product.cost_price = cost_price
                        product.selling_price = selling_price
                        product.save(update_fields=["quantity_in_stock", "cost_price", "selling_price"])

                    messages.success(
                        request,
                        f"✅ Added {quantity} {product_def['default_unit']} of {product_name} to stock"
                    )

                    # Clear session
                    for key in [
                        "cement_stock_in_category",
                        "cement_stock_in_product_slug",
                        "cement_stock_in_brand",
                        "cement_stock_in_size",
                        "cement_stock_in_finish",
                        "cement_stock_in_color",
                        "cement_stock_in_gauge",
                        "cement_stock_in_dimension",
                    ]:
                        if key in request.session:
                            del request.session[key]

                    return redirect("cement:stock_in")

        except (ValueError, TypeError) as e:
            messages.error(request, f"Invalid input: {e}")
            return redirect(f"{reverse('cement:stock_in')}?step={step}")
        except Exception as e:
            messages.error(request, f"Error adding stock: {e}")
            return redirect(f"{reverse('cement:stock_in')}?step={step}")

    # GET: Show appropriate step
    context = {
        "business": business,
        "step": step,
        "active_tab": "stock_in",
    }

    # Step 1: Show category cards from catalog registry
    if step == "1":
        categories = get_all_stock_in_categories()
        context["categories"] = categories

    # Step 2: Show product cards for selected category
    elif step == "2":
        category = request.session.get("cement_stock_in_category", "")
        products = get_all_products()  # Get all construction products
        context["selected_category"] = category
        context["products"] = products

    # Step 3: Show variant selection for selected product
    elif step == "3":
        product_slug = request.session.get("cement_stock_in_product_slug", "")
        product_def = get_product_by_slug(product_slug)
        
        if not product_def:
            messages.error(request, "Product not found. Please start from Step 1.")
            return redirect("cement:stock_in")
        
        context["product_def"] = product_def
        context["selected_product_slug"] = product_slug

    # Step 4: Show quantity/pricing form
    elif step == "4":
        product_slug = request.session.get("cement_stock_in_product_slug", "")
        brand = request.session.get("cement_stock_in_brand", "")
        size = request.session.get("cement_stock_in_size", "")
        finish = request.session.get("cement_stock_in_finish", "")
        color = request.session.get("cement_stock_in_color", "")
        gauge = request.session.get("cement_stock_in_gauge", "")
        dimension = request.session.get("cement_stock_in_dimension", "")
        
        product_def = get_product_by_slug(product_slug)
        if not product_def:
            messages.error(request, "Product not found. Please start from Step 1.")
            return redirect("cement:stock_in")
        
        # Build suggested product name
        suggested_name = build_product_name(
            product_slug,
            brand=brand,
            size=size,
            finish=finish,
            color=color,
            gauge=gauge,
            dimension=dimension,
        )
        
        context["product_def"] = product_def
        context["suggested_name"] = suggested_name
        context["selected_brand"] = brand
        context["selected_size"] = size
        context["selected_finish"] = finish
        context["selected_color"] = color
        context["selected_gauge"] = gauge
        context["selected_dimension"] = dimension

    return render(request, "verticals/cement/stock_in_v2.html", context)


@login_required
@require_business
@require_business_kind(BusinessKind.CEMENT)
def sell(request):
    """Gamified sell flow for cement: Brand → Product → Quantity → Payment"""
    business = get_active_business(request)

    step = request.GET.get("step", "1")

    if request.method == "POST":
        try:
            # Step 1: Brand selection
            if step == "1":
                brand = request.POST.get("brand", "").strip()
                if not brand:
                    messages.error(request, "Please select a brand")
                    return redirect(f"{reverse('cement:sell')}?step=1")
                request.session["cement_sell_brand"] = brand
                return redirect(f"{reverse('cement:sell')}?step=2")

            # Step 2: Product selection
            elif step == "2":
                product_id = int(request.POST.get("product_id", 0))
                if not product_id:
                    messages.error(request, "Please select a product")
                    return redirect(f"{reverse('cement:sell')}?step=2")
                request.session["cement_sell_product_id"] = product_id
                return redirect(f"{reverse('cement:sell')}?step=3")

            # Step 3: Quantity and payment
            elif step == "3":
                product_id = request.session.get("cement_sell_product_id")
                if not product_id:
                    messages.error(request, "Please start from Step 1")
                    return redirect("cement:sell")

                quantity = int(request.POST.get("quantity", 0))
                payment_method = request.POST.get("payment_method", "CASH")

                if quantity <= 0:
                    messages.error(request, "Quantity must be greater than 0")
                    return redirect(f"{reverse('cement:sell')}?step=3")

                product = MerchProduct.objects.select_for_update().get(
                    pk=product_id, business=business, kind=BusinessKind.CEMENT, is_active=True
                )

                if product.quantity_in_stock < quantity:
                    messages.error(
                        request, f"Insufficient stock. Available: {product.quantity_in_stock}, Requested: {quantity}"
                    )
                    return redirect(f"{reverse('cement:sell')}?step=3")

                with transaction.atomic():
                    # Calculate totals
                    unit_cost = product.cost_price or Decimal("0")
                    unit_price = product.selling_price or Decimal("0")
                    total_cost = unit_cost * quantity
                    total_revenue = unit_price * quantity
                    profit = total_revenue - total_cost

                    # Decrease stock
                    product.quantity_in_stock -= quantity
                    product.save(update_fields=["quantity_in_stock"])

                    # Create sale record
                    CementSale.objects.create(
                        business=business,
                        product=product,
                        quantity=quantity,
                        unit_price=unit_price,
                        total_price=total_revenue,
                        unit_cost=unit_cost,
                        total_cost=total_cost,
                        payment_method=payment_method,
                        sold_by=request.user,
                        notes=request.POST.get("notes", ""),
                    )

                    # Clear session
                    for key in ["cement_sell_brand", "cement_sell_product_id"]:
                        if key in request.session:
                            del request.session[key]

                    messages.success(
                        request,
                        f"✅ Sold {quantity} {product.base_unit} of {product.name}. "
                        f"Revenue: MK {total_revenue:,.2f}, Profit: MK {profit:,.2f}",
                    )
                    return redirect("cement:sell")

        except MerchProduct.DoesNotExist:
            messages.error(request, "Product not found")
            return redirect("cement:sell")
        except (ValueError, TypeError) as e:
            messages.error(request, f"Invalid input: {e}")
            return redirect(f"{reverse('cement:sell')}?step={step}")
        except Exception as e:
            messages.error(request, f"Error processing sale: {e}")
            return redirect(f"{reverse('cement:sell')}?step={step}")

    # GET: Show appropriate step
    # Get all cement brands with stock
    in_stock_products = MerchProduct.objects.filter(
        business=business, kind=BusinessKind.CEMENT, is_active=True, quantity_in_stock__gt=0
    ).values_list("name", flat=True)

    # Use seeded brands list
    seed_brands = get_cement_brands_list()

    # Extract custom brands from in-stock products (not in seed list)
    seed_names_lower = [b["name"].lower() for b in seed_brands]
    custom_brands = set()
    for name in in_stock_products:
        # Extract brand from "Brand - Product" format or use full name
        brand_name = name.split(" - ")[0] if " - " in name else name
        if brand_name.lower() not in seed_names_lower:
            custom_brands.add(brand_name)

    # Filter seed brands to only show those with stock
    available_seed_brands = []
    for brand in seed_brands:
        # Check if any product with this brand name (or starting with it) has stock
        has_stock = MerchProduct.objects.filter(
            business=business,
            kind=BusinessKind.CEMENT,
            is_active=True,
            quantity_in_stock__gt=0,
            name__istartswith=brand["name"],
        ).exists()
        if has_stock:
            available_seed_brands.append(brand)

    # Combine available seeded + custom brands
    all_brands = available_seed_brands + [
        {"key": b.lower().replace(" ", "_"), "name": b, "icon": "📦"} for b in custom_brands
    ]

    context = {
        "business": business,
        "step": step,
        "brands": all_brands,
        "active_tab": "sell",
    }

    # Step 2: Show products for selected brand
    if step == "2":
        brand = request.session.get("cement_sell_brand", "")
        if brand:
            products = MerchProduct.objects.filter(
                business=business,
                kind=BusinessKind.CEMENT,
                is_active=True,
                quantity_in_stock__gt=0,
                name__istartswith=brand,
            ).order_by("name")
            context["selected_brand"] = brand
            context["products"] = products

    # Step 3: Show quantity/payment form
    elif step == "3":
        product_id = request.session.get("cement_sell_product_id")
        if product_id:
            try:
                product = MerchProduct.objects.get(pk=product_id, business=business)
                context["selected_product"] = product
            except MerchProduct.DoesNotExist:
                messages.error(request, "Product not found")
                return redirect(f"{reverse('cement:sell')}?step=2")

    return render(request, "verticals/cement/sell.html", context)


@login_required
@require_business
@require_business_kind(BusinessKind.CEMENT)
def costs(request):
    """Manage costs for cement business (transport, labor, rent, utilities, etc.)"""
    business = get_active_business(request)
    location = getattr(request.user, "agent_profile", None)
    if location:
        location = location.location

    if request.method == "POST":
        try:
            amount = Decimal(request.POST.get("amount", "0"))
            category = request.POST.get("category", "other").strip()
            description = request.POST.get("description", "").strip()
            cost_date = request.POST.get("cost_date", "")
            notes = request.POST.get("notes", "").strip()

            if amount <= 0:
                messages.error(request, "Amount must be greater than 0")
                return redirect("cement:costs")

            if not description:
                messages.error(request, "Description is required")
                return redirect("cement:costs")

            from django.utils.dateparse import parse_date

            cost_date_obj = parse_date(cost_date) if cost_date else timezone.now().date()

            with transaction.atomic():
                CementCost.objects.create(
                    business=business,
                    location=location,
                    amount=amount,
                    category=category,
                    description=description,
                    cost_date=cost_date_obj,
                    notes=notes,
                    created_by=request.user,
                )

                messages.success(request, f"✅ Cost entry added: {description} - MK {amount:,.2f}")
                return redirect("cement:costs")

        except (ValueError, TypeError) as e:
            messages.error(request, f"Invalid input: {e}")
            return redirect("cement:costs")
        except Exception as e:
            messages.error(request, f"Error adding cost: {e}")
            return redirect("cement:costs")

    # GET: Show costs list and form
    costs_list = CementCost.objects.filter(business=business).order_by("-cost_date", "-created_at")[:50]

    # Calculate totals by category
    category_totals = (
        CementCost.objects.filter(business=business).values("category").annotate(total=Sum("amount")).order_by("-total")
    )

    # Total costs
    total_costs = CementCost.objects.filter(business=business).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    categories = [
        ("transport", "Transport"),
        ("labor", "Labor"),
        ("rent", "Rent"),
        ("utilities", "Utilities"),
        ("other", "Other"),
    ]

    context = {
        "business": business,
        "costs": costs_list,
        "category_totals": category_totals,
        "total_costs": total_costs,
        "categories": categories,
        "active_tab": "costs",
    }

    return render(request, "verticals/cement/costs.html", context)


@login_required
@require_business
@require_business_kind(BusinessKind.CEMENT)
def analytics(request):
    """Comprehensive analytics for cement/hardware with date filters"""
    business = get_active_business(request)

    # Get date range filters
    preset = request.GET.get("preset", "mtd")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    start_dt, end_dt = parse_date_range(preset, start_date, end_date)
    date_label = get_date_range_label(preset, start_date, end_date)

    products = MerchProduct.objects.filter(business=business, kind=BusinessKind.CEMENT, is_active=True)

    # Basic stats
    total_products = products.count()
    total_stock_value = sum((p.quantity_in_stock or 0) * (p.cost_price or Decimal("0")) for p in products)

    # Sales stats (exclude voided sales) - filter by date range
    sales_qs = CementSale.objects.filter(business=business, is_void=False)
    if start_dt and end_dt:
        sales_qs = sales_qs.filter(sold_at__gte=start_dt, sold_at__lte=end_dt)

    sales_aggregates = sales_qs.aggregate(
        total_revenue=Sum("total_price"),
        total_cost=Sum("total_cost"),
        total_count=Count("id"),
    )
    total_revenue = sales_aggregates["total_revenue"] or Decimal("0")
    total_cogs = sales_aggregates["total_cost"] or Decimal("0")
    total_profit = total_revenue - total_cogs
    total_sales_count = sales_aggregates["total_count"] or 0

    # Gross margin percentage
    gross_margin_pct = (total_profit / total_revenue * 100) if total_revenue > 0 else Decimal("0")

    # Sales by payment method
    sales_by_payment = (
        sales_qs.values("payment_method")
        .annotate(
            total=Sum("total_price"),
            count=Count("id"),
        )
        .order_by("-total")
    )

    # Sales by product category
    sales_by_category = (
        sales_qs.values("product__category")
        .annotate(
            total_revenue=Sum("total_price"),
            total_quantity=Sum("quantity"),
            count=Count("id"),
        )
        .order_by("-total_revenue")
    )

    # Top 20 products by revenue
    top_products = (
        sales_qs.values("product__name", "product__base_unit", "product__category")
        .annotate(
            total_revenue=Sum("total_price"),
            total_profit=Sum("total_price") - Sum("total_cost"),
            total_quantity=Sum("quantity"),
            sales_count=Count("id"),
        )
        .order_by("-total_revenue")[:20]
    )

    # Costs stats - filter by date range
    costs_qs = CementCost.objects.filter(business=business)
    if start_dt and end_dt:
        costs_qs = costs_qs.filter(cost_date__gte=start_dt.date(), cost_date__lte=end_dt.date())

    total_costs = costs_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0")

    # Costs by category
    costs_by_category = costs_qs.values("category").annotate(total=Sum("amount"), count=Count("id")).order_by("-total")

    # Net profit (gross profit - operating costs)
    net_profit = total_profit - total_costs

    # Daily sales trend (last 30 days or within date range)
    if start_dt and end_dt:
        trend_sales = (
            sales_qs.extra(select={"day": "DATE(sold_at)"})
            .values("day")
            .annotate(
                daily_revenue=Sum("total_price"),
                daily_profit=Sum("total_price") - Sum("total_cost"),
                daily_count=Count("id"),
            )
            .order_by("day")
        )
    else:
        # Default to last 30 days
        thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
        trend_sales = (
            CementSale.objects.filter(business=business, is_void=False, sold_at__gte=thirty_days_ago)
            .extra(select={"day": "DATE(sold_at)"})
            .values("day")
            .annotate(
                daily_revenue=Sum("total_price"),
                daily_profit=Sum("total_price") - Sum("total_cost"),
                daily_count=Count("id"),
            )
            .order_by("day")
        )

    context = {
        "business": business,
        "total_products": total_products,
        "total_stock_value": total_stock_value,
        "total_revenue": total_revenue,
        "total_cogs": total_cogs,
        "total_profit": total_profit,
        "total_costs": total_costs,
        "net_profit": net_profit,
        "total_sales_count": total_sales_count,
        "gross_margin_pct": gross_margin_pct,
        "sales_by_payment": sales_by_payment,
        "sales_by_category": sales_by_category,
        "top_products": top_products,
        "costs_by_category": costs_by_category,
        "trend_sales": trend_sales,
        "active_tab": "analytics",
        # Date filter context
        "preset": preset,
        "start_date": start_date,
        "end_date": end_date,
        "date_label": date_label,
        "preset_options": get_preset_options(),
    }

    return render(request, "verticals/cement/analytics.html", context)


@login_required
@require_business
@require_business_kind(BusinessKind.CEMENT)
@manager_required
def undo_sale(request, sale_id: int):
    """
    Undo/rollback a cement sale (manager only).
    Restores stock, marks sale as void, creates audit trail.
    Only allowed within 7 days of sale.
    """
    business = get_active_business(request)

    try:
        sale = CementSale.objects.select_related("product").get(
            pk=sale_id,
            business=business,
        )
    except CementSale.DoesNotExist:
        messages.error(request, "Sale not found")
        return redirect("cement:dashboard")

    # Check if already undone
    if sale.is_void:
        messages.error(request, "This sale has already been undone")
        return redirect("cement:dashboard")

    # Check if undo record exists
    if hasattr(sale, "undo_record"):
        messages.error(request, "This sale has already been undone")
        return redirect("cement:dashboard")

    # Check if sale is within allowed time window (7 days)
    days_since_sale = (timezone.now() - sale.sold_at).days
    if days_since_sale > 7:
        messages.error(request, f"Cannot undo sales older than 7 days (this sale is {days_since_sale} days old)")
        return redirect("cement:dashboard")

    if request.method == "POST":
        reason = request.POST.get("reason", "").strip()

        try:
            with transaction.atomic():
                # Restore stock quantity
                product = MerchProduct.objects.select_for_update().get(pk=sale.product.pk)
                product.quantity_in_stock += sale.quantity
                product.save(update_fields=["quantity_in_stock"])

                # Mark sale as void
                sale.is_void = True
                sale.save(update_fields=["is_void"])

                # Create undo record (audit trail)
                CementSaleUndo.objects.create(
                    sale=sale,
                    business=business,
                    undone_by=request.user,
                    reason=reason,
                    original_quantity=sale.quantity,
                    original_total_price=sale.total_price,
                    original_product_name=sale.product.name,
                )

                messages.success(
                    request,
                    f"✅ Sale undone: {sale.quantity} {sale.product.base_unit} of {sale.product.name} "
                    f"restored to stock. Amount: MK {sale.total_price:,.2f}",
                )
                return redirect("cement:dashboard")

        except Exception as e:
            messages.error(request, f"Error undoing sale: {e}")
            return redirect("cement:dashboard")

    # GET: Show confirmation form
    context = {
        "business": business,
        "sale": sale,
        "days_since_sale": days_since_sale,
        "active_tab": "dashboard",
    }

    return render(request, "verticals/cement/undo_sale_confirm.html", context)


# ============================================================
# HARDWARE PRODUCT CATALOG (PREMIUM FEATURE)
# ============================================================
@login_required
@require_business
@require_business_kind(BusinessKind.CEMENT)
def products_catalog(request):
    """
    Hardware Product Catalog - Category-based, searchable, no duplicates.
    
    Handles legacy paint size URLs (4L → 5L redirect).

    Features:
    - Category chips for filtering
    - Search by product name + keywords
    - Popular items section (top 12)
    - List results grouped by category (collapsible)
    """
    business = get_active_business(request)

    # Handle legacy paint size (4L → 5L)
    size_param = request.GET.get("size", "")
    if size_param and not is_valid_paint_size(size_param):
        # Invalid size, redirect to catalog home
        return redirect("cement:products_catalog")
    
    if size_param in ["4L", "4l"]:
        # Legacy 4L paint size - redirect to 5L
        new_params = request.GET.copy()
        new_params["size"] = "5L"
        redirect_url = f"{reverse('cement:products_catalog')}?{new_params.urlencode()}"
        return redirect(redirect_url)

    # Get search query and category filter
    search_query = request.GET.get("q", "").strip()
    category_filter = request.GET.get("category", "").strip()

    # Get all products (filtered by search/category)
    if search_query:
        products = search_products(search_query)
    elif category_filter:
        products = get_products_by_category(category_filter)
    else:
        products = get_catalog_products()

    # Get popular products (for quick access section)
    popular_products = get_popular_products(limit=12)

    # Group products by category for display
    products_by_category = {}
    for product in products:
        cat = product["category"]
        if cat not in products_by_category:
            products_by_category[cat] = []
        products_by_category[cat].append(product)

    # Get category display names
    category_map = {cat["slug"]: cat["name"] for cat in HARDWARE_CATEGORIES}

    context = {
        "business": business,
        "categories": HARDWARE_CATEGORIES,
        "products": products,
        "products_by_category": products_by_category,
        "category_map": category_map,
        "popular_products": popular_products,
        "search_query": search_query,
        "category_filter": category_filter,
        "active_tab": "products",
    }

    return render(request, "verticals/cement/products_catalog.html", context)


@login_required
@require_business
@require_business_kind(BusinessKind.CEMENT)
def product_detail(request, slug: str):
    """
    Product detail page with variation picker.
    
    Handles legacy paint size URLs (4L → 5L redirect).

    Flow:
    1. Show base product info
    2. Step-by-step variation selection (brand → size → color/finish)
    3. "Add to Inventory" button → redirects to stock-in with prefilled data
    """
    business = get_active_business(request)

    # Handle legacy paint size (4L → 5L)
    size_param = request.GET.get("size", "")
    if slug == "paint" and size_param in ["4L", "4l"]:
        # Legacy 4L paint size - redirect to 5L
        new_params = request.GET.copy()
        new_params["size"] = "5L"
        redirect_url = f"{reverse('cement:product_detail', args=[slug])}?{new_params.urlencode()}"
        return redirect(redirect_url)

    # Get product from catalog
    product = get_hardware_product(slug)
    if not product:
        raise Http404("Product not found in catalog")

    # Get category display name
    category_map = {cat["slug"]: cat["name"] for cat in HARDWARE_CATEGORIES}
    category_name = category_map.get(product["category"], product["category"])

    # Extract variation schema
    variation_schema = product["variation_schema"]

    # Get selected variations from query params (for multi-step selection)
    selected_brand = request.GET.get("brand", "")
    selected_size = request.GET.get("size", "")
    selected_color = request.GET.get("color", "")
    selected_finish = request.GET.get("finish", "")
    selected_dimension = request.GET.get("dimension", "")
    selected_viscosity = request.GET.get("viscosity", "")
    selected_gauge = request.GET.get("gauge", "")
    
    # Normalize paint size if needed
    if slug == "paint" and selected_size:
        selected_size = normalize_paint_size(selected_size)

    # Build suggested product name based on selections
    suggested_name_parts = [product["base_name"]]
    if selected_brand:
        suggested_name_parts.append(selected_brand)
    if selected_size:
        suggested_name_parts.append(selected_size)
    if selected_dimension:
        suggested_name_parts.append(selected_dimension)
    if selected_viscosity:
        suggested_name_parts.append(selected_viscosity)
    if selected_gauge:
        suggested_name_parts.append(f"Gauge {selected_gauge}")
    if selected_finish:
        suggested_name_parts.append(selected_finish)
    if selected_color:
        suggested_name_parts.append(selected_color)

    suggested_name = " — ".join(suggested_name_parts)

    context = {
        "business": business,
        "product": product,
        "category_name": category_name,
        "variation_schema": variation_schema,
        "selected_brand": selected_brand,
        "selected_size": selected_size,
        "selected_color": selected_color,
        "selected_finish": selected_finish,
        "selected_dimension": selected_dimension,
        "selected_viscosity": selected_viscosity,
        "selected_gauge": selected_gauge,
        "suggested_name": suggested_name,
        "active_tab": "products",
    }

    return render(request, "verticals/cement/product_detail.html", context)

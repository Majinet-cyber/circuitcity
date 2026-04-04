# inventory/verticals/cement.py
"""
Cement / Hardware Vertical - Building materials and hardware store

SSOT: All product definitions come from inventory/catalog/construction_materials.py
"""
from __future__ import annotations

from decimal import Decimal
import re
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
    STOCK_IN_CATEGORIES,
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


def normalize_label(value: str) -> str:
    """Normalize labels by replacing separators, collapsing whitespace, and title-casing."""
    if not value:
        return ""
    cleaned = re.sub(r"[_-]+", " ", str(value))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.title()


def infer_brand_from_name(name: str) -> str:
    """Infer cement brand from product name using 'Brand Cement' or first token fallback."""
    if not name:
        return ""
    cleaned = re.sub(r"[_-]+", " ", str(name))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    lowered = cleaned.lower()
    cement_index = lowered.find(" cement")
    if cement_index != -1:
        brand_chunk = cleaned[:cement_index].strip()
        if brand_chunk:
            return normalize_label(brand_chunk)
    tokens = cleaned.split()
    return normalize_label(tokens[0] if tokens else cleaned)


def _has_unit_markers(name: str) -> bool:
    lowered = (name or "").lower()
    if re.search(r"\d", lowered):
        return True
    markers = ("kg", "bag", "bags", "pack", "tin", "sheet", "sheets", "mm", "cm", "m", "l", "litre", "liter")
    return any(marker in lowered for marker in markers) or ("(" in lowered and ")" in lowered)


def get_brand_label_for_product(product: MerchProduct) -> str:
    brand_value = getattr(product, "brand", "").strip()
    return normalize_label(brand_value) if brand_value else infer_brand_from_name(product.name)


def is_placeholder_product(product: MerchProduct) -> bool:
    """Exclude placeholder brand rows that shouldn't appear in cement UI."""
    name = (product.name or "").strip()
    if not name:
        return True
    inferred_brand = get_brand_label_for_product(product)
    if not inferred_brand:
        return False
    if normalize_label(name) != normalize_label(inferred_brand):
        return False
    has_variant_markers = _has_unit_markers(name) or bool(product.base_unit) or bool(product.pack_size) or bool(
        product.spec_label
    )
    has_stock_data = any(
        [
            (product.quantity_in_stock or 0) > 0,
            (product.cost_price or Decimal("0")) > 0,
            (product.selling_price or Decimal("0")) > 0,
        ]
    )
    return (not has_variant_markers) or (not has_stock_data)


def build_unit_label(product: MerchProduct) -> str:
    unit = (product.base_unit or "").strip()
    pack_size = product.pack_size
    if pack_size and unit:
        return f"{unit.upper()} {pack_size}KG"
    spec = (product.spec_label or "").strip()
    if spec:
        return spec
    return unit.upper() if unit else "Unit"


def build_cement_brand_choices(business, in_stock_only: bool = True) -> list[dict]:
    """
    Build list of cement brands from stocked products.
    
    FIX (Jan 2026): Filter out generic "Cement" placeholder entries.
    Only show actual brand names like "Dangote", "Akshar", etc.
    """
    products = MerchProduct.objects.filter(business=business, kind=BusinessKind.CEMENT, is_active=True)
    if in_stock_only:
        products = products.filter(quantity_in_stock__gt=0)
    products = [p for p in products if not is_placeholder_product(p)]
    brand_icon_map = {
        normalize_label(b["name"]).lower(): b.get("icon", "🏗️") for b in get_cement_brands_list()
    }
    
    # Generic/placeholder brand names to exclude
    EXCLUDED_BRANDS = {"cement", "cements", "construction", "materials", "general", "other"}
    
    seen = {}
    for product in products:
        label = get_brand_label_for_product(product)
        if not label:
            continue
        # FIX: Skip generic placeholder brand names
        if label.lower() in EXCLUDED_BRANDS:
            continue
        key = label.lower().replace(" ", "_")
        if key not in seen:
            seen[key] = {
                "key": key,
                "name": label,
                "icon": brand_icon_map.get(label.lower(), "📦"),
            }
    return list(seen.values())


def get_filtered_stock_in_categories(business) -> list[dict]:
    """
    Return all enabled stock-in categories for the hardware/cement vertical.

    All registered categories are shown so users can stock any hardware product type
    without needing to have pre-existing products for that category.
    Categories that have products already stocked are marked with a badge count.
    """
    from inventory.catalog.registry import get_all_stock_in_categories

    all_cats = get_all_stock_in_categories()

    # Compute a stock count per category key for the badge display
    products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.CEMENT,
        is_active=True,
    ).values("category", "quantity_in_stock")

    # Map DB categories → registry keys (many-to-one)
    db_to_registry: dict[str, str] = {
        "cement": "construction-materials",
        "construction-materials": "construction-materials",
        "paint": "paint-and-finishing",
        "paint-and-finishing": "paint-and-finishing",
        "plumbing": "plumbing-supplies",
        "plumbing-supplies": "plumbing-supplies",
        "electrical": "electrical-supplies",
        "electrical-supplies": "electrical-supplies",
        "tools": "tools-and-hardware",
        "tools-and-hardware": "tools-and-hardware",
        "roofing": "roofing-materials",
        "roofing-materials": "roofing-materials",
        "iron-sheets": "roofing-materials",
        "angle-iron": "construction-materials",
        "fasteners": "fasteners-and-fixings",
        "fasteners-and-fixings": "fasteners-and-fixings",
        "welding-materials": "welding-materials",
        "welding": "welding-materials",
        "adhesives": "adhesives-and-sealants",
        "adhesives-and-sealants": "adhesives-and-sealants",
        "car-spares": "car-spares",
        "automotive": "car-spares",
    }

    stock_counts: dict[str, int] = {}
    for row in products:
        raw_cat = (row["category"] or "").strip().lower()
        reg_key = db_to_registry.get(raw_cat, "construction-materials")
        stock_counts[reg_key] = stock_counts.get(reg_key, 0) + (row["quantity_in_stock"] or 0)

    # Annotate each category with a stock count badge
    annotated = []
    for cat in all_cats:
        entry = dict(cat)
        entry["stock_count"] = stock_counts.get(cat["key"], 0)
        annotated.append(entry)

    return annotated


def is_cement_product(product_slug: str) -> bool:
    """Check if a product slug is cement (for skip-variant logic)."""
    return product_slug == "cement"


def get_cement_default_variant() -> dict:
    """Get the default cement variant (BAG 50KG) - used to skip variant step."""
    return {
        "brand": None,  # Brand still required
        "size": "50kg",
        "size_label": "BAG (50KG)",
    }


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
        'hero_gradient_classes': 'linear-gradient(135deg,#0ea5e9 0%,#38bdf8 50%,#60a5fa 100%)',  # Blue gradient like clothing
        'hero_gradient_shadow': 'rgba(14,165,233,0.2)',
        'hero_primary_text_color': '#0284c7',
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
    
    # Add border_style to each KPI card for template compatibility
    def _kpi_border_style(color_hex: str) -> str:
        """Generate subtle premium border style from color hex.
        
        Uses 20% opacity (0x33) to create glass-morphic effect consistent
        with cement vertical's premium UI theme.
        """
        return f"border: 1px solid {color_hex}33;"
    
    for kpi in dashboard_config['kpis']:
        kpi['border_style'] = _kpi_border_style(kpi['color'])
    
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
    """List all cement/hardware products with premium KPIs"""
    business = get_active_business(request)

    products_qs = MerchProduct.objects.filter(business=business, kind=BusinessKind.CEMENT, is_active=True).order_by(
        "name"
    )
    products = []
    healthy_count = 0
    low_stock_items = []
    out_of_stock_items = []
    total_units = 0
    total_stock_value = Decimal("0")
    total_potential_profit = Decimal("0")
    
    for product in products_qs:
        if is_placeholder_product(product):
            continue
        product.display_name = normalize_label(product.name) if any(c in product.name for c in "_-") else product.name
        product.unit_label = build_unit_label(product)
        product.brand_label = get_brand_label_for_product(product)
        product.brand_key = product.brand_label.lower().replace(" ", "_") if product.brand_label else ""
        qty = product.quantity_in_stock or 0
        total_units += qty
        
        if qty <= 0:
            product.stock_badge_label = "Out of stock"
            product.stock_badge_class = "danger"
            out_of_stock_items.append(product)
        elif qty <= 3:
            product.stock_badge_label = "Low stock"
            product.stock_badge_class = "warning"
            low_stock_items.append(product)
        elif qty <= 10:
            product.stock_badge_label = "Good"
            product.stock_badge_class = "success"
            healthy_count += 1
        else:
            product.stock_badge_label = "Plenty"
            product.stock_badge_class = "primary"
            healthy_count += 1
            
        if product.cost_price is not None and product.selling_price is not None:
            product.potential_profit = (product.selling_price - product.cost_price) * Decimal(qty)
            total_potential_profit += product.potential_profit
        else:
            product.potential_profit = None
            
        if product.cost_price is not None:
            product.stock_value = Decimal(qty) * product.cost_price
            total_stock_value += product.stock_value
        else:
            product.stock_value = None
        products.append(product)

    total_products = len(products)
    warehouse_score = round((healthy_count / total_products) * 100) if total_products else 0
    
    # Build reorder queue: top 3 low/out items by urgency (out of stock first, then lowest qty)
    reorder_queue = out_of_stock_items[:3]
    if len(reorder_queue) < 3:
        reorder_queue.extend(low_stock_items[:3 - len(reorder_queue)])

    context = {
        "business": business,
        "products": products,
        "warehouse_score": warehouse_score,
        "warehouse_healthy_count": healthy_count,
        "warehouse_total_products": total_products,
        # Premium KPIs
        "total_units": total_units,
        "total_stock_value": total_stock_value,
        "total_potential_profit": total_potential_profit,
        "low_stock_count": len(low_stock_items),
        "out_of_stock_count": len(out_of_stock_items),
        "reorder_queue": reorder_queue,
        "active_tab": "stock",
    }

    return render(request, "verticals/cement/stock_list.html", context)


@login_required
@require_business
@require_business_kind(BusinessKind.CEMENT)
def stock_in(request):
    """
    Hardware / Cement Stock-In wizard.

    Flow:
      Step "choose" (default) — category selection grid (all hardware categories)
      For "construction-materials":
        Step 1 — Select brand (seeded cement brands)
        Step 2 — Quantity & pricing → save
      For any other category:
        Step "generic" — simple product-name + qty + price form → save
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)

    business = get_active_business(request)

    # Seed default cement brands (idempotent)
    seed_cement_defaults(business)

    category_key = request.GET.get("category", "").strip()

    # ------------------------------------------------------------------ #
    # GENERIC STOCK-IN: for non-construction categories                   #
    # ------------------------------------------------------------------ #
    if category_key and category_key != "construction-materials":
        from inventory.catalog.registry import get_category_by_key

        cat_def = get_category_by_key(category_key) or {}
        category_label = cat_def.get("label", category_key.replace("-", " ").title())

        if request.method == "POST":
            try:
                product_name = request.POST.get("product_name", "").strip()
                unit = request.POST.get("unit", "unit").strip() or "unit"
                quantity_raw = request.POST.get("quantity", "0").strip()
                cost_raw = request.POST.get("cost_price", "0").strip()
                selling_raw = request.POST.get("selling_price", "0").strip()
                notes = request.POST.get("notes", "").strip()

                if not product_name:
                    messages.error(request, "Product name is required.")
                    return redirect(f"{reverse('cement:stock_in')}?category={category_key}&step=generic")

                quantity = int(quantity_raw) if quantity_raw else 0
                cost_price = Decimal(cost_raw) if cost_raw else Decimal("0")
                selling_price = Decimal(selling_raw) if selling_raw else Decimal("0")

                if quantity <= 0:
                    messages.error(request, "Quantity must be greater than 0.")
                    return redirect(f"{reverse('cement:stock_in')}?category={category_key}&step=generic")

                with transaction.atomic():
                    product, created = MerchProduct.objects.get_or_create(
                        business=business,
                        kind=BusinessKind.CEMENT,
                        name=product_name,
                        category=category_key,
                        defaults={
                            "base_unit": unit,
                            "cost_price": cost_price,
                            "selling_price": selling_price,
                            "quantity_in_stock": 0,
                            "is_active": True,
                        },
                    )
                    product.quantity_in_stock = (product.quantity_in_stock or 0) + quantity
                    if cost_price > 0:
                        product.cost_price = cost_price
                    if selling_price > 0:
                        product.selling_price = selling_price
                    if notes and not product.description:
                        product.description = notes
                    product.save()

                action = "created and stocked" if created else f"stocked (+{quantity})"
                messages.success(request, f"✅ {product_name} — {action} successfully.")
                return redirect(f"{reverse('cement:stock_in')}?category={category_key}&step=generic")

            except (ValueError, TypeError) as e:
                messages.error(request, f"Invalid input: {e}")
                _log.warning("Hardware stock-in generic form error: %s", e)
                return redirect(f"{reverse('cement:stock_in')}?category={category_key}&step=generic")
            except Exception as e:
                messages.error(request, f"Could not save stock: {e}")
                _log.exception("Hardware stock-in generic save error: %s", e)
                return redirect(f"{reverse('cement:stock_in')}?category={category_key}&step=generic")

        # GET: existing products in this category for reference
        existing_products = (
            MerchProduct.objects.filter(
                business=business,
                kind=BusinessKind.CEMENT,
                category=category_key,
                is_active=True,
            )
            .order_by("name")[:30]
        )

        return render(request, "verticals/cement/stock_in_fast.html", {
            "business": business,
            "step": "generic",
            "category_key": category_key,
            "category_label": category_label,
            "category_def": cat_def,
            "existing_products": existing_products,
            "active_tab": "stock_in",
        })

    # ------------------------------------------------------------------ #
    # CATEGORY CHOOSER — no category selected yet                         #
    # ------------------------------------------------------------------ #
    step = request.GET.get("step", "choose" if not category_key else "1")
    if not category_key and step not in ("1", "2"):
        step = "choose"

    if step == "choose":
        all_categories = get_filtered_stock_in_categories(business)
        return render(request, "verticals/cement/stock_in_fast.html", {
            "business": business,
            "step": "choose",
            "all_categories": all_categories,
            "active_tab": "stock_in",
        })

    # ------------------------------------------------------------------ #
    # CONSTRUCTION MATERIALS FLOW (existing cement wizard)               #
    # ------------------------------------------------------------------ #
    if request.method == "POST":
        try:
            _con_prefix = f"{reverse('cement:stock_in')}?category=construction-materials"

            # Step 1: Brand selection (select existing cement product by ID)
            if step == "1":
                product_id = request.POST.get("product_id", "").strip()
                if not product_id:
                    messages.error(request, "Please select a cement brand")
                    return redirect(f"{_con_prefix}&step=1")

                try:
                    selected_product = MerchProduct.objects.get(
                        id=int(product_id),
                        business=business,
                        kind=BusinessKind.CEMENT,
                        is_active=True
                    )
                    request.session["cement_stock_in_product_id"] = selected_product.id
                    request.session["cement_stock_in_brand"] = get_brand_label_for_product(selected_product)
                    return redirect(f"{_con_prefix}&step=2")
                except (MerchProduct.DoesNotExist, ValueError):
                    messages.error(request, "Invalid cement brand selected")
                    return redirect(f"{_con_prefix}&step=1")

            # Step 2: Quantity and pricing
            elif step == "2":
                product_id = request.session.get("cement_stock_in_product_id")
                if not product_id:
                    messages.error(request, "Please start from Step 1")
                    return redirect("cement:stock_in")

                quantity = int(request.POST.get("quantity", 0))
                cost_price = Decimal(request.POST.get("cost_price", "0"))
                selling_price = Decimal(request.POST.get("selling_price", "0"))

                if quantity <= 0:
                    messages.error(request, "Quantity must be greater than 0")
                    return redirect(f"{_con_prefix}&step=2")

                if cost_price <= 0 or selling_price <= 0:
                    messages.error(request, "Cost and selling prices must be greater than 0")
                    return redirect(f"{_con_prefix}&step=2")

                with transaction.atomic():
                    try:
                        product = MerchProduct.objects.get(
                            id=product_id,
                            business=business,
                            kind=BusinessKind.CEMENT,
                            is_active=True
                        )
                        
                        # Check if prices have changed (need price history entry)
                        price_changed = (
                            product.selling_price != selling_price or 
                            product.cost_price != cost_price
                        )
                        
                        # Update existing product
                        product.quantity_in_stock += quantity
                        product.cost_price = cost_price
                        product.selling_price = selling_price
                        product.save(update_fields=["quantity_in_stock", "cost_price", "selling_price"])
                        
                        # Record price history if prices changed
                        if price_changed and product.selling_price and product.selling_price > 0:
                            from inventory.models import ProductPriceHistory
                            from datetime import date
                            
                            # Try to create price history (will fail silently if duplicate for today)
                            try:
                                ProductPriceHistory.objects.get_or_create(
                                    product=product,
                                    effective_date=date.today(),
                                    defaults={
                                        'selling_price': product.selling_price,
                                        'cost_price': product.cost_price,
                                        'created_by': request.user,
                                    }
                                )
                            except Exception:
                                # Silently continue if price history fails (non-critical)
                                pass
                        
                        messages.success(
                            request,
                            f"✅ Added {quantity} bag of {product.name} to stock"
                        )
                    except MerchProduct.DoesNotExist:
                        messages.error(request, "Product not found")
                        return redirect("cement:stock_in")

                    # Clear session
                    for key in ["cement_stock_in_product_id", "cement_stock_in_brand"]:
                        if key in request.session:
                            del request.session[key]

                    return redirect("cement:stock_in")

        except (ValueError, TypeError) as e:
            messages.error(request, f"Invalid input: {e}")
            return redirect(f"{reverse('cement:stock_in')}?category=construction-materials&step={step}")
        except Exception as e:
            messages.error(request, f"Error adding stock: {e}")
            return redirect(f"{reverse('cement:stock_in')}?category=construction-materials&step={step}")

    # GET: Show appropriate step
    context = {
        "business": business,
        "step": step,
        "active_tab": "stock_in",
    }

    # Step 1: Show cement brand selection (direct brand cards)
    if step == "1":
        # Get real cement products from DB for this business
        cement_products = MerchProduct.objects.filter(
            business=business,
            kind=BusinessKind.CEMENT,
            is_active=True,
            category__icontains="cement"
        ).exclude(
            name__iexact="Cement"  # Exclude generic placeholder
        ).order_by("name")
        
        # Filter out placeholder products
        cement_products = [p for p in cement_products if not is_placeholder_product(p)]
        
        # Build brand choices from actual products
        cement_brand_products = []
        seen_brands = set()
        for product in cement_products:
            brand_label = get_brand_label_for_product(product)
            if brand_label and brand_label.lower() not in seen_brands:
                seen_brands.add(brand_label.lower())
                cement_brand_products.append({
                    "product_id": product.id,
                    "brand_name": brand_label,
                    "full_name": product.name,
                    "icon": "🏗️",
                })
        
        context["cement_brand_products"] = cement_brand_products

    # Step 2: Show quantity/pricing form
    elif step == "2":
        product_id = request.session.get("cement_stock_in_product_id")
        if not product_id:
            messages.error(request, "Please start from Step 1")
            return redirect("cement:stock_in")
        
        try:
            selected_product = MerchProduct.objects.get(
                id=product_id,
                business=business,
                kind=BusinessKind.CEMENT,
                is_active=True
            )
            context["selected_product"] = selected_product
            context["selected_product_name"] = selected_product.name
            context["is_cement"] = True
            
            # For prefill: use existing prices if available
            if selected_product.selling_price:
                context["default_selling_price"] = selected_product.selling_price
            if selected_product.cost_price:
                context["default_cost_price"] = selected_product.cost_price
        except MerchProduct.DoesNotExist:
            messages.error(request, "Selected product not found. Please start over.")
            return redirect("cement:stock_in")

    return render(request, "verticals/cement/stock_in_fast.html", context)


@login_required
@require_business
@require_business_kind(BusinessKind.CEMENT)
def sell(request):
    """Gamified sell flow for cement: Brand → Product → Quantity → Payment"""
    business = get_active_business(request)

    step = request.GET.get("step", "1")

    if request.method == "GET" and step == "1":
        prefill_product = request.GET.get("prefill_product")
        prefill_brand = request.GET.get("prefill_brand")
        if prefill_product:
            try:
                product = MerchProduct.objects.get(pk=int(prefill_product), business=business)
                if not is_placeholder_product(product) and (product.quantity_in_stock or 0) > 0:
                    brand_label = get_brand_label_for_product(product)
                    brand_key = brand_label.lower().replace(" ", "_") if brand_label else ""
                    request.session["cement_sell_brand"] = brand_label
                    request.session["cement_sell_brand_label"] = brand_label
                    request.session["cement_sell_brand_key"] = brand_key
                    request.session["cement_sell_product_id"] = product.id
                    return redirect(f"{reverse('cement:sell')}?step=3")
            except (MerchProduct.DoesNotExist, ValueError, TypeError):
                pass
        elif prefill_brand:
            available_brands = build_cement_brand_choices(business)
            brand_map = {b["key"]: b["name"] for b in available_brands}
            if prefill_brand in brand_map:
                request.session["cement_sell_brand"] = brand_map[prefill_brand]
                request.session["cement_sell_brand_label"] = brand_map[prefill_brand]
                request.session["cement_sell_brand_key"] = prefill_brand
                return redirect(f"{reverse('cement:sell')}?step=2")

    if request.method == "POST":
        try:
            # Step 1: Brand selection
            if step == "1":
                brand_key = request.POST.get("brand", "").strip()
                if not brand_key:
                    messages.error(request, "Please select a brand")
                    return redirect(f"{reverse('cement:sell')}?step=1")
                available_brands = build_cement_brand_choices(business)
                brand_map = {b["key"]: b["name"] for b in available_brands}
                brand_label = brand_map.get(brand_key)
                if not brand_label:
                    messages.error(request, "Invalid brand selection")
                    return redirect(f"{reverse('cement:sell')}?step=1")
                request.session["cement_sell_brand"] = brand_label
                request.session["cement_sell_brand_label"] = brand_label
                request.session["cement_sell_brand_key"] = brand_key
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

                # FIX: select_for_update MUST be inside transaction.atomic()
                # Otherwise: "select_for_update cannot be used outside of a transaction"
                with transaction.atomic():
                    # Lock product row for atomic update
                    product = MerchProduct.objects.select_for_update().get(
                        pk=product_id, business=business, kind=BusinessKind.CEMENT, is_active=True
                    )

                    if product.quantity_in_stock < quantity:
                        messages.error(
                            request, f"Insufficient stock. Available: {product.quantity_in_stock}, Requested: {quantity}"
                        )
                        return redirect(f"{reverse('cement:sell')}?step=3")

                    # Calculate totals
                    unit_cost = product.cost_price or Decimal("0")
                    unit_price = product.selling_price or Decimal("0")
                    total_cost = unit_cost * quantity
                    total_revenue = unit_price * quantity
                    profit = total_revenue - total_cost

                    # Decrease stock atomically
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
    all_brands = build_cement_brand_choices(business, in_stock_only=True)
    
    # FIX: Handle empty state - no cement products in stock
    if not all_brands and step == "1":
        messages.info(request, "No cement stock found. Stock in products first.")
        context = {
            "business": business,
            "step": "empty",
            "brands": [],
            "active_tab": "sell",
        }
        return render(request, "verticals/cement/sell.html", context)
    
    # FIX: Auto-skip step 1 if only one brand exists
    if len(all_brands) == 1 and step == "1":
        brand = all_brands[0]
        request.session["cement_sell_brand"] = brand["name"]
        request.session["cement_sell_brand_label"] = brand["name"]
        request.session["cement_sell_brand_key"] = brand["key"]
        return redirect(f"{reverse('cement:sell')}?step=2")

    context = {
        "business": business,
        "step": step,
        "brands": all_brands,
        "active_tab": "sell",
    }

    # Step 2: Show products for selected brand
    if step == "2":
        brand_label = request.session.get("cement_sell_brand_label") or request.session.get("cement_sell_brand", "")
        if brand_label:
            products_qs = MerchProduct.objects.filter(
                business=business,
                kind=BusinessKind.CEMENT,
                is_active=True,
                quantity_in_stock__gt=0,
            ).order_by("name")
            products = []
            for product in products_qs:
                if is_placeholder_product(product):
                    continue
                if get_brand_label_for_product(product).lower() != brand_label.lower():
                    continue
                product.display_name = (
                    normalize_label(product.name) if any(c in product.name for c in "_-") else product.name
                )
                product.unit_label = build_unit_label(product)
                products.append(product)
            context["selected_brand_label"] = normalize_label(brand_label)
            context["products"] = products

    # Step 3: Show quantity/payment form
    elif step == "3":
        product_id = request.session.get("cement_sell_product_id")
        if product_id:
            try:
                product = MerchProduct.objects.get(pk=product_id, business=business)
                product.display_name = (
                    normalize_label(product.name) if any(c in product.name for c in "_-") else product.name
                )
                product.unit_label = build_unit_label(product)
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
        "today": timezone.now().date(),
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


@login_required
@require_business
@require_business_kind(BusinessKind.CEMENT)
@manager_required
def edit_sale(request, sale_id: int):
    """
    Edit a cement sale (manager only).
    Allows correcting quantity, price, payment method, and notes.
    Automatically adjusts stock and recalculates profit.
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

    # Check if already undone/void
    if sale.is_void:
        messages.error(request, "Cannot edit a voided sale. Create a new sale instead.")
        return redirect("cement:dashboard")

    # Store original values for stock delta calculation
    original_quantity = sale.quantity
    original_unit_price = sale.unit_price

    if request.method == "POST":
        try:
            new_quantity = int(request.POST.get("quantity", original_quantity))
            new_unit_price = Decimal(request.POST.get("unit_price", str(original_unit_price)))
            new_payment_method = request.POST.get("payment_method", sale.payment_method)
            new_notes = request.POST.get("notes", sale.notes or "")

            if new_quantity <= 0:
                messages.error(request, "Quantity must be greater than 0")
                return redirect("cement:edit_sale", sale_id=sale_id)

            if new_unit_price < Decimal("0"):
                messages.error(request, "Price cannot be negative")
                return redirect("cement:edit_sale", sale_id=sale_id)

            # Calculate stock delta
            stock_delta = original_quantity - new_quantity  # Positive = return to stock, Negative = take from stock

            with transaction.atomic():
                # Update stock
                product = MerchProduct.objects.select_for_update().get(pk=sale.product.pk)

                # Check if we have enough stock if quantity increased
                if stock_delta < 0:  # Need more stock
                    needed = abs(stock_delta)
                    if product.quantity_in_stock < needed:
                        messages.error(
                            request,
                            f"Insufficient stock. Available: {product.quantity_in_stock}, "
                            f"Additional needed: {needed}"
                        )
                        return redirect("cement:edit_sale", sale_id=sale_id)
                
                # Apply stock delta
                product.quantity_in_stock += stock_delta
                product.save(update_fields=["quantity_in_stock"])

                # Update sale record
                sale.quantity = new_quantity
                sale.unit_price = new_unit_price
                sale.payment_method = new_payment_method
                sale.notes = new_notes
                # total_price and total_cost are auto-calculated in save()
                sale.save()

                # Prepare stock change message
                if stock_delta > 0:
                    stock_msg = f"Stock increased by {stock_delta} {product.base_unit}"
                elif stock_delta < 0:
                    stock_msg = f"Stock decreased by {abs(stock_delta)} {product.base_unit}"
                else:
                    stock_msg = "Stock unchanged"

                messages.success(
                    request,
                    f"✅ Sale updated: {sale.product.name} - "
                    f"Qty: {new_quantity}, Price: MK {new_unit_price:,.0f}, "
                    f"Total: MK {sale.total_price:,.0f}. {stock_msg}"
                )
                return redirect("cement:dashboard")

        except (ValueError, TypeError) as e:
            messages.error(request, f"Invalid input: {e}")
            return redirect("cement:edit_sale", sale_id=sale_id)
        except Exception as e:
            messages.error(request, f"Error updating sale: {e}")
            return redirect("cement:edit_sale", sale_id=sale_id)

    # GET: Show edit form
    # Calculate impact preview data
    payment_methods = [
        ("CASH", "Cash"),
        ("BANK", "Bank Transfer"),
        ("MOBILE_MONEY", "Mobile Money"),
    ]

    context = {
        "business": business,
        "sale": sale,
        "product": sale.product,
        "original_quantity": original_quantity,
        "original_unit_price": original_unit_price,
        "original_total": sale.total_price,
        "original_profit": sale.profit,
        "payment_methods": payment_methods,
        "active_tab": "dashboard",
    }

    return render(request, "verticals/cement/sale_edit.html", context)


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

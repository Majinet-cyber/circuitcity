# inventory/verticals/cement.py
"""
Cement / Hardware Vertical - Building materials and hardware store
"""
from __future__ import annotations

from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.catalog.hardware import (
    HARDWARE_CATEGORIES,
    get_catalog_products,
    get_popular_products,
    get_product_by_slug,
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

    total_costs_period = costs_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0")

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
        "total_costs": total_costs_period,
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
    """Gamified stock-in flow for cement: Brand → Product → Quantity → Pricing"""
    business = get_active_business(request)

    # Seed default cement brands if not already seeded (idempotent)
    seed_cement_defaults(business)

    # Step tracking
    step = request.GET.get("step", "1")

    if request.method == "POST":
        try:
            # Step 1: Brand selection
            if step == "1":
                brand = request.POST.get("brand", "").strip()
                if not brand:
                    messages.error(request, "Please select a brand")
                    return redirect(f"{reverse('cement:stock_in')}?step=1")
                # Store brand in session for next step
                request.session["cement_stock_in_brand"] = brand
                return redirect(f"{reverse('cement:stock_in')}?step=2")

            # Step 2: Product selection/creation
            elif step == "2":
                brand = request.session.get("cement_stock_in_brand", "")
                product_name = request.POST.get("product_name", "").strip()
                product_id = request.POST.get("product_id", "").strip()

                if product_id:
                    # Existing product selected
                    request.session["cement_stock_in_product_id"] = int(product_id)
                elif product_name:
                    # New product name entered
                    request.session["cement_stock_in_product_name"] = product_name
                else:
                    messages.error(request, "Please select or enter a product")
                    return redirect(f"{reverse('cement:stock_in')}?step=2")

                request.session["cement_stock_in_brand"] = brand
                return redirect(f"{reverse('cement:stock_in')}?step=3")

            # Step 3: Quantity and pricing
            elif step == "3":
                brand = request.session.get("cement_stock_in_brand", "")
                product_id = request.session.get("cement_stock_in_product_id")
                product_name = request.session.get("cement_stock_in_product_name", "")

                quantity = int(request.POST.get("quantity", 0))
                cost_price = Decimal(request.POST.get("cost_price", "0"))
                selling_price = Decimal(request.POST.get("selling_price", "0"))
                unit = request.POST.get("unit", "bag").strip()

                if quantity <= 0:
                    messages.error(request, "Quantity must be greater than 0")
                    return redirect(f"{reverse('cement:stock_in')}?step=3")

                if cost_price <= 0 or selling_price <= 0:
                    messages.error(request, "Cost and selling prices must be greater than 0")
                    return redirect(f"{reverse('cement:stock_in')}?step=3")

                with transaction.atomic():
                    if product_id:
                        # Update existing product
                        product = MerchProduct.objects.get(pk=product_id, business=business, kind=BusinessKind.CEMENT)
                        product.quantity_in_stock += quantity
                        product.cost_price = cost_price
                        product.selling_price = selling_price
                        product.save(update_fields=["quantity_in_stock", "cost_price", "selling_price"])
                        final_name = product.name
                    else:
                        # Create new product
                        final_name = f"{brand} - {product_name}" if brand else product_name
                        product, created = MerchProduct.objects.get_or_create(
                            business=business,
                            name=final_name,
                            kind=BusinessKind.CEMENT,
                            defaults={
                                "category": "cement",
                                "spec_label": "",  # CRITICAL: Always set spec_label (prevents NULL constraint)
                                "cost_price": cost_price,
                                "selling_price": selling_price,
                                "quantity_in_stock": quantity,
                                "base_unit": unit,
                                "is_active": True,
                                "track_inventory": True,
                            },
                        )

                        if not created:
                            product.quantity_in_stock += quantity
                            product.cost_price = cost_price
                            product.selling_price = selling_price
                            product.save(update_fields=["quantity_in_stock", "cost_price", "selling_price"])

                    messages.success(request, f"✅ Added {quantity} {unit} of {final_name} to stock")

                    # Clear session
                    for key in ["cement_stock_in_brand", "cement_stock_in_product_id", "cement_stock_in_product_name"]:
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
    # Get all cement brands (seeded + custom)
    all_products = MerchProduct.objects.filter(business=business, kind=BusinessKind.CEMENT, is_active=True).values_list(
        "name", flat=True
    )

    # Use seeded brands list
    seed_brands = get_cement_brands_list()

    # Extract custom brands from products (not in seed list)
    seed_names_lower = [b["name"].lower() for b in seed_brands]
    custom_brands = set()
    for name in all_products:
        # Extract brand from "Brand - Product" format or use full name
        brand_name = name.split(" - ")[0] if " - " in name else name
        if brand_name.lower() not in seed_names_lower:
            custom_brands.add(brand_name)

    # Combine seeded + custom brands
    all_brands = seed_brands + [{"key": b.lower().replace(" ", "_"), "name": b, "icon": "📦"} for b in custom_brands]

    context = {
        "business": business,
        "step": step,
        "brands": all_brands,
        "active_tab": "stock_in",
    }

    # Step 2: Show products for selected brand (with variation grouping)
    if step == "2":
        brand = request.session.get("cement_stock_in_brand", "")
        if brand:
            # Get existing products for this brand
            products = MerchProduct.objects.filter(
                business=business, kind=BusinessKind.CEMENT, is_active=True, name__istartswith=brand
            ).order_by("name")

            # Group products by base name (e.g., "Paint" instead of "Paint 1L", "Paint 4L")
            grouped_products = group_products_by_base_name(products)

            context["selected_brand"] = brand
            context["products"] = products
            context["grouped_products"] = grouped_products

    # Step 3: Show quantity/pricing form
    elif step == "3":
        brand = request.session.get("cement_stock_in_brand", "")
        product_id = request.session.get("cement_stock_in_product_id")
        product_name = request.session.get("cement_stock_in_product_name", "")

        context["selected_brand"] = brand
        if product_id:
            try:
                product = MerchProduct.objects.get(pk=product_id, business=business)
                context["selected_product"] = product
            except MerchProduct.DoesNotExist:
                messages.error(request, "Product not found")
                return redirect(f"{reverse('cement:stock_in')}?step=2")
        else:
            context["new_product_name"] = product_name

        units = [
            ("bag", "Bag (50kg)"),
            ("ton", "Ton"),
            ("kg", "Kilograms"),
        ]
        context["units"] = units

    return render(request, "verticals/cement/stock_in.html", context)


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

    Features:
    - Category chips for filtering
    - Search by product name + keywords
    - Popular items section (top 12)
    - List results grouped by category (collapsible)
    """
    business = get_active_business(request)

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

    Flow:
    1. Show base product info
    2. Step-by-step variation selection (brand → size → color/finish)
    3. "Add to Inventory" button → redirects to stock-in with prefilled data
    """
    business = get_active_business(request)

    # Get product from catalog
    product = get_product_by_slug(slug)
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

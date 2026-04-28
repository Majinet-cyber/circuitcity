# inventory/verticals/groceries.py
"""
Groceries Vertical - Simple retail store for food and household items
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.utils import timezone

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.helpers import get_active_business
from inventory.models import MerchProduct
from inventory.models_verticals import GrocerySale

logger = logging.getLogger(__name__)
from inventory.verticals.groceries_seed import (
    CATEGORIES,
    SEED_ITEMS,
    get_category_by_key,
    get_item_by_key,
    get_items_by_category,
    get_seed_key,
    get_variant_by_label,
    parse_seed_key,
)
from tenants.utils import require_business


@login_required
@require_business
@require_business_kind(BusinessKind.GROCERY)
def dashboard(request):
    """Groceries dashboard with KPIs and wholesale/retail toggle"""
    business = get_active_business(request)

    # Get/set mode from session (retail, wholesale, both)
    mode = request.GET.get("mode", request.session.get("groceries_mode", "both"))
    if mode in ["retail", "wholesale", "both"]:
        request.session["groceries_mode"] = mode

    # Get all grocery products
    products = MerchProduct.objects.filter(business=business, kind=BusinessKind.GROCERY, is_active=True)

    # Calculate KPIs
    total_products = products.count()
    total_stock_value = sum((p.quantity_in_stock or 0) * (p.cost_price or Decimal("0")) for p in products)
    items_in_stock = sum(p.quantity_in_stock or 0 for p in products)

    # Sales data (from actual sales)
    today = timezone.now().date()
    from django.db import connection
    from django.db.models import DecimalField, F, Sum, Value
    from django.db.models.functions import Coalesce

    # Check if total_price column exists in GrocerySale table (works for both SQLite and Postgres)
    def _has_column(model, column_name):
        """Check if a column exists in the database table (database-agnostic)"""
        try:
            table_name = model._meta.db_table
            with connection.cursor() as cursor:
                columns = {col.name for col in connection.introspection.get_table_description(cursor, table_name)}
                return column_name in columns
        except Exception:
            # If introspection fails, assume column doesn't exist to be safe
            return False

    has_total_price = _has_column(GrocerySale, "total_price")

    # Build base queryset
    today_sales = GrocerySale.objects.filter(business=business, sold_at__date=today)
    if mode != "both":
        today_sales = today_sales.filter(sale_mode=mode)

    sold_today_count = today_sales.count()

    # Use DecimalField for all calculations
    dec_field = DecimalField(max_digits=12, decimal_places=2)

    if has_total_price:
        # Column exists - use efficient aggregation
        revenue_result = today_sales.aggregate(
            total_revenue=Coalesce(Sum("total_price"), Value(0), output_field=dec_field)
        )
        total_revenue = Decimal(str(revenue_result.get("total_revenue") or 0))

        # Calculate profit: sum(total_price - total_cost) = sum(total_price) - sum(total_cost)
        profit_result = today_sales.aggregate(
            total_revenue_sum=Coalesce(Sum("total_price"), Value(0), output_field=dec_field),
            total_cost_sum=Coalesce(Sum("total_cost"), Value(0), output_field=dec_field),
        )
        revenue_sum = Decimal(str(profit_result.get("total_revenue_sum") or 0))
        cost_sum = Decimal(str(profit_result.get("total_cost_sum") or 0))
        total_profit = revenue_sum - cost_sum
    else:
        # Column doesn't exist - calculate manually from quantity * unit_price
        # Use aggregation for efficiency even without total_price column
        revenue_result = today_sales.aggregate(
            total_revenue=Coalesce(
                Sum(F("quantity") * F("unit_price"), output_field=dec_field), Value(0), output_field=dec_field
            )
        )
        total_revenue = Decimal(str(revenue_result.get("total_revenue") or 0))

        # Calculate profit: sum(quantity * unit_price - quantity * unit_cost)
        profit_result = today_sales.aggregate(
            revenue_sum=Coalesce(
                Sum(F("quantity") * F("unit_price"), output_field=dec_field), Value(0), output_field=dec_field
            ),
            cost_sum=Coalesce(
                Sum(F("quantity") * F("unit_cost"), output_field=dec_field), Value(0), output_field=dec_field
            ),
        )
        revenue_sum = Decimal(str(profit_result.get("revenue_sum") or 0))
        cost_sum = Decimal(str(profit_result.get("cost_sum") or 0))
        total_profit = revenue_sum - cost_sum
    total_costs = total_stock_value

    # Low stock items (less than 10 units)
    low_stock_items = products.filter(quantity_in_stock__lt=10, quantity_in_stock__gt=0).order_by("quantity_in_stock")[
        :10
    ]

    # Recent stock-ins (last 10 products added/updated)
    recent_products = products.order_by("-id")[:10]

    # Demo preview when workspace is empty
    is_demo = total_products == 0 and sold_today_count == 0
    if is_demo:
        total_revenue = Decimal("12400")
        total_profit = Decimal("3200")
        total_stock_value = Decimal("48000")
        items_in_stock = 312
        sold_today_count = 8
        # Fake low-stock items for demo
        class _FakeProduct:
            def __init__(self, name, cat, qty, unit):
                self.name = name; self.category = cat; self.quantity_in_stock = qty; self.base_unit = unit
        low_stock_items = [
            _FakeProduct("Sugar 2kg", "food", 3, "pcs"),
            _FakeProduct("Cooking Oil 2L", "food", 2, "pcs"),
            _FakeProduct("Bread", "food", 4, "pcs"),
        ]

    context = {
        "business": business,
        "is_demo": is_demo,
        "total_revenue": total_revenue,
        "total_profit": total_profit,
        "total_costs": total_costs,
        "stock_value": total_stock_value,
        "sold_today": sold_today_count,
        "items_in_stock": items_in_stock,
        "total_products": total_products,
        "low_stock_items": low_stock_items,
        "recent_products": recent_products,
        "active_mode": mode,
        "active_tab": "dashboard",
    }
    
    # Apply SSOT defaults to prevent KeyError failures
    from reports.services.context_defaults import apply_default_report_context
    context = apply_default_report_context(context)

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
                "DASHBOARD_BRAND_TITLE": business.name if business else "Groceries Dashboard",
                "DASHBOARD_QUOTES": daily_quotes,
                "quotes_json": quotes_json_data,
            }
        )
    except Exception:
        # Gracefully degrade if helpers not available
        pass

    context.update(ctx_enhancements)

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
                "DASHBOARD_BRAND_TITLE": business.name if business else "Groceries Dashboard",
                "DASHBOARD_QUOTES": daily_quotes,
                "quotes_json": quotes_json_data,
            }
        )
    except Exception:
        # Gracefully degrade if helpers not available
        pass

    context.update(ctx_enhancements)

    return render(request, "verticals/groceries/dashboard.html", context)


@login_required
@require_business
@require_business_kind(BusinessKind.GROCERY)
def stock_list(request):
    """List all grocery products"""
    business = get_active_business(request)

    products = MerchProduct.objects.filter(business=business, kind=BusinessKind.GROCERY, is_active=True).order_by(
        "name"
    )

    # Compute stock values in Python (avoid template math)
    products_with_values = []
    for product in products:
        quantity = product.quantity_in_stock or 0
        cost_price = product.cost_price or Decimal("0")
        stock_value = Decimal(str(quantity)) * Decimal(str(cost_price))
        products_with_values.append(
            {
                "product": product,
                "stock_value": stock_value,
            }
        )

    context = {
        "business": business,
        "products": products,
        "products_with_values": products_with_values,
        "active_tab": "stock",
    }

    return render(request, "verticals/groceries/stock_list.html", context)


@login_required
@require_business
@require_business_kind(BusinessKind.GROCERY)
def stock_in(request):
    """Add stock for grocery products"""
    business = get_active_business(request)

    if request.method == "POST":
        try:
            product_name = request.POST.get("product_name", "").strip()
            category = request.POST.get("category", "other").strip()
            quantity = int(request.POST.get("quantity", 0))
            cost_price = Decimal(request.POST.get("cost_price", "0"))
            selling_price = Decimal(request.POST.get("selling_price", "0"))
            unit = request.POST.get("unit", "pcs").strip()

            if not product_name:
                messages.error(request, "Product name is required")
                return redirect("groceries:stock_in")

            if quantity <= 0:
                messages.error(request, "Quantity must be greater than 0")
                return redirect("groceries:stock_in")

            with transaction.atomic():
                # Get or create product
                product, created = MerchProduct.objects.get_or_create(
                    business=business,
                    name=product_name,
                    kind=BusinessKind.GROCERY,
                    defaults={
                        "category": category,
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
                    # Update existing product
                    product.quantity_in_stock += quantity
                    product.cost_price = cost_price
                    product.selling_price = selling_price
                    product.save(update_fields=["quantity_in_stock", "cost_price", "selling_price"])

                messages.success(request, f"✅ Added {quantity} {unit} of {product_name} to stock")
                return redirect("groceries:stock_in")

        except (ValueError, TypeError) as e:
            messages.error(request, f"Invalid input: {e}")
            return redirect("groceries:stock_in")
        except Exception as e:
            messages.error(request, f"Error adding stock: {e}")
            return redirect("groceries:stock_in")

    # GET: Show form
    categories = [
        ("food", "Food Items"),
        ("beverages", "Beverages"),
        ("household", "Household Items"),
        ("snacks", "Snacks"),
        ("dairy", "Dairy Products"),
        ("frozen", "Frozen Foods"),
        ("other", "Other"),
    ]

    units = [
        ("pcs", "Pieces"),
        ("kg", "Kilograms"),
        ("g", "Grams"),
        ("l", "Liters"),
        ("ml", "Milliliters"),
        ("pack", "Pack"),
        ("box", "Box"),
    ]

    context = {
        "business": business,
        "categories": categories,
        "units": units,
        "active_tab": "stock_in",
    }

    return render(request, "verticals/groceries/stock_in.html", context)


@login_required
@require_business
@require_business_kind(BusinessKind.GROCERY)
def sell(request):
    """Sell grocery products"""
    business = get_active_business(request)

    if request.method == "POST":
        try:
            product_id = int(request.POST.get("product_id", 0))
            quantity = int(request.POST.get("quantity", 0))
        except (ValueError, TypeError) as e:
            messages.error(request, f"Invalid input: {e}")
            return redirect("groceries:sell")

        if quantity <= 0:
            messages.error(request, "Quantity must be greater than 0")
            return redirect("groceries:sell")

        # Get sale mode (retail/wholesale)
        sale_mode = request.POST.get("sale_mode", "retail").strip()
        if sale_mode not in ["retail", "wholesale"]:
            sale_mode = "retail"

        # Normalise payment_method to lowercase DB choices: cash / bank / mobile_money
        raw_pm = request.POST.get("payment_method", "cash").strip().lower()
        payment_method = raw_pm if raw_pm in {"cash", "bank", "mobile_money"} else "cash"
        notes = request.POST.get("notes", "")

        try:
            with transaction.atomic():
                # --- Lock the product row INSIDE the atomic block (correct select_for_update usage) ---
                try:
                    product = MerchProduct.objects.select_for_update().get(
                        pk=product_id,
                        business=business,
                        kind=BusinessKind.GROCERY,
                        is_active=True,
                    )
                except MerchProduct.DoesNotExist:
                    messages.error(request, "Product not found or not available")
                    return redirect("groceries:sell")

                # Stock validation (re-checked inside lock)
                if product.quantity_in_stock < quantity:
                    messages.error(
                        request,
                        f"Insufficient stock. Available: {product.quantity_in_stock}, "
                        f"Requested: {quantity}",
                    )
                    return redirect("groceries:sell")

                # --- Explicit field calculation ---
                unit_cost = product.cost_price or Decimal("0")
                unit_price = product.selling_price or Decimal("0")
                total_cost = unit_cost * Decimal(quantity)
                total_revenue = unit_price * Decimal(quantity)
                profit = total_revenue - total_cost

                # --- Reduce stock ---
                product.quantity_in_stock -= quantity
                product.save(update_fields=["quantity_in_stock"])

                # --- Create sale record: ALL required DB fields explicitly provided ---
                # Legacy NOT NULL columns (old DB schema: sale_type, total_amount,
                # customer_name, customer_phone, is_deleted, created_at) are included
                # so SQLite's FK enforcement never sees a NULL where NOT NULL is required.
                sale = GrocerySale.objects.create(
                    business=business,
                    product=product,
                    quantity=quantity,
                    unit_price=unit_price,
                    total_price=total_revenue,
                    unit_cost=unit_cost,
                    total_cost=total_cost,
                    sale_mode=sale_mode,
                    sale_type="regular",
                    total_amount=total_revenue,
                    customer_name="",
                    customer_phone="",
                    is_deleted=False,
                    payment_method=payment_method,
                    sold_by=request.user,
                    notes=notes,
                )

                # --- Success message via on_commit ---
                # CRITICAL: Using transaction.on_commit() ensures the success message is
                # queued ONLY after the DB transaction has truly committed. If the commit
                # fails (e.g. deferred FK violation), on_commit callbacks are NOT fired,
                # so no false-positive success message ever appears alongside an error.
                _qty = quantity
                _unit = product.base_unit
                _name = product.name
                _mode = sale_mode
                _rev = total_revenue
                _prof = profit

                def _success(_qty=_qty, _unit=_unit, _name=_name, _mode=_mode,
                             _rev=_rev, _prof=_prof):
                    messages.success(
                        request,
                        f"✅ Sold {_qty} {_unit} of {_name} ({_mode}). "
                        f"Revenue: MK {_rev:,.2f}, Profit: MK {_prof:,.2f}",
                    )

                transaction.on_commit(_success)

            # Redirect OUTSIDE the atomic block so it only runs on successful commit
            return redirect("groceries:sell")

        except IntegrityError as e:
            # Log the full traceback so the server log tells us exactly which FK failed
            logger.exception(
                "GrocerySale IntegrityError for business=%s product=%s user=%s",
                business.id if business else None,
                product_id,
                request.user.id if request.user.is_authenticated else None,
            )
            messages.error(
                request,
                f"Sale could not be saved due to a database constraint error. "
                f"Please contact support if this persists. (Detail: {e})",
            )
            return redirect("groceries:sell")
        except MerchProduct.DoesNotExist:
            messages.error(request, "Product not found")
            return redirect("groceries:sell")
        except (ValueError, TypeError) as e:
            messages.error(request, f"Invalid input: {e}")
            return redirect("groceries:sell")
        except Exception as e:
            logger.exception(
                "GrocerySale unexpected error for business=%s product=%s",
                business.id if business else None,
                product_id,
            )
            messages.error(request, f"Error processing sale: {e}")
            return redirect("groceries:sell")

    # GET: Show products
    products = MerchProduct.objects.filter(
        business=business, kind=BusinessKind.GROCERY, is_active=True, quantity_in_stock__gt=0
    ).order_by("name")

    context = {
        "business": business,
        "products": products,
        "active_tab": "sell",
    }

    return render(request, "verticals/groceries/sell.html", context)


@login_required
@require_business
@require_business_kind(BusinessKind.GROCERY)
def analytics(request):
    """Basic analytics for groceries"""
    business = get_active_business(request)

    products = MerchProduct.objects.filter(business=business, kind=BusinessKind.GROCERY, is_active=True)

    # Basic stats
    total_products = products.count()
    total_stock_value = sum((p.quantity_in_stock or 0) * (p.cost_price or Decimal("0")) for p in products)

    context = {
        "business": business,
        "total_products": total_products,
        "total_stock_value": total_stock_value,
        "active_tab": "analytics",
    }

    return render(request, "verticals/groceries/analytics.html", context)


@login_required
@require_business
@require_business_kind(BusinessKind.GROCERY)
def product_add(request):
    """Add grocery product via wizard flow (seed catalog or custom)"""
    business = get_active_business(request)
    step = int(request.GET.get("step", 1))

    # Handle POST - save product
    if request.method == "POST":
        try:
            # Check if this is a seed product or custom
            seed_key = request.POST.get("seed_key", "").strip()
            is_custom = request.POST.get("is_custom", "false") == "true"

            if seed_key and not is_custom:
                # Seed product path
                parsed = parse_seed_key(seed_key)
                if not parsed:
                    messages.error(request, "Invalid product selection")
                    return redirect("groceries:product_add")

                category_key, item_name, variant_label = parsed
                item = get_item_by_key(category_key, item_name)
                if not item:
                    messages.error(request, "Product not found in catalog")
                    return redirect("groceries:product_add")

                variant = get_variant_by_label(item, variant_label)
                if not variant:
                    messages.error(request, "Variant not found")
                    return redirect("groceries:product_add")

                # Build product name
                product_name = f"{item_name} {variant_label}"

                # Map unit types to base_unit field
                unit_type = variant["unit_type"]
                if unit_type == "pcs":
                    base_unit = "pcs"
                elif unit_type == "kg":
                    base_unit = "kg"
                elif unit_type == "litre":
                    base_unit = "l"
                elif unit_type == "tray":
                    base_unit = "pcs"  # Store as pieces, label shows "tray"
                else:
                    base_unit = "pcs"

            else:
                # Custom product path
                product_name = request.POST.get("product_name", "").strip()
                base_unit = request.POST.get("unit_type", "pcs").strip()
                variant_label = ""

                if not product_name:
                    messages.error(request, "Product name is required")
                    return redirect("groceries:product_add?step=4&custom=true")

            # Get pricing
            cost_price_str = request.POST.get("cost_price", "").strip()
            selling_price_str = request.POST.get("selling_price", "").strip()
            initial_stock_str = request.POST.get("initial_stock", "0").strip()

            cost_price = None
            if cost_price_str:
                try:
                    cost_price = Decimal(cost_price_str)
                    if cost_price < 0:
                        raise ValueError("Cost price must be non-negative")
                except (ValueError, Exception) as e:
                    messages.error(request, f"Invalid cost price: {e}")
                    return redirect(
                        f'groceries:product_add?step=4&{"custom=true&" if is_custom else ""}seed_key={seed_key}'
                    )

            selling_price = None
            if selling_price_str:
                try:
                    selling_price = Decimal(selling_price_str)
                    if selling_price < 0:
                        raise ValueError("Selling price must be non-negative")
                except (ValueError, Exception) as e:
                    messages.error(request, f"Invalid selling price: {e}")
                    return redirect(
                        f'groceries:product_add?step=4&{"custom=true&" if is_custom else ""}seed_key={seed_key}'
                    )

            # Get initial stock (must be integer >= 0)
            initial_stock = 0
            if initial_stock_str:
                try:
                    initial_stock_int = int(float(initial_stock_str))  # Allow "24.0" -> 24
                    if initial_stock_int < 0:
                        raise ValueError("Stock quantity must be non-negative")
                    initial_stock = initial_stock_int
                except (ValueError, TypeError) as e:
                    messages.error(request, f"Invalid stock quantity: must be a whole number >= 0. {e}")
                    return redirect(
                        f'groceries:product_add?step=4&{"custom=true&" if is_custom else ""}seed_key={seed_key}'
                    )

            # Get spec_label (size/weight/volume specification)
            spec_label = ""
            if seed_key and not is_custom:
                # For seed products, variant_label contains the spec (e.g., "5L", "10L", "9kg")
                spec_label = variant_label or ""
                # Extract base product name (remove variant label if it's in the name)
                full_name = product_name
            else:
                # For custom products, get spec_label from form field
                spec_label = request.POST.get("spec_label", "").strip()
                full_name = product_name

            # Create product
            with transaction.atomic():
                # Get category
                if seed_key and not is_custom:
                    category = category_key
                else:
                    category = request.POST.get("category", "other").strip()

                product, created = MerchProduct.objects.get_or_create(
                    business=business,
                    name=full_name,
                    kind=BusinessKind.GROCERY,
                    defaults={
                        "category": category,
                        "cost_price": cost_price,
                        "selling_price": selling_price,
                        "quantity_in_stock": initial_stock,
                        "base_unit": base_unit,
                        "spec_label": spec_label,
                        "is_active": True,
                        "track_inventory": True,
                    },
                )

                if not created:
                    # Update existing product
                    if cost_price is not None:
                        product.cost_price = cost_price
                    if selling_price is not None:
                        product.selling_price = selling_price
                    product.quantity_in_stock += initial_stock
                    # Update spec_label if provided
                    if spec_label:
                        product.spec_label = spec_label
                    product.save(update_fields=["cost_price", "selling_price", "quantity_in_stock", "spec_label"])
                    messages.info(request, f"📝 Updated {full_name} (added {initial_stock} to stock)")
                else:
                    messages.success(request, f"✅ Product saved: {full_name}")

            # Redirect to stock list with success
            return redirect("groceries:stock_list")

        except Exception as e:
            messages.error(request, f"Error saving product: {e}")
            return redirect("groceries:product_add")

    # GET: Show wizard steps
    context = {
        "business": business,
        "step": step,
        "categories": CATEGORIES,
    }

    # Step 1: Categories
    if step == 1:
        context["active_tab"] = "product_add"
        return render(request, "verticals/groceries/product_add.html", context)

    # Step 2: Items for category
    if step == 2:
        category_key = request.GET.get("category", "").strip()
        if not category_key:
            messages.error(request, "Please select a category")
            return redirect("groceries:product_add")

        category = get_category_by_key(category_key)
        if not category:
            messages.error(request, "Invalid category")
            return redirect("groceries:product_add")

        items = get_items_by_category(category_key)
        context.update(
            {
                "category": category,
                "category_key": category_key,
                "items": items,
            }
        )
        return render(request, "verticals/groceries/product_add.html", context)

    # Step 3: Variants for item
    if step == 3:
        category_key = request.GET.get("category", "").strip()
        item_name = request.GET.get("item", "").strip()

        if not category_key or not item_name:
            messages.error(request, "Please select a category and item")
            return redirect("groceries:product_add")

        item = get_item_by_key(category_key, item_name)
        if not item:
            messages.error(request, "Item not found")
            return redirect("groceries:product_add")

        category = get_category_by_key(category_key)
        context.update(
            {
                "category": category,
                "category_key": category_key,
                "item": item,
                "item_name": item_name,
            }
        )
        return render(request, "verticals/groceries/product_add.html", context)

    # Step 4: Pricing and stock
    if step == 4:
        seed_key = request.GET.get("seed_key", "").strip()
        is_custom = request.GET.get("custom", "false") == "true"

        if seed_key and not is_custom:
            parsed = parse_seed_key(seed_key)
            if not parsed:
                messages.error(request, "Invalid product selection")
                return redirect("groceries:product_add")

            category_key, item_name, variant_label = parsed
            item = get_item_by_key(category_key, item_name)
            if not item:
                messages.error(request, "Product not found")
                return redirect("groceries:product_add")

            variant = get_variant_by_label(item, variant_label)
            if not variant:
                messages.error(request, "Variant not found")
                return redirect("groceries:product_add")

            category = get_category_by_key(category_key)
            context.update(
                {
                    "category": category,
                    "category_key": category_key,
                    "item": item,
                    "item_name": item_name,
                    "variant": variant,
                    "variant_label": variant_label,
                    "seed_key": seed_key,
                }
            )
        else:
            # Custom product
            context.update(
                {
                    "is_custom": True,
                }
            )

        return render(request, "verticals/groceries/product_add.html", context)

    # Default: redirect to step 1
    return redirect("groceries:product_add")


@login_required
@require_business
@require_business_kind(BusinessKind.GROCERY)
def rollback_sale(request, sale_id):
    """
    Rollback/cancel a grocery sale and restore product inventory.
    Manager-only feature for correcting mistakes.
    """
    from django.contrib import messages
    from django.db import transaction
    from django.http import JsonResponse
    from django.shortcuts import redirect

    from tenants.models import Membership

    business = get_active_business(request)

    # Check if user is manager/owner/admin (managers must always be able to rollback)
    try:
        membership = Membership.objects.get(user=request.user, business=business, status="ACTIVE")
        role = membership.role.upper()
        if role not in ["MANAGER", "OWNER", "ADMIN", "HQ_ADMIN"]:
            if request.method == "POST":
                return JsonResponse({"ok": False, "error": "Only managers can rollback sales"}, status=403)
            messages.error(request, "Only managers can rollback sales")
            return redirect("groceries:stock_list")
    except Membership.DoesNotExist:
        if request.method == "POST":
            return JsonResponse({"ok": False, "error": "User is not a member of this business"}, status=403)
        messages.error(request, "User is not a member of this business")
        return redirect("groceries:stock_list")

    # Get the sale
    try:
        sale = GrocerySale.objects.get(id=sale_id, business=business)
    except GrocerySale.DoesNotExist:
        if request.method == "POST":
            return JsonResponse({"ok": False, "error": "Sale not found"}, status=404)
        messages.error(request, "Sale not found")
        return redirect("groceries:stock_list")

    if request.method == "POST":
        with transaction.atomic():
            # Restore product inventory
            product = sale.product
            product.quantity_in_stock += sale.quantity
            product.save(update_fields=["quantity_in_stock"])

            # Mark sale as rolled back by adding note (GrocerySale doesn't have is_rolled_back field)
            sale.notes = f"[ROLLED BACK by {request.user.username} on {timezone.now()}] {sale.notes or ''}"
            sale.save(update_fields=["notes"])

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {"ok": True, "message": f"Sale #{sale_id} rolled back successfully. Inventory restored."}
            )

        messages.success(request, f"Sale #{sale_id} rolled back successfully. Inventory restored.")
        return redirect("groceries:stock_list")

    # GET request: show confirmation page
    context = {
        "business": business,
        "sale": sale,
        "active_tab": "stock",
    }
    return render(request, "verticals/groceries/rollback_confirm.html", context)


# ---------------------------------------------------------------------------
# Phase 2: Inventory Intelligence
# ---------------------------------------------------------------------------

@login_required
@require_business
@require_business_kind(BusinessKind.GROCERY)
def inventory_intelligence(request):
    """Advanced inventory analytics: turnover, fast/slow movers, category performance."""
    business = get_active_business(request)

    try:
        from inventory.services.groceries_intelligence import get_inventory_intelligence
        intel = get_inventory_intelligence(business)
    except Exception:
        intel = {}

    context = {
        "business": business,
        "active_tab": "intelligence",
        "intel": intel,
    }
    return render(request, "verticals/groceries/inventory_intelligence.html", context)


@login_required
@require_business
@require_business_kind(BusinessKind.GROCERY)
def sales_analytics(request):
    """Sales analytics: daily trends, product performance, payment mix."""
    business = get_active_business(request)
    days = int(request.GET.get("days", 30))

    try:
        from inventory.services.groceries_intelligence import get_sales_analytics
        analytics = get_sales_analytics(business, days=days)
    except Exception:
        analytics = {}

    context = {
        "business": business,
        "active_tab": "sales_analytics",
        "analytics": analytics,
        "days": days,
    }
    return render(request, "verticals/groceries/sales_analytics.html", context)


@login_required
@require_business
@require_business_kind(BusinessKind.GROCERY)
def smart_restocking(request):
    """Smart restocking recommendations based on sales velocity."""
    business = get_active_business(request)

    try:
        from inventory.services.groceries_intelligence import get_restock_recommendations
        recommendations = get_restock_recommendations(business)
    except Exception:
        recommendations = []

    total_cost = sum(r.get("estimated_cost", 0) for r in recommendations)

    context = {
        "business": business,
        "active_tab": "restocking",
        "recommendations": recommendations,
        "total_restock_cost": total_cost,
    }
    return render(request, "verticals/groceries/smart_restocking.html", context)

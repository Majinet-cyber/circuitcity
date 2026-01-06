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

from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.clothing_config import (
    BADGES,
    CLOTHING_CATEGORIES,
    CLOTHING_COLORS,
    DEFAULT_DAILY_REVENUE_TARGET,
    DEFAULT_DAILY_SALES_TARGET,
    PRICE_TIER_LABELS,
    check_badges_earned,
    get_category_display,
    get_category_icon,
    get_price_tier,
    get_sizes_for_category,
    get_stock_status,
)
from inventory.models import MerchProduct
from inventory.models_verticals import (
    ClothingProductAction,
    ClothingProductLog,
    ClothingSale,
    ClothingVariant,
    PaymentMethod,
)
from inventory.services.clothing_service import (
    get_low_stock_products,
    get_slow_movers,
    get_top_sellers,
    sell_clothing,
    stock_in_clothing,
)
from inventory.verticals import base
from tenants.utils import require_business

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
    Step 2: Minimal form for product details.
    """
    from django import forms

    ctx = base.base_context(request)
    business = ctx.get("business")

    # Get category display
    category_display = get_category_display(category)
    category_icon = get_category_icon(category)

    # Get appropriate sizes for this category
    size_choices = get_sizes_for_category(category)

    # Build form dynamically
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
        }
    )

    return render(request, "verticals/clothing/quick_add_step2.html", ctx)


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
# FAST SELL (NON-BARCODED ITEMS ONLY)
# ============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def fast_sell(request):
    """
    Fast sell page for NON-BARCODED items: search box + top items grid + sticky cart.

    For BARCODED items, use fast_sell_barcode_scanner instead.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")

    # Get products with stock (non-barcoded bulk items)
    available_products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.CLOTHING,
        is_active=True,
        is_archived=False,
        quantity_in_stock__gt=0,
    ).order_by("-id")[:20]

    # Get top sellers
    top_sellers = get_top_sellers(business, days=7, limit=10)
    top_seller_ids = [item["product"].id for item in top_sellers]

    ctx.update(
        {
            "available_products": available_products,
            "top_seller_ids": top_seller_ids,
            "page_title": "Sell",
        }
    )

    return render(request, "verticals/clothing/fast_sell.html", ctx)


# ============================================================================
# BARCODE FAST SELL (BARCODED ITEMS ONLY)
# ============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def fast_sell_barcode_scanner(request):
    """
    Fast sell scanner page for BARCODED clothing items.

    Flow:
    1. Open scanner (camera or manual input)
    2. Scan barcode -> lookup barcoded unit -> auto-complete sale
    3. Return to scan again

    NO quantity prompts, NO manual price selection (uses pre-stored prices from barcode unit).
    """
    ctx = base.base_context(request)
    business = ctx.get("business")

    # Get today's stats for this user (for KPI display)
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_sales = ClothingSale.objects.filter(
        business=business,
        sold_by=request.user,
        sold_at__gte=today_start,
    )

    today_count = today_sales.count()
    today_revenue = today_sales.aggregate(total=Sum("total_price"))["total"] or Decimal("0.00")

    ctx.update(
        {
            "page_title": "Fast Sell - Barcode Scanner",
            "today_count": today_count,
            "today_revenue": today_revenue,
        }
    )

    return render(request, "verticals/clothing/fast_sell_barcode.html", ctx)


# ============================================================================
# BARCODE WIZARD (ADD BARCODED ITEMS)
# ============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def barcode_add_step1(request):
    """
    Barcode Add - Step 1: Collect prices, quantity, size BEFORE scanning.

    Fields:
    - Category & Subcategory
    - Size (CRITICAL: shoes = numeric only, validated)
    - Quantity (how many units to scan)
    - Cost Price
    - Selling Price (auto-suggest if blank, manager override if < cost)
    - Brand (optional)
    - Color (optional)

    Validation:
    - Inline errors only (NO popups)
    - Shoes size must be numeric 30-50
    - Selling price < cost requires manager override checkbox

    After validation -> redirect to Step 2 (scanning loop)
    """
    from django import forms
    from django.core.exceptions import ValidationError

    from inventory.clothing_size_validation import (
        get_allowed_sizes_for_category,
        is_footwear_category,
        validate_clothing_size,
    )
    from inventory.services.clothing_barcode_service import create_barcode_batch_session

    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")
    user = request.user
    is_manager = user.groups.filter(name="Manager").exists() or user.is_staff

    # Get categories for dropdown
    categories_choices = [(cat[0], cat[1]) for cat in CLOTHING_CATEGORIES]

    class BarcodeAddStep1Form(forms.Form):
        category = forms.ChoiceField(
            choices=[("", "-- Select Category --")] + categories_choices,
            required=True,
            widget=forms.Select(attrs={"class": "form-control", "id": "id_category"}),
            label="Category",
        )

        subcategory = forms.CharField(
            max_length=50,
            required=False,
            widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., sneaker, boot (optional)"}),
            label="Subcategory (optional)",
        )

        size = forms.CharField(
            max_length=20,
            required=True,
            widget=forms.TextInput(attrs={"class": "form-control", "id": "id_size", "placeholder": "e.g., 42, M, L"}),
            label="Size",
            help_text="IMPORTANT: Shoes must use numeric sizes only (30-50)",
        )

        quantity = forms.IntegerField(
            min_value=1,
            max_value=100,
            initial=1,
            required=True,
            widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "How many units to scan"}),
            label="Quantity",
            help_text="Number of units you will scan (max 100 per batch)",
        )

        cost_price = forms.DecimalField(
            max_digits=12,
            decimal_places=2,
            min_value=Decimal("0.00"),
            required=True,
            widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}),
            label="Cost Price (per unit)",
        )

        selling_price = forms.DecimalField(
            max_digits=12,
            decimal_places=2,
            min_value=Decimal("0.01"),
            required=False,  # Auto-suggest if blank
            widget=forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "placeholder": "Auto-calculated if left blank"}
            ),
            label="Selling Price (per unit)",
            help_text="Leave blank to auto-calculate (cost × 1.35, rounded)",
        )

        brand = forms.CharField(
            max_length=100,
            required=False,
            widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., Nike, Adidas (optional)"}),
            label="Brand (optional)",
        )

        color = forms.CharField(
            max_length=50,
            required=False,
            widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., Black, Blue (optional)"}),
            label="Color (optional)",
        )

        product_name = forms.CharField(
            max_length=200,
            required=False,
            widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional descriptive name"}),
            label="Product Name (optional)",
            help_text="Auto-generated from category + size if left blank",
        )

        # Manager override checkbox (only shown if selling < cost)
        allow_below_cost = forms.BooleanField(
            required=False,
            widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
            label="Allow selling below cost (Manager only)",
        )

        def clean(self):
            cleaned_data = super().clean()
            category = cleaned_data.get("category")
            subcategory = cleaned_data.get("subcategory", "")
            size = cleaned_data.get("size", "").strip()
            cost_price = cleaned_data.get("cost_price")
            selling_price = cleaned_data.get("selling_price")
            allow_below_cost = cleaned_data.get("allow_below_cost", False)

            # Validate size (CRITICAL: shoes must be numeric)
            if category and size:
                is_valid, error_msg = validate_clothing_size(size, category, subcategory)
                if not is_valid:
                    self.add_error("size", error_msg)

            # Auto-suggest selling price if blank
            if cost_price and not selling_price:
                # Auto-suggest: cost × 1.35, rounded to nearest 100
                suggested = cost_price * Decimal("1.35")
                # Round to nearest 100
                selling_price = (suggested / 100).quantize(Decimal("1")) * 100
                cleaned_data["selling_price"] = selling_price

            # Check if selling < cost (requires manager override)
            if cost_price and selling_price and selling_price < cost_price:
                if not allow_below_cost:
                    self.add_error(
                        "selling_price",
                        "Selling price is below cost. Check 'Allow selling below cost' to proceed (Manager only).",
                    )
                elif not is_manager:
                    self.add_error("allow_below_cost", "Only managers can approve selling below cost.")

            return cleaned_data

    if request.method == "POST":
        form = BarcodeAddStep1Form(request.POST)
        if form.is_valid():
            data = form.cleaned_data

            try:
                # Create batch session (validates and stores in session)
                session_data = create_barcode_batch_session(
                    business=business,
                    location=location,
                    user=user,
                    category=data["category"],
                    subcategory=data.get("subcategory", ""),
                    size=data["size"],
                    quantity=data["quantity"],
                    cost_price=data["cost_price"],
                    selling_price=data["selling_price"],
                    brand=data.get("brand", ""),
                    color=data.get("color", ""),
                    product_name=data.get("product_name", ""),
                )

                # Store in session
                request.session["clothing_barcode_batch"] = session_data
                request.session.modified = True

                # Redirect to Step 2 (scanning)
                return redirect("verticals:clothing_barcode_add_step2")

            except ValidationError as e:
                # Add validation errors to form
                form.add_error(None, str(e))
    else:
        form = BarcodeAddStep1Form()

    ctx.update(
        {
            "form": form,
            "is_manager": is_manager,
            "page_title": "Add Barcoded Items - Step 1",
        }
    )

    return render(request, "verticals/clothing/barcode_add_step1.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def barcode_add_step2(request):
    """
    Barcode Add - Step 2: Scanning loop.

    Flow:
    1. Show progress: "Scanned X / QTY"
    2. Open scanner (camera or manual input)
    3. On scan:
       - POST barcode to API endpoint
       - API creates ClothingBarcodeUnit record
       - If scanned < qty -> re-open scanner automatically
       - If scanned == qty -> redirect to success page

    Features:
    - Back button to Step 1 (preserves session data)
    - Inline error messages (duplicate barcode, invalid format, etc.)
    - NO popup alerts
    - Progress bar

    Session data required:
    - clothing_barcode_batch (from Step 1)
    """
    ctx = base.base_context(request)

    # Get session data
    session_data = request.session.get("clothing_barcode_batch")
    if not session_data:
        messages.error(request, "No batch session found. Please complete Step 1 first.")
        return redirect("verticals:clothing_barcode_add_step1")

    quantity = session_data.get("quantity", 1)
    scanned_count = session_data.get("scanned_count", 0)
    remaining = quantity - scanned_count
    progress_pct = int((scanned_count / quantity) * 100) if quantity > 0 else 0

    # Check if complete
    if scanned_count >= quantity:
        # Clear session and redirect to success
        del request.session["clothing_barcode_batch"]
        request.session.modified = True
        messages.success(request, f"✅ All {quantity} items scanned successfully!")
        return redirect("verticals:clothing_dashboard_v2")

    ctx.update(
        {
            "session_data": session_data,
            "quantity": quantity,
            "scanned_count": scanned_count,
            "remaining": remaining,
            "progress_pct": progress_pct,
            "page_title": f"Scanning {session_data.get('category', 'Items')}",
        }
    )

    return render(request, "verticals/clothing/barcode_add_step2.html", ctx)


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

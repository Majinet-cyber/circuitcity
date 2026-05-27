# inventory/views_liquor.py
"""
Views for liquor store operations: sales, credits, payments, stock edit requests.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional, Any

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum, F
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.decorators import manager_required
from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.helpers import get_active_business
from inventory.models import MerchProduct
from inventory.models_verticals import (
    LiquorSale,
    LiquorCredit,
    LiquorCreditPayment,
    LiquorStockEditRequest,
    LiquorWalletEntry,
    LiquorUnitType,
    LiquorSaleType,
    LiquorCreditStatus,
    LiquorCreditPaymentStatus,
    LiquorStockEditRequestStatus,
    MonthlySalesTarget,
)
from tenants.utils import require_business


# ==============================================================================
# LIQUOR SALES
# ==============================================================================


class LiquorSellForm(forms.Form):
    """Form for selling liquor (bottle or shot)"""

    product = forms.ModelChoiceField(
        queryset=MerchProduct.objects.none(), widget=forms.Select(attrs={"class": "form-control", "id": "id_product"})
    )
    unit = forms.ChoiceField(
        choices=LiquorUnitType.choices,
        initial=LiquorUnitType.BOTTLE,
        widget=forms.Select(attrs={"class": "form-control", "id": "id_unit"}),
    )
    quantity = forms.IntegerField(
        min_value=1, initial=1, widget=forms.NumberInput(attrs={"class": "form-control", "id": "id_quantity"})
    )
    unit_price = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "id": "id_unit_price"}),
    )
    sale_type = forms.ChoiceField(
        choices=LiquorSaleType.choices,
        initial=LiquorSaleType.SALE,
        widget=forms.Select(attrs={"class": "form-control", "id": "id_sale_type"}),
    )
    customer_name = forms.CharField(
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Required for credit sales"}),
    )
    customer_phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional"}),
    )
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}))

    def __init__(self, business=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if business:
            self.fields["product"].queryset = MerchProduct.objects.filter(
                business=business, kind=BusinessKind.LIQUOR, is_active=True
            ).order_by("name")

    def clean(self):
        cleaned_data = super().clean()
        sale_type = cleaned_data.get("sale_type")
        customer_name = cleaned_data.get("customer_name")
        product = cleaned_data.get("product")
        unit = cleaned_data.get("unit")

        # If credit sale, require customer name
        if sale_type == LiquorSaleType.CREDIT and not customer_name:
            raise forms.ValidationError("Customer name is required for credit sales.")

        # If shot is selected but product doesn't have shots
        if unit == LiquorUnitType.SHOT and product and not product.has_shots:
            raise forms.ValidationError(f"{product.name} does not support shot sales.")

        return cleaned_data


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def sell_liquor(request):
    """Sell liquor (bottle or shot) - Gamified flow"""
    business = get_active_business(request)

    # Safely get membership and subscription
    membership = getattr(request, "membership", None)
    subscription = None
    try:
        subscription = getattr(business, "subscription", None)
    except Exception:
        # Business has no subscription yet (trial or free tier)
        subscription = None

    # Get or auto-start active shift (prevents "no active shift" blocking)
    location = getattr(request, "location", None)
    active_shift = get_or_start_active_shift(request.user, business, location)

    # No warning needed - shift is always available now

    if request.method == "POST":
        # POST logic remains intact - handle sale recording
        # Extract POST data directly (no form validation for speed)
        try:
            # Validate and extract product_id
            product_id_str = request.POST.get("product_id", "").strip()
            if not product_id_str:
                messages.error(request, "❌ Please select a product.")
                return redirect("liquor:sell")

            try:
                product_id = int(product_id_str)
            except (ValueError, TypeError):
                messages.error(request, "❌ Invalid product selected.")
                return redirect("liquor:sell")

            if product_id <= 0:
                messages.error(request, "❌ Please select a valid product.")
                return redirect("liquor:sell")

            # Validate and extract quantity
            quantity_str = request.POST.get("quantity", "1").strip()
            try:
                quantity = int(quantity_str)
            except (ValueError, TypeError):
                quantity = 1

            if quantity <= 0:
                messages.error(request, "❌ Quantity must be at least 1.")
                return redirect("liquor:sell")

            # CRITICAL: Default mode is "bottle" (NOT crate) - bottle-first selling
            mode = request.POST.get("mode", "bottle")  # "bottle", "shot", or "glass"
            sale_type = request.POST.get("sale_type", "cash")  # "cash" or "credit"
            customer_name = request.POST.get("customer_name", "").strip()
            customer_phone = request.POST.get("customer_phone", "").strip()
            notes = request.POST.get("notes", "").strip()

            # Payment mix amounts (if provided) - safe Decimal conversion
            try:
                cash_amount = Decimal(str(request.POST.get("cash_amount", "0") or "0"))
            except (ValueError, TypeError, InvalidOperation):
                cash_amount = Decimal("0.00")

            try:
                bank_amount = Decimal(str(request.POST.get("bank_amount", "0") or "0"))
            except (ValueError, TypeError, InvalidOperation):
                bank_amount = Decimal("0.00")

            try:
                mobile_money_amount = Decimal(str(request.POST.get("mobile_money_amount", "0") or "0"))
            except (ValueError, TypeError, InvalidOperation):
                mobile_money_amount = Decimal("0.00")

            # Get price based on mode - validate product exists first (no locking yet)
            try:
                product = MerchProduct.objects.get(
                    pk=product_id, business=business, kind=BusinessKind.LIQUOR, is_active=True
                )
            except MerchProduct.DoesNotExist:
                messages.error(request, "❌ Product not found or not available.")
                return redirect("liquor:sell")

            # Validate credit sale requires customer name
            if sale_type == "credit" and not customer_name:
                messages.error(request, "❌ Customer name is required for credit sales.")
                return redirect("liquor:sell")

            # Map mode to unit
            if mode == "shot":
                unit = "shot"
            elif mode == "glass":
                unit = "glass"
            else:
                unit = "bottle"

            # CRITICAL FIX: Use liquor unit helper for correct pricing
            from inventory.helpers_liquor_units import get_liquor_unit_info
            
            unit_info = get_liquor_unit_info(product)
            default_unit_price = unit_info["unit_price"]
            
            # Check if user provided an override price
            try:
                override_price_str = request.POST.get("unit_price", "").strip()
                if override_price_str:
                    unit_price = Decimal(str(override_price_str))
                    # Validate override price is positive
                    if unit_price <= 0:
                        messages.error(request, "❌ Price must be greater than zero.")
                        return redirect("liquor:sell")
                else:
                    unit_price = default_unit_price
            except (ValueError, TypeError, InvalidOperation):
                # Fall back to default if override is invalid
                unit_price = default_unit_price
            
            # Validate unit price is set
            if unit_price == Decimal("0.00"):
                messages.error(request, f"❌ {product.name} does not have a price per {unit} set.")
                return redirect("liquor:sell")

            # Use the centralized liquor sale service (handles all transaction logic)
            from inventory.services.liquor_sale import create_liquor_sale, OutOfStockError

            try:
                result = create_liquor_sale(
                    business=business,
                    product_id=product_id,
                    user=request.user,
                    quantity=quantity,
                    unit=unit,
                    unit_price=unit_price,
                    sale_type=sale_type,
                    customer_name=customer_name,
                    customer_phone=customer_phone,
                    notes=notes,
                    cash_amount=cash_amount,
                    bank_amount=bank_amount,
                    mobile_money_amount=mobile_money_amount,
                    shift=active_shift,
                )

                if result["ok"]:
                    messages.success(request, f"✅ {result['message']}")
                else:
                    messages.error(request, f"❌ {result.get('error', 'Sale failed')}")

            except OutOfStockError as e:
                messages.error(request, f"❌ {str(e)}")
            except ValidationError as e:
                messages.error(request, f"❌ {str(e)}")
            except Exception as e:
                # Catch any unexpected errors including TransactionManagementError
                import logging

                logger = logging.getLogger(__name__)
                logger.error(
                    f"Unexpected error in liquor sell: {e}",
                    exc_info=True,
                    extra={
                        "business_id": business.id if business else None,
                        "product_id": product_id,
                        "quantity": quantity,
                        "user_id": request.user.id if request.user.is_authenticated else None,
                    },
                )
                # Never show raw DB errors to users
                if "select_for_update" in str(e).lower() or "transaction" in str(e).lower():
                    messages.error(request, "❌ Sale failed: Database error. Please try again.")
                else:
                    messages.error(request, f"❌ Sale failed: {str(e)}")

            return redirect("liquor:sell")

        except (ValueError, KeyError) as e:
            messages.error(request, f"❌ Sale failed: Invalid input. {str(e)}")
            return redirect("liquor:sell")
        except Exception as e:
            # Catch any unexpected errors to prevent 500
            import logging

            logger = logging.getLogger(__name__)
            logger.error(
                f"Unexpected error in liquor sell: {e}",
                exc_info=True,
                extra={
                    "business_id": getattr(business, "id", None) if business else None,
                    "user_id": request.user.id if request.user.is_authenticated else None,
                },
            )
            # Never show raw DB errors to users
            if "select_for_update" in str(e).lower() or "transaction" in str(e).lower():
                messages.error(request, "❌ Sale failed: Database error. Please try again.")
            else:
                messages.error(request, "❌ Sale failed: An unexpected error occurred. Please try again.")
            return redirect("liquor:sell")

    # GET: Build category-grouped products
    from collections import defaultdict
    from inventory.helpers_liquor_units import get_liquor_unit_info, get_bottle_breakdown

    products = MerchProduct.objects.filter(
        business=business, kind=BusinessKind.LIQUOR, is_archived=False, is_active=True
    ).order_by("category", "name")

    products_by_category = defaultdict(list)
    for p in products:
        cat = (p.category or "").lower()
        if cat:
            qty = p.quantity_in_stock or 0
            p.current_stock = qty
            p.is_in_stock = qty > 0

            # Correct low-stock threshold per unit type
            if cat in ("spirits", "whiskey") and p.shots_per_bottle:
                # Low stock = less than 1 bottle worth of shots
                p.is_low_stock = 0 < qty <= p.shots_per_bottle
            elif cat == "wine" and p.glasses_per_bottle:
                p.is_low_stock = 0 < qty <= p.glasses_per_bottle
            else:
                p.is_low_stock = 0 < qty <= 5

            # Bottle breakdown for display (spirits/wine)
            breakdown = get_bottle_breakdown(p)
            p.bb_full_bottles = breakdown["full_bottles"]
            p.bb_partial_units = breakdown["partial_units"]
            p.bb_units_per_bottle = breakdown["units_per_bottle"]
            p.bb_has_open_bottle = breakdown["has_open_bottle"]
            p.bb_display_text = breakdown["display_text"]
            p.bb_total_label = breakdown["total_label"]
            p.bb_unit_label = breakdown["unit_label"]

            # Computed unit pricing info
            unit_info = get_liquor_unit_info(p)
            p.computed_unit_price = unit_info["unit_price"]
            p.computed_unit_cost = unit_info["unit_cost"]
            p.computed_unit_label = unit_info["label"]
            p.computed_max_quantity = unit_info["max_quantity"]

            # Override displayed prices if product-specific prices are not set
            if not p.price_per_bottle and unit_info["sale_unit"] == "bottle":
                p.price_per_bottle = unit_info["unit_price"]
                p.cost_per_bottle = unit_info["unit_cost"]
            if not p.price_per_shot and unit_info["sale_unit"] == "shot":
                p.price_per_shot = unit_info["unit_price"]
                p.cost_per_shot = unit_info["unit_cost"]
            if not p.price_per_glass and unit_info["sale_unit"] == "glass":
                p.price_per_glass = unit_info["unit_price"]
                p.cost_per_glass = unit_info["unit_cost"]

            products_by_category[cat].append(p)

    # Build categories list in order, but include only those that have products
    category_order = ["beer", "cider", "wine", "spirits", "whiskey"]
    categories = [cat for cat in category_order if cat in products_by_category]

    recent_sales = LiquorSale.objects.filter(business=business).select_related("product", "sold_by", "shift")[:10]

    return render(
        request,
        "inventory/liquor/sell.html",
        {
            "categories": categories,
            "products_by_category": dict(products_by_category),
            "recent_sales": recent_sales,
            "business": business,
            "membership": membership,
            "subscription": subscription,
            "active_shift": active_shift,
            "active_tab": "sell",
        },
    )


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def sales_list(request):
    """List all liquor sales"""
    business = get_active_business(request)
    sales = (
        LiquorSale.objects.filter(business=business)
        .select_related("product", "sold_by", "linked_credit")
        .order_by("-sold_at")
    )

    # Filter by type
    sale_type = request.GET.get("type")
    if sale_type:
        sales = sales.filter(sale_type=sale_type)

    return render(
        request,
        "inventory/liquor/sales_list.html",
        {
            "sales": sales,
            "business": business,
        },
    )


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def get_product_pricing(request, product_id):
    """API endpoint to get pricing for a product"""
    business = get_active_business(request)
    try:
        product = MerchProduct.objects.get(pk=product_id, business=business, kind=BusinessKind.LIQUOR)
        
        # CRITICAL FIX: Use liquor unit helper for correct unit pricing
        from inventory.helpers_liquor_units import get_liquor_unit_info
        
        unit_info = get_liquor_unit_info(product)
        
        return JsonResponse(
            {
                "success": True,
                "has_shots": product.has_shots,
                "has_glasses": product.has_glasses,
                "price_per_bottle": str(unit_info["unit_price"]) if unit_info["sale_unit"] == "bottle" else str(product.price_per_bottle or "0.00"),
                "price_per_shot": str(unit_info["unit_price"]) if unit_info["sale_unit"] == "shot" else str(product.price_per_shot or "0.00"),
                "price_per_glass": str(unit_info["unit_price"]) if unit_info["sale_unit"] == "glass" else str(product.price_per_glass or "0.00"),
                "sellable_shots": product.sellable_shots_per_bottle,
                "unit_label": unit_info["label"],
                "max_quantity": unit_info["max_quantity"],
                "sale_unit": unit_info["sale_unit"],
            }
        )
    except MerchProduct.DoesNotExist:
        return JsonResponse({"success": False, "error": "Product not found"})


# ==============================================================================
# CREDIT MANAGEMENT
# ==============================================================================


class ConvertToCreditForm(forms.Form):
    """Form for converting a sale to credit"""

    customer_name = forms.CharField(max_length=120, widget=forms.TextInput(attrs={"class": "form-control"}))
    customer_phone = forms.CharField(
        max_length=20, required=False, widget=forms.TextInput(attrs={"class": "form-control"})
    )
    claim_from_sale = forms.BooleanField(
        required=False,
        initial=True,
        label="Convert existing cash sale to credit?",
        help_text="If checked, this will convert the selected sale. If unchecked, creates fresh credit.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
@manager_required
def convert_sale_to_credit(request, sale_id):
    """Convert a cash sale to credit"""
    business = get_active_business(request)
    sale = get_object_or_404(LiquorSale, pk=sale_id, business=business)

    if sale.is_credit:
        messages.warning(request, "This sale is already marked as credit.")
        return redirect("liquor:sales_list")

    if request.method == "POST":
        form = ConvertToCreditForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data

            with transaction.atomic():
                if data["claim_from_sale"]:
                    # Convert sale to credit
                    sale.sale_type = LiquorSaleType.CREDIT
                    sale.is_credit = True
                    sale.save(update_fields=["sale_type", "is_credit"])

                    # Create credit record
                    credit = LiquorCredit.objects.create(
                        business=business,
                        customer_name=data["customer_name"],
                        customer_phone=data.get("customer_phone", ""),
                        amount=sale.total_price,
                        related_sale=sale,
                        created_by=request.user,
                        notes=f"Converted from sale #{sale.id}",
                    )

                    sale.linked_credit = credit
                    sale.save(update_fields=["linked_credit"])

                    messages.success(request, f"Sale #{sale.id} converted to credit for {data['customer_name']}")
                else:
                    # Create fresh credit (don't touch the sale)
                    credit = LiquorCredit.objects.create(
                        business=business,
                        customer_name=data["customer_name"],
                        customer_phone=data.get("customer_phone", ""),
                        amount=sale.total_price,
                        created_by=request.user,
                        notes=f"Fresh credit based on sale #{sale.id}",
                    )
                    messages.success(request, f"New credit created for {data['customer_name']}")

            return redirect("liquor:credits_list")
    else:
        form = ConvertToCreditForm()

    return render(
        request,
        "inventory/liquor/convert_to_credit.html",
        {
            "form": form,
            "sale": sale,
            "business": business,
        },
    )


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def credits_list(request):
    """List all credits with metrics"""
    from django.db.models import Sum, Count, Q
    from decimal import Decimal

    business = get_active_business(request)
    credits_qs = LiquorCredit.objects.filter(business=business).select_related("created_by", "related_sale__product").order_by("-created_at")

    # Filter by status
    status = request.GET.get("status")
    if status:
        credits_qs = credits_qs.filter(status=status)

    # Search
    search = request.GET.get("search", "").strip()
    if search:
        from django.db.models import Q
        credits_qs = credits_qs.filter(
            Q(customer_name__icontains=search) | Q(customer_phone__icontains=search)
        )

    # Credit metrics (all, not filtered)
    all_credits = LiquorCredit.objects.filter(business=business)
    outstanding_count = all_credits.filter(status__in=["open", "partial"]).count()
    outstanding_total = all_credits.filter(status__in=["open", "partial"]).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")
    outstanding_balance = all_credits.filter(status__in=["open", "partial"]).aggregate(
        bal=Sum("amount") - Sum("amount_paid")
    )["bal"] or Decimal("0.00")
    cleared_this_month = all_credits.filter(
        status="settled",
        settled_at__year=timezone.now().year,
        settled_at__month=timezone.now().month,
    ).count()

    return render(
        request,
        "inventory/liquor/credits_list.html",
        {
            "credits": credits_qs,
            "business": business,
            "outstanding_count": outstanding_count,
            "outstanding_total": outstanding_total,
            "outstanding_balance": outstanding_balance,
            "cleared_this_month": cleared_this_month,
            "active_status_filter": status,
            "search_query": search,
        },
    )


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def record_credit_sale(request):
    """
    Dedicated credit sale recording flow.
    Records a credit directly without going through the POS sell flow.
    """
    from decimal import Decimal
    from inventory.models import MerchProduct

    business = get_active_business(request)

    if request.method == "POST":
        try:
            customer_name = request.POST.get("customer_name", "").strip()
            customer_phone = request.POST.get("customer_phone", "").strip()
            notes = request.POST.get("notes", "").strip()
            product_id_raw = request.POST.get("product_id", "").strip()
            quantity_raw = request.POST.get("quantity", "1").strip()
            unit_price_raw = request.POST.get("unit_price", "").strip()
            unit = request.POST.get("unit", "bottle")

            if not customer_name:
                messages.error(request, "Customer name is required.")
                return redirect("liquor:record_credit_sale")

            if not product_id_raw:
                messages.error(request, "Please select a product.")
                return redirect("liquor:record_credit_sale")

            product = get_object_or_404(MerchProduct, pk=int(product_id_raw), business=business, kind=BusinessKind.LIQUOR)
            quantity = max(1, int(quantity_raw)) if quantity_raw.isdigit() else 1

            if not unit_price_raw:
                # Use canonical price
                from inventory.helpers_liquor_units import get_liquor_unit_info
                unit_info = get_liquor_unit_info(product)
                unit_price = unit_info["unit_price"]
            else:
                unit_price = Decimal(unit_price_raw)

            if unit_price <= 0:
                messages.error(request, "Unit price must be greater than zero.")
                return redirect("liquor:record_credit_sale")

            total = Decimal(quantity) * unit_price

            with transaction.atomic():
                # Decrement stock
                from django.db.models import F
                updated = MerchProduct.objects.filter(
                    pk=product.pk, quantity_in_stock__gte=quantity
                ).update(quantity_in_stock=F("quantity_in_stock") - quantity)

                if not updated and product.track_inventory:
                    messages.error(request, f"Insufficient stock for {product.name}.")
                    return redirect("liquor:record_credit_sale")

                # Create sale record
                sale = LiquorSale.objects.create(
                    business=business,
                    product=product,
                    unit=unit,
                    quantity=quantity,
                    unit_price=unit_price,
                    total_price=total,
                    unit_cost=product.get_cost_for_unit(unit) or Decimal("0.00"),
                    total_cost=(product.get_cost_for_unit(unit) or Decimal("0.00")) * quantity,
                    sale_type=LiquorSaleType.CREDIT,
                    is_credit=True,
                    sold_by=request.user,
                    notes=notes,
                    payment_method="cash",  # placeholder
                )

                # Create credit record
                credit = LiquorCredit.objects.create(
                    business=business,
                    customer_name=customer_name,
                    customer_phone=customer_phone,
                    amount=total,
                    amount_paid=Decimal("0.00"),
                    status=LiquorCreditStatus.OPEN,
                    notes=notes or f"{product.name} - {quantity} {unit}",
                    related_sale=sale,
                    created_by=request.user,
                )

                sale.linked_credit = credit
                sale.save(update_fields=["linked_credit"])

            messages.success(request, f"Credit sale recorded: {customer_name} owes MK {total:,.0f} for {product.name}.")
            return redirect("liquor:credits_list")

        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Credit sale recording failed: {e}", exc_info=True)
            messages.error(request, f"Failed to record credit sale: {str(e)}")
            return redirect("liquor:record_credit_sale")

    # GET: Show form
    products = MerchProduct.objects.filter(
        business=business, kind=BusinessKind.LIQUOR, is_active=True, is_archived=False
    ).order_by("category", "name")

    return render(request, "inventory/liquor/record_credit_sale.html", {
        "business": business,
        "products": products,
        "active_tab": "credits",
    })


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def credit_detail(request, credit_id):
    """View credit details and payments"""
    business = get_active_business(request)
    credit = get_object_or_404(LiquorCredit, pk=credit_id, business=business)
    payments = credit.payments.select_related("paid_by", "reviewed_by").order_by("-created_at")

    return render(
        request,
        "inventory/liquor/credit_detail.html",
        {
            "credit": credit,
            "payments": payments,
            "business": business,
        },
    )


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def credit_statement_print(request, credit_id):
    """Print-friendly credit statement — also used for WhatsApp/PDF share."""
    business = get_active_business(request)
    credit = get_object_or_404(LiquorCredit, pk=credit_id, business=business)
    payments = credit.payments.select_related("paid_by").order_by("created_at")
    return render(
        request,
        "inventory/liquor/credit_statement_print.html",
        {
            "credit": credit,
            "payments": payments,
            "business": business,
        },
    )


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
@manager_required
@require_POST
def clear_credit(request, credit_id):
    """
    Manager clears/settles a credit (confirms customer has paid).
    This converts the credit into revenue immediately.
    """
    business = get_active_business(request)
    credit = get_object_or_404(LiquorCredit, pk=credit_id, business=business)

    # Check if already settled
    if credit.status == LiquorCreditStatus.SETTLED:
        messages.warning(request, f"Credit for {credit.customer_name} is already settled.")
        return redirect("liquor:credits_list")

    with transaction.atomic():
        # Mark credit as settled
        credit.status = LiquorCreditStatus.SETTLED
        credit.amount_paid = credit.amount
        credit.settled_at = timezone.now()
        credit.settled_by = request.user
        credit.save(update_fields=["status", "amount_paid", "settled_at", "settled_by"])

        # Create wallet entry for the cleared credit (now it's real income)
        LiquorWalletEntry.objects.create(
            business=business,
            amount=credit.amount,
            description=f"Credit cleared: {credit.customer_name} - {credit.notes or 'No notes'}",
            entry_type="income",
            created_by=request.user,
        )

        messages.success(
            request, f"✅ Credit cleared for {credit.customer_name}! MK {credit.amount:,.2f} now included in revenue."
        )

    return redirect("liquor:credits_list")


# ==============================================================================
# CREDIT PAYMENT SUBMISSION (Bartenders)
# ==============================================================================


class CreditPaymentForm(forms.Form):
    """Form for submitting credit payment (bartender)"""

    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    transaction_id = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. TXN123456"}),
    )
    proof_file = forms.FileField(required=False, widget=forms.FileInput(attrs={"class": "form-control"}))

    def clean(self):
        cleaned_data = super().clean()
        transaction_id = cleaned_data.get("transaction_id")
        proof_file = cleaned_data.get("proof_file")

        # Require at least one: transaction ID or proof file
        if not transaction_id and not proof_file:
            raise forms.ValidationError("Please provide either a transaction ID or upload proof of payment.")

        return cleaned_data


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def submit_credit_payment(request, credit_id):
    """Bartender submits payment for credit (requires proof)"""
    business = get_active_business(request)
    credit = get_object_or_404(LiquorCredit, pk=credit_id, business=business)

    if credit.status == LiquorCreditStatus.SETTLED:
        messages.warning(request, "This credit is already settled.")
        return redirect("liquor:credit_detail", credit_id=credit.id)

    if request.method == "POST":
        form = CreditPaymentForm(request.POST, request.FILES)
        if form.is_valid():
            data = form.cleaned_data

            payment = LiquorCreditPayment.objects.create(
                credit=credit,
                amount=data["amount"],
                transaction_id=data.get("transaction_id", ""),
                proof_file=data.get("proof_file"),
                paid_by=request.user,
                status=LiquorCreditPaymentStatus.PENDING,
            )

            messages.success(request, "Payment submitted for approval.")
            return redirect("liquor:credit_detail", credit_id=credit.id)
    else:
        form = CreditPaymentForm(initial={"amount": credit.balance})

    return render(
        request,
        "inventory/liquor/submit_payment.html",
        {
            "form": form,
            "credit": credit,
            "business": business,
        },
    )


# ==============================================================================
# CREDIT PAYMENT APPROVAL (Managers)
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
@manager_required
def pending_payments(request):
    """Manager view of pending credit payments"""
    business = get_active_business(request)
    payments = (
        LiquorCreditPayment.objects.filter(credit__business=business, status=LiquorCreditPaymentStatus.PENDING)
        .select_related("credit", "paid_by")
        .order_by("-created_at")
    )

    return render(
        request,
        "inventory/liquor/pending_payments.html",
        {
            "payments": payments,
            "business": business,
        },
    )


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
@manager_required
@require_POST
def approve_payment(request, payment_id):
    """Manager approves a credit payment"""
    business = get_active_business(request)
    payment = get_object_or_404(
        LiquorCreditPayment, pk=payment_id, credit__business=business, status=LiquorCreditPaymentStatus.PENDING
    )

    with transaction.atomic():
        payment.approve(request.user)

        # Create wallet entry
        LiquorWalletEntry.objects.create(
            business=business,
            amount=payment.amount,
            description=f"Credit payment from {payment.credit.customer_name}",
            entry_type="income",
            related_payment=payment,
            created_by=request.user,
        )

    messages.success(request, f"Payment of {payment.amount} approved and credit updated.")
    return redirect("liquor:pending_payments")


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
@manager_required
@require_POST
def reject_payment(request, payment_id):
    """Manager rejects a credit payment"""
    business = get_active_business(request)
    payment = get_object_or_404(
        LiquorCreditPayment, pk=payment_id, credit__business=business, status=LiquorCreditPaymentStatus.PENDING
    )

    reason = request.POST.get("reason", "No reason provided")
    payment.reject(request.user, reason)

    messages.warning(request, f"Payment rejected. Reason: {reason}")
    return redirect("liquor:pending_payments")


# ==============================================================================
# STOCK EDIT REQUESTS (Bartenders)
# ==============================================================================


class StockEditRequestForm(forms.Form):
    """Form for bartenders to request stock edits"""

    requested_changes = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        help_text="Describe the changes you want to make (e.g., 'Change quantity from 10 to 15')",
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}), help_text="Explain why this change is needed"
    )


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def request_stock_edit(request, product_id):
    """Bartender requests permission to edit stock"""
    business = get_active_business(request)
    product = get_object_or_404(MerchProduct, pk=product_id, business=business, kind=BusinessKind.LIQUOR)

    if request.method == "POST":
        form = StockEditRequestForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data

            stock_request = LiquorStockEditRequest.objects.create(
                business=business,
                product=product,
                requested_changes={"description": data["requested_changes"]},
                reason=data["reason"],
                requested_by=request.user,
            )

            messages.success(request, "Stock edit request submitted for manager approval.")
            return redirect("verticals:liquor_dashboard")
    else:
        form = StockEditRequestForm()

    return render(
        request,
        "inventory/liquor/request_stock_edit.html",
        {
            "form": form,
            "product": product,
            "business": business,
        },
    )


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
@manager_required
def stock_edit_requests(request):
    """Manager view of stock edit requests"""
    business = get_active_business(request)
    requests_qs = (
        LiquorStockEditRequest.objects.filter(business=business, status=LiquorStockEditRequestStatus.PENDING)
        .select_related("product", "requested_by")
        .order_by("-created_at")
    )

    return render(
        request,
        "inventory/liquor/stock_edit_requests.html",
        {
            "requests": requests_qs,
            "business": business,
        },
    )


# ==============================================================================
# STOCK SETTINGS (Managers)
# ==============================================================================


class LiquorStockSettingsForm(forms.Form):
    """Form for editing business-level liquor stock settings"""

    beer_target = forms.IntegerField(
        min_value=0, initial=600, widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"})
    )
    cider_target = forms.IntegerField(
        min_value=0, initial=600, widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"})
    )
    spirits_target = forms.IntegerField(
        min_value=0, initial=600, widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"})
    )
    whiskey_target = forms.IntegerField(
        min_value=0, initial=600, widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"})
    )
    wine_target = forms.IntegerField(
        min_value=0, initial=600, widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"})
    )
    other_target = forms.IntegerField(
        min_value=0, initial=600, widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"})
    )
    default_auto_adjust_pct = forms.IntegerField(
        min_value=0,
        max_value=200,
        initial=20,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0", "max": "200"}),
        label="Default Auto-Adjust Percentage",
        help_text="Default percentage to increase targets over peak demand (typically 20%)",
    )
    auto_adjust_lookback_days = forms.IntegerField(
        min_value=1,
        max_value=90,
        initial=30,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "1", "max": "90"}),
        label="Auto-Adjust Lookback Period (Days)",
        help_text="Number of days to analyze when calculating peak demand (typically 30)",
    )


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
@manager_required
def stock_settings(request):
    """Edit business-level stock settings"""
    from inventory.models_verticals import LiquorStockSettings

    business = get_active_business(request)

    # Get or create settings
    settings, created = LiquorStockSettings.objects.get_or_create(
        business=business,
        defaults={
            "beer_target": 600,
            "cider_target": 600,
            "spirits_target": 600,
            "whiskey_target": 600,
            "wine_target": 600,
            "other_target": 600,
            "default_auto_adjust_pct": 20,
            "auto_adjust_lookback_days": 30,
        },
    )

    if request.method == "POST":
        form = LiquorStockSettingsForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data

            settings.beer_target = data["beer_target"]
            settings.cider_target = data["cider_target"]
            settings.spirits_target = data["spirits_target"]
            settings.whiskey_target = data["whiskey_target"]
            settings.wine_target = data["wine_target"]
            settings.other_target = data["other_target"]
            settings.default_auto_adjust_pct = data["default_auto_adjust_pct"]
            settings.auto_adjust_lookback_days = data["auto_adjust_lookback_days"]
            settings.save()

            messages.success(request, "Stock settings updated successfully.")
            return redirect("liquor:stock_overview")
    else:
        initial = {
            "beer_target": settings.beer_target,
            "cider_target": settings.cider_target,
            "spirits_target": settings.spirits_target,
            "whiskey_target": settings.whiskey_target,
            "wine_target": settings.wine_target,
            "other_target": settings.other_target,
            "default_auto_adjust_pct": settings.default_auto_adjust_pct,
            "auto_adjust_lookback_days": settings.auto_adjust_lookback_days,
        }
        form = LiquorStockSettingsForm(initial=initial)

    return render(
        request,
        "inventory/liquor/stock_settings.html",
        {
            "form": form,
            "settings": settings,
            "business": business,
        },
    )


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
@manager_required
@require_POST
def update_category_target(request, category):
    """Update target for a specific category (AJAX endpoint)"""
    from inventory.models_verticals import LiquorStockSettings
    from decimal import Decimal

    business = get_active_business(request)

    # Validate category
    valid_categories = ["beer", "cider", "spirits", "whiskey", "wine", "other"]
    if category not in valid_categories:
        return JsonResponse({"success": False, "error": "Invalid category"}, status=400)

    # Get or create settings
    settings, created = LiquorStockSettings.objects.get_or_create(
        business=business,
        defaults={
            "beer_target": 600,
            "cider_target": 600,
            "spirits_target": 600,
            "whiskey_target": 600,
            "wine_target": 600,
            "other_target": 600,
            "default_auto_adjust_pct": 20,
            "auto_adjust_lookback_days": 30,
        },
    )

    # Get new target from POST
    try:
        new_target = int(request.POST.get("target", 0))
        if new_target < 0:
            return JsonResponse({"success": False, "error": "Target must be non-negative"}, status=400)
    except (ValueError, TypeError):
        return JsonResponse({"success": False, "error": "Invalid target value"}, status=400)

    # Update the appropriate field
    field_name = f"{category}_target"
    setattr(settings, field_name, new_target)
    settings.save(update_fields=[field_name])

    messages.success(request, f"Updated {category.title()} target to {new_target} bottles.")

    return JsonResponse(
        {
            "success": True,
            "category": category,
            "new_target": new_target,
            "message": f"Updated {category.title()} target to {new_target} bottles.",
        }
    )


# ==============================================================================
# SHIFT MANAGEMENT
# ==============================================================================


def get_active_shift(request) -> Optional[Any]:
    """Get the currently active shift for the logged-in user"""
    from inventory.models_verticals import LiquorShift, LiquorShiftStatus

    business = get_active_business(request)
    return (
        LiquorShift.objects.filter(business=business, barman=request.user, status=LiquorShiftStatus.OPEN)
        .order_by("-started_at")
        .first()
    )


def get_or_start_active_shift(user, business, location=None):
    """
    Get the currently active shift for the user, or create one automatically if missing.

    This prevents "no active shift" errors from blocking liquor flows.
    Idempotent: won't create duplicates if a shift already exists.

    Args:
        user: The user/barman
        business: The business instance
        location: Optional location (defaults to business default location if None)

    Returns:
        LiquorShift instance (existing or newly created)
    """
    from inventory.models_verticals import LiquorShift, LiquorShiftStatus, LiquorShiftStock
    from inventory.models import Location, MerchProduct
    from tenants.models import BusinessKind
    from django.db import transaction

    # Check if user already has an active shift
    existing_shift = (
        LiquorShift.objects.filter(business=business, barman=user, status=LiquorShiftStatus.OPEN)
        .order_by("-started_at")
        .first()
    )

    if existing_shift:
        return existing_shift

    # No active shift - create one automatically
    if location is None:
        location = Location.default_for(business)

    with transaction.atomic():
        shift = LiquorShift.objects.create(
            business=business,
            location=location,
            barman=user,
            created_by=user,
            opening_notes="Auto-started shift (no manual count)",
        )

        # Create opening stock snapshots with zero counts for all active liquor products
        products = MerchProduct.objects.filter(business=business, kind=BusinessKind.LIQUOR, is_active=True).order_by(
            "category", "name"
        )

        for product in products:
            LiquorShiftStock.objects.create(
                shift=shift,
                product=product,
                bottles_count=0,  # Default to 0 since we don't have actual counts
                shots_count=0,
                snapshot_type="opening",
                recorded_by=user,
            )

    return shift


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def active_shift_status(request):
    """API endpoint to check if user has an active shift"""
    shift = get_active_shift(request)
    if shift:
        return JsonResponse(
            {
                "has_active_shift": True,
                "shift_id": shift.id,
                "started_at": shift.started_at.isoformat(),
                "is_stale": shift.is_stale(),
            }
        )
    return JsonResponse({"has_active_shift": False})


class StartShiftForm(forms.Form):
    """Form for starting a new shift"""

    location = forms.ModelChoiceField(
        queryset=None, required=False, widget=forms.Select(attrs={"class": "form-control"})
    )
    opening_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 2, "placeholder": "Any notes about the opening stock..."}
        ),
    )

    def __init__(self, business=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if business:
            from inventory.models import Location

            self.fields["location"].queryset = Location.objects.filter(business=business)


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def start_shift(request):
    """Start a new shift with opening stock count"""
    from inventory.models_verticals import LiquorShift, LiquorShiftStock
    from inventory.models import Location

    business = get_active_business(request)

    # Check if user already has an active shift
    existing_shift = get_active_shift(request)
    if existing_shift:
        messages.warning(
            request,
            f"You already have an active shift (started {existing_shift.started_at.strftime('%H:%M %d/%m/%Y')}). Close it before starting a new one.",
        )
        return redirect("liquor:close_shift", shift_id=existing_shift.id)

    if request.method == "POST":
        form = StartShiftForm(business, request.POST)
        if form.is_valid():
            with transaction.atomic():
                location = form.cleaned_data.get("location") or Location.default_for(business)

                # Create the shift
                shift = LiquorShift.objects.create(
                    business=business,
                    location=location,
                    barman=request.user,
                    created_by=request.user,
                    opening_notes=form.cleaned_data.get("opening_notes", ""),
                )

                # Get all active liquor products
                products = MerchProduct.objects.filter(
                    business=business, kind=BusinessKind.LIQUOR, is_active=True
                ).order_by("category", "name")

                # Create opening stock snapshots for each product
                for product in products:
                    # Get current stock counts from POST data
                    bottles_key = f"bottles_{product.id}"
                    shots_key = f"shots_{product.id}"

                    bottles_count = int(request.POST.get(bottles_key, 0))
                    shots_count = int(request.POST.get(shots_key, 0)) if product.has_shots else 0

                    LiquorShiftStock.objects.create(
                        shift=shift,
                        product=product,
                        bottles_count=bottles_count,
                        shots_count=shots_count,
                        snapshot_type="opening",
                        recorded_by=request.user,
                    )

                messages.success(request, f"Shift started successfully! Record all sales during your shift.")
                return redirect("liquor:sell")
    else:
        form = StartShiftForm(business)

    # Get all active liquor products grouped by category
    products = MerchProduct.objects.filter(business=business, kind=BusinessKind.LIQUOR, is_active=True).order_by(
        "category", "name"
    )

    # Group products by category
    from itertools import groupby

    products_by_category = {}
    for category, items in groupby(products, key=lambda p: p.category or "other"):
        products_by_category[category] = list(items)

    return render(
        request,
        "inventory/liquor/start_shift.html",
        {
            "form": form,
            "business": business,
            "products_by_category": products_by_category,
        },
    )


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def close_shift(request, shift_id):
    """Close a shift with closing stock count and variance calculation"""
    from inventory.models_verticals import LiquorShift, LiquorShiftStock, LiquorShiftStatus

    business = get_active_business(request)
    shift = get_object_or_404(LiquorShift, pk=shift_id, business=business, status=LiquorShiftStatus.OPEN)

    # Only the barman or a manager can close the shift
    if not (shift.barman == request.user or _is_manager(request.user)):
        messages.error(request, "You can only close your own shifts.")
        return redirect("verticals:liquor_dashboard")

    if request.method == "POST":
        with transaction.atomic():
            # Get opening stock
            opening_stock = {stock.product_id: stock for stock in shift.stock_snapshots.filter(snapshot_type="opening")}

            # Record closing stock
            products = MerchProduct.objects.filter(business=business, kind=BusinessKind.LIQUOR, is_active=True)

            total_variance_value = Decimal("0.00")

            for product in products:
                bottles_key = f"bottles_{product.id}"
                shots_key = f"shots_{product.id}"

                bottles_count = int(request.POST.get(bottles_key, 0))
                shots_count = int(request.POST.get(shots_key, 0)) if product.has_shots else 0

                # Create closing stock snapshot
                LiquorShiftStock.objects.create(
                    shift=shift,
                    product=product,
                    bottles_count=bottles_count,
                    shots_count=shots_count,
                    snapshot_type="closing",
                    recorded_by=request.user,
                )

                # Calculate variance
                opening = opening_stock.get(product.id)
                if opening:
                    # Expected: opening + purchases - sales
                    # For now, assume no purchases during shift (can enhance later)

                    # Calculate sold from shift sales
                    shift_sales = shift.sales.filter(product=product)
                    sold_bottles = shift_sales.filter(unit="bottle").aggregate(total=Sum("quantity"))["total"] or 0
                    sold_shots = shift_sales.filter(unit="shot").aggregate(total=Sum("quantity"))["total"] or 0

                    # Expected closing
                    expected_bottles = opening.bottles_count - sold_bottles
                    expected_shots = opening.shots_count - sold_shots

                    # Handle shot/bottle conversion if needed
                    if product.has_shots and expected_shots < 0:
                        # Convert bottles to shots
                        bottles_needed = abs(expected_shots) // product.sellable_shots_per_bottle + 1
                        expected_bottles -= bottles_needed
                        expected_shots += bottles_needed * product.sellable_shots_per_bottle

                    # Variance (negative = missing stock)
                    variance_bottles = bottles_count - expected_bottles
                    variance_shots = shots_count - expected_shots

                    # Calculate monetary value of variance
                    if product.cost_per_bottle and variance_bottles != 0:
                        total_variance_value += variance_bottles * product.cost_per_bottle
                    if product.cost_per_shot and variance_shots != 0:
                        total_variance_value += variance_shots * product.cost_per_shot

            # Calculate shift totals
            shift_sales = shift.sales.all()

            total_sales = shift_sales.aggregate(total=Sum("total_price"))["total"] or Decimal("0.00")
            total_cost = shift_sales.aggregate(total=Sum("total_cost"))["total"] or Decimal("0.00")
            total_credit = shift_sales.filter(is_credit=True).aggregate(total=Sum("total_price"))["total"] or Decimal(
                "0.00"
            )
            total_free = shift_sales.filter(is_free=True).aggregate(total=Sum("total_price"))["total"] or Decimal(
                "0.00"
            )

            # Update shift
            shift.ended_at = timezone.now()
            shift.status = LiquorShiftStatus.CLOSED
            shift.total_sales_amount = total_sales
            shift.total_cost_amount = total_cost
            shift.total_profit_amount = total_sales - total_cost
            shift.total_credit_amount = total_credit
            shift.total_free_amount = total_free
            shift.missing_stock_value = abs(total_variance_value) if total_variance_value < 0 else Decimal("0.00")
            shift.closing_notes = request.POST.get("closing_notes", "")
            shift.save()

            messages.success(
                request,
                f"Shift closed successfully! Total sales: MK {total_sales:,.2f}, Profit: MK {shift.total_profit_amount:,.2f}",
            )
            return redirect("liquor:shift_report", shift_id=shift.id)

    # Get opening stock to display
    opening_stock = shift.stock_snapshots.filter(snapshot_type="opening").select_related("product")

    # Group by category
    from itertools import groupby

    stock_by_category = {}
    for category, items in groupby(opening_stock, key=lambda s: s.product.category or "other"):
        stock_by_category[category] = list(items)

    return render(
        request,
        "inventory/liquor/close_shift.html",
        {
            "shift": shift,
            "business": business,
            "stock_by_category": stock_by_category,
        },
    )


def _is_manager(user):
    """Check if user is a manager"""
    try:
        from core.decorators import _is_manager as core_is_manager

        return core_is_manager(user)
    except ImportError:
        # Fallback
        return user.is_staff or user.is_superuser


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def shift_report(request, shift_id):
    """View detailed shift report with variance analysis"""
    from inventory.models_verticals import LiquorShift
    from django.db.models import Sum, F

    business = get_active_business(request)
    shift = get_object_or_404(LiquorShift, pk=shift_id, business=business)

    # Get opening and closing stock
    opening_stock = {
        stock.product_id: stock
        for stock in shift.stock_snapshots.filter(snapshot_type="opening").select_related("product")
    }
    closing_stock = {
        stock.product_id: stock
        for stock in shift.stock_snapshots.filter(snapshot_type="closing").select_related("product")
    }

    # Calculate variance for each product
    variance_data = []
    for product_id, opening in opening_stock.items():
        closing = closing_stock.get(product_id)
        if not closing:
            continue

        product = opening.product

        # Calculate sales
        sales = shift.sales.filter(product=product)
        sold_bottles = sales.filter(unit="bottle").aggregate(total=Sum("quantity"))["total"] or 0
        sold_shots = sales.filter(unit="shot").aggregate(total=Sum("quantity"))["total"] or 0

        # Expected closing
        expected_bottles = opening.bottles_count - sold_bottles
        expected_shots = opening.shots_count - sold_shots

        # Variance
        variance_bottles = closing.bottles_count - expected_bottles
        variance_shots = closing.shots_count - expected_shots if product.has_shots else 0

        # Monetary value
        variance_value = Decimal("0.00")
        if variance_bottles != 0 and product.cost_per_bottle:
            variance_value += variance_bottles * product.cost_per_bottle
        if variance_shots != 0 and product.cost_per_shot:
            variance_value += variance_shots * product.cost_per_shot

        if variance_bottles != 0 or variance_shots != 0:
            variance_data.append(
                {
                    "product": product,
                    "opening_bottles": opening.bottles_count,
                    "opening_shots": opening.shots_count,
                    "sold_bottles": sold_bottles,
                    "sold_shots": sold_shots,
                    "expected_bottles": expected_bottles,
                    "expected_shots": expected_shots,
                    "closing_bottles": closing.bottles_count,
                    "closing_shots": closing.shots_count,
                    "variance_bottles": variance_bottles,
                    "variance_shots": variance_shots,
                    "variance_value": variance_value,
                }
            )

    # Top products by profit
    top_products = (
        shift.sales.values("product__name")
        .annotate(
            total_profit=Sum(F("total_price") - F("total_cost")),
            total_sales=Sum("total_price"),
            quantity_sold=Sum("quantity"),
        )
        .order_by("-total_profit")[:5]
    )

    return render(
        request,
        "inventory/liquor/shift_report.html",
        {
            "shift": shift,
            "business": business,
            "variance_data": variance_data,
            "top_products": top_products,
        },
    )


# ==============================================================================
# STOCK OVERVIEW
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def stock_overview(request):
    """
    Stock overview with category batteries using configurable per-product and business-level targets.
    """
    from inventory.liquor_utils import get_stock_overview_data, recalculate_liquor_targets_for_business

    business = get_active_business(request)
    location = getattr(request, "active_location", None)
    is_manager = _is_manager(request.user)

    # Handle auto-adjust trigger (managers only)
    if request.method == "POST" and is_manager and "trigger_auto_adjust" in request.POST:
        try:
            updated = recalculate_liquor_targets_for_business(business)
            if updated:
                count = len(updated)
                messages.success(request, f"Auto-adjusted targets for {count} product(s) based on recent sales data.")
            else:
                messages.info(request, "No products required target adjustment at this time.")
            return redirect("liquor:stock_overview")
        except Exception as e:
            messages.error(request, f"Error during auto-adjust: {str(e)}")

    # Get stock overview data using the new utility function
    data = get_stock_overview_data(business, location)

    ctx = {
        "business": business,
        "location": location,
        "categories": data["categories"],
        "totals": data["totals"],
        "warnings": data["warnings"],
        "settings": data["settings"],
        "is_manager": is_manager,
        "active_tab": "stock_overview",
    }
    return render(request, "verticals/liquor/stock_overview.html", ctx)


# ==============================================================================
# BUSINESS INSIGHTS API
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def business_insights_api(request):
    """
    API endpoint for liquor dashboard Business Insights.
    
    Returns:
    - Revenue trend (last 7/30 days)
    - Top selling items (top 5)
    - Low stock alerts count
    - Stock value summary
    """
    from datetime import timedelta
    from django.db.models import Sum, Count, Q
    from django.db.models.functions import TruncDate
    
    business = get_active_business(request)
    
    if not business:
        return JsonResponse({"error": "No active business found"}, status=400)
    
    # Get date range from request (default to 30 days)
    days = int(request.GET.get("days", 30))
    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)
    
    # Revenue trend by day
    # Use database-safe date grouping
    from django.conf import settings
    from django.db import connection
    
    sales = LiquorSale.objects.filter(
        business=business,
        sold_at__gte=start_date,
        sold_at__lte=end_date
    )
    
    # Database-agnostic date grouping
    if connection.vendor == 'sqlite':
        # SQLite: use DATE() function
        from django.db.models import Func, DateField
        
        class SQLiteDate(Func):
            function = 'DATE'
            output_field = DateField()
        
        revenue_by_day = (
            sales
            .annotate(date=SQLiteDate('sold_at'))
            .values('date')
            .annotate(
                revenue=Sum('total_price'),
                count=Count('id')
            )
            .order_by('date')
        )
    else:
        # PostgreSQL: use TruncDate
        revenue_by_day = (
            sales
            .annotate(date=TruncDate('sold_at'))
            .values('date')
            .annotate(
                revenue=Sum('total_price'),
                count=Count('id')
            )
            .order_by('date')
        )
    
    # Convert to list of dicts with string dates
    revenue_trend = [
        {
            'date': item['date'].isoformat() if item['date'] else None,
            'revenue': float(item['revenue'] or 0),
            'count': item['count']
        }
        for item in revenue_by_day
    ]
    
    # Top selling items (top 5 by revenue)
    top_items = (
        sales
        .values('product__name', 'product__category')
        .annotate(
            revenue=Sum('total_price'),
            quantity=Sum('quantity'),
            count=Count('id')
        )
        .order_by('-revenue')[:5]
    )
    
    top_items_list = [
        {
            'name': item['product__name'],
            'category': item['product__category'],
            'revenue': float(item['revenue'] or 0),
            'quantity': item['quantity'],
            'sales_count': item['count']
        }
        for item in top_items
    ]
    
    # Low stock alerts (products with stock <= 5)
    low_stock_products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.LIQUOR,
        is_active=True,
        quantity_in_stock__lte=5,
        quantity_in_stock__gt=0
    )
    low_stock_count = low_stock_products.count()
    
    # Out of stock count
    out_of_stock_count = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.LIQUOR,
        is_active=True,
        quantity_in_stock=0
    ).count()
    
    # Total stock value
    products_with_stock = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.LIQUOR,
        is_active=True,
        quantity_in_stock__gt=0
    )
    
    total_stock_value = Decimal("0.00")
    for product in products_with_stock:
        if product.cost_per_bottle:
            total_stock_value += product.quantity_in_stock * product.cost_per_bottle
    
    # Total revenue / count for period
    total_revenue = sales.exclude(is_free=True).aggregate(total=Sum('total_price'))['total'] or Decimal("0.00")
    total_sales_count = sales.count()

    # Cash today (payment method breakdown for period)
    from inventory.models_verticals import PaymentMethod as _PM
    today_cash = sales.filter(payment_method=_PM.CASH, is_credit=False, is_free=False).aggregate(
        t=Sum('total_price'))['t'] or Decimal("0.00")

    # Credit issued in period
    today_credit_issued = sales.filter(is_credit=True).aggregate(
        t=Sum('total_price'))['t'] or Decimal("0.00")

    # Outstanding credit (total balance owed across all time)
    outstanding_credit_data = LiquorCredit.objects.filter(
        business=business, status__in=['open', 'partial']
    ).aggregate(
        total=Sum('amount'),
        paid=Sum('amount_paid'),
        cnt=Count('id')
    )
    outstanding_credit_bal = (outstanding_credit_data['total'] or Decimal("0.00")) - \
                              (outstanding_credit_data['paid'] or Decimal("0.00"))
    open_credits_count = outstanding_credit_data['cnt'] or 0

    # Repeat debtors: customers with 2+ credits still open
    repeat_debtors = LiquorCredit.objects.filter(
        business=business, status__in=['open', 'partial']
    ).values('customer_name').annotate(cnt=Count('id')).filter(cnt__gte=2).count()

    # Today's profit estimate (revenue - cost of goods sold for period)
    period_cogs = sales.exclude(is_credit=True).aggregate(t=Sum('total_cost'))['t'] or Decimal("0.00")
    today_profit = total_revenue - period_cogs

    # Best seller today (by revenue)
    today_best_seller = top_items_list[0]['name'] if top_items_list else None

    # Low stock items list (for alerts panel)
    low_stock_items_list = [
        {'name': p.name, 'stock_display': f'{p.quantity_in_stock} units'}
        for p in low_stock_products[:4]
    ]
    out_of_stock_items_list = [
        {'name': p.name}
        for p in MerchProduct.objects.filter(
            business=business, kind=BusinessKind.LIQUOR, is_active=True, quantity_in_stock=0
        )[:3]
    ]

    return JsonResponse({
        'ok': True,
        'period_days': days,
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'revenue_trend': revenue_trend,
        'top_items': top_items_list,
        'low_stock_count': low_stock_count,
        'low_stock_items': low_stock_items_list,
        'out_of_stock_count': out_of_stock_count,
        'out_of_stock_items': out_of_stock_items_list,
        'total_stock_value': float(total_stock_value),
        'total_revenue': float(total_revenue),
        'total_sales_count': total_sales_count,
        # Today-specific fields (meaningful when days=1, useful anytime)
        'today_revenue': float(total_revenue),
        'today_cash': float(today_cash),
        'today_credit_issued': float(today_credit_issued),
        'outstanding_credit': float(outstanding_credit_bal),
        'open_credits_count': open_credits_count,
        'today_profit': float(today_profit),
        'today_best_seller': today_best_seller,
        'today_sales_count': total_sales_count,
        'repeat_debtors': repeat_debtors,
    })

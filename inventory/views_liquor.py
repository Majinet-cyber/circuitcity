# inventory/views_liquor.py
"""
Views for liquor store operations: sales, credits, payments, stock edit requests.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Any

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
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
    LiquorSale, LiquorCredit, LiquorCreditPayment, LiquorStockEditRequest,
    LiquorWalletEntry, LiquorUnitType, LiquorSaleType, LiquorCreditStatus,
    LiquorCreditPaymentStatus, LiquorStockEditRequestStatus, MonthlySalesTarget
)
from tenants.utils import require_business


# ==============================================================================
# LIQUOR SALES
# ==============================================================================

class LiquorSellForm(forms.Form):
    """Form for selling liquor (bottle or shot)"""
    product = forms.ModelChoiceField(
        queryset=MerchProduct.objects.none(),
        widget=forms.Select(attrs={"class": "form-control", "id": "id_product"})
    )
    unit = forms.ChoiceField(
        choices=LiquorUnitType.choices,
        initial=LiquorUnitType.BOTTLE,
        widget=forms.Select(attrs={"class": "form-control", "id": "id_unit"})
    )
    quantity = forms.IntegerField(
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "id": "id_quantity"})
    )
    unit_price = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "id": "id_unit_price"})
    )
    sale_type = forms.ChoiceField(
        choices=LiquorSaleType.choices,
        initial=LiquorSaleType.SALE,
        widget=forms.Select(attrs={"class": "form-control", "id": "id_sale_type"})
    )
    customer_name = forms.CharField(
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Required for credit sales"})
    )
    customer_phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional"})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2})
    )
    
    def __init__(self, business=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if business:
            self.fields["product"].queryset = MerchProduct.objects.filter(
                business=business,
                kind=BusinessKind.LIQUOR,
                is_active=True
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
            product_id = int(request.POST.get("product_id", 0))
            quantity = int(request.POST.get("quantity", 1))
            mode = request.POST.get("mode", "bottle")  # "bottle" or "shot"
            
            product = MerchProduct.objects.get(
                pk=product_id,
                business=business,
                kind=BusinessKind.LIQUOR,
                is_active=True
            )
            
            # Map mode to unit
            unit = LiquorUnitType.SHOT if mode == "shot" else LiquorUnitType.BOTTLE
            
            # Validate shot sales
            if mode == "shot" and not product.has_shots:
                messages.error(request, f"{product.name} does not support shot sales.")
                return redirect("liquor:sell")
            
            # Get price
            unit_price = product.price_per_shot if mode == "shot" else product.price_per_bottle
            
            with transaction.atomic():
                # Calculate cost for profit tracking
                unit_cost = product.get_cost_for_unit(unit)
                total_cost = Decimal(quantity) * unit_cost
                
                # Calculate total price
                total = Decimal(quantity) * unit_price
                
                # Create sale (always cash for quick flow; free/credit can use old form if needed)
                sale = LiquorSale.objects.create(
                    business=business,
                    product=product,
                    shift=active_shift,
                    unit=unit,
                    quantity=quantity,
                    unit_price=unit_price,
                    total_price=total,
                    unit_cost=unit_cost,
                    total_cost=total_cost,
                    sale_type=LiquorSaleType.SALE,
                    sold_by=request.user,
                    notes=""
                )
                
                # Create wallet entry for cash sale
                LiquorWalletEntry.objects.create(
                    business=business,
                    amount=total,
                    description=f"Sale: {product.name} ({quantity} {unit})",
                    entry_type="income",
                    related_sale=sale,
                    created_by=request.user
                )
            
            messages.success(request, f"Sold {quantity} × {product.name} ({mode})")
            return redirect("liquor:sell")
            
        except (ValueError, MerchProduct.DoesNotExist, KeyError) as e:
            messages.error(request, f"Sale failed: {e}")
            return redirect("liquor:sell")
    
    # GET: Build category-grouped products
    from collections import defaultdict
    
    products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.LIQUOR,
        is_archived=False,
        is_active=True
    ).order_by("category", "name")
    
    products_by_category = defaultdict(list)
    for p in products:
        cat = (p.category or "").lower()
        if cat:
            products_by_category[cat].append(p)
    
    # Build categories list in order, but include only those that have products
    category_order = ["beer", "cider", "wine", "spirits", "whiskey"]
    categories = [cat for cat in category_order if cat in products_by_category]
    
    recent_sales = LiquorSale.objects.filter(business=business).select_related("product", "sold_by", "shift")[:10]
    
    return render(request, "inventory/liquor/sell.html", {
        "categories": categories,
        "products_by_category": dict(products_by_category),
        "recent_sales": recent_sales,
        "business": business,
        "membership": membership,
        "subscription": subscription,
        "active_shift": active_shift,
        "active_tab": "sell",
    })


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def sales_list(request):
    """List all liquor sales"""
    business = get_active_business(request)
    sales = LiquorSale.objects.filter(business=business).select_related("product", "sold_by", "linked_credit").order_by("-sold_at")
    
    # Filter by type
    sale_type = request.GET.get("type")
    if sale_type:
        sales = sales.filter(sale_type=sale_type)
    
    return render(request, "inventory/liquor/sales_list.html", {
        "sales": sales,
        "business": business,
    })


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def get_product_pricing(request, product_id):
    """API endpoint to get pricing for a product"""
    business = get_active_business(request)
    try:
        product = MerchProduct.objects.get(pk=product_id, business=business, kind=BusinessKind.LIQUOR)
        return JsonResponse({
            "success": True,
            "has_shots": product.has_shots,
            "price_per_bottle": str(product.price_per_bottle or "0.00"),
            "price_per_shot": str(product.price_per_shot or "0.00"),
            "sellable_shots": product.sellable_shots_per_bottle,
        })
    except MerchProduct.DoesNotExist:
        return JsonResponse({"success": False, "error": "Product not found"})


# ==============================================================================
# CREDIT MANAGEMENT
# ==============================================================================

class ConvertToCreditForm(forms.Form):
    """Form for converting a sale to credit"""
    customer_name = forms.CharField(
        max_length=120,
        widget=forms.TextInput(attrs={"class": "form-control"})
    )
    customer_phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"})
    )
    claim_from_sale = forms.BooleanField(
        required=False,
        initial=True,
        label="Convert existing cash sale to credit?",
        help_text="If checked, this will convert the selected sale. If unchecked, creates fresh credit.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"})
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
                        notes=f"Converted from sale #{sale.id}"
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
                        notes=f"Fresh credit based on sale #{sale.id}"
                    )
                    messages.success(request, f"New credit created for {data['customer_name']}")
            
            return redirect("liquor:credits_list")
    else:
        form = ConvertToCreditForm()
    
    return render(request, "inventory/liquor/convert_to_credit.html", {
        "form": form,
        "sale": sale,
        "business": business,
    })


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def credits_list(request):
    """List all credits"""
    business = get_active_business(request)
    credits = LiquorCredit.objects.filter(business=business).select_related("created_by").order_by("-created_at")
    
    # Filter by status
    status = request.GET.get("status")
    if status:
        credits = credits.filter(status=status)
    
    return render(request, "inventory/liquor/credits_list.html", {
        "credits": credits,
        "business": business,
    })


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def credit_detail(request, credit_id):
    """View credit details and payments"""
    business = get_active_business(request)
    credit = get_object_or_404(LiquorCredit, pk=credit_id, business=business)
    payments = credit.payments.select_related("paid_by", "reviewed_by").order_by("-created_at")
    
    return render(request, "inventory/liquor/credit_detail.html", {
        "credit": credit,
        "payments": payments,
        "business": business,
    })


# ==============================================================================
# CREDIT PAYMENT SUBMISSION (Bartenders)
# ==============================================================================

class CreditPaymentForm(forms.Form):
    """Form for submitting credit payment (bartender)"""
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"})
    )
    transaction_id = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. TXN123456"})
    )
    proof_file = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={"class": "form-control"})
    )
    
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
                status=LiquorCreditPaymentStatus.PENDING
            )
            
            messages.success(request, "Payment submitted for approval.")
            return redirect("liquor:credit_detail", credit_id=credit.id)
    else:
        form = CreditPaymentForm(initial={"amount": credit.balance})
    
    return render(request, "inventory/liquor/submit_payment.html", {
        "form": form,
        "credit": credit,
        "business": business,
    })


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
    payments = LiquorCreditPayment.objects.filter(
        credit__business=business,
        status=LiquorCreditPaymentStatus.PENDING
    ).select_related("credit", "paid_by").order_by("-created_at")
    
    return render(request, "inventory/liquor/pending_payments.html", {
        "payments": payments,
        "business": business,
    })


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
@manager_required
@require_POST
def approve_payment(request, payment_id):
    """Manager approves a credit payment"""
    business = get_active_business(request)
    payment = get_object_or_404(
        LiquorCreditPayment,
        pk=payment_id,
        credit__business=business,
        status=LiquorCreditPaymentStatus.PENDING
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
            created_by=request.user
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
        LiquorCreditPayment,
        pk=payment_id,
        credit__business=business,
        status=LiquorCreditPaymentStatus.PENDING
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
        help_text="Describe the changes you want to make (e.g., 'Change quantity from 10 to 15')"
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        help_text="Explain why this change is needed"
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
                requested_by=request.user
            )
            
            messages.success(request, "Stock edit request submitted for manager approval.")
            return redirect("verticals:liquor_dashboard")
    else:
        form = StockEditRequestForm()
    
    return render(request, "inventory/liquor/request_stock_edit.html", {
        "form": form,
        "product": product,
        "business": business,
    })


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
@manager_required
def stock_edit_requests(request):
    """Manager view of stock edit requests"""
    business = get_active_business(request)
    requests_qs = LiquorStockEditRequest.objects.filter(
        business=business,
        status=LiquorStockEditRequestStatus.PENDING
    ).select_related("product", "requested_by").order_by("-created_at")
    
    return render(request, "inventory/liquor/stock_edit_requests.html", {
        "requests": requests_qs,
        "business": business,
    })


# ==============================================================================
# STOCK SETTINGS (Managers)
# ==============================================================================

class LiquorStockSettingsForm(forms.Form):
    """Form for editing business-level liquor stock settings"""
    beer_target = forms.IntegerField(
        min_value=0, initial=600,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"})
    )
    cider_target = forms.IntegerField(
        min_value=0, initial=600,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"})
    )
    spirits_target = forms.IntegerField(
        min_value=0, initial=600,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"})
    )
    whiskey_target = forms.IntegerField(
        min_value=0, initial=600,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"})
    )
    wine_target = forms.IntegerField(
        min_value=0, initial=600,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"})
    )
    other_target = forms.IntegerField(
        min_value=0, initial=600,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"})
    )
    default_auto_adjust_pct = forms.IntegerField(
        min_value=0, max_value=200, initial=20,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0", "max": "200"}),
        label="Default Auto-Adjust Percentage",
        help_text="Default percentage to increase targets over peak demand (typically 20%)"
    )
    auto_adjust_lookback_days = forms.IntegerField(
        min_value=1, max_value=90, initial=30,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "1", "max": "90"}),
        label="Auto-Adjust Lookback Period (Days)",
        help_text="Number of days to analyze when calculating peak demand (typically 30)"
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
        }
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
    
    return render(request, "inventory/liquor/stock_settings.html", {
        "form": form,
        "settings": settings,
        "business": business,
    })


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
        }
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
    
    return JsonResponse({
        "success": True,
        "category": category,
        "new_target": new_target,
        "message": f"Updated {category.title()} target to {new_target} bottles."
    })


# ==============================================================================
# SHIFT MANAGEMENT
# ==============================================================================

def get_active_shift(request) -> Optional[Any]:
    """Get the currently active shift for the logged-in user"""
    from inventory.models_verticals import LiquorShift, LiquorShiftStatus
    business = get_active_business(request)
    return LiquorShift.objects.filter(
        business=business,
        barman=request.user,
        status=LiquorShiftStatus.OPEN
    ).order_by("-started_at").first()


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
    existing_shift = LiquorShift.objects.filter(
        business=business,
        barman=user,
        status=LiquorShiftStatus.OPEN
    ).order_by("-started_at").first()
    
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
            opening_notes="Auto-started shift (no manual count)"
        )
        
        # Create opening stock snapshots with zero counts for all active liquor products
        products = MerchProduct.objects.filter(
            business=business,
            kind=BusinessKind.LIQUOR,
            is_active=True
        ).order_by("category", "name")
        
        for product in products:
            LiquorShiftStock.objects.create(
                shift=shift,
                product=product,
                bottles_count=0,  # Default to 0 since we don't have actual counts
                shots_count=0,
                snapshot_type="opening",
                recorded_by=user
            )
    
    return shift


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def active_shift_status(request):
    """API endpoint to check if user has an active shift"""
    shift = get_active_shift(request)
    if shift:
        return JsonResponse({
            "has_active_shift": True,
            "shift_id": shift.id,
            "started_at": shift.started_at.isoformat(),
            "is_stale": shift.is_stale(),
        })
    return JsonResponse({"has_active_shift": False})


class StartShiftForm(forms.Form):
    """Form for starting a new shift"""
    location = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(attrs={"class": "form-control"})
    )
    opening_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Any notes about the opening stock..."})
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
        messages.warning(request, f"You already have an active shift (started {existing_shift.started_at.strftime('%H:%M %d/%m/%Y')}). Close it before starting a new one.")
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
                    opening_notes=form.cleaned_data.get("opening_notes", "")
                )
                
                # Get all active liquor products
                products = MerchProduct.objects.filter(
                    business=business,
                    kind=BusinessKind.LIQUOR,
                    is_active=True
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
                        recorded_by=request.user
                    )
                
                messages.success(request, f"Shift started successfully! Record all sales during your shift.")
                return redirect("liquor:sell")
    else:
        form = StartShiftForm(business)
    
    # Get all active liquor products grouped by category
    products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.LIQUOR,
        is_active=True
    ).order_by("category", "name")
    
    # Group products by category
    from itertools import groupby
    products_by_category = {}
    for category, items in groupby(products, key=lambda p: p.category or "other"):
        products_by_category[category] = list(items)
    
    return render(request, "inventory/liquor/start_shift.html", {
        "form": form,
        "business": business,
        "products_by_category": products_by_category,
    })


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def close_shift(request, shift_id):
    """Close a shift with closing stock count and variance calculation"""
    from inventory.models_verticals import LiquorShift, LiquorShiftStock, LiquorShiftStatus
    
    business = get_active_business(request)
    shift = get_object_or_404(
        LiquorShift,
        pk=shift_id,
        business=business,
        status=LiquorShiftStatus.OPEN
    )
    
    # Only the barman or a manager can close the shift
    if not (shift.barman == request.user or _is_manager(request.user)):
        messages.error(request, "You can only close your own shifts.")
        return redirect("verticals:liquor_dashboard")
    
    if request.method == "POST":
        with transaction.atomic():
            # Get opening stock
            opening_stock = {
                stock.product_id: stock 
                for stock in shift.stock_snapshots.filter(snapshot_type="opening")
            }
            
            # Record closing stock
            products = MerchProduct.objects.filter(
                business=business,
                kind=BusinessKind.LIQUOR,
                is_active=True
            )
            
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
                    recorded_by=request.user
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
            total_credit = shift_sales.filter(is_credit=True).aggregate(total=Sum("total_price"))["total"] or Decimal("0.00")
            total_free = shift_sales.filter(is_free=True).aggregate(total=Sum("total_price"))["total"] or Decimal("0.00")
            
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
            
            messages.success(request, f"Shift closed successfully! Total sales: MK {total_sales:,.2f}, Profit: MK {shift.total_profit_amount:,.2f}")
            return redirect("liquor:shift_report", shift_id=shift.id)
    
    # Get opening stock to display
    opening_stock = shift.stock_snapshots.filter(snapshot_type="opening").select_related("product")
    
    # Group by category
    from itertools import groupby
    stock_by_category = {}
    for category, items in groupby(opening_stock, key=lambda s: s.product.category or "other"):
        stock_by_category[category] = list(items)
    
    return render(request, "inventory/liquor/close_shift.html", {
        "shift": shift,
        "business": business,
        "stock_by_category": stock_by_category,
    })


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
            variance_data.append({
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
            })
    
    # Top products by profit
    top_products = shift.sales.values(
        "product__name"
    ).annotate(
        total_profit=Sum(F("total_price") - F("total_cost")),
        total_sales=Sum("total_price"),
        quantity_sold=Sum("quantity")
    ).order_by("-total_profit")[:5]
    
    return render(request, "inventory/liquor/shift_report.html", {
        "shift": shift,
        "business": business,
        "variance_data": variance_data,
        "top_products": top_products,
    })


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
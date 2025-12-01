# inventory/views_liquor.py
"""
Views for liquor store operations: sales, credits, payments, stock edit requests.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from inventory.authz import require_business_kind, manager_required
from inventory.business_kinds import BusinessKind
from inventory.helpers import get_active_business
from inventory.models import MerchProduct
from inventory.models_verticals import (
    LiquorSale, LiquorCredit, LiquorCreditPayment, LiquorStockEditRequest,
    LiquorWalletEntry, LiquorUnitType, LiquorSaleType, LiquorCreditStatus,
    LiquorCreditPaymentStatus, LiquorStockEditRequestStatus
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
        widget=forms.Select(attrs={"class": "form-control"})
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
    """Sell liquor (bottle or shot)"""
    business = get_active_business(request)
    
    if request.method == "POST":
        form = LiquorSellForm(business, request.POST)
        if form.is_valid():
            data = form.cleaned_data
            
            with transaction.atomic():
                # Calculate total
                total = Decimal(data["quantity"]) * data["unit_price"]
                
                # Create sale
                sale = LiquorSale.objects.create(
                    business=business,
                    product=data["product"],
                    unit=data["unit"],
                    quantity=data["quantity"],
                    unit_price=data["unit_price"],
                    total_price=total,
                    sale_type=data["sale_type"],
                    sold_by=request.user,
                    notes=data.get("notes", "")
                )
                
                # If credit sale, create credit record
                if data["sale_type"] == LiquorSaleType.CREDIT:
                    credit = LiquorCredit.objects.create(
                        business=business,
                        customer_name=data["customer_name"],
                        customer_phone=data.get("customer_phone", ""),
                        amount=total,
                        related_sale=sale,
                        created_by=request.user
                    )
                    sale.linked_credit = credit
                    sale.save(update_fields=["linked_credit"])
                else:
                    # Create wallet entry for cash sale
                    LiquorWalletEntry.objects.create(
                        business=business,
                        amount=total,
                        description=f"Sale: {data['product'].name} ({data['quantity']} {data['unit']})",
                        entry_type="income",
                        related_sale=sale,
                        created_by=request.user
                    )
            
            messages.success(request, f"Sale recorded: {data['quantity']} {data['unit']} of {data['product'].name}")
            return redirect("inventory:liquor_sales_list")
    else:
        form = LiquorSellForm(business)
    
    recent_sales = LiquorSale.objects.filter(business=business).select_related("product", "sold_by")[:10]
    
    return render(request, "inventory/liquor/sell.html", {
        "form": form,
        "recent_sales": recent_sales,
        "business": business,
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
        return redirect("inventory:liquor_sales_list")
    
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
            
            return redirect("inventory:liquor_credits_list")
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
        return redirect("inventory:liquor_credit_detail", credit_id=credit.id)
    
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
            return redirect("inventory:liquor_credit_detail", credit_id=credit.id)
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
    return redirect("inventory:liquor_pending_payments")


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
    return redirect("inventory:liquor_pending_payments")


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
            return redirect("inventory:liquor_dashboard")
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


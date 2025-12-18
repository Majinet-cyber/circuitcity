# inventory/views_phone_sale_wizard_v2.py
"""
Simplified 3-step Phone Sale Wizard (IMEI → Price → Payment Method).

This is the core selling flow for agents. Every sale must:
- Find in-stock phone by IMEI
- Set selling price
- Choose payment method
- Update ALL numbers (stock, dashboards, wallets, leaderboard)
"""
from __future__ import annotations

from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from tenants.utils import require_business, get_active_business
from tenants.models import Membership
from inventory.models import InventoryItem
from sales.models import Sale, SaleCommission, CommissionConfig

WIZARD_SESSION_KEY = "phone_sale_wizard_v2"


def _clear_wizard(request):
    """Clear wizard session data"""
    if WIZARD_SESSION_KEY in request.session:
        del request.session[WIZARD_SESSION_KEY]
        request.session.modified = True


def _get_wizard_data(request):
    """Get wizard data from session"""
    return request.session.get(WIZARD_SESSION_KEY, {})


def _set_wizard_data(request, data):
    """Save wizard data to session"""
    request.session[WIZARD_SESSION_KEY] = data
    request.session.modified = True


@login_required
@require_business
def phone_sale_wizard_v2(request):
    """
    3-step wizard for selling phones:
    Step 1: IMEI search/scan
    Step 2: Price entry
    Step 3: Payment method & sell
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect('tenants:activate_mine')
    
    wizard_data = _get_wizard_data(request)
    step = int(request.GET.get('step', wizard_data.get('step', 1)))
    
    if step == 1:
        return _step1_imei(request, business, wizard_data)
    elif step == 2:
        return _step2_price(request, business, wizard_data)
    elif step == 3:
        return _step3_payment(request, business, wizard_data)
    else:
        _clear_wizard(request)
        return redirect(reverse('inventory:phone_sale_wizard_v2'))


def _step1_imei(request, business, wizard_data):
    """
    Step 1: IMEI search & scan
    
    User enters/scans IMEI → system checks if it's in stock at their location
    """
    if request.method == 'POST':
        imei = request.POST.get('imei', '').strip()
        
        # Validate IMEI
        if not imei:
            messages.error(request, "IMEI is required.")
        elif len(imei) != 15 or not imei.isdigit():
            messages.error(request, "IMEI must be exactly 15 digits.")
        else:
            # Search for stock item
            # AGENTS CAN SELL ANY UNSOLD PHONE IN BUSINESS INVENTORY
            # No longer filter by assigned_agent - allow agents to sell any business stock
            qs = InventoryItem.objects.filter(
                business=business,
                imei=imei,
                status='IN_STOCK',
                is_active=True
            ).select_related('product', 'current_location')
            
            # No agent filtering - any agent can sell any unsold phone
            # This allows better inventory utilization and flexibility
            
            stock_item = qs.first()
            
            if not stock_item:
                messages.error(
                    request,
                    f"IMEI {imei} is not in stock at your location. "
                    f"Please check the number or ask your manager."
                )
            else:
                # Stock found! Save to wizard and move to price step
                product = stock_item.product
                variant = getattr(product, 'variant', '')
                
                # Build full display name consistent with Scan In
                # Format: BRAND MODEL (RAM+ROM) e.g. "ITEL A90 (3+128)"
                full_product_name = f"{product.brand} {product.model}"
                if variant:
                    full_product_name += f" ({variant})"
                
                wizard_data.update({
                    'step': 2,
                    'imei': imei,
                    'stock_id': stock_item.id,
                    'product_name': full_product_name,
                    'variant': variant,
                    'location': str(stock_item.current_location),
                    'suggested_price': float(stock_item.selling_price or product.sale_price or 0),
                })
                _set_wizard_data(request, wizard_data)
                
                messages.success(
                    request,
                    f"✅ In stock – {wizard_data['product_name']} at {wizard_data['location']}"
                )
                
                return redirect(f"{reverse('inventory:phone_sale_wizard_v2')}?step=2")
    
    # GET: show IMEI form
    return render(request, 'inventory/phone_sale_wizard_v2_step1.html', {
        'step': 1,
        'business': business,
        'wizard_data': wizard_data,
    })


def _step2_price(request, business, wizard_data):
    """
    Step 2: Set selling price
    
    Shows phone summary + price input (pre-filled with suggested price)
    """
    if not wizard_data.get('stock_id'):
        messages.error(request, "Please start from Step 1.")
        return redirect(reverse('inventory:phone_sale_wizard_v2'))
    
    if request.method == 'POST':
        selling_price_str = request.POST.get('selling_price', '').strip()
        
        try:
            selling_price = Decimal(selling_price_str)
            if selling_price <= 0:
                raise ValueError("Price must be positive")
            
            wizard_data['selling_price'] = float(selling_price)
            wizard_data['step'] = 3
            _set_wizard_data(request, wizard_data)
            
            return redirect(f"{reverse('inventory:phone_sale_wizard_v2')}?step=3")
            
        except (ValueError, Exception) as e:
            messages.error(request, f"Invalid price: {e}")
    
    # GET: show price form
    return render(request, 'inventory/phone_sale_wizard_v2_step2.html', {
        'step': 2,
        'business': business,
        'wizard_data': wizard_data,
    })


def _step3_payment(request, business, wizard_data):
    """
    Step 3: Payment method selection & complete sale
    
    Radio cards for Cash / Mobile Money / Bank
    On submit: create Sale, update stock, record commission, update all dashboards
    """
    if not wizard_data.get('stock_id') or not wizard_data.get('selling_price'):
        messages.error(request, "Please complete previous steps.")
        return redirect(reverse('inventory:phone_sale_wizard_v2'))
    
    if request.method == 'POST':
        payment_method = request.POST.get('payment_method', 'CASH')
        
        # Validate payment method
        valid_methods = ['CASH', 'MOBILE_MONEY', 'BANK']
        if payment_method not in valid_methods:
            messages.error(request, "Invalid payment method.")
            return render(request, 'inventory/phone_sale_wizard_v2_step3.html', {
                'step': 3,
                'business': business,
                'wizard_data': wizard_data,
            })
        
        # Execute the sale
        try:
            result = _complete_sale(request, business, wizard_data, payment_method)
            
            _clear_wizard(request)
            
            # Success message - hide IMEI from agents (security best practice)
            is_manager = getattr(request, 'is_manager_plus', False)
            if is_manager:
                success_msg = (
                    f"🎉 Sale recorded! {result['product_name']} (IMEI: {result['imei']}) "
                    f"sold for MK {result['price']:,.0f} – {result['payment_method_display']}"
                )
            else:
                success_msg = (
                    f"🎉 Sale recorded! {result['product_name']} "
                    f"sold for MK {result['price']:,.0f} – {result['payment_method_display']}"
                )
            
            messages.success(request, success_msg)
            
            return redirect('inventory:inventory_dashboard')
            
        except Exception as e:
            messages.error(request, f"Error completing sale: {e}")
    
    # GET: show payment method selection
    return render(request, 'inventory/phone_sale_wizard_v2_step3.html', {
        'step': 3,
        'business': business,
        'wizard_data': wizard_data,
    })


@transaction.atomic
def _complete_sale(request, business, wizard_data, payment_method):
    """
    Complete the sale transaction:
    1. Get stock item
    2. Create Sale record
    3. Mark stock as SOLD
    4. Create commission record (triggers wallet update via signal)
    5. Return sale info
    """
    stock_id = wizard_data['stock_id']
    selling_price = Decimal(str(wizard_data['selling_price']))
    
    # Get stock item (with lock to prevent race conditions)
    # AGENTS CAN SELL ANY UNSOLD PHONE IN BUSINESS
    stock_item = InventoryItem.objects.select_for_update().get(
        id=stock_id,
        business=business
    )
    
    # Validate still in stock
    if stock_item.status != 'IN_STOCK':
        raise ValueError(f"Stock item {stock_item.imei} is no longer in stock.")
    
    # Get agent's location from membership
    try:
        membership = Membership.objects.get(
            user=request.user,
            business=business,
            status='ACTIVE'
        )
        location = membership.location or stock_item.current_location
    except Membership.DoesNotExist:
        location = stock_item.current_location
    
    # Get commission config for this business
    commission_config = CommissionConfig.get_active(business)
    commission_pct = commission_config.base_commission_pct if commission_config else Decimal('10.00')
    
    # Create Sale record (agent is who sold it, regardless of who it was assigned to)
    sale = Sale.objects.create(
        item=stock_item,
        agent=request.user,  # Selling agent
        location=location,
        sold_at=timezone.localdate(),
        price=selling_price,
        commission_pct=commission_pct,
        payment_method=payment_method
    )
    
    # Mark stock as SOLD and track who sold it
    stock_item.status = 'SOLD'
    stock_item.sold_at = timezone.now()
    stock_item.selling_price = selling_price
    stock_item.payment_method = payment_method
    stock_item.sold_by = request.user  # Track selling agent for commission
    stock_item.save(update_fields=['status', 'sold_at', 'selling_price', 'payment_method', 'sold_by'])
    
    # Commission is automatically created by the post_save signal on Sale
    # (see wallet/signals.py: create_commission_on_phone_sale)
    
    return {
        'sale_id': sale.id,
        'product_name': wizard_data['product_name'],
        'imei': wizard_data['imei'],
        'price': selling_price,
        'payment_method': payment_method,
        'payment_method_display': dict(Sale._meta.get_field('payment_method').choices).get(payment_method, payment_method),
    }


@login_required
@require_business
@require_POST
def phone_sale_wizard_v2_reset(request):
    """Reset wizard and start over"""
    _clear_wizard(request)
    messages.info(request, "Wizard reset. Starting fresh!")
    return redirect('inventory:phone_sale_wizard_v2')


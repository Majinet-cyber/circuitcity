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
    Step 2: Set selling price with real-time validation
    
    Shows phone summary + price input (pre-filled with suggested price)
    Provides smart warnings and profit margin feedback
    """
    if not wizard_data.get('stock_id'):
        messages.error(request, "Please start from Step 1.")
        return redirect(reverse('inventory:phone_sale_wizard_v2'))
    
    # Get stock item for cost price
    try:
        stock_item = InventoryItem.objects.select_related('product').get(
            id=wizard_data['stock_id'],
            business=business
        )
        cost_price = stock_item.order_price or getattr(stock_item.product, 'cost_price', None)
        suggested_price = wizard_data.get('suggested_price', 0)
    except InventoryItem.DoesNotExist:
        messages.error(request, "Stock item not found. Please start over.")
        _clear_wizard(request)
        return redirect(reverse('inventory:phone_sale_wizard_v2'))
    
    if request.method == 'POST':
        selling_price_str = request.POST.get('selling_price', '').strip()
        
        try:
            # Parse price (handle commas)
            from inventory.utils_pricing import parse_currency_input, validate_selling_price, format_currency
            
            selling_price = parse_currency_input(selling_price_str)
            
            if selling_price <= 0:
                messages.error(request, "❌ Price must be greater than zero")
                return render(request, 'inventory/phone_sale_wizard_v2_step2.html', {
                    'step': 2,
                    'business': business,
                    'wizard_data': wizard_data,
                    'cost_price': cost_price,
                    'cost_price_formatted': format_currency(cost_price) if cost_price else None,
                })
            
            # Validate price with smart warnings
            validation = validate_selling_price(
                selling_price=selling_price,
                cost_price=cost_price,
                suggested_price=Decimal(str(suggested_price)) if suggested_price else None,
                product_name=wizard_data.get('product_name', '')
            )
            
            # Show warnings but allow user to proceed
            for warning in validation['warnings']:
                messages.warning(request, warning)
            
            # Show positive feedback
            if validation['feedback']:
                messages.success(request, validation['feedback'])
            
            # If invalid (absurd price), block
            if not validation['valid']:
                return render(request, 'inventory/phone_sale_wizard_v2_step2.html', {
                    'step': 2,
                    'business': business,
                    'wizard_data': wizard_data,
                    'cost_price': cost_price,
                    'cost_price_formatted': format_currency(cost_price) if cost_price else None,
                    'validation': validation,
                })
            
            wizard_data['selling_price'] = float(selling_price)
            wizard_data['step'] = 3
            wizard_data['validation'] = validation  # Store for confirmation
            _set_wizard_data(request, wizard_data)
            
            return redirect(f"{reverse('inventory:phone_sale_wizard_v2')}?step=3")
            
        except (ValueError, Exception) as e:
            messages.error(request, f"❌ Invalid price: {e}")
    
    # GET: show price form with formatting
    from inventory.utils_pricing import format_currency
    
    context = {
        'step': 2,
        'business': business,
        'wizard_data': wizard_data,
        'cost_price': cost_price,
        'cost_price_formatted': format_currency(cost_price) if cost_price else None,
        'suggested_price_formatted': format_currency(Decimal(str(suggested_price))) if suggested_price else None,
    }
    
    return render(request, 'inventory/phone_sale_wizard_v2_step2.html', context)


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
            messages.error(request, "❌ Invalid payment method. Please select Cash, Mobile Money, or Bank.")
            return render(request, 'inventory/phone_sale_wizard_v2_step3.html', {
                'step': 3,
                'business': business,
                'wizard_data': wizard_data,
            })
        
        # Execute the sale with comprehensive error handling
        try:
            result = _complete_sale(request, business, wizard_data, payment_method)
            
            _clear_wizard(request)
            
            # Format numbers with commas
            from inventory.utils_pricing import format_currency
            
            price_formatted = format_currency(result['price'])
            
            # Success message - hide IMEI from agents (security best practice)
            is_manager = getattr(request, 'is_manager_plus', False)
            
            # Build success message with profit info
            if result.get('profit') and result['profit'] > 0:
                profit_formatted = format_currency(result['profit'])
                profit_info = f" (Profit: {profit_formatted})"
            else:
                profit_info = ""
            
            if is_manager:
                success_msg = (
                    f"🎉 Sale completed successfully!\n"
                    f"Product: {result['product_name']} (IMEI: {result['imei']})\n"
                    f"Price: {price_formatted} – {result['payment_method_display']}"
                    f"{profit_info}"
                )
            else:
                success_msg = (
                    f"🎉 Sale completed successfully!\n"
                    f"Product: {result['product_name']}\n"
                    f"Price: {price_formatted} – {result['payment_method_display']}"
                    f"{profit_info}"
                )
            
            messages.success(request, success_msg)
            
            # Additional confirmation message
            messages.info(request, f"✅ Sale ID: #{result['sale_id']} – Your commission has been recorded.")
            
            # FIXED: Redirect to phones dashboard (not generic inventory dashboard)
            return redirect('inventory_verticals:phones_dashboard')
            
        except ValueError as e:
            # Business logic errors (user-friendly)
            messages.error(request, f"❌ Sale failed: {str(e)}")
        except Exception as e:
            # Unexpected errors (logged but user-friendly message)
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Unexpected error completing phone sale: {e}", exc_info=True)
            messages.error(
                request,
                "❌ An unexpected error occurred while completing the sale. "
                "Please try again or contact support if the problem persists."
            )
    
    # GET: show payment method selection
    return render(request, 'inventory/phone_sale_wizard_v2_step3.html', {
        'step': 3,
        'business': business,
        'wizard_data': wizard_data,
    })


@transaction.atomic
def _complete_sale(request, business, wizard_data, payment_method):
    """
    Complete the sale transaction with comprehensive error handling:
    1. Get stock item (with lock)
    2. Create Sale record
    3. Mark stock as SOLD
    4. Create commission record (triggers wallet update via signal)
    5. Return sale info
    
    NO HTTP 500s - all errors are caught and raised as ValueError with clear messages.
    """
    try:
        stock_id = wizard_data['stock_id']
        selling_price = Decimal(str(wizard_data['selling_price']))
        
        # Get stock item (with lock to prevent race conditions)
        try:
            stock_item = InventoryItem.objects.select_for_update().get(
                id=stock_id,
                business=business
            )
        except InventoryItem.DoesNotExist:
            raise ValueError("Stock item not found. It may have been sold by another agent.")
        
        # Validate still in stock
        if stock_item.status != 'IN_STOCK':
            raise ValueError(
                f"This phone is no longer available (status: {stock_item.status}). "
                f"It may have been sold by another agent."
            )
        
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
        
        if not location:
            raise ValueError("Unable to determine sale location. Please contact your manager.")
        
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
        
        # Calculate profit for display
        cost_price = stock_item.order_price or getattr(stock_item.product, 'cost_price', Decimal('0'))
        profit = selling_price - cost_price if cost_price else None
        
        return {
            'sale_id': sale.id,
            'product_name': wizard_data['product_name'],
            'imei': wizard_data['imei'],
            'price': selling_price,
            'profit': profit,
            'payment_method': payment_method,
            'payment_method_display': dict(Sale._meta.get_field('payment_method').choices).get(payment_method, payment_method),
        }
    
    except ValueError:
        # Re-raise business logic errors as-is
        raise
    except Exception as e:
        # Catch any unexpected errors and wrap them
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error completing phone sale: {e}", exc_info=True)
        raise ValueError(f"Unable to complete sale: {str(e)}")


@login_required
@require_business
@require_POST
def phone_sale_wizard_v2_reset(request):
    """Reset wizard and start over"""
    _clear_wizard(request)
    messages.info(request, "Wizard reset. Starting fresh!")
    return redirect('inventory:phone_sale_wizard_v2')


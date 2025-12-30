# inventory/views_wizard_liquor_simple.py
"""
SIMPLIFIED Liquor Wizard Handler (2-step flow with Malawi defaults)

REAL-WORLD RULES:
- Beer: bottle/can + crate (20 bottles)
- Cider: bottle/can + 6-pack (6 bottles) - NO CRATES
- Wine: glass (5 per bottle) or bottle
- Spirits/Whisky: shot (30 per bottle) or bottle

NO BARCODE REQUIRED
"""
import json
from decimal import Decimal, InvalidOperation
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db import transaction

from core.decorators import manager_required
from tenants.decorators import require_business_access as require_business
from tenants.middleware import get_active_business
from inventory.models import MerchProduct
from inventory.business_kinds import BusinessKind
from inventory.liquor_config import get_default_config_for_kind, LiquorKind


@login_required
@manager_required
@require_business
@require_http_methods(["POST"])
def liquor_wizard_submit_simple(request):
    """
    Handle SIMPLIFIED liquor wizard submission (2-step flow).
    Creates MerchProduct with Malawi defaults auto-populated.
    """
    try:
        business = get_active_business(request)
        
        if not business:
            return JsonResponse({'success': False, 'error': 'No active business'}, status=400)
        
        # Parse JSON payload from simplified 2-step wizard
        data = json.loads(request.body)
        
        # Step 1 data: category
        category = data.get('category', '').lower()
        
        # Step 2 data: details
        details = data.get('details', {})
        product_name = details.get('product_name', '').strip()
        
        # Validate required fields
        if not product_name:
            return JsonResponse({'success': False, 'error': 'Product name is required'}, status=400)
        
        if not category or category not in [LiquorKind.BEER, LiquorKind.CIDER, LiquorKind.WINE, LiquorKind.SPIRITS, LiquorKind.WHISKY]:
            return JsonResponse({'success': False, 'error': 'Invalid category'}, status=400)
        
        # Get Malawi defaults for this liquor kind
        defaults = get_default_config_for_kind(category)
        
        # Parse pricing (required)
        try:
            sell_per_bottle = Decimal(str(details.get('sell_per_bottle', 0)))
            if sell_per_bottle <= 0:
                return JsonResponse({'success': False, 'error': 'Selling price is required'}, status=400)
            
            cost_str = details.get('cost_per_bottle')
            cost_per_bottle = Decimal(str(cost_str)) if cost_str else None
            
        except (ValueError, InvalidOperation) as e:
            return JsonResponse({'success': False, 'error': f'Invalid pricing: {str(e)}'}, status=400)
        
        # Build product data based on category
        product_data = {
            'business': business,
            'name': product_name,
            'kind': BusinessKind.LIQUOR,
            'category': category,
            'spec_label': "",  # CRITICAL: Always set spec_label (prevents NULL constraint)
            'is_active': True,
            'track_inventory': True,
        }
        
        # Set base prices
        product_data['price_per_bottle'] = sell_per_bottle
        product_data['cost_per_bottle'] = cost_per_bottle
        product_data['selling_price'] = sell_per_bottle  # Backward compatibility
        
        # Category-specific configuration
        if category == LiquorKind.BEER:
            # Beer: Enable crate if requested
            enable_crate = details.get('enable_crate', True)
            if enable_crate:
                product_data['pack_label'] = defaults['pack_label']
                product_data['bottles_per_crate'] = int(details.get('crate_size', defaults['pack_size']))
                product_data['supports_crates'] = True
                
                # Optional crate discount price
                sell_per_crate = details.get('sell_per_crate')
                if sell_per_crate:
                    # Store as price_per_shot field (reusing existing field for pack pricing)
                    product_data['price_per_shot'] = Decimal(str(sell_per_crate))
        
        elif category == LiquorKind.CIDER:
            # Cider: Enable 6-pack if requested (NO CRATES)
            enable_6pack = details.get('enable_6pack', True)
            if enable_6pack:
                product_data['pack_label'] = defaults['pack_label']  # "6-Pack"
                product_data['bottles_per_crate'] = int(details.get('pack_size', defaults['pack_size']))
                product_data['supports_crates'] = True  # Uses same field but label is "6-Pack"
                
                # Optional 6-pack discount price
                sell_per_pack = details.get('sell_per_pack')
                if sell_per_pack:
                    product_data['price_per_shot'] = Decimal(str(sell_per_pack))
        
        elif category == LiquorKind.WINE:
            # Wine: Enable glass selling if requested
            enable_glass = details.get('enable_glass', True)
            if enable_glass:
                product_data['has_glasses'] = True
                product_data['glasses_per_bottle'] = int(details.get('glasses_per_bottle', defaults['glasses_per_bottle']))
                
                # Glass price (optional - can be derived)
                sell_per_glass = details.get('sell_per_glass')
                if sell_per_glass:
                    product_data['price_per_glass'] = Decimal(str(sell_per_glass))
                else:
                    # Auto-calculate: bottle price / glasses per bottle
                    product_data['price_per_glass'] = (sell_per_bottle / Decimal(product_data['glasses_per_bottle'])).quantize(Decimal("0.01"))
        
        elif category in (LiquorKind.SPIRITS, LiquorKind.WHISKY):
            # Spirits/Whisky: Enable shot selling if requested
            enable_shot = details.get('enable_shot', True)
            if enable_shot:
                product_data['has_shots'] = True
                product_data['shots_per_bottle'] = int(details.get('shots_per_bottle', defaults['shots_per_bottle']))
                product_data['barman_shots_reserved'] = 2  # Malawi default
                
                # Shot price (optional - can be derived)
                sell_per_shot = details.get('sell_per_shot')
                if sell_per_shot:
                    product_data['price_per_shot'] = Decimal(str(sell_per_shot))
                else:
                    # Auto-calculate: bottle price / sellable shots
                    sellable_shots = product_data['shots_per_bottle'] - product_data['barman_shots_reserved']
                    product_data['price_per_shot'] = (sell_per_bottle / Decimal(sellable_shots)).quantize(Decimal("0.01"))
        
        # Create product
        with transaction.atomic():
            product = MerchProduct.objects.create(**product_data)
        
        return JsonResponse({
            'success': True,
            'product_id': product.id,
            'redirect': '/verticals/liquor/dashboard/',
            'message': f'{product_name} added successfully!'
        })
        
    except Exception as e:
        import logging
        from django.db import IntegrityError
        from django.core.exceptions import ValidationError
        
        logger = logging.getLogger(__name__)
        
        # Log the full error with context
        logger.error(
            f"Liquor wizard submission failed: {str(e)}",
            extra={
                'business_id': getattr(business, 'id', None) if 'business' in locals() else None,
                'user_id': getattr(request.user, 'id', None),
                'vertical': 'liquor',
                'exception_type': type(e).__name__,
            },
            exc_info=True
        )
        
        # Return friendly error message (never expose raw DB errors)
        if isinstance(e, IntegrityError):
            if 'unique' in str(e).lower():
                return JsonResponse({
                    'success': False,
                    'error': f'A product named "{product_name}" already exists. Please use a different name.'
                }, status=400)
            return JsonResponse({
                'success': False,
                'error': 'Database error. Please check your input and try again.'
            }, status=400)
        elif isinstance(e, ValidationError):
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
        else:
            return JsonResponse({
                'success': False,
                'error': f'Failed to create product: {str(e)}'
            }, status=500)


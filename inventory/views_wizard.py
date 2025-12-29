# inventory/views_wizard.py
"""
Gamified Add-Product Wizard Views
Handles wizard submissions for all verticals
"""

import json
from decimal import Decimal, InvalidOperation
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.shortcuts import render
from django.db import transaction
from django.conf import settings
from django.core.exceptions import ValidationError

from core.decorators import manager_required
from tenants.decorators import require_business_access as require_business
from tenants.middleware import get_active_business
from inventory.models import MerchProduct, PhoneProductCatalog, Product, BusinessKind
from inventory.business_kinds import BusinessKind as BK


# =============================================================================
# Wizard Page Views
# =============================================================================

@login_required
@manager_required
@require_business
def liquor_wizard(request):
    """Render the liquor add-product wizard"""
    from inventory.liquor_catalog import get_all_suggestions
    
    # Get product suggestions from single source of truth
    liquor_suggestions = get_all_suggestions()
    
    return render(request, 'inventory/wizards/liquor_wizard.html', {
        'liquor_suggestions_json': json.dumps(liquor_suggestions)
    })


@login_required
@manager_required
@require_business
def phones_wizard(request):
    """Render the phones add-product wizard"""
    return render(request, 'inventory/wizards/phones_wizard.html')


@login_required
@manager_required
@require_business
def pharmacy_wizard(request):
    """Render the pharmacy add-product wizard"""
    business = get_active_business(request)
    
    # Get existing brands for brand cards
    existing_brands = list(
        MerchProduct.objects.filter(
            business=business,
            kind=BK.PHARMACY
        ).values_list('category', flat=True).distinct()
    )
    
    return render(request, 'inventory/wizards/pharmacy_wizard.html', {
        'brands_json': json.dumps(existing_brands)
    })


@login_required
@manager_required
@require_business
def clothing_wizard(request):
    """Render the clothing add-product wizard"""
    return render(request, 'inventory/wizards/clothing_wizard.html')


# =============================================================================
# Wizard Submission Handlers
# =============================================================================

@login_required
@manager_required
@require_business
@require_http_methods(["POST"])
def liquor_wizard_submit(request):
    """Handle liquor wizard submission"""
    try:
        data = json.loads(request.body)
        business = get_active_business(request)
        
        if not business:
            return JsonResponse({'success': False, 'error': 'No active business'}, status=400)
        
        # Extract data
        category = data.get('category', '')
        product_name = data.get('product_name', '')
        selling_mode = data.get('selling_mode', 'bottle')
        
        # Validate required fields
        if not product_name:
            return JsonResponse({'success': False, 'error': 'Product name is required'}, status=400)
        
        # Parse pricing
        try:
            price_per_bottle = Decimal(data.get('price_per_bottle', 0)) if selling_mode in ['bottle', 'both'] else None
            price_per_shot = Decimal(data.get('price_per_shot', 0)) if selling_mode in ['shot', 'both'] else None
            shots_per_bottle = int(data.get('shots_per_bottle', 0)) if selling_mode in ['shot', 'both'] else None
            barman_reserved = int(data.get('barman_reserved', 2)) if selling_mode in ['shot', 'both'] else 2
            
            # CRITICAL FIX: Handle crate pricing
            # If user provides crate pricing, compute cost_per_bottle from it
            bottles_per_crate = int(data.get('bottles_per_crate', 20))  # Default 20 for Malawi beers
            is_crate_product = data.get('is_crate_product', False)
            crate_order_price = data.get('crate_order_price')
            
            if is_crate_product and crate_order_price:
                # User is ordering by crate - compute cost per bottle
                crate_price = Decimal(crate_order_price)
                cost_per_bottle = crate_price / Decimal(bottles_per_crate)
            elif data.get('cost_per_bottle'):
                # Direct cost per bottle provided
                cost_per_bottle = Decimal(data.get('cost_per_bottle'))
            else:
                cost_per_bottle = None
        except (ValueError, InvalidOperation) as e:
            return JsonResponse({'success': False, 'error': f'Invalid pricing: {str(e)}'}, status=400)
        
        # Create product
        with transaction.atomic():
            # CRITICAL FIX: Always set spec_label (empty string for liquor, prevents NULL constraint)
            product = MerchProduct.objects.create(
                business=business,
                name=product_name,
                kind=BK.LIQUOR,
                category=category,
                spec_label="",  # CRITICAL: Always set spec_label (prevents NULL constraint)
                has_shots=(selling_mode in ['shot', 'both']),
                shots_per_bottle=shots_per_bottle,
                barman_shots_reserved=barman_reserved,
                price_per_bottle=price_per_bottle,
                cost_per_bottle=cost_per_bottle,  # Now correctly computed from crate price if applicable
                price_per_shot=price_per_shot,
                bottles_per_crate=bottles_per_crate,  # Store crate size
                is_active=True
            )
            
            # NOTE: Barcode handling removed - liquor products do not require barcodes
            # If barcode is provided in the future, it should be optional and never block saving
        
        return JsonResponse({
            'success': True,
            'product_id': product.id,
            'redirect': '/verticals/liquor/dashboard/'
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
            return JsonResponse({
                'success': False,
                'error': 'Could not save product. Please check required fields and try again.'
            }, status=400)
        elif isinstance(e, ValidationError):
            return JsonResponse({
                'success': False,
                'error': 'Invalid product data. Please check your inputs and try again.'
            }, status=400)
        else:
            return JsonResponse({
                'success': False,
                'error': 'Could not save product. Please try again.'
            }, status=500)


@login_required
@manager_required
@require_business
@require_http_methods(["POST"])
def phones_wizard_submit(request):
    """Handle phones wizard submission"""
    try:
        data = json.loads(request.body)
        business = get_active_business(request)
        
        if not business:
            return JsonResponse({'success': False, 'error': 'No active business'}, status=400)
        
        # Extract data
        brand = data.get('brand', '')
        model = data.get('model', '')
        ram_storage = data.get('ram_storage', '')
        condition = data.get('condition', 'new')
        tracking_type = data.get('tracking_type', 'imei')
        
        # Validate required fields
        if not brand or not model:
            return JsonResponse({'success': False, 'error': 'Brand and model are required'}, status=400)
        
        # Parse RAM/Storage
        try:
            ram_gb, rom_gb = ram_storage.split('/')
            ram_gb = int(ram_gb)
            rom_gb = int(rom_gb)
        except (ValueError, AttributeError):
            return JsonResponse({'success': False, 'error': 'Invalid RAM/Storage format'}, status=400)
        
        # Parse pricing
        try:
            selling_price = Decimal(data.get('selling_price', 0))
            cost_price = Decimal(data.get('cost_price', 0)) if data.get('cost_price') else None
        except (ValueError, InvalidOperation) as e:
            return JsonResponse({'success': False, 'error': f'Invalid pricing: {str(e)}'}, status=400)
        
        # Create product in catalog
        with transaction.atomic():
            product, created = PhoneProductCatalog.objects.update_or_create(
                business=business,
                brand=brand.capitalize(),
                model_name=model,
                ram_gb=ram_gb,
                rom_gb=rom_gb,
                defaults={
                    'variant_label': ram_storage,
                    'default_cost_price': cost_price,
                    'condition': condition,
                    'tracking_type': tracking_type,
                    'is_active': True,
                    'created_by': request.user
                }
            )
        
        return JsonResponse({
            'success': True,
            'product_id': product.id,
            'redirect': '/inventory/dashboard/'
        })
        
    except Exception as e:
        import logging
        from django.db import IntegrityError
        from django.core.exceptions import ValidationError
        
        logger = logging.getLogger(__name__)
        
        # Log the full error with context
        logger.error(
            f"Phones wizard submission failed: {str(e)}",
            extra={
                'business_id': getattr(business, 'id', None) if 'business' in locals() else None,
                'user_id': getattr(request.user, 'id', None),
                'vertical': 'phones',
                'exception_type': type(e).__name__,
            },
            exc_info=True
        )
        
        # Return friendly error message (never expose raw DB errors)
        if isinstance(e, IntegrityError):
            return JsonResponse({
                'success': False,
                'error': 'Could not save product. Please check required fields and try again.'
            }, status=400)
        elif isinstance(e, ValidationError):
            return JsonResponse({
                'success': False,
                'error': 'Invalid product data. Please check your inputs and try again.'
            }, status=400)
        else:
            return JsonResponse({
                'success': False,
                'error': 'Could not save product. Please try again.'
            }, status=500)


@login_required
@manager_required
@require_business
@require_http_methods(["POST"])
def pharmacy_wizard_submit(request):
    """Handle pharmacy wizard submission"""
    try:
        data = json.loads(request.body)
        business = get_active_business(request)
        
        if not business:
            return JsonResponse({'success': False, 'error': 'No active business'}, status=400)
        
        # Extract data
        category = data.get('category', '')
        brand = data.get('brand', '')
        product_name = data.get('product_name', '')
        unit_type = data.get('unit_type', 'unit')
        
        # Validate required fields
        if not product_name:
            return JsonResponse({'success': False, 'error': 'Product name is required'}, status=400)
        
        # Parse pricing
        try:
            selling_price = Decimal(data.get('selling_price', 0))
            cost_price = Decimal(data.get('cost_price', 0)) if data.get('cost_price') else None
            initial_stock = int(data.get('initial_stock', 0))
        except (ValueError, InvalidOperation) as e:
            return JsonResponse({'success': False, 'error': f'Invalid data: {str(e)}'}, status=400)
        
        # Create full product name with brand if provided
        full_name = f"{brand} {product_name}" if brand else product_name
        
        # Create product
        with transaction.atomic():
            product = MerchProduct.objects.create(
                business=business,
                name=full_name,
                kind=BK.PHARMACY,
                category=category,
                spec_label="",  # CRITICAL: Always set spec_label (prevents NULL constraint)
                selling_price=selling_price,
                cost_price=cost_price,
                quantity_in_stock=initial_stock,
                base_unit=unit_type,
                is_active=True
            )
            
            # Handle barcode if provided
            if data.get('has_barcode') == 'yes' and data.get('barcode'):
                product.sku = data.get('barcode')
                product.scan_required = True
                product.save(update_fields=['sku', 'scan_required'])
        
        return JsonResponse({
            'success': True,
            'product_id': product.id,
            'redirect': '/inventory/dashboard/'
        })
        
    except Exception as e:
        import logging
        from django.db import IntegrityError
        from django.core.exceptions import ValidationError
        
        logger = logging.getLogger(__name__)
        
        # Log the full error with context
        logger.error(
            f"Pharmacy wizard submission failed: {str(e)}",
            extra={
                'business_id': getattr(business, 'id', None) if 'business' in locals() else None,
                'user_id': getattr(request.user, 'id', None),
                'vertical': 'pharmacy',
                'exception_type': type(e).__name__,
            },
            exc_info=True
        )
        
        # Return friendly error message (never expose raw DB errors)
        if isinstance(e, IntegrityError):
            return JsonResponse({
                'success': False,
                'error': 'Could not save product. Please check required fields and try again.'
            }, status=400)
        elif isinstance(e, ValidationError):
            return JsonResponse({
                'success': False,
                'error': 'Invalid product data. Please check your inputs and try again.'
            }, status=400)
        else:
            return JsonResponse({
                'success': False,
                'error': 'Could not save product. Please try again.'
            }, status=500)


@login_required
@manager_required
@require_business
@require_http_methods(["POST"])
def clothing_wizard_submit(request):
    """Handle clothing wizard submission - Simplified flow"""
    try:
        data = json.loads(request.body)
        business = get_active_business(request)
        
        if not business:
            return JsonResponse({'success': False, 'error': 'No active business'}, status=400)
        
        # Extract data - simplified flow
        category = data.get('category', '').strip()
        brand = data.get('brand', '').strip()  # Optional for all categories
        color = data.get('color', '').strip()
        product_name_input = data.get('product_name', '').strip()  # Direct name input
        size = data.get('size', '').strip()
        
        # For shoes: extract subtype
        shoe_subtype = data.get('shoe_subtype', '').strip() if category == 'shoes' else ''
        
        # Build product name - simplified logic
        if category == 'shoes':
            # Shoes: subtype + brand (optional) + name + size
            name_parts = []
            if shoe_subtype:
                name_parts.append(shoe_subtype.capitalize())
            if brand:
                name_parts.append(brand)
            if product_name_input:
                name_parts.append(product_name_input)
            elif brand:
                name_parts.append(brand)  # Use brand as name if no name provided
            if size:
                name_parts.append(f"Size {size}")
            product_name = ' - '.join(name_parts) if name_parts else 'Shoe'
        else:
            # Other clothing: category + brand (optional) + name + color + size
            name_parts = [category.capitalize()] if category else []
            if brand:
                name_parts.append(brand)
            if product_name_input:
                name_parts.append(product_name_input)
            if color:
                name_parts.append(color.capitalize())
            if size:
                name_parts.append(f"Size {size}")
            product_name = ' - '.join(name_parts) if name_parts else 'Clothing Item'
        
        # Validate required fields
        if not category:
            return JsonResponse({'success': False, 'error': 'Product type is required'}, status=400)
        if not product_name_input and category != 'shoes':
            return JsonResponse({'success': False, 'error': 'Product name is required'}, status=400)
        if not size:
            return JsonResponse({'success': False, 'error': 'Size is required'}, status=400)
        
        # Parse pricing
        try:
            selling_price = Decimal(data.get('selling_price', 0))
            if selling_price <= 0:
                return JsonResponse({'success': False, 'error': 'Selling price must be greater than zero'}, status=400)
            cost_price = Decimal(data.get('cost_price', 0)) if data.get('cost_price') else None
            if cost_price is not None and cost_price < 0:
                return JsonResponse({'success': False, 'error': 'Cost price cannot be negative'}, status=400)
            initial_stock = int(data.get('quantity', data.get('initial_stock', 0)))
            if initial_stock < 0:
                return JsonResponse({'success': False, 'error': 'Quantity cannot be negative'}, status=400)
        except (ValueError, InvalidOperation) as e:
            return JsonResponse({'success': False, 'error': f'Invalid pricing data: {str(e)}'}, status=400)
        
        # Handle barcode - CRITICAL: "No barcode" must work smoothly
        has_barcode = data.get('has_barcode', 'no').strip().lower()
        barcode_value = data.get('barcode', '').strip() if has_barcode == 'yes' else ''
        barcodes_list = data.get('barcodes', [])  # List of barcodes for quantity > 1
        
        # Only validate barcode if user explicitly selected "yes"
        if has_barcode == 'yes':
            # If quantity > 1, we need multiple barcodes
            if initial_stock > 1:
                if not barcodes_list or len(barcodes_list) != initial_stock:
                    return JsonResponse({
                        'success': False,
                        'error': f'You must scan exactly {initial_stock} unique barcodes. Currently scanned: {len(barcodes_list) if barcodes_list else 0}'
                    }, status=400)
                
                # Validate all barcodes are unique
                if len(barcodes_list) != len(set(barcodes_list)):
                    return JsonResponse({
                        'success': False,
                        'error': 'Duplicate barcodes detected. Each barcode must be unique.'
                    }, status=400)
                
                # Use first barcode for product-level barcode field
                barcode_value = barcodes_list[0] if barcodes_list else ''
            else:
                # Single barcode
                if not barcode_value:
                    return JsonResponse({
                        'success': False,
                        'error': 'Barcode is required when "With barcode" is selected. Please scan or enter a barcode.'
                    }, status=400)
        
        # If "no" or not provided, barcode_value is empty string, which we'll set to None
        
        # Create product - ensure barcode is None when "no barcode"
        with transaction.atomic():
            final_barcode = barcode_value if (has_barcode == 'yes' and barcode_value) else None
            
            # CRITICAL FIX: Set spec_label for clothing (use size, e.g., "M", "L", "Size 42")
            # This prevents NULL constraint violations
            spec_label_value = size if size else ""
            if spec_label_value and not spec_label_value.startswith("Size "):
                spec_label_value = f"Size {spec_label_value}"
            
            product = MerchProduct.objects.create(
                business=business,
                name=product_name,
                kind=BK.CLOTHING,
                category=category,
                size=size,
                color=color if color else '',
                spec_label=spec_label_value,  # CRITICAL: Always set spec_label (prevents NULL constraint)
                selling_price=selling_price,
                cost_price=cost_price,
                quantity_in_stock=initial_stock,
                barcode=final_barcode,  # None if no barcode, value if yes (first barcode for multi-barcode)
                scan_required=(has_barcode == 'yes' and final_barcode is not None),
                is_active=True,
                track_inventory=True
            )
            
            # Create InventoryBarcode records if barcodes provided
            if has_barcode == 'yes' and (barcodes_list or barcode_value):
                from inventory.services_barcodes import create_barcodes
                from inventory.models import Location
                from tenants.scope import resolve_location_for_user
                
                # Get location (optional)
                location = None
                try:
                    location_id = resolve_location_for_user(request)
                    if location_id:
                        location = Location.objects.get(pk=location_id, business=business)
                    else:
                        # Fallback to default location
                        location = Location.objects.filter(business=business, is_default=True).first()
                        if not location:
                            location = Location.objects.filter(business=business).first()
                except Exception:
                    pass
                
                # Prepare barcodes list
                codes_to_create = barcodes_list if barcodes_list else ([barcode_value] if barcode_value else [])
                
                if codes_to_create:
                    try:
                        create_barcodes(
                            product=product,
                            codes=codes_to_create,
                            business=business,
                            location=location,
                            user=request.user
                        )
                    except ValidationError as e:
                        return JsonResponse({
                            'success': False,
                            'error': f'Barcode validation failed: {str(e)}'
                        }, status=400)
        
        return JsonResponse({
            'success': True,
            'product_id': product.id,
            'redirect': '/verticals/clothing/dashboard/',
            'message': f'✅ Product "{product_name}" created successfully!'
        })
        
    except Exception as e:
        import logging
        import traceback
        from django.db import IntegrityError
        from django.core.exceptions import ValidationError
        
        logger = logging.getLogger(__name__)
        
        # Log the full error with context
        logger.error(
            f"Clothing wizard submission failed: {str(e)}",
            extra={
                'business_id': getattr(business, 'id', None),
                'user_id': getattr(request.user, 'id', None),
                'vertical': 'clothing',
                'exception_type': type(e).__name__,
            },
            exc_info=True
        )
        
        # Return friendly error message (never expose raw DB errors)
        if isinstance(e, IntegrityError):
            # Check if it's the spec_label constraint
            error_msg = str(e)
            if 'spec_label' in error_msg.lower() and 'null' in error_msg.lower():
                return JsonResponse({
                    'success': False,
                    'error': 'Could not save product. Please ensure all required fields are filled.'
                }, status=400)
            return JsonResponse({
                'success': False,
                'error': 'Could not save product. Please check required fields and try again.'
            }, status=400)
        elif isinstance(e, ValidationError):
            return JsonResponse({
                'success': False,
                'error': 'Invalid product data. Please check your inputs and try again.'
            }, status=400)
        else:
            # Only show debug info in DEBUG mode
            return JsonResponse({
                'success': False,
                'error': 'Could not save product. Please try again.',
                'debug': traceback.format_exc() if settings.DEBUG else None
            }, status=500)


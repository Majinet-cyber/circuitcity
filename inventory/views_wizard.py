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
            cost_per_bottle = Decimal(data.get('cost_per_bottle', 0)) if data.get('cost_per_bottle') else None
            price_per_shot = Decimal(data.get('price_per_shot', 0)) if selling_mode in ['shot', 'both'] else None
            shots_per_bottle = int(data.get('shots_per_bottle', 0)) if selling_mode in ['shot', 'both'] else None
            barman_reserved = int(data.get('barman_reserved', 2)) if selling_mode in ['shot', 'both'] else 2
        except (ValueError, InvalidOperation) as e:
            return JsonResponse({'success': False, 'error': f'Invalid pricing: {str(e)}'}, status=400)
        
        # Create product
        with transaction.atomic():
            product = MerchProduct.objects.create(
                business=business,
                name=product_name,
                kind=BK.LIQUOR,
                category=category,
                has_shots=(selling_mode in ['shot', 'both']),
                shots_per_bottle=shots_per_bottle,
                barman_shots_reserved=barman_reserved,
                price_per_bottle=price_per_bottle,
                cost_per_bottle=cost_per_bottle,
                price_per_shot=price_per_shot,
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
            'redirect': '/verticals/liquor/dashboard/'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


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
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


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
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@manager_required
@require_business
@require_http_methods(["POST"])
def clothing_wizard_submit(request):
    """Handle clothing wizard submission"""
    try:
        data = json.loads(request.body)
        business = get_active_business(request)
        
        if not business:
            return JsonResponse({'success': False, 'error': 'No active business'}, status=400)
        
        # Extract data
        category = data.get('category', '')
        size = data.get('size', '')
        gender = data.get('gender', '')
        color = data.get('color', '')
        
        # Build product name from hierarchy
        name_parts = [category.capitalize()]
        
        # Add category-specific details
        if category == 'shoes':
            subtype = data.get('shoe_subtype', '')
            brand = data.get('brand', '')
            model = data.get('model', '')
            if subtype:
                name_parts.append(subtype.capitalize())
            if brand:
                name_parts.append(brand)
            if model:
                name_parts.append(model)
        elif category == 'suits':
            subtype = data.get('suit_subtype', '')
            fit = data.get('fit', '')
            if subtype:
                name_parts.append(subtype.capitalize())
            if fit:
                name_parts.append(fit.capitalize())
        elif category == 'jeans':
            jeans_type = data.get('jeans_type', '')
            if jeans_type:
                name_parts.append(jeans_type.capitalize())
        
        # Add size and color if provided
        if size:
            name_parts.append(f"Size {size}")
        if color:
            name_parts.append(color.capitalize())
        
        product_name = ' - '.join(name_parts)
        
        # Parse pricing
        try:
            selling_price = Decimal(data.get('selling_price', 0))
            cost_price = Decimal(data.get('cost_price', 0)) if data.get('cost_price') else None
            initial_stock = int(data.get('initial_stock', 0))
        except (ValueError, InvalidOperation) as e:
            return JsonResponse({'success': False, 'error': f'Invalid data: {str(e)}'}, status=400)
        
        # Validate barcode requirement
        has_barcode = data.get('has_barcode', 'no')
        barcode_value = data.get('barcode', '').strip()
        
        # If user selected "yes" for barcode, barcode value is required
        if has_barcode == 'yes' and not barcode_value:
            return JsonResponse({
                'success': False,
                'error': 'Barcode is required when "Has Barcode" is selected.'
            }, status=400)
        
        # Create product
        with transaction.atomic():
            product = MerchProduct.objects.create(
                business=business,
                name=product_name,
                kind=BK.CLOTHING,
                category=category,
                size=size,
                color=color,
                selling_price=selling_price,
                cost_price=cost_price,
                quantity_in_stock=initial_stock,
                is_active=True
            )
            
            # Handle barcode if provided
            if has_barcode == 'yes' and barcode_value:
                product.barcode = barcode_value
                product.scan_required = True
                product.save(update_fields=['barcode', 'scan_required'])
            else:
                # Explicitly set barcode to None and scan_required to False
                product.barcode = None
                product.scan_required = False
                product.save(update_fields=['barcode', 'scan_required'])
        
        return JsonResponse({
            'success': True,
            'product_id': product.id,
            'redirect': '/verticals/clothing/dashboard/',
            'message': f'Product "{product_name}" created successfully!'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


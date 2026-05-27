# inventory/views_liquor_wizard.py
"""
Liquor catalog + stock-in flow (NO product creation on Step 1)
Step 1: Choose category → go to catalog
Catalog: Select or search products → go to stock-in
Stock-in: Add stock for selected product
"""
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Q

from core.decorators import manager_required
from tenants.decorators import require_business_access as require_business
from tenants.middleware import get_active_business
from inventory.models import MerchProduct, Location
from inventory.business_kinds import BusinessKind
from inventory.forms_liquor import LiquorTypeSelectForm, LiquorProductForm, LiquorStockInForm
from inventory.liquor_config import get_default_config_for_kind
from inventory.liquor_seed import create_default_liquor_catalog, should_seed_liquor_products


@login_required
@manager_required
@require_business
def liquor_wizard_step1(request):
    """Step 1: Choose liquor category - SIMPLE LINKS ONLY (no POST, no validation)"""
    # Just show category cards with links - no form processing
    return render(request, 'inventory/liquor/choose_category.html', {})


@login_required
@manager_required
@require_business
def liquor_wizard_step2(request):
    """Step 2: Enter product details"""
    # Get liquor type from session
    liquor_type = request.session.get('liquor_wizard_type')
    if not liquor_type:
        messages.warning(request, 'Please select a category first')
        return redirect('inventory:liquor_wizard_step1')
    
    # Get default config for this liquor type
    defaults = get_default_config_for_kind(liquor_type)
    
    if request.method == 'POST':
        form = LiquorProductForm(request.POST)
        if form.is_valid():
            try:
                business = get_active_business(request)
                
                # Create the product
                with transaction.atomic():
                    product_data = {
                        'business': business,
                        'name': form.cleaned_data['product_name'],
                        'kind': BusinessKind.LIQUOR,
                        'category': liquor_type,
                        'spec_label': '',
                        'is_active': True,
                        'track_inventory': True,
                        'price_per_bottle': form.cleaned_data['sell_per_unit'],
                        'selling_price': form.cleaned_data['sell_per_unit'],
                    }
                    
                    # Set cost if provided
                    if form.cleaned_data.get('cost_per_unit'):
                        product_data['cost_per_bottle'] = form.cleaned_data['cost_per_unit']
                    
                    # Handle category-specific features
                    if liquor_type == 'beer':
                        if form.cleaned_data.get('enable_pack'):
                            product_data['supports_crates'] = True
                            product_data['pack_label'] = defaults.get('pack_label', 'Crate')
                            product_data['bottles_per_crate'] = form.cleaned_data.get('pack_size', defaults.get('pack_size', 20))
                            if form.cleaned_data.get('sell_per_pack'):
                                product_data['price_per_shot'] = form.cleaned_data['sell_per_pack']
                    
                    elif liquor_type == 'cider':
                        if form.cleaned_data.get('enable_pack'):
                            product_data['supports_crates'] = True
                            product_data['pack_label'] = defaults.get('pack_label', '6-Pack')
                            product_data['bottles_per_crate'] = form.cleaned_data.get('pack_size', defaults.get('pack_size', 6))
                            if form.cleaned_data.get('sell_per_pack'):
                                product_data['price_per_shot'] = form.cleaned_data['sell_per_pack']
                    
                    elif liquor_type == 'wine':
                        if form.cleaned_data.get('enable_glass'):
                            product_data['has_glasses'] = True
                            glasses = form.cleaned_data.get('glasses_per_bottle', defaults.get('glasses_per_bottle', 5))
                            product_data['glasses_per_bottle'] = glasses
                            if form.cleaned_data.get('sell_per_glass'):
                                product_data['price_per_glass'] = form.cleaned_data['sell_per_glass']
                            else:
                                # Auto-calculate glass price
                                product_data['price_per_glass'] = (
                                    form.cleaned_data['sell_per_unit'] / Decimal(glasses)
                                ).quantize(Decimal('0.01'))
                    
                    elif liquor_type in ('spirits', 'whisky'):
                        if form.cleaned_data.get('enable_shot'):
                            product_data['has_shots'] = True
                            shots = form.cleaned_data.get('shots_per_bottle', defaults.get('shots_per_bottle', 30))
                            product_data['shots_per_bottle'] = shots
                            product_data['barman_shots_reserved'] = 2
                            if form.cleaned_data.get('sell_per_shot'):
                                product_data['price_per_shot'] = form.cleaned_data['sell_per_shot']
                            else:
                                # Auto-calculate shot price
                                sellable_shots = shots - 2
                                product_data['price_per_shot'] = (
                                    form.cleaned_data['sell_per_unit'] / Decimal(sellable_shots)
                                ).quantize(Decimal('0.01'))
                    
                    # Create the product
                    product = MerchProduct.objects.create(**product_data)
                
                # Clear session
                if 'liquor_wizard_type' in request.session:
                    del request.session['liquor_wizard_type']
                
                messages.success(request, f'✅ {product.name} added successfully!')
                return redirect('verticals:liquor_dashboard')
            
            except Exception as e:
                messages.error(request, f'Failed to create product: {str(e)}')
    else:
        # Pre-fill form with defaults
        initial = {
            'enable_pack': True,
            'enable_glass': True,
            'enable_shot': True,
        }
        
        if liquor_type in ('beer', 'cider'):
            initial['pack_size'] = defaults.get('pack_size', 20 if liquor_type == 'beer' else 6)
        elif liquor_type == 'wine':
            initial['glasses_per_bottle'] = defaults.get('glasses_per_bottle', 5)
        elif liquor_type in ('spirits', 'whisky'):
            initial['shots_per_bottle'] = defaults.get('shots_per_bottle', 30)
        
        form = LiquorProductForm(initial=initial)
    
    # Get liquor type display name
    type_names = {
        'beer': '🍺 Beer',
        'cider': '🍎 Cider',
        'wine': '🍷 Wine',
        'spirits': '🥃 Spirits',
        'whisky': '🥃 Whisky'
    }
    
    context = {
        'form': form,
        'step': 2,
        'total_steps': 2,
        'liquor_type': liquor_type,
        'liquor_type_display': type_names.get(liquor_type, liquor_type.title()),
        'defaults': defaults
    }
    return render(request, 'inventory/liquor/wizard_step2.html', context)


@login_required
@manager_required
@require_business
def liquor_catalog(request, category):
    """
    Catalog page for a specific liquor category.
    Shows pre-seeded products + allows selection or adding custom product.
    """
    business = get_active_business(request)
    
    # Validate category
    valid_categories = ['beer', 'cider', 'wine', 'spirits', 'whisky']
    if category not in valid_categories:
        messages.error(request, f'Invalid category: {category}')
        return redirect('inventory:liquor_wizard_step1')
    
    # Lazy seed: If business has no products in this category, seed defaults
    existing_count = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.LIQUOR,
        category=category,
        is_active=True
    ).count()
    
    if existing_count == 0:
        # Auto-seed catalog for this business
        try:
            create_default_liquor_catalog(business)
            messages.info(request, f'✨ We\'ve added some popular {category} products to get you started!')
        except Exception as e:
            messages.warning(request, f'Could not load default catalog: {str(e)}')
    
    # Get products for this category
    search_query = request.GET.get('q', '').strip()
    products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.LIQUOR,
        category=category,
        is_active=True
    )
    
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) |
            Q(spec_label__icontains=search_query)
        )
    
    products = products.order_by('name')
    
    # Log selection for debugging
    messages.info(request, f'Selected category: {category}')
    
    # Category metadata
    category_names = {
        'beer': '🍺 Beer',
        'cider': '🍎 Cider',
        'wine': '🍷 Wine',
        'spirits': '🥃 Spirits',
        'whisky': '🥃 Whisky'
    }
    
    context = {
        'category': category,
        'category_display': category_names.get(category, category.title()),
        'products': products,
        'search_query': search_query,
        'has_products': products.exists()
    }
    return render(request, 'inventory/liquor/catalog.html', context)


@login_required
@manager_required
@require_business
def liquor_stock_in_page(request, product_id):
    """
    Premium 3-step wizard for liquor stock-in.
    Supports type-specific inputs for Beer, Cider, Wine, Spirits, and Whisky.
    """
    business = get_active_business(request)
    
    try:
        product = MerchProduct.objects.get(
            id=product_id,
            business=business,
            kind=BusinessKind.LIQUOR,
            is_active=True
        )
        
        # Get liquor type (category)
        liquor_type = (product.category or '').lower().strip()
        if not liquor_type:
            messages.error(request, 'Product category not set')
            return redirect('inventory:liquor_wizard')
        
        # Validate liquor type
        valid_types = ['beer', 'cider', 'wine', 'spirits', 'whisky']
        if liquor_type not in valid_types:
            messages.error(request, f'Invalid liquor type: {liquor_type}')
            return redirect('inventory:liquor_wizard')
        
        # Type metadata
        type_metadata = {
            'beer': {'icon': '🍺', 'label': 'Beer', 'color': '#f59e0b'},
            'cider': {'icon': '🍎', 'label': 'Cider', 'color': '#84cc16'},
            'wine': {'icon': '🍷', 'label': 'Wine', 'color': '#ec4899'},
            'spirits': {'icon': '🥃', 'label': 'Spirits', 'color': '#8b5cf6'},
            'whisky': {'icon': '🥃', 'label': 'Whisky', 'color': '#d97706'},
        }
        
        metadata = type_metadata.get(liquor_type, {'icon': '🍾', 'label': liquor_type.title(), 'color': '#6b7280'})
        
        context = {
            'product': product,
            'liquor_type': liquor_type,
            'type_icon': metadata['icon'],
            'type_label': metadata['label'],
            'type_color': metadata['color'],
        }
        return render(request, 'inventory/liquor/stock_in_wizard.html', context)
    except MerchProduct.DoesNotExist:
        messages.error(request, 'Product not found')
        return redirect('inventory:liquor_wizard')


@login_required
@manager_required
@require_business
@require_http_methods(['POST'])
def liquor_stock_in_submit(request, product_id):
    """
    Process liquor stock-in submission using wizard adapter.
    Supports Beer, Cider, Wine, Spirits, and Whisky with type-specific calculations.
    """
    from inventory.liquor_stockin_wizard_adapter import LiquorStockInAdapter
    from django.core.exceptions import ValidationError as DjangoValidationError
    
    try:
        business = get_active_business(request)
        product = MerchProduct.objects.get(
            id=product_id,
            business=business,
            kind=BusinessKind.LIQUOR,
            is_active=True
        )
        
        # Get liquor type
        liquor_type = (product.category or '').lower().strip()
        if not liquor_type:
            messages.error(request, 'Product category not set')
            return redirect('inventory:liquor_stock_in', product_id=product_id)
        
        # Parse universal fields
        date_received_str = request.POST.get('date_received', '').strip()
        notes = request.POST.get('notes', '').strip()
        
        date_received = None
        if date_received_str:
            try:
                date_received = timezone.datetime.strptime(date_received_str, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, 'Invalid date format')
                return redirect('inventory:liquor_stock_in', product_id=product_id)
        
        # Parse type-specific inputs and compute values
        try:
            if liquor_type == 'beer':
                crates = int(request.POST.get('crates', '0'))
                loose_bottles = int(request.POST.get('loose_bottles', '0'))
                cost_per_crate = Decimal(request.POST.get('cost_per_crate', '0'))
                
                result = LiquorStockInAdapter.compute_beer_stockin(
                    crates=crates,
                    loose_bottles=loose_bottles,
                    cost_per_crate=cost_per_crate
                )
            
            elif liquor_type == 'cider':
                quantity_bottles = int(request.POST.get('quantity_bottles', '0'))
                cost_per_bottle = Decimal(request.POST.get('cost_per_bottle', '0'))
                
                result = LiquorStockInAdapter.compute_cider_stockin(
                    quantity_bottles=quantity_bottles,
                    cost_per_bottle=cost_per_bottle
                )
            
            elif liquor_type == 'wine':
                bottles = int(request.POST.get('bottles', '0'))
                cost_per_bottle = Decimal(request.POST.get('cost_per_bottle', '0'))
                
                result = LiquorStockInAdapter.compute_wine_stockin(
                    bottles=bottles,
                    cost_per_bottle=cost_per_bottle
                )
            
            elif liquor_type == 'spirits':
                shots_added = int(request.POST.get('shots_added', '0'))
                cost_per_shot = Decimal(request.POST.get('cost_per_shot', '0'))
                reserved_barman_shots = int(request.POST.get('reserved_barman_shots', '0'))
                
                result = LiquorStockInAdapter.compute_spirits_stockin(
                    shots_added=shots_added,
                    cost_per_shot=cost_per_shot,
                    reserved_barman_shots=reserved_barman_shots
                )
            
            elif liquor_type == 'whisky':
                shots_added = int(request.POST.get('shots_added', '0'))
                cost_per_shot = Decimal(request.POST.get('cost_per_shot', '0'))
                reserved_barman_shots = int(request.POST.get('reserved_barman_shots', '0'))
                
                result = LiquorStockInAdapter.compute_whisky_stockin(
                    shots_added=shots_added,
                    cost_per_shot=cost_per_shot,
                    reserved_barman_shots=reserved_barman_shots
                )
            
            else:
                messages.error(request, f'Invalid liquor type: {liquor_type}')
                return redirect('inventory:liquor_stock_in', product_id=product_id)
        
        except (ValueError, TypeError, DjangoValidationError) as e:
            messages.error(request, f'Invalid input: {str(e)}')
            return redirect('inventory:liquor_stock_in', product_id=product_id)
        
        # Extract computed values
        quantity_units_added = result['quantity_units_added']
        unit_cost = result['unit_cost']
        total_cost = result['total_cost']
        reserved_shots = result.get('reserved_shots', 0)
        
        # Save stock-in transaction
        with transaction.atomic():
            # Update product stock
            current_stock = product.quantity_in_stock or 0
            product.quantity_in_stock = current_stock + quantity_units_added
            
            # Update cost price
            product.cost_per_bottle = unit_cost
            
            # Handle reserved shots (append to notes if not stored in model)
            final_notes = notes
            if reserved_shots > 0:
                reserved_note = f"Reserved barman shots: {reserved_shots}"
                if final_notes:
                    final_notes = f"{final_notes}\n{reserved_note}"
                else:
                    final_notes = reserved_note
            
            product.save(update_fields=['quantity_in_stock', 'cost_per_bottle'])
            
            # Create stock-in transaction log for COGS tracking
            from inventory.models_verticals import LiquorStockInTransaction
            location = getattr(request, 'location', None)
            
            txn_data = {
                'business': business,
                'location': location,
                'product': product,
                'quantity_added': quantity_units_added,
                'unit_cost': unit_cost,
                'total_cost': total_cost,
                'notes': final_notes,
                'created_by': request.user,
            }
            
            # Use date_received if provided, otherwise default to today
            if date_received:
                txn_data['date_received'] = date_received
            
            LiquorStockInTransaction.objects.create(**txn_data)
        
        # Success message
        messages.success(
            request,
            f'✅ Stock-in complete: {quantity_units_added} units added, total cost: MWK {total_cost:,.2f}'
        )
        
        # Redirect to My Stock or Dashboard
        try:
            return redirect('verticals:liquor_my_stock')
        except:
            return redirect('verticals:liquor_dashboard')
    
    except MerchProduct.DoesNotExist:
        messages.error(request, 'Product not found')
        return redirect('inventory:liquor_wizard')
    except Exception as e:
        messages.error(request, f'Failed to add stock: {str(e)}')
        return redirect('inventory:liquor_stock_in', product_id=product_id)


# inventory/views_liquor_stockin_v2.py
"""
Category-aware stock-in views for Liquor products.
PART B: Effortless forms (users input unit cost + quantity, system calculates totals).
PART C: Backend adapters for consistent save path.
PART D: Gamified UX with progress indicators and live calculators.
"""
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.helpers import get_active_business
from inventory.models import MerchProduct
from inventory.forms_liquor import (
    BeerStockInForm,
    CiderStockInForm,
    WineStockInForm,
    SpiritsStockInForm,
    WhiskyStockInForm,
)
from inventory.services_liquor_stockin import (
    get_adapter_for_category,
    save_stock_in_transaction,
)
from tenants.utils import require_business


def get_form_class_for_category(category: str):
    """Get the appropriate form class for a category."""
    category_lower = category.lower().strip()
    
    forms = {
        'beer': BeerStockInForm,
        'cider': CiderStockInForm,
        'wine': WineStockInForm,
        'spirits': SpiritsStockInForm,
        'whisky': WhiskyStockInForm,
    }
    
    return forms.get(category_lower)


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def liquor_stock_in_category(request, category):
    """
    Category-aware stock-in page (PART D: Gamified UX).
    Shows products in the selected category with a form specific to that category.
    """
    business = get_active_business(request)
    
    # Validate category
    valid_categories = ['beer', 'cider', 'wine', 'spirits', 'whisky']
    if category.lower() not in valid_categories:
        messages.error(request, f"Invalid category: {category}")
        return redirect('verticals:liquor_dashboard')
    
    # Get products in this category
    products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.LIQUOR,
        is_active=True,
        category__iexact=category
    ).order_by('name')
    
    # Get selected product if provided
    product_id = request.GET.get('product')
    selected_product = None
    if product_id:
        try:
            selected_product = products.get(pk=int(product_id))
        except (MerchProduct.DoesNotExist, ValueError):
            pass
    
    context = {
        'business': business,
        'category': category,
        'category_display': category.capitalize(),
        'products': products,
        'selected_product': selected_product,
        'has_products': products.exists(),
    }
    
    return render(request, 'inventory/liquor/stock_in_category.html', context)


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
@require_http_methods(["POST"])
def liquor_stock_in_submit_v2(request):
    """
    Handle category-aware stock-in form submission.
    Uses adapters to convert user inputs to standardized transaction format.
    """
    business = get_active_business(request)
    
    try:
        # Extract product and category
        product_id = request.POST.get('product_id')
        if not product_id:
            messages.error(request, "❌ Product ID is required.")
            return redirect('verticals:liquor_dashboard')
        
        product = get_object_or_404(
            MerchProduct,
            pk=int(product_id),
            business=business,
            kind=BusinessKind.LIQUOR,
            is_active=True
        )
        
        category = product.category.lower()
        
        # Get the appropriate form class
        FormClass = get_form_class_for_category(category)
        if not FormClass:
            messages.error(request, f"❌ Category '{category}' is not supported.")
            return redirect('verticals:liquor_dashboard')
        
        # Validate form
        form = FormClass(request.POST)
        if not form.is_valid():
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"❌ {error}")
            return redirect(f'/inventory/liquor/stock-in/{category}/?product={product.id}')
        
        # Get adapter and convert user inputs
        adapter = get_adapter_for_category(category)
        user_inputs = form.cleaned_data.copy()
        
        try:
            adapted_data = adapter.adapt(user_inputs)
        except ValueError as e:
            messages.error(request, f"❌ {str(e)}")
            return redirect(f'/inventory/liquor/stock-in/{category}/?product={product.id}')
        
        # Save transaction
        save_stock_in_transaction(product, adapted_data, request.user)
        
        # Success message with details
        messages.success(
            request,
            f"✅ Stock added successfully!\n"
            f"Product: {product.name}\n"
            f"Added: {adapted_data['quantity_units_added']} units\n"
            f"Unit Cost: MK {adapted_data['unit_cost']:,.2f}\n"
            f"Total Cost: MK {adapted_data['total_cost']:,.2f}"
        )
        
        return redirect('verticals:liquor_dashboard')
    
    except Exception as e:
        messages.error(request, f"❌ An error occurred: {str(e)}")
        return redirect('verticals:liquor_dashboard')


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def liquor_stock_in_calculator_api(request):
    """
    API endpoint for live calculator (PART D: UX enhancement).
    Returns calculated values based on user inputs without saving.
    """
    try:
        category = request.GET.get('category', '').lower()
        
        # Get adapter
        adapter = get_adapter_for_category(category)
        
        # Build user_inputs from GET parameters
        user_inputs = {}
        
        if category == 'beer':
            user_inputs = {
                'number_of_crates': int(request.GET.get('number_of_crates', 0)),
                'cost_per_crate': request.GET.get('cost_per_crate', '0'),
                'loose_bottles': int(request.GET.get('loose_bottles', 0)),
            }
        elif category == 'cider':
            user_inputs = {
                'quantity_bottles': int(request.GET.get('quantity_bottles', 0)),
                'cost_per_bottle': request.GET.get('cost_per_bottle', '0'),
            }
        elif category == 'wine':
            user_inputs = {
                'number_of_bottles': int(request.GET.get('number_of_bottles', 0)),
                'cost_per_bottle': request.GET.get('cost_per_bottle', '0'),
                'glasses_per_bottle': int(request.GET.get('glasses_per_bottle', 5)),
                'selling_price_per_bottle': request.GET.get('selling_price_per_bottle') or None,
                'selling_price_per_glass': request.GET.get('selling_price_per_glass') or None,
            }
        elif category in ['spirits', 'whisky']:
            user_inputs = {
                'quantity_of_shots_added': int(request.GET.get('quantity_of_shots_added', 0)),
                'cost_per_shot': request.GET.get('cost_per_shot', '0'),
                'reserved_barman_shots': int(request.GET.get('reserved_barman_shots', 0)),
            }
        else:
            return JsonResponse({'error': 'Invalid category'}, status=400)
        
        # Calculate
        try:
            result = adapter.adapt(user_inputs)
            
            return JsonResponse({
                'success': True,
                'quantity_units_added': result['quantity_units_added'],
                'unit_cost': float(result['unit_cost']),
                'total_cost': float(result['total_cost']),
                'metadata': result['metadata'],
            })
        except ValueError as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Calculation error: {str(e)}'
        }, status=400)





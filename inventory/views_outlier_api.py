"""
Outlier Detection API Endpoint
Non-blocking AI-driven warnings for unusual values
"""

import json
from decimal import Decimal
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from common.utils.outlier_detector import check_value_outlier


@login_required
@require_http_methods(["POST"])
def check_outlier_api(request):
    """
    API endpoint to check if a value is an outlier.
    
    POST body:
    {
        "check_type": "sale" | "stock_quantity" | "selling_price" | "cost_price",
        "value": number,
        "context": {
            "vertical": "groceries" (optional),
            "product_name": "Sugar" (optional)
        }
    }
    
    Returns:
    {
        "is_outlier": bool,
        "warning_message": str (if outlier),
        "suggested_value": number (optional),
        "typical_range": [lower, upper] (optional),
        "confidence": "low" | "medium" | "high"
    }
    """
    try:
        business = request.user.profile.business
        if not business:
            return JsonResponse({
                'error': 'No business associated with user',
                'is_outlier': False
            }, status=400)
        
        # Parse request body
        data = json.loads(request.body.decode('utf-8'))
        
        check_type = data.get('check_type')
        value = data.get('value')
        context = data.get('context', {})
        
        # Validate inputs
        if not check_type or value is None:
            return JsonResponse({
                'error': 'Missing required fields: check_type, value',
                'is_outlier': False
            }, status=400)
        
        # Convert value to Decimal
        try:
            value = Decimal(str(value))
        except (ValueError, TypeError):
            return JsonResponse({
                'error': 'Invalid value format',
                'is_outlier': False
            }, status=400)
        
        # Perform outlier check
        result = check_value_outlier(
            business=business,
            value=value,
            check_type=check_type,
            **context
        )
        
        # Format response
        response_data = {
            'is_outlier': result.get('is_outlier', False),
            'confidence': result.get('confidence', 'low'),
        }
        
        if result.get('warning_message'):
            response_data['warning_message'] = result['warning_message']
        
        if result.get('suggested_value'):
            response_data['suggested_value'] = float(result['suggested_value'])
        
        if result.get('typical_range'):
            lower, upper = result['typical_range']
            response_data['typical_range'] = {
                'lower': float(lower),
                'upper': float(upper)
            }
        
        if result.get('median'):
            response_data['median'] = float(result['median'])
        
        return JsonResponse(response_data)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON',
            'is_outlier': False
        }, status=400)
    except Exception as e:
        # Log error but don't block user
        print(f"Outlier check error: {str(e)}")
        return JsonResponse({
            'error': 'Internal error - proceeding without check',
            'is_outlier': False
        }, status=500)


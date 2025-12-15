# core/views_well_known.py
"""
Well-known endpoints for external services (Chrome DevTools, etc.)
"""
from django.http import JsonResponse


def chrome_devtools_appspecific(request):
    """
    Handle Chrome DevTools well-known requests.
    
    Chrome DevTools automatically requests:
    /.well-known/appspecific/com.chrome.devtools.json
    
    This endpoint returns an empty JSON object to prevent 404 errors.
    """
    return JsonResponse({}, safe=True)


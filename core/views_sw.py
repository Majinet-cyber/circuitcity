# core/views_sw.py
"""Service Worker view with dynamic version injection for cache busting."""

from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@never_cache
@require_GET
def service_worker(request):
    """
    Serve service worker with dynamically injected BUILD_ID for cache busting.
    This ensures the SW version changes with every deployment, forcing cache refresh.
    """
    # Get BUILD_ID from settings (timestamp-based or git hash)
    build_id = getattr(settings, 'BUILD_ID', getattr(settings, 'STATIC_VERSION', '1'))
    
    # Read the SW template and inject BUILD_ID
    try:
        with open(settings.BASE_DIR / 'static' / 'sw.js', 'r', encoding='utf-8') as f:
            sw_content = f.read()
        
        # Replace placeholder with actual BUILD_ID
        sw_content = sw_content.replace('BUILD_ID_PLACEHOLDER', build_id)
        
        return HttpResponse(
            sw_content,
            content_type='application/javascript; charset=utf-8',
            headers={
                'Service-Worker-Allowed': '/',
                'Cache-Control': 'no-cache, no-store, must-revalidate',
            }
        )
    except FileNotFoundError:
        return HttpResponse(
            '// Service worker not found',
            content_type='application/javascript; charset=utf-8',
            status=404
        )


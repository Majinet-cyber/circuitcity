# core/views_sw.py
"""
Service Worker view — serves the cleanup/no-op SW with BUILD_ID injection.

The SW at /sw.js is intentionally a no-op cleanup worker.  It clears all caches
left by the previous caching SW and intercepts nothing.  The /sw.js endpoint must
always be served with aggressive no-cache headers so that browsers always fetch the
latest version and never serve a stale copy from HTTP cache.
"""

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@never_cache
@require_GET
def service_worker(request):
    """
    Serve the cleanup service worker with dynamically injected BUILD_ID.

    The BUILD_ID ensures the SW VERSION string changes on every deploy,
    which forces the browser to treat it as a new SW and re-run activate
    (which clears all old caches).

    Headers:
      Cache-Control: no-cache, no-store, must-revalidate
      Pragma: no-cache
      Expires: 0
      Service-Worker-Allowed: /
    """
    build_id = getattr(settings, 'BUILD_ID', getattr(settings, 'STATIC_VERSION', '1'))

    try:
        with open(settings.BASE_DIR / 'static' / 'sw.js', 'r', encoding='utf-8') as f:
            sw_content = f.read()

        sw_content = sw_content.replace('BUILD_ID_PLACEHOLDER', build_id)

        return HttpResponse(
            sw_content,
            content_type='application/javascript; charset=utf-8',
            headers={
                'Service-Worker-Allowed': '/',
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
            }
        )
    except FileNotFoundError:
        return HttpResponse(
            '// Service worker not found',
            content_type='application/javascript; charset=utf-8',
            status=404
        )

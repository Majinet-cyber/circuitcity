# inventory/views_legacy_shims.py
"""
Legacy URL shim views - Redirect or block old scan/sell/simulator pages.

These views ensure legacy URLs never render old templates. They either:
1. Redirect to canonical/new pages when a replacement exists
2. Return 410 Gone for pages that have been upgraded/removed
"""
from django.http import HttpResponse, HttpResponsePermanentRedirect, HttpResponseGone
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache


@never_cache
def legacy_scan_in_shim(request):
    """
    Legacy scan_in page - redirect to canonical scan-in URL.
    Old URL: /inventory/scan-in/ (using old template)
    New URL: /inventory/scan-in/ (using new gamified template)
    
    This shim ensures if someone cached the old URL, they get the new flow.
    """
    # Redirect to the canonical scan-in page (now uses phones gamified scan)
    return HttpResponsePermanentRedirect(reverse('inventory:scan_in'))


@never_cache
def legacy_scan_sold_shim(request):
    """
    Legacy scan_sold page - redirect to new phone sale wizard.
    Old URL: /inventory/scan-sold/ (using old template)
    New URL: /inventory/phone-sale-wizard/ (gamified sale flow)
    """
    # Redirect to new gamified phone sale wizard
    try:
        return HttpResponsePermanentRedirect(reverse('inventory:phone_sale_wizard'))
    except:
        # Fallback to scan_sold if phone_sale_wizard not available
        return HttpResponsePermanentRedirect(reverse('inventory:scan_sold'))


@never_cache
def legacy_simulator_shim(request):
    """
    Legacy public business simulator - return 410 Gone.
    Old URL: /simulator/ (public staticpage)
    New URL: /simulator/business/ (manager-only, uses real data)
    
    The old public simulator page has been upgraded to a manager-only tool.
    """
    context = {
        'title': 'Page Upgraded',
        'message': 'The Business Simulator has been upgraded.',
        'detail': (
            'The public simulator has been replaced with a manager-only tool '
            'that uses real business data. Please log in as a manager to access it.'
        ),
        'cta_text': 'Go to Dashboard',
        'cta_url': '/',
    }
    return HttpResponseGone(render(request, 'legacy_gone.html', context).content)


def legacy_scan_in_fallback_view(request):
    """
    Fallback view for scan_in if somehow old template is still accessed.
    This auto-redirects to canonical page with JS + fallback button.
    """
    return render(request, 'inventory/scan_in_redirect.html', {
        'redirect_url': reverse('inventory:scan_in'),
        'canonical_name': 'Scan IN',
    })


def legacy_scan_sold_fallback_view(request):
    """
    Fallback view for scan_sold if somehow old template is still accessed.
    This auto-redirects to canonical page with JS + fallback button.
    """
    try:
        redirect_url = reverse('inventory:phone_sale_wizard')
    except:
        redirect_url = reverse('inventory:scan_sold')
    
    return render(request, 'inventory/scan_sold_redirect.html', {
        'redirect_url': redirect_url,
        'canonical_name': 'Phone Sale Wizard',
    })


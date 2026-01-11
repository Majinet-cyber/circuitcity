# cc/urls_compat_extra.py
"""
Extra URL compatibility aliases for URLs that require special handling.

This module contains URL aliases that can't use simple RedirectView because
they require argument forwarding or have other special requirements.

These patterns are imported into cc/urls.py and added to urlpatterns.

SSOT: All aliases defined here are the ONLY place these non-namespaced URL names exist.
"""
from django.http import HttpResponseRedirect
from django.urls import path, reverse


def member_qr_image_redirect(request, qr_uuid):
    """
    Redirect member_qr_image/<uuid>/ to gym:member_qr_png/<uuid>/
    
    This allows reverse('member_qr_image', kwargs={'qr_uuid': uuid}) to work
    and GET requests will properly redirect to the canonical gym:member_qr_png route.
    """
    target_url = reverse('gym:member_qr_png', kwargs={'qr_uuid': qr_uuid})
    return HttpResponseRedirect(target_url)


def get_extra_compat_urlpatterns():
    """
    Return URL patterns for aliases that require argument forwarding.
    
    These patterns handle URLs that can't use simple RedirectView because
    they need to forward URL parameters to the canonical routes.
    
    Returns:
        list: List of URL patterns for extra compatibility aliases
    """
    return [
        # member_qr_image with UUID argument - forwards to gym:member_qr_png
        path(
            "__alias__/member-qr-image/<uuid:qr_uuid>/",
            member_qr_image_redirect,
            name="member_qr_image_with_uuid",
        ),
    ]


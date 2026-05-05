# inventory/urls_marketplace_public.py
"""
Public marketplace URL patterns.
Namespace: marketplace

Routes:
  /marketplace/                         - All live businesses / global marketplace home
  /marketplace/<business_slug>/         - Business public marketplace page
  /marketplace/<business_slug>/<listing_slug>/  - Listing detail
"""
from django.urls import path

app_name = "marketplace"

try:
    from inventory import views_marketplace as views

    urlpatterns = [
        path("", views.marketplace_home, name="home"),
        path("stores/<slug:business_slug>/", views.storefront_public_page, name="storefront"),
        path("checkout/webhook/", views.marketplace_checkout_webhook, name="checkout_webhook"),
        path("checkout/return/<str:tx_ref>/", views.marketplace_checkout_return, name="checkout_return"),
        path("<slug:business_slug>/<slug:listing_slug>/checkout/", views.marketplace_checkout_start, name="checkout"),
        path("<slug:business_slug>/", views.business_public_page, name="business"),
        path("<slug:business_slug>/<slug:listing_slug>/", views.listing_detail, name="listing"),
    ]
except ImportError:
    from django.http import HttpResponse

    def _placeholder(request, *a, **kw):
        return HttpResponse("Marketplace coming soon.", status=503)

    urlpatterns = [
        path("", _placeholder, name="home"),
        path("stores/<slug:business_slug>/", _placeholder, name="storefront"),
        path("checkout/webhook/", _placeholder, name="checkout_webhook"),
        path("checkout/return/<str:tx_ref>/", _placeholder, name="checkout_return"),
        path("<slug:business_slug>/<slug:listing_slug>/checkout/", _placeholder, name="checkout"),
        path("<slug:business_slug>/", _placeholder, name="business"),
        path("<slug:business_slug>/<slug:listing_slug>/", _placeholder, name="listing"),
    ]

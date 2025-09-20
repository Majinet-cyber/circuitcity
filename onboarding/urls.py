# circuitcity/onboarding/urls.py
from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = "onboarding"

urlpatterns = [
    # Landing → run the smart router
    path("", views.start, name="start"),
    path("start/", views.start),  # alias

    # Create business
    path("create-business/", views.create_business, name="create_business"),
    path("create/", RedirectView.as_view(pattern_name="onboarding:create_business", permanent=False)),

    # Add first product
    path("add-product/", views.add_product, name="add_product"),
    path("add/", RedirectView.as_view(pattern_name="onboarding:add_product", permanent=False)),

    # Nice alias for links that say “activate”
    path("activate/", RedirectView.as_view(pattern_name="onboarding:start", permanent=False)),
]

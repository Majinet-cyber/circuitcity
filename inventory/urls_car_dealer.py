# inventory/urls_car_dealer.py
"""
URL patterns for the Car Dealer vertical.
Namespace: car_dealer
"""
from django.urls import path

from inventory.verticals import car_dealer as views

app_name = "car_dealer"

urlpatterns = [
    path("", views.car_dealer_dashboard, name="dashboard"),
    path("vehicles/", views.vehicle_list, name="vehicle_list"),
    path("vehicles/add/", views.stock_in_vehicle, name="stock_in"),
    path("vehicles/<int:pk>/", views.vehicle_detail, name="vehicle_detail"),
    path("vehicles/<int:pk>/sell/", views.sell_vehicle, name="sell_vehicle"),
    path("vehicles/<int:pk>/images/<int:image_pk>/delete/", views.delete_vehicle_image, name="delete_vehicle_image"),
    path("vehicles/<int:pk>/images/<int:image_pk>/set-cover/", views.set_cover_image, name="set_cover_image"),
    path("vehicles/<int:pk>/publish/", views.publish_to_marketplace, name="publish_to_marketplace"),
    path("seed/", views.seed_car_data, name="seed_data"),
]

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
]

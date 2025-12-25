# inventory/urls_cement.py
"""URL routing for Cement vertical"""
from django.urls import path
from inventory.verticals import cement

app_name = 'cement'

urlpatterns = [
    path('dashboard/', cement.dashboard, name='dashboard'),
    path('stock/', cement.stock_list, name='stock_list'),
    path('stock-in/', cement.stock_in, name='stock_in'),
    path('sell/', cement.sell, name='sell'),
    path('costs/', cement.costs, name='costs'),
    path('analytics/', cement.analytics, name='analytics'),
]


# inventory/urls_groceries.py
"""URL routing for Groceries vertical"""
from django.urls import path
from inventory.verticals import groceries

app_name = 'groceries'

urlpatterns = [
    path('dashboard/', groceries.dashboard, name='dashboard'),
    path('stock/', groceries.stock_list, name='stock_list'),
    path('stock-in/', groceries.stock_in, name='stock_in'),
    path('sell/', groceries.sell, name='sell'),
    path('analytics/', groceries.analytics, name='analytics'),
]


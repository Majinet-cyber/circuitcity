"""
KPI Breakdown URL Patterns
Routes for clickable KPI breakdown pages
"""

from django.urls import path
from inventory import views_kpi_breakdown

app_name = 'kpi_breakdown'

urlpatterns = [
    # KPI Breakdown Views
    path('revenue/', views_kpi_breakdown.revenue_breakdown, name='revenue'),
    path('profit/', views_kpi_breakdown.profit_breakdown, name='profit'),
    path('cogs/', views_kpi_breakdown.cogs_breakdown, name='cogs'),
    path('stock-value/', views_kpi_breakdown.stock_value_breakdown, name='stock_value'),
]


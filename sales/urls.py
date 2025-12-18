# sales/urls.py
"""
Sales app URL patterns
"""
from django.urls import path
from sales import views, views_rollback, views_commission, views_export

app_name = "sales"

urlpatterns = [
    # Sale rollback URLs
    path('rollback/', views_rollback.rollback_home, name='rollback_home'),
    path('rollback/search/', views_rollback.rollback_search, name='rollback_search'),
    path('rollback/<int:sale_id>/confirm/', views_rollback.rollback_confirm, name='rollback_confirm'),
    path('rollback/<int:rollback_id>/detail/', views_rollback.rollback_detail, name='rollback_detail'),
    
    # Commission URLs (if they exist)
    # path('commissions/', views_commission.commission_list, name='commission_list'),
    
    # Export URLs (if they exist)
    # path('export/', views_export.export_sales, name='export_sales'),
]


# inventory/urls_butchery.py
"""URL routing for Butchery vertical."""
from django.urls import path

from inventory.verticals import butchery

app_name = "butchery"

urlpatterns = [
    # Core
    path("dashboard/", butchery.dashboard, name="dashboard"),

    # Products / Cuts
    path("products/", butchery.products, name="products"),
    path("products/add/", butchery.product_add, name="product_add"),
    path("products/<int:product_id>/edit/", butchery.product_edit, name="product_edit"),

    # Intake & Processing
    path("intake/", butchery.intake, name="intake"),
    path("processing/", butchery.processing, name="processing"),

    # Sales
    path("sell/", butchery.sell, name="sell"),
    path("daily-sales/", butchery.daily_sales, name="daily_sales"),
    path("sales/", butchery.sales, name="sales"),

    # Expenses
    path("expenses/", butchery.expenses, name="expenses"),

    # Reports
    path("reports/", butchery.reports, name="reports"),
    path("reports/export/csv/", butchery.reports_export_csv, name="reports_export_csv"),
    path("reports/export/pdf/", butchery.reports_export_pdf, name="reports_export_pdf"),
]

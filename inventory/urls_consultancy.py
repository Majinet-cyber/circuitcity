# inventory/urls_consultancy.py
"""URL routing for Consultancy & Services vertical."""
from django.urls import path

from inventory.verticals import consultancy

app_name = "consultancy"

urlpatterns = [
    path("dashboard/", consultancy.dashboard, name="dashboard"),
    path("clients/", consultancy.clients_list, name="clients"),
    path("projects/", consultancy.projects_list, name="projects"),
    path("projects/add/", consultancy.project_add, name="project_add"),
    path("projects/<int:project_id>/", consultancy.project_detail, name="project_detail"),
    path("quotes/", consultancy.quotes_list, name="quotes"),
    path("quotes/create/", consultancy.quote_create, name="quote_create"),
    path("quotes/<int:quote_id>/", consultancy.quote_detail, name="quote_detail"),
    path("invoices/", consultancy.invoices_list, name="invoices"),
    path("invoices/create/", consultancy.invoice_create, name="invoice_create"),
    path("invoices/<int:invoice_id>/", consultancy.invoice_detail, name="invoice_detail"),
    path("expenses/", consultancy.expenses, name="expenses"),
]

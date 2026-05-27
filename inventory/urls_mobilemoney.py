# inventory/urls_mobilemoney.py
"""URL routing for Mobile Money vertical."""
from django.urls import path

from inventory.verticals import mobilemoney

app_name = "mobilemoney"

urlpatterns = [
    path("dashboard/", mobilemoney.dashboard, name="dashboard"),
    path("transactions/", mobilemoney.transactions, name="transactions"),
    path("credits/", mobilemoney.credits, name="credits"),
    path("credits/<int:credit_id>/repay/", mobilemoney.credit_repayment, name="credit_repayment"),
    path("reconciliation/", mobilemoney.reconciliation, name="reconciliation"),
    path("commissions/", mobilemoney.commissions, name="commissions"),
    path("settlements/", mobilemoney.settlements, name="settlements"),
]

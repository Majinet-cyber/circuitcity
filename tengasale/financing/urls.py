from django.urls import path

from . import views

urlpatterns = [
    path("tengasale/financing/", views.financing_dashboard, name="financing_dashboard"),
    path("tengasale/financing/customers/", views.customers, name="financing_customers"),
    path("tengasale/financing/devices/", views.devices, name="financing_devices"),
    path("tengasale/financing/contracts/", views.contracts, name="financing_contracts"),
    path("tengasale/financing/payments/pending/", views.pending_payments, name="financing_pending_payments"),
    path("tengasale/financing/payments/<int:payment_id>/", views.payment_detail, name="financing_payment_detail"),
    path("tengasale/financing/payments/<int:payment_id>/approve/", views.approve_payment, name="financing_approve_payment"),
    path("tengasale/financing/payments/<int:payment_id>/reject/", views.reject_payment, name="financing_reject_payment"),
    path("tengasale/financing/contracts/<int:contract_id>/pay/", views.submit_payment, name="financing_submit_payment"),
    path(
        "tengasale/financing/contracts/<int:contract_id>/command/<str:command_type>/",
        views.request_device_command,
        name="financing_request_command",
    ),
    path("tengasale/financing/commands/", views.command_history, name="financing_command_history"),
    path("tengasale/customer/device/<int:contract_id>/", views.customer_device_portal, name="customer_device_portal"),
    path("tengasale/customer/device/<int:contract_id>/unlock/", views.customer_unlock_pin, name="customer_unlock_pin"),
]

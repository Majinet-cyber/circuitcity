from django.urls import path

from . import views

urlpatterns = [
    path("devices/register/", views.api_register_device, name="api_tengasale_device_register"),
    path("devices/lock/", views.api_lock_device, name="api_tengasale_device_lock"),
    path("devices/unlock/", views.api_unlock_device, name="api_tengasale_device_unlock"),
    path("devices/status/", views.api_device_status_post, name="api_tengasale_device_status_post"),
    path("payments/verify/", views.api_verify_payment, name="api_tengasale_payment_verify"),
    path("contracts/<int:contract_id>/status/", views.api_contract_status, name="api_tengasale_contract_status"),
    path("devices/<int:device_id>/status/", views.api_device_status_get, name="api_tengasale_device_status_get"),
]

from django.urls import path
from . import views

app_name = "integrations"

urlpatterns = [
    path("iot/", views.iot_webhook, name="webhook_iot"),
    path("credit/", views.credit_webhook, name="webhook_credit"),
    path("generic/", views.generic_webhook, name="webhook_generic"),
]

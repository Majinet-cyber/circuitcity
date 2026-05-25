from django.urls import path

from . import views


urlpatterns = [
    path("<int:app_id>/terms/", views.contract_terms, name="contract_terms"),
    path("<int:contract_id>/signature/", views.contract_signature, name="contract_signature"),
    path("<int:contract_id>/imei/", views.contract_imei, name="contract_imei"),
    path("<int:contract_id>/progress/", views.contract_progress, name="contract_progress"),
    path("<int:contract_id>/complete/", views.contract_complete, name="contract_complete"),
    path("<int:contract_id>/", views.contract_detail, name="contract_detail"),
]

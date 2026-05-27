from django.urls import path
from . import views

urlpatterns = [
    path("", views.portal_search, name="portal_search"),
    path("support/", views.portal_support, name="portal_support"),
    path("search/", views.portal_search_post, name="portal_search_post"),
    path("contract/<str:contract_number>/", views.portal_contract, name="portal_contract"),
    path("contract/<str:contract_number>/payment/", views.portal_payment, name="portal_payment"),
    path("contract/<str:contract_number>/history/", views.portal_history, name="portal_history"),
]

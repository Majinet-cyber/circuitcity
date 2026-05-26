from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("home/", views.home, name="home_redirect"),
    path("tengasale/merchant/", views.merchant_dashboard, name="merchant_dashboard"),
    path("tengasale/hq/", views.hq_dashboard, name="hq_dashboard"),
]

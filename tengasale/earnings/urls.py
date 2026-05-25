from django.urls import path
from . import views

urlpatterns = [
    path("", views.earnings_home, name="earnings_home"),
]
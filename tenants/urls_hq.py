# circuitcity/tenants/urls_hq.py
from django.urls import path
from . import views_hq

app_name = "hq"

urlpatterns = [
    path("", views_hq.home, name="home"),
    path("agents/", views_hq.agents_list, name="agents_list"),
    path("stock-trends/", views_hq.stock_trends, name="stock_trends"),
]



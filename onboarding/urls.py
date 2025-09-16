# onboarding/urls.py
from django.urls import path
from . import views

app_name = "onboarding"
urlpatterns = [
    path("start/", views.start, name="start"),
    path("create-business/", views.create_business, name="create_business"),
    path("add-product/", views.add_product, name="add_product"),
]

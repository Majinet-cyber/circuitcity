from django.urls import path
from . import views

urlpatterns = [
    path("", views.landing, name="website_landing"),
    path("about/", views.about, name="website_about"),
    path("how-it-works/", views.how_it_works, name="website_how_it_works"),
    path("merchants/", views.merchants, name="website_merchants"),
    path("customers/", views.customers, name="website_customers"),
    path("integrations/", views.integrations, name="website_integrations"),
    path("faq/", views.faq, name="website_faq"),
    path("contact/", views.contact, name="website_contact"),
]

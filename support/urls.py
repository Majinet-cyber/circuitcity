# support/urls.py
from django.urls import path
from . import views

app_name = "support"

urlpatterns = [
    # Manager URLs
    path("tickets/", views.manager_ticket_list, name="manager_ticket_list"),
    path("tickets/create/", views.manager_ticket_create, name="manager_ticket_create"),
    path("tickets/<int:pk>/", views.manager_ticket_detail, name="manager_ticket_detail"),
    # HQ URLs
    path("hq/tickets/", views.hq_ticket_list, name="hq_ticket_list"),
    path("hq/tickets/<int:pk>/", views.hq_ticket_detail, name="hq_ticket_detail"),
]

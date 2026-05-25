from django.urls import path
from . import views

urlpatterns = [
    path("", views.manager_home, name="manager_home"),
    path("claim-next/", views.claim_next, name="claim_next"),
    path("review/<int:app_id>/", views.review_application, name="review_application"),
]
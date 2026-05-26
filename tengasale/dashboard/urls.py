from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("home/", views.home, name="home_redirect"),
    path("tengasale/merchant/", views.merchant_dashboard, name="merchant_dashboard"),
    path("tengasale/hq/", views.hq_dashboard, name="hq_dashboard"),
    path("tengasale/hq/users/", views.hq_users, name="hq_users"),
    path("tengasale/hq/users/<int:user_id>/", views.hq_user_edit, name="hq_user_edit"),
    path("tengasale/hq/deals/", views.hq_deals, name="hq_deals"),
    path("tengasale/hq/applications/", views.hq_applications, name="hq_applications"),
    path("tengasale/hq/commissions/", views.hq_commissions, name="hq_commissions"),
]

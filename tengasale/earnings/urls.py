from django.urls import path
from . import views

urlpatterns = [
    path("", views.earnings_home, name="earnings_home"),
    path("leaderboard/", views.merchant_leaderboard, name="merchant_leaderboard"),
    path("spin/", views.spin_rewards, name="spin_rewards"),
]

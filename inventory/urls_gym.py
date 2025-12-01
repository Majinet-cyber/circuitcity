# inventory/urls_gym.py
"""
URL patterns for gym operations.
"""
from django.urls import path
from . import views_gym

app_name = "gym"

urlpatterns = [
    # Dashboard
    path("", views_gym.gym_dashboard, name="dashboard"),
    
    # Members
    path("members/", views_gym.members_list, name="members_list"),
    path("member/add/", views_gym.member_add, name="member_add"),
    path("member/<int:member_id>/", views_gym.member_detail, name="member_detail"),
    path("member/<int:member_id>/edit/", views_gym.member_edit, name="member_edit"),
    path("member/<int:member_id>/archive/", views_gym.member_archive, name="member_archive"),
    path("member/<int:member_id>/restore/", views_gym.member_restore, name="member_restore"),
    
    # Payments
    path("payment/add/", views_gym.add_payment, name="add_payment"),
    
    # Settings
    path("settings/", views_gym.gym_settings_view, name="settings"),
]


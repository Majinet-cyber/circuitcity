# inventory/urls_gym.py
"""
URL patterns for gym operations.
"""
from django.urls import path, reverse_lazy
from django.views.generic import RedirectView
from . import views_gym

app_name = "gym"

urlpatterns = [
    # Dashboard
    path("", views_gym.gym_dashboard, name="dashboard"),
    
    # Alias for compatibility: /gym/dashboard/ -> /gym/
    path(
        "dashboard/",
        RedirectView.as_view(url=reverse_lazy("gym:dashboard"), permanent=False),
        name="dashboard_alias",
    ),
    
    # Members
    path("members/", views_gym.members_list, name="members_list"),
    path("member/add/", views_gym.member_add, name="member_add"),
    path("member/<int:member_id>/", views_gym.member_detail, name="member_detail"),
    path("member/<int:member_id>/edit/", views_gym.member_edit, name="member_edit"),
    path("member/<int:member_id>/archive/", views_gym.member_archive, name="member_archive"),
    path("member/<int:member_id>/restore/", views_gym.member_restore, name="member_restore"),
    path("member/<int:member_id>/set-paid/", views_gym.member_set_paid, name="member_set_paid"),
    path("member/<int:member_id>/checkin/", views_gym.member_checkin, name="member_checkin"),
    
    # Check-in
    path("checkin/", views_gym.checkin_page, name="checkin_page"),
    
    # Payments
    path("payment/add/", views_gym.add_payment, name="add_payment"),
    
    # Settings
    path("settings/", views_gym.gym_settings_view, name="settings"),
    
    # Trainers
    path("trainers/", views_gym.trainers_list, name="trainers_list"),
    path("trainer/add/", views_gym.trainer_add, name="trainer_add"),
    path("trainer/<int:trainer_id>/edit/", views_gym.trainer_edit, name="trainer_edit"),
    path("trainer/<int:trainer_id>/deactivate/", views_gym.trainer_deactivate, name="trainer_deactivate"),
]


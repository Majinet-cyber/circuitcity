# inventory/urls_gym.py
"""
URL patterns for gym operations.
"""
from django.urls import path, reverse_lazy
from django.views.generic import RedirectView

from . import views_gym, views_gym_qr, views_gym_wizard, views_gym_bulk_qr

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
    path("member/add/", views_gym_wizard.member_add_wizard, name="member_add"),
    path("member/add/old/", views_gym.member_add, name="member_add_old"),  # Keep old form as fallback
    path("member/<int:member_id>/", views_gym.member_detail, name="member_detail"),
    path("member/<int:member_id>/edit/", views_gym.member_edit, name="member_edit"),
    path("member/<int:member_id>/archive/", views_gym.member_archive, name="member_archive"),
    path("member/<int:member_id>/restore/", views_gym.member_restore, name="member_restore"),
    path("member/<int:member_id>/set-paid/", views_gym.member_set_paid, name="member_set_paid"),
    path("member/<int:member_id>/checkin/", views_gym.member_checkin, name="member_checkin"),
    path("member/<int:member_id>/delete/", views_gym.member_delete, name="member_delete"),
    path("member/<int:member_id>/purge/", views_gym.member_purge, name="member_purge"),
    path("member/<int:source_id>/merge/", views_gym.member_merge, name="member_merge"),
    # Bulk operations
    path("members/bulk-add/", views_gym.members_bulk_add, name="members_bulk_add"),
    path("members/bulk-add/results/", views_gym.members_bulk_add_results, name="members_bulk_add_results"),
    # QR Code routes (public, no auth required)
    path("qr/<uuid:qr_uuid>/", views_gym_qr.member_qr_status_public, name="member_qr_status_public"),
    path("qr/<uuid:qr_uuid>/image.png", views_gym_qr.member_qr_png, name="member_qr_png"),
    path("qr/<uuid:qr_uuid>/card.pdf", views_gym_qr.member_qr_card_pdf, name="member_qr_card_pdf"),
    path("qr/<uuid:qr_uuid>/print/", views_gym_qr.member_qr_print, name="member_qr_print"),
    path("qr/<uuid:qr_uuid>/whatsapp/", views_gym_qr.member_whatsapp_forward, name="member_whatsapp_forward"),
    # Bulk QR download (manager only)
    path("members/qr/bulk.pdf", views_gym_bulk_qr.bulk_qr_pdf, name="bulk_qr_pdf"),
    # Public member status (short, non-guessable token URL - no auth required)
    path("m/<str:token>/", views_gym_qr.public_member_status, name="gym_public_member_status"),
    # Check-in
    path("checkin/", views_gym.checkin_page, name="checkin_page"),
    # Leaderboard
    path("leaderboard/", views_gym.gym_leaderboard, name="leaderboard"),
    # Payments
    path("payment/add/", views_gym.add_payment, name="add_payment"),
    # Settings
    path("settings/", views_gym.gym_settings_view, name="settings"),
    # Trainers
    path("trainers/", views_gym.trainers_list, name="trainers_list"),
    path("trainer/add/", views_gym.trainer_add, name="trainer_add"),
    path("trainer/<int:trainer_id>/edit/", views_gym.trainer_edit, name="trainer_edit"),
    path("trainer/<int:trainer_id>/deactivate/", views_gym.trainer_deactivate, name="trainer_deactivate"),
    # Member Scanning
    path("scan/", views_gym.gym_scan_page, name="scan_member"),
    path("scan/lookup/", views_gym.gym_scan_lookup, name="scan_lookup"),
]

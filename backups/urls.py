# backups/urls.py
from django.urls import path
from . import views

app_name = 'backups'

urlpatterns = [
    # Manager backup management
    path('manager/', views.manager_backups_list, name='manager_list'),
    path('manager/generate/', views.generate_backup, name='generate'),
    path('manager/<int:snapshot_id>/download/', views.download_backup, name='download'),
    path('manager/<int:snapshot_id>/pdf/', views.export_backup_pdf, name='export_pdf'),
    path('manager/<int:snapshot_id>/resend-pdf/', views.resend_backup_pdf, name='resend_pdf'),
    path('manager/<int:snapshot_id>/delete/', views.delete_backup, name='delete'),
]


"""
Corrections Framework URL Configuration (Feb 2026)
===================================================

Vertical-aware URL patterns for data corrections.

All URLs are scoped by vertical:
- /corrections/<vertical>/
"""
from django.urls import path

from corrections import views

app_name = 'corrections'

urlpatterns = [
    # Dashboard
    path(
        '<str:vertical>/',
        views.corrections_dashboard,
        name='dashboard',
    ),
    
    # Entity browser (find records to correct)
    path(
        '<str:vertical>/entity/<str:entity_label>/',
        views.browse_entity,
        name='browse_entity',
    ),
    
    # Single record edit
    path(
        '<str:vertical>/entity/<str:entity_label>/<int:object_id>/edit/',
        views.edit_record,
        name='edit_record',
    ),
    
    # Single record delete (for duplicates/errors)
    path(
        '<str:vertical>/entity/<str:entity_label>/<int:object_id>/delete/',
        views.delete_record,
        name='delete_record',
    ),
    
    # Batch operations
    path(
        '<str:vertical>/batch/<int:batch_id>/',
        views.batch_detail,
        name='batch_detail',
    ),
    path(
        '<str:vertical>/batch/<int:batch_id>/apply/',
        views.batch_apply,
        name='batch_apply',
    ),
    path(
        '<str:vertical>/batch/<int:batch_id>/rollback/',
        views.batch_rollback,
        name='batch_rollback',
    ),
    
    # Audit trail
    path(
        '<str:vertical>/audit/',
        views.audit_trail,
        name='audit_trail',
    ),
]


# backups/views.py
"""
Views for per-business backup and export functionality.
"""
from __future__ import annotations

import os
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import File
from django.http import HttpRequest, HttpResponse, FileResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from tenants.utils import require_role, manager_required, get_active_business

from .models import BackupSnapshot, BackupStatus
from .helpers import export_business_data_to_zip, cleanup_temp_files


@login_required
@manager_required
def manager_backups_list(request: HttpRequest) -> HttpResponse:
    """
    List all backup snapshots for the active business.
    Managers can view, download, and generate new backups.
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("dashboard:home")
    
    # Get all backups for this business
    snapshots = BackupSnapshot.objects.filter(business=business).select_related('created_by')
    
    ctx = {
        'business': business,
        'snapshots': snapshots,
        'page_title': 'Data Backup & Export',
    }
    return render(request, 'backups/manager_list.html', ctx)


@login_required
@manager_required
@require_POST
def generate_backup(request: HttpRequest) -> HttpResponse:
    """
    Generate a new backup for the active business.
    
    This creates a BackupSnapshot and generates a ZIP file with all business data.
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("dashboard:home")
    
    # Check if there's already a pending/running backup
    existing = BackupSnapshot.objects.filter(
        business=business,
        status__in=[BackupStatus.PENDING, BackupStatus.RUNNING]
    ).exists()
    
    if existing:
        messages.warning(request, "A backup is already in progress. Please wait for it to complete.")
        return redirect("backups:manager_list")
    
    # Create new backup snapshot
    snapshot = BackupSnapshot.objects.create(
        business=business,
        created_by=request.user,
        status=BackupStatus.PENDING
    )
    
    # Generate backup (synchronous for now - can be moved to Celery task later)
    try:
        snapshot.status = BackupStatus.RUNNING
        snapshot.save(update_fields=['status'])
        
        # Export data to ZIP
        zip_path, records_count = export_business_data_to_zip(business)
        
        # Save ZIP file to snapshot
        with open(zip_path, 'rb') as f:
            snapshot.file.save(
                zip_path.name,
                File(f),
                save=False
            )
        
        # Get file size
        snapshot.file_size = os.path.getsize(zip_path)
        snapshot.records_count = records_count
        snapshot.status = BackupStatus.SUCCESS
        snapshot.completed_at = timezone.now()
        snapshot.save()
        
        # Clean up temp files
        cleanup_temp_files(zip_path)
        
        messages.success(
            request,
            f"Backup generated successfully! ({snapshot.file_size_mb} MB, "
            f"{sum(records_count.values()):,} records)"
        )
    
    except Exception as e:
        snapshot.status = BackupStatus.FAILED
        snapshot.error_message = str(e)
        snapshot.completed_at = timezone.now()
        snapshot.save()
        
        messages.error(request, f"Backup failed: {str(e)}")
    
    return redirect("backups:manager_list")


@login_required
@manager_required
def download_backup(request: HttpRequest, snapshot_id: int) -> HttpResponse:
    """
    Download a backup snapshot file.
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("dashboard:home")
    
    snapshot = get_object_or_404(
        BackupSnapshot,
        pk=snapshot_id,
        business=business
    )
    
    if not snapshot.file or snapshot.status != BackupStatus.SUCCESS:
        messages.error(request, "This backup is not available for download.")
        return redirect("backups:manager_list")
    
    try:
        response = FileResponse(
            snapshot.file.open('rb'),
            as_attachment=True,
            filename=os.path.basename(snapshot.file.name)
        )
        return response
    except Exception as e:
        messages.error(request, f"Error downloading backup: {str(e)}")
        return redirect("backups:manager_list")


@login_required
@manager_required
@require_POST
def delete_backup(request: HttpRequest, snapshot_id: int) -> HttpResponse:
    """
    Delete a backup snapshot.
    
    Note: This is one of the few places where we do a hard delete,
    since backups themselves are not critical business data.
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("dashboard:home")
    
    snapshot = get_object_or_404(
        BackupSnapshot,
        pk=snapshot_id,
        business=business
    )
    
    # Delete the file
    if snapshot.file:
        snapshot.file.delete(save=False)
    
    # Delete the snapshot record
    snapshot.delete()
    
    messages.success(request, "Backup deleted successfully.")
    return redirect("backups:manager_list")


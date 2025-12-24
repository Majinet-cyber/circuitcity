# backups/views.py
"""
Views for per-business backup and export functionality.
"""
from __future__ import annotations

import os
from io import BytesIO
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import File
from django.http import HttpRequest, HttpResponse, FileResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
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
        
        # Get file size from the actual saved file (not temp file)
        # This ensures we get the correct size after Django storage processes it
        if snapshot.file:
            snapshot.file_size = snapshot.file.size
        else:
            # Fallback to temp file size if file object doesn't have size
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


@login_required
@manager_required
def export_backup_pdf(request: HttpRequest, snapshot_id: int) -> HttpResponse:
    """
    Export a backup summary as PDF.
    
    This generates a PDF report showing:
    - Backup metadata (date, size, status)
    - Record counts per table
    - Business information
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
    
    if snapshot.status != BackupStatus.SUCCESS:
        messages.error(request, "This backup is not complete or failed. Cannot export as PDF.")
        return redirect("backups:manager_list")
    
    try:
        # Prepare context for PDF template
        ctx = {
            'snapshot': snapshot,
            'business': business,
            'total_records': sum(snapshot.records_count.values()) if snapshot.records_count else 0,
            'as_pdf': True,
        }
        
        # Render HTML template
        html = render_to_string('backups/backup_pdf.html', ctx)
        
        # Try WeasyPrint for proper PDF generation
        try:
            from weasyprint import HTML
            pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
            filename = f"backup_summary_{business.name}_{snapshot.created_at:%Y%m%d_%H%M%S}.pdf"
            return HttpResponse(
                pdf_bytes,
                content_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )
        except ImportError:
            # Fallback to minimal PDF generator if WeasyPrint is not available
            pdf_bytes = _generate_minimal_backup_pdf(snapshot, business)
            filename = f"backup_summary_{business.name}_{snapshot.created_at:%Y%m%d_%H%M%S}.pdf"
            return HttpResponse(
                pdf_bytes,
                content_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )
    
    except Exception as e:
        messages.error(request, f"Error generating PDF: {str(e)}")
        return redirect("backups:manager_list")


def _generate_minimal_backup_pdf(snapshot: BackupSnapshot, business) -> bytes:
    """
    Generate a minimal but valid PDF for backup summary when WeasyPrint is not available.
    Uses a simple PDF structure with basic metadata.
    """
    total_records = sum(snapshot.records_count.values()) if snapshot.records_count else 0
    
    # Build text content
    content_lines = [
        "BACKUP SUMMARY REPORT",
        "=" * 60,
        "",
        f"Business: {business.name}",
        f"Business Type: {business.business_kind}",
        "",
        f"Backup Date: {snapshot.created_at:%Y-%m-%d %H:%M:%S}",
        f"Status: {snapshot.get_status_display()}",
        f"File Size: {snapshot.file_size_mb} MB",
        f"Total Records: {total_records:,}",
        "",
        "RECORD COUNTS BY TABLE:",
        "-" * 60,
    ]
    
    # Add record counts
    if snapshot.records_count:
        for table, count in sorted(snapshot.records_count.items()):
            content_lines.append(f"{table:30} {count:>10,} records")
    
    content_lines.extend([
        "",
        "-" * 60,
        f"Generated by Emajinet on {timezone.now():%Y-%m-%d %H:%M:%S}",
    ])
    
    text = "\n".join(content_lines)
    
    # Escape special PDF characters
    text = text.replace("(", r"\(").replace(")", r"\)").replace("\\", r"\\")
    lines = text.splitlines()
    
    # Build PDF structure
    y = 750
    content_ops = []
    for i, line in enumerate(lines):
        if i == 0:  # Title in bold
            content_ops.append(f"BT /F2 14 Tf 50 {y - i * 14} Td ({line}) Tj ET")
        else:
            content_ops.append(f"BT /F1 10 Tf 50 {y - i * 14} Td ({line}) Tj ET")
    
    content_body = "\n".join(content_ops).encode("latin-1", "ignore")
    
    xref = []
    out = BytesIO()
    
    def w(s):
        out.write(s if isinstance(s, bytes) else s.encode("latin-1"))
    
    w("%PDF-1.4\n")
    xref.append(out.tell())
    w("1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj\n")
    xref.append(out.tell())
    w("2 0 obj <</Type /Pages /Kids [3 0 R] /Count 1>> endobj\n")
    xref.append(out.tell())
    w("3 0 obj <</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources <</Font <</F1 5 0 R /F2 6 0 R>>>>>> endobj\n")
    xref.append(out.tell())
    w(f"4 0 obj <</Length {len(content_body)}>> stream\n")
    out.write(content_body)
    w("\nendstream endobj\n")
    xref.append(out.tell())
    w("5 0 obj <</Type /Font /Subtype /Type1 /BaseFont /Courier>> endobj\n")
    xref.append(out.tell())
    w("6 0 obj <</Type /Font /Subtype /Type1 /BaseFont /Courier-Bold>> endobj\n")
    
    xref_pos = out.tell()
    w("xref\n0 7\n0000000000 65535 f \n")
    for pos in xref:
        w(f"{pos:010} 00000 n \n")
    w(f"trailer <</Size 7 /Root 1 0 R>>\nstartxref\n{xref_pos}\n%%EOF")
    
    return out.getvalue()


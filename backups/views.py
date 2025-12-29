# backups/views.py
"""
Views for per-business backup and export functionality.
"""
from __future__ import annotations

import os
import logging
from io import BytesIO
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import File
from django.core.mail import EmailMessage
from django.conf import settings
from django.http import HttpRequest, HttpResponse, FileResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from tenants.utils import require_role, manager_required, get_active_business
from tenants.models import Membership

from .models import BackupSnapshot, BackupStatus
from .helpers import export_business_data_to_zip, cleanup_temp_files

logger = logging.getLogger(__name__)


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
        
        # Get file size from temp file before saving (most reliable)
        # This ensures we get the actual ZIP file size in bytes
        zip_size_bytes = os.path.getsize(zip_path)
        
        # Save ZIP file to snapshot
        with open(zip_path, 'rb') as f:
            snapshot.file.save(
                zip_path.name,
                File(f),
                save=False
            )
        
        # Store file size in bytes (from temp file, which is the actual ZIP size)
        snapshot.file_size = zip_size_bytes
        
        snapshot.records_count = records_count
        snapshot.status = BackupStatus.SUCCESS
        snapshot.completed_at = timezone.now()
        snapshot.save()
        
        # Generate PDF and send email (don't fail backup if email fails)
        email_sent = False
        email_recipients = []
        try:
            pdf_bytes = _generate_backup_pdf_bytes(snapshot, business, request)
            manager_emails = _get_manager_emails(business, request.user)
            
            if manager_emails and pdf_bytes:
                email_sent = _send_backup_pdf_email(
                    snapshot=snapshot,
                    business=business,
                    pdf_bytes=pdf_bytes,
                    recipient_emails=manager_emails
                )
                email_recipients = manager_emails
        except Exception as e:
            # Log but don't fail the backup
            logger.error(f"Failed to send backup PDF email: {e}", exc_info=True)
        
        # Clean up temp files
        cleanup_temp_files(zip_path)
        
        # Build success message
        total_records = sum(records_count.values())
        tables_count = len(records_count)
        size_str = snapshot.size_display
        
        success_msg = f"Backup generated successfully! ({size_str}, {tables_count} tables, {total_records:,} records)"
        
        if email_sent and email_recipients:
            emails_str = ", ".join(email_recipients)
            success_msg += f" Sent to: {emails_str}"
        elif not email_sent and email_recipients:
            success_msg += " (Email failed; use 'Resend PDF' to retry)"
        
        messages.success(request, success_msg)
    
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
@require_POST
def resend_backup_pdf(request: HttpRequest, snapshot_id: int) -> HttpResponse:
    """
    Resend backup PDF report via email to manager(s).
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
        messages.error(request, "This backup is not complete or failed. Cannot send PDF.")
        return redirect("backups:manager_list")
    
    try:
        # Generate PDF
        pdf_bytes = _generate_backup_pdf_bytes(snapshot, business, request)
        
        # Get manager emails
        manager_emails = _get_manager_emails(business, request.user)
        
        if not manager_emails:
            messages.warning(request, "No manager email addresses found. Cannot send PDF.")
            return redirect("backups:manager_list")
        
        # Send email
        email_sent = _send_backup_pdf_email(
            snapshot=snapshot,
            business=business,
            pdf_bytes=pdf_bytes,
            recipient_emails=manager_emails
        )
        
        if email_sent:
            emails_str = ", ".join(manager_emails)
            messages.success(request, f"PDF report resent successfully to: {emails_str}")
        else:
            messages.error(request, "Failed to send PDF email. Please try again.")
    
    except Exception as e:
        logger.error(f"Error resending backup PDF: {e}", exc_info=True)
        messages.error(request, f"Error resending PDF: {str(e)}")
    
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
        # Generate PDF using shared helper function
        pdf_bytes = _generate_backup_pdf_bytes(snapshot, business, request)
        
        # Build filename
        business_name = business.name or "business"
        filename = f"backup_summary_{business_name}_{snapshot.created_at:%Y%m%d_%H%M%S}.pdf"
        # Sanitize filename
        filename = "".join(c for c in filename if c.isalnum() or c in ('_', '-', '.'))
        
        return HttpResponse(
            pdf_bytes,
            content_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    
    except Exception as e:
        messages.error(request, f"Error generating PDF: {str(e)}")
        return redirect("backups:manager_list")


def _generate_backup_pdf_bytes(snapshot: BackupSnapshot, business, request: HttpRequest = None) -> bytes:
    """
    Generate PDF bytes for a backup snapshot.
    
    Uses WeasyPrint if available, otherwise falls back to minimal PDF generator.
    """
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
        base_url = request.build_absolute_uri("/") if request else None
        pdf_bytes = HTML(string=html, base_url=base_url).write_pdf()
        return pdf_bytes
    except ImportError:
        # Fallback to minimal PDF generator if WeasyPrint is not available
        return _generate_minimal_backup_pdf(snapshot, business)


def _get_manager_emails(business, requesting_user) -> list[str]:
    """
    Get list of manager email addresses for a business.
    
    Returns:
        List of email addresses (primary: requesting user, plus other active managers)
    """
    emails = []
    
    # Primary: requesting user's email
    if requesting_user and hasattr(requesting_user, 'email') and requesting_user.email:
        emails.append(requesting_user.email)
    
    # Also get other active managers in the business
    try:
        manager_memberships = Membership.objects.filter(
            business=business,
            role='MANAGER',
            status='ACTIVE'
        ).select_related('user')
        
        for membership in manager_memberships:
            user = membership.user
            if user and hasattr(user, 'email') and user.email:
                email = user.email.strip()
                if email and email not in emails:  # Avoid duplicates
                    emails.append(email)
    except Exception as e:
        logger.warning(f"Error fetching manager emails: {e}", exc_info=True)
    
    return emails


def _send_backup_pdf_email(snapshot: BackupSnapshot, business, pdf_bytes: bytes, recipient_emails: list[str]) -> bool:
    """
    Send backup PDF report via email.
    
    Returns:
        True if email was sent successfully, False otherwise
    """
    if not recipient_emails:
        logger.warning("No recipient emails provided for backup PDF")
        return False
    
    # Filter out empty emails
    valid_emails = [e.strip() for e in recipient_emails if e and e.strip()]
    if not valid_emails:
        logger.warning("No valid email addresses for backup PDF")
        return False
    
    try:
        # Build email subject
        business_name = business.name or "Business"
        date_str = snapshot.created_at.strftime("%b %d, %Y %H:%M")
        subject = f"Emajinet Backup ({business_name}) — {date_str}"
        
        # Build email body
        body = "Backup completed successfully. PDF report attached.\n\n"
        body += f"Backup ID: {snapshot.id}\n"
        body += f"Generated: {snapshot.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
        body += f"File Size: {snapshot.size_display}\n"
        
        total_records = sum(snapshot.records_count.values()) if snapshot.records_count else 0
        body += f"Total Records: {total_records:,}\n"
        
        # Create email message
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@emajinet.com')
        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_email,
            to=valid_emails
        )
        
        # Attach PDF
        filename = f"backup_summary_{business_name}_{snapshot.created_at:%Y%m%d_%H%M%S}.pdf"
        # Sanitize filename (remove invalid chars)
        filename = "".join(c for c in filename if c.isalnum() or c in ('_', '-', '.'))
        msg.attach(filename, pdf_bytes, 'application/pdf')
        
        # Send email (fail_silently=False to catch errors)
        msg.send(fail_silently=False)
        
        logger.info(f"Backup PDF email sent successfully to {valid_emails}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send backup PDF email: {e}", exc_info=True)
        return False


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
        f"File Size: {snapshot.size_display}",
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


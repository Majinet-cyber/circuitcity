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

from .models import BackupSnapshot, BackupStatus, DataExportLog
from .helpers import (
    EXPORT_CATEGORY_LABELS,
    build_executive_summary,
    build_export_summary,
    cleanup_temp_files,
    create_export_xlsx_bytes,
    export_business_data_to_zip,
    create_export_zip_path,
    restore_business_from_snapshot,
    snapshot_has_restore_fixture,
)

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

    snapshots = BackupSnapshot.objects.filter(business=business).select_related("created_by")
    latest_success = snapshots.filter(status=BackupStatus.SUCCESS).first()
    last_export = DataExportLog.objects.filter(business=business, status=BackupStatus.SUCCESS).first()
    export_summary = build_export_summary(business, "all", include_rows=False)
    category_cards = []
    category_icons = {
        "inventory": "bi-box-seam",
        "financial": "bi-cash-coin",
        "staff": "bi-people",
        "sales": "bi-receipt",
        "wallet": "bi-wallet2",
        "reports": "bi-graph-up-arrow",
        "marketplace": "bi-shop",
    }
    for category, label in EXPORT_CATEGORY_LABELS.items():
        if category == "all":
            continue
        summary = build_export_summary(business, category, include_rows=False)
        category_cards.append(
            {
                "key": category,
                "label": label,
                "icon": category_icons.get(category, "bi-file-earmark-spreadsheet"),
                "record_count": summary["total_records"],
                "section_count": summary["section_count"],
                "last_export": DataExportLog.objects.filter(
                    business=business, category=category, status=BackupStatus.SUCCESS
                ).first(),
            }
        )

    now = timezone.now()
    if latest_success:
        days_since_backup = (now - latest_success.created_at).days
        backup_health = "Protected" if days_since_backup <= 1 else "Backup overdue" if days_since_backup >= 7 else "Export ready"
        data_safety_score = 95 if days_since_backup <= 1 else 82 if days_since_backup < 7 else 62
    else:
        days_since_backup = None
        backup_health = "Backup overdue"
        data_safety_score = 48

    estimate_bytes = max(export_summary["total_records"] * 220, 4096)
    if latest_success and latest_success.file_size:
        estimate_bytes = latest_success.file_size

    ctx = {
        "business": business,
        "snapshots": snapshots,
        "page_title": "Backup & Export Center",
        "latest_success": latest_success,
        "last_export": last_export,
        "total_records": export_summary["total_records"],
        "section_count": export_summary["section_count"],
        "category_cards": category_cards,
        "backup_health": backup_health,
        "data_safety_score": data_safety_score,
        "estimate_bytes": estimate_bytes,
        "estimate_mb": max(round(estimate_bytes / (1024 * 1024), 2), 0.01),
        "days_since_backup": days_since_backup,
        "auto_backup_status": "Daily snapshots ready",
        "active_tab": "data_vault",
        "show_search": False,
    }
    return render(request, "backups/manager_list.html", ctx)


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
        business=business, status__in=[BackupStatus.PENDING, BackupStatus.RUNNING]
    ).exists()

    if existing:
        messages.warning(request, "A backup is already in progress. Please wait for it to complete.")
        return redirect("backups:manager_list")

    # Create new backup snapshot
    snapshot = BackupSnapshot.objects.create(business=business, created_by=request.user, status=BackupStatus.PENDING)

    # Generate backup (synchronous for now - can be moved to Celery task later)
    try:
        snapshot.status = BackupStatus.RUNNING
        snapshot.save(update_fields=["status"])

        # Export data to ZIP
        zip_path, records_count = export_business_data_to_zip(business)

        # Get file size from temp file before saving (most reliable)
        # This ensures we get the actual ZIP file size in bytes
        zip_size_bytes = os.path.getsize(zip_path)

        # Save ZIP file to snapshot
        with open(zip_path, "rb") as f:
            snapshot.file.save(zip_path.name, File(f), save=False)

        # Store file size in bytes (from temp file, which is the actual ZIP size)
        snapshot.file_size = zip_size_bytes

        snapshot.records_count = records_count
        snapshot.status = BackupStatus.SUCCESS
        snapshot.completed_at = timezone.now()
        snapshot.save()

        DataExportLog.objects.create(
            business=business,
            user=request.user,
            category=DataExportLog.ExportCategory.ALL,
            export_format=DataExportLog.ExportFormat.ZIP,
            label="Manual snapshot",
            records_count=records_count,
            file_size=zip_size_bytes,
            status=BackupStatus.SUCCESS,
            snapshot=snapshot,
        )

        # Generate PDF and send email (don't fail backup if email fails)
        email_sent = False
        email_recipients = []
        try:
            pdf_bytes = _generate_backup_pdf_bytes(snapshot, business, request)
            manager_emails = _get_manager_emails(business, request.user)

            if manager_emails and pdf_bytes:
                email_sent = _send_backup_pdf_email(
                    snapshot=snapshot, business=business, pdf_bytes=pdf_bytes, recipient_emails=manager_emails
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

    snapshot = get_object_or_404(BackupSnapshot, pk=snapshot_id, business=business)

    if not snapshot.file or snapshot.status != BackupStatus.SUCCESS:
        messages.error(request, "This backup is not available for download.")
        return redirect("backups:manager_list")

    try:
        response = FileResponse(
            snapshot.file.open("rb"), as_attachment=True, filename=os.path.basename(snapshot.file.name)
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

    snapshot = get_object_or_404(BackupSnapshot, pk=snapshot_id, business=business)

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

    snapshot = get_object_or_404(BackupSnapshot, pk=snapshot_id, business=business)

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
            snapshot=snapshot, business=business, pdf_bytes=pdf_bytes, recipient_emails=manager_emails
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

    snapshot = get_object_or_404(BackupSnapshot, pk=snapshot_id, business=business)

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
        filename = "".join(c for c in filename if c.isalnum() or c in ("_", "-", "."))

        return HttpResponse(
            pdf_bytes,
            content_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except Exception as e:
        messages.error(request, f"Error generating PDF: {str(e)}")
        return redirect("backups:manager_list")


def _log_export_action(
    *,
    business,
    user,
    category: str,
    export_format: str,
    records_count: dict,
    file_size: int | None = None,
    label: str = "",
    snapshot: BackupSnapshot | None = None,
    status: str = BackupStatus.SUCCESS,
):
    try:
        DataExportLog.objects.create(
            business=business,
            user=user,
            category=category,
            export_format=export_format,
            label=label,
            records_count=records_count or {},
            file_size=file_size,
            status=status,
            snapshot=snapshot,
        )
    except Exception:
        logger.warning("Could not log data export action", exc_info=True)


@login_required
@manager_required
@require_http_methods(["POST"])
def export_data(request: HttpRequest, category: str = "all") -> HttpResponse:
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("dashboard:home")

    category = category if category in EXPORT_CATEGORY_LABELS else "all"
    export_format = (request.POST.get("format") or "zip").lower()
    business_slug = "".join(c for c in (business.name or "business") if c.isalnum() or c in ("-", "_")).strip() or "business"
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")

    try:
        if export_format in {"zip", "csv"}:
            zip_path, records_count = create_export_zip_path(business, category)
            file_size = os.path.getsize(zip_path)
            _log_export_action(
                business=business,
                user=request.user,
                category=category,
                export_format=DataExportLog.ExportFormat.ZIP if export_format == "zip" else DataExportLog.ExportFormat.CSV,
                records_count=records_count,
                file_size=file_size,
                label=EXPORT_CATEGORY_LABELS.get(category, category.title()),
            )
            filename = f"{business_slug}_{category}_{'csv_package' if export_format == 'csv' else 'data_vault'}_{timestamp}.zip"
            return FileResponse(open(zip_path, "rb"), as_attachment=True, filename=filename)

        if export_format in {"xlsx", "excel"}:
            xlsx_bytes, records_count = create_export_xlsx_bytes(business, category)
            _log_export_action(
                business=business,
                user=request.user,
                category=category,
                export_format=DataExportLog.ExportFormat.XLSX,
                records_count=records_count,
                file_size=len(xlsx_bytes),
                label=EXPORT_CATEGORY_LABELS.get(category, category.title()),
            )
            filename = f"{business_slug}_{category}_data_vault_{timestamp}.xlsx"
            return HttpResponse(
                xlsx_bytes,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        if export_format == "pdf":
            return executive_report_pdf(request)

        messages.error(request, "Unsupported export format.")
    except Exception as exc:
        _log_export_action(
            business=business,
            user=request.user,
            category=category,
            export_format=export_format[:16],
            records_count={},
            label=EXPORT_CATEGORY_LABELS.get(category, category.title()),
            status=BackupStatus.FAILED,
        )
        logger.error("Data export failed: %s", exc, exc_info=True)
        messages.error(request, f"Export failed: {exc}")

    return redirect("backups:manager_list")


@login_required
@manager_required
def executive_report_pdf(request: HttpRequest) -> HttpResponse:
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("dashboard:home")

    snapshot = BackupSnapshot.objects.filter(business=business, status=BackupStatus.SUCCESS).first()
    if snapshot is None:
        summary = build_export_summary(business, "all", include_rows=False)
        snapshot = BackupSnapshot(
            business=business,
            created_by=request.user,
            status=BackupStatus.SUCCESS,
            created_at=timezone.now(),
            completed_at=timezone.now(),
            records_count=summary["records_count"],
        )

    pdf_bytes = _generate_backup_pdf_bytes(snapshot, business, request, executive=True)
    _log_export_action(
        business=business,
        user=request.user,
        category=DataExportLog.ExportCategory.REPORTS,
        export_format=DataExportLog.ExportFormat.PDF,
        records_count=snapshot.records_count,
        file_size=len(pdf_bytes),
        label="Business Summary Report",
        snapshot=snapshot if snapshot.pk else None,
    )
    business_slug = "".join(c for c in (business.name or "business") if c.isalnum() or c in ("-", "_")).strip() or "business"
    filename = f"{business_slug}_business_summary_{timezone.now():%Y%m%d_%H%M%S}.pdf"
    return HttpResponse(
        pdf_bytes,
        content_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@login_required
@manager_required
def compare_backup(request: HttpRequest, snapshot_id: int) -> HttpResponse:
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("dashboard:home")
    snapshot = get_object_or_404(BackupSnapshot, pk=snapshot_id, business=business)
    previous = BackupSnapshot.objects.filter(
        business=business,
        status=BackupStatus.SUCCESS,
        created_at__lt=snapshot.created_at,
    ).first()
    keys = sorted(set((snapshot.records_count or {}).keys()) | set((previous.records_count or {}).keys() if previous else []))
    comparisons = []
    for key in keys:
        current = (snapshot.records_count or {}).get(key, 0)
        before = (previous.records_count or {}).get(key, 0) if previous else 0
        comparisons.append({"label": key.replace("_", " ").title(), "current": current, "previous": before, "delta": current - before})
    return render(
        request,
        "backups/compare.html",
        {"business": business, "snapshot": snapshot, "previous": previous, "comparisons": comparisons},
    )


@login_required
@manager_required
@require_http_methods(["GET", "POST"])
def restore_backup(request: HttpRequest, snapshot_id: int) -> HttpResponse:
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("dashboard:home")
    snapshot = get_object_or_404(BackupSnapshot, pk=snapshot_id, business=business)

    if snapshot.status != BackupStatus.SUCCESS or not snapshot.file:
        messages.error(request, "Only completed snapshots can be restored.")
        return redirect("backups:manager_list")

    if request.method == "POST":
        typed_name = (request.POST.get("business_name") or "").strip()
        confirmation = (request.POST.get("confirmation") or "").strip().upper()
        if typed_name != business.name or confirmation != "RESTORE":
            messages.error(request, "Restore confirmation did not match. No data was changed.")
            return redirect("backups:restore", snapshot_id=snapshot.id)

        _log_export_action(
            business=business,
            user=request.user,
            category=DataExportLog.ExportCategory.RESTORE,
            export_format=DataExportLog.ExportFormat.ZIP,
            records_count=snapshot.records_count,
            file_size=snapshot.file_size,
            label="Restore package validated",
            snapshot=snapshot,
        )
        try:
            restored = restore_business_from_snapshot(snapshot, business)
        except Exception as exc:
            messages.error(request, f"Restore could not be completed: {exc}")
            return redirect("backups:restore", snapshot_id=snapshot.id)

        messages.success(request, f"Restore completed safely. {restored:,} business records were restored from the snapshot.")
        return redirect("backups:manager_list")

    return render(
        request,
        "backups/restore_confirm.html",
        {"business": business, "snapshot": snapshot, "can_restore": snapshot_has_restore_fixture(snapshot)},
    )


def _generate_backup_pdf_bytes(snapshot: BackupSnapshot, business, request: HttpRequest = None, executive: bool = False) -> bytes:
    """
    Generate PDF bytes for a backup snapshot.

    Uses WeasyPrint if available, otherwise falls back to minimal PDF generator.
    """
    # Prepare context for PDF template
    ctx = {
        "snapshot": snapshot,
        "business": business,
        "total_records": sum(snapshot.records_count.values()) if snapshot.records_count else 0,
        "as_pdf": True,
        "executive": executive,
        "executive_summary": build_executive_summary(business) if executive else None,
    }

    # Render HTML template
    html = render_to_string("backups/backup_pdf.html", ctx)

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
    if requesting_user and hasattr(requesting_user, "email") and requesting_user.email:
        emails.append(requesting_user.email)

    # Also get other active managers in the business
    try:
        manager_memberships = Membership.objects.filter(
            business=business, role="MANAGER", status="ACTIVE"
        ).select_related("user")

        for membership in manager_memberships:
            user = membership.user
            if user and hasattr(user, "email") and user.email:
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
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@emajinet.com")
        msg = EmailMessage(subject=subject, body=body, from_email=from_email, to=valid_emails)

        # Attach PDF
        filename = f"backup_summary_{business_name}_{snapshot.created_at:%Y%m%d_%H%M%S}.pdf"
        # Sanitize filename (remove invalid chars)
        filename = "".join(c for c in filename if c.isalnum() or c in ("_", "-", "."))
        msg.attach(filename, pdf_bytes, "application/pdf")

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

    content_lines.extend(
        [
            "",
            "-" * 60,
            f"Generated by Emajinet on {timezone.now():%Y-%m-%d %H:%M:%S}",
        ]
    )

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
    w(
        "3 0 obj <</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources <</Font <</F1 5 0 R /F2 6 0 R>>>>>> endobj\n"
    )
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

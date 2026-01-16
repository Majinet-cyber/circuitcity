# billing/views_invoice.py
"""
Invoice management views (list, download, send, preview).
Handles invoice PDF generation, email sending, and preview with friendly error handling.
"""
from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from tenants.utils import require_business

from .models import Invoice

logger = logging.getLogger(__name__)


@login_required
@require_business
def invoice_list(request: HttpRequest) -> HttpResponse:
    """
    List all invoices for current business.
    Managers can see their business invoices.
    """
    business = request.business

    invoices = Invoice.objects.filter(business=business).order_by("-created_at")

    context = {
        "business": business,
        "invoices": invoices,
    }

    return render(request, "billing/invoice_list.html", context)


def _get_invoice_or_friendly_404(request, pk):
    """
    Get invoice scoped to business with friendly 404 handling.
    
    Returns:
        (invoice, None) if found
        (None, HttpResponse) if not found (friendly error page)
    """
    business = request.business
    
    try:
        invoice = Invoice.objects.get(pk=pk, business=business)
        return invoice, None
    except Invoice.DoesNotExist:
        # Check if invoice exists but belongs to different business
        try:
            Invoice.objects.get(pk=pk)
            # Exists but wrong business - security issue, show generic 404
            logger.warning(
                f"Invoice {pk} access denied for business {business.id} - belongs to different business"
            )
        except Invoice.DoesNotExist:
            # Truly doesn't exist
            logger.warning(f"Invoice {pk} not found for business {business.id}")
        
        # Return friendly error page
        context = {
            "business": business,
            "invoice_id": pk,
            "message": "The invoice you're looking for could not be found.",
            "subtext": "This invoice may have been deleted, or you may not have permission to view it.",
        }
        response = render(request, "billing/invoice_not_found.html", context, status=404)
        return None, response


@login_required
@require_business
def invoice_preview(request: HttpRequest, pk) -> HttpResponse:
    """
    Preview invoice as HTML.
    
    Shows invoice details in a printable HTML format.
    This always works even if PDF generation fails.
    
    Args:
        pk: Invoice UUID or int primary key
    """
    invoice, error_response = _get_invoice_or_friendly_404(request, pk)
    if error_response:
        return error_response
    
    business = request.business
    
    # Get payment method display
    payment_method = "N/A"
    subscription = getattr(invoice, "subscription", None)
    if subscription:
        payment_method = subscription.get_payment_method_display() if hasattr(subscription, "get_payment_method_display") else "Mobile Money"
    
    context = {
        "invoice": invoice,
        "business": business,
        "issuer_name": "Emajinet",
        "issuer_email": "support@emajinet.africa",
        "issuer_phone": "+265 991 234 567",
        "payment_method": payment_method,
        "can_download": True,
    }
    
    return render(request, "billing/invoice_preview.html", context)


@login_required
@require_business
def invoice_download(request: HttpRequest, pk) -> HttpResponse:
    """
    Download invoice as PDF.

    Generates PDF on-demand if not already generated,
    then serves the file.
    
    NEVER returns 404 for valid invoices - falls back to HTML if PDF fails.

    Args:
        pk: Invoice UUID or int primary key
    """
    invoice, error_response = _get_invoice_or_friendly_404(request, pk)
    if error_response:
        return error_response
    
    invoice_number = getattr(invoice, 'number', pk) or pk

    # Generate PDF if not already generated or if file missing
    try:
        needs_generation = not getattr(invoice, 'pdf_file', None) or not getattr(invoice, 'pdf_generated_at', None)
        
        # Also regenerate if file doesn't exist on storage
        pdf_file = getattr(invoice, 'pdf_file', None)
        if pdf_file and pdf_file.name:
            try:
                # Use context manager to ensure file handle is closed
                with pdf_file.open("rb"):
                    pass  # Just checking if file exists and is readable
            except Exception:
                needs_generation = True
        
        if needs_generation:
            from . import pdf_generator

            success = pdf_generator.generate_and_save_invoice_pdf(invoice)

            if not success:
                logger.error(f"Failed to generate PDF for invoice {invoice_number}")
                # FALLBACK: Redirect to HTML preview instead of failing
                messages.warning(
                    request, 
                    "PDF generation is temporarily unavailable. Showing HTML invoice instead."
                )
                return redirect("billing:invoice_preview", pk=pk)
            
            # Refresh the invoice to get the updated pdf_file
            invoice.refresh_from_db()

        # Serve PDF file
        pdf_file = getattr(invoice, 'pdf_file', None)
        if not pdf_file:
            logger.error(f"PDF file missing after generation for invoice {invoice_number}")
            # FALLBACK: Redirect to HTML preview
            messages.warning(
                request, 
                "PDF file not available. Showing HTML invoice instead."
            )
            return redirect("billing:invoice_preview", pk=pk)
            
        response = FileResponse(
            pdf_file.open("rb"),
            content_type="application/pdf",
        )
        response["Content-Disposition"] = f'attachment; filename="invoice_{invoice_number}.pdf"'
        return response

    except Exception as e:
        logger.error(f"Error serving invoice PDF {invoice_number}: {e}", exc_info=True)
        # FALLBACK: Redirect to HTML preview
        messages.warning(
            request, 
            "An error occurred generating the PDF. Showing HTML invoice instead."
        )
        return redirect("billing:invoice_preview", pk=pk)


@login_required
@require_business
def invoice_send(request: HttpRequest, pk) -> HttpResponse:
    """
    Send invoice via email to manager.
    
    Uses idempotency to prevent duplicate sends.
    """
    invoice, error_response = _get_invoice_or_friendly_404(request, pk)
    if error_response:
        return error_response
    
    business = request.business
    
    # Check if already sent recently (idempotency - allow resend after 5 minutes)
    meta = invoice.meta or {}
    last_sent_at = meta.get("last_email_sent_at")
    if last_sent_at:
        try:
            from datetime import datetime
            sent_time = datetime.fromisoformat(last_sent_at)
            now = timezone.now()
            # Allow resend after 5 minutes
            if hasattr(sent_time, 'tzinfo') and sent_time.tzinfo is None:
                sent_time = timezone.make_aware(sent_time)
            minutes_since = (now - sent_time).total_seconds() / 60
            if minutes_since < 5:
                messages.info(
                    request, 
                    f"Invoice was sent recently. Please wait a few minutes before sending again."
                )
                return redirect("billing:invoices")
        except Exception:
            pass
    
    # Queue email sending
    try:
        from . import tasks
        
        # Mark that we're sending (idempotency)
        invoice.meta = meta
        invoice.meta["last_email_sent_at"] = timezone.now().isoformat()
        invoice.meta["email_send_requested_by"] = str(request.user.id)
        invoice.save(update_fields=["meta", "updated_at"])
        
        # Queue the task
        tasks.send_invoice_paid_email.delay(str(invoice.id))
        
        recipient = invoice.manager_email or getattr(business, "email", "manager")
        messages.success(
            request, 
            f"Invoice {invoice.number} is being sent to {recipient}."
        )
    except Exception as e:
        logger.error(f"Failed to queue invoice email for {invoice.number}: {e}", exc_info=True)
        messages.error(
            request, 
            "Failed to send invoice email. Please try again or contact support."
        )
    
    return redirect("billing:invoices")

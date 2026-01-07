# billing/views_invoice.py
"""
Invoice management views (list, download, send).
"""
from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

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


@login_required
@require_business
def invoice_download(request: HttpRequest, pk) -> HttpResponse:
    """
    Download invoice as PDF.

    Generates PDF on-demand if not already generated,
    then serves the file.

    Args:
        pk: Invoice UUID or int primary key
    """
    business = request.business

    # Get invoice (scoped to business for security)
    invoice = get_object_or_404(Invoice, pk=pk, business=business)

    # Generate PDF if not already generated or if file missing
    if not invoice.pdf_file or not invoice.pdf_generated_at:
        from . import pdf_generator

        success = pdf_generator.generate_and_save_invoice_pdf(invoice)

        if not success:
            messages.error(request, "Failed to generate PDF. Please try again or contact support.")
            return redirect("billing:invoices")

    # Serve PDF file
    try:
        response = FileResponse(
            invoice.pdf_file.open("rb"),
            content_type="application/pdf",
        )
        response["Content-Disposition"] = f'attachment; filename="invoice_{invoice.number}.pdf"'
        return response

    except Exception as e:
        logger.error(f"Error serving invoice PDF {invoice.number}: {e}", exc_info=True)
        messages.error(request, "Failed to download invoice. Please try again.")
        return redirect("billing:invoices")


@login_required
def invoice_send(request: HttpRequest, pk) -> HttpResponse:
    """
    Send invoice via email (placeholder for STEP 6).
    """
    # This will be implemented in STEP 6 (Email Receipts)
    messages.info(request, "Email sending will be implemented in the next phase.")
    return redirect("billing:invoices")

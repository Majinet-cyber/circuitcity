# billing/views_receipt.py
"""
Receipt PDF generation endpoints for payments.
"""
from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404

from tenants.utils import manager_required, require_business

from . import pdf_generator
from .models import Payment, PaymentTransaction

logger = logging.getLogger(__name__)


@login_required
@require_business
@manager_required
def payment_receipt_pdf(request: HttpRequest, payment_id) -> HttpResponse:
    """
    Generate and download receipt PDF for a payment.

    Security: Only managers of the payment's business can access.
    """
    business = request.business

    # Get payment (scoped to business)
    payment = get_object_or_404(Payment, id=payment_id, business=business)

    # Only allow successful payments to have receipts
    if payment.status != Payment.Status.SUCCEEDED:
        return HttpResponseForbidden("Receipts are only available for successful payments.")

    # Generate receipt PDF
    pdf_bytes = pdf_generator.generate_payment_receipt_pdf(payment)

    if not pdf_bytes:
        return HttpResponse("Failed to generate receipt PDF.", status=500)

    # Return PDF as response
    from io import BytesIO

    response = FileResponse(
        BytesIO(pdf_bytes),
        content_type="application/pdf",
    )
    response["Content-Disposition"] = f'attachment; filename="receipt_{payment.reference or payment.id}.pdf"'
    return response


@login_required
@require_business
@manager_required
def transaction_receipt_pdf(request: HttpRequest, transaction_id) -> HttpResponse:
    """
    Generate and download receipt PDF for a PaymentTransaction.

    Security: Only managers of the transaction's business can access.
    """
    business = request.business

    # Get transaction (scoped to business)
    transaction = get_object_or_404(PaymentTransaction, id=transaction_id, business=business)

    # Only allow successful transactions to have receipts
    if transaction.status != PaymentTransaction.Status.SUCCESS:
        return HttpResponseForbidden("Receipts are only available for successful transactions.")

    # Generate receipt PDF
    pdf_bytes = pdf_generator.generate_transaction_receipt_pdf(transaction)

    if not pdf_bytes:
        return HttpResponse("Failed to generate receipt PDF.", status=500)

    # Return PDF as response
    from io import BytesIO

    response = FileResponse(
        BytesIO(pdf_bytes),
        content_type="application/pdf",
    )
    response["Content-Disposition"] = f'attachment; filename="receipt_{transaction.tx_ref}.pdf"'
    return response

# billing/views_billing_hub.py
"""
Premium Billing Hub for Managers
Stripe-style billing portal with invoices, payments, and subscription management.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from tenants.utils import manager_required, require_business

from .models import BusinessSubscription, Invoice, Payment, PaymentTransaction, SubscriptionPlan

logger = logging.getLogger(__name__)


@login_required
@require_business
@manager_required
def billing_hub(request: HttpRequest) -> HttpResponse:
    """
    Premium billing hub page for managers.

    Shows:
    - Current plan + trial status + limits
    - Past payments (successful/failed/pending)
    - Invoices and receipts (downloadable PDF)
    - Billing history with clear timeline
    - Next billing date, amount, billing cycle, payment method
    - Payment attempts + failure reason (if available)
    - Pay now / Retry button for failed or pending invoices
    """
    business = request.business

    # Get subscription
    try:
        subscription = business.subscription
    except BusinessSubscription.DoesNotExist:
        # Optionally create a trial subscription
        subscription = BusinessSubscription.ensure_trial_for_business(business)

    # Get invoices (scoped to business)
    invoices = Invoice.objects.filter(business=business).order_by("-created_at")

    # Get payments (scoped to business)
    # Include both Payment model records and PaymentTransaction records
    payments = Payment.objects.filter(business=business).order_by("-created_at")
    payment_transactions = PaymentTransaction.objects.filter(business=business).order_by("-created_at")

    # Calculate KPIs
    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)

    # Total paid (last 30 days)
    total_paid_30d = Payment.objects.filter(
        business=business,
        status=Payment.Status.SUCCEEDED,
        processed_at__gte=thirty_days_ago,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    # Total paid (all time)
    total_paid_all_time = Payment.objects.filter(
        business=business,
        status=Payment.Status.SUCCEEDED,
    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")

    # Outstanding invoices count
    outstanding_invoices = invoices.filter(
        status__in=[Invoice.Status.ISSUED, Invoice.Status.SENT, Invoice.Status.OVERDUE]
    ).count()

    # Last payment status
    last_payment = payments.filter(status=Payment.Status.SUCCEEDED).first()
    last_payment_status = "success" if last_payment else "none"

    # If no Payment records, check PaymentTransaction
    if not last_payment:
        last_txn = payment_transactions.filter(status=PaymentTransaction.Status.SUCCESS).first()
        if last_txn:
            last_payment_status = "success"

    # Get failed/pending payments for retry
    failed_payments = payments.filter(status=Payment.Status.FAILED)
    pending_payments = payments.filter(status=Payment.Status.PENDING)

    # Combine PaymentTransaction records that don't have Payment records
    # For display purposes, we'll show both Payment and PaymentTransaction
    all_payment_records = []

    # Add Payment records
    for payment in payments:
        all_payment_records.append(
            {
                "type": "payment",
                "id": payment.id,
                "date": payment.created_at,
                "amount": payment.amount,
                "currency": payment.currency,
                "status": payment.status,
                "provider": payment.provider,
                "reference": payment.reference or payment.external_id,
                "invoice": payment.invoice,
                "failure_reason": payment.failure_reason,
                "processed_at": payment.processed_at,
            }
        )

    # Add PaymentTransaction records that don't have corresponding Payment records
    for txn in payment_transactions:
        # Check if there's already a Payment record for this transaction
        existing_payment = payments.filter(Q(reference=txn.tx_ref) | Q(external_id=txn.tx_ref)).first()

        if not existing_payment:
            all_payment_records.append(
                {
                    "type": "transaction",
                    "id": txn.id,
                    "date": txn.created_at,
                    "amount": txn.amount,
                    "currency": txn.currency,
                    "status": "success"
                    if txn.status == PaymentTransaction.Status.SUCCESS
                    else ("failed" if txn.status == PaymentTransaction.Status.FAILED else "pending"),
                    "provider": txn.provider,
                    "reference": txn.tx_ref,
                    "invoice": None,  # PaymentTransaction doesn't directly link to Invoice
                    "failure_reason": None,  # PaymentTransaction doesn't have failure_reason
                    "processed_at": txn.updated_at if txn.status == PaymentTransaction.Status.SUCCESS else None,
                }
            )

    # Sort all payment records by date
    all_payment_records.sort(key=lambda x: x["date"], reverse=True)

    context = {
        "business": business,
        "subscription": subscription,
        "invoices": invoices,
        "payments": payments,
        "payment_transactions": payment_transactions,
        "all_payment_records": all_payment_records,
        "total_paid_30d": total_paid_30d,
        "total_paid_all_time": total_paid_all_time,
        "outstanding_invoices": outstanding_invoices,
        "last_payment_status": last_payment_status,
        "failed_payments": failed_payments,
        "pending_payments": pending_payments,
    }

    return render(request, "billing/billing_hub.html", context)

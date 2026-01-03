# billing/views_reconciliation.py
"""
Reconciliation and debugging views (staff-only).
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Q, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from .models import (
    BusinessSubscription,
    Invoice,
    Payment,
    PaymentEvent,
    PaymentTransaction,
)

logger = logging.getLogger(__name__)


@staff_member_required
def reconciliation_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Internal reconciliation dashboard for staff.
    
    Shows:
    - Recent webhook events
    - Unmatched payments (payment without invoice)
    - Unpaid invoices (invoice without payment)
    - Payment statistics
    - Subscription health check
    """
    # Get filter parameters
    days = int(request.GET.get("days", "7"))
    business_id = request.GET.get("business")
    
    # Date range
    start_date = timezone.now() - timedelta(days=days)
    
    # Base querysets
    events_qs = PaymentEvent.objects.filter(received_at__gte=start_date)
    transactions_qs = PaymentTransaction.objects.filter(created_at__gte=start_date)
    invoices_qs = Invoice.objects.filter(created_at__gte=start_date)
    payments_qs = Payment.objects.filter(created_at__gte=start_date)
    
    # Filter by business if specified
    if business_id:
        transactions_qs = transactions_qs.filter(business_id=business_id)
        invoices_qs = invoices_qs.filter(business_id=business_id)
        payments_qs = payments_qs.filter(business_id=business_id)
    
    # Recent webhook events
    recent_events = events_qs.order_by("-received_at")[:20]
    
    # Event statistics
    event_stats = events_qs.aggregate(
        total=Count("id"),
        processed=Count("id", filter=Q(status=PaymentEvent.Status.PROCESSED)),
        failed=Count("id", filter=Q(status=PaymentEvent.Status.FAILED)),
        ignored=Count("id", filter=Q(status=PaymentEvent.Status.IGNORED)),
        invalid_signature=Count("id", filter=Q(signature_valid=False)),
    )
    
    # Transaction statistics
    transaction_stats = transactions_qs.aggregate(
        total=Count("id"),
        success=Count("id", filter=Q(status=PaymentTransaction.Status.SUCCESS)),
        pending=Count("id", filter=Q(status=PaymentTransaction.Status.PENDING)),
        failed=Count("id", filter=Q(status=PaymentTransaction.Status.FAILED)),
        total_amount=Sum("amount", filter=Q(status=PaymentTransaction.Status.SUCCESS)),
    )
    
    # Invoice statistics
    invoice_stats = invoices_qs.aggregate(
        total=Count("id"),
        paid=Count("id", filter=Q(status=Invoice.Status.PAID)),
        issued=Count("id", filter=Q(status=Invoice.Status.ISSUED)),
        draft=Count("id", filter=Q(status=Invoice.Status.DRAFT)),
        total_amount=Sum("total", filter=Q(status=Invoice.Status.PAID)),
    )
    
    # Find unmatched transactions (SUCCESS but no linked invoice PAID)
    unmatched_transactions = (
        transactions_qs.filter(status=PaymentTransaction.Status.SUCCESS)
        .exclude(
            business__invoices__status=Invoice.Status.PAID,
            business__invoices__provider_reference=Q("tx_ref"),
        )
        .select_related("business")
        .order_by("-created_at")[:10]
    )
    
    # Find unpaid invoices (ISSUED but no payment)
    unpaid_invoices = (
        invoices_qs.filter(Q(status=Invoice.Status.ISSUED) | Q(status=Invoice.Status.SENT))
        .select_related("business", "subscription")
        .order_by("-created_at")[:10]
    )
    
    # Subscription health check
    subscription_stats = BusinessSubscription.objects.aggregate(
        total=Count("id"),
        trial=Count("id", filter=Q(status=BusinessSubscription.Status.TRIAL)),
        active=Count("id", filter=Q(status=BusinessSubscription.Status.ACTIVE)),
        past_due=Count("id", filter=Q(status=BusinessSubscription.Status.PAST_DUE)),
        suspended=Count("id", filter=Q(status=BusinessSubscription.Status.SUSPENDED)),
        cancelled=Count("id", filter=Q(status=BusinessSubscription.Status.CANCELLED)),
    )
    
    # Subscriptions expiring soon
    expiring_soon = BusinessSubscription.objects.filter(
        status__in=[BusinessSubscription.Status.TRIAL, BusinessSubscription.Status.ACTIVE],
        current_period_end__lte=timezone.now() + timedelta(days=3),
        current_period_end__gte=timezone.now(),
    ).select_related("business", "plan")[:10]
    
    context = {
        "days": days,
        "business_id": business_id,
        "start_date": start_date,
        "recent_events": recent_events,
        "event_stats": event_stats,
        "transaction_stats": transaction_stats,
        "invoice_stats": invoice_stats,
        "unmatched_transactions": unmatched_transactions,
        "unpaid_invoices": unpaid_invoices,
        "subscription_stats": subscription_stats,
        "expiring_soon": expiring_soon,
    }
    
    return render(request, "billing/reconciliation_dashboard.html", context)


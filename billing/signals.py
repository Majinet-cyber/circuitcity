# billing/signals.py
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import connection, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone

from .models import Invoice, Payment, SubscriptionPlan, BusinessSubscription
from .notify import fanout


# ---------- Utilities ------------------------------------------------------
def _table_exists(table_name: str) -> bool:
    """
    Return True if a DB table exists. Safe to call during startup/migrations.
    """
    try:
        return table_name in connection.introspection.table_names()
    except Exception:
        return False


# ---------- Plan seeding on import (idempotent, safe during migrate) ------
def _seed_plans() -> None:
    """
    Safe, idempotent seeding of a few common plans.
    Only runs if the subscription plan table exists (no migration breakage).
    """
    if not _table_exists(SubscriptionPlan._meta.db_table):
        return

    currency = getattr(settings, "REPORTS_DEFAULT_CURRENCY", "MWK")
    plans = [
        dict(
            code="starter",
            name="Starter",
            amount=Decimal("20000.00"),
            interval=SubscriptionPlan.Interval.MONTH,
            max_stores=1,
            max_agents=3,
        ),
        dict(
            code="growth",
            name="Growth",
            amount=Decimal("60000.00"),
            interval=SubscriptionPlan.Interval.MONTH,
            max_stores=3,
            max_agents=15,
        ),
        dict(
            code="pro",
            name="Pro",
            amount=Decimal("120000.00"),
            interval=SubscriptionPlan.Interval.MONTH,
            max_stores=10,
            max_agents=50,
        ),
    ]

    with transaction.atomic():
        for p in plans:
            SubscriptionPlan.objects.update_or_create(
                code=p["code"],
                defaults={
                    "name": p["name"],
                    "amount": p["amount"],
                    "interval": p["interval"],
                    "max_stores": p["max_stores"],
                    "max_agents": p["max_agents"],
                    "is_active": True,
                    "currency": currency,
                },
            )


# Try to seed at import time; safe to no-op if DB not ready.
try:
    _seed_plans()
except Exception:
    # Ignore during early migrate phases or if DB is unavailable
    pass


# ---------- Invoice created -> notify --------------------------------------
@receiver(post_save, sender=Invoice)
def _on_invoice_created(sender, instance: Invoice, created: bool, **kwargs):
    if not created:
        return

    biz = instance.business
    amount = instance.total

    biz_part = f" ({getattr(biz, 'name', '')})" if biz else ""

    title = f"Invoice {instance.number} issued"
    body = (
        "Hello!\n\n"
        f"An invoice has been generated for your business{biz_part}.\n"
        f"Amount: {instance.currency} {amount}\n"
        f"Issue date: {instance.issue_date}   "
        f"Due date: {instance.due_date or (instance.issue_date + timedelta(days=7))}\n\n"
        "You can pay via Airtel Money, Standard Bank, or Card from the subscription page.\n"
        "Thank you!"
    )

    try:
        url = reverse("billing:subscribe")
    except Exception:
        url = "/billing/subscribe/"

    # ntype must be "invoice" to appear in your UI badge map
    fanout(business=biz, title=title, body=body, ntype="invoice", url=url)


# ---------- Payment status -> notify (success/failure) ---------------------
@receiver(post_save, sender=Payment)
def _on_payment_saved(sender, instance: Payment, created: bool, **kwargs):
    """
    Notify whenever payment status is SUCCEEDED or FAILED.
    It's okay if this fires multiple times; fanout should handle dedupe if desired.
    """
    biz = instance.business
    currency = instance.currency
    amt = instance.amount

    if instance.status == Payment.Status.SUCCEEDED:
        title = "Payment received"
        body = (
            f"Great news! We received your payment of {currency} {amt} "
            f"via {instance.get_provider_display()}.\n"
            f"Reference: {instance.reference or instance.external_id or 'â€”'}\n\n"
            "Your subscription remains active. Thanks!"
        )
        # Use "payment" to match your UI badge/types
        fanout(business=biz, title=title, body=body, ntype="payment")
        return

    if instance.status == Payment.Status.FAILED:
        title = "Payment failed"
        body = (
            f"Unfortunately your payment of {currency} {amt} "
            f"via {instance.get_provider_display()} did not succeed.\n"
            f"Reference: {instance.reference or instance.external_id or 'â€”'}\n\n"
            "Please try again from the subscription page."
        )
        try:
            url = reverse("billing:subscribe")
        except Exception:
            url = "/billing/subscribe/"
        # Use "payment" to match your UI badge/types
        fanout(business=biz, title=title, body=body, ntype="payment", url=url)


# ---------- Trial seeding: ensure default trial window on new subs ---------
@receiver(post_save, sender=BusinessSubscription)
def _ensure_trial_window(sender, instance: BusinessSubscription, created: bool, **kwargs):
    """
    If a subscription is created without trial_end, set a trial window
    based on settings.BILLING_TRIAL_DAYS (default 30).
    """
    if not created or instance.trial_end:
        return

    days = getattr(settings, "BILLING_TRIAL_DAYS", 30)
    now = timezone.now()
    instance.trial_end = now + timedelta(days=days)
    instance.current_period_start = now
    instance.current_period_end = instance.trial_end
    instance.next_billing_date = instance.trial_end
    instance.save(
        update_fields=[
            "trial_end",
            "current_period_start",
            "current_period_end",
            "next_billing_date",
        ]
    )



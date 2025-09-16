# billing/signals.py
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone

from .models import Invoice, InvoiceItem, Payment, SubscriptionPlan, BusinessSubscription
from .notify import fanout


# ---------- Plan seeding on first migrate (idempotent) -------------------
def _seed_plans():
    """
    Safe, idempotent seeding of a few common plans.
    """
    plans = [
        dict(code="starter", name="Starter", amount=Decimal("20000.00"), interval=SubscriptionPlan.Interval.MONTH, max_stores=1, max_agents=3),
        dict(code="growth",  name="Growth",  amount=Decimal("60000.00"), interval=SubscriptionPlan.Interval.MONTH, max_stores=3, max_agents=15),
        dict(code="pro",     name="Pro",     amount=Decimal("120000.00"),interval=SubscriptionPlan.Interval.MONTH, max_stores=10, max_agents=50),
    ]
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
                "currency": getattr(settings, "REPORTS_DEFAULT_CURRENCY", "MWK"),
            },
        )


try:
    # Seed plans as soon as app imports (safe if DB is ready)
    _seed_plans()
except Exception:
    # Ignore errors during early migrate phases
    pass


# ---------- Invoice created -> notify ------------------------------------
@receiver(post_save, sender=Invoice)
def _on_invoice_created(sender, instance: Invoice, created: bool, **kwargs):
    if not created:
        return
    biz = instance.business
    amount = instance.total
    title = f"Invoice {instance.number} issued"
    body = (
        f"Hello!\n\n"
        f"An invoice has been generated for your business{f' ({getattr(biz, 'name', '')})' if biz else ''}.\n"
        f"Amount: {instance.currency} {amount}\n"
        f"Issue date: {instance.issue_date}   Due date: {instance.due_date or (instance.issue_date + timedelta(days=7))}\n\n"
        f"You can pay via Airtel Money, Standard Bank, or Card from the subscription page.\n"
        f"Thank you!"
    )
    url = ""
    try:
        url = reverse("billing:subscribe")
    except Exception:
        url = "/billing/subscribe/"
    fanout(business=biz, title=title, body=body, ntype="invoice", url=url)


# ---------- Payment status -> notify (success/failure) -------------------
@receiver(post_save, sender=Payment)
def _on_payment_saved(sender, instance: Payment, created: bool, **kwargs):
    # Notify whenever status becomes SUCCEEDED or FAILED (may be called multiple times — acceptable)
    biz = instance.business
    currency = instance.currency
    amt = instance.amount

    if instance.status == Payment.Status.SUCCEEDED:
        title = "Payment received"
        body = (
            f"Great news! We received your payment of {currency} {amt} "
            f"via {instance.get_provider_display()}.\n"
            f"Reference: {instance.reference or instance.external_id or '—'}\n\n"
            f"Your subscription remains active. Thanks!"
        )
        fanout(business=biz, title=title, body=body, ntype="payment_ok")
        return

    if instance.status == Payment.Status.FAILED:
        title = "Payment failed"
        body = (
            f"Unfortunately your payment of {currency} {amt} "
            f"via {instance.get_provider_display()} did not succeed.\n"
            f"Reference: {instance.reference or instance.external_id or '—'}\n\n"
            f"Please try again from the subscription page."
        )
        url = ""
        try:
            url = reverse("billing:subscribe")
        except Exception:
            url = "/billing/subscribe/"
        fanout(business=biz, title=title, body=body, ntype="payment_failed", url=url)


# ---------- Trial seeding safety: ensure 30d default on new subs ----------
@receiver(post_save, sender=BusinessSubscription)
def _ensure_trial_window(sender, instance: BusinessSubscription, created: bool, **kwargs):
    """
    If a subscription is created without trial_end, set a 30d trial window
    (or settings.BILLING_TRIAL_DAYS if configured).
    """
    if not created:
        return
    if not instance.trial_end:
        days = getattr(settings, "BILLING_TRIAL_DAYS", 30)
        now = timezone.now()
        instance.trial_end = now + timedelta(days=days)
        instance.current_period_start = now
        instance.current_period_end = instance.trial_end
        instance.next_billing_date = instance.trial_end
        instance.save(update_fields=["trial_end", "current_period_start", "current_period_end", "next_billing_date"])

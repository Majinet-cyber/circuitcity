# billing/middleware.py
from __future__ import annotations

from datetime import timedelta
from typing import Iterable

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from tenants.models import Business  # type: ignore
from .models import BusinessSubscription, SubscriptionPlan


# Paths we never block (prefix match). Keep short, stable prefixes only.
SAFE_PREFIXES: tuple[str, ...] = (
    "/admin/",                 # let superusers fix billing if needed
    "/healthz",                # health probes
    "/robots.txt",
    "/favicon.ico",
    "/static/",                # assets
    settings.STATIC_URL or "/static/",
    settings.MEDIA_URL or "/media/",
    # Auth + account management
    "/accounts/login/",
    "/accounts/logout/",
    "/accounts/password/",
    # Tenant switching / onboarding
    "/tenants/choose/",
    "/tenants/create/",
    # Billing flows
    "/billing/subscribe/",
    "/billing/checkout/",
    "/billing/success/",
    "/billing/webhook/",
    "/billing/invoices/",      # allow users to view/pay invoices
    # Notifications list is OK even if read-only
    "/notifications/",
)


def _is_safe(path: str, safe_prefixes: Iterable[str]) -> bool:
    p = path or "/"
    return any(p.startswith(pref) for pref in safe_prefixes if pref)


class SubscriptionGateMiddleware:
    """
    Enforce basic subscription access rules for multi-tenant SaaS.

    Behavior:
      â€¢ Bootstrap: If a Business has no subscription yet, seed a TRIAL for BILLING_TRIAL_DAYS (default 30).
      â€¢ Enforcement (only when FEATURES['BILLING_ENFORCE'] is true):
          - Allow while TRIAL is active
          - Allow while ACTIVE
          - Allow during GRACE window (GRACE_DAYS, default 30)
          - Otherwise redirect to billing:subscribe
      â€¢ Superusers and staff are never blocked.
      â€¢ SAFE_PREFIXES are always allowed to avoid loops (login, billing, static, etc.).
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._enforce = bool(getattr(settings, "FEATURES", {}).get("BILLING_ENFORCE", False))
        # Settings knobs with sensible defaults
        self._trial_days = int(getattr(settings, "BILLING_TRIAL_DAYS", 30))
        self._grace_days = int(getattr(settings, "BILLING_GRACE_DAYS", 30))

    # --------------- helpers ----------------
    def _bootstrap_subscription(self, biz: Business) -> BusinessSubscription:
        """
        Create a trial subscription for a new Business.
        Picks the cheapest active plan (or creates a basic one).
        """
        plan = (
            SubscriptionPlan.objects.filter(is_active=True)
            .order_by("amount", "sort_order")
            .first()
        )
        if not plan:
            plan = SubscriptionPlan.objects.create(
                code="starter",
                name="Starter",
                amount=0,
                currency=getattr(settings, "REPORTS_DEFAULT_CURRENCY", "MWK"),
                interval=SubscriptionPlan.Interval.MONTH,
                max_stores=1,
                max_agents=3,
                features={"notes": "Autocreated plan"},
                is_active=True,
                sort_order=1,
            )
        # Seed trial with configured days
        return BusinessSubscription.start_trial(business=biz, plan=plan, days=self._trial_days)

    # --------------- main ----------------
    def __call__(self, request: HttpRequest) -> HttpResponse:
        path = request.path or "/"

        # Always let safe URLs through
        if _is_safe(path, SAFE_PREFIXES):
            return self.get_response(request)

        # If staff/superuser, never block (they need access to administer)
        user = getattr(request, "user", None)
        if getattr(user, "is_authenticated", False) and (user.is_superuser or user.is_staff):
            return self.get_response(request)

        # Resolve tenant (set earlier by TenantResolutionMiddleware)
        biz: Business | None = getattr(request, "business", None)
        if not biz:
            # No active tenant -> skip enforcement; other middlewares/guards handle this
            return self.get_response(request)

        # Ensure a subscription exists
        sub: BusinessSubscription | None = getattr(biz, "subscription", None)
        if not sub:
            sub = self._bootstrap_subscription(biz)

        # If we're not enforcing yet, just pass through (but with seeded trial above)
        if not self._enforce:
            return self.get_response(request)

        # Live enforcement
        # Allow while subscription considers itself active (ACTIVE/TRIAL/GRACE)
        if sub.is_active_now():
            return self.get_response(request)

        # If not active but still within our computed grace window, allow
        # (BusinessSubscription.in_grace already computes based on next_billing_date/trial_end)
        if sub.in_grace():
            return self.get_response(request)

        # Past grace â†’ expired
        if not sub.is_expired():
            # Belt-and-suspenders: mark expired when we detect it
            anchor = sub.next_billing_date or sub.trial_end or sub.current_period_end or timezone.now()
            if timezone.now() >= (anchor + timedelta(days=self._grace_days)):
                sub.status = BusinessSubscription.Status.EXPIRED
                sub.save(update_fields=["status", "updated_at"])

        # Redirect to subscribe/checkout
        try:
            subscribe_url = reverse("billing:subscribe")
        except Exception:
            subscribe_url = "/billing/subscribe/"
        reason = "expired" if sub.is_expired() else "inactive"
        return redirect(f"{subscribe_url}?reason={reason}")



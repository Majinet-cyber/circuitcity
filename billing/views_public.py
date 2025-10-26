from __future__ import annotations
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone

try:
    # single source of truth for prices & limits
    from circuitcity.hq.views import PLAN_CATALOG  # type: ignore
except Exception:  # pragma: no cover
    PLAN_CATALOG = {
        "starter": {"code": "starter", "name": "Starter", "amount": Decimal("20000.00"), "max_agents": 0, "max_stores": 1},
        "pro":     {"code": "pro",     "name": "Pro",     "amount": Decimal("35000.00"), "max_agents": 5, "max_stores": None},
        "promax":  {"code": "promax",  "name": "Pro Max", "amount": Decimal("50000.00"), "max_agents": None, "max_stores": None},
    }

from tenants.utils import get_active_business  # your helper
from billing.models import Subscription, Invoice


@login_required
def subscribe(request: HttpRequest) -> HttpResponse:
    """
    Show plan cards for the active business and let a manager choose a plan.
    Posts redirect to a provider-specific checkout (stubbed for now).
    """
    biz = get_active_business(request)
    if not biz:
        # send them to choose/activate a business
        return redirect(reverse("tenants:activate_mine"))

    # current sub (if any)
    current = (
        Subscription.objects.filter(business=biz).order_by("-id").first()
    )

    if request.method == "POST":
        code = (request.POST.get("plan_code") or "").lower().strip()
        provider = (request.POST.get("provider") or "manual").lower().strip()
        if code not in PLAN_CATALOG:
            return redirect(request.path)  # ignore bad input

        # Create/update a subscription record pointing at the chosen plan amount.
        plan = PLAN_CATALOG[code]
        sub = current or Subscription(business=biz)
        # keep a shadow code if your model has it; otherwise store amount
        if hasattr(sub, "plan_code"): sub.plan_code = plan["code"]
        if hasattr(sub, "amount"):    sub.amount = plan["amount"]
        sub.status = "ACTIVE" if provider == "manual" else "PENDING"
        # align periods in a simple way (start now, next bill +30d)
        now = timezone.now()
        if hasattr(sub, "current_period_start"): sub.current_period_start = now
        if hasattr(sub, "current_period_end"):   sub.current_period_end = now + timezone.timedelta(days=30)
        sub.save()

        # generate an OPEN invoice (you can swap to PENDING when provider != manual)
        Invoice.objects.create(
            business=biz,
            total=plan["amount"],
            status="OPEN" if provider == "manual" else "PENDING",
            currency=getattr(current, "currency", "MWK"),
            number=f"INV-{timezone.now().strftime('%Y%m%d-%H%M%S')}",
            issue_date=timezone.localdate(),
            notes=f"{plan['name']} monthly subscription"
        )

        # Redirect to payment. For now:
        return redirect(reverse("billing_checkout", kwargs={"provider": provider}) + f"?plan={code}")

    return render(request, "billing/subscribe.html", {
        "biz": biz,
        "catalog": PLAN_CATALOG,
        "current": current,
    })


@login_required
def checkout(request: HttpRequest, provider: str) -> HttpResponse:
    """
    Placeholder "checkout" page â€“ pluggable providers.
    Later youâ€™ll integrate Airtel/TNM SDKs or hosted pay pages here.
    """
    provider = (provider or "manual").lower()
    plan_code = (request.GET.get("plan") or "").lower()
    plan = PLAN_CATALOG.get(plan_code)
    if not plan:
        return redirect(reverse("billing_subscribe"))

    # For now, 'manual' just confirms instantly and returns.
    if provider == "manual":
        return redirect(reverse("billing_return", kwargs={"provider": provider}) + f"?plan={plan_code}&ok=1")

    # Stubs for future providers
    return render(request, "billing/checkout_stub.html", {
        "provider": provider,
        "plan": plan,
        "return_url": reverse("billing_return", kwargs={"provider": provider}),
    })


@login_required
def return_view(request: HttpRequest, provider: str) -> HttpResponse:
    """
    Generic return/callback. Mark invoice paid in a real integration.
    """
    ok = request.GET.get("ok") == "1"
    plan_code = (request.GET.get("plan") or "").lower()
    if ok:
        # In a real flow, verify the transaction, mark the latest OPEN/PENDING invoice as PAID, etc.
        pass
    # land them back in HQ or their business dashboard
    try:
        return redirect(reverse("hq:dashboard"))
    except Exception:
        return redirect("/")



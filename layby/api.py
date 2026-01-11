from __future__ import annotations
from django.http import JsonResponse, HttpRequest, HttpResponseBadRequest
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from django.conf import settings
from .models import LaybyOrder, LaybyPayment, notify

import json

# ✅ SECURITY: Import tenant isolation helpers
try:
    from tenants.services.active_business import get_active_business
    from tenants.models import Membership
except ImportError:
    def get_active_business(request):
        return None
    Membership = None


def _scope_layby_queryset(request: HttpRequest, qs):
    """
    Scope LaybyOrder queryset to the current business via created_by membership.
    
    SECURITY: LaybyOrder doesn't have a direct business FK, so we scope via
    the created_by user's membership to prevent IDOR vulnerabilities.
    """
    business = get_active_business(request)
    if not business or Membership is None:
        return qs.none()
    
    # Get user IDs that belong to this business
    business_user_ids = Membership.objects.filter(
        business=business,
        status="ACTIVE"
    ).values_list("user_id", flat=True)
    
    return qs.filter(created_by_id__in=list(business_user_ids))


@login_required
@require_GET
def api_orders(request: HttpRequest):
    scope = request.GET.get("scope", "agent")  # agent|admin|customer
    if scope == "admin" and request.user.is_staff:
        # ✅ SECURITY: Scope admin view to business to prevent IDOR
        qs = _scope_layby_queryset(request, LaybyOrder.objects.all()).order_by("-created_at")
    elif scope == "customer":
        phone = request.GET.get("phone")
        # ✅ SECURITY: Customer scope also filtered by business
        qs = _scope_layby_queryset(request, LaybyOrder.objects.filter(customer_phone=phone)).order_by("-created_at")
    else:
        qs = LaybyOrder.objects.filter(agent=request.user).order_by("-created_at")

    data = [
        {
            "id": o.id,
            "customer": {"name": o.customer_name, "phone": o.customer_phone},
            "product": {"name": o.product_name, "sku": o.product_sku, "serial": o.product_serial, "qty": o.qty},
            "price": str(o.unit_price),
            "total": str(o.total_price),
            "paid": str(o.amount_paid),
            "balance": str(o.balance),
            "status": o.status,
            "target_date": o.target_date.isoformat() if o.target_date else None,
            "created_at": o.created_at.isoformat(),
        }
        for o in qs[:200]
    ]
    return JsonResponse({"ok": True, "orders": data})


@login_required
@require_GET
def api_payments(request: HttpRequest, pk: int):
    """
    Get payments for a layby order.
    
    SECURITY: Uses pre-fetch scoping to prevent IDOR info leaks.
    """
    business = get_active_business(request)
    
    # ✅ SECURITY: Build scoped queryset BEFORE fetching to prevent IDOR info leaks
    qs = LaybyOrder.objects.filter(pk=pk)
    
    # Apply business scope via membership
    if business and Membership is not None:
        business_user_ids = Membership.objects.filter(
            business=business,
            status="ACTIVE"
        ).values_list("user_id", flat=True)
        qs = qs.filter(created_by_id__in=list(business_user_ids))
    
    # Apply agent scope: non-staff can only see their own orders
    if not request.user.is_staff:
        qs = qs.filter(agent_id=request.user.id)
    
    # Now fetch - will return empty if doesn't exist OR doesn't match scope
    o = qs.first()
    if not o:
        return JsonResponse({"ok": False, "error": "Not found"}, status=404)

    data = [
        {
            "id": p.id,
            "amount": str(p.amount),
            "method": p.method,
            "provider_ref": p.provider_ref,
            "note": p.note,
            "created_at": p.created_at.isoformat(),
        }
        for p in o.payments.all().order_by("-created_at")
    ]
    return JsonResponse({"ok": True, "payments": data})


# --- Webhook security helpers ---
def _check_webhook_secret(request: HttpRequest) -> bool:
    require = getattr(settings, "LAYBY_WEBHOOK_REQUIRE_SECRET", True)
    if not require:
        return True
    expected = getattr(settings, "LAYBY_WEBHOOK_SECRET", "")
    got = request.META.get("HTTP_X_LAYBY_SIGNATURE", "")
    return bool(expected) and (got == expected)


@require_POST
def api_payment_webhook(request: HttpRequest):
    if not _check_webhook_secret(request):
        return HttpResponseBadRequest("Invalid or missing X-Layby-Signature")

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    order_id = payload.get("order_id")
    amount = payload.get("amount")
    method = payload.get("method", "OTHER")
    provider_ref = payload.get("provider_ref", "")
    note = payload.get("note", "")

    try:
        o = LaybyOrder.objects.get(pk=order_id)
    except LaybyOrder.DoesNotExist:
        return HttpResponseBadRequest("Unknown order")

    p = LaybyPayment.objects.create(order=o, amount=amount, method=method, provider_ref=provider_ref, note=note)
    if o.balance <= 0 and o.status not in ["DELIVERED"]:
        o.status = "ACTIVE"  # ready for pickup; mark delivered via UI when collected
        o.save(update_fields=["status", "updated_at"])

    notify("layby.payment", f"Webhook payment {p.amount} for {o.customer_name}", audience="AGENT", user=o.agent)
    return JsonResponse({"ok": True})

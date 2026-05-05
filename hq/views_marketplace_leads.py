from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import OperationalError, ProgrammingError
from django.db.models import Count, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, NoReverseMatch
from django.utils import timezone
from django.views.decorators.http import require_POST

from billing import paychangu_service
from hq.permissions import hq_admin_required
from inventory.models_marketplace import (
    MarketplaceCommissionStatus,
    MarketplaceLead,
    MarketplaceLeadSource,
    MarketplaceLeadStatus,
    MarketplaceListing,
    MarketplaceOrder,
    MarketplaceOrderStatus,
    ListingVerificationStatus,
)
from inventory.services.marketplace_leads import mark_lead_outcome
from tenants.models import Business

log = logging.getLogger(__name__)


def _leads_url() -> str:
    """Safe fallback URL for marketplace leads list."""
    try:
        return reverse("hq:marketplace_leads")
    except NoReverseMatch:
        return "/hq/marketplace/leads/"


# Plan definitions (matches pricing_config.py)
_PLANS = {
    "lite": {"name": "Lite Plan", "amount": Decimal("9500.00")},
    "pro": {"name": "Pro Plan", "amount": Decimal("20000.00")},
    "enterprise": {"name": "Enterprise Plan", "amount": Decimal("50000.00")},
}


def _empty_order_metrics():
    return {
        "total": 0,
        "paid": 0,
        "pending": 0,
        "failed": 0,
        "gmv": 0,
        "platform_commission": 0,
        "seller_earnings": 0,
    }


def _checkout_order_analytics():
    """Keep HQ leads usable while marketplace checkout migrations are pending."""
    try:
        orders_qs = MarketplaceOrder.objects.select_related("listing", "seller_business")
        paid_qs = orders_qs.filter(payment_status=MarketplaceOrderStatus.PAID)
        return {
            "order_metrics": {
                "total": orders_qs.count(),
                "paid": paid_qs.count(),
                "pending": orders_qs.filter(payment_status=MarketplaceOrderStatus.PENDING).count(),
                "failed": orders_qs.filter(payment_status=MarketplaceOrderStatus.FAILED).count(),
                "gmv": paid_qs.aggregate(total=Sum("total_amount"))["total"] or 0,
                "platform_commission": paid_qs.aggregate(total=Sum("platform_commission_amount"))["total"] or 0,
                "seller_earnings": paid_qs.aggregate(total=Sum("seller_net_earnings"))["total"] or 0,
            },
            "orders_by_vertical": (
                paid_qs
                .values("listing__vertical")
                .annotate(count=Count("id"), total=Sum("total_amount"))
                .order_by("-total")[:8]
            ),
            "recent_paid_orders": paid_qs.order_by("-paid_at")[:8],
        }
    except (OperationalError, ProgrammingError):
        return {
            "order_metrics": _empty_order_metrics(),
            "orders_by_vertical": [],
            "recent_paid_orders": [],
        }


def _parse_date(value: str, end=False):
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None
    dt = timezone.make_aware(parsed)
    if end:
        dt = dt + timedelta(days=1)
    return dt


def _filtered_leads(request):
    qs = MarketplaceLead.objects.select_related("listing", "seller_business").order_by("-created_at")
    date_from = _parse_date(request.GET.get("date_from", ""))
    date_to = _parse_date(request.GET.get("date_to", ""), end=True)
    business_id = request.GET.get("seller_business", "").strip()
    vertical = request.GET.get("vertical", "").strip()
    status = request.GET.get("status", "").strip()
    commission_status = request.GET.get("commission_status", "").strip()
    source_type = request.GET.get("source_type", "").strip()

    if date_from:
        qs = qs.filter(created_at__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__lt=date_to)
    if business_id:
        qs = qs.filter(seller_business_id=business_id)
    if vertical:
        qs = qs.filter(listing__vertical=vertical)
    if status:
        qs = qs.filter(status=status)
    if commission_status:
        qs = qs.filter(commission_status=commission_status)
    if source_type:
        qs = qs.filter(source_type=source_type)
    return qs


def _filter_values(request):
    return {
        "date_from": request.GET.get("date_from", "").strip(),
        "date_to": request.GET.get("date_to", "").strip(),
        "seller_business": request.GET.get("seller_business", "").strip(),
        "vertical": request.GET.get("vertical", "").strip(),
        "status": request.GET.get("status", "").strip(),
        "commission_status": request.GET.get("commission_status", "").strip(),
        "source_type": request.GET.get("source_type", "").strip(),
    }


def _metrics(qs):
    total = qs.count()
    won = qs.filter(status=MarketplaceLeadStatus.WON).count()
    lost = qs.filter(status=MarketplaceLeadStatus.LOST).count()
    contacted = qs.filter(status=MarketplaceLeadStatus.CONTACTED).count()
    new = qs.filter(status=MarketplaceLeadStatus.NEW).count()
    gmv = qs.filter(status=MarketplaceLeadStatus.WON).aggregate(total=Sum("deal_amount"))["total"] or 0
    commission_due = qs.filter(commission_status=MarketplaceCommissionStatus.DUE).aggregate(total=Sum("commission_amount"))["total"] or 0
    commission_paid = qs.filter(commission_status=MarketplaceCommissionStatus.PAID).aggregate(total=Sum("commission_amount"))["total"] or 0
    commission_pending = qs.filter(commission_status=MarketplaceCommissionStatus.PENDING).aggregate(total=Sum("commission_amount"))["total"] or 0
    commission_waived = qs.filter(commission_status=MarketplaceCommissionStatus.WAIVED).aggregate(total=Sum("commission_amount"))["total"] or 0
    return {
        "total": total,
        "new": new,
        "contacted": contacted,
        "won": won,
        "lost": lost,
        "conversion_rate": round((won / total) * 100, 1) if total else 0,
        "gmv": gmv,
        "commission_due": commission_due,
        "commission_paid": commission_paid,
        "commission_pending": commission_pending,
        "commission_waived": commission_waived,
    }


@hq_admin_required
def marketplace_leads_dashboard(request):
    qs = _filtered_leads(request)
    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    all_leads = MarketplaceLead.objects.select_related("listing", "seller_business")
    sellers = Business.objects.filter(marketplace_leads__isnull=False).distinct().order_by("name")
    verticals = (
        all_leads.exclude(listing__vertical="")
        .values_list("listing__vertical", flat=True)
        .distinct()
        .order_by("listing__vertical")
    )
    by_vertical = qs.values("listing__vertical").annotate(count=Count("id")).order_by("-count")[:12]
    by_business = qs.values("seller_business__name").annotate(count=Count("id")).order_by("-count")[:12]
    by_source = qs.values("source_type").annotate(count=Count("id")).order_by("-count")
    top_sellers_gmv = (
        qs.filter(status=MarketplaceLeadStatus.WON)
        .values("seller_business__name")
        .annotate(won=Count("id"), gmv=Sum("deal_amount"), commission=Sum("commission_amount"))
        .order_by("-gmv")[:8]
    )
    recent_won = qs.filter(status=MarketplaceLeadStatus.WON).order_by("-converted_at", "-updated_at")[:8]
    order_analytics = _checkout_order_analytics()

    return render(
        request,
        "hq/marketplace_leads.html",
        {
            "page_obj": page_obj,
            "metrics": _metrics(qs),
            "sellers": sellers,
            "verticals": verticals,
            "by_vertical": by_vertical,
            "by_business": by_business,
            "by_source": by_source,
            "top_sellers_gmv": top_sellers_gmv,
            "recent_won": recent_won,
            "order_metrics": order_analytics["order_metrics"],
            "orders_by_vertical": order_analytics["orders_by_vertical"],
            "recent_paid_orders": order_analytics["recent_paid_orders"],
            "lead_statuses": MarketplaceLeadStatus.choices,
            "source_types": MarketplaceLeadSource.choices,
            "commission_statuses": MarketplaceCommissionStatus.choices,
            "filters": _filter_values(request),
            "contracts_enabled": False,
        },
    )


@hq_admin_required
def marketplace_lead_detail(request, lead_id: int):
    lead = get_object_or_404(
        MarketplaceLead.objects.select_related("listing", "seller_business"),
        pk=lead_id,
    )
    return render(
        request,
        "hq/marketplace_lead_detail.html",
        {
            "lead": lead,
            "lead_statuses": MarketplaceLeadStatus.choices,
            "commission_statuses": MarketplaceCommissionStatus.choices,
            "contracts_enabled": False,
        },
    )


@hq_admin_required
@require_POST
def marketplace_lead_update(request, lead_id: int):
    lead = get_object_or_404(MarketplaceLead, pk=lead_id)
    try:
        mark_lead_outcome(
            lead,
            status=request.POST.get("status", lead.status),
            deal_amount=request.POST.get("deal_amount"),
            commission_percentage=request.POST.get("commission_percentage"),
            commission_amount=request.POST.get("commission_amount"),
            commission_status=request.POST.get("commission_status"),
            notes=request.POST.get("notes", lead.notes),
            hq_notes=request.POST.get("hq_notes", lead.hq_notes),
        )
        if lead.status == MarketplaceLeadStatus.WON and lead.commission_status == MarketplaceCommissionStatus.PAID:
            lead.commission_paid_at = lead.commission_paid_at or timezone.now()
            lead.commission_paid_by = lead.commission_paid_by or request.user
            lead.save(update_fields=["commission_paid_at", "commission_paid_by", "updated_at"])
        elif lead.status == MarketplaceLeadStatus.WON and lead.commission_status == MarketplaceCommissionStatus.WAIVED:
            lead.commission_waived_at = lead.commission_waived_at or timezone.now()
            lead.commission_waived_by = lead.commission_waived_by or request.user
            lead.save(update_fields=["commission_waived_at", "commission_waived_by", "updated_at"])
        messages.success(request, "Marketplace lead updated.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("hq:marketplace_lead_detail", lead_id=lead.pk)


@hq_admin_required
@require_POST
def marketplace_lead_mark_paid(request, lead_id: int):
    lead = get_object_or_404(MarketplaceLead, pk=lead_id)
    if lead.status != MarketplaceLeadStatus.WON:
        messages.error(request, "Commission can only be marked paid after a lead is won.")
        return redirect(request.META.get("HTTP_REFERER") or _leads_url())
    lead.commission_status = MarketplaceCommissionStatus.PAID
    lead.commission_paid_at = timezone.now()
    lead.commission_paid_by = request.user
    lead.save(update_fields=["commission_status", "commission_paid_at", "commission_paid_by", "updated_at"])
    messages.success(request, "Commission marked paid.")
    return redirect(request.META.get("HTTP_REFERER") or _leads_url())


@hq_admin_required
@require_POST
def marketplace_lead_mark_waived(request, lead_id: int):
    lead = get_object_or_404(MarketplaceLead, pk=lead_id)
    if lead.status != MarketplaceLeadStatus.WON:
        messages.error(request, "Commission can only be waived after a lead is won.")
        return redirect(request.META.get("HTTP_REFERER") or _leads_url())
    lead.commission_status = MarketplaceCommissionStatus.WAIVED
    lead.commission_waived_at = timezone.now()
    lead.commission_waived_by = request.user
    lead.save(update_fields=["commission_status", "commission_waived_at", "commission_waived_by", "updated_at"])
    messages.success(request, "Commission waived.")
    return redirect(request.META.get("HTTP_REFERER") or _leads_url())


@hq_admin_required
@require_POST
def marketplace_lead_initiate_payment(request, lead_id: int):
    """
    Generate a PayChangu checkout URL for a WON lead's subscription.
    Accepts JSON body: {plan: "lite"|"pro"|"enterprise", amount: number}
    Returns JSON: {checkout_url, tx_ref, plan_name, amount} or {error}
    """
    lead = get_object_or_404(
        MarketplaceLead.objects.select_related("seller_business"),
        pk=lead_id,
    )

    if lead.status != MarketplaceLeadStatus.WON:
        return JsonResponse({"error": "Payment can only be initiated for WON leads."}, status=400)

    # Parse request body
    try:
        body = json.loads(request.body)
        plan_key = str(body.get("plan", "")).lower()
    except (json.JSONDecodeError, AttributeError):
        plan_key = request.POST.get("plan", "").lower()

    plan = _PLANS.get(plan_key)
    if not plan:
        return JsonResponse({"error": f"Unknown plan '{plan_key}'. Choose: lite, pro, enterprise."}, status=400)

    business = lead.seller_business
    if not business:
        return JsonResponse({"error": "This lead has no associated business."}, status=400)

    if not paychangu_service.is_paychangu_configured():
        return JsonResponse({"error": "PayChangu is not configured. Please contact the system administrator."}, status=503)

    tx_ref = f"HQ-SUB-{lead_id}-{uuid.uuid4().hex[:8].upper()}"
    return_url = request.build_absolute_uri(f"/hq/marketplace/leads/{lead_id}/")

    try:
        # Create a PaymentTransaction record for audit trail
        try:
            from billing.models import PaymentTransaction
            PaymentTransaction.objects.create(
                business=business,
                location=None,
                amount=plan["amount"],
                currency="MWK",
                status=PaymentTransaction.Status.PENDING,
                tx_ref=tx_ref,
                raw_init_payload={
                    "source": "hq_lead_subscription",
                    "lead_id": lead_id,
                    "plan": plan_key,
                    "initiated_by": request.user.username,
                },
            )
        except Exception as e:
            log.warning("Could not create PaymentTransaction for HQ lead %d: %s", lead_id, e)

        result = paychangu_service.create_checkout(
            business=business,
            location=None,
            amount=plan["amount"],
            currency="MWK",
            tx_ref=tx_ref,
            return_url=return_url,
            meta={
                "source": "hq_lead_subscription",
                "lead_id": str(lead_id),
                "plan": plan_key,
                "business_id": str(business.id),
            },
            description=f"Emajinet {plan['name']} subscription for {business.name}",
        )

        if result.get("status") == "success":
            log.info("HQ lead %d: payment initiated. tx_ref=%s plan=%s", lead_id, tx_ref, plan_key)
            return JsonResponse({
                "checkout_url": result.get("checkout_url", ""),
                "tx_ref": tx_ref,
                "plan_name": plan["name"],
                "amount": str(plan["amount"]),
            })
        else:
            log.warning("PayChangu checkout failed for lead %d: %s", lead_id, result.get("message"))
            return JsonResponse({"error": result.get("message", "PayChangu checkout failed.")}, status=502)

    except Exception as exc:
        log.exception("Unexpected error initiating payment for lead %d", lead_id)
        return JsonResponse({"error": f"Server error: {exc}"}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
# HQ Marketplace Listing Moderation
# ─────────────────────────────────────────────────────────────────────────────

@hq_admin_required
def marketplace_listings_moderation(request):
    """
    HQ admin: review and moderate marketplace listings.
    Filter by verification_status. Shows verification badges per listing.
    """
    status_filter = request.GET.get("status", "pending")
    search_q = request.GET.get("q", "").strip()
    vertical_filter = request.GET.get("vertical", "").strip()

    try:
        qs = (
            MarketplaceListing.objects
            .select_related("business", "verified_by", "created_by")
            .prefetch_related("images")
        )
        valid_statuses = [s.value for s in ListingVerificationStatus]
        if status_filter in valid_statuses:
            qs = qs.filter(verification_status=status_filter)
        if search_q:
            from django.db.models import Q
            qs = qs.filter(
                Q(title__icontains=search_q)
                | Q(business__name__icontains=search_q)
                | Q(description__icontains=search_q)
            )
        if vertical_filter:
            qs = qs.filter(vertical=vertical_filter)

        qs = qs.order_by("-created_at")
        paginator = Paginator(qs, 20)
        page_obj = paginator.get_page(request.GET.get("page", 1))

        counts = {
            "pending": MarketplaceListing.objects.filter(verification_status=ListingVerificationStatus.PENDING).count(),
            "verified": MarketplaceListing.objects.filter(verification_status=ListingVerificationStatus.VERIFIED).count(),
            "rejected": MarketplaceListing.objects.filter(verification_status=ListingVerificationStatus.REJECTED).count(),
            "taken_down": MarketplaceListing.objects.filter(verification_status=ListingVerificationStatus.TAKEN_DOWN).count(),
        }
    except Exception as exc:
        log.exception("marketplace_listings_moderation query failed: %s", exc)
        page_obj = Paginator([], 20).get_page(1)
        counts = {"pending": 0, "verified": 0, "rejected": 0, "taken_down": 0}

    return render(request, "hq/marketplace_listings_moderation.html", {
        "page_obj": page_obj,
        "counts": counts,
        "status_filter": status_filter,
        "search_q": search_q,
        "vertical_filter": vertical_filter,
        "verification_statuses": ListingVerificationStatus,
    })


@hq_admin_required
@require_POST
def marketplace_listing_moderate(request, listing_id: int):
    """
    HQ admin: verify, reject, or take down a single marketplace listing.
    POST body fields:
      action: verify | reject | takedown | restore
      reason: (required for reject and takedown)
    """
    listing = get_object_or_404(
        MarketplaceListing.objects.select_related("business"),
        pk=listing_id,
    )
    action = request.POST.get("action", "").strip()
    reason = request.POST.get("reason", "").strip()

    now = timezone.now()

    if action == "verify":
        listing.verification_status = ListingVerificationStatus.VERIFIED
        listing.is_visible_publicly = True
        listing.verified_by = request.user
        listing.verified_at = now
        listing.rejection_reason = ""
        listing.takedown_reason = ""
        listing.save(update_fields=[
            "verification_status", "is_visible_publicly",
            "verified_by", "verified_at", "rejection_reason", "takedown_reason",
        ])
        messages.success(request, f"Listing '{listing.title}' verified successfully.")

    elif action == "reject":
        if not reason:
            messages.error(request, "Please provide a rejection reason.")
            return redirect(request.META.get("HTTP_REFERER", _moderation_url()))
        listing.verification_status = ListingVerificationStatus.REJECTED
        listing.is_visible_publicly = False
        listing.verified_by = request.user
        listing.verified_at = now
        listing.rejection_reason = reason
        listing.save(update_fields=[
            "verification_status", "is_visible_publicly",
            "verified_by", "verified_at", "rejection_reason",
        ])
        messages.warning(request, f"Listing '{listing.title}' rejected.")

    elif action == "takedown":
        if not reason:
            messages.error(request, "Please provide a takedown reason.")
            return redirect(request.META.get("HTTP_REFERER", _moderation_url()))
        listing.verification_status = ListingVerificationStatus.TAKEN_DOWN
        listing.is_visible_publicly = False
        listing.verified_by = request.user
        listing.verified_at = now
        listing.takedown_reason = reason
        listing.save(update_fields=[
            "verification_status", "is_visible_publicly",
            "verified_by", "verified_at", "takedown_reason",
        ])
        messages.warning(request, f"Listing '{listing.title}' taken down.")

    elif action == "restore":
        listing.verification_status = ListingVerificationStatus.PENDING
        listing.is_visible_publicly = True
        listing.verified_by = request.user
        listing.verified_at = now
        listing.rejection_reason = ""
        listing.takedown_reason = ""
        listing.save(update_fields=[
            "verification_status", "is_visible_publicly",
            "verified_by", "verified_at", "rejection_reason", "takedown_reason",
        ])
        messages.success(request, f"Listing '{listing.title}' restored to pending review.")

    else:
        messages.error(request, f"Unknown action '{action}'.")

    return redirect(request.META.get("HTTP_REFERER", _moderation_url()))


def _moderation_url() -> str:
    try:
        return reverse("hq:marketplace_listings_moderation")
    except NoReverseMatch:
        return "/hq/marketplace/listings/"

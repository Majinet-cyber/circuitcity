from __future__ import annotations

from datetime import datetime, timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from hq.permissions import hq_admin_required
from inventory.models_marketplace import (
    MarketplaceCommissionStatus,
    MarketplaceLead,
    MarketplaceLeadSource,
    MarketplaceLeadStatus,
)
from inventory.services.marketplace_leads import mark_lead_outcome
from tenants.models import Business


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
        return redirect(request.META.get("HTTP_REFERER", "hq:marketplace_leads"))
    lead.commission_status = MarketplaceCommissionStatus.PAID
    lead.commission_paid_at = timezone.now()
    lead.commission_paid_by = request.user
    lead.save(update_fields=["commission_status", "commission_paid_at", "commission_paid_by", "updated_at"])
    messages.success(request, "Commission marked paid.")
    return redirect(request.META.get("HTTP_REFERER", "hq:marketplace_leads"))


@hq_admin_required
@require_POST
def marketplace_lead_mark_waived(request, lead_id: int):
    lead = get_object_or_404(MarketplaceLead, pk=lead_id)
    if lead.status != MarketplaceLeadStatus.WON:
        messages.error(request, "Commission can only be waived after a lead is won.")
        return redirect(request.META.get("HTTP_REFERER", "hq:marketplace_leads"))
    lead.commission_status = MarketplaceCommissionStatus.WAIVED
    lead.commission_waived_at = timezone.now()
    lead.commission_waived_by = request.user
    lead.save(update_fields=["commission_status", "commission_waived_at", "commission_waived_by", "updated_at"])
    messages.success(request, "Commission waived.")
    return redirect(request.META.get("HTTP_REFERER", "hq:marketplace_leads"))

"""Merchant Administrator portal views."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import merchant_admin_required
from accounts.utils import is_hq
from core.models import AuditLog
from website.models import MerchantLead

from .models import MerchantChecklist, MerchantKYC


# ── helpers ──────────────────────────────────────────────────────────────────

def _require_hq_approval():
    return getattr(settings, "REQUIRE_HQ_MERCHANT_APPROVAL", True)


def _is_staff_user(user):
    """True if user is HQ or Merchant Admin."""
    return is_hq(user) or getattr(getattr(user, "profile", None), "role", "") == "merchant_admin"


# ── dashboard ────────────────────────────────────────────────────────────────

@merchant_admin_required
def ma_dashboard(request):
    from django.db.models import Count
    from django.utils.timezone import now

    month_start = now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    ctx = {
        "new_leads":        MerchantLead.objects.filter(status=MerchantLead.STATUS_NEW).count(),
        "kyc_pending":      MerchantLead.objects.filter(status=MerchantLead.STATUS_KYC_PENDING).count(),
        "docs_pending":     MerchantLead.objects.filter(status=MerchantLead.STATUS_DOCUMENTS_PENDING).count(),
        "site_visit":       MerchantLead.objects.filter(status=MerchantLead.STATUS_SITE_VISIT).count(),
        "awaiting_hq":      MerchantLead.objects.filter(status=MerchantLead.STATUS_AWAITING_HQ).count(),
        "approved_month":   MerchantLead.objects.filter(status=MerchantLead.STATUS_APPROVED, updated_at__gte=month_start).count(),
        "rejected_month":   MerchantLead.objects.filter(status=MerchantLead.STATUS_REJECTED, updated_at__gte=month_start).count(),
        "recent_leads":     MerchantLead.objects.select_related("assigned_to").order_by("-created_at")[:8],
        "require_hq":       _require_hq_approval(),
    }
    return render(request, "merchant_admin/dashboard.html", ctx)


# ── lead list ────────────────────────────────────────────────────────────────

@merchant_admin_required
def ma_leads(request):
    status_filter = request.GET.get("status", "")
    leads = MerchantLead.objects.select_related("assigned_to").order_by("-created_at")
    if status_filter:
        leads = leads.filter(status=status_filter)

    ctx = {
        "leads": leads,
        "status_filter": status_filter,
        "status_choices": MerchantLead.STATUS_CHOICES,
    }
    return render(request, "merchant_admin/leads.html", ctx)


# ── lead detail ──────────────────────────────────────────────────────────────

@merchant_admin_required
def ma_lead_detail(request, lead_id):
    lead = get_object_or_404(MerchantLead, id=lead_id)
    kyc, _ = MerchantKYC.objects.get_or_create(lead=lead)
    checklist, _ = MerchantChecklist.objects.get_or_create(lead=lead)

    ctx = {
        "lead": lead,
        "kyc": kyc,
        "checklist": checklist,
        "status_choices": MerchantLead.STATUS_CHOICES,
        "require_hq": _require_hq_approval(),
        "all_staff": get_user_model().objects.filter(
            profile__role__in=["merchant_admin", "hq"]
        ).select_related("profile").order_by("username"),
    }
    return render(request, "merchant_admin/lead_detail.html", ctx)


# ── KYC form save ─────────────────────────────────────────────────────────────

@merchant_admin_required
def ma_lead_kyc(request, lead_id):
    lead = get_object_or_404(MerchantLead, id=lead_id)
    if request.method != "POST":
        return redirect("ma_lead_detail", lead_id=lead_id)

    kyc, _ = MerchantKYC.objects.get_or_create(lead=lead, defaults={"collected_by": request.user})

    kyc.national_id_number = request.POST.get("national_id_number", "").strip()
    kyc.business_reg_number = request.POST.get("business_reg_number", "").strip()
    kyc.region = request.POST.get("region", "").strip()
    kyc.physical_address = request.POST.get("physical_address", "").strip()
    kyc.trading_area = request.POST.get("trading_area", "").strip()
    kyc.bank_name = request.POST.get("bank_name", "").strip()
    kyc.bank_account_name = request.POST.get("bank_account_name", "").strip()
    kyc.bank_account_number = request.POST.get("bank_account_number", "").strip()
    kyc.airtel_money_number = request.POST.get("airtel_money_number", "").strip()
    kyc.tnm_mpamba_number = request.POST.get("tnm_mpamba_number", "").strip()
    kyc.notes = request.POST.get("notes", "").strip()

    lat = request.POST.get("gps_latitude", "").strip()
    lon = request.POST.get("gps_longitude", "").strip()
    try:
        kyc.gps_latitude = float(lat) if lat else None
        kyc.gps_longitude = float(lon) if lon else None
    except ValueError:
        pass

    for field in ["business_certificate", "tax_certificate", "shop_photo_1", "shop_photo_2"]:
        if field in request.FILES:
            setattr(kyc, field, request.FILES[field])

    kyc.save()

    if lead.status == MerchantLead.STATUS_NEW:
        lead.status = MerchantLead.STATUS_KYC_PENDING
        lead.save(update_fields=["status", "updated_at"])

    AuditLog.objects.create(
        user=request.user,
        action=AuditLog.ACTION_KYC_CHANGE,
        object_type="MerchantLead",
        object_id=str(lead.id),
        detail={"action": "kyc_saved", "lead": lead.business_name},
    )
    messages.success(request, "KYC details saved.")
    return redirect("ma_lead_detail", lead_id=lead_id)


# ── checklist save ────────────────────────────────────────────────────────────

@merchant_admin_required
def ma_checklist(request, lead_id):
    lead = get_object_or_404(MerchantLead, id=lead_id)
    if request.method != "POST":
        return redirect("ma_lead_detail", lead_id=lead_id)

    checklist, _ = MerchantChecklist.objects.get_or_create(lead=lead, defaults={"assigned_to": request.user})

    def _bool(key):
        val = request.POST.get(key, "")
        if val == "yes":
            return True
        if val == "no":
            return False
        return None

    checklist.spoke_to_owner = _bool("spoke_to_owner")
    checklist.shop_physically_traceable = _bool("shop_physically_traceable")
    checklist.documents_verified = _bool("documents_verified")
    checklist.bank_name_matches = _bool("bank_name_matches")
    checklist.understands_settlement = _bool("understands_settlement")
    checklist.understands_no_wht = _bool("understands_no_wht")
    checklist.understands_fraud_consequences = _bool("understands_fraud_consequences")
    checklist.approved_for_pilot = _bool("approved_for_pilot")
    checklist.notes = request.POST.get("notes", "").strip()
    checklist.site_visit_completed = request.POST.get("site_visit_completed") == "yes"

    if request.POST.get("site_visit_date"):
        from datetime import date
        try:
            checklist.site_visit_date = date.fromisoformat(request.POST["site_visit_date"])
        except ValueError:
            pass

    checklist.save()
    messages.success(request, "Checklist saved.")
    return redirect("ma_lead_detail", lead_id=lead_id)


# ── status change ─────────────────────────────────────────────────────────────

@merchant_admin_required
def ma_lead_status(request, lead_id):
    lead = get_object_or_404(MerchantLead, id=lead_id)
    if request.method != "POST":
        return redirect("ma_lead_detail", lead_id=lead_id)

    new_status = request.POST.get("status", "").strip()
    valid_statuses = {s for s, _ in MerchantLead.STATUS_CHOICES}
    if new_status not in valid_statuses:
        messages.error(request, "Invalid status.")
        return redirect("ma_lead_detail", lead_id=lead_id)

    old_status = lead.status
    lead.status = new_status

    assigned_to_id = request.POST.get("assigned_to")
    if assigned_to_id:
        try:
            lead.assigned_to_id = int(assigned_to_id)
        except (ValueError, TypeError):
            pass

    lead.save(update_fields=["status", "assigned_to", "updated_at"])

    AuditLog.objects.create(
        user=request.user,
        action=AuditLog.ACTION_KYC_CHANGE,
        object_type="MerchantLead",
        object_id=str(lead.id),
        detail={"action": "status_change", "from": old_status, "to": new_status},
    )
    messages.success(request, f"Status updated to {lead.get_status_display()}.")
    return redirect("ma_lead_detail", lead_id=lead_id)


# ── recommendation ────────────────────────────────────────────────────────────

@merchant_admin_required
def ma_recommend(request, lead_id):
    lead = get_object_or_404(MerchantLead, id=lead_id)
    if request.method != "POST":
        return redirect("ma_lead_detail", lead_id=lead_id)

    action = request.POST.get("action", "")
    checklist, _ = MerchantChecklist.objects.get_or_create(lead=lead)

    if action == "approve":
        checklist.recommendation = MerchantChecklist.RECOMMEND_APPROVE
        checklist.save(update_fields=["recommendation", "updated_at"])
        if _require_hq_approval():
            lead.status = MerchantLead.STATUS_AWAITING_HQ
            messages.info(request, "Approval recommended. Awaiting HQ final approval.")
        else:
            lead.status = MerchantLead.STATUS_APPROVED
            messages.success(request, "Merchant approved.")
        lead.save(update_fields=["status", "updated_at"])

    elif action == "reject":
        checklist.recommendation = MerchantChecklist.RECOMMEND_REJECT
        checklist.save(update_fields=["recommendation", "updated_at"])
        lead.status = MerchantLead.STATUS_REJECTED
        lead.save(update_fields=["status", "updated_at"])
        messages.warning(request, "Merchant lead rejected.")

    elif action == "escalate":
        checklist.recommendation = MerchantChecklist.RECOMMEND_ESCALATE
        checklist.save(update_fields=["recommendation", "updated_at"])
        lead.status = MerchantLead.STATUS_AWAITING_HQ
        lead.save(update_fields=["status", "updated_at"])
        messages.info(request, "Escalated to HQ.")

    AuditLog.objects.create(
        user=request.user,
        action=AuditLog.ACTION_KYC_CHANGE,
        object_type="MerchantLead",
        object_id=str(lead.id),
        detail={"action": "recommendation", "choice": action},
    )
    return redirect("ma_lead_detail", lead_id=lead_id)

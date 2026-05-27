# hq/views_esignature.py
"""
Merchant-facing e-signature portal.

Merchants can open their contract, read it, type their name to confirm, and submit
a legally-binding click-wrap signature. HQ can then see the signed record.
"""
from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from hq.models import MerchantContract

logger = logging.getLogger(__name__)


def _get_client_ip(request: HttpRequest) -> str:
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


@login_required
def merchant_contract_portal(request: HttpRequest, token: uuid.UUID) -> HttpResponse:
    """
    Merchant-facing contract viewer & e-signature portal.

    Access is granted to:
    - Any authenticated user who is a manager/owner of the contract's business
    - HQ admins (for preview/testing)
    """
    contract = get_object_or_404(MerchantContract, sign_token=token)
    business = contract.business

    # Check access: user must belong to this business or be HQ admin
    user = request.user
    is_hq = getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)
    is_member = False
    try:
        from tenants.models import Membership
        is_member = Membership.objects.filter(
            business=business,
            user=user,
            status="ACTIVE",
        ).exists()
    except Exception:
        pass

    if not is_hq and not is_member:
        return HttpResponseForbidden(
            "You do not have permission to access this contract. "
            "Please log in with the correct account."
        )

    # Mark as viewed if not already signed/voided
    if contract.status in (MerchantContract.CONTRACT_STATUS_DRAFT, MerchantContract.CONTRACT_STATUS_SENT):
        contract.status = MerchantContract.CONTRACT_STATUS_VIEWED
        contract.save(update_fields=["status", "updated_at"])

    ctx = {
        "contract": contract,
        "business": business,
        "already_signed": contract.is_signed,
        "is_void": contract.status == MerchantContract.CONTRACT_STATUS_VOID,
        "token": token,
        "page_title": f"Contract — {business.name}",
    }
    return render(request, "hq/esignature_portal.html", ctx)


@login_required
@require_POST
def merchant_contract_sign(request: HttpRequest, token: uuid.UUID) -> HttpResponse:
    """
    Process the merchant e-signature submission.
    """
    contract = get_object_or_404(MerchantContract, sign_token=token)
    business = contract.business

    user = request.user
    is_hq = getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)
    is_member = False
    try:
        from tenants.models import Membership
        is_member = Membership.objects.filter(
            business=business,
            user=user,
            status="ACTIVE",
        ).exists()
    except Exception:
        pass

    if not is_hq and not is_member:
        return HttpResponseForbidden("Access denied.")

    # Already signed — idempotent
    if contract.is_signed:
        messages.info(request, "This contract has already been signed.")
        return redirect("hq:contract_sign_portal", token=token)

    # Voided contracts cannot be signed
    if contract.status == MerchantContract.CONTRACT_STATUS_VOID:
        messages.error(request, "This contract has been voided and cannot be signed.")
        return redirect("hq:contract_sign_portal", token=token)

    # Validate inputs
    signature_name = request.POST.get("signature_name", "").strip()
    agreement_checked = request.POST.get("agreement", "") == "on"

    if not signature_name:
        messages.error(request, "Please type your full name as your signature.")
        return redirect("hq:contract_sign_portal", token=token)

    if not agreement_checked:
        messages.error(request, "You must agree to the contract terms before signing.")
        return redirect("hq:contract_sign_portal", token=token)

    # Record signature
    contract.status = MerchantContract.CONTRACT_STATUS_SIGNED
    contract.signature_name = signature_name
    contract.signed_at = timezone.now()
    contract.signed_ip = _get_client_ip(request)
    contract.signed_user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
    contract.save(update_fields=[
        "status", "signature_name", "signed_at", "signed_ip",
        "signed_user_agent", "updated_at",
    ])

    # Audit log
    try:
        from audit.models import AuditLog
        AuditLog.objects.create(
            business=business,
            user=user,
            action="SIGN_CONTRACT",
            resource_type="MerchantContract",
            resource_id=contract.id,
            details={
                "business_id": business.id,
                "business_name": business.name,
                "signature_name": signature_name,
                "signed_ip": contract.signed_ip,
                "contract_id": contract.id,
            },
        )
    except Exception:
        pass

    messages.success(
        request,
        f"Contract signed successfully by {signature_name}. "
        "A record of your signature has been saved."
    )
    return redirect("hq:contract_sign_portal", token=token)


@login_required
def merchant_contract_sign_success(request: HttpRequest, token: uuid.UUID) -> HttpResponse:
    """Simple success/confirmation redirect."""
    contract = get_object_or_404(MerchantContract, sign_token=token)
    return render(request, "hq/esignature_portal.html", {
        "contract": contract,
        "business": contract.business,
        "already_signed": True,
        "token": token,
        "page_title": f"Contract Signed — {contract.business.name}",
    })


# ============================================================================
# HQ: mark contract as "sent to merchant"
# ============================================================================

@login_required
@require_POST
def contract_send_to_merchant(request: HttpRequest, contract_id: int) -> HttpResponse:
    """
    HQ action: mark contract as 'sent' and display the sign link.
    Does not actually send an email (can be extended), just updates status
    and redirects back to contracts detail with the link shown.
    """
    from hq.permissions import hq_admin_required

    if not (getattr(request.user, "is_staff", False) or getattr(request.user, "is_superuser", False)):
        return HttpResponseForbidden("HQ access required.")

    contract = get_object_or_404(MerchantContract, id=contract_id)

    if contract.status in (MerchantContract.CONTRACT_STATUS_VOID, MerchantContract.CONTRACT_STATUS_SIGNED):
        messages.warning(
            request,
            f"Contract is already {contract.get_status_display()} — no change made.",
        )
    else:
        contract.status = MerchantContract.CONTRACT_STATUS_SENT
        contract.save(update_fields=["status", "updated_at"])
        messages.success(
            request,
            "Contract marked as 'Sent to Merchant'. "
            f"Share this link with the merchant: "
            f"{request.build_absolute_uri(contract.get_sign_url())}",
        )

    return redirect("hq:contracts_detail", business_id=contract.business_id)

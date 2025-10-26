# tenants/services/invites.py
from __future__ import annotations

from typing import Iterable, List, Optional, Tuple, Dict
from datetime import timedelta
import uuid

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from tenants.models import AgentInvite, Business, Membership

User = get_user_model()


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------

@transaction.atomic
def create_agent_invite(
    *,
    tenant: Business,
    created_by: User | None,
    invited_name: str = "",
    email: str = "",
    phone: str = "",
    ttl_days: int = 7,
    message: str = "",
    mark_sent: bool = True,
) -> AgentInvite:
    """
    Create a new invite scoped to a tenant.

    - No schema assumptions beyond AgentInvite fields.
    - Returns the saved invite instance.
    - If mark_sent=True, status â†’ SENT (kept â€œpendingâ€ by our UI rule).
    """
    invited_name = (invited_name or "").strip()
    email = (email or "").strip().lower()
    phone = (phone or "").strip()

    expires_at = timezone.now() + timedelta(days=max(1, int(ttl_days)))

    inv = AgentInvite.all_objects.create(   # all_objects: bypass thread-local if needed
        business=tenant,
        created_by=created_by,
        invited_name=invited_name,
        email=email,
        phone=phone,
        token=uuid.uuid4().hex,             # will be retained; model ensures one exists
        status="PENDING",
        message=(message or "").strip(),
        expires_at=expires_at,
    )

    if mark_sent:
        inv.mark_sent(save=True)

    return inv


# ---------------------------------------------------------------------------
# Queries (read-only helpers)
# ---------------------------------------------------------------------------

def invites_for_business(tenant: Business) -> List[AgentInvite]:
    """All invites for a tenant (newest first)."""
    return list(AgentInvite.all_objects.filter(business=tenant).order_by("-created_at", "-id"))


def pending_invites_for_business(tenant: Business) -> List[AgentInvite]:
    """
    Invites considered 'pending' for UI (matches AgentInvite.is_pending()).
    """
    items = invites_for_business(tenant)
    return [i for i in items if i.is_pending()]


def annotate_shares(invites: Iterable[AgentInvite], request) -> List[AgentInvite]:
    """
    Attach share fields computed by the model (keeps templates dumb).
    """
    out: List[AgentInvite] = []
    for inv in invites:
        try:
            payload = inv.share_payload(request)
            inv.share_copy_text = payload["copy_text"]
            inv.share_url = payload["url"]
            inv.share_wa = payload["wa_url"]
            inv.share_mailto = payload["mailto_url"]
        except Exception:
            inv.share_copy_text = ""
            inv.share_url = "#"
            inv.share_wa = "#"
            inv.share_mailto = "#"
        out.append(inv)
    return out


# ---------------------------------------------------------------------------
# Lifecycle operations
# ---------------------------------------------------------------------------

@transaction.atomic
def resend_invite(
    *,
    invite: AgentInvite,
    extend_days: int = 7,
    message: str | None = None,
) -> AgentInvite:
    """
    Resend an invite (no duplication). Optionally extends the expiry window.
    - Keeps the same token so previously shared links still work.
    - Status â†’ SENT.
    """
    if extend_days and extend_days > 0:
        invite.expires_at = timezone.now() + timedelta(days=extend_days)

    invite.mark_sent(message=message, save=True)
    return invite


@transaction.atomic
def revoke_invite(*, invite: AgentInvite) -> AgentInvite:
    """
    Soft-revoke by marking EXPIRED (we don't introduce a new status).
    """
    invite.status = "EXPIRED"
    invite.expires_at = invite.expires_at or timezone.now()
    invite.save(update_fields=["status", "expires_at"])
    return invite


def bulk_mark_expired(*, tenant: Business) -> int:
    """
    Scan and mark expired invites. Returns number updated.
    """
    count = 0
    for inv in invites_for_business(tenant):
        changed = inv.mark_expired_if_needed(save=True)
        if changed:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Redemption
# ---------------------------------------------------------------------------

@transaction.atomic
def accept_invite_by_token(
    *,
    token: str,
    user: User,
    role: str = "AGENT",
) -> Tuple[AgentInvite, Membership]:
    """
    Validate and redeem an invite token, attaching the user to the business.

    Rules:
      - Invite must exist and not be expired.
      - If already JOINED, we still ensure membership is ACTIVE and return it.
      - Idempotent on repeat calls for the same user/invite.

    Returns (invite, membership).
    Raises ValueError on invalid/expired tokens.
    """
    try:
        inv = AgentInvite.all_objects.get(token=token)
    except AgentInvite.DoesNotExist:
        raise ValueError("Invalid invite token")

    # Expiry check (also respects explicit EXPIRED status)
    if inv.is_expired():
        inv.status = "EXPIRED"
        inv.save(update_fields=["status"])
        raise ValueError("Invite has expired")

    # Ensure membership exists / is active
    mem, _created = Membership.objects.get_or_create(
        user=user,
        business=inv.business,
        defaults={"role": role, "status": "ACTIVE"},
    )
    # If it existed but was not active/role differs, gently fix it (do no harm)
    updates = []
    if mem.status != "ACTIVE":
        mem.status = "ACTIVE"
        updates.append("status")
    if role and mem.role != role:
        mem.role = role
        updates.append("role")
    if updates:
        mem.save(update_fields=updates)

    # Mark invite joined (idempotent)
    if inv.status != "JOINED" or inv.joined_user_id != getattr(user, "id", None):
        inv.mark_joined(user=user, save=True)

    return inv, mem


# ---------------------------------------------------------------------------
# Small convenience for views
# ---------------------------------------------------------------------------

def share_bundle(invite: AgentInvite, request) -> Dict[str, str]:
    """
    One-liner for views/templates that want all share strings.
    Delegates to the model to avoid duplication.
    """
    return invite.share_payload(request)



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
    generate_temp_password: bool = True,
    location=None,
) -> Tuple[AgentInvite, Optional[str]]:
    """
    Create a new invite scoped to a tenant.

    - No schema assumptions beyond AgentInvite fields.
    - Returns (invite instance, temp_password_plaintext or None).
    - If mark_sent=True, status -> SENT.
    - If generate_temp_password=True, creates a temp password (returned plaintext).
    """
    invited_name = (invited_name or "").strip()
    email = (email or "").strip().lower()
    phone = (phone or "").strip()

    expires_at = timezone.now() + timedelta(days=max(1, int(ttl_days)))

    inv = AgentInvite.all_objects.create(
        business=tenant,
        created_by=created_by,
        invited_name=invited_name,
        email=email,
        phone=phone,
        location=location,
        token=uuid.uuid4().hex,
        status="PENDING",
        message=(message or "").strip(),
        expires_at=expires_at,
    )

    temp_password = None
    if generate_temp_password:
        temp_password = inv.create_and_set_temp_password()
        inv.save(update_fields=["temp_password_hash", "temp_password_used"])

    if mark_sent:
        inv.mark_sent(save=True)

    return inv, temp_password


def create_agent_invite_simple(
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
    Simplified version for backwards compatibility.
    Returns just the invite (no temp password).
    """
    inv, _ = create_agent_invite(
        tenant=tenant,
        created_by=created_by,
        invited_name=invited_name,
        email=email,
        phone=phone,
        ttl_days=ttl_days,
        message=message,
        mark_sent=mark_sent,
        generate_temp_password=False,
    )
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
    regenerate_password: bool = False,
) -> Tuple[AgentInvite, Optional[str]]:
    """
    Resend an invite (no duplication). Optionally extends the expiry window.
    - Keeps the same token so previously shared links still work.
    - Status -> SENT.
    - Returns (invite, new_temp_password or None).
    """
    if extend_days and extend_days > 0:
        invite.expires_at = timezone.now() + timedelta(days=extend_days)

    new_password = None
    if regenerate_password:
        new_password = invite.create_and_set_temp_password()
        invite.save(update_fields=["temp_password_hash", "temp_password_used", "expires_at"])
    
    invite.mark_sent(message=message, save=True)
    return invite, new_password


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
    force_password_change: bool = True,
) -> Tuple[AgentInvite, Membership]:
    """
    Validate and redeem an invite token, attaching the user to the business.

    Rules:
      - Invite must exist and not be expired.
      - If already JOINED, we still ensure membership is ACTIVE and return it.
      - Idempotent on repeat calls for the same user/invite.
      - If force_password_change=True, sets user's profile.force_password_change=True.

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
        location=inv.location,
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
    if inv.location and not mem.location:
        mem.location = inv.location
        updates.append("location")
    if updates:
        mem.save(update_fields=updates)

    # Mark invite joined (idempotent)
    if inv.status != "JOINED" or inv.joined_user_id != getattr(user, "id", None):
        inv.mark_joined(user=user, save=True)
    
    # Mark temp password as used
    if inv.temp_password_hash and not inv.temp_password_used:
        inv.temp_password_used = True
        inv.save(update_fields=["temp_password_used"])
    
    # Force password change if requested
    if force_password_change:
        try:
            profile = user.profile
            if not profile.force_password_change:
                profile.force_password_change = True
                profile.save(update_fields=["force_password_change"])
        except Exception:
            pass

    return inv, mem


@transaction.atomic
def accept_invite_with_temp_password(
    *,
    token: str,
    temp_password: str,
    username: str,
    email: str = "",
) -> Tuple[AgentInvite, User, Membership]:
    """
    Accept an invite using the temp password to create a new user account.
    
    - Verifies the temp password matches.
    - Creates a new user with the temp password (they must change it).
    - Attaches the user as an agent to the business.
    
    Returns (invite, user, membership).
    Raises ValueError on invalid token/password.
    """
    try:
        inv = AgentInvite.all_objects.get(token=token)
    except AgentInvite.DoesNotExist:
        raise ValueError("Invalid invite token")
    
    if inv.is_expired():
        inv.status = "EXPIRED"
        inv.save(update_fields=["status"])
        raise ValueError("Invite has expired")
    
    if inv.status == "JOINED":
        raise ValueError("Invite has already been used")
    
    # Verify temp password
    if not inv.check_temp_password(temp_password):
        raise ValueError("Invalid temporary password")
    
    # Check if user already exists
    if User.objects.filter(username__iexact=username).exists():
        raise ValueError("Username is already taken")
    
    # Create user with temp password (they'll be forced to change it)
    user = User.objects.create_user(
        username=username,
        password=temp_password,
        email=email or inv.email or "",
        first_name=inv.invited_name.split()[0] if inv.invited_name else "",
    )
    
    # Accept the invite
    inv, mem = accept_invite_by_token(
        token=token,
        user=user,
        role="AGENT",
        force_password_change=True,
    )
    
    return inv, user, mem


# ---------------------------------------------------------------------------
# Small convenience for views
# ---------------------------------------------------------------------------

def share_bundle(invite: AgentInvite, request) -> Dict[str, str]:
    """
    One-liner for views/templates that want all share strings.
    Delegates to the model to avoid duplication.
    """
    return invite.share_payload(request)


def get_invite_email_content(invite: AgentInvite, request, temp_password: Optional[str] = None) -> Dict[str, str]:
    """
    Generate email content for an invite including the temp password.
    """
    payload = invite.share_payload(request)
    
    biz_name = invite.business.name if invite.business else "the team"
    agent_name = invite.invited_name or "there"
    
    text = f"""Hi {agent_name},

You have been invited to join {biz_name} as an Agent.

Click here to get started: {payload['url']}
"""
    
    if temp_password:
        text += f"""
Your temporary password is: {temp_password}

You will be asked to change this password when you first log in.
"""
    
    text += f"""
This invite expires on {invite.expires_at:%b %d, %Y at %H:%M}.

Best regards,
{biz_name}
"""
    
    return {
        "subject": f"Join {biz_name}",
        "text": text,
        "url": payload["url"],
        "temp_password": temp_password,
    }

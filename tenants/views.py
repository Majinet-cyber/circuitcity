# tenants/views.py
from __future__ import annotations

from typing import Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch

from .forms import CreateBusinessForm, JoinAsAgentForm
from .models import Business, Membership
from .utils import (
    require_business,
    require_role,
    set_active_business,
    get_active_business,
)

# -------------------------------------------------------------------
# Small helpers
# -------------------------------------------------------------------

def _home_redirect(request: HttpRequest) -> HttpResponse:
    """Redirect to your main dashboard if defined; otherwise to root."""
    from django.urls import reverse
    try:
        return redirect("dashboard:home")
    except NoReverseMatch:
        return redirect("/")


def _redirect_next_or_home(request: HttpRequest, fallback="tenants:choose_business") -> HttpResponse:
    nxt = request.GET.get("next") or request.POST.get("next")
    if nxt:
        return redirect(nxt)
    try:
        from django.urls import reverse
        return redirect(fallback)
    except Exception:
        return _home_redirect(request)


def _ensure_seed_on_switch(biz: Business) -> None:
    """
    Safety: seed defaults whenever someone switches into a business that might
    not yet have Store/Warehouse (e.g., brand-new tenant).
    """
    try:
        biz.seed_defaults()
    except Exception:
        # Never block a tenant switch on seeding issues
        pass


# -------------------------------------------------------------------
# Activation / selection flow
# -------------------------------------------------------------------

@login_required
def activate_mine(request: HttpRequest) -> HttpResponse:
    """
    Try to auto-activate a sensible business for the current user.

    Priority:
      1) If already active → go to next/home.
      2) If exactly ONE ACTIVE membership → activate that business.
      3) If multiple ACTIVE memberships → show chooser.
      4) If none:
         - If they created a business that's PENDING → inform and send to chooser.
         - Else show Join form.
    """
    # 1) honor existing selection
    if get_active_business(request):
        return _redirect_next_or_home(request, fallback="tenants:choose_business")

    user = request.user

    # 2) look for a single ACTIVE membership (and business ACTIVE)
    active_memberships = list(
        Membership.objects.filter(user=user, status="ACTIVE")
        .select_related("business")
        .order_by("-created_at")
    )
    active_memberships = [m for m in active_memberships if getattr(m.business, "status", "ACTIVE") == "ACTIVE"]

    if len(active_memberships) == 1:
        b = active_memberships[0].business
        _ensure_seed_on_switch(b)
        set_active_business(request, b)
        messages.success(request, f"Switched to {b.name}.")
        return _redirect_next_or_home(request, fallback="tenants:choose_business")

    if len(active_memberships) > 1:
        # 3) let them choose
        return redirect("tenants:choose_business")

    # 4) none active — nudge based on what exists
    pending_i_created = Business.objects.filter(created_by=user, status="PENDING").order_by("-created_at").first()
    if pending_i_created:
        messages.info(request, "Your business is pending approval. You can still browse or request to join another.")
        return redirect("tenants:choose_business")

    messages.info(request, "Join an existing business to get started.")
    return redirect("tenants:join_as_agent")


@login_required
def clear_active(request: HttpRequest) -> HttpResponse:
    """Clear current active business and send to chooser/next."""
    set_active_business(request, None)
    messages.info(request, "Cleared active business.")
    return _redirect_next_or_home(request, fallback="tenants:choose_business")


@login_required
def set_active(request: HttpRequest, biz_id) -> HttpResponse:
    """
    Switch the active business for this session.

    **Superusers** may switch to any ACTIVE business.
    **Everyone else (including staff)** must have an ACTIVE membership in that business.
    """
    biz = get_object_or_404(Business, pk=biz_id, status="ACTIVE")

    user = request.user
    if not user.is_superuser:
        has_access = Membership.objects.filter(
            business=biz, user=user, status="ACTIVE"
        ).exists()
        if not has_access:
            messages.error(request, "You do not have access to that business.")
            return redirect("tenants:choose_business")

    _ensure_seed_on_switch(biz)
    set_active_business(request, biz)
    messages.success(request, f"Switched to {biz.name}.")
    return _home_redirect(request)


@login_required
def choose_business(request: HttpRequest) -> HttpResponse:
    """
    GET:
      - **Superusers**: can see ALL ACTIVE businesses (for support).
      - **Everyone else**: only businesses where they have an ACTIVE membership.
    POST:
      - Attempts to switch to the selected business using `set_active` rules above.
    """
    user = request.user

    memberships_qs = (
        Membership.objects.filter(user=user, status="ACTIVE")
        .select_related("business")
        .order_by("-created_at")
    )

    # Only superusers get a global list; staff users do NOT get blanket access.
    all_active_businesses = None
    if user.is_superuser:
        all_active_businesses = Business.objects.filter(status="ACTIVE").order_by("name")

    if request.method == "POST":
        bid = request.POST.get("business_id")
        if not bid:
            messages.error(request, "No business selected.")
            return redirect("tenants:choose_business")

        b = get_object_or_404(Business, pk=bid, status="ACTIVE")

        if not user.is_superuser:
            ok = Membership.objects.filter(
                business=b, user=user, status="ACTIVE"
            ).exists()
            if not ok:
                messages.error(request, "You cannot switch to that business.")
                return redirect("tenants:choose_business")

        _ensure_seed_on_switch(b)
        set_active_business(request, b)
        messages.success(request, f"Switched to {b.name}.")
        return _home_redirect(request)

    return render(
        request,
        "tenants/choose_business.html",
        {
            "memberships": memberships_qs,
            "all_active_businesses": all_active_businesses,  # None unless superuser
        },
    )


# -------------------------------------------------------------------
# Onboarding
# -------------------------------------------------------------------

@login_required
def create_business_as_manager(request: HttpRequest) -> HttpResponse:
    """
    Manager onboarding: user proposes a new Business (PENDING) and gets a PENDING manager membership.
    A staff user must approve the business (and activates the creator's manager membership).
    """
    if request.method == "POST":
        form = CreateBusinessForm(request.POST)
        if form.is_valid():
            b: Business = form.save(commit=False)
            b.slug = form.cleaned_data["slug"]
            b.created_by = request.user
            b.status = "PENDING"
            b.save()

            Membership.objects.create(
                user=request.user,
                business=b,
                role="MANAGER",
                status="PENDING",
            )

            messages.success(
                request,
                "Business submitted. A developer will approve it shortly."
            )
            return redirect("tenants:choose_business")
    else:
        form = CreateBusinessForm()

    return render(request, "tenants/create_business.html", {"form": form})


@login_required
def join_as_agent(request: HttpRequest) -> HttpResponse:
    """
    Agent onboarding: user requests to join an ACTIVE business by name.
    Managers of that business will approve/reject the request.
    """
    if request.method == "POST":
        form = JoinAsAgentForm(request.POST)
        if form.is_valid():
            b: Business = form.cleaned_data["business"]

            # Only allow join requests to ACTIVE businesses
            if b.status != "ACTIVE":
                messages.error(request, "You can only join a business that is ACTIVE.")
                return redirect("tenants:join_as_agent")

            mem, created = Membership.objects.get_or_create(
                user=request.user,
                business=b,
                defaults={"role": "AGENT", "status": "PENDING"},
            )

            if not created:
                if mem.status == "ACTIVE":
                    _ensure_seed_on_switch(b)
                    set_active_business(request, b)
                    messages.info(request, f"Already active in {b.name}. Switched.")
                    return _home_redirect(request)
                elif mem.status == "REJECTED":
                    mem.status = "PENDING"
                    mem.role = "AGENT"
                    mem.save(update_fields=["status", "role"])

            messages.success(request, f"Join request sent to {b.name}'s managers.")
            return redirect("tenants:choose_business")
    else:
        form = JoinAsAgentForm()

    return render(request, "tenants/join_as_agent.html", {"form": form})


# -------------------------------------------------------------------
# Staff approval / manager tools
# -------------------------------------------------------------------

@user_passes_test(lambda u: u.is_staff)
def staff_approve_business(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Staff-only screen to approve or reject a newly created business.
    On approve:
      - Business → ACTIVE
      - Creator's MANAGER membership → ACTIVE
      - Seed default Store/Warehouse so manager sees a fresh dashboard
    On reject:
      - Business → SUSPENDED
      - All memberships → REJECTED
    """
    b = get_object_or_404(Business, pk=pk)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "approve":
            b.status = "ACTIVE"
            b.save(update_fields=["status"])

            # Activate the creating manager membership (if exists)
            Membership.objects.filter(
                business=b, role="MANAGER", user=b.created_by
            ).update(status="ACTIVE")

            _ensure_seed_on_switch(b)
            messages.success(request, f"Approved business {b.name}.")
        elif action == "reject":
            b.status = "SUSPENDED"
            b.save(update_fields=["status"])
            Membership.objects.filter(business=b).update(status="REJECTED")
            messages.info(request, f"Rejected business {b.name}.")
        else:
            messages.error(request, "Unknown action.")
        return redirect(request.path)

    pending_members = Membership.objects.filter(business=b).select_related("user")
    return render(
        request,
        "tenants/staff_approve_business.html",
        {"business": b, "members": pending_members},
    )


@login_required
@require_business
@require_role(["Manager", "Admin"])  # group-based manager/admin access
def manager_review_agents(request: HttpRequest) -> HttpResponse:
    """
    Manager screen within the active business to approve/reject agent join requests.
    """
    b: Business = request.business

    if request.method == "POST":
        mem_id = request.POST.get("membership_id")
        action = request.POST.get("action")
        mem = get_object_or_404(Membership, pk=mem_id, business=b)

        if action == "approve":
            mem.status = "ACTIVE"
            mem.save(update_fields=["status"])
            messages.success(request, f"Approved {mem.user} as agent.")
        elif action == "reject":
            mem.status = "REJECTED"
            mem.save(update_fields=["status"])
            messages.info(request, f"Rejected {mem.user}.")
        else:
            messages.error(request, "Unknown action.")
        return redirect("tenants:manager_review_agents")

    pending = (
        Membership.objects.filter(business=b, role="AGENT", status="PENDING")
        .select_related("user")
        .order_by("-created_at")
    )
    active = (
        Membership.objects.filter(business=b, role="AGENT", status="ACTIVE")
        .select_related("user")
        .order_by("-created_at")
    )

    return render(
        request,
        "tenants/manager_review_agents.html",
        {"pending": pending, "active": active},
    )


# -------------------------------------------------------------------
# NEW: Locations (safe, template-free placeholder)
# -------------------------------------------------------------------

@login_required
@require_business
@require_role(["Manager", "Admin"])
def manager_locations(request: HttpRequest) -> HttpResponse:
    """
    Lightweight, **safe** locations page so the sidebar link never 404s/500s.

    - If `inventory.Store` exists, we try to list locations for the active business.
    - If not, we show a friendly message so managers aren't stuck.
    - We intentionally return inline HTML to avoid missing-template errors for now.
    """
    b: Business = request.business

    # Try to import a Store model if your inventory app provides one.
    Store = None  # type: ignore
    try:
        from inventory.models import Store as _Store  # type: ignore
        Store = _Store
    except Exception:
        Store = None  # not installed yet

    locations: list = []
    error: Optional[str] = None

    if Store is not None:
        try:
            # Prefer filtering by business if field exists; otherwise fall back to all.
            try:
                locations = list(Store.objects.filter(business=b).order_by("name"))
            except Exception:
                locations = list(Store.objects.all().order_by("id")[:50])
        except Exception as e:
            error = f"Could not load locations: {e!s}"

    # Very small, styled HTML so you have *something* useful immediately.
    def _esc(s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    rows = "".join(
        f"<tr><td>{_esc(getattr(loc, 'name', str(loc)))}</td>"
        f"<td>{_esc(getattr(loc, 'kind', getattr(loc, 'type', 'STORE') or 'STORE'))}</td>"
        f"<td>{'Yes' if getattr(loc, 'is_active', True) else 'No'}</td></tr>"
        for loc in locations
    ) or '<tr><td colspan="3" style="color:#64748b">No locations found.</td></tr>'

    note = ""
    if Store is None:
        note = (
            '<div style="padding:.75rem 1rem; border:1px solid #e2e8f0; '
            'border-radius:10px; background:#f8fafc; color:#334155; margin-bottom:1rem">'
            "Locations UI is not wired to a Store model yet. "
            "Ask a developer to add <code>inventory.Store</code> (with at least <em>name</em> and "
            "<em>business</em> fields) to enable full management here."
            "</div>"
        )
    elif error:
        note = (
            f'<div style="padding:.75rem 1rem; border:1px solid #fee2e2; '
            f'border-radius:10px; background:#fef2f2; color:#991b1b; margin-bottom:1rem">{_esc(error)}</div>'
        )

    html = f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>Locations · { _esc(b.name) }</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      body{{font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; margin:24px; color:#0b1220;}}
      .h1{{font-weight:800; font-size:22px; margin:0 0 12px}}
      .muted{{color:#64748b}}
      table{{border-collapse:collapse; width:100%; background:#fff; border:1px solid #e2e8f0; border-radius:10px; overflow:hidden}}
      th,td{{padding:.6rem .8rem; border-bottom:1px solid #eef2f7; font-size:14px;}}
      th{{text-align:left; background:#f8fafc; font-weight:800; color:#0b1220}}
    </style>
  </head>
  <body>
    <div class="h1">Locations <span class="muted">· { _esc(b.name) }</span></div>
    {note}
    <table role="table" aria-label="Locations">
      <thead><tr><th>Name</th><th>Type</th><th>Active</th></tr></thead>
      <tbody>
        {rows}
      </tbody>
    </table>
  </body>
</html>
    """.strip()

    return HttpResponse(html)

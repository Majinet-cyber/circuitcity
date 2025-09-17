#--- PART 1/3 START (inventory/views.py) ---

# --- PART 1/3 — circuitcity/inventory/views.py ---


from __future__ import annotations

# --- Role helper import (safe) ----------------------------------------
try:
    from accounts.utils import user_is_manager  # type: ignore[attr-defined]
except Exception:
    def user_is_manager(user) -> bool:  # type: ignore[no-redef]
        if not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        try:
            return user.groups.filter(name__in=["Manager", "Admin"]).exists()
        except Exception:
            return False

# --- Optional Business model (safe) ----------------------------------
try:
    from tenants.models import Business  # type: ignore
except Exception:
    Business = None  # graceful fallback when multi-tenant app is absent
from datetime import datetime, timedelta, date
from django.db.models.functions import TruncMonth, TruncDate, Cast, Coalesce
from django.db import connection, transaction
from django.urls import reverse
from urllib.parse import quote
from decimal import Decimal
import logging

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required


from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.conf import settings
from datetime import timedelta, date, datetime   # ← add datetime
from django.db.models.functions import TruncMonth, TruncDate, Cast, Coalesce  # ← add TruncDate
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.mail import mail_admins
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.cache import cache
from django.db import transaction, connection, IntegrityError
from django.db.models import (
    Sum, Q, Exists, OuterRef, Count, F, DecimalField, ExpressionWrapper, Case, When, Value
)
from django.db.models.deletion import ProtectedError
from django.db.models.functions import TruncMonth, TruncDate, Cast, Coalesce
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.exceptions import TemplateDoesNotExist
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_http_methods, require_GET
from django.views.decorators.csrf import ensure_csrf_cookie
from django.urls import reverse
from django.core.exceptions import ValidationError

import csv
import json
import math
from functools import wraps
from datetime import datetime, timedelta, date, time  # <-- added time
from urllib.parse import urlencode, quote
import logging

# Forms
from .forms import ScanInForm, ScanSoldForm, InventoryItemForm

# Models (inventory)
from .models import (
    InventoryItem,
    Product,
    InventoryAudit,
    WarrantyCheckLog,
    TimeLog,
    Location,
)

# Wallet models live in the wallet app (safe import)
try:
    from wallet.models import WalletTxn  # type: ignore
except Exception:
    WalletTxn = None  # graceful fallback

from sales.models import Sale

# Admin Purchase Orders (wallet app)
try:
    from wallet.models import AdminPurchaseOrder, AdminPurchaseOrderItem  # type: ignore
except Exception:
    AdminPurchaseOrder = None
    AdminPurchaseOrderItem = None

# Cache version (signals may bump this). Safe fallback.
try:
    from .cache_utils import get_dashboard_cache_version
except Exception:
    def get_dashboard_cache_version() -> int:
        return 1

User = get_user_model()

# ------------------------------------------------------------------
# Warranty lookups DISABLED: do NOT import warranty.py or requests.
# ------------------------------------------------------------------
_WARRANTY_LOOKUPS_DISABLED = True

# ------------------------------------------------------------------
# OTP alias: when ENABLE_2FA=1 use django-otp, else fall back to login_required
# ------------------------------------------------------------------
try:
    if getattr(settings, "ENABLE_2FA", False):
        from django_otp.decorators import otp_required  # type: ignore
    else:
        raise ImportError
except Exception:  # pragma: no cover
    from django.contrib.auth.decorators import login_required as otp_required  # type: ignore

# -----------------------
# Role helpers
# -----------------------
def is_manager_like(user) -> bool:
    if getattr(user, "is_staff", False):
        return True
    try:
        manager_group_names = set(getattr(settings, "ROLE_GROUP_MANAGER_NAMES", ["Manager", "Admin"]))
    except Exception:
        manager_group_names = {"Manager", "Admin"}
    return user.groups.filter(name__in=manager_group_names).exists()

# -----------------------
# JSON helpers / safe API wrapper
# -----------------------
def json_ok(payload=None, **extra):
    data = {"ok": True}
    if payload:
        data.update(payload)
    if extra:
        data.update(extra)
    return JsonResponse(data)

def json_err(message, status=400, **extra):
    data = {"ok": False, "error": str(message)}
    if extra:
        data.update(extra)
    return JsonResponse(data, status=status)

def safe_api(fn):
    @wraps(fn)
    def _wrap(request, *args, **kwargs):
        try:
            return fn(request, *args, **kwargs)
        except PermissionError as e:
            return json_err(e, status=403)
        except ValueError as e:
            return json_err(e, status=400)
        except Exception as e:
            return json_err(f"Unexpected error: {e}", status=500)
    return _wrap

# -----------------------
# Multi-tenant helpers
# -----------------------
_SESSION_BIZ_KEY = "active_business_id"

def _model_has_field(model, field_name: str) -> bool:
    try:
        model._meta.get_field(field_name)  # type: ignore[attr-defined]
        return True
    except Exception:
        return False

def _biz_field_name_for(model) -> str | None:
    """Return the FK field name used for business/tenant on this model, if any."""
    for name in ("business", "tenant", "store", "company", "org", "organization"):
        if _model_has_field(model, name):
            return name
    return None

def _biz_filter_kwargs(model, biz_id: int | None) -> dict:
    """Build a filter dict for the model based on the active business id."""
    if not biz_id:
        return {}
    fld = _biz_field_name_for(model)
    return {fld: biz_id} if fld else {}

def _attach_business_kwargs(model, biz_id: int | None) -> dict:
    """
    Return kwargs to attach business FK when creating objects.
    IMPORTANT: use the *_id form so we can pass an integer pk safely.
    """
    if not biz_id:
        return {}
    fld = _biz_field_name_for(model)
    return {f"{fld}_id": biz_id} if fld else {}

def _get_active_business(request):
    """
    Return the active Business object (if available) and its id from session.
    Never raises; returns (None, None) when unavailable.
    """
    biz_id = None
    try:
        biz_id = int(request.session.get(_SESSION_BIZ_KEY) or 0) or None
    except Exception:
        biz_id = None

    if Business is None or not biz_id:
        return None, None

    try:
        biz = Business.objects.filter(pk=biz_id).first()
        if not biz:
            return None, None
        return biz, biz.pk
    except Exception:
        return None, None

def _require_active_business(request):
    """
    If no active business is selected, redirect the user to the setup/join page.
    This keeps brand-new managers from seeing global data.
    """
    _, biz_id = _get_active_business(request)
    if biz_id:
        return None  # OK
    # Try a best-effort URL
    try:
        url = reverse("tenants:join")
    except Exception:
        url = "/tenants/join/"
    messages.info(request, "Select or create your business to continue.")
    return redirect(url)

def _scoped(qs, request):
    """
    Scope any queryset to the active business if the underlying model supports it.
    """
    _, biz_id = _get_active_business(request)
    if not biz_id:
        return qs  # No scoping field or no business selected
    try:
        return qs.filter(**_biz_filter_kwargs(qs.model, biz_id))
    except Exception:
        return qs

def _obj_belongs_to_active_business(obj, request) -> bool:
    """Return True if obj has a business/tenant FK matching the active business (or no FK)."""
    if obj is None:
        return True
    _, biz_id = _get_active_business(request)
    if not biz_id:
        return True
    fld = _biz_field_name_for(obj.__class__)
    if not fld:
        return True
    try:
        related = getattr(obj, fld, None)
        if related is None:
            return False
        rel_id = getattr(related, "pk", getattr(related, "id", related))
        return rel_id == biz_id
    except Exception:
        return False

def _limit_form_querysets(form, request):
    """Constrain form dropdowns (Product, Location) to the active business."""
    try:
        if hasattr(form, "fields"):
            if "product" in form.fields:
                form.fields["product"].queryset = _scoped(Product.objects.all(), request)
            if "location" in form.fields:
                form.fields["location"].queryset = _scoped(Location.objects.all(), request)
    except Exception:
        pass

# -----------------------
# Date-window helpers (for calendar filtering)
# -----------------------
def parse_day_window(day_str: str) -> tuple[datetime | None, datetime | None]:
    """
    Parse YYYY-MM-DD and return aware start/end for that local day.
    Returns (None, None) if invalid.
    """
    if not day_str:
        return None, None
    try:
        d = datetime.fromisoformat(day_str).date()
    except Exception:
        return None, None
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(d, time.min), tz)
    end   = timezone.make_aware(datetime.combine(d, time.max), tz)
    return start, end

def get_preset_window(request, default_preset: str = "month") -> tuple[str, str, datetime | None, datetime | None]:
    """
    Read ?range=month|7d|all|day and ?day=YYYY-MM-DD
    Returns (preset, day_str, start, end).
    """
    preset = (request.GET.get("range") or default_preset).strip().lower()
    day_str = (request.GET.get("day") or "").strip()
    now = timezone.now()
    start = end = None

    if preset == "7d":
        end = now
        start = end - timedelta(days=7)
    elif preset == "all":
        start = end = None
    elif preset == "day":
        start, end = parse_day_window(day_str)
        if not (start and end):
            # fall back to default if invalid
            preset = default_preset
    if preset == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now
    return preset, day_str, start, end

def _time_q_for(model, start, end, fields: tuple[str, ...]) -> Q:
    """
    Build a Q(...) covering start..end over the first existing timestamp fields.
    If no (start,end) or no matching fields exist, returns empty Q().
    """
    if not (start and end):
        return Q()
    q = Q()
    for f in fields:
        try:
            model._meta.get_field(f)
            q |= (Q(**{f + "__gte": start}) & Q(**{f + "__lte": end}))
        except Exception:
            continue
    return q

# -----------------------
# Other helpers
# -----------------------
def _user_home_location(user):
    prof = getattr(user, "agent_profile", None)
    return getattr(prof, "location", None)

def _is_manager_or_admin(user):
    return bool(user_is_manager(user))

def _is_admin(user):
    return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))

def _is_auditor(user):
    try:
        return user.groups.filter(name__in=["Auditor", "Auditors"]).exists()
    except Exception:
        return False

def _can_view_all(user):
    return _is_manager_or_admin(user) or _is_auditor(user)

def _can_edit_inventory(user):
    return _is_manager_or_admin(user)

def _is_agent_user(user) -> bool:
    return bool(getattr(user, "agent_profile", None)) and not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))

def _reject_admin_assignment(user) -> str | None:
    """
    Returns an error message if this user is not eligible to be assigned stock.
    Agents only — never staff/superusers; must have an AgentProfile.
    """
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return "Stock cannot be assigned to admin/staff accounts. Assign to an agent."
    if not hasattr(user, "agent_profile"):
        return "Assigned user must be an agent (has AgentProfile)."
    return None

def _audit(item, user, action: str, details: str = ""):
    if not item:
        return
    try:
        biz_id = None
        # If the item itself has a biz FK (most do), reuse it
        for fldname in ("business", "tenant", "store", "company", "org", "organization"):
            if hasattr(item, fldname):
                rel = getattr(item, fldname)
                biz_id = getattr(rel, "id", getattr(rel, "pk", None))
                break
        InventoryAudit.objects.create(
            item=item, by_user=user, action=action, details=details or "",
            **_attach_business_kwargs(InventoryAudit, biz_id)
        )
    except Exception:
        pass  # never block on auditing

def _haversine_m(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    R = 6371000.0
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlmb = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return int(round(R * c))

def _paginate_qs(request, qs, default_per_page=50, max_per_page=200):
    try:
        per_page = int(request.GET.get("page_size", default_per_page))
    except (TypeError, ValueError):
        per_page = default_per_page
    per_page = min(max(per_page, 1), max_per_page)

    paginator = Paginator(qs, per_page)
    page_num = request.GET.get("page") or 1
    try:
        page_obj = paginator.page(page_num)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.page(1)

    def url_for(page):
        params = request.GET.copy()
        params["page"] = page
        return f"?{urlencode(params)}"

    return page_obj, url_for

def _wallet_balance(user):
    if WalletTxn is None:
        return 0
    try:
        return WalletTxn.balance_for(user)  # type: ignore[attr-defined]
    except Exception:
        try:
            return WalletTxn.objects.filter(user=user).aggregate(s=Sum("amount"))["s"] or 0
        except Exception:
            return 0

def _wallet_month_sum(user, year: int, month: int):
    if WalletTxn is None:
        return 0
    try:
        return WalletTxn.month_sum_for(user, year, month)  # type: ignore[attr-defined]
    except Exception:
        try:
            return (
                WalletTxn.objects.filter(user=user, created_at__year=year, created_at__month=month)
                .aggregate(s=Sum("amount"))["s"] or 0
            )
        except Exception:
            return 0

def _inv_base(show_archived: bool):
    if show_archived:
        return InventoryItem.objects
    if hasattr(InventoryItem, "active"):
        return InventoryItem.active
    try:
        return InventoryItem.objects.filter(is_active=True)
    except Exception:
        return InventoryItem.objects

def _render_dashboard_safe(request, context, today, mtd_count, all_time_count):
    try:
        return render(request, "inventory/dashboard.html", context)
    except TemplateDoesNotExist:
        return HttpResponse(
            f"<h1>Inventory Dashboard</h1>"
            f"<p>Template <code>inventory/dashboard.html</code> not found.</p>"
            f"<pre>today={today}  mtd={mtd_count}  all_time={all_time_count}</pre>",
            content_type="text/html",
        )

def _render_stock_list_safe(request, context):
    candidates = [
        "inventory/stock_list.html",  # preferred
        "inventory/list.html",        # legacy/alt
    ]
    for tpl in candidates:
        try:
            return render(request, tpl, context)
        except TemplateDoesNotExist:
            continue

    items = context.get("items", [])
    rows_html = []
    for it in items:
        rows_html.append(
            f"<tr>"
            f"<td>{it.imei or ''}</td>"
            f"<td>{(it.product or '')}</td>"
            f"<td>{it.status}</td>"
            f"<td>{'' if it.order_price is None else it.order_price}</td>"
            f"<td>{'' if it.selling_price is None else it.selling_price}</td>"
            f"<td>{getattr(getattr(it, 'current_location', None), 'name', getattr(getattr(it, 'location', None), 'name', '—')) or '—'}</td>"
            f"<td>{getattr(getattr(it, 'assigned_agent', None), 'username', getattr(getattr(it, 'assigned_to', None), 'username', '—')) or '—'}</td>"
            f"</tr>"
        )
    html = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Stock List — Fallback</title>
<style>
body{{font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;background:#f7fafc;margin:0}}
.wrap{{max-width:1100px;margin:24px auto;padding:0 16px}}
h1{{margin:.2rem 0 1rem}}
.table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e2e8f0}}
.table th,.table td{{padding:.5rem .65rem;border-top:1px solid #e2e8f0;font-size:14px}}
.table thead th{{background:#f1f5f9;text-align:left}}
.badge{{display:inline-block;padding:.15rem .4rem;border-radius:.4rem;background:#e2e8f0}}
.kpis{{display:flex;gap:12px;flex-wrap:wrap;margin:.75rem 0 1rem}}
.kpis .card{{background:#fff;border:1px solid #e2e8f0;border-radius:.5rem;padding:.6rem .8rem}}
</style>
</head><body>
<div class="wrap">
  <h1>Stock List (Safe Fallback)</h1>
  <div class="kpis">
    <div class="card">In stock: <strong>{context.get('total_in_stock', 0)}</strong></div>
    <div class="card">Sold: <strong>{context.get('total_sold', 0)}</strong></div>
    <div class="card">Order total: <strong>{context.get('sum_order_price', 0)}</strong></div>
    <div class="card">Selling total: <strong>{context.get('sum_selling_price', 0)}</strong></div>
  </div>
  <table class="table">
    <thead><tr>
      <th>IMEI</th><th>Product</th><th>Status</th><th>Order Price</th>
      <th>Selling Price</th><th>Location</th><th>Agent</th>
    </tr></thead>
    <tbody>
      {''.join(rows_html) if rows_html else '<tr><td colspan="7">No items found.</td></tr>'}
    </tbody>
  </table>
</div>
</body></html>"""
    return HttpResponse(html, content_type="text/html")

# -----------------------
# Scan pages (tenant-scoped)
# -----------------------
# --- required imports (safe if duplicated) ---
from decimal import Decimal
import logging

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

# scan_in view
@never_cache
@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def scan_in(request):
    # Require business selection for all inventory ops
    gate = _require_active_business(request)
    if gate:
        return gate

    if _is_auditor(request.user) and request.method == "POST":
        messages.error(request, "Auditors cannot stock-in devices.")
        return redirect("inventory:stock_list")

    # ---------- helper: is this user an Agent? ----------
    def _is_agent_user(u):
        try:
            if getattr(u, "agentprofile", None):  # AgentProfile relation if present
                return True
        except Exception:
            pass
        try:
            return u.groups.filter(name__iexact="Agent").exists()
        except Exception:
            return False

    # ---------- helper: resolve a default Location (scoped to active biz) ----------
    def _resolve_default_location():
        """
        Pick a sensible default location:
        1) exact match to the active business/store name (e.g., "Air Easy"),
           also tries "<name> Store" and icontains match.
        2) user home location (if your project defines it)
        3) other sane fallbacks (Maren/Home/Main/default/first)
        All queries are scoped to the active business when possible.
        """
        loc_field = (
            "current_location" if _model_has_field(InventoryItem, "current_location")
            else ("location" if _model_has_field(InventoryItem, "location") else None)
        )
        if not loc_field:
            return None

        # Active business (store) and its name
        biz, biz_id = _get_active_business(request)
        store_name = None
        try:
            store_name = (
                getattr(biz, "display_name", None)
                or getattr(biz, "name", None)
                or getattr(biz, "title", None)
            )
        except Exception:
            store_name = None

        # Related Location model
        Loc = None
        try:
            f = InventoryItem._meta.get_field(loc_field)
            Loc = getattr(getattr(f, "remote_field", None), "model", None)
        except Exception:
            Loc = None
        if not Loc:
            return None

        # Scope to this business if the model supports it
        qs = Loc.objects.all()
        try:
            if biz_id:
                if hasattr(Loc, "business_id"):
                    qs = qs.filter(business_id=biz_id)
                elif hasattr(Loc, "business"):
                    qs = qs.filter(business_id=biz_id)
        except Exception:
            pass

        # Prefer the active store name (e.g., "Air Easy")
        try:
            if store_name:
                for filt in (
                    {"name__iexact": store_name},
                    {"name__iexact": f"{store_name} Store"},
                    {"name__icontains": store_name},
                ):
                    m = qs.filter(**filt).order_by("id").first()
                    if m:
                        return m
        except Exception:
            pass

        # Per-user home/store next
        try:
            loc = _user_home_location(request.user)
            if loc:
                return loc
        except Exception:
            pass

        # Legacy / generic fallbacks
        try:
            cand = (
                qs.filter(name__iexact="Maren Store").first()
                or qs.filter(name__iexact="Maren").first()
                or qs.filter(name__icontains="maren").first()
                or qs.filter(name__iexact="Home").first()
                or qs.filter(name__iexact="Main").first()
                or qs.filter(name__icontains="default").first()
                or qs.order_by("id").first()
            )
            if cand:
                return cand
        except Exception:
            pass

        return None

    # Compute default BEFORE using it anywhere
    default_location = _resolve_default_location()

    # ---------- initial form values for GET ----------
    initial = {}
    if default_location:
        initial["location"] = default_location
    initial.setdefault("received_at", timezone.localdate())

    # Active business scoping
    _, biz_id = _get_active_business(request)
    biz_create_kwargs = _attach_business_kwargs(InventoryItem, biz_id)

    # Is location column REQUIRED (not null)?
    loc_field_name = (
        "current_location" if _model_has_field(InventoryItem, "current_location")
        else ("location" if _model_has_field(InventoryItem, "location") else None)
    )
    loc_is_required = False
    if loc_field_name:
        try:
            loc_field_obj = InventoryItem._meta.get_field(loc_field_name)
            loc_is_required = not getattr(loc_field_obj, "null", True)
        except Exception:
            loc_is_required = False

    if request.method == "POST":
        # If user didn’t pick a location, inject our default (so validation won’t block).
        post_data = request.POST.copy()
        if not post_data.get("location") and default_location is not None:
            try:
                post_data["location"] = str(getattr(default_location, "pk", default_location.id))
            except Exception:
                pass

        form = ScanInForm(post_data)
        _limit_form_querysets(form, request)  # scope dropdowns

        if not form.is_valid():
            messages.error(request, "Please correct the errors below.")
            return render(request, "inventory/scan_in.html", {"form": form})

        data = form.cleaned_data

        # Product is required
        if not data.get("product"):
            messages.error(request, "Select a product model.")
            return render(request, "inventory/scan_in.html", {"form": form})

        # Location handling
        if not data.get("location"):
            data["location"] = default_location  # may still be None
        if loc_is_required and not data.get("location"):
            messages.error(
                request,
                "Your inventory requires a location, but none were found for this store. "
                "Please create a location (e.g., “Air Easy Store”) and try again."
            )
            return render(request, "inventory/scan_in.html", {"form": form})

        # Tenant checks
        if not _obj_belongs_to_active_business(data["product"], request):
            messages.error(request, "That product is not in your store.")
            return render(request, "inventory/scan_in.html", {"form": form})
        if data.get("location") and not _obj_belongs_to_active_business(data["location"], request):
            messages.error(request, "That location is not in your store.")
            return render(request, "inventory/scan_in.html", {"form": form})

        imei = (data.get("imei") or "").strip()

        # Duplicate check (tenant-scoped)
        dup_qs = InventoryItem.objects.select_for_update()
        if biz_id:
            dup_qs = dup_qs.filter(**_biz_filter_kwargs(InventoryItem, biz_id))
        if imei and _model_has_field(InventoryItem, "imei") and dup_qs.filter(imei=imei).exists():
            messages.error(request, f"Item with IMEI {imei} already exists in your store.")
            return render(request, "inventory/scan_in.html", {"form": form})

        # ---------- build create kwargs ----------
        create_kwargs = {}
        if _model_has_field(InventoryItem, "product"):
            create_kwargs["product"] = data["product"]

        # Map Location field (only if we have one)
        if data.get("location"):
            if _model_has_field(InventoryItem, "current_location"):
                create_kwargs["current_location"] = data["location"]
            elif _model_has_field(InventoryItem, "location"):
                create_kwargs["location"] = data["location"]

        # Dates & price
        if _model_has_field(InventoryItem, "received_at"):
            create_kwargs["received_at"] = data.get("received_at") or timezone.localdate()
        if _model_has_field(InventoryItem, "order_price"):
            create_kwargs["order_price"] = data.get("order_price") or Decimal("0.00")
        if _model_has_field(InventoryItem, "imei"):
            create_kwargs["imei"] = imei
        if _model_has_field(InventoryItem, "status"):
            create_kwargs.setdefault("status", "IN_STOCK")

        # Assign to current user only if they are truly an Agent
        if data.get("assigned_to_me") and _is_agent_user(request.user):
            if _model_has_field(InventoryItem, "assigned_agent"):
                create_kwargs["assigned_agent"] = request.user
            elif _model_has_field(InventoryItem, "assigned_to"):
                create_kwargs["assigned_to"] = request.user
        # (Managers/admins: toggle is ignored so we don't violate model rules)

        # Attach business (tenant)
        create_kwargs.update(biz_create_kwargs)

        # ---------- save ----------
        try:
            item = InventoryItem(**create_kwargs)
            try:
                item.full_clean()
            except ValidationError as ve:
                first_err = "; ".join([f"{k}: {', '.join(v)}" for k, v in ve.message_dict.items()])
                messages.error(request, f"Cannot stock-in: {first_err}")
                return render(request, "inventory/scan_in.html", {"form": form})
            item.save()
        except IntegrityError as e:
            if "unique" in str(e).lower():
                messages.error(request, f"Item with IMEI {imei or '(blank)'} already exists.")
            else:
                messages.error(request, "Could not save this item (constraint error). Please check values and try again.")
            return render(request, "inventory/scan_in.html", {"form": form})
        except Exception:
            logging.exception("Scan IN failed | kwargs=%s", create_kwargs)
            if getattr(settings, "DEBUG", False):
                raise
            messages.error(request, "Unexpected error while saving this item. Please try again.")
            return render(request, "inventory/scan_in.html", {"form": form})

        _audit(item, request.user, "STOCK_IN", "Scan IN")
        messages.success(request, "Item saved.")
        return redirect("inventory:stock_list")

    # GET
    form = ScanInForm(initial=initial)
    _limit_form_querysets(form, request)
    return render(request, "inventory/scan_in.html", {"form": form})

@never_cache
@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def scan_sold(request):
    # Require business selection for all inventory ops
    gate = _require_active_business(request)
    if gate:
        return gate

    if _is_auditor(request.user) and request.method == "POST":
        messages.error(request, "Auditors cannot mark items as SOLD.")
        return redirect("inventory:stock_list")

    initial = {}
    loc = _user_home_location(request.user)
    if loc:
        initial["location"] = loc
    initial.setdefault("sold_at", timezone.localdate())

    # Active business
    _, biz_id = _get_active_business(request)

    if request.method == "POST":
        form = ScanSoldForm(request.POST)
        _limit_form_querysets(form, request)  # <-- scope dropdowns
        if not form.is_valid():
            messages.error(request, "Please correct the errors below.")
            return render(request, "inventory/scan_sold.html", {"form": form})

        data = form.cleaned_data
        imei = data["imei"]

        # Tenant-scoped fetch
        qs = InventoryItem.objects.select_for_update()
        if biz_id:
            qs = qs.filter(**_biz_filter_kwargs(InventoryItem, biz_id))
        try:
            item = qs.get(imei=imei)
        except InventoryItem.DoesNotExist:
            messages.error(request, "Item not found in your store. Check the IMEI and try again.")
            return render(request, "inventory/scan_sold.html", {"form": form})

        # If model has a "status" field, respect it
        if _model_has_field(InventoryItem, "status") and str(getattr(item, "status", "")) == "SOLD":
            messages.error(request, f"Item {item.imei} is already sold.")
            return render(request, "inventory/scan_sold.html", {"form": form})

        if data.get("price") is not None and data["price"] < 0:
            messages.error(request, "Price must be a non-negative amount.")
            return render(request, "inventory/scan_sold.html", {"form": form})

        # Ensure the chosen location is within this business
        if not _obj_belongs_to_active_business(data["location"], request):
            messages.error(request, "That location is not in your store.")
            return render(request, "inventory/scan_sold.html", {"form": form})

        # Apply updates only for fields that exist
        item._actor = request.user
        if _model_has_field(InventoryItem, "status"):
            item.status = "SOLD"
        if _model_has_field(InventoryItem, "selling_price"):
            item.selling_price = data.get("price")
        # Location may be 'current_location' or 'location'
        if _model_has_field(InventoryItem, "current_location"):
            item.current_location = data["location"]
        elif _model_has_field(InventoryItem, "location"):
            item.location = data["location"]
        if _model_has_field(InventoryItem, "sold_at"):
            item.sold_at = data.get("sold_at") or timezone.localdate()
        if _model_has_field(InventoryItem, "sold_by") and getattr(item, "sold_by", None) is None:
            try:
                item.sold_by = request.user
            except Exception:
                pass

        item.save()

        # Best-effort Sale record (also tenant-safe if Sale has business FK)
        try:
            sale_kwargs = {
                "item": item,
                "agent": request.user,
                "price": getattr(item, "selling_price", None) or 0,
            }
            if _model_has_field(InventoryItem, "sold_at"):
                sale_kwargs["sold_at"] = getattr(item, "sold_at", timezone.localdate())
            # pick a location for the Sale if available
            if _model_has_field(InventoryItem, "current_location"):
                sale_kwargs["location"] = data["location"]
            elif _model_has_field(InventoryItem, "location"):
                sale_kwargs["location"] = data["location"]
            sale_kwargs["commission_pct"] = data.get("commission_pct")
            sale_kwargs.update(_attach_business_kwargs(Sale, biz_id))
            Sale.objects.create(**{k: v for k, v in sale_kwargs.items() if v is not None})
        except Exception:
            pass

        _audit(item, request.user, "SOLD_FORM", "V1 flow")
        messages.success(
            request,
            f"Marked SOLD: {item.imei}{' at ' + str(getattr(item, 'selling_price', '')) if getattr(item, 'selling_price', None) else ''}",
        )
        return redirect("inventory:scan_sold")

    form = ScanSoldForm(initial=initial)
    _limit_form_querysets(form, request)  # <-- scope dropdowns
    return render(request, "inventory/scan_sold.html", {"form": form})


@never_cache
@login_required
@require_GET
@ensure_csrf_cookie
def scan_web(request):
    """
    Render the web-scanner page; if the template is missing, render a minimal fallback.
    """
    gate = _require_active_business(request)
    if gate:
        return gate

    candidates = [
        "inventory/scan_web.html",
        "circuitcity/templates/inventory/scan_web.html",
    ]
    for tpl in candidates:
        try:
            return render(request, tpl, {})
        except TemplateDoesNotExist:
            continue

    # Minimal fallback (never blank)
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Scan (Web) — Fallback</title>
  <style>body{font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;padding:24px;}
  .wrap{max-width:640px;margin:auto}.f{display:flex;gap:8px}</style>
</head>
<body>
  <div class="wrap">
    <h2>Scan (Web) — Fallback</h2>
    <p>If you see this, the template wasn't found. You can still mark SOLD here.</p>
    <div class="f">
      <input id="imei" placeholder="IMEI (15 digits)" inputmode="numeric" maxlength="15" />
      <input id="price" type="number" step="0.01" placeholder="Price (optional)" />
      <button id="go">Mark SOLD</button>
    </div>
    <pre id="out"></pre>
  </div>
  <script>
    const CSRFTOKEN_NAME = "{CSRFTOKEN}";
    function getCSRFCookie(){
      const m = document.cookie.match(new RegExp(CSRFTOKEN_NAME+"=([^;]+)"));
      return m ? m[1] : "";
    }
    document.getElementById('go').onclick = async () => {
      const imei = document.getElementById('imei').value.replace(/\\D/g, '');
      const price = document.getElementById('price').value;
      const out = document.getElementById('out');
      if (imei.length !== 15){ out.textContent = 'IMEI must be exactly 15 digits.'; return; }
      try{
        const r = await fetch("/inventory/api/mark-sold/", {
          method: "POST",
          headers: {"Content-Type":"application/json","X-CSRFToken": getCSRFCookie()},
          body: JSON.stringify({imei, price: price || undefined})
        });
        out.textContent = 'HTTP ' + r.status + '\\n' + (await r.text());
      }catch(err){
        out.textContent = 'Network error.';
      }
    };
  </script>
</body></html>"""
    html = html.replace("{CSRFTOKEN}", settings.CSRF_COOKIE_NAME)
    return HttpResponse(html, content_type="text/html")

# -----------------------
# Place Order (OTP-protected page)
# -----------------------
@never_cache
@login_required
@otp_required
@require_GET
def place_order_page(request):
    # Require business selection (POs are tenant data)
    gate = _require_active_business(request)
    if gate:
        return gate

    if not _is_manager_or_admin(request.user):
        return redirect("inventory:stock_list")

    html = """
    <!doctype html><html lang="en"><head>
      <meta charset="utf-8"/>
      <meta name="viewport" content="width=device-width,initial-scale=1"/>
      <title>Place Order</title>
      <style>
        :root{
          --bg:#0b1020; --panel:#0e172b; --muted:#a8b3cf;
          --border:#1f2a44; --primary:#2f6df6; --accent:#46c0ff; --ok:#16a34a; --warn:#f59e0b; --err:#ef4444;
          --radius:14px;
        }
        @media (prefers-color-scheme: light){
          :root{ --bg:#eef5ff; --panel:#ffffff; --muted:#475569; --border:#cfe0ff; --primary:#2f6df6; --accent:#0ea5e9; }
        }
        *{box-sizing:border-box}
        body{font-family:system-ui,Segoe UI,Inter,Roboto,Arial,sans-serif;background:var(--bg);color:#e6edf6;margin:0}
        .wrap{max-width:980px;margin:28px auto;padding:0 16px}
        h2{margin:.2rem 0 1rem}
        .note{background:var(--panel);border:1px solid var(--border);padding:12px;border-radius:var(--radius);color:#cbd5e1}
        .row{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:12px 0}
        .row-1{display:grid;grid-template-columns:1fr;gap:12px;margin:12px 0}
        label{display:block;font-size:13px;color:#cbd5e1;margin-bottom:6px}
        input[type="text"], input[type="email"], input[type="tel"], input[type="number"], select, textarea{
          width:100%;padding:10px 12px;border-radius:12px;border:1px solid var(--border);background:#0a1222;color:#e6edf6;
        }
        textarea{min-height:90px;resize:vertical}
        .card{background:var(--panel);border:1px solid var(--border);border-radius:var(--radius);padding:14px}
        .btn{display:inline-flex;gap:8px;align-items:center;padding:10px 14px;border-radius:12px;border:1px solid var(--border);text-decoration:none;color:#e6edf6;background:#0a1222;cursor:pointer}
        .btn:hover{filter:brightness(1.1)}
        .btn.primary{background:var(--primary);border-color:var(--primary);color:#fff}
        .btn.ghost{background:transparent}
        .btn.link{background:transparent;border:none;padding:0;color:#2f6df6;cursor:pointer}
        .btn.small{padding:6px 10px;border-radius:10px;font-size:13px}
        .grid-3{display:grid;grid-template-columns:2fr 1fr 1fr;gap:10px}
        .grid-4{display:grid;grid-template-columns:2fr 1fr 1fr 90px;gap:10px}
        table{width:100%;border-collapse:collapse}
        th,td{padding:10px;border-top:1px solid var(--border);font-size:14px}
        thead th{background:#0a1222;color:#cbd5e1;border-top:none}
        .right{text-align:right}
        .hidden{display:none}
        .pill{display:inline-block;padding:3px 8px;border-radius:999px;border:1px solid var(--border);color:#cbd5e1;font-size:12px}
        .onhand{color:#a3e635}
      </style>
    </head><body><div class="wrap">
      <h2>Place Order</h2>

      <div class="kpis">
        <div class="chip">Currency: <strong style="margin-left:6px">MWK</strong></div>
        <div class="chip hidden" id="roleChip"></div>
      </div>

      <div class="row">
        <div class="card">
          <h3 style="margin:0 0 8px">Supplier</h3>
          <div class="row">
            <div>
              <label>Supplier name</label>
              <input id="supplier_name" type="text" placeholder="e.g. ACME Phones Ltd" />
            </div>
            <div>
              <label>Supplier phone</label>
              <input id="supplier_phone" type="tel" placeholder="+26588..." />
            </div>
          </div>
          <div class="row">
            <div>
              <label>Supplier email</label>
              <input id="supplier_email" type="email" placeholder="vendor@example.com" />
            </div>
            <div>
              <label>Agent name (optional)</label>
              <input id="agent_name" type="text" placeholder="Who will receive?" />
            </div>
          </div>
          <div class="row-1">
            <div>
              <label>Notes</label>
              <textarea id="notes" placeholder="E.g. Urgent restock for next week..."></textarea>
            </div>
          </div>
        </div>

        <div class="card">
          <h3 style="margin:0 0 8px">Add Items</h3>

          <div class="row-1">
            <div class="search">
              <input id="search" type="text" placeholder="Search model (brand / model / variant)..." />
              <button class="btn small ghost" id="refreshBtn">↻ Refresh</button>
            </div>
          </div>

          <div class="grid-3" style="margin:8px 0">
            <div>
              <label>Model</label>
              <select id="model"></select>
              <div class="muted" id="onhandHint"></div>
            </div>
            <div>
              <label>Qty</label>
              <input id="qty" type="number" min="1" value="1" />
            </div>
            <div style="align-self:end">
              <button class="btn primary" id="addLine">+ Add</button>
            </div>
          </div>

          <div id="modelsEmpty" class="empty hidden">No models in stock right now.</div>
        </div>
      </div>

      <div class="card">
        <h3 style="margin:0 0 8px">Order Lines</h3>
        <div id="linesEmpty" class="hidden">No items added yet.</div>
        <div id="linesWrap">
          <table>
            <thead>
              <tr>
                <th>#</th><th>Product</th><th class="right">Qty</th><th class="right">Est. Unit</th><th class="right">Est. Line</th><th></th>
              </tr>
            </thead>
            <tbody id="linesBody"></tbody>
            <tfoot>
              <tr>
                <td colspan="4" class="right"><strong>Estimated Total</strong></td>
                <td class="right"><strong id="ttl">0</strong></td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>

      <div class="row">
        <div class="card">
          <div class="note">The Admin Purchase Order will price each line using the Product's <em>cost_price</em>. The totals shown here are estimates using the same value surfaced by the API.</div>
        </div>
        <div class="card" style="display:flex;justify-content:space-between;align-items:center">
          <a class="btn" href="/inventory/">← Back to stock</a>
          <button class="btn primary" id="submitOrder">Create Purchase Order</button>
        </div>
      </div>

      <div id="alert" class="card hidden"></div>

      <div id="successPanel" class="card hidden" style="border-color:#134e4a;background:#052e2b">
        <h3 style="margin:0 0 6px">PO created ✅</h3>
        <div id="successText" class="note" style="margin-bottom:8px"></div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <a class="btn" id="dlBtn" download>⬇ Download invoice</a>
          <a class="btn" id="whBtn" target="_blank" rel="noopener">WhatsApp</a>
          <a class="btn" id="emBtn">Email</a>
        </div>
      </div>

      <div class="note" style="margin-top:12px">
        Tip: need default pricing for Scan-In? Use <code>/inventory/api/order-price/&lt;product_id&gt;/</code>.
      </div>
    </div>

    <script>
      const CSRFTOKEN_NAME = "{{CSRFTOKEN}}";
      function getCSRFCookie(){
        const m = document.cookie.match(new RegExp(CSRFTOKEN_NAME+"=([^;]+)"));
        return m ? m[1] : "";
      }

      const nf = new Intl.NumberFormat();
      const $ = (id)=>document.getElementById(id);
      const modelSel = $("model");
      const qtyInp = $("qty");
      const linesBody = $("linesBody");
      const onhandHint = $("onhandHint");
      const alertBox = $("alert");
      const successPanel = $("successPanel");
      const successText = $("successText");
      const dlBtn = $("dlBtn");
      const whBtn = $("whBtn");
      const emBtn = $("emBtn");

      const order = { items: [] };

      function setAlert(kind, msg){
        alertBox.className = "card " + (kind==="error"?"error":kind==="warn"?"warn":"");
        alertBox.textContent = msg;
        alertBox.classList.remove("hidden");
        setTimeout(()=>alertBox.classList.add("hidden"), 4000);
      }

      function recalc(){
        let total = 0;
        linesBody.innerHTML = "";
        order.items.forEach((it, idx)=>{
          const line = (it.unit||0) * it.qty;
          total += line;
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td>${idx+1}</td>
            <td>${it.product}</td>
            <td class="right">${nf.format(it.qty)}</td>
            <td class="right">${nf.format(it.unit||0)}</td>
            <td class="right">${nf.format(line)}</td>
            <td class="right"><button class="btn small" data-i="${idx}" style="background:transparent;border:none;color:#2f6df6;cursor:pointer">Remove</button></td>
          `;
          linesBody.appendChild(tr);
        });
        document.getElementById("ttl").textContent = nf.format(total);
      }

      function addOrBump(pid, product, unit, addQty){
        const existing = order.items.find(i=>i.product_id===pid);
        if(existing){
          existing.qty += addQty;
        } else {
          order.items.push({product_id: pid, product, unit, qty: addQty});
        }
        recalc();
      }

      document.getElementById("linesBody").addEventListener("click", (e)=>{
        const btn = e.target.closest("button[data-i]");
        if(!btn) return;
        const i = parseInt(btn.getAttribute("data-i"),10);
        if(!Number.isNaN(i)){
          order.items.splice(i,1);
          recalc();
        }
      });

      async function loadModels(){
        try{
          const r = await fetch("/inventory/api/stock-models/");
          const data = await r.json();
          const list = (data && data.models) || [];
          modelSel.innerHTML = "";
          if(!list.length){
            onhandHint.textContent = "No models in stock right now.";
            return;
          }
          list.forEach(m=>{
            const opt = document.createElement("option");
            opt.value = m.product_id;
            opt.textContent = `${m.product}  ·  on hand ${m.on_hand}`;
            opt.dataset.price = m.default_price || "0";
            opt.dataset.onhand = m.on_hand || 0;
            modelSel.appendChild(opt);
          });
          updateOnhandHint();
        }catch(err){
          setAlert("error", "Failed to load models.");
        }
      }

      function updateOnhandHint(){
        const opt = modelSel.options[modelSel.selectedIndex];
        if(!opt){ onhandHint.textContent = ""; return; }
        const p = opt.dataset.price || "0";
        const oh = opt.dataset.onhand || 0;
        onhandHint.textContent = `Default price ~ ${nf.format(parseFloat(p)||0)} · On hand: ${oh}`;
      }

      modelSel.addEventListener("change", updateOnhandHint);
      document.getElementById("refreshBtn")?.addEventListener("click", (e)=>{ e.preventDefault(); loadModels(); });
      document.getElementById("search")?.addEventListener("input", (e)=>{
        const q = (e.target.value||"").toLowerCase();
        for(const opt of modelSel.options){
          const txt = opt.textContent.toLowerCase();
          opt.hidden = q && !txt.includes(q);
        }
        for(const opt of modelSel.options){
          if(!opt.hidden){ modelSel.value = opt.value; break; }
        }
        updateOnhandHint();
      });

      document.getElementById("addLine")?.addEventListener("click", (e)=>{
        e.preventDefault();
        const opt = modelSel.options[modelSel.selectedIndex];
        if(!opt){ setAlert("warn","No model selected."); return; }
        const qty = parseInt(qtyInp.value,10);
        if(!qty || qty < 1){ setAlert("warn","Quantity must be at least 1."); return; }
        const pid = parseInt(opt.value,10);
        const unit = parseFloat(opt.dataset.price||"0") || 0;
        addOrBump(pid, opt.textContent, unit, qty);
        qtyInp.value = "1";
      });

      document.getElementById("submitOrder")?.addEventListener("click", async ()=>{
        if(order.items.length===0){ setAlert("warn","Add at least one item to the order."); return; }
        const payload = {
          supplier_name: document.getElementById("supplier_name").value.trim(),
          supplier_email: document.getElementById("supplier_email").value.trim(),
          supplier_phone: document.getElementById("supplier_phone").value.trim(),
          agent_name: document.getElementById("agent_name").value.trim(),
          notes: document.getElementById("notes").value.trim(),
          items: order.items.map(i=>({product_id:i.product_id, quantity:i.qty}))
        };
        try{
          const r = await fetch("/inventory/api/place-order/", {
            method:"POST",
            headers:{ "Content-Type":"application/json", "X-CSRFToken": getCSRFCookie() },
            body: JSON.stringify(payload)
          });
          const data = await r.json();
          if(!r.ok || !data.ok){
            const msg = (data && (data.error || data.detail)) || ("HTTP "+r.status);
            setAlert("error", "Failed to create PO: " + msg);
            return;
          }
          successPanel.classList.remove("hidden");
          successText.textContent = `PO-${data.po_id} created. Total will reflect product cost prices.`;
          dlBtn.href = data.invoice_url;
          whBtn.href = data.share && data.share.whatsapp ? data.share.whatsapp : "#";
          emBtn.setAttribute("href", data.share && data.share.email ? data.share.email : "#");
          order.items = [];
          recalc();
          window.scrollTo({top: document.body.scrollHeight, behavior: "smooth"});
        }catch(err){
          setAlert("error", "Network error creating PO.");
        }
      });

      loadModels();
      updateOnhandHint();
    </script>
    </body></html>
    """
    html = html.replace("{{CSRFTOKEN}}", settings.CSRF_COOKIE_NAME)
    return HttpResponse(html, content_type="text/html; charset=utf-8")


@never_cache
@login_required
@require_POST
@transaction.atomic
@safe_api
def api_mark_sold(request):
    # Require business selection
    gate = _require_active_business(request)
    if gate:
        return gate  # safe_api will wrap this into a response

    if _is_auditor(request.user):
        return JsonResponse({"ok": False, "error": "Auditors cannot modify inventory."}, status=403)

    # Parse body (JSON or form)
    try:
        ctype = (request.headers.get("Content-Type") or request.content_type or "").lower()
        if "application/json" in ctype:
            payload = json.loads(request.body or "{}")
        else:
            payload = request.POST
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON body."}, status=400)

    imei = (payload.get("imei") or "").strip()
    comment = (payload.get("comment") or "").strip()
    raw_price = payload.get("price")
    raw_loc = payload.get("location_id") or payload.get("location")

    if not imei.isdigit() or len(imei) != 15:
        return JsonResponse({"ok": False, "error": "IMEI must be exactly 15 digits."}, status=400)

    # Active business & tenant-scoped fetch
    _, biz_id = _get_active_business(request)
    qs = InventoryItem.objects.select_for_update()
    if biz_id:
        qs = qs.filter(**_biz_filter_kwargs(InventoryItem, biz_id))
    try:
        item = qs.get(imei=imei)
    except InventoryItem.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Item not found in your store."}, status=404)

    # If already sold (when model has status)
    if _model_has_field(InventoryItem, "status") and str(getattr(item, "status", "")) == "SOLD":
        _audit(item, request.user, "SOLD_API_DUP", f"Duplicate mark-sold via API. Comment: {comment}")
        return JsonResponse({"ok": True, "imei": imei, "already_sold": True})

    # Validate price (optional)
    price_val = None
    if raw_price is not None and raw_price != "":
        try:
            price_val = float(raw_price)
            if price_val < 0:
                return JsonResponse({"ok": False, "error": "Price must be a non-negative amount."}, status=400)
        except Exception:
            return JsonResponse({"ok": False, "error": "Invalid price format."}, status=400)

    # Validate location (optional) WITH tenant check
    loc_id = None
    if raw_loc not in (None, "", 0, "0"):
        try:
            loc_id = int(raw_loc)
        except Exception:
            return JsonResponse({"ok": False, "error": "Invalid location id."}, status=400)
        # ensure provided location belongs to active tenant
        try:
            loc_qs = Location.objects.all()
            if biz_id:
                loc_qs = loc_qs.filter(**_biz_filter_kwargs(Location, biz_id))
            if not loc_qs.filter(id=loc_id).exists():
                return JsonResponse({"ok": False, "error": "That location is not in your store."}, status=403)
        except Exception:
            # If we cannot check, fail safe
            return JsonResponse({"ok": False, "error": "Unable to verify location for this store."}, status=400)

    # Apply updates (only existing fields)
    updates = {}
    if _model_has_field(InventoryItem, "status"):
        item.status = "SOLD"
        updates["status"] = "SOLD"

    if _model_has_field(InventoryItem, "sold_at") and not getattr(item, "sold_at", None):
        item.sold_at = timezone.localdate()
        updates["sold_at"] = item.sold_at

    if price_val is not None and _model_has_field(InventoryItem, "selling_price"):
        item.selling_price = price_val
        updates["selling_price"] = item.selling_price

    # Location may be 'current_location' or 'location'
    if loc_id is not None:
        if _model_has_field(InventoryItem, "current_location"):
            item.current_location_id = loc_id
            updates["current_location_id"] = item.current_location_id
        elif _model_has_field(InventoryItem, "location"):
            item.location_id = loc_id
            updates["location_id"] = item.location_id

    if _model_has_field(InventoryItem, "sold_by") and getattr(item, "sold_by", None) is None:
        try:
            item.sold_by = request.user
        except Exception:
            pass

    item.save()
    _audit(item, request.user, "SOLD_API", f"via scan_web; comment={comment}")

    # Create Sale record (best-effort, tenant-safe)
    try:
        sale_kwargs = {
            "item": item,
            "agent": request.user,
            "price": getattr(item, "selling_price", None) or 0,
        }
        if _model_has_field(InventoryItem, "sold_at"):
            sale_kwargs["sold_at"] = getattr(item, "sold_at", timezone.localdate())
        if loc_id is not None:
            sale_kwargs["location_id"] = (
                item.current_location_id if hasattr(item, "current_location_id") else getattr(item, "location_id", None)
            )
        sale_kwargs.update(_attach_business_kwargs(Sale, biz_id))
        Sale.objects.create(**{k: v for k, v in sale_kwargs.items() if v is not None})
    except Exception:
        pass

    return JsonResponse({"ok": True, "imei": imei, "updates": updates})

# --- PART 1/3 end ---
# --- PART 2/3 — circuitcity/inventory/views.py ---

# -----------------------
# Dashboard & list
# -----------------------
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_GET, require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.db.models import (
    Sum, Q, Exists, OuterRef, Count, F, DecimalField, ExpressionWrapper, Case, When, Value
)
from django.db.models.functions import TruncMonth, TruncDate, Cast, Coalesce
from django.utils import timezone
from datetime import timedelta, date
import json
import csv

@login_required
def inventory_dashboard(request):
    # Require a selected business
    gate = _require_active_business(request)
    if gate:
        return gate
    _, biz_id = _get_active_business(request)

    # NEW: calendar filter (range: all | 7d | month | day; day: YYYY-MM-DD)
    range_preset, day_str, start_dt, end_dt = get_preset_window(request, default_preset="month")

    # Back-compat: keep old ?period=month behavior if no new range supplied
    period = request.GET.get("period", "month")
    if request.GET.get("range"):
        # If explicit range given, normalize the legacy period label
        period = {"7d": "7d", "all": "all", "day": "day"}.get(range_preset, "month")

    model_id = request.GET.get("model") or None
    today = timezone.localdate()
    tomorrow = today + timedelta(days=1)
    month_start = today.replace(day=1)

    ver = get_dashboard_cache_version()
    cache_key = (
        f"dash:v{ver}:biz:{biz_id or 'none'}:u{request.user.id}"
        f":p:{period}:m:{model_id or 'all'}:r:{range_preset}:d:{day_str or '*'}"
    )
    cached = cache.get(cache_key)
    if cached:
        return _render_dashboard_safe(
            request, cached, today, cached.get("mtd_count", 0), cached.get("all_time_count", 0)
        )

    # Scope for KPIs and stock widgets (respect permissions AND business)
    if _can_view_all(request.user):
        sales_qs_all = _scoped(Sale.objects.select_related("item", "agent", "item__product"), request)
        items_qs = _scoped(
            InventoryItem.objects.select_related("product", "assigned_agent", "current_location"),
            request,
        )
        scope_label = "All agents"
    else:
        sales_qs_all = _scoped(
            Sale.objects.filter(agent=request.user).select_related("item", "agent", "item__product"),
            request,
        )
        items_qs = _scoped(
            InventoryItem.objects.filter(assigned_agent=request.user).select_related(
                "product", "assigned_agent", "current_location"
            ),
            request,
        )
        scope_label = "My sales"

    if model_id:
        sales_qs_all = sales_qs_all.filter(item__product_id=model_id)
        items_qs = items_qs.filter(product_id=model_id)

    # Period/window filter for charts + KPIs (sold_at range)
    time_q = _time_q_for(Sale, start_dt, end_dt, ("sold_at",))
    if time_q:
        sales_qs_period = sales_qs_all.filter(time_q)
    else:
        sales_qs_period = sales_qs_all
        if period == "month":
            sales_qs_period = sales_qs_all.filter(sold_at__gte=month_start)
        elif period == "7d":
            sales_qs_period = sales_qs_all.filter(sold_at__gte=timezone.now() - timedelta(days=7))
        # period == "all" -> no extra filter; period == "day" would have time_q already

    # KPI: today + month + all-time (unchanged legacy)
    today_count = sales_qs_all.filter(sold_at__gte=today, sold_at__lt=tomorrow).count()
    dec2 = DecimalField(max_digits=14, decimal_places=2)
    today_total = sales_qs_all.filter(sold_at__gte=today, sold_at__lt=tomorrow).aggregate(
        s=Coalesce(Sum("price"), Value(0), output_field=dec2)
    )["s"] or 0
    mtd_count = sales_qs_all.filter(sold_at__gte=month_start, sold_at__lt=tomorrow).count()
    all_time_count = sales_qs_all.count()

    # NEW: window KPIs (respecting calendar range)
    window_totals = sales_qs_period.aggregate(
        window_revenue=Coalesce(Sum("price"), Value(0), output_field=dec2)
    )
    window_count = sales_qs_period.count()
    window_revenue = float(window_totals.get("window_revenue") or 0)

    # ---- Agent ranking (ALL agents within this business) ----
    pct_dec = DecimalField(max_digits=5, decimal_places=2)
    rank_base = _scoped(Sale.objects.select_related("agent"), request)
    if model_id:
        rank_base = rank_base.filter(item__product_id=model_id)
    # Apply the same window
    if time_q:
        rank_base = rank_base.filter(time_q)
    elif period == "month":
        rank_base = rank_base.filter(sold_at__gte=month_start)
    elif period == "7d":
        rank_base = rank_base.filter(sold_at__gte=timezone.now() - timedelta(days=7))

    commission_pct_dec = Cast(F("commission_pct"), pct_dec)
    commission_expr = ExpressionWrapper(
        Coalesce(F("price"), Value(0), output_field=dec2) *
        (Coalesce(commission_pct_dec, Value(0), output_field=pct_dec) / Value(100, output_field=pct_dec)),
        output_field=dec2,
    )

    agent_rank_qs = (
        rank_base.values("agent_id", "agent__username")
        .annotate(
            total_sales=Count("id"),
            earnings=Coalesce(Sum(commission_expr), Value(0), output_field=dec2),
            revenue=Coalesce(Sum("price"), Value(0), output_field=dec2),
        )
        .order_by("-earnings", "-total_sales", "agent__username")
    )
    agent_rank = list(agent_rank_qs)

    # Wallet summaries (decimal-safe) — scoped to business if WalletTxn has a business FK
    agent_wallet_summaries = {}
    agent_ids = [row["agent_id"] for row in agent_rank if row.get("agent_id")]
    if agent_ids and WalletTxn is not None:
        w = _scoped(WalletTxn.objects, request).filter(user_id__in=agent_ids)  # type: ignore[union-attr]
        month_start_dt = timezone.make_aware(timezone.datetime.combine(month_start, timezone.datetime.min.time()))
        today_dt = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.max.time()))
        agent_wallet_rows = w.values("user_id").annotate(
            balance=Sum("amount"),
            lifetime_commission=Sum(Case(When(reason="COMMISSION", then="amount"),
                                         default=Value(0, output_field=dec2))),
            lifetime_advance=Sum(Case(When(reason="ADVANCE", then="amount"),
                                      default=Value(0, output_field=dec2))),
            lifetime_adjustment=Sum(Case(When(reason="ADJUSTMENT", then="amount"),
                                         default=Value(0, output_field=dec2))),
            month_commission=Sum(
                Case(
                    When(reason="COMMISSION",
                         created_at__gte=month_start_dt, created_at__lte=today_dt,
                         then="amount"),
                    default=Value(0, output_field=dec2),
                )
            ),
            month_advance=Sum(
                Case(
                    When(reason="ADVANCE",
                         created_at__gte=month_start_dt, created_at__lte=today_dt,
                         then="amount"),
                    default=Value(0, output_field=dec2),
                )
            ),
            month_adjustment=Sum(
                Case(
                    When(reason="ADJUSTMENT",
                         created_at__gte=month_start_dt, created_at__lte=today_dt,
                         then="amount"),
                    default=Value(0, output_field=dec2),
                )
            ),
        )
        for r in agent_wallet_rows:
            uid = r["user_id"]
            m_total = (r["month_commission"] or 0) + (r["month_advance"] or 0) + (r["month_adjustment"] or 0)
            lt_total = (r["lifetime_commission"] or 0) + (r["lifetime_advance"] or 0) + (r["lifetime_adjustment"] or 0)
            agent_wallet_summaries[uid] = {
                "balance": float(r["balance"] or 0),
                "month": {
                    "commission": float(r["month_commission"] or 0),
                    "advance": float(r["month_advance"] or 0),
                    "adjustment": float(r["month_adjustment"] or 0),
                    "total": float(m_total or 0),
                },
                "lifetime": {
                    "commission": float(r["lifetime_commission"] or 0),
                    "advance": float(r["lifetime_advance"] or 0),
                    "adjustment": float(r["lifetime_adjustment"] or 0),
                    "total": float(lt_total or 0),
                },
            }

    # >>> Rank by WALLET BALANCE (desc) as primary key; keep original ties
    for row in agent_rank:
        uid = row.get("agent_id")
        row["wallet_balance"] = float(agent_wallet_summaries.get(uid, {}).get("balance", 0.0))
    agent_rank.sort(
        key=lambda r: (
            r.get("wallet_balance", 0.0),
            float(r.get("earnings") or 0.0),
            int(r.get("total_sales") or 0),
        ),
        reverse=True,
    )
    # <<< End wallet-based ranking

    # ===== Revenue/Profit last 12 months (scoped to business) =====
    def back_n_months(d: date, n: int) -> date:
        y = d.year
        m = d.month - n
        while m <= 0:
            m += 12
            y -= 1
        return date(y, m, 1)

    month_start_base = month_start
    last_12_labels = [back_n_months(month_start_base, n).strftime("%Y-%m") for n in range(11, -1, -1)]

    rev_qs = _scoped(Sale.objects.select_related("item"), request).filter(
        sold_at__gte=back_n_months(month_start_base, 11)
    )
    if not _can_view_all(request.user):
        rev_qs = rev_qs.filter(agent=request.user)
    if model_id:
        rev_qs = rev_qs.filter(item__product_id=model_id)

    rev_by_month = (
        rev_qs.annotate(m=TruncMonth("sold_at"))
        .values("m")
        .annotate(total=Coalesce(Sum("price"), Value(0), output_field=dec2))
        .order_by("m")
    )
    totals_map = {r["m"].strftime("%Y-%m"): float(r["total"] or 0) for r in rev_by_month if r["m"]}

    # Profit uses Coalesce so NULL order prices don't nuke a month
    profit_expr_month = ExpressionWrapper(
        Coalesce(F("price"), Value(0), output_field=dec2) -
        Coalesce(F("item__order_price"), Value(0), output_field=dec2),
        output_field=dec2,
    )
    prof_by_month = (
        rev_qs.annotate(m=TruncMonth("sold_at"))
        .values("m")
        .annotate(total=Coalesce(Sum(profit_expr_month), Value(0), output_field=dec2))
        .order_by("m")
    )
    prof_map = {r["m"].strftime("%Y-%m"): float(r["total"] or 0) for r in prof_by_month if r["m"]}

    revenue_points = [totals_map.get(lbl, 0.0) for lbl in last_12_labels]
    profit_points = [prof_map.get(lbl, 0.0) for lbl in last_12_labels]

    # ===== Agents: total stock vs sold units (period filter applied, scoped) =====
    if _can_view_all(request.user):
        items_scope = _scoped(
            InventoryItem.objects.select_related("product", "assigned_agent", "current_location"),
            request,
        )
    else:
        items_scope = _scoped(
            InventoryItem.objects.filter(assigned_agent=request.user).select_related(
                "product", "assigned_agent", "current_location"
            ),
            request,
        )
    if model_id:
        items_scope = items_scope.filter(product_id=model_id)
    total_assigned = (
        items_scope.values("assigned_agent_id", "assigned_agent__username")
        .annotate(total_stock=Count("id"))
        .order_by("assigned_agent__username")
    )
    sold_units = sales_qs_period.values("agent_id").annotate(sold=Count("id"))
    sold_map = {r["agent_id"]: r["sold"] for r in sold_units}
    agent_rows = [
        {
            "agent_id": row["assigned_agent_id"],
            "agent": row["assigned_agent__username"] or "—",
            "total_stock": row["total_stock"],
            "sold_units": sold_map.get(row["assigned_agent_id"], 0),
        }
        for row in total_assigned
    ]

    # ===== Cost vs Revenue vs Profit (period/model filtered, decimal-safe) =====
    totals = sales_qs_period.aggregate(
        revenue=Coalesce(Sum("price"), Value(0), output_field=dec2),
        cost=Coalesce(Sum(Coalesce(F("item__order_price"), Value(0), output_field=dec2)), Value(0), output_field=dec2),
        profit=Coalesce(Sum(profit_expr_month), Value(0), output_field=dec2),
    )
    pie_revenue = float(totals.get("revenue") or 0)
    pie_cost = float(totals.get("cost") or 0)
    pie_profit = float(totals.get("profit") or 0)

    # ===== Battery =====
    in_stock_qs = items_scope.filter(status="IN_STOCK")
    jug_count = in_stock_qs.count()
    jug_fill_pct = min(100, int(round((jug_count / 100.0) * 100))) if jug_count > 0 else 0
    if jug_count <= 20:
        jug_color = "red"
    elif 21 <= jug_count <= 50:
        jug_color = "yellow"
    elif 51 <= jug_count <= 69:
        jug_color = "mildgreen"
    else:
        jug_color = "lightgreen"

    # NEW for UI: map to Stock Health label
    if jug_count <= 10:
        stock_health = "Critical"
    elif jug_count <= 30:
        stock_health = "Low"
    else:
        stock_health = "Good"

    # Products dropdown (scoped)
    products_qs = _scoped(Product.objects.order_by("brand", "model", "variant"), request)
    products = products_qs.values("id", "brand", "model", "variant")

    # ===== Wallet (current user) - scoped if WalletTxn supports business =====
    def _sum(qs):
        return qs.aggregate(s=Sum("amount"))["s"] or 0

    if WalletTxn is not None:
        month_qs = _scoped(
            WalletTxn.objects.filter(user=request.user, created_at__date__gte=month_start, created_at__date__lte=today),
            request,
        )  # type: ignore[union-attr]
        my_month_commission = _sum(month_qs.filter(reason="COMMISSION"))
        my_month_advance = _sum(month_qs.filter(reason="ADVANCE"))
        my_month_adjustment = _sum(month_qs.filter(reason="ADJUSTMENT"))
        life_qs = _scoped(WalletTxn.objects.filter(user=request.user), request)  # type: ignore[union-attr]
        my_life_commission = _sum(life_qs.filter(reason="COMMISSION"))
        my_life_advance = _sum(life_qs.filter(reason="ADVANCE"))
        my_life_adjustment = _sum(life_qs.filter(reason="ADJUSTMENT"))
        my_life_total = _sum(life_qs)
        my_balance = _sum(life_qs)
    else:
        my_month_commission = my_month_advance = my_month_adjustment = 0
        my_life_commission = my_life_advance = my_life_adjustment = my_life_total = 0
        my_balance = 0

    # NEW for UI: Profit Margin (% of selected period)
    profit_margin = int(round((pie_profit / pie_revenue) * 100)) if pie_revenue > 0 else 0

    context = {
        # filter state for the UI (calendar picker can read these)
        "range": range_preset,
        "filter_day": day_str or "",
        "filter_start": start_dt.isoformat() if start_dt else None,
        "filter_end": end_dt.isoformat() if end_dt else None,

        "period": period,
        "model_id": int(model_id) if model_id else None,
        "products": list(products),

        # Leaderboard + wallet chips
        "agent_rank": agent_rank,
        "agent_wallet_summaries": agent_wallet_summaries,

        # Charts
        "labels_json": json.dumps(last_12_labels),
        "revenue_points_json": json.dumps(revenue_points),
        "profit_points_json": json.dumps(profit_points),
        "pie_data_json": json.dumps([pie_cost, pie_revenue, pie_profit]),

        # Agent stock table
        "agent_rows": agent_rows,

        # Battery / Stock health
        "jug_count": jug_count,
        "jug_fill_pct": jug_fill_pct,
        "jug_color": jug_color,
        "stock_health": stock_health,

        # KPIs (legacy + new window KPIs)
        "is_manager_or_admin": _is_manager_or_admin(request.user),
        "today_count": today_count,
        "mtd_count": mtd_count,
        "all_time_count": all_time_count,
        "today_total": float(today_total or 0),
        "profit_margin": profit_margin,

        # NEW window KPIs
        "window_count": window_count,
        "window_revenue": window_revenue,

        "kpis": {
            "scope": scope_label,
            "today_count": today_count,
            "month_count": mtd_count,
            "all_count": all_time_count,
        },

        # My wallet (summary)
        "wallet": {
            "balance": my_balance,
            "month": {
                "commission": my_month_commission,
                "advance": my_month_advance,
                "adjustment": my_month_adjustment,
                "total": my_month_commission + my_month_advance + my_month_adjustment,
                "month_label": month_start.strftime("%b %Y"),
            },
            "lifetime": {
                "commission": my_life_commission,
                "advance": my_life_advance,
                "adjustment": my_life_adjustment,
                "total": my_life_total,
            },
        },
    }

    # --- Feature flags & slide config: disable the landing overlay/rotator “cloud”
    context["PREDICTIVE_ENABLED"]   = bool(getattr(settings, "PREDICTIVE_ENABLED", True))
    context["THEME_ROTATE_ENABLED"] = False  # <— turn off rotation by default
    context["THEME_ROTATE_MS"]      = int(getattr(settings, "THEME_ROTATE_MS", 10000))
    context["THEME_DEFAULT"]        = str(getattr(settings, "THEME_DEFAULT", "style-1"))
    context["ROTATOR_MODE"]         = "off"  # <— no slideshow overlay on first land
    context["DASHBOARD_SLIDES"] = [
        # kept for compatibility if you choose to re-enable rotation later
        {
            "key": "trends",
            "title": "Sales Trends",
            "apis": ["/inventory/api_sales_trend/?period=7d&metric=count",
                     "/inventory/api_profit_bar/",
                     "/inventory/api_top_models/?period=today"]
        },
        {
            "key": "cash",
            "title": "Cash Overview",
            "apis": ["/inventory/api_cash_overview/"]
        },
        {
            "key": "agents",
            "title": "Agent Performance",
            "apis": ["/inventory/api_agent_trend/?months=6&metric=sales"]
        }
    ]

    cache.set(cache_key, context, 60)
    return _render_dashboard_safe(request, context, today, mtd_count, all_time_count)


@never_cache
@login_required
@require_http_methods(["GET"])
def stock_list(request):
    # Tenant gate
    gate = _require_active_business(request)
    if gate:
        return gate
    _, biz_id = _get_active_business(request)

    q = (request.GET.get("q") or "").strip()
    show_archived = request.GET.get("archived") == "1"
    want_csv = request.GET.get("export") == "csv"

    # NEW: calendar filter on stock page too (for sales KPIs panel)
    range_preset, day_str, start_dt, end_dt = get_preset_window(request, default_preset="all")
    time_q_sales = _time_q_for(Sale, start_dt, end_dt, ("sold_at",))

    # Normalize status filter:
    raw_status = (request.GET.get("status") or "").lower()
    # accepted: "in", "in_stock", "sold", "all" (default -> "in")
    if raw_status in ("sold", "all", "in", "in_stock"):
        status = raw_status
    else:
        status = "in"

    # Base queryset (scoped to business)
    has_sales_subq = Sale.objects.filter(item=OuterRef("pk"))
    if biz_id:
        has_sales_subq = has_sales_subq.filter(**_biz_filter_kwargs(Sale, biz_id))

    base_mgr = _inv_base(show_archived)
    base_scoped = _scoped(base_mgr.all(), request).select_related(
        "product", "current_location", "assigned_agent"
    ).annotate(has_sales=Exists(has_sales_subq))

    # Permission scoping for visible data
    if _can_view_all(request.user):
        visible_base = base_scoped
        sales_scope = _scoped(Sale.objects.select_related("item", "agent"), request)
    else:
        visible_base = base_scoped.filter(assigned_agent=request.user)
        sales_scope = _scoped(Sale.objects.filter(agent=request.user).select_related("item", "agent"), request)

    # ===== KPIs (computed from visible_base; not affected by search/status UI) =====
    is_sold = Q(status="SOLD")
    dec2 = DecimalField(max_digits=14, decimal_places=2)

    total_in_stock = visible_base.exclude(is_sold).count()
    total_sold = visible_base.filter(is_sold).count()
    sum_order_price = visible_base.exclude(is_sold).aggregate(
        s=Coalesce(Sum("order_price"), Value(0), output_field=dec2)
    )["s"] or 0
    sum_selling_price = visible_base.filter(is_sold).aggregate(
        s=Coalesce(Sum("selling_price"), Value(0), output_field=dec2)
    )["s"] or 0

    # NEW: window sales KPIs for the selected date/day/7d/all
    if time_q_sales:
        win_sales_qs = sales_scope.filter(time_q_sales)
    else:
        if range_preset == "7d":
            win_sales_qs = sales_scope.filter(sold_at__gte=timezone.now() - timedelta(days=7))
        elif range_preset == "month":
            win_sales_qs = sales_scope.filter(sold_at__gte=timezone.now().replace(day=1))
        else:
            win_sales_qs = sales_scope  # all time

    window_sales_count = win_sales_qs.count()
    window_sales_total = float(
        win_sales_qs.aggregate(s=Coalesce(Sum("price"), Value(0), output_field=dec2))["s"] or 0
    )

    # ===== Build list queryset (status + search) from visible_base =====
    qs = visible_base
    if status == "sold":
        qs = qs.filter(is_sold)
    elif status in ("all",):
        pass
    else:  # default: in-stock
        qs = qs.exclude(is_sold)

    if q:
        qs = qs.filter(
            Q(imei__icontains=q)
            | Q(product__name__icontains=q)
            | Q(product__brand__icontains=q)
            | Q(product__model__icontains=q)
            | Q(product__code__icontains=q)  # replaced sku with code (field exists)
        )

    # Sort results
    qs = qs.order_by("-received_at", "product__model")

    # Paginate
    page_obj, url_for = _paginate_qs(
        request,
        qs,
        default_per_page=50,
        max_per_page=200
    )

    # Build rows for template
    rows = [
        {
            "imei": it.imei or "",
            "product": str(it.product) if it.product else "",
            "status": "SOLD" if it.status == "SOLD" else "In stock",
            "order_price": f"{(it.order_price or 0):,.0f}",
            "selling_price": "-" if it.selling_price is None else f"{float(it.selling_price):,.0f}",
            "location": it.current_location.name if it.current_location_id else "-",
            "agent": it.assigned_agent.get_username() if it.assigned_agent_id else "-",
        }
        for it in page_obj.object_list
    ]

    # Optional CSV export (still scoped)
    if want_csv:
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="stock.csv"'
        writer = csv.writer(response)
        writer.writerow(["IMEI", "Product", "Status", "Order Price", "Selling Price", "Location", "Agent"])
        for row in rows:
            writer.writerow([
                row["imei"], row["product"], row["status"],
                row["order_price"], row["selling_price"],
                row["location"], row["agent"],
            ])
        return response

    # Render with robust fallback if the template is missing
    return _render_stock_list_safe(
        request,
        {
            "items": page_obj.object_list,
            "rows": rows,
            "q": q,
            "is_admin": _is_admin(request.user),
            "can_edit": _can_edit_inventory(request.user),
            "show_archived": show_archived,

            # date filter state for UI calendar
            "range": range_preset,
            "filter_day": day_str or "",
            "filter_start": start_dt.isoformat() if start_dt else None,
            "filter_end": end_dt.isoformat() if end_dt else None,

            # Fallback template expects these exact keys:
            "total_in_stock": total_in_stock,
            "total_sold": total_sold,
            "sum_order_price": sum_order_price,
            "sum_selling_price": sum_selling_price,

            # Extra KPIs for the selected window
            "window_sales_count": window_sales_count,
            "window_sales_total": window_sales_total,

            # Also include the more descriptive ones some templates use:
            "in_stock": total_in_stock,
            "sold_count": total_sold,
            "sum_order": sum_order_price,
            "sum_selling": sum_selling_price,
            "page_obj": page_obj,
            "url_for": url_for,
            "status": status,
            # Battery target: managers/admins/auditors see a 100-cap battery, agents see 20-cap
            "target_full": 100 if _can_view_all(request.user) else 20,
        }
    )


@never_cache
@login_required
@require_http_methods(["GET"])
def export_csv(request):
    # Same filters/permissions as stock_list, but always returns CSV
    gate = _require_active_business(request)
    if gate:
        return gate
    _, biz_id = _get_active_business(request)

    q = request.GET.get("q", "").strip()
    show_archived = request.GET.get("archived") == "1"
    status = (request.GET.get("status") or "").lower()

    has_sales_subq = Sale.objects.filter(item=OuterRef("pk"))
    if biz_id:
        has_sales_subq = has_sales_subq.filter(**_biz_filter_kwargs(Sale, biz_id))
    base_mgr = _inv_base(show_archived)

    qs = _scoped(base_mgr.all(), request).select_related("product", "current_location", "assigned_agent").annotate(has_sales=Exists(has_sales_subq))
    if not _can_view_all(request.user):
        qs = qs.filter(assigned_agent=request.user)

    # Match stock_list search & status handling
    if q:
        qs = qs.filter(
            Q(imei__icontains=q)
            | Q(product__model__icontains=q)
            | Q(product__brand__icontains=q)
            | Q(product__variant__icontains=q)
        )
    is_sold = Q(status="SOLD")
    if status == "sold":
        qs = qs.filter(is_sold)
    elif status not in ("", "all"):
        qs = qs.exclude(is_sold)

    qs = qs.order_by("-received_at", "product__model")

    filename = f"stock_export_{timezone.now():%Y%m%d_%H%M}.csv"
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(
        ["IMEI", "Product", "Status", "Order Price", "Selling Price", "Location", "Agent", "Received", "Archived", "Has Sales"]
    )
    for it in qs.iterator():
        product_str = str(it.product) if it.product else ""
        location_str = it.current_location.name if it.current_location_id else ""
        agent_str = it.assigned_agent.get_username() if it.assigned_agent_id else ""
        received_str = it.received_at.strftime("%Y-%m-%d") if it.received_at else ""
        writer.writerow(
            [
                it.imei or "",
                product_str,
                it.status,
                f"{it.order_price:.2f}" if it.order_price is not None else "",
                f"{it.selling_price:.2f}" if it.selling_price is not None else "",
                location_str,
                agent_str,
                received_str,
                "No" if getattr(it, "is_active", True) else "Yes",
                "Yes" if getattr(it, "has_sales", False) else "No",
            ]
        )
    return response


# -----------------------
# Time logging & Wallet
# -----------------------
@never_cache
@login_required
@require_http_methods(["GET"])
def time_checkin_page(request):
    # Prefer a home location only if it belongs to the active business
    pref_loc = _user_home_location(request.user)
    if pref_loc and not _obj_belongs_to_active_business(pref_loc, request):
        pref_loc = None
    return render(
        request,
        "inventory/time_checkin.html",
        {"pref_loc_id": pref_loc.id if pref_loc else "", "pref_loc_name": pref_loc.name if pref_loc else ""},
    )

# --- Inventory Settings (profile + 2FA + notifications) ---
from hashlib import md5

def _gravatar(email: str, size: int = 160) -> str:
    if not email:
        email = "user@example.com"
    h = md5(email.strip().lower().encode("utf-8")).hexdigest()
    return f"https://www.gravatar.com/avatar/{h}?s={size}&d=identicon"

def _two_factor_status(user) -> dict:
    """
    Try to detect common 2FA setups gracefully.
    - django-two-factor-auth (user.phonenumber or default device)
    - django-otp devices
    Fallback: disabled.
    """
    enabled = False
    provider = None
    try:
        # django-otp
        from django_otp import devices_for_user
        devs = list(devices_for_user(user))
        if devs:
            enabled = True
            provider = devs[0].device_id if hasattr(devs[0], "device_id") else devs[0].__class__.__name__
    except Exception:
        pass

    try:
        # two_factor default device API
        if hasattr(user, "staticdevice_set") or hasattr(user, "defaultdevice"):
            # If any static tokens or default device exists, assume enabled
            if getattr(user, "defaultdevice", None) or (hasattr(user, "staticdevice_set") and user.staticdevice_set.exists()):
                enabled = True
                provider = provider or "TOTP"
    except Exception:
        pass

    return {
        "enabled": enabled,
        "provider": provider or ("TOTP" if enabled else None),
        # Where to send user to manage 2FA if you have the app mounted; otherwise leave "#"
        "manage_url": getattr(settings, "TWO_FACTOR_MANAGE_URL", "/account/two-factor/"),
    }

@login_required
def settings_home(request):
    user = request.user
    profile = getattr(user, "profile", None)  # ok if you don’t have a Profile model
    avatar_url = getattr(profile, "avatar_url", None) or _gravatar(user.email, 160)

    twofa = _two_factor_status(user)

    context = {
        "title": "Settings",
        "avatar_url": avatar_url,
        "user_full_name": (user.get_full_name() or user.username),
        "user_username": user.username,
        "user_email": user.email,
        "last_login": user.last_login,
        "twofa": twofa,
        # existing notification toggles can be wired later; showing as UI only
    }
    return render(request, "inventory/settings.html", context)

@login_required
def settings_redirect(request):
    return redirect("accounts:settings_unified")


@never_cache
@login_required
@require_POST
def api_time_checkin(request):
    # Ensure an active business and attach it to TimeLog when possible
    gate = _require_active_business(request)
    if gate:
        return gate
    _, biz_id = _get_active_business(request)

    try:
        if request.content_type and "application/json" in request.content_type.lower():
            payload = json.loads(request.body or "{}")
        else:
            payload = request.POST
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON body."}, status=400)

    checkin_type = (payload.get("checkin_type") or payload.get("type") or "ARRIVAL").upper()
    if checkin_type not in (TimeLog.ARRIVAL, TimeLog.DEPARTURE):
        checkin_type = TimeLog.ARRIVAL

    lat_raw = payload.get("latitude", payload.get("lat"))
    lon_raw = payload.get("longitude", payload.get("lon"))
    acc_raw = payload.get("accuracy_m", payload.get("accuracy"))

    try:
        lat = float(lat_raw) if lat_raw not in (None, "") else None
        lon = float(lon_raw) if lon_raw not in (None, "") else None
        acc = int(acc_raw) if acc_raw not in (None, "") else None
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid lat/lon/accuracy."}, status=400)

    loc = None
    loc_id = payload.get("location_id")
    if loc_id:
        try:
            loc = _scoped(Location.objects.all(), request).get(pk=int(loc_id))
        except Exception:
            return JsonResponse({"ok": False, "error": "Invalid location_id."}, status=400)
    if not loc:
        loc = _user_home_location(request.user)
        if loc and not _obj_belongs_to_active_business(loc, request):
            loc = None  # ignore foreign-business locations

    dist = None
    within = False
    if loc and loc.latitude is not None and loc.longitude is not None and lat is not None and lon is not None:
        dist = _haversine_m(lat, lon, float(loc.latitude), float(loc.longitude))
        radius = (loc.geofence_radius_m or 150) + (acc or 0)
        within = dist <= radius

    tl = TimeLog.objects.create(
        user=request.user,
        location=loc,
        checkin_type=checkin_type,
        latitude=lat,
        longitude=lon,
        accuracy_m=acc,
        distance_m=dist,
        within_geofence=within,
        note=(payload.get("note") or "").strip()[:200],
        **_attach_business_kwargs(TimeLog, biz_id),
    )

    return JsonResponse(
        {
            "ok": True,
            "id": tl.id,
            "logged_at": tl.logged_at.isoformat(),
            "location": (loc.name if loc else None),
            "distance_m": dist,
            "within_geofence": within,
            "checkin_type": checkin_type,
        }
    )

@never_cache
@login_required
@require_http_methods(["GET"])
def time_logs(request):
    # Scope TimeLog to business if model supports it
    base = _scoped(TimeLog.objects.select_related("user", "location"), request)
    if _can_view_all(request.user):
        qs = base.order_by("-logged_at")
    else:
        qs = base.filter(user=request.user).order_by("-logged_at")

    page_obj, url_for = _paginate_qs(request, qs, default_per_page=50, max_per_page=200)
    return render(
        request, "inventory/time_logs.html", {"logs": page_obj.object_list, "page_obj": page_obj, "url_for": url_for}
    )


@never_cache
@login_required
@require_GET
def api_wallet_summary(request):
    # Scoped wallet summary (if WalletTxn has business FK, _scoped will apply it)
    target = request.user
    user_id = request.GET.get("user_id")
    if user_id:
        if not _is_manager_or_admin(request.user):
            return JsonResponse({"ok": False, "error": "Permission denied."}, status=403)
        try:
            target = User.objects.get(pk=int(user_id))
        except Exception:
            return JsonResponse({"ok": False, "error": "Unknown user_id."}, status=400)

    if WalletTxn is not None:
        balance = _scoped(WalletTxn.objects.filter(user=target), request).aggregate(s=Sum("amount"))["s"] or 0
    else:
        balance = 0

    year = request.GET.get("year")
    month = request.GET.get("month")
    data = {"ok": True, "user_id": target.id, "balance": balance}
    if year and month:
        try:
            y, m = int(year), int(month)
            if WalletTxn is not None:
                data["month_sum"] = _scoped(
                    WalletTxn.objects.filter(user=target, created_at__year=y, created_at__month=m),
                    request,
                ).aggregate(s=Sum("amount"))["s"] or 0
            else:
                data["month_sum"] = 0
            data["year"] = y
            data["month"] = m
        except Exception:
            data["month_sum"] = None
    return JsonResponse(data)


api_wallet_balance = api_wallet_summary


@never_cache
@login_required
@otp_required
@require_POST
def api_wallet_add_txn(request):
    if WalletTxn is None:
        return JsonResponse({"ok": False, "error": "Wallet models not installed."}, status=500)

    if not _is_admin(request.user):
        return JsonResponse({"ok": False, "error": "Admin only."}, status=403)

    # Ensure business to attach on create
    gate = _require_active_business(request)
    if gate:
        return gate
    _, biz_id = _get_active_business(request)

    try:
        if request.content_type and "application/json" in request.content_type.lower():
            payload = json.loads(request.body or "{}")
        else:
            payload = request.POST
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON body."}, status=400)

    try:
        target = User.objects.get(pk=int(payload.get("user_id")))
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid or missing user_id."}, status=400)

    try:
        amount = float(payload.get("amount"))
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid amount."}, status=400)

    reason = (payload.get("reason") or "ADJUSTMENT").upper()
    allowed = {k for k, _ in getattr(WalletTxn, "REASON_CHOICES", [])} or {"ADJUSTMENT", "ADVANCE", "COMMISSION", "PAYOUT"}  # type: ignore[arg-type]
    if reason not in allowed:
        return JsonResponse({"ok": False, "error": f"Invalid reason. Allowed: {sorted(list(allowed))}"}, status=400)

    memo = (payload.get("memo") or "").strip()[:200]

    txn = WalletTxn.objects.create(  # type: ignore[union-attr]
        user=target,
        amount=amount,
        reason=reason,
        memo=memo,
        **_attach_business_kwargs(WalletTxn, biz_id),
    )

    # Return business-scoped balance
    new_balance = _scoped(WalletTxn.objects.filter(user=target), request).aggregate(s=Sum("amount"))["s"] or 0
    return JsonResponse({"ok": True, "txn_id": txn.id, "balance": new_balance})


api_wallet_txn = api_wallet_add_txn


@never_cache
@login_required
@require_http_methods(["GET"])
def wallet_page(request):
    # Business gate
    gate = _require_active_business(request)
    if gate:
        return gate
    _, biz_id = _get_active_business(request)

    target = request.user
    user_id = request.GET.get("user_id")
    if user_id and _is_manager_or_admin(request.user):
        try:
            target = User.objects.get(pk=int(user_id))
        except Exception:
            target = request.user

    today = timezone.localdate()

    if WalletTxn is not None:
        life_qs = _scoped(WalletTxn.objects.filter(user=target), request)  # type: ignore[union-attr]
        balance = life_qs.aggregate(s=Sum("amount"))["s"] or 0
        month_sum = _scoped(
            WalletTxn.objects.filter(user=target, created_at__year=today.year, created_at__month=today.month),
            request,
        ).aggregate(s=Sum("amount"))["s"] or 0
        recent_txns = _scoped(
            WalletTxn.objects.select_related("user").filter(user=target).order_by("-created_at")[:50],
            request,
        )  # type: ignore[union-attr]
        reasons = getattr(WalletTxn, "REASON_CHOICES", [])
    else:
        balance = 0
        month_sum = 0
        recent_txns = []
        reasons = []

    # Restrict agent list to current business if possible
    agents = []
    if _is_manager_or_admin(request.user):
        if biz_id:
            agents_qs = User.objects.filter(assigned_items__business_id=biz_id).order_by("username").distinct()
        else:
            agents_qs = User.objects.order_by("username")
        agents = list(agents_qs.values("id", "username"))

    context = {
        "target": target,
        "balance": balance,
        "month_sum": month_sum,
        "recent_txns": recent_txns,
        "reasons": reasons,
        "is_admin": _is_admin(request.user),
        "is_manager_or_admin": _is_manager_or_admin(request.user),
        "agents": agents,
        "today_year": today.year,
        "today_month": today.month,
    }
    return render(request, "inventory/wallet.html", context)


# -----------------------
# Stock management
# -----------------------
@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def update_stock(request, pk):
    # Only load items from the active business
    item = get_object_or_404(_scoped(InventoryItem.objects, request), pk=pk)

    if not _can_edit_inventory(request.user):
        msg = (
            f"EDIT attempt BLOCKED: user '{request.user.username}' tried to edit "
            f"item {item.imei or item.pk} at {timezone.now():%Y-%m-%d %H:%M}."
        )
        _audit(item, request.user, "EDIT_DENIED", "Insufficient permissions")
        mail_admins(subject="Edit attempt blocked", message=msg, fail_silently=True)
        messages.error(request, "Only managers/admins can edit inventory items.")
        return redirect("inventory:stock_list")

    if request.method == "POST":
        form = InventoryItemForm(request.POST, instance=item, user=request.user)
        if form.is_valid():
            # Enforce: only agents (non-staff/superuser with AgentProfile) can *hold* stock
            new_holder = form.cleaned_data.get("assigned_agent")
            if new_holder and not _is_agent_user(new_holder):
                messages.error(request, "Only agent accounts can hold stock. Choose a non-admin user with an AgentProfile.")
                return render(request, "inventory/edit_stock.html", {"form": form, "item": item})

            changed_fields = list(form.changed_data)
            price_fields = {"order_price", "selling_price"}
            if (price_fields & set(changed_fields)) and not _is_admin(request.user):
                messages.error(request, "Only admins can edit order/selling prices.")
                return render(request, "inventory/edit_stock.html", {"form": form, "item": item})

            old_vals = {name: getattr(item, name) for name in changed_fields}
            saved_item = form.save()

            if _is_admin(request.user):
                bulk_updates = {}
                if "order_price" in changed_fields:
                    bulk_updates["order_price"] = form.cleaned_data.get("order_price")
                if "selling_price" in changed_fields:
                    bulk_updates["selling_price"] = form.cleaned_data.get("selling_price")

                if bulk_updates:
                    base_mgr = (
                        InventoryItem.active if hasattr(InventoryItem, "active") else InventoryItem.objects.filter(is_active=True)
                    )
                    # Apply bulk updates only within the same business
                    qs = _scoped(base_mgr, request).filter(product=saved_item.product).exclude(pk=saved_item.pk)
                    updated = qs.update(**bulk_updates)
                    if updated:
                        _audit(
                            saved_item,
                            request.user,
                            "BULK_PRICE_UPDATE",
                            f"Updated {updated} items for product '{saved_item.product}'. Fields: {bulk_updates}",
                        )
                        messages.info(
                            request, f"Applied {', '.join(bulk_updates.keys())} to {updated} other '{saved_item.product}' item(s)."
                        )

            details = "Changed fields:\n" + (
                "\n".join([f"{k}: {old_vals.get(k)} \u2192 {getattr(saved_item, k)}" for k in changed_fields])
                if changed_fields
                else "No field changes"
            )
            _audit(saved_item, request.user, "EDIT", details)

            messages.success(request, "Item updated.")
            return redirect("inventory:stock_list")
    else:
        form = InventoryItemForm(instance=item, user=request.user)

    return render(request, "inventory/edit_stock.html", {"form": form, "item": item})


@require_POST
@never_cache
@login_required
def delete_stock(request, pk):
    # Only delete within the active business
    item = get_object_or_404(_scoped(InventoryItem.objects, request), pk=pk)

    if not _is_admin(request.user):
        msg = (
            f"Deletion attempt BLOCKED: user '{request.user.username}' tried to delete "
            f"item {item.imei or item.pk} at {timezone.now():%Y-%m-%d %H:%M}."
        )
        _audit(item, request.user, "DELETE_DENIED", msg)
        mail_admins(subject="Deletion attempt blocked", message=msg, fail_silently=True)
        messages.error(request, "Only admins can delete items. Admin has been notified.")
        return redirect("inventory:stock_list")

    item_repr = f"{item.imei or item.pk} ({item.product})"
    try:
        _audit(
            item,
            request.user,
            "DELETE",
            f"Attempt by {request.user.username} at {timezone.now():%Y-%m-%d %H:%M}. Item: {item_repr}",
        )
        item.delete()
        messages.success(request, "Item deleted.")
    except ProtectedError:
        item.is_active = False
        item.save(update_fields=["is_active"])
        _audit(item, request.user, "ARCHIVE_FALLBACK", "ProtectedError: related sales exist; archived instead.")
        messages.info(request, "This item has sales, so it was archived instead of deleted.")
    return redirect("inventory:stock_list")

# --- PART 2/3 ENDS ---

# --- PART 3/3 — circuitcity/inventory/views.py ---

from django.db import transaction, connection
from django.urls import reverse
from urllib.parse import quote
from django.db.models.functions import TruncDate
from datetime import datetime

@require_POST
@never_cache
@login_required
def restore_stock(request, pk):
    # Tenant gate + scoped fetch
    gate = _require_active_business(request)
    if gate:
        return gate

    item = get_object_or_404(_scoped(InventoryItem.objects, request), pk=pk)

    if not _is_admin(request.user):
        msg = (
            f"Restore attempt BLOCKED: user '{request.user.username}' tried to restore "
            f"item {item.imei or item.pk} at {timezone.now():%Y-%m-%d %H:%M}."
        )
        # Use a valid action choice (RESTORE_DENIED is not in InventoryAudit.ACTION_CHOICES)
        _audit(item, request.user, "EDIT_DENIED", msg)
        messages.error(request, "You do not have permission to restore items.")
        return redirect("inventory:stock_list")

    if getattr(item, "is_active", True):
        messages.info(request, "Item is already active.")
        return redirect("inventory:stock_list")

    item.is_active = True
    item.save(update_fields=["is_active"])
    _audit(item, request.user, "RESTORE", f"Restored by {request.user.username} at {timezone.now():%Y-%m-%d %H:%M}.")
    messages.success(request, "Item restored.")
    return redirect("inventory:stock_list")


# -----------------------
# Auth placeholders
# -----------------------
@never_cache
def agent_forgot_password(request):
    return HttpResponse("Forgot password page – not implemented yet.")


@never_cache
def agent_reset_confirm(request, token=None):
    return HttpResponse(f"Reset confirm – token received: {token}")


# -----------------------
# Charts & analytics APIs
# -----------------------
@never_cache
@login_required
def api_sales_trend(request):
    # Tenant scope
    gate = _require_active_business(request)
    if gate:
        return gate
    _, biz_id = _get_active_business(request)

    period = request.GET.get("period", "month")
    metric = request.GET.get("metric", "amount")  # amount|count

    ver = get_dashboard_cache_version()
    key = f"api:sales_trend:v{ver}:biz:{biz_id or 'none'}:u{request.user.id}:p:{period}:m:{metric}"

    def _build():
        today = timezone.localdate()
        end_excl = today + timedelta(days=1)
        if period == "7d":
            start = today - timedelta(days=6)
        else:
            start = today.replace(day=1)

        base = _scoped(Sale.objects.all(), request)
        if not _can_view_all(request.user):
            base = base.filter(agent=request.user)

        qs = base.filter(sold_at__gte=start, sold_at__lt=end_excl).annotate(d=TruncDate("sold_at")).values("d").order_by("d")

        if metric == "count":
            agg = qs.annotate(v=Count("id"))
        else:
            agg = qs.annotate(v=Sum("price"))
        raw = {row["d"]: float(row["v"] or 0) for row in agg}

        labels, values = [], []
        cur = start
        while cur < end_excl:
            labels.append(cur.strftime("%b %d"))
            values.append(raw.get(cur, 0.0))
            cur += timedelta(days=1)
        return {"labels": labels, "values": values}

    data = cache.get(key)
    if data is None:
        data = _build()
        cache.set(key, data, 60)
    return JsonResponse(data)


@never_cache
@login_required
def api_top_models(request):
    # Tenant scope
    gate = _require_active_business(request)
    if gate:
        return gate
    _, biz_id = _get_active_business(request)

    period = request.GET.get("period", "today")
    ver = get_dashboard_cache_version()
    key = f"api:top_models:v{ver}:biz:{biz_id or 'none'}:u{request.user.id}:p:{period}"

    def _build():
        today = timezone.localdate()
        end_excl = today + timedelta(days=1)
        start = today if period == "today" else today.replace(day=1)

        base = _scoped(Sale.objects.select_related("item__product"), request)
        if not _can_view_all(request.user):
            base = base.filter(agent=request.user)

        qs = (
            base.filter(sold_at__gte=start, sold_at__lt=end_excl)
            .values("item__product__brand", "item__product__model")
            .annotate(c=Count("id"))
            .order_by("-c")[:8]
        )

        labels = [f'{r["item__product__brand"]} {r["item__product__model"]}' for r in qs]
        values = [r["c"] for r in qs]
        return {"labels": labels, "values": values}

    data = cache.get(key)
    if data is None:
        data = _build()
        cache.set(key, data, 60)
    return JsonResponse(data)


@never_cache
@login_required
def api_profit_bar(request):
    # Tenant scope
    gate = _require_active_business(request)
    if gate:
        return gate
    _, biz_id = _get_active_business(request)

    month_str = request.GET.get("month")
    group_by = request.GET.get("group_by")  # 'model' or None
    ver = get_dashboard_cache_version()
    key = f"api:profit_bar:v{ver}:biz:{biz_id or 'none'}:u:{request.user.id}:m:{month_str or 'curr'}:g:{group_by or 'none'}"

    def _build():
        today = timezone.localdate()
        if month_str:
            dt = datetime.strptime(month_str, "%Y-%m")
            start = dt.replace(day=1).date()
        else:
            start = today.replace(day=1)

        if month_str and (start.year != today.year or start.month != today.month):
            end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        else:
            end = today
        end_excl = end + timedelta(days=1)

        base = _scoped(Sale.objects.select_related("item__product"), request)
        if not _can_view_all(request.user):
            base = base.filter(agent=request.user)

        base = base.filter(sold_at__gte=start, sold_at__lt=end_excl)

        profit_expr = ExpressionWrapper(
            Coalesce(F("price"), Value(0)) - Coalesce(F("item__order_price"), Value(0)),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )

        if group_by == "model":
            rows = base.values("item__product__brand", "item__product__model").annotate(v=Sum(profit_expr)).order_by("-v")[:20]
            labels = [f"{r['item__product__brand']} {r['item__product__model']}" for r in rows]
            data = [float(r["v"] or 0) for r in rows]
        else:
            monthly = base.annotate(m=TruncMonth("sold_at")).values("m").annotate(v=Sum(profit_expr)).order_by("m")
            labels = [r["m"].strftime("%b %Y") for r in monthly]
            data = [float(r["v"] or 0) for r in monthly]

        return {"labels": labels, "data": data}

    data = cache.get(key)
    if data is None:
        data = _build()
        cache.set(key, data, 60)
    return JsonResponse(data)


@never_cache
@login_required
def api_agent_trend(request):
    # Tenant scope
    gate = _require_active_business(request)
    if gate:
        return gate
    _, biz_id = _get_active_business(request)

    months = int(request.GET.get("months", 6))
    metric = request.GET.get("metric", "sales")
    agent_id = request.GET.get("agent")
    ver = get_dashboard_cache_version()
    key = f"api:agent_trend:v{ver}:biz:{biz_id or 'none'}:u:{request.user.id}:mo:{months}:met:{metric}:a:{agent_id or 'all'}"

    def _build():
        base = _scoped(Sale.objects.select_related("agent", "item"), request)
        if not _can_view_all(request.user):
            base = base.filter(agent=request.user)
        if agent_id:
            base = base.filter(agent_id=agent_id)

        today = timezone.localdate()
        end_excl = today + timedelta(days=1)
        start = today - timedelta(days=months * 31)

        base = base.filter(sold_at__gte=start, sold_at__lt=end_excl)

        if metric == "profit":
            agg = Sum(Coalesce(F("price"), Value(0)) - Coalesce(F("item__order_price"), Value(0)))
        else:
            agg = Count("id")

        rows = base.annotate(m=TruncMonth("sold_at")).values("m").annotate(v=agg).order_by("m")

        labels = [r["m"].strftime("%b %Y") for r in rows]
        data = [float(r["v"] or 0) for r in rows]
        return {"labels": labels, "data": data}

    data = cache.get(key)
    if data is None:
        data = _build()
        cache.set(key, data, 60)
    return JsonResponse(data)


# -----------------------
# AI & Cash APIs (NEW)
# -----------------------
@never_cache
@login_required
@require_GET
def api_predictions(request):
    """
    Dashboard 'AI Recommendations' endpoint.

    Preferred path: delegate to inventory.api.predictions_summary (if available).
    Fallback: local baseline so the endpoint never 500s.
    """
    # Tenant gate
    gate = _require_active_business(request)
    if gate:
        return gate

    # ---- Preferred: reuse inventory/api.py implementation ----
    try:
        from . import api as _api  # lazy import
        if hasattr(_api, "predictions_summary") and callable(_api.predictions_summary):
            return _api.predictions_summary(request)
    except Exception:
        pass

    # ---- Fallback baseline (tenant-scoped) ----
    today = timezone.localdate()
    lookback_days = 14
    start = today - timedelta(days=lookback_days)
    end_excl = today + timedelta(days=1)

    sales = _scoped(Sale.objects.select_related("item__product"), request).filter(sold_at__gte=start, sold_at__lt=end_excl)
    items = _scoped(InventoryItem.objects.select_related("product"), request).filter(status="IN_STOCK")
    if not _can_view_all(request.user):
        sales = sales.filter(agent=request.user)
        items = items.filter(assigned_agent=request.user)

    # Per-day counts (last 14d)
    per_day_counts = sales.annotate(d=TruncDate("sold_at")).values("d").annotate(c=Count("id"))
    total_units_14 = sum(r["c"] for r in per_day_counts) or 0
    daily_units_avg = total_units_14 / float(lookback_days)

    # Per-day revenue (last 14d)
    per_day_rev = sales.annotate(d=TruncDate("sold_at")).values("d").annotate(v=Sum("price"))
    total_rev_14 = float(sum(r["v"] or 0 for r in per_day_rev))
    daily_rev_avg = total_rev_14 / float(lookback_days) if total_rev_14 else 0.0

    overall = [
        {
            "date": (today + timedelta(days=i)).isoformat(),
            "predicted_units": round(daily_units_avg, 2),
            "predicted_revenue": round(daily_rev_avg, 2),
        }
        for i in range(1, 8)
    ]

    # Model-level stockout risk
    by_model_14 = sales.values("item__product_id", "item__product__brand", "item__product__model").annotate(c=Count("id"))
    model_count_map = {r["item__product_id"]: r["c"] for r in by_model_14}

    risky = []
    by_model_stock = (
        items.values("product_id", "product__brand", "product__model")
        .annotate(on_hand=Count("id"))
        .order_by("product__brand", "product__model")
    )
    for r in by_model_stock:
        pid = r["product_id"]
        daily_model_avg = (model_count_map.get(pid, 0) / float(lookback_days)) if pid in model_count_map else 0.0
        need_next_7 = daily_model_avg * 7.0
        on_hand = int(r["on_hand"] or 0)
        if daily_model_avg > 0 and on_hand < need_next_7:
            days_cover = (on_hand / daily_model_avg) if daily_model_avg else 0
            risky.append({
                "product": f'{r["product__brand"]} {r["product__model"]}',
                "on_hand": on_hand,
                "stockout_date": (today + timedelta(days=max(0, int(days_cover)))).isoformat(),
                "suggested_restock": int(round(max(0.0, need_next_7 - on_hand))),
                "urgent": on_hand <= (daily_model_avg * 2.0),
            })

    return JsonResponse({"ok": True, "overall": overall, "risky": risky})


@never_cache
@login_required
@require_GET
def api_cash_overview(request):
    """
    Totals for 'Cash' slide.
    - total_orders (current month)
    - total_revenue (current month)
    - total_paid_out (Wallet Payouts, current month)
    - total_expenses (Advances + Adjustments, current month)
    """
    # Tenant scope
    gate = _require_active_business(request)
    if gate:
        return gate

    today = timezone.localdate()
    start = today.replace(day=1)
    end_excl = today + timedelta(days=1)

    sales = _scoped(Sale.objects.filter(sold_at__gte=start, sold_at__lt=end_excl), request)
    if not _can_view_all(request.user):
        sales = sales.filter(agent=request.user)

    dec2 = DecimalField(max_digits=14, decimal_places=2)
    totals = sales.aggregate(
        orders=Count("id"),
        revenue=Coalesce(Sum("price"), Value(0), output_field=dec2),
    )

    if WalletTxn is not None:
        tx = _scoped(WalletTxn.objects.filter(created_at__date__gte=start, created_at__date__lte=today), request)  # type: ignore[union-attr]
        if not _can_view_all(request.user):
            tx = tx.filter(user=request.user)
        paid_out = tx.filter(reason="PAYOUT").aggregate(s=Coalesce(Sum("amount"), Value(0)))["s"] or 0
        advances = tx.filter(reason="ADVANCE").aggregate(s=Coalesce(Sum("amount"), Value(0)))["s"] or 0
        adjustments = tx.filter(reason="ADJUSTMENT").aggregate(s=Coalesce(Sum("amount"), Value(0)))["s"] or 0
    else:
        paid_out = advances = adjustments = 0

    data = {
        "orders": int(totals.get("orders") or 0),
        "revenue": float(totals.get("revenue") or 0),
        "paid_out": float(paid_out or 0),
        "expenses": float((advances or 0) + (adjustments or 0)),
        "period_label": start.strftime("%b %Y"),
    }
    return JsonResponse({"ok": True, **data})


# -----------------------
# Alerts API (NEW for UI)
# -----------------------
@never_cache
@login_required
@require_GET
def api_alerts(request):
    """
    Provides alert items for the Dashboard 'Stock Alerts' card.

    Response:
      {"ok": true, "alerts": [
        {"type": "Low stock", "severity": "high|warn|info", "message": "..."}
      ]}
    """
    # Tenant scope
    gate = _require_active_business(request)
    if gate:
        return gate

    alerts = []
    today = timezone.localdate()

    items_qs = _scoped(InventoryItem.objects.select_related("product", "current_location"), request)
    sales_qs = _scoped(Sale.objects.select_related("item__product"), request)
    if not _can_view_all(request.user):
        items_qs = items_qs.filter(assigned_agent=request.user)
        sales_qs = sales_qs.filter(agent=request.user)

    # 1) Low stock by model
    low_rows = (
        items_qs.filter(status="IN_STOCK")
        .values("product__brand", "product__model")
        .annotate(on_hand=Count("id"))
        .order_by("on_hand")[:10]
    )
    for r in low_rows:
        on_hand = int(r["on_hand"] or 0)
        if on_hand <= 3:
            sev = "high" if on_hand <= 1 else "warn"
            product_name = f'{r["product__brand"]} {r["product__model"]}'.strip()
            alerts.append({
                "type": "Low stock",
                "severity": sev,
                "message": f"{product_name}: only {on_hand} on hand.",
            })

    # 2) Unpriced SOLD items (recent)
    recent_unpriced = sales_qs.filter(Q(price__isnull=True) | Q(price__lte=0), sold_at__gte=today - timedelta(days=30)).count()
    if recent_unpriced:
        alerts.append({
            "type": "Pricing",
            "severity": "warn",
            "message": f"{recent_unpriced} sold item(s) with missing/zero price in last 30 days.",
        })

    # 3) Stale stock (older than 45 days)
    stale_count = items_qs.filter(status="IN_STOCK", received_at__lt=today - timedelta(days=45)).count()
    if stale_count:
        alerts.append({
            "type": "Aging stock",
            "severity": "info",
            "message": f"{stale_count} item(s) in stock for 45+ days.",
        })

    # 4) Negative wallet balance (current user; tenant-scoped if WalletTxn present)
    try:
        if WalletTxn is not None:
            bal = float(_scoped(WalletTxn.objects.filter(user=request.user), request).aggregate(s=Sum("amount"))["s"] or 0)  # type: ignore[union-attr]
        else:
            bal = float(_wallet_balance(request.user))
        if bal < 0:
            alerts.append({
                "type": "Wallet",
                "severity": "warn",
                "message": f"Your wallet balance is negative: MK {abs(int(bal)):,}.",
            })
    except Exception:
        pass

    return JsonResponse({"ok": True, "alerts": alerts})


# -----------------------
# Manager-only: Dashboard CSV export
# -----------------------
@never_cache
@login_required
@require_http_methods(["GET"])
def dashboard_export_csv(request):
    """
    Exports the key dashboard datasets into a single CSV file (sectioned).
    Manager-only.
    """
    # Tenant scope
    gate = _require_active_business(request)
    if gate:
        return gate

    if not _is_manager_or_admin(request.user):
        return JsonResponse({"ok": False, "error": "Manager only."}, status=403)

    # Rebuild the main dashboard datasets with current query params
    period = request.GET.get("period", "month")
    model_id = request.GET.get("model") or None
    today = timezone.localdate()
    month_start = today.replace(day=1)

    # Scope
    sales_qs_all = _scoped(Sale.objects.select_related("item", "agent", "item__product"), request)
    items_qs = _scoped(InventoryItem.objects.select_related("product", "assigned_agent", "current_location"), request)
    if model_id:
        sales_qs_all = sales_qs_all.filter(item__product_id=model_id)
        items_qs = items_qs.filter(product_id=model_id)

    sales_qs_period = sales_qs_all.filter(sold_at__gte=month_start) if period == "month" else sales_qs_all

    # KPIs
    tomorrow = today + timedelta(days=1)
    kpi_today = sales_qs_all.filter(sold_at__gte=today, sold_at__lt=tomorrow).count()
    kpi_mtd = sales_qs_all.filter(sold_at__gte=month_start, sold_at__lt=tomorrow).count()
    kpi_all = sales_qs_all.count()

    # Agent ranking + wallet
    dec2 = DecimalField(max_digits=14, decimal_places=2)
    pct_dec = DecimalField(max_digits=5, decimal_places=2)
    commission_pct_dec = Cast(F("commission_pct"), pct_dec)
    commission_expr = ExpressionWrapper(
        Coalesce(F("price"), Value(0), output_field=dec2) *
        (Coalesce(commission_pct_dec, Value(0), output_field=pct_dec) / Value(100, output_field=pct_dec)),
        output_field=dec2,
    )
    rank_base = _scoped(Sale.objects.select_related("agent"), request)
    if model_id:
        rank_base = rank_base.filter(item__product_id=model_id)
    if period == "month":
        rank_base = rank_base.filter(sold_at__gte=month_start)
    agent_rank = list(
        rank_base.values("agent_id", "agent__username")
        .annotate(
            total_sales=Count("id"),
            earnings=Coalesce(Sum(commission_expr), Value(0), output_field=dec2),
            revenue=Coalesce(Sum("price"), Value(0), output_field=dec2),
        )
        .order_by("-earnings", "-total_sales", "agent__username")
    )
    # Wallet balances (scoped)
    agent_wallet_map = {}
    if agent_rank and WalletTxn is not None:
        ids = [r["agent_id"] for r in agent_rank if r.get("agent_id")]
        w = _scoped(WalletTxn.objects.filter(user_id__in=ids), request).values("user_id").annotate(balance=Sum("amount"))  # type: ignore[union-attr]
        agent_wallet_map = {r["user_id"]: float(r["balance"] or 0) for r in w}
    for r in agent_rank:
        r["wallet_balance"] = agent_wallet_map.get(r.get("agent_id"), 0.0)

    # Agent stock vs sold
    total_assigned = (
        items_qs.values("assigned_agent_id", "assigned_agent__username")
        .annotate(total_stock=Count("id"))
        .order_by("assigned_agent__username")
    )
    sold_units = sales_qs_period.values("agent_id").annotate(sold=Count("id"))
    sold_map = {r["agent_id"]: r["sold"] for r in sold_units}
    agent_rows = [
        {
            "agent_id": row["assigned_agent_id"],
            "agent": row["assigned_agent__username"] or "—",
            "total_stock": row["total_stock"],
            "sold_units": sold_map.get(row["assigned_agent_id"], 0),
        }
        for row in total_assigned
    ]

    # 12 months revenue/profit
    def back_n_months(d: date, n: int) -> date:
        y = d.year
        m = d.month - n
        while m <= 0:
            m += 12
            y -= 1
        return date(y, m, 1)
    labels = [back_n_months(month_start, n).strftime("%Y-%m") for n in range(11, -1, -1)]
    rev_qs = _scoped(Sale.objects.select_related("item"), request).filter(sold_at__gte=back_n_months(month_start, 11))
    if model_id:
        rev_qs = rev_qs.filter(item__product_id=model_id)
    rev_by_month = (
        rev_qs.annotate(m=TruncMonth("sold_at")).values("m")
        .annotate(total=Coalesce(Sum("price"), Value(0), output_field=dec2))
        .order_by("m")
    )
    totals_map = {r["m"].strftime("%Y-%m"): float(r["total"] or 0) for r in rev_by_month if r["m"]}
    profit_expr_month = ExpressionWrapper(
        Coalesce(F("price"), Value(0), output_field=dec2) -
        Coalesce(F("item__order_price"), Value(0), output_field=dec2),
        output_field=dec2,
    )
    prof_by_month = (
        rev_qs.annotate(m=TruncMonth("sold_at")).values("m")
        .annotate(total=Coalesce(Sum(profit_expr_month), Value(0), output_field=dec2))
        .order_by("m")
    )
    prof_map = {r["m"].strftime("%Y-%m"): float(r["total"] or 0) for r in prof_by_month if r["m"]}

    # Pie summary (period)
    totals = sales_qs_period.aggregate(
        revenue=Coalesce(Sum("price"), Value(0), output_field=dec2),
        cost=Coalesce(Sum(Coalesce(F("item__order_price"), Value(0), output_field=dec2)), Value(0), output_field=dec2),
        profit=Coalesce(Sum(profit_expr_month), Value(0), output_field=dec2),
    )

    # ---- Write CSV ----
    filename = f"dashboard_export_{timezone.now():%Y%m%d_%H%M}.csv"
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp["Pragma"] = "no-cache"
    resp.write("\ufeff")  # Excel BOM
    w = csv.writer(resp)

    # Section 1: KPIs
    w.writerow(["# Dashboard KPIs"])
    w.writerow(["period", period])
    w.writerow(["model_id", model_id or "all"])
    w.writerow(["today_count", kpi_today])
    w.writerow(["mtd_count", kpi_mtd])
    w.writerow(["all_time_count", kpi_all])
    w.writerow([])

    # Section 2: Leaderboard
    w.writerow(["# Top Agents (wallet_balance desc, then earnings desc, sales desc)"])
    w.writerow(["Agent", "Earnings", "Sales", "Revenue", "WalletBalance"])
    agent_rank.sort(key=lambda r: (r.get("wallet_balance", 0.0), float(r.get("earnings") or 0.0), int(r.get("total_sales") or 0)), reverse=True)
    for r in agent_rank:
        w.writerow([
            r["agent__username"],
            f'{float(r["earnings"] or 0):.2f}',
            int(r["total_sales"] or 0),
            f'{float(r["revenue"] or 0):.2f}',
            f'{float(r.get("wallet_balance", 0.0)):.2f}',
        ])
    w.writerow([])

    # Section 3: Agent stock vs sold
    w.writerow(["# Agent Stock vs Sold Units"])
    w.writerow(["Agent", "TotalStock", f'SoldUnits ({ "this month" if period=="month" else "all time" })'])
    for r in agent_rows:
        w.writerow([r["agent"], int(r["total_stock"] or 0), int(r["sold_units"] or 0)])
    w.writerow([])

    # Section 4: Revenue/Profit 12 months
    w.writerow(["# Revenue and Profit (last 12 months)"])
    w.writerow(["Month", "Revenue", "Profit"])
    for lbl in labels:
        w.writerow([lbl, f'{float(totals_map.get(lbl, 0.0)):.2f}', f'{float(prof_map.get(lbl, 0.0)):.2f}'])
    w.writerow([])

    # Section 5: Cost vs Revenue vs Profit (current selection)
    w.writerow(["# Cost vs Revenue vs Profit (current selection)"])
    w.writerow(["Cost", "Revenue", "Profit"])
    w.writerow([f'{float(totals.get("cost") or 0):.2f}', f'{float(totals.get("revenue") or 0):.2f}', f'{float(totals.get("profit") or 0):.2f}'])

    return resp


# -----------------------
# Health check (Render)
# -----------------------
@never_cache
@require_http_methods(["GET"])
def healthz(request):
    ok = True
    err = None
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
    except Exception as e:
        ok = False
        err = str(e)
    payload = {"ok": ok, "time": timezone.now().isoformat()}
    if err:
        payload["error"] = err
    return JsonResponse(payload, status=200 if ok else 500)


# -----------------------
# Restock Heatmap API (manager-aware; agents get scoped view)
# -----------------------
@never_cache
@login_required
@require_GET
def restock_heatmap_api(request):
    """
    Returns heatmap-style restock suggestions and a stock 'battery' percentage.

    Manager/Admin  -> whole org (all products/locations), battery cap=100
    Agent          -> only own stock/sales, battery cap=20
    """
    # Tenant scope
    gate = _require_active_business(request)
    if gate:
        return gate

    mode_manager = _is_manager_or_admin(request.user)
    window_days = int(request.GET.get("days", 30) or 30)
    window_days = max(7, min(window_days, 90))
    today = timezone.localdate()
    start = today - timedelta(days=window_days)
    end_excl = today + timedelta(days=1)

    items_qs = _scoped(InventoryItem.objects.select_related("product", "current_location"), request).filter(status="IN_STOCK")
    sales_qs = _scoped(Sale.objects.select_related("item__product", "location").filter(sold_at__gte=start, sold_at__lt=end_excl), request)
    if not mode_manager:
        items_qs = items_qs.filter(assigned_agent=request.user)
        sales_qs = sales_qs.filter(agent=request.user)

    battery_cap = 100 if mode_manager else 20

    # Battery
    battery_count = items_qs.count()
    battery_pct = int(round(min(100.0, (battery_count / float(battery_cap)) * 100))) if battery_count else 0

    # On-hand by (product, location)
    onhand_rows = items_qs.values(
        "product_id", "product__brand", "product__model", "current_location_id", "current_location__name"
    ).annotate(on_hand=Count("id"))

    onhand_map = {}
    for r in onhand_rows:
        key = (r["product_id"], r["current_location_id"])
        onhand_map[key] = {
            "product_id": r["product_id"],
            "product": f'{r["product__brand"]} {r["product__model"]}'.strip(),
            "location_id": r["current_location_id"],
            "location": r["current_location__name"] or "—",
            "on_hand": int(r["on_hand"] or 0),
        }

    # Sold last N days by (product, location)
    sold_rows = sales_qs.values(
        "item__product_id", "item__product__brand", "item__product__model", "location_id", "location__name"
    ).annotate(sold_30d=Count("id"))

    combos = {}
    for k, v in onhand_map.items():
        combos[k] = {**v, "sold_30d": 0}
    for r in sold_rows:
        key = (r["item__product_id"], r["location_id"])
        prod_name = f'{r["item__product__brand"]} {r["item__product__model"]}'.strip()
        if key not in combos:
            combos[key] = {
                "product_id": r["item__product_id"],
                "product": prod_name,
                "location_id": r["location_id"],
                "location": r["location__name"] or "—",
                "on_hand": 0,
                "sold_30d": 0,
            }
        combos[key]["sold_30d"] = int(r["sold_30d"] or 0)

    # Compute burn, cover, risk
    heatmap = []
    eps = 1e-9
    for (_pid, _loc), row in combos.items():
        sold_30d = int(row["sold_30d"] or 0)
        on_hand = int(row["on_hand"] or 0)
        burn = sold_30d / float(window_days) if sold_30d > 0 else 0.0
        need_next_7 = burn * 7.0
        days_cover = (on_hand / (burn + eps)) if burn > 0 else None

        if need_next_7 <= eps:
            risk = 0
        else:
            deficit = max(0.0, need_next_7 - on_hand)
            risk = int(round(min(100.0, (deficit / need_next_7) * 100.0)))

        heatmap.append({
            "product_id": row["product_id"],
            "product": row["product"],
            "location_id": row["location_id"],
            "location": row["location"],
            "on_hand": on_hand,
            "sold_30d": sold_30d,
            "burn_rate_per_day": round(burn, 3),
            "need_next_7": int(round(need_next_7)),
            "days_cover": (round(days_cover, 1) if days_cover is not None else None),
            "risk_score": risk,
        })

    heatmap.sort(key=lambda x: (x["risk_score"], (x["need_next_7"] - x["on_hand"])), reverse=True)

    # Top products across locations
    prod_totals = {}
    for row in heatmap:
        pid = row["product_id"]
        if pid not in prod_totals:
            prod_totals[pid] = {"product_id": pid, "product": row["product"], "sold_30d": 0, "on_hand": 0}
        prod_totals[pid]["sold_30d"] += row["sold_30d"]
        prod_totals[pid]["on_hand"]  += row["on_hand"]

    top_products = []
    for p in prod_totals.values():
        burn = p["sold_30d"] / float(window_days) if p["sold_30d"] > 0 else 0.0
        need7 = burn * 7.0
        if need7 <= eps:
            risk = 0
        else:
            deficit = max(0.0, need7 - p["on_hand"])
            risk = int(round(min(100.0, (deficit / need7) * 100.0)))
        top_products.append({**p, "risk_score": risk})

    top_products.sort(key=lambda r: (r["risk_score"], r["sold_30d"]), reverse=True)
    top_products = top_products[:20]

    return JsonResponse({
        "ok": True,
        "mode": "manager" if mode_manager else "agent",
        "window_days": window_days,
        "generated_at": timezone.now().isoformat(),
        "battery_pct": battery_pct,
        "battery_count": battery_count,
        "battery_cap": battery_cap,
        "heatmap": heatmap,
        "top_products": top_products,
    })


# =======================
# NEW: Stock List helpers for Admin Wallet
# =======================

@never_cache
@login_required
@require_GET
def api_order_price(request, product_id: int):
    """
    Returns the default order price for a product (used to auto-fill Scan IN).
    Source of truth: Product.cost_price
    Response: {"ok": true, "product_id": 1, "price": "12345.00"}
    """
    gate = _require_active_business(request)
    if gate:
        return gate

    try:
        p = _scoped(Product.objects.only("id", "cost_price"), request).get(pk=int(product_id))
    except (Product.DoesNotExist, ValueError):
        return JsonResponse({"ok": False, "error": "Unknown product."}, status=404)
    price = p.cost_price or 0
    return JsonResponse({"ok": True, "product_id": p.id, "price": str(price)})


@never_cache
@login_required
@require_GET
def api_stock_models(request):
    """
    Compact list of product models in stock with on-hand counts.
    Response: {"ok":true, "models":[{"product_id":1,"product":"Brand Model Variant","on_hand":5,"default_price":"100000.00"}]}
    """
    gate = _require_active_business(request)
    if gate:
        return gate

    qs = (
        _scoped(InventoryItem.objects.filter(status="IN_STOCK"), request)
        .values("product_id", "product__brand", "product__model", "product__variant", "product__cost_price")
        .annotate(on_hand=Count("id"))
        .order_by("product__brand", "product__model", "product__variant")
    )
    models = []
    for r in qs:
        name = " ".join([r.get("product__brand") or "", r.get("product__model") or "", r.get("product__variant") or ""]).strip()
        models.append({
            "product_id": r["product_id"],
            "product": name,
            "on_hand": int(r["on_hand"] or 0),
            "default_price": str(r.get("product__cost_price") or "0.00"),
        })
    return JsonResponse({"ok": True, "models": models})


@never_cache
@login_required
@otp_required
@require_POST
@transaction.atomic
def api_place_order(request):
    gate = _require_active_business(request)
    if gate:
        return gate
    _, biz_id = _get_active_business(request)

    if not _is_manager_or_admin(request.user):
        return JsonResponse({"ok": False, "error": "Manager/Admin only."}, status=403)
    if AdminPurchaseOrder is None or AdminPurchaseOrderItem is None:
        return JsonResponse({"ok": False, "error": "Purchase Order models not installed."}, status=500)

    try:
        payload = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON."}, status=400)

    items = payload.get("items") or []
    if not isinstance(items, list) or not items:
        return JsonResponse({"ok": False, "error": "Provide at least one item."}, status=400)

    po = AdminPurchaseOrder.objects.create(
        created_by=request.user,
        supplier_name=(payload.get("supplier_name") or "").strip()[:120],
        supplier_email=(payload.get("supplier_email") or "").strip()[:254],
        supplier_phone=(payload.get("supplier_phone") or "").strip()[:40],
        agent_name=(payload.get("agent_name") or "").strip()[:120],
        notes=(payload.get("notes") or "").strip(),
        currency=getattr(settings, "DEFAULT_CURRENCY", "MWK"),
        **_attach_business_kwargs(AdminPurchaseOrder, biz_id),
    )

    prod_ids = [it.get("product_id") for it in items if it.get("product_id") is not None]
    prod_map = {p.id: p for p in _scoped(Product.objects.filter(id__in=prod_ids), request)}
    created_any = False
    for it in items:
        try:
            pid = int(it.get("product_id"))
            qty = int(it.get("quantity"))
        except Exception:
            return JsonResponse({"ok": False, "error": "Bad product_id/quantity."}, status=400)
        if qty <= 0 or pid not in prod_map:
            return JsonResponse({"ok": False, "error": f"Invalid item: product={pid}, qty={qty}."}, status=400)

        prod = prod_map[pid]
        unit = None
        if "unit_price" in it and it["unit_price"] is not None:
            try:
                unit = float(it["unit_price"])
                if unit < 0:
                    raise ValueError()
            except Exception:
                return JsonResponse({"ok": False, "error": f"Invalid unit_price for product {pid}."}, status=400)
        if unit is None:
            unit = float(prod.cost_price or 0)

        line_total = (unit or 0) * qty
        AdminPurchaseOrderItem.objects.create(
            po=po, product=prod, quantity=qty, unit_price=unit, line_total=line_total, **_attach_business_kwargs(AdminPurchaseOrderItem, biz_id)
        )
        created_any = True

    if not created_any:
        po.delete()
        return JsonResponse({"ok": False, "error": "No valid items."}, status=400)

    po.recompute_totals(save=True)

    invoice_url = reverse("inventory:po_invoice", args=[po.id])
    subject = quote(f"Purchase Order PO-{po.id}")
    body_lines = [
        f"PO-{po.id} · Total {po.total} {po.currency}",
        f"Supplier: {po.supplier_name or '-'}",
        f"Agent: {po.agent_name or '-'}",
        "", "Items:",
    ]
    for ln in po.items.select_related("product").all():
        body_lines.append(f" - {ln.product} × {ln.quantity} @ {ln.unit_price} = {ln.line_total}")
    body_lines.append("")
    body_lines.append(f"Download invoice: {request.build_absolute_uri(invoice_url)}")
    body = quote("\n".join(body_lines))
    mailto = f"mailto:{quote((po.supplier_email or ''))}?subject={subject}&body={body}"
    whatsapp = f"https://wa.me/?text={body}"

    return JsonResponse({"ok": True, "po_id": po.id, "invoice_url": invoice_url,
                         "share": {"email": mailto, "whatsapp": whatsapp}})


@never_cache
@login_required
@otp_required
@require_GET
def po_invoice(request, po_id: int):
    """
    Simple downloadable HTML invoice for a PO. Manager/Admin only.
    """
    if AdminPurchaseOrder is None:
        return HttpResponse("PO model missing.", status=500)

    if not _is_manager_or_admin(request.user):
        return HttpResponse("Manager/Admin only.", status=403)

    # Tenant-scoped fetch
    po = get_object_or_404(_scoped(AdminPurchaseOrder.objects.select_related("created_by"), request), pk=int(po_id))
    lines = list(po.items.select_related("product").all())

    rows_html = "".join(
        f"<tr><td>{i+1}</td><td>{ln.product}</td><td style='text-align:right'>{ln.quantity}</td>"
        f"<td style='text-align:right'>{ln.unit_price:.2f}</td><td style='text-align:right'>{ln.line_total:.2f}</td></tr>"
        for i, ln in enumerate(lines)
    )

    html = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>PO-{po.id}</title>
<style>
body{{font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;background:#fff;margin:24px;color:#0f172a}}
.h{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px}}
.table{{width:100%;border-collapse:collapse;margin-top:8px}}
.table th,.table td{{border:1px solid #e5e7eb;padding:8px;font-size:14px}}
.table th{{background:#f3f4f6;text-align:left}}
.total{{text-align:right;margin-top:12px}}
.badge{{display:inline-block;padding:.1rem .4rem;border-radius:.4rem;background:#eef2ff;border:1px solid #dbeafe}}
.small{{font-size:12px;opacity:.8}}
</style>
</head><body>
<div class="h">
  <div>
    <h2 style="margin:0">Purchase Order <span class="badge">PO-{po.id}</span></h2>
    <div class="small">Created: {po.created_at:%Y-%m-%d %H:%M}</div>
    <div class="small">By: {getattr(po.created_by, 'username', '—')}</div>
  </div>
  <div>
    <div><strong>Supplier</strong>: {po.supplier_name or '—'}</div>
    <div><strong>Email</strong>: {po.supplier_email or '—'}</div>
    <div><strong>Phone</strong>: {po.supplier_phone or '—'}</div>
    <div><strong>Agent</strong>: {po.agent_name or '—'}</div>
  </div>
</div>

<table class="table">
  <thead><tr><th>#</th><th>Product</th><th style='text-align:right'>Qty</th><th style='text-align:right'>Unit</th><th style='text-align:right'>Line total</th></tr></thead>
  <tbody>{rows_html or '<tr><td colspan="5">No items.</td></tr>'}</tbody>
</table>

<div class="total">
  <div>Subtotal: <strong>{po.subtotal:.2f} {po.currency}</strong></div>
  <div>Tax: <strong>{po.tax:.2f} {po.currency}</strong></div>
  <div style="font-size:18px">TOTAL: <strong>{po.total:.2f} {po.currency}</strong></div>
</div>

<div style="margin-top:12px"><strong>Notes:</strong><br/>{(po.notes or '').replace('<','&lt;').replace('>','&gt;')}</div>
</body></html>"""

    resp = HttpResponse(html, content_type="text/html; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="PO_{po.id}.html"'
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp["Pragma"] = "no-cache"
    return resp
# --- PART 3/3 ENDS ---

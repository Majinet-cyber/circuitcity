#--- PART 1/3 START (inventory/views.py) ---# --- PART 1/3 â€” circuitcity/inventory/views.py ---

from __future__ import annotations
from django.contrib import messages
from .models import BusinessKind
from django.shortcuts import render, redirect
from django.urls import reverse
from .utils import get_invite_token, invite_join_url
from .forms import MerchProductForm, MerchUnitPriceFormSet
import logging

import csv
import json
import logging
import math
# ------------------------------
# Helpers (keep above all views)
# ------------------------------
def _wants_json(request):
    """Return True only if JSON was explicitly requested."""
    if request.GET.get("as") == "json":
        return True
    return request.headers.get("x-requested-with") == "XMLHttpRequest"
from django.urls import reverse
from .forms import MerchProductForm, MerchUnitPriceFormSet
from .forms import MerchProductForm, MerchUnitPriceFormSet
from functools import wraps
from urllib.parse import urlencode
from .api import predictions_summary as api_predictions
from django.utils.translation import gettext as _
from decimal import Decimal
from datetime import datetime, timedelta, date, time  # NOTE: keep 'time' for wallet calc in Part 2
# ORM bits for subqueries/annotations
from django.db.models import Q, OuterRef, Subquery, Exists, Value, BooleanField
# --- Safe, module-level binding so functions can read Sale without shadowing
try:
    from sales.models import Sale as Sale  # noqa: F401
except Exception:
    Sale = None  # type: ignore
    # ----- Optional Sales models (Order / OrderItem) -------------------
    try:
        from sales.models import Order, OrderItem  # type: ignore
    except Exception:
        Order = None  # type: ignore[assignment]
        OrderItem = None  # type: ignore[assignment]

from datetime import datetime, timedelta, time as dtime
from django.utils import timezone
from tenants.utils import require_business, require_role
from django.conf import settings
from django.contrib import messages
from django.shortcuts import render
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import IntegrityError, transaction, connection
from django.db.models import Sum, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.exceptions import TemplateDoesNotExist
from django.urls import reverse
from django.utils import timezone
from django.http import JsonResponse
from .models import InventoryItem
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_http_methods

# === HOTFIX: active business + default location helpers (non-breaking) ========
# (Additive only; does not replace your existing helpers. Double-underscore
#  names avoid collisions. The decorator is defined here so it's available
#  before it is used further down in the file.)
from functools import wraps as _wraps_hotfix
# --- add near the top of inventory/views.py (after imports) ---

from django.views.decorators.http import require_http_methods

try:
    # Prefer your existing helpers if present
    from tenants.utils import get_active_business  # or circuitcity.tenants.utils
except Exception:
    get_active_business = None

# If you have a Location model in tenants (or inventory) import it:
try:
    from tenants.models import Location
except Exception:
    Location = None

# --- Header counters computed from the single source of truth ---
from decimal import Decimal
from django.db.models import Sum
from django.db.models.functions import Coalesce

# if not already imported:
from .scope import stock_queryset_for_request, active_scope, get_inventory_model

def _inventory_header_stats(request):
    """
    Returns dict with counters for the four header badges, computed
    from the same queryset as the table so numbers always match.
    """
    Model = get_inventory_model()
    if Model is None:
        return {"in_stock_count": 0, "sold_count": 0,
                "sum_order": Decimal("0.00"), "sum_selling": Decimal("0.00")}

    # 1) "In stock" and sums are from the canonical stock queryset
    qs = stock_queryset_for_request(request)

    sums = qs.aggregate(
        sum_order=Coalesce(Sum("order_price"), Decimal("0.00")),
        sum_selling=Coalesce(Sum("selling_price"), Decimal("0.00")),
    )
    in_stock_count = qs.count()

    # 2) "Sold" uses the same business/location scope, but with 'sold' filter
    biz_id, loc_id = active_scope(request)
    base = getattr(Model, "_base_manager", Model.objects).all()

    # scope by business
    try:
        if biz_id is not None:
            try:
                base = base.filter(business_id=biz_id)
            except Exception:
                base = base.filter(business__id=biz_id)
    except Exception:
        pass

    # scope by location (prefer current_location)
    try:
        loc_fields = {f.name for f in Model._meta.get_fields()}
    except Exception:
        loc_fields = set()
    if loc_id is not None:
        for fk in ("current_location", "location", "store", "branch"):
            if fk in loc_fields or f"{fk}_id" in loc_fields:
                try:
                    base = base.filter(**{f"{fk}_id": loc_id})
                except Exception:
                    base = base.filter(**{fk: loc_id})
                break

    # sold filter (cover common schemas)
    if "sold_at" in loc_fields:
        sold_qs = base.exclude(sold_at__isnull=True)
    elif "status" in loc_fields:
        sold_qs = base.filter(status__iexact="sold")
    elif "available" in loc_fields:
        sold_qs = base.filter(available=False)
    else:
        sold_qs = base.none()

    sold_count = sold_qs.count()

    # expose with multiple keys to be template-friendly
    return {
        "in_stock": in_stock_count,
        "in_stock_count": in_stock_count,
        "sold": sold_count,
        "sold_count": sold_count,
        "sum_order": sums["sum_order"] or Decimal("0.00"),
        "sum_selling": sums["sum_selling"] or Decimal("0.00"),
    }
# --- Add if these imports are not already present ---
  # TextChoices you added (PHARMACY, PHONES, LIQUOR, etc.)

def _detect_kind(business: Business) -> str | None:
    """
    Return a normalized business kind string that matches BusinessKind values.
    Tries a few common field names on your Business model.
    """
    if not business:
        return None
    for attr in ("kind", "business_kind", "industry", "category", "type"):
        val = getattr(business, attr, None)
        if val:
            return str(val)
    return None

@login_required
def merch_add_router(request):
    """
    One URL that decides WHICH 'Add Products' form to render based on the active business.
    """
    biz = getattr(request, "business", None)
    if not biz:
        # No active business selected â†’ send user to chooser
        return redirect("tenants:choose_business")

    kind = _detect_kind(biz)

    # Map business kind â†’ template
    template_map = {
        BusinessKind.PHARMACY: "inventory/add_product_pharmacy.html",
        BusinessKind.PHONES:   "inventory/add_product_phones.html",
        BusinessKind.LIQUOR:   "inventory/add_product_liquor.html",
        # If you have a separate TextChoice for clothing, add it; otherwise treat as 'grocery' fallback
        "clothing":            "inventory/add_product_clothing.html",
        BusinessKind.GROCERY:  "inventory/add_product_clothing.html",  # change if you have a dedicated grocery template
    }

    template = template_map.get(kind) or "inventory/add_product_clothing.html"

    ctx = {
        "page_title": "Add Products",
        "business": biz,
        "BUSINESS_KIND": kind,
    }
    return render(request, template, ctx)

def _ensure_active_business_and_location(request):
    """
    Ensure request has an active business (and pick a default location).
    - If user has exactly one membership, pick it (your URL shim already tries this,
      but this makes the view self-contained).
    - Pick active_location if set; else first active Location for the business.
    Returns (business, location) or (None, None) if not resolvable.
    """
    biz = getattr(request, "active_business", None)
    loc = getattr(request, "active_location", None)

    # Try central helper if available
    if not biz and callable(get_active_business):
        try:
            biz = get_active_business(request)
        except Exception:
            biz = None

    # Fallback: single membership auto-select (mirrors your cc.urls logic)
    if not biz:
        try:
            from tenants.models import BusinessMembership, Business  # noqa
            qs = BusinessMembership.objects.filter(user=request.user)
            for f in ("is_active", "active", "accepted"):
                if f in [fld.name for fld in BusinessMembership._meta.fields]:
                    try:
                        qs = qs.filter(**{f: True})
                    except Exception:
                        pass
            if qs.count() == 1:
                m = qs.first()
                biz = getattr(m, "business", None)
                if biz:
                    request.active_business = biz
                    request.session["active_business_id"] = getattr(biz, "id", None)
                    request.session["biz_id"] = getattr(biz, "id", None)
        except Exception:
            pass

    # Choose a location automatically if missing
    if biz and not loc and Location:
        try:
            loc = Location.objects.filter(business=biz, is_active=True).order_by("name").first()
            if loc:
                request.active_location = loc
                request.active_location_id = getattr(loc, "id", None)
        except Exception:
            pass

    return biz, loc


# --- Example: Scan IN view (adapt to your projectâ€™s view name) ---

# --- Example: Scan SOLD view gets the same treatment ---

# ---------------- Business/Store auto-select helpers ----------------
from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone
def _resolve_default_location_id(request):
    """
    Returns a location id to use when nothing is chosen yet:
      1) session['active_location_id']
      2) request.user.agent_profile.location_id (if present)
      3) business default (if present)
      4) first Location id for this business
    """
    # 1) session
    sid = request.session.get("active_location_id")
    if sid:
        return sid

    # 2) agent home
    try:
        ap = getattr(request.user, "agent_profile", None)
        if ap and ap.location_id:
            return ap.location_id
    except Exception:
        pass

    # 3) business default, then 4) first for business
    try:
        biz = getattr(request, "business", None) or getattr(request, "active_business", None)
        if biz:
            default = Location.default_for(biz.id)
            if default:
                return default.id
    except Exception:
        pass

    # Last fallback: any location at all
    first = Location.objects.values_list("id", flat=True).first()
    if first:
        return first
    return None


def with_active_location(view):
    """Decorator: sets request.active_location(_id) and persists to session."""
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        lid = _resolve_default_location_id(request)
        request.active_location_id = lid
        request.active_location = Location.objects.filter(id=lid).first() if (Location and lid) else None
        if lid:
            request.session["active_location_id"] = lid
        return view(request, *args, **kwargs)
    return _wrapped

def _get_active_business(request):
    # 1) already attached by middleware or prior selection?
    biz = getattr(request, "business", None)
    if biz:
        return biz

    # 2) session?
    biz_id = request.session.get("active_business_id")
    if biz_id:
        from tenants.models import Business  # adjust path if different
        try:
            biz = Business.objects.get(pk=biz_id, is_active=True)
            request.business = biz
            return biz
        except Business.DoesNotExist:
            pass

    # 3) auto-pick for manager: first active business they manage
    user = request.user
    if user.is_authenticated:
        from tenants.models import Business  # adjust path if different
        biz = (Business.objects
               .filter(is_active=True, managers=user)  # or owners=user depending on your schema
               .order_by("name")
               .first())
        if biz:
            request.business = biz
            request.session["active_business_id"] = biz.id
            return biz

    return None

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from .models import BusinessKind

@login_required
def merch_add_router(request):
    """
    One URL that decides WHICH 'Add Products' form to render based on the active business.
    """
    biz = getattr(request, "business", None)
    if not biz:
        return redirect("tenants:choose_business")

    # try several field names on your Business model
    kind = None
    for attr in ("kind", "business_kind", "industry", "category", "type"):
        v = getattr(biz, attr, None)
        if v:
            kind = str(v)
            break

    template_map = {
        BusinessKind.PHARMACY: "inventory/add_product_pharmacy.html",
        BusinessKind.PHONES:   "inventory/add_product_phones.html",
        BusinessKind.LIQUOR:   "inventory/add_product_liquor.html",
        # if you have a dedicated clothing TextChoice, add it; otherwise use clothing as grocery fallback
        "clothing":            "inventory/add_product_clothing.html",
        BusinessKind.GROCERY:  "inventory/add_product_clothing.html",
    }
    template = template_map.get(kind) or "inventory/add_product_clothing.html"

    # DEBUG breadcrumb so you can confirm the router is actually hit in your runserver console
    print("ðŸ§­ merch_add_router â†’ business:", getattr(biz, "name", None), "kind:", kind, "template:", template)

    ctx = {
        "page_title": "Add Products",
        "BUSINESS_KIND": kind,
        "business": biz,
    }
    return render(request, template, ctx)

def _require_active_business(request):
    """Attach/choose a business for this request, or show error + redirect."""
    biz = _get_active_business(request)
    if not biz:
        messages.error(request, "No active business selected. Switch business and try again.")
        return redirect("dashboard:home")  # or your choose-business page
    return None  # OK

def __active_business_id(request):
    """
    Resolve active business id using your existing _get_active_business helper,
    which sometimes returns (biz, id) and sometimes a biz. Falls back to session.
    """
    bid = None
    try:
        res = _get_active_business(request)
        if isinstance(res, tuple) and len(res) == 2:
            _, bid = res
        else:
            bid = getattr(res, "id", None)
    except Exception:
        pass
    if not bid:
        bid = request.session.get("active_business_id")
    if bid:
        request.session["active_business_id"] = bid
    return bid
# Ensure Django views return HttpResponse, not tuples
from functools import wraps
from django.http import HttpResponseBase

def __default_location_id(request):
    """
    Priority:
      1) ?location=<id>
      2) session['active_location_id']
      3) default_location_for_request(request) (your function)
      4) None (no fallback to random store)
    """
    lid = request.GET.get("location")
    if lid and str(lid).isdigit():
        lid = int(lid)
        request.session["active_location_id"] = lid
        return lid

    lid = request.session.get("active_location_id")
    if lid:
        return lid

    try:
        loc = default_location_for_request(request)
        if loc:
            lid = getattr(loc, "pk", getattr(loc, "id", None))
            if lid:
                request.session["active_location_id"] = lid
                return lid
    except Exception:
        pass
    return None

def __apply_scope(qs, request):
    """
    Apply business + location filters to any queryset, supporting either
    `location/current_location` and optional `business` FKs.
    Uses *only* the helpers above; does not change your other functions.
    """
    try:
        fields = {f.name for f in qs.model._meta.get_fields()}
    except Exception:
        fields = set()

    # Business
    bid = __active_business_id(request)
    if bid and (("business" in fields) or ("business_id" in fields)):
        qs = qs.filter(business_id=bid)

    # Location
    lid = __default_location_id(request)
    if lid:
        if ("location_id" in fields) or ("location" in fields):
            qs = qs.filter(location_id=lid)
        elif ("current_location_id" in fields) or ("current_location" in fields):
            qs = qs.filter(current_location_id=lid)

    return qs

# Define with_active_location early so decorators below can use it.
try:
    with_active_location  # type: ignore[name-defined]
except NameError:
    def with_active_location(view):
        """
        Decorator: sets request.active_location(_id) using the same rules
        as stock_list. Name matches your existing decorator to avoid template edits.
        """
        @_wraps_hotfix(view)
        def _wrapped(request, *args, **kwargs):
            lid = __default_location_id(request)
            request.active_location_id = lid
            try:
                # Location may not yet be imported at this point; guard it.
                from .models import Location as _LocModel
                loc = _LocModel.objects.filter(id=lid).first() if (lid) else None
            except Exception:
                loc = None
            request.active_location = loc
            return view(request, *args, **kwargs)
        return _wrapped
# === END HOTFIX ===============================================================
# inventory/views.py
from decimal import Decimal
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone

try:
    from sales.models import Sale
except Exception:
    Sale = None  # keep app import-safe

def _json_ok(data, **extra):
    out = {"ok": True, "data": data}
    out.update(extra)
    return JsonResponse(out)

def _json_err(msg, status=400):
    return JsonResponse({"ok": False, "error": msg}, status=status)

def _to_decimal(x, default=Decimal("0")):
    try:
        if x is None or str(x).strip() == "":
            return default
        return Decimal(str(x))
    except Exception:
        return default

# --- Role helper import (safe) ----------------------------------------
try:
    from accounts.utils import user_is_manager  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
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
except Exception:  # pragma: no cover
    Business = None  # graceful fallback when multi-tenant app is absent

# OTP alias: when ENABLE_2FA=1 use django-otp, else fall back to login_required
try:
    if getattr(settings, "ENABLE_2FA", False):
        from django_otp.decorators import otp_required  # type: ignore
    else:
        raise ImportError
except Exception:  # pragma: no cover
    from django.contrib.auth.decorators import login_required as otp_required  # type: ignore

# Forms
from .forms import ScanInForm, ScanSoldForm, InventoryItemForm

# Inventory models
from .models import (
    InventoryItem,
    Product,
    InventoryAudit,
    WarrantyCheckLog,
    TimeLog,
    Location,
)
# ---- Safe model imports (no booleans!) ----
InventoryItem = Stock = Product = AuditLog = Location = Sale = None

try:
    # adjust import paths to match your project
    from .models import InventoryItem as _InventoryItem, Stock as _Stock, Product as _Product, AuditLog as _AuditLog, Location as _Location
    InventoryItem, Stock, Product, AuditLog, Location = _InventoryItem, _Stock, _Product, _AuditLog, _Location
except Exception:
    pass

try:
    # if Sale lives in a different app, fix the dotted path
    from sales.models import Sale as _Sale
    Sale = _Sale
except Exception:
    pass

# Wallet models live in the wallet app (safe import)
try:
    from wallet.models import WalletTransaction  # type: ignore
except Exception:  # pragma: no cover
    WalletTransaction = None  # graceful fallback

# Sales (safe import; used to record a sale on mark-sold)
try:
    from sales.models import Sale  # type: ignore
except Exception:  # pragma: no cover
    Sale = None

# Admin Purchase Orders (wallet app)
try:
    from wallet.models import AdminPurchaseOrder, AdminPurchaseOrderItem  # type: ignore
except Exception:  # pragma: no cover
    AdminPurchaseOrder = None
    AdminPurchaseOrderItem = None

# Cache version (signals may bump this). Safe fallback.
try:
    from .cache_utils import get_dashboard_cache_version
except Exception:  # pragma: no cover
    def get_dashboard_cache_version() -> int:
        return 1

User = get_user_model()

# ------------------------------------------------------------------
# Warranty lookups DISABLED: do NOT import warranty.py or requests.
# ------------------------------------------------------------------
_WARRANTY_LOOKUPS_DISABLED = True


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
# ---- safe imports used by helpers ----
try:
    from tenants.utils import (
        default_location_for_request,
        user_is_manager as _utils_is_manager,
        user_is_admin as _utils_is_admin,
    )
except Exception:
    def default_location_for_request(_request): return None
    def _utils_is_manager(_u): return False
    def _utils_is_admin(_u): return False


def _user_home_location(user):
    def _effective_default_location(request):
        """
        Return a default Location strictly within the *active business*:
          1) user's profile.home_location if it belongs to the active business
          2) otherwise the first location in the active business (prefer 'is_default' / 'is_primary' if present)
          3) otherwise None (no misleading global fallback like 'Area 25, Dwenza')
        """
        # Which FK does InventoryItem use for a location?
        loc_field = (
            "current_location" if _model_has_field(InventoryItem, "current_location")
            else ("location" if _model_has_field(InventoryItem, "location") else None)
        )
        if not loc_field:
            return None

        try:
            f = InventoryItem._meta.get_field(loc_field)
            Loc = getattr(getattr(f, "remote_field", None), "model", None)
        except Exception:
            Loc = None
        if Loc is None:
            return None

        # Active business id
        biz, biz_id = _require_active_business(request)

        # 1) user home_location only if it belongs to active business
        try:
            home = _user_home_location(request.user)
            if home and _obj_belongs_to_active_business(home, request):
                return home
        except Exception:
            pass

        # 2) some location inside the active business
        try:
            qs = Loc.objects.all()
            if biz_id:
                qs = qs.filter(**_biz_filter_kwargs(Loc, biz_id))
            # Prefer any boolean default flag if your model has it
            order = []
            for flag in ("is_default", "is_primary", "default"):
                if _model_has_field(Loc, flag):
                    order.append(f"-{flag}")
                    break
            order += ["name", "pk"]  # stable, readable ordering
            qs = qs.order_by(*order)
            return qs.first()
        except Exception:
            return None

    # views.py (top-level helper used by scan_in / scan_sold / update_stock)

    def _effective_default_location(request):
        """
        Pick the correct default store/location for the current user & active business.
        Priority:
          1) The user's home/store (_user_home_location)
          2) Location for the active business flagged is_default=True
          3) Location whose name == business name
          4) First location that belongs to the active business
        """

        # Figure out which model is used for the InventoryItem's location FK
        def _get_location_model():
            if _model_has_field(InventoryItem, "current_location"):
                f = InventoryItem._meta.get_field("current_location")
            elif _model_has_field(InventoryItem, "location"):
                f = InventoryItem._meta.get_field("location")
            else:
                return None
            return getattr(getattr(f, "remote_field", None), "model", None)

        Loc = _get_location_model()
        if not Loc:
            return None

        # Active business scope
        biz, biz_id = _require_active_business(request)
        qs = Loc.objects.all()
        if biz_id and hasattr(Loc, "business"):
            qs = qs.filter(**_biz_filter_kwargs(Loc, biz_id))

        if not qs.exists():
            return None

        # 1) user's home/store if it belongs to this business
        home = _user_home_location(request.user)
        if home and qs.filter(pk=getattr(home, "pk", getattr(home, "id", None))).exists():
            return home

        # 2) business default flag
        if _model_has_field(Loc, "is_default"):
            loc = qs.filter(is_default=True).order_by("id").first()
            if loc:
                return loc

        # 3) name matches business
        biz, _ = _get_active_business(request)
        if biz and _model_has_field(Loc, "name"):
            loc = qs.filter(name__iexact=getattr(biz, "name", "")).first()
            if loc:
                return loc

        # 4) final fallback â€“ first for the business
        return qs.order_by("id").first()

    """
    Best-effort 'home' location for a user.
    If you have profile.home_location, we use it; otherwise None.
    """
    try:
        prof = getattr(user, "profile", None)
        loc = getattr(prof, "home_location", None)
        if getattr(loc, "id", None) is not None:
            return loc
    except Exception:
        pass
    return None


def _is_manager_or_admin(user):
    """
    Treat platform admins, managers, Django staff and superusers as managers/admins.
    """
    try:
        if getattr(user, "is_superuser", False):
            return True
        if _utils_is_admin(user) or _utils_is_manager(user):
            return True
        if getattr(user, "is_staff", False):
            return True
        prof = getattr(user, "profile", None)
        if getattr(prof, "is_manager", False):
            return True
    except Exception:
        pass
    return False

# --- Permissions: safe imports + fallbacks -----------------------------------
from django.contrib.auth.decorators import user_passes_test

def _in_groups(user, names):
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(name__in=names).exists()

try:
    # optional centralization if you created tenants/roles.py earlier
    from circuitcity.tenants.roles import (
        is_auditor,
        is_manager_or_admin,
        is_store_clerk,
    )
except Exception:
    is_auditor = lambda u: _in_groups(u, ["Auditor", "Finance", "Admin"])
    is_manager_or_admin = lambda u: _in_groups(u, ["Manager", "Admin"])
    is_store_clerk = lambda u: _in_groups(u, ["Clerk", "Seller", "Manager", "Admin"])

# Existing decorators (used by other views)
_is_auditor = user_passes_test(is_auditor)
_is_manager_or_admin = user_passes_test(is_manager_or_admin)
_is_store_clerk = user_passes_test(is_store_clerk)

# NEW: who can view *all* time logs? (managers, finance, admins)
def _pred_can_view_all(user):
    # allow Django permission too, if you've granted it in admin
    has_perm = user.has_perm("inventory.view_timelog") if user.is_authenticated else False
    return has_perm or _in_groups(user, ["Manager", "Finance", "Admin"])

_can_view_all = user_passes_test(_pred_can_view_all)

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
# ---- SAFE calendar window helper (no WSGIRequest usage) ----
from datetime import datetime, timedelta, date, time as dtime
from django.utils import timezone

def _get_preset_window_safe(request, default_preset: str = "month"):
    """
    Returns (range_preset, day_str, start_dt, end_dt)
    range_preset: 'month' | '7d' | 'all' | 'day'
    start_dt/end_dt: timezone-aware datetimes or None
    """
    qs = request.GET
    range_preset = (qs.get("range") or default_preset).strip().lower()
    day_str = qs.get("day")

    now = timezone.now()
    today = timezone.localdate()

    start_dt = end_dt = None

    if range_preset == "day":
        try:
            day_obj = datetime.strptime(day_str, "%Y-%m-%d").date() if day_str else today
        except Exception:
            day_obj = today
        start_dt = timezone.make_aware(datetime.combine(day_obj, dtime.min))
        end_dt   = timezone.make_aware(datetime.combine(day_obj, dtime.max))

    elif range_preset == "7d":
        start_dt = now - timedelta(days=7)
        end_dt   = now

    elif range_preset == "all":
        start_dt = None
        end_dt   = None

    else:  # default month
        month_start = today.replace(day=1)
        start_dt = timezone.make_aware(datetime.combine(month_start, dtime.min))
        end_dt   = now
        range_preset = "month"

    return range_preset, (day_str or None), start_dt, end_dt
# ---- SAFE calendar window helper (no WSGIRequest usage) ----
from datetime import datetime, timedelta, date, time as dtime
from django.utils import timezone

def _get_preset_window_safe(request, default_preset: str = "month"):
    """
    Returns (range_preset, day_str, start_dt, end_dt)
    start_dt/end_dt are tz-aware datetimes or None for 'all'.
    """
    qs = request.GET
    range_preset = (qs.get("range") or default_preset).strip().lower()
    day_str = qs.get("day")

    now = timezone.now()
    today = timezone.localdate()
    start_dt = end_dt = None

    if range_preset == "day":
        try:
            day_obj = datetime.strptime(day_str, "%Y-%m-%d").date() if day_str else today
        except Exception:
            day_obj = today
        start_dt = timezone.make_aware(datetime.combine(day_obj, dtime.min))
        end_dt   = timezone.make_aware(datetime.combine(day_obj, dtime.max))
    elif range_preset == "7d":
        start_dt = now - timedelta(days=7)
        end_dt   = now
    elif range_preset == "all":
        start_dt = None
        end_dt   = None
    else:  # default: month
        month_start = today.replace(day=1)
        start_dt = timezone.make_aware(datetime.combine(month_start, dtime.min))
        end_dt   = now
        range_preset = "month"

    return range_preset, (day_str or None), start_dt, end_dt

# >>> HARD OVERRIDE any bad implementation imported earlier
get_preset_window = _get_preset_window_safe
# <<<


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

# --- Role helper import (safe fallbacks) -------------------------------------
from django.contrib.auth.decorators import user_passes_test

def _in_groups(user, names: list[str]) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    # superusers always pass
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(name__in=names).exists()

try:
    # If you have a central roles module, greatâ€”use it.
    # Adjust the import path to wherever your project keeps role predicates.
    from circuitcity.tenants.roles import (
        is_auditor as _pred_is_auditor,
        is_manager_or_admin as _pred_is_manager_or_admin,
        is_store_clerk as _pred_is_store_clerk,
    )
except Exception:
    # Fallbacks so the app never breaks if the roles module is missing
    def _pred_is_auditor(user):
        # allow Finance/Auditor/Admin to read audit-y pages
        return _in_groups(user, ["Auditor", "Finance", "Admin"])

    def _pred_is_manager_or_admin(user):
        return _in_groups(user, ["Manager", "Admin"])

    def _pred_is_store_clerk(user):
        return _in_groups(user, ["Clerk", "Seller", "Manager", "Admin"])

# Expose decorators used throughout the file (these names were causing NameError)
_is_auditor = user_passes_test(_pred_is_auditor)
_is_manager_or_admin = user_passes_test(_pred_is_manager_or_admin)
_is_store_clerk = user_passes_test(_pred_is_store_clerk)
# inventory/views.py (near the other imports)
try:
    from tenants.utils import user_is_admin, user_is_manager
except Exception:
    # ultra-defensive fallbacks so the view never crashes if tenants.utils is unavailable
    def user_is_admin(u):   return bool(getattr(u, "is_superuser", False) or getattr(u, "is_staff", False))
    def user_is_manager(u): return user_is_admin(u)

def _is_manager_or_admin(user):
    """Return True if user is a platform admin, manager, or superuser."""
    try:
        if not getattr(user, "is_authenticated", False):
            return False
        return bool(
            getattr(user, "is_superuser", False)
            or user_is_admin(user)
            or user_is_manager(user)
        )
    except Exception:
        return False
# ---- Safe imports used by helpers (place near other imports) ----
try:
    from tenants.utils import default_location_for_request
except Exception:
    # ultra-defensive fallback: if tenants.utils isn't loaded yet
    def default_location_for_request(_request):
        return None

# If you have a Location model, we don't need to import it here for this helper.
# The view already falls back to default_location_for_request(request).
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache

# ---- Guard: ensure Django views return HttpResponse, not tuples ----------
from functools import wraps
from django.http import HttpResponseBase

def _enforce_http_response(viewfunc):
    @wraps(viewfunc)
    def _inner(request, *args, **kwargs):
        rv = viewfunc(request, *args, **kwargs)
        if isinstance(rv, tuple):
            # Common accident: (HttpResponse, None) or a trailing comma.
            first_http = next((x for x in rv if isinstance(x, HttpResponseBase)), None)
            if first_http is not None:
                return first_http
            raise TypeError(f"{viewfunc.__name__} returned a tuple; Django views must return HttpResponse.")
        return rv
    return _inner


from typing import Dict, Any
import logging
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache


@login_required
@never_cache
def stock_list(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    """
    Inventory Â· Stock List

    â€¢ Always scoped to active business.
    â€¢ Location filter is opt-in (?location / ?location_id).
    â€¢ Default table hides SOLD; use status=sold to view sold rows.
    â€¢ Badges are computed business-wide.
    â€¢ Hardened query parsing so bad params never 500.
    """
    import logging
    from decimal import Decimal
    from django.db.models import Q, Sum
    from django.http import JsonResponse

    from django.contrib import messages

    log = logging.getLogger(__name__)

    # ---------- tiny helpers (safe param parsing) ----------
    def _int(request, key, default, min_=1, max_=200):
        try:
            v = int(request.GET.get(key, default))
            return max(min_, min(v, max_))
        except (TypeError, ValueError):
            return default

    def _choice(request, key, allowed, default):
        v = (request.GET.get(key) or "").lower()
        return v if v in allowed else default

    # ---------- util helpers ----------
    def _try_import(modpath: str, attr: str | None = None):
        try:
            mod = __import__(modpath, fromlist=[attr] if attr else [])
            return getattr(mod, attr) if attr else mod
        except Exception:
            return None

    def _hasf(model, name: str) -> bool:
        try:
            return any(f.name == name for f in model._meta.get_fields())
        except Exception:
            return False

    def _sum(qs, names: tuple[str, ...]) -> Decimal:
        # uses outer-scope Model at call-time
        for n in names:
            if n and _hasf(Model, n):
                try:
                    v = qs.aggregate(_t=Sum(n))["_t"]
                    return Decimal(v or 0)
                except Exception:
                    continue
        return Decimal("0")

    # ---------- business context ----------
    get_active_business = (
        _try_import("circuitcity.tenants.utils", "get_active_business")
        or _try_import("tenants.utils", "get_active_business")
        or (lambda _r: None)
    )
    ensure_request_defaults = (
        _try_import("inventory.middleware", "ensure_request_defaults")
        or (lambda _r: None)
    )

    biz = get_active_business(request)
    biz_id = getattr(biz, "id", None)
    if not biz_id:
        messages.error(request, "No active business selected. Switch business and try again.")
        try:
            return redirect("tenants:activate_mine")
        except Exception:
            return redirect("/tenants/activate-mine/")
    try:
        ensure_request_defaults(request)
    except Exception:
        pass

    # ---------- canonical model ----------
    Model = None
    try:
        from .models import InventoryItem as _InventoryItem
        Model = _InventoryItem
    except Exception:
        for alt in ("Stock", "Inventory"):
            try:
                Model = getattr(__import__(f"{__package__}.models", fromlist=[alt]), alt)
                break
            except Exception:
                continue
    if Model is None:
        return JsonResponse({"ok": False, "error": "No inventory model found"}, status=500)

    manager = getattr(Model, "_base_manager", Model.objects)
    qs = manager.all()

    # ---------- base scope (biz + active + not archived) ----------
    if _hasf(Model, "business_id"):
        qs = qs.filter(business_id=biz_id)
    elif _hasf(Model, "business"):
        qs = qs.filter(business__id=biz_id)

    if _hasf(Model, "is_active"):
        qs = qs.filter(is_active=True)
    if _hasf(Model, "archived"):
        qs = qs.filter(archived=False)

    # ---------- location (opt-in) ----------
    loc_id = request.GET.get("location") or request.GET.get("location_id")
    if loc_id:
        for fk in ("current_location", "location", "store", "branch"):
            if _hasf(Model, f"{fk}_id"):
                qs = qs.filter(**{f"{fk}_id": loc_id})
                break
            if _hasf(Model, fk):
                qs = qs.filter(**{fk: loc_id})
                break

    # ---------- SOLD vs IN-STOCK predicates (OR across indicators) ----------
    def SOLD_Q() -> Q:
        q = Q()
        if _hasf(Model, "status"):     q |= Q(status__iexact="sold")
        if _hasf(Model, "sold_at"):    q |= Q(sold_at__isnull=False)
        if _hasf(Model, "in_stock"):   q |= Q(in_stock=False)
        if _hasf(Model, "quantity"):   q |= Q(quantity=0)
        if _hasf(Model, "qty"):        q |= Q(qty=0)
        return q

    def INSTOCK_Q() -> Q:
        q = Q()
        if _hasf(Model, "status"):     q |= ~Q(status__iexact="sold")
        if _hasf(Model, "sold_at"):    q |= Q(sold_at__isnull=True)
        if _hasf(Model, "in_stock"):   q |= Q(in_stock=True)
        if _hasf(Model, "quantity"):   q |= Q(quantity__gt=0)
        if _hasf(Model, "qty"):        q |= Q(qty__gt=0)
        return q

    # ---------- badge snapshot (business-wide) ----------
    qs_base = qs
    try:
        instock_all = qs_base.filter(INSTOCK_Q())
        sold_all = qs_base.filter(SOLD_Q())
    except Exception:
        instock_all, sold_all = qs_base, qs_base.none()

    try:
        in_stock_count = int(instock_all.count())
    except Exception:
        in_stock_count = 0
    try:
        sold_count = int(sold_all.count())
    except Exception:
        sold_count = 0

    sum_order_amt   = _sum(instock_all, ("order_price", "order_cost", "cost_price"))
    sum_selling_amt = _sum(sold_all,   ("selling_price", "sale_price", "price"))

    # ---------- table filters (status + search) ----------
    status = _choice(request, "status", {"sold", "s", "in", "in_stock", "stock", "all", "al", "ai"}, "in_stock")
    q_text = (request.GET.get("q") or "").strip()

    if status in {"sold", "s"}:
        qs = sold_all
    elif status in {"in", "in_stock", "stock"}:
        qs = instock_all
    elif status in {"all", "al", "ai"}:
        qs = qs_base
    else:
        qs = instock_all  # default hide sold

    if q_text:
        OR = Q()
        for fname in ("imei", "serial", "code", "sku", "name"):
            if _hasf(Model, fname):
                OR |= Q(**{f"{fname}__icontains": q_text})
        # product name (if FK exists)
        try:
            prod_field = Model._meta.get_field("product")
            Rel = getattr(prod_field, "related_model", None)
            if Rel and any(f.name == "name" for f in Rel._meta.get_fields()):
                OR |= Q(product__name__icontains=q_text)
        except Exception:
            pass
        if OR:
            qs = qs.filter(OR)

    # joins for UI
    rels = [r for r in ("product", "current_location", "location", "store", "business") if _hasf(Model, r)]
    if rels:
        try:
            qs = qs.select_related(*rels)
        except Exception:
            pass

    # ---------- negotiate & paginate ----------
    accept = (request.headers.get("Accept") or "").lower()
    wants_json = (
        (request.GET.get("format") or "").lower() == "json"
        or (request.headers.get("x-requested-with") or "").lower() == "xmlhttprequest"
        or "application/json" in accept
    )

    per_page = _int(request, "page_size", default=50, min_=1, max_=200)
    page     = _int(request, "page", default=1, min_=1, max_=10_000)  # reserved for future server-side paging

    def _loc(o):
        loc = getattr(o, "current_location", None) or getattr(o, "location", None) or getattr(o, "store", None)
        return {"id": getattr(loc, "id", None), "name": getattr(loc, "name", None)} if loc else None

    def _qty(o) -> int:
        for n in ("quantity", "qty"):
            if hasattr(o, n):
                try:
                    return int(getattr(o, n) or 0)
                except Exception:
                    return 0
        return 1

    def _first_price(o, names: tuple[str, ...]):
        for n in names:
            if hasattr(o, n):
                v = getattr(o, n)
                if v is not None:
                    return v
        return None

    def _row(o):
        prod = getattr(o, "product", None)
        name = getattr(o, "name", None) or (getattr(prod, "name", None) if prod else "") or ""
        sku = None
        for k in ("imei", "serial", "sku", "code"):
            if getattr(o, k, None):
                sku = getattr(o, k)
                break
        return {
            "id": getattr(o, "id", None),
            "sku": sku,
            "name": name,
            "qty": _qty(o),
            "status": getattr(o, "status", None),
            "order_price": _first_price(o, ("order_price", "order_cost", "cost_price")),
            "selling_price": _first_price(o, ("selling_price", "sale_price", "price")),
            "location": _loc(o),
        }

    try:
        total = qs.count()
    except Exception:
        total = 0
    qs = qs.order_by("-id")

    # ---------- badge payload (with wide compatibility aliases) ----------
    header = {
        "in_stock": in_stock_count,
        "sold": sold_count,
        "sum_order": sum_order_amt,
        "sum_selling": sum_selling_amt,
    }

    # Aliases so legacy templates pick them up
    badge_aliases = {
        # counts
        "in_stock": in_stock_count,
        "in_stock_count": in_stock_count,
        "count_in_stock": in_stock_count,
        "stocks_in_stock": in_stock_count,
        "sold": sold_count,
        "sold_count": sold_count,
        "count_sold": sold_count,
        "stocks_sold": sold_count,
        "sold_total": sold_count,
        # sums
        "sum_order": sum_order_amt,
        "order_sum": sum_order_amt,
        "total_order": sum_order_amt,
        "sum_selling": sum_selling_amt,
        "selling_sum": sum_selling_amt,
        "total_selling": sum_selling_amt,
    }

    if wants_json:
        data = [_row(o) for o in qs[:per_page]]
        out_header = {
            "in_stock": in_stock_count,
            "sold": sold_count,
            "sum_order": str(sum_order_amt),
            "sum_selling": str(sum_selling_amt),
        }
        # include the aliases in JSON too (cast Decimals to str)
        out_header.update({k: (str(v) if isinstance(v, Decimal) else v) for k, v in badge_aliases.items()})
        return JsonResponse({"ok": True, "count": total, "page": page, "limit": per_page,
                             "header": out_header, "data": data}, status=200)

    items = list(qs[:per_page])

    # pick a template that exists
    template = "inventory/list.html"
    try:
        from django.template.loader import get_template
        for cand in ("inventory/list.html", "inventory/stock_list.html"):
            try:
                get_template(cand)
                template = cand
                break
            except Exception:
                continue
    except Exception:
        pass

    # Context: items + badges + aliases
    ctx = {
        "items": items,
        "rows": items,
        "count": total,
        "rows_per_page": per_page,
        "header": header,
        # primary keys
        "in_stock": in_stock_count,
        "sold": sold_count,
        "sum_order": sum_order_amt,
        "sum_selling": sum_selling_amt,
        # wide aliases
        **badge_aliases,
    }
    return render(request, template, ctx)
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


from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse

def _get_active_business(request):
    """
    Return (business, business_id). Also persists id into the session.
    Never redirects.
    """
    try:
        # use your tenants utility if available
        from circuitcity.tenants.utils import get_active_business as _get_active
    except Exception:
        _get_active = None

    biz = None
    if _get_active:
        try:
            biz = _get_active(request)
        except Exception:
            biz = None

    if biz:
        request.active_business_id = biz.id
        request.session["active_business_id"] = biz.id
        return biz, biz.id

    return None, None

from django.http import Http404

def _get_active_location(request):
    """
    Best-effort: return the active Location or None.
    """
    try:
        from circuitcity.tenants.utils import get_active_location as _gal
    except Exception:
        try:
            from tenants.utils import get_active_location as _gal
        except Exception:
            _gal = None
    if not _gal:
        return None
    try:
        return _gal(request)
    except Exception:
        return None
def _require_active_business(request):
    """
    ALWAYS returns a tuple: (business, location).

    If no active business is resolved, it falls back to the first Business in DB,
    and raises 404 only if none exist at all.
    """
    biz = _get_active_business(request)
    loc = _get_active_location(request)

    if biz is None:
        try:
            from tenants.models import Business
            biz = Business.objects.first()
        except Exception:
            biz = None

    if biz is None:
        raise Http404("No active business configured")

    return biz, loc

def _scoped(qs, request):
    """
    Scope any queryset to the active business if the underlying model supports it.
    """
    biz, biz_id = _require_active_business(request)
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
    biz, biz_id = _require_active_business(request)
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
    """Constrain form dropdowns (Product, Location) to the active business, and set default location."""
    try:
        if not hasattr(form, "fields"):
            return

        # Scope Product
        if "product" in form.fields:
            form.fields["product"].queryset = _scoped(Product.objects.all(), request).order_by("brand", "name", "variant")

        # Scope Location
        if "location" in form.fields:
            qs = _scoped(Location.objects.all(), request).order_by("name")
            form.fields["location"].queryset = qs

            # --- Default: active business/store ---
            biz, biz_id = _get_active_business(request)
            if biz_id:
                store_name = getattr(biz, "display_name", None) or getattr(biz, "name", None)
                if store_name:
                    default_loc = qs.filter(name__iexact=store_name).first() \
                                  or qs.filter(name__iexact=f"{store_name} Store").first() \
                                  or qs.filter(name__icontains=store_name).first()
                else:
                    default_loc = qs.first()

                if not default_loc and store_name:
                    # Auto-create if missing
                    try:
                        default_loc = Location.objects.create(
                            business_id=biz_id,
                            name=store_name,
                            city=""
                        )
                    except Exception:
                        default_loc = None

                if default_loc:
                    form.fields["location"].initial = default_loc.id
    except Exception as e:
        import logging
        logging.exception("Failed to scope querysets: %s", e)
        pass

# ---------------- Common helpers & safe imports (add once) ----------------
from django.db.models import Q, OuterRef, Subquery, Exists, Value, BooleanField, QuerySet
from django.utils import timezone
from datetime import datetime, timedelta, date, time

# Tenancy scoping (safe fallback)
try:
    from circuitcity.tenants.utils import scoped as _scoped  # applies business/role scoping
except Exception:
    def _scoped(qs, _request):  # no-op fallback
        return qs

# Safe model placeholders & imports (NEVER booleans)
InventoryItem = Stock = Product = AuditLog = Location = Sale = None
try:
    from .models import (
        InventoryItem as _InventoryItem,
        Stock as _Stock,
        Product as _Product,
        AuditLog as _AuditLog,
        Location as _Location,
    )
    InventoryItem, Stock, Product, AuditLog, Location = _InventoryItem, _Stock, _Product, _AuditLog, _Location
except Exception:
    pass

try:
    from sales.models import Sale as _Sale
    Sale = _Sale
except Exception:
    pass

def _pick_manager(*models):
    """Return the first available .objects manager from the given model classes."""
    for m in models:
        if m is not None:
            mgr = getattr(m, "objects", None)
            if mgr is not None:
                return mgr
    return None

# ---- build a time-range Q() across one or more datetime fields
def _time_q_for(_model, start_dt, end_dt, fields: tuple[str, ...]):
    if not (start_dt and end_dt):
        return Q()
    q = Q()
    for f in fields:
        q |= Q(**{f"{f}__gte": start_dt, f"{f}__lte": end_dt})
    return q

def _inv_base(qs: QuerySet, start_dt=None, end_dt=None, time_fields=("created_at",)):
    if start_dt and end_dt:
        q = Q()
        for f in time_fields:
            q |= Q(**{f"{f}__gte": start_dt, f"{f}__lte": end_dt})
        qs = qs.filter(q)
    return qs

# Put near your other helpers in inventory/views.py

# inventory/views.py  â€” REPLACE your existing get_preset_window with this



# ---- REPLACE the whole get_preset_window with this safe version ----
from datetime import datetime, timedelta, time as dtime
from django.utils import timezone

def get_preset_window(request, default_preset: str = "month"):
    """
    Returns (range_preset, day_str, start_dt, end_dt)
    range_preset âˆˆ {'month','7d','all','day'}
    start_dt/end_dt are tz-aware datetimes, or None for 'all'.
    """
    qs = request.GET
    range_preset = (qs.get("range") or default_preset).strip().lower()
    day_str = qs.get("day")

    now = timezone.now()
    today = timezone.localdate()
    start_dt = end_dt = None

    if range_preset == "day":
        try:
            day_obj = datetime.strptime(day_str, "%Y-%m-%d").date() if day_str else today
        except Exception:
            day_obj = today
        start_dt = timezone.make_aware(datetime.combine(day_obj, dtime.min))
        end_dt   = timezone.make_aware(datetime.combine(day_obj, dtime.max))

    elif range_preset == "7d":
        start_dt = now - timedelta(days=7)
        end_dt   = now

    elif range_preset == "all":
        start_dt = None
        end_dt   = None

    else:  # default: month
        month_start = today.replace(day=1)
        start_dt = timezone.make_aware(datetime.combine(month_start, dtime.min))
        end_dt   = now
        range_preset = "month"

    return range_preset, (day_str or None), start_dt, end_dt
# ---------------- End helpers ----------------
# --- helpers to ensure default location & scoped form querysets ---

# --- inventory/views.py (snippet) ---

from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.shortcuts import render
from typing import Optional, Tuple

from .models import InventoryItem  # used by _inv_location_model()
from .utils import ensure_default_location  # new helper we added earlier

# If your project exposes a tenant-biz helper, import it defensively.
try:
    from tenants.utils import get_active_business as _tenants_get_active_business  # type: ignore
except Exception:
    _tenants_get_active_business = None  # type: ignore


# ------- Location helpers -------
def _model_has_field(model, field_name: str) -> bool:
    try:
        model._meta.get_field(field_name)  # type: ignore[attr-defined]
        return True
    except Exception:
        return False

def _inv_location_model() -> Tuple[Optional[type], Optional[str]]:
    """
    Returns (LocationModel, field_name_on_InventoryItem) or (None, None).
    Detects whether your InventoryItem points to 'current_location' or 'location'.
    """
    for fname in ("current_location", "location"):
        try:
            if _model_has_field(InventoryItem, fname):
                f = InventoryItem._meta.get_field(fname)
                Loc = getattr(getattr(f, "remote_field", None), "model", None)
                if Loc:
                    return Loc, fname  # type: ignore[return-value]
        except Exception:
            pass
    return None, None

def _get_active_business(request):
    """
    Try to read request.business first (set by TenantResolutionMiddleware);
    fall back to tenants.utils.get_active_business(request) when available.
    Returns (business_obj_or_None, business_id_or_None).
    """
    biz = getattr(request, "business", None)
    if biz is None and _tenants_get_active_business:
        try:
            biz = _tenants_get_active_business(request)
        except Exception:
            biz = None
    return biz, getattr(biz, "id", None)


def default_location_for_request(request):
    """
    Return a default Location for the active business; create one if none.
    Uses utils.ensure_default_location so it works whether you have Location or Store.
    """
    biz, biz_id = _get_active_business(request)
    if not biz_id:
        return None
    try:
        return ensure_default_location(biz)
    except Exception:
        return None


# ------------------- SCAN SOLD -------------------

# --- Inventory Â· Scan SOLD (paste over your current function) ---
@never_cache
@login_required
@require_business
@require_role(["Manager", "Admin", "Agent"])
def scan_sold(request, *args, **kwargs):
    """
    Scan-to-sell screen.

    - Shows correct identifier rules (IMEI/Serial) from the single source of truth
    - Respects active/default location (same helpers your APIs use)
    - Exposes the API endpoints the UI should call
    - If ScanSoldForm exists, renders a clamped Location <select>; otherwise supplies locations[] for a custom UI
    """
    from django.shortcuts import render
    from django.utils import timezone

    # ---------- tiny safe helpers (prefer globals when already provided) ----------
    def _safe_has_field(model, name: str) -> bool:
        try:
            return any(getattr(f, "name", None) == name for f in getattr(model, "_meta").get_fields())
        except Exception:
            return False

    _has_field = globals().get("_model_has_field", _safe_has_field)
    InventoryItem = globals().get("InventoryItem", None)
    Location = globals().get("Location", None)
    scoped = globals().get("scoped", lambda qs, _r: qs)

    # Optional: ScanSoldForm and a tiny field-clamper
    try:
        from inventory.forms import ScanSoldForm  # type: ignore
    except Exception:
        ScanSoldForm = None  # type: ignore

    def _restrict_location_field(form, request_, dflt_loc, *, set_initial=True):
        """Clamp the form's location-like field to only the user's active/default location."""
        if not dflt_loc or not form:
            return
        from django.forms import ModelChoiceField

        cand = ("location", "current_location", "store", "branch")
        fld_name = next(
            (n for n in cand if n in form.fields and isinstance(form.fields[n], ModelChoiceField)),
            None
        )
        if not fld_name:
            return
        fld = form.fields[fld_name]
        dflt_id = getattr(dflt_loc, "pk", getattr(dflt_loc, "id", None))
        label = (
            getattr(dflt_loc, "store_name", None)
            or getattr(dflt_loc, "name", None)
            or getattr(dflt_loc, "title", None)
            or f"Loc #{dflt_id}"
        )

        try:
            fld.empty_label = None
        except Exception:
            pass

        # choices + initial (for non-DB rendered widgets)
        try:
            fld.choices = [(dflt_id, label)]
        except Exception:
            pass
        if set_initial:
            try:
                fld.initial = dflt_id
            except Exception:
                pass

        # queryset clamp (for ModelChoiceField widgets)
        try:
            qs = getattr(fld, "queryset", None)
            if qs is not None:
                fld.queryset = qs.model.objects.filter(pk=dflt_id)
        except Exception:
            pass

    # May be provided by your tenants/helpers layer; use if available
    _get_active_business = globals().get("_get_active_business", None)
    default_location_for_request_fn = globals().get("default_location_for_request", None)

    # ---------- 1) Active business ----------
    biz = getattr(request, "business", None)
    biz_id = getattr(biz, "id", None)
    if callable(_get_active_business):
        try:
            g_biz, g_id = _get_active_business(request)
            biz = g_biz or biz
            biz_id = g_id or biz_id
        except Exception:
            pass

    # ---------- 2) Ensure request.active_location (memoize) ----------
    loc = getattr(request, "active_location", None)
    if loc is None and callable(default_location_for_request_fn):
        try:
            loc = default_location_for_request_fn(request)
        except Exception:
            loc = None
        if loc is not None:
            try:
                request.active_location = loc
                request.active_location_id = getattr(loc, "id", None)
            except Exception:
                pass
    loc_id = getattr(loc, "id", None)

    # ---------- 3) Discover InventoryItem's location FK ----------
    def _discover_inv_location_model():
        if not InventoryItem:
            return None, None
        fname = "current_location" if _has_field(InventoryItem, "current_location") else (
            "location" if _has_field(InventoryItem, "location") else None
        )
        if not fname:
            return None, None
        try:
            f = InventoryItem._meta.get_field(fname)
            LocModel = getattr(getattr(f, "remote_field", None), "model", None)
            return LocModel, fname
        except Exception:
            return None, None

    loc_model, loc_field_name = _discover_inv_location_model()

    # ---------- 4) Identifier rules ----------
    uses_imei = bool(InventoryItem and _has_field(InventoryItem, "imei"))
    uses_serial = bool(not uses_imei and InventoryItem and _has_field(InventoryItem, "serial"))
    identifier_field = "imei" if uses_imei else ("serial" if uses_serial else None)

    min_len, max_len, require_imei = 15, 15, True
    rule_name = "Phone sales"

    biz_code = None
    try:
        biz_code = getattr(biz, "business_type", None) or getattr(biz, "type", None) or getattr(biz, "code", None)
    except Exception:
        biz_code = None

    try:
        from inventory.validators import _active_business_code_from_request  # type: ignore
        try:
            biz_code = _active_business_code_from_request(request) or biz_code
        except Exception:
            pass
    except Exception:
        pass

    try:
        from core.business_rules import get_rule  # type: ignore
        r = get_rule(biz_code)
        rule_name = getattr(r, "name", rule_name) or rule_name
        min_len = int(getattr(r, "serial_min", min_len))
        max_len = int(getattr(r, "serial_max", max_len))
        require_imei = bool(getattr(r, "require_imei", require_imei))
    except Exception:
        pass

    if identifier_field == "imei":
        min_len = max_len = 15
        require_imei = True

    identifier_label = "IMEI" if (require_imei or identifier_field == "imei") else "Serial"
    if min_len == max_len:
        identifier_hint = f"{identifier_label} must be exactly {min_len} digits."
        identifier_pattern = rf"^\d{{{min_len}}}$"
        identifier_placeholder = f"{identifier_label} ({min_len} digits)"
    else:
        identifier_hint = f"{identifier_label} must be {min_len}â€“{max_len} digits."
        identifier_pattern = rf"^\d{{{min_len},{max_len}}}$"
        identifier_placeholder = f"{identifier_label} ({min_len}â€“{max_len} digits)"

    # ---------- 5) Locations list (scoped) ----------
    locations = []
    location_default = None
    if Location is not None:
        try:
            q = scoped(Location.objects.all(), request)
            # If tenant-scoped, keep within this biz
            try:
                names = {f.name for f in Location._meta.get_fields()}
            except Exception:
                names = set()
            if "business_id" in names or "business" in names:
                try:
                    q = q.filter(business_id=biz_id)
                except Exception:
                    q = q.filter(business__id=biz_id)
            q = q.order_by("name")
            rows = list(q[:50])
            locations = [{"id": getattr(L, "id", None), "name": getattr(L, "name", f"Loc #{getattr(L, 'id', '')}")} for L in rows]
            location_default = loc_id or (locations[0]["id"] if locations else None)
        except Exception:
            locations = []
            location_default = loc_id

    # ---------- 6) Optional form (keeps template compatibility with {{ form.location }}) ----------
    form = None
    if ScanSoldForm is not None:
        try:
            form = ScanSoldForm(initial={"location": loc})
            _restrict_location_field(form, request, loc, set_initial=True)
        except Exception:
            form = None  # fall back to locations[] below

    # ---------- 7) API endpoints ----------
    api_paths = {
        "probe": "/inventory/api/stock-status",
        "sell":  "/inventory/api/mark-sold",
    }

    # ---------- 8) Context ----------
    ctx = {
        # Business
        "active_business": biz,
        "active_business_id": biz_id,
        "active_business_name": getattr(biz, "display_name", None) or getattr(biz, "name", None),
        "active_business_code": biz_code,
        "business_rule_name": rule_name,

        # Location (both form-based and list-based UIs can work)
        "active_location": loc,
        "active_location_id": loc_id,
        "active_location_name": (
            getattr(loc, "store_name", None)
            or getattr(loc, "name", None)
            or getattr(loc, "title", None)
        ) if loc else None,
        "locations": locations,
        "location_default": location_default,

        # Inventory location metadata
        "inventory_location_field": loc_field_name,
        "inventory_location_model": getattr(loc_model, "__name__", None),

        # Identifier metadata
        "identifier_field": identifier_field,
        "identifier_label": identifier_label,
        "identifier_min_len": min_len,
        "identifier_max_len": max_len,
        "identifier_digits_only": True,
        "identifier_require_imei": require_imei,
        "identifier_placeholder": identifier_placeholder,
        "identifier_hint": identifier_hint,
        "identifier_regex": identifier_pattern,

        # APIs
        "api_probe_url": api_paths["probe"],
        "api_sell_url": api_paths["sell"],

        # UI defaults
        "sold_date_default": timezone.localdate().isoformat(),
        "commission_default": 0.0,
        "auto_submit_default": False,

        # Optional form for templates that expect {{ form }}
        "form": form,
    }

    return render(request, "inventory/scan_sold.html", ctx)


def _inv_location_model():
    """
    Resolve the Location model class that Inventory items point at.
    Returns (LocationModel, fk_field_name) or (None, None) if missing.
    """
    try:
        from inventory.models import InventoryItem  # local import to avoid cycles
    except Exception:
        return None, None

    if hasattr(InventoryItem, "current_location"):
        return getattr(InventoryItem, "current_location").field.remote_field.model, "current_location"
    if hasattr(InventoryItem, "location"):
        return getattr(InventoryItem, "location").field.remote_field.model, "location"
    return None, None


def _user_home_location(request):
    """
    Best-effort 'home' Location for the logged-in user.
    Looks at user.profile.home_location (if present) and returns the object.
    Does NOT apply tenant filtering here; callers should validate it.
    """
    Loc, _ = _inv_location_model()
    if not Loc:
        return None

    user = getattr(request, "user", None)
    if not user:
        return None

    try:
        prof = getattr(user, "profile", None)
        loc = getattr(prof, "home_location", None)
        if getattr(loc, "id", None) is not None:
            return loc
    except Exception:
        pass
    return None


def default_location_for_request(request):
    """
    Return a Location inside the *active business*:
      1) user.profile.home_location if it belongs to active business
      2) otherwise the first location in that business (prefers is_default / is_primary when available)
      3) otherwise None
    """
    Loc, _ = _inv_location_model()
    if not Loc:
        return None

    # Which business are we in?
    try:
        biz, biz_id = _require_active_business(request)
    except Exception:
        biz_id = None

    def _belongs(loc):
        try:
            for fk in ("business_id", "store_id", "tenant_id"):
                if hasattr(loc, fk):
                    return getattr(loc, fk) == biz_id
        except Exception:
            pass
        return False

    home = _user_home_location(request)
    if home and _belongs(home):
        return home

    try:
        qs = Loc.objects.all()
        if biz_id:
            names = {f.name for f in Loc._meta.fields}
            for fk in ("business_id", "store_id", "tenant_id"):
                if fk in names:
                    qs = qs.filter(**{fk: biz_id})
                    break

        names = {f.name for f in Loc._meta.fields}
        if "is_default" in names:
            first = qs.order_by("-is_default", "id").first()
        elif "is_primary" in names:
            first = qs.order_by("-is_primary", "id").first()
        else:
            first = qs.order_by("id").first()
        return first
    except Exception:
        return None

# A tiny paginator many views use
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger  # noqa: E402 (after Django import)

def _paginate_qs(request, qs, per_page=25, page_param="page"):
    """
    Safe paginator that returns (page_obj, page_number).
    Works with QuerySets or iterables.
    """
    try:
        page_num = request.GET.get(page_param, "1")
        paginator = Paginator(qs, per_page)
        try:
            page_obj = paginator.page(page_num)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)
        return page_obj, int(page_obj.number)
    except Exception:
        # Fall back to a trivial shape so callers donâ€™t blow up
        class _Trivial:
            object_list = list(qs) if hasattr(qs, "__iter__") else []
            number = 1
            has_next = False
            has_previous = False
            paginator = None
        return _Trivial(), 1

def _location_field_name_for_item():
    """Return the InventoryItem location field name, or None."""
    try:
        if _model_has_field(InventoryItem, "current_location"):
            return "current_location"
        if _model_has_field(InventoryItem, "location"):
            return "location"
    except Exception:
        pass
    return None


def default_location_for_request(request):
    """
    Best-effort default location for this user + active business.
    Tries:
      1) request.user.profile.[store|location|branch|current_location|default_store]
      2) First Location linked to InventoryItem's FK and active business
    Returns a Location-like instance or None.
    """
    user = getattr(request, "user", None)
    biz, biz_id = _require_active_business(request)

    # 1) user.profile hints
    prof = getattr(user, "profile", None)
    for attr in ("store", "location", "current_location", "default_store", "branch"):
        loc = getattr(prof, attr, None)
        if loc and (not biz_id or _obj_belongs_to_active_business(loc, request)):
            return loc

    # 2) infer model from InventoryItem's FK
    loc_field_nm = _location_field_name_for_item()
    if not loc_field_nm:
        return None
    try:
        loc_field = InventoryItem._meta.get_field(loc_field_nm)
        Loc = getattr(getattr(loc_field, "remote_field", None), "model", None)
        if not Loc:
            return None
        qs = Loc.objects.all()
        if biz_id:
            qs = qs.filter(**_biz_filter_kwargs(Loc, biz_id))
        return qs.order_by("id").first()
    except Exception:
        return None


def _restrict_location_to_default_store(form, request, *, set_initial=True):
    """
    Limit the form's location field queryset to ONLY the user's default location.
    Optionally set it as initial.
    Returns the chosen default (or None).
    """
    # find form field
    loc_field_form = None
    if "current_location" in form.fields:
        loc_field_form = "current_location"
    elif "location" in form.fields:
        loc_field_form = "location"
    else:
        return None  # no location field in this form

    default_loc = default_location_for_request(request)

    # Narrow the queryset to the single location (or none if we couldn't resolve)
    try:
        if default_loc is not None:
            LocModel = default_loc.__class__
            form.fields[loc_field_form].queryset = LocModel.objects.filter(pk=getattr(default_loc, "pk", None))
            if set_initial:
                form.fields[loc_field_form].initial = getattr(default_loc, "pk", None)
            # Make the widget show only the one option (nice UX)
            form.fields[loc_field_form].empty_label = None
        else:
            form.fields[loc_field_form].queryset = form.fields[loc_field_form].queryset.none()
            form.fields[loc_field_form].help_text = (
                (form.fields[loc_field_form].help_text or "") +
                " No store found for your account. Ask an admin to set your store."
            ).strip()
    except Exception:
        # If anything odd happens, don't crash the page
        pass

    return default_loc


def _limit_form_querysets(form, request):
    """
    Constrain ScanIn/ScanSold/InventoryItem forms to the active business,
    and preselect the default store as location.
    """
    try:
        if not hasattr(form, "fields"):
            return

        # Products -> only those in this business (order nicely)
        if "product" in form.fields:
            form.fields["product"].queryset = _scoped(
                Product.objects.order_by("brand", "model", "variant", "name"),
                request,
            )

        # Locations -> scope & default to store
        if "location" in form.fields:
            qs = _scoped(Location.objects.order_by("name"), request)
            form.fields["location"].queryset = qs
            default_loc = default_location_for_request(request)
            if default_loc:
                form.fields["location"].initial = getattr(default_loc, "pk", default_loc.id)
    except Exception:
        # never break the page on scoping issues
        pass
# -----------------------
# Scan pages (tenant-scoped)
# -----------------------
from django.apps import apps
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
# -------- Canonical location resolver (single source of truth) --------
from functools import wraps

from django.apps import apps

# ---------- Active business helpers (tuple-safe) ----------
from functools import wraps

from django.apps import apps

def _get_model(app_label, model):
    try:
        return apps.get_model(app_label, model)
    except Exception:
        return None

BusinessModel = _get_model("tenants", "Business")
# Prefer your tenants util if present
try:
    from circuitcity.tenants.utils import get_active_business as _get_active_business  # use project helper if available
except Exception:
    # Fall back to the local implementation defined above in this file
    pass


def get_active_business_pair(request):
    """
    Returns (business_obj_or_None, business_id_or_None).
    """
    biz = _get_active_business(request)
    return biz, getattr(biz, "id", None)
# =========================
# Active business helpers
# =========================

def _set_active_business(request, biz):
    """Persist active business on the session and request object."""
    request.session["active_business_id"] = biz.id
    request.active_business = biz
    request.active_business_id = biz.id


def _get_active_business_from_session(request):
    bid = request.session.get("active_business_id")
    if not bid:
        return None
    try:
        return BusinessModel.objects.get(id=bid)
    except BusinessModel.DoesNotExist:
        return None


def _get_user_businesses(request):
    """Adjust this queryset to match your membership model/relations."""
    u = request.user
    # If you use a many-to-many like Business.managers or members, filter accordingly.
    qs = BusinessModel.objects.all()
    try:
        # Prefer a managers field if you have it
        return qs.filter(managers=u)
    except Exception:
        # Fallback: own/created_by, etc.
        return qs.filter(owner=u) if hasattr(BusinessModel, "owner") else qs.none()


def _get_active_business(request):
    """
    Returns the currently active Business or None.
    Strategy:
      1) Session
      2) If user has exactly one business, auto-select it
      3) Otherwise, None (caller may redirect to join/select)
    """
    biz = _get_active_business_from_session(request)
    if biz:
        return biz

    # Auto-select if the user has exactly one business
    my_biz = list(_get_user_businesses(request)[:2])
    if len(my_biz) == 1:
        _set_active_business(request, my_biz[0])
        return my_biz[0]

    return None


def get_active_business_pair(request):
    """Compatibility helper."""
    biz = _get_active_business(request)
    return biz, (biz.id if biz else None)


def require_active_business(view):
    """
    Decorator for inventory views: ensures an active business.
    If user has one business, auto-selects it; otherwise redirects to join/select.
    """
    from functools import wraps
    from django.shortcuts import redirect

    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        biz = _get_active_business(request)
        if not biz:
            # If they have multiple businesses, send them to a selector if you have one.
            # Otherwise, to join/create.
            return redirect("tenants:join_business")
        return view(request, *args, **kwargs)

    return _wrapped

def _resolve_default_location_id(request):
    """
    Priority:
      1) ?location=<id>
      2) session['active_location_id']
      3) request.user.profile.default_location_id (or home_location_id)
      4) the only location the user manages (if exactly one)
      5) the only location under the active business (if exactly one)
      6) DEBUG: first Location (dev convenience)
    """
    if not Location:
        return None

    # 1) explicit
    lid = request.GET.get("location")
    if lid and str(lid).isdigit():
        return int(lid)

    # 2) session
    lid = request.session.get("active_location_id")
    if lid:
        return lid

    # 3) profile default/home
    prof = getattr(request.user, "profile", None)
    for attr in ("default_location_id", "home_location_id"):
        lid = getattr(prof, attr, None) if prof else None
        if lid:
            return lid

    # 4) exactly one managed location
    try:
        managed = Location.objects.filter(managers=request.user).values_list("id", flat=True)
        if managed.count() == 1:
            return managed.first()
    except Exception:
        pass

    # 5) only location in active business
    try:
        biz, biz_id = _require_active_business(request)
        if biz:
            locs = Location.objects.filter(business_id=biz.id).values_list("id", flat=True)
            if locs.count() == 1:
                return locs.first()
    except Exception:
        pass

    # 6) dev convenience
    if getattr(settings, "DEBUG", False):
        first = Location.objects.values_list("id", flat=True).first()
        if first:
            return first
    return None

def with_active_location(view):
    """Decorator: sets request.active_location(_id) and persists to session."""
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        lid = _resolve_default_location_id(request)
        request.active_location_id = lid
        request.active_location = Location.objects.filter(id=lid).first() if (Location and lid) else None
        if lid:
            request.session["active_location_id"] = lid
        return view(request, *args, **kwargs)
    return _wrapped

def filter_by_location_and_business(qs, request):
    """
    Reusable filter that works with either `location` or `current_location`,
    and with/without business field.
    """
    model = qs.model
    fields = {f.name for f in model._meta.get_fields()}

    # business
    if ("business" in fields) or ("business_id" in fields):
        biz, biz_id = _require_active_business(request)
        if biz:
            qs = qs.filter(business_id=biz.id)

    # location
    lid = getattr(request, "active_location_id", None) or request.session.get("active_location_id")
    if lid:
        if ("location" in fields) or ("location_id" in fields):
            qs = qs.filter(location_id=lid)
        elif ("current_location" in fields) or ("current_location_id" in fields):
            qs = qs.filter(current_location_id=lid)
    return qs



# --- PART 1/3 ENDS ---
# --- PART 2/3 â€” circuitcity/inventory/views.py (cleaned) ---

# stdlib
import csv
import json
import logging
import datetime
from decimal import Decimal

# django
from .forms import MerchProductForm, MerchUnitPriceFormSet
from .models import BusinessKind, MerchProduct
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import (
    Q, Sum, Value, Exists, OuterRef, DecimalField,
)
from django.db.models.functions import Coalesce
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template import TemplateDoesNotExist
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_http_methods

# optional OTP decorator (be forgiving if the package name differs or is missing)
try:
    from two_factor.decorators import otp_required  # django-two-factor-auth
except Exception:
    try:
        from django_otp.decorators import otp_required  # django-otp
    except Exception:
        def otp_required(view):
            return view

# ---- optional / defensive imports for models & forms -----------------------
try:
    from .models import InventoryItem as InventoryItem
except Exception:
    InventoryItem = None  # type: ignore

try:
    from .models import Location as Location
except Exception:
    Location = None  # type: ignore

try:
    from sales.models import Sale as Sale
except Exception:
    Sale = None  # type: ignore

try:
    from .forms import ScanInForm, ScanSoldForm
except Exception:
    ScanInForm = None  # type: ignore
    ScanSoldForm = None  # type: ignore

# ---- your project helpers (assumed defined in PART 1/3) --------------------
# _require_active_business, _attach_business_kwargs, _biz_filter_kwargs,
# _model_has_field, _obj_belongs_to_active_business, _limit_form_querysets,
# _audit, _user_home_location, _can_view_all, _is_manager_or_admin, _scoped
# (We just call them; they live in your other parts.)

# ---------------------------------------------------------------------------
# SCAN SOLD
# ---------------------------------------------------------------------------

# --- add this tiny helper once near the top of views.py (outside any view) ---
# -----------------------------------------------------------------------------
# --- Wallet page (agent) ------------------------------------------------------
from django.shortcuts import get_object_or_404, render, redirect
from django.core.paginator import Paginator
from django.utils import timezone
from django.db.models import Sum
from django.contrib.auth import get_user_model

from .models import WalletTxn  # make sure this import exists

def wallet_page(request):
    """
    Simple read-only wallet page for a specific agent.
    URL expected: /inventory/wallet/?user=<id>  (your urls.py already routes here)
    """
    User = get_user_model()

    # Accept ?user= or ?agent= for convenience
    uid = request.GET.get("user") or request.GET.get("agent")
    if not uid:
        # Nothing to show; send them back to stock list (or anywhere you prefer)
        return redirect("/inventory/list/")

    target = get_object_or_404(User, pk=uid)

    # Balance (lifetime sum)
    balance = (
        WalletTxn.objects.filter(user=target)
        .aggregate(s=Sum("amount"))["s"] or 0
    )

    # Monthly window (local time)
    today = timezone.localdate()
    month_start = today.replace(day=1)
    next_month = (month_start.replace(day=28) + timezone.timedelta(days=4)).replace(day=1)

    monthly_total = (
        WalletTxn.objects.filter(user=target, created_at__gte=month_start, created_at__lt=next_month)
        .aggregate(s=Sum("amount"))["s"] or 0
    )

    # Optional breakdowns (you used these in the template)
    monthly_adv = (
        WalletTxn.objects.filter(
            user=target,
            created_at__gte=month_start, created_at__lt=next_month,
            reason="ADVANCE",
        ).aggregate(s=Sum("amount"))["s"] or 0
    )
    lifetime_total = balance  # lifetime earnings == balance if no payouts are modeled separately

    # Paginated transaction list
    txns_qs = WalletTxn.objects.filter(user=target).order_by("-created_at")
    paginator = Paginator(txns_qs, 25)
    page = request.GET.get("page") or 1
    page_obj = paginator.get_page(page)

    # Helper for the pager links
    def url_for(n):
        q = request.GET.copy()
        q["page"] = n
        return f"{request.path}?{q.urlencode()}"

    ctx = {
        "target": target,
        "balance": balance,
        "monthly_total": monthly_total,
        "monthly_adv": monthly_adv,
        "lifetime_total": lifetime_total,
        "txns": page_obj.object_list,
        "page_obj": page_obj,
        "url_for": url_for,
    }
    return render(request, "agents/wallet.html", ctx)

# ---------------------------------------------------------------------------
# SCAN WEB
# ---------------------------------------------------------------------------

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
  <title>Scan (Web) â€” Fallback</title>
  <style>body{font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;padding:24px;}
  .wrap{max-width:640px;margin:auto}.f{display:flex;gap:8px}</style>
</head>
<body>
  <div class="wrap">
    <h2>Scan (Web) â€” Fallback</h2>
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

# ---------------------------------------------------------------------------
# SCAN IN  (single, consolidated version)
# ---------------------------------------------------------------------------

from django.views.decorators.cache import never_cache
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.shortcuts import render, redirect
from django.core.exceptions import ValidationError
from decimal import Decimal
import logging

# --- Inventory Â· Scan IN (paste over your current function) ---
# put this tiny helper once near the top of views.py (outside the function)

@never_cache
@login_required
@require_business
@require_role(["Manager", "Admin", "Agent"])
@require_http_methods(["GET", "POST"])
@transaction.atomic
def scan_in(request):
    """
    Inventory Â· Scan IN
    HTML by default; JSON only when ?as=json or XHR.

    Updates:
      - Validates IMEI/serial length using single source of truth (core.business_rules) via inventory.validators.
      - Works for models that use either `imei` OR `serial` (or both). Prefers `imei` if present.
      - Duplicate guard checks the correct identifier field within the active business.
    """
    # --- local imports (keeps module import-time light) ---
    import logging
    from decimal import Decimal
    from django.conf import settings
    from django.utils import timezone
    from django.core.exceptions import ValidationError
    from django.db import IntegrityError
    from django.forms import ModelChoiceField
    from django.contrib import messages
    from django.shortcuts import redirect, render
    from django.http import JsonResponse

    # serial/IMEI validation (single source of truth)
    try:
        from inventory.validators import validate_serial_for_request  # type: ignore
    except Exception:
        validate_serial_for_request = None  # type: ignore

    # single-source-of-truth helpers
    from inventory.helpers.request_ctx import (
        ensure_request_defaults,
        _get_active_business,
        default_location_for_request,
    )

    # Local fallback for wants-json detection (uses global if present)
    _wants_json_fn = globals().get("_wants_json")
    def _wants_json(req):
        if callable(_wants_json_fn):
            return _wants_json_fn(req)
        # Lightweight heuristic fallback
        return (req.GET.get("as") == "json") or (req.headers.get("X-Requested-With") == "XMLHttpRequest")

    log = logging.getLogger(__name__)
    template_name = "inventory/scan_in.html"
    # ---- Merchandise product create (PAGE) ---------------------------------
    from django.shortcuts import render, redirect
    from django.contrib import messages

    def merch_product_create(request):
        """
        Renders the Add Product form and saves Product + inline UnitPrice rows.
        Form classes are imported locally so missing forms won't break module import.
        """
        # Local import avoids ImportError on module import time
        try:
            from .forms import MerchProductForm, MerchUnitPriceFormSet
        except Exception:  # keep the page from crashing if forms not present
            messages.error(request, "Product form not available yet.")
            return redirect("inventory:stock_list")

        # Try to prefill the current business on the form
        biz_id = getattr(request, "business_id", None) or (
            getattr(request, "session", {}).get("active_business_id")
            if hasattr(request, "session") else None
        )
        initial = {"business": biz_id} if biz_id else {}

        if request.method == "POST":
            form = MerchProductForm(request.POST, initial=initial)
            formset = MerchUnitPriceFormSet(request.POST, prefix="unitprice_set")
            if form.is_valid() and formset.is_valid():
                product = form.save()
                prices = formset.save(commit=False)
                for p in prices:
                    p.product = product
                    p.save()
                messages.success(request, "Product created.")
                return redirect("inventory:stock_list")
            else:
                messages.error(request, "Please fix the errors below.")
        else:
            form = MerchProductForm(initial=initial)
            formset = MerchUnitPriceFormSet(prefix="unitprice_set")

        return render(
            request,
            "inventory/product_create.html",
            {
                "form": form,
                "formset": formset,
                # tells the template which variant of the UI to show (phones/liquor/etc.)
                "PRODUCT_MODE": getattr(request, "product_mode", None) or "generic",
            },
        )

    # ---------- Ensure active business/location ----------
    biz, biz_id = _get_active_business(request)
    if not biz_id:
        messages.error(request, "No active business selected. Switch business and try again.")
        try:
            return redirect("tenants:activate_mine")
        except Exception:
            return redirect("/tenants/activate-mine/")

    ensure_request_defaults(request)

    # ---------- Forbid superusers on POST ----------
    if request.user.is_superuser and request.method == "POST":
        messages.error(request, "Superusers cannot stock-in devices.")
        return redirect("inventory:stock_list")


    # ---------- tiny helpers ----------
    def _model_has_field(model, name):
        try:
            return any(f.name == name for f in getattr(model, "_meta").get_fields())
        except Exception:
            return False

    def _biz_filter_kwargs(model, business_id):
        if _model_has_field(model, "business_id"):
            return {"business_id": business_id}
        if _model_has_field(model, "business"):
            return {"business_id": business_id}
        return {}

    def _attach_business_kwargs(model, business_id):
        return _biz_filter_kwargs(model, business_id)

    def _obj_belongs_to_active_business(obj):
        try:
            if hasattr(obj, "business_id"):
                return obj.business_id == biz_id
            if hasattr(obj, "business") and getattr(obj, "business", None):
                return getattr(obj.business, "id", None) == biz_id
        except Exception:
            pass
        return True

    # ---------- models/forms ----------
    try:
        from .models import InventoryItem
    except Exception:
        InventoryItem = None
    try:
        from .forms import ScanInForm
    except Exception:
        ScanInForm = None

    if InventoryItem is None or ScanInForm is None:
        messages.error(request, "Inventory model or form not available.")
        return redirect("inventory:stock_list")

    # ---------- defaults ----------
    default_loc = default_location_for_request(request)
    dflt_pk = getattr(default_loc, "pk", getattr(default_loc, "id", None)) if default_loc else None

    today = timezone.localdate()
    page_initial = {"received_at": today}
    if dflt_pk is not None:
        for key in ("location", "current_location", "store", "branch"):
            page_initial[key] = dflt_pk

    biz_create_kwargs = _attach_business_kwargs(InventoryItem, biz_id)

    # which FK name carries location?
    def _loc_field_name():
        if _model_has_field(InventoryItem, "current_location"):
            return "current_location"
        if _model_has_field(InventoryItem, "location"):
            return "location"
        return None

    loc_field_name = _loc_field_name()
    loc_is_required = False
    if loc_field_name:
        try:
            loc_field_obj = InventoryItem._meta.get_field(loc_field_name)
            loc_is_required = not getattr(loc_field_obj, "null", True)
        except Exception:
            pass

    # clamp form location to user's default store
    def _restrict_location_to_user_store(form, set_initial=True):
        if not default_loc:
            return
        fname = next((n for n in ("location", "current_location", "store", "branch")
                      if n in form.fields and isinstance(form.fields[n], ModelChoiceField)), None)
        if not fname:
            return
        fld = form.fields[fname]
        dpk = dflt_pk

        def _label(loc_obj):
            b = getattr(request, "business", None)
            if b and getattr(b, "name", None):
                return str(b.name).strip()
            for attr in ("store_name", "name", "title", "label"):
                v = getattr(loc_obj, attr, None)
                if v:
                    return str(v)
            return str(loc_obj)

        try:
            fld.empty_label = None
        except Exception:
            pass
        fld.choices = [(dpk, _label(default_loc))]
        try:
            qs = getattr(fld, "queryset", None)
            if qs is not None:
                fld.queryset = qs.model.objects.filter(pk=dpk)
        except Exception:
            pass
        if set_initial:
            fld.initial = dpk

    # ---------- JSON boot (for HTMX/fetch; opt-in) ----------
    locations_boot = []
    try:
        if default_loc is not None:
            LocCls = default_loc.__class__
            q = LocCls.objects.all()
            if any(f.name in ("business", "business_id") for f in LocCls._meta.get_fields()):
                q = q.filter(business_id=biz_id)
            locations_boot = list(q.values("id", "name"))
    except Exception:
        locations_boot = []

    boot = {
        "ok": True,
        "data": {
            "note": "scan_in ready",
            "received_date_default": today.isoformat(),
            "location_default": dflt_pk,
            "auto_submit_default": False,
            "locations": locations_boot,
        },
    }

    # ===================== POST =====================
    if request.method == "POST":
        post_data = request.POST.copy()

        # force location to user's store when missing
        if dflt_pk is not None:
            for key in ("location", "current_location", "store", "branch"):
                if not post_data.get(key):
                    post_data[key] = str(dflt_pk)

        if not post_data.get("received_at"):
            post_data["received_at"] = today

        form = ScanInForm(post_data)
        _restrict_location_to_user_store(form, set_initial=False)

        if not form.is_valid():
            if _wants_json(request):
                return JsonResponse({"ok": False, "errors": form.errors}, status=400)
            messages.error(request, "Please correct the errors below.")
            return render(request, template_name, {
                "form": form,
                "default_location": default_loc,
                "loc_is_required": loc_is_required,
                "is_agent_user": True,
                "today": today,
            })

        data = form.cleaned_data

        # Product required and must belong to active business
        product = data.get("product")
        if not product or not _obj_belongs_to_active_business(product):
            msg = "Select a valid product model in your store."
            if _wants_json(request):
                return JsonResponse({"ok": False, "error": msg}, status=400)
            messages.error(request, msg)
            return render(request, template_name, {"form": form})

        # Resolve location respecting model field
        location_obj = data.get("location") or data.get("current_location") or default_loc
        if loc_is_required and not location_obj:
            msg = "Your inventory requires a location; none found for this store."
            if _wants_json(request):
                return JsonResponse({"ok": False, "error": msg}, status=400)
            messages.error(request, msg)
            return render(request, template_name, {"form": form})

        # ---- Serial/IMEI (single source of truth rules) ----
        # Prefer explicit form fields; fall back to empty
        form_imei = (data.get("imei") or "").strip()
        form_serial = (data.get("serial") or "").strip()
        # Choose which identifier field we will use on the model
        model_uses_imei = _model_has_field(InventoryItem, "imei")
        model_uses_serial = _model_has_field(InventoryItem, "serial")

        chosen_value_raw = None
        chosen_field_name = None
        if model_uses_imei:
            chosen_value_raw = form_imei or form_serial  # tolerate forms that post "serial"
            chosen_field_name = "imei"
        elif model_uses_serial:
            chosen_value_raw = form_serial or form_imei  # tolerate forms that post "imei"
            chosen_field_name = "serial"

        cleaned_identifier = None
        if chosen_field_name and chosen_value_raw:
            try:
                if validate_serial_for_request:
                    cleaned_identifier = validate_serial_for_request(request, chosen_value_raw)
                else:
                    # Fallback: minimal guard (digits-only)
                    s = chosen_value_raw.replace(" ", "")
                    if not s.isdigit():
                        raise ValidationError("Serial must contain digits only.")
                    cleaned_identifier = s
            except ValidationError as ve:
                msg = ve.messages[0] if ve.messages else "Invalid serial value."
                if _wants_json(request):
                    return JsonResponse({"ok": False, "error": msg}, status=400)
                messages.error(request, msg)
                return render(request, template_name, {"form": form})

        # ---- Duplicate guard within this business ----
        try:
            with transaction.atomic():
                dup_qs = InventoryItem.objects.select_for_update()
                if biz_id:
                    dup_qs = dup_qs.filter(**_biz_filter_kwargs(InventoryItem, biz_id))

                if cleaned_identifier and chosen_field_name and _model_has_field(InventoryItem, chosen_field_name):
                    if dup_qs.filter(**{chosen_field_name: cleaned_identifier}).exists():
                        msg = f"Item with {chosen_field_name.upper()} {cleaned_identifier} already exists in your store."
                        if _wants_json(request):
                            return JsonResponse({"ok": False, "error": msg}, status=400)
                        messages.error(request, msg)
                        return render(request, template_name, {"form": form})

                create_kwargs = {}
                if _model_has_field(InventoryItem, "product"):
                    create_kwargs["product"] = product

                if location_obj:
                    if _model_has_field(InventoryItem, "current_location"):
                        create_kwargs["current_location"] = location_obj
                    elif _model_has_field(InventoryItem, "location"):
                        create_kwargs["location"] = location_obj

                # safe defaults to ensure visibility in Stock
                if _model_has_field(InventoryItem, "received_at"):
                    create_kwargs["received_at"] = data.get("received_at") or today
                if _model_has_field(InventoryItem, "order_price"):
                    create_kwargs["order_price"] = data.get("order_price") or Decimal("0.00")

                if cleaned_identifier and chosen_field_name and _model_has_field(InventoryItem, chosen_field_name):
                    create_kwargs[chosen_field_name] = cleaned_identifier

                if _model_has_field(InventoryItem, "status"):
                    create_kwargs.setdefault("status", "IN_STOCK")
                if _model_has_field(InventoryItem, "is_active"):
                    create_kwargs.setdefault("is_active", True)

                # attach business (hard requirement)
                create_kwargs.update(biz_create_kwargs)

                # validate & save
                item = InventoryItem(**create_kwargs)
                try:
                    item.full_clean()
                except ValidationError as ve:
                    first_err = "; ".join([f"{k}: {', '.join(v)}" for k, v in ve.message_dict.items()])
                    if _wants_json(request):
                        return JsonResponse({"ok": False, "error": f"Cannot stock-in: {first_err}"}, status=400)
                    messages.error(request, f"Cannot stock-in: {first_err}")
                    return render(request, template_name, {"form": form})

                # optional: attach owner-like field for agents
                for name in ("assigned_agent","assigned_to","assignee","owner","user","agent","created_by","added_by","received_by"):
                    if _model_has_field(InventoryItem, name) and not getattr(item, name, None):
                        try:
                            setattr(item, name, request.user)
                            break
                        except Exception:
                            pass

                item.save()

        except IntegrityError as e:
            msg = "Could not save this item (constraint error). Check values and try again."
            # Attempt to give a clearer message
            if "unique" in str(e).lower() and cleaned_identifier and chosen_field_name:
                msg = f"Item with {chosen_field_name.upper()} {cleaned_identifier} already exists."
            if _wants_json(request):
                return JsonResponse({"ok": False, "error": msg}, status=400)
            messages.error(request, msg)
            return render(request, template_name, {"form": form})
        except Exception:
            log.exception("Scan IN failed")
            if getattr(settings, "DEBUG", False):
                raise
            if _wants_json(request):
                return JsonResponse({"ok": False, "error": "Unexpected error while saving this item. Please try again."}, status=500)
            messages.error(request, "Unexpected error while saving this item. Please try again.")
            return render(request, template_name, {"form": form})

        if _wants_json(request):
            return JsonResponse({"ok": True, "message": "Item saved."})
        messages.success(request, "Item saved.")
        return redirect("inventory:stock_list")

    # ===================== GET -> HTML by default =====================
    form = ScanInForm(initial=page_initial)
    _restrict_location_to_user_store(form, set_initial=True)

    try:
        if dflt_pk is not None:
            for key in ("location", "current_location", "store", "branch"):
                if key in form.fields:
                    form.fields[key].initial = dflt_pk
    except Exception:
        pass

    # Only return JSON when explicitly requested
    if _wants_json(request):
        return JsonResponse(boot)

    ctx = {
        "form": form,
        "default_location": default_loc,
        "loc_is_required": loc_is_required,
        "today": today,
    }
    return render(request, template_name, ctx)

# inventory/views.py  (append)

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse, HttpRequest, HttpResponseBadRequest
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect
from django.db.models import Sum
from .models import Location as Store
# --- put near the top of inventory/views.py (with other helpers) ---
from django.apps import apps

def _get_inventory_model(*names):
    """
    Return the first model that exists in the 'inventory' app from the
    provided candidate names, else None (so views can degrade gracefully).
    """
    for name in names:
        try:
            m = apps.get_model('inventory', name)
            if m:
                return m
        except Exception:
            pass
    return None

# Try old and new names in order of likelihood
AgentStore = _get_inventory_model('AgentLocation', 'AgentStore', 'StoreLocation', 'Location')

import json
from datetime import date

def _is_manager(u):  # adjust to your own permission system
    return getattr(u, "is_staff", False) or u.groups.filter(name__iexact="Manager").exists()

@login_required
def api_geo_ping(request: HttpRequest) -> JsonResponse:
    """
    Agents call this via JS with current geolocation.
    Body: {lat, lon, accuracy}
    Determines agent's current store, updates timer, logs arrival/exit boundaries.
    """
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)
    try:
        body = json.loads(request.body or "{}")
        lat = float(body.get("lat"))
        lon = float(body.get("lon"))
        acc = float(body.get("accuracy") or 0)
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid payload"}, status=400)

    # Which store is the agent tied to?
    try:
        asg = request.user.agent_store
    except AgentStore.DoesNotExist:
        return JsonResponse({"ok": False, "error": "No store assignment"}, status=400)
    store = asg.store

    now = timezone.now()
    timer, _ = WorkTimer.objects.get_or_create(user=request.user, store=store, day=timezone.localdate())

    # Previous state
    was_in = timer.in_range

    res = timer.apply_ping(now, lat, lon)  # updates state and accumulators

    # Emit arrival/exit edges
    now_in = res["in_range"]
    if now_in != was_in:
        TimeEvent.objects.create(
            user=request.user, store=store,
            kind=(TimeEvent.ARRIVAL if now_in else TimeEvent.EXIT),
            at=now, latitude=lat, longitude=lon, accuracy_m=acc, distance_m=res["distance_m"]
        )

    return JsonResponse({"ok": True, **res})

@login_required
@user_passes_test(_is_manager)
def api_timers(request: HttpRequest) -> JsonResponse:
    """
    Manager: live timers for my stores (today).
    Optional query: store=<id>
    """
    store_id = request.GET.get("store")
    stores = Store.objects.filter(manager=request.user)
    if store_id:
        stores = stores.filter(pk=store_id)

    day = timezone.localdate()
    data = []
    for st in stores:
        tms = WorkTimer.objects.filter(store=st, day=day).select_related("user")
        for t in tms:
            data.append({
                "store": st.name, "user": t.user.get_username(),
                "in_range": t.in_range, "work_s": t.work_seconds, "away_s": t.away_seconds,
            })
    return JsonResponse({"ok": True, "items": data})

@login_required
@user_passes_test(_is_manager)
def api_month_summary(request: HttpRequest) -> JsonResponse:
    """
    Manager monthly totals per agent for a store.
    Query: store=<id>&month=YYYY-MM
    """
    store_id = request.GET.get("store")
    if not store_id:
        return JsonResponse({"ok": False, "error": "store is required"}, status=400)
    store = get_object_or_404(Store, pk=store_id, manager=request.user)

    month = request.GET.get("month")
    if month:
        y, m = map(int, month.split("-"))
        start = date(y, m, 1)
    else:
        today = timezone.localdate()
        start = date(today.year, today.month, 1)
    # end boundary
    if start.month == 12:
        end = date(start.year + 1, 1, 1)
    else:
        end = date(start.year, start.month + 1, 1)

    qs = WorkTimer.objects.filter(store=store, day__gte=start, day__lt=end).select_related("user")
    # aggregate per user
    aggregates = {}
    for t in qs:
        key = t.user.get_username()
        agg = aggregates.setdefault(key, {"user": key, "work_s": 0, "away_s": 0})
        agg["work_s"] += t.work_seconds
        agg["away_s"] += t.away_seconds

    items = list(aggregates.values())
    # grand totals for pie
    total_work = sum(i["work_s"] for i in items)
    total_away = sum(i["away_s"] for i in items)

    return JsonResponse({"ok": True, "items": items, "totals": {"work_s": total_work, "away_s": total_away}})
# inventory/views.py (optional simple form)
from django import forms
from django.shortcuts import render

class StoreGeoForm(forms.ModelForm):
    class Meta:
        model = Store
        fields = ("name","latitude","longitude","geofence_radius_m")

@login_required
@user_passes_test(_is_manager)
def store_settings(request, pk:int):
    store = get_object_or_404(Store, pk=pk, manager=request.user)
    if request.method == "POST":
        form = StoreGeoForm(request.POST, instance=store)
        if form.is_valid():
            form.save()
            return redirect("inventory:time_logs")
    else:
        form = StoreGeoForm(instance=store)
    return render(request, "inventory/store_settings.html", {"form": form, "store": store})

@login_required
@user_passes_test(_is_manager)
def transfer_agent(request: HttpRequest, pk: int, user_id: int):
    """
    Move an agent to another store (manager-owned only).
    """
    store = get_object_or_404(Store, pk=pk, manager=request.user)
    asg = get_object_or_404(AgentStore, user_id=user_id)
    asg.store = store
    asg.save(update_fields=["store"])
    return redirect("inventory:time_logs")  # adjust to your time logs route name


def merch_product_create(request):
    """
    Add Product page (renders MerchProductForm + inline price rows).
    If POST is valid, saves and redirects to stock list.
    """
    log = logging.getLogger(__name__)
    log.info("merch_product_create: %s %s", request.method, request.path)

    # If your middleware attaches an active business to the request,
    # grab it so the form can scope choices correctly.
    business = getattr(request, "business", None) or getattr(request, "active_business", None)

    if request.method == "POST":
        form = MerchProductForm(request.POST, business=business)
        formset = MerchUnitPriceFormSet(request.POST, prefix="unitprice_set")
        if form.is_valid() and formset.is_valid():
            product = form.save()
            formset.instance = product
            formset.save()
            messages.success(request, "Product created.")
            try:
                return redirect("inventory:stock_list")
            except Exception:
                return redirect("/inventory/list/")
    else:
        form = MerchProductForm(business=business)
        formset = MerchUnitPriceFormSet(prefix="unitprice_set")

    ctx = {"form": form, "formset": formset}
    return render(request, "inventory/product_create.html", ctx)



# inventory/views.py



from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

# ----- Optional Sales model (Order) ---------------------------------
# If the sales app (or Order model) isn't available, fall back gracefully.
try:
    from sales.models import Order  # type: ignore
except Exception:
    Order = None  # type: ignore[assignment]


# inventory/views.py


from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

# ---- optional Sales model (Order) ----
try:
    from sales.models import Order  # type: ignore
except Exception:
    Order = None  # type: ignore[assignment]


@login_required
@require_GET
def orders_list(request: HttpRequest) -> HttpResponse:
    """
    Orders table page. If Order exists, paginate it; otherwise
    show a friendly empty state. Never 501.
    """
    if Order is None:
        return render(
            request,
            "inventory/orders_list.html",
            {"page_obj": None, "orders": [], "message": "Orders model not available yet."},
        )

    qs = Order.objects.all().order_by("-id")

    # optional filters
    status = request.GET.get("status")
    if status:
        try:
            qs = qs.filter(status=status)
        except Exception:
            pass

    q = request.GET.get("q")
    if q:
        for field in ("reference", "number", "customer_name"):
            try:
                qs = qs.filter(**{f"{field}__icontains": q})
                break
            except Exception:
                continue

    try:
        per_page = int(request.GET.get("per_page") or 25)
    except Exception:
        per_page = 25

    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "inventory/orders_list.html",
        {"page_obj": page_obj, "orders": page_obj.object_list},
    )

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse, NoReverseMatch
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required
from django.template.exceptions import TemplateDoesNotExist
from django.http import HttpResponse, HttpResponseBase

def _normalize_response(request, resp):
    """
    Ensure we always return a Django HttpResponse, never a tuple.
    Handles common mistakes like (response,), (response, status),
    or (template_name, ctx).
    """
    if isinstance(resp, (HttpResponse, HttpResponseBase)):
        return resp
    if isinstance(resp, tuple):
        # If one of the items is an HttpResponse, return it.
        for item in resp:
            if isinstance(item, (HttpResponse, HttpResponseBase)) or hasattr(item, "has_header"):
                return item
        # Maybe got (template_name, context) by mistake â€” render it.
        if len(resp) == 2 and isinstance(resp[0], str) and isinstance(resp[1], dict):
            return render(request, resp[0], resp[1])
        # Fallback: just take the first element if it quacks like a response
        first = resp[0]
        if hasattr(first, "has_header"):
            return first
        raise TypeError(f"Unexpected tuple return from view: {type(resp)} {resp!r}")
    return resp  # allow None for gates; caller should handle

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse, NoReverseMatch
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required
from django.template.exceptions import TemplateDoesNotExist
from django.http import HttpResponse, HttpResponseBase

def _as_http_response(resp):
    """Return resp if it is a real HttpResponse, else None."""
    if isinstance(resp, (HttpResponse, HttpResponseBase)) or hasattr(resp, "has_header"):
        return resp
    return None

@never_cache
@login_required
@require_GET
def place_order_page(request):
    """
    Purchase Order page (manager/admin only).
    - Requires an active business (tenant).
    - Soft OTP gate (no @otp_required to avoid AttributeError when OTP isn't wired).
    - Robust to helpers that accidentally return tuples.
    """

    # ---- tenant gate ----
    gate = _require_active_business(request)

    # _require_active_business sometimes returns tuples; handle them:
    #   - (HttpResponse, ...) -> return that response
    #   - (<Business ...>, None) or (<Business ...>, biz_id) -> OK (treat as None)
    #   - anything else tuple: scan for an HttpResponse; otherwise ignore
    if isinstance(gate, tuple):
        # 1) If any element is an HttpResponse, return it
        for item in gate:
            hr = _as_http_response(item)
            if hr is not None:
                return hr
        # 2) If first element looks like a Business instance, treat as "gate passed"
        first = gate[0] if gate else None
        looks_like_business = (
            first is not None
            and hasattr(first, "_meta")
            and getattr(getattr(first, "_meta", None), "model_name", "") == "business"
        )
        if looks_like_business:
            gate = None
        else:
            # Fallthrough: nothing actionable in the tuple; treat as no gate
            gate = None

    # If gate is a plain HttpResponse (redirect, etc.), return it
    if _as_http_response(gate) is not None:
        return gate

    # ---- soft OTP gate (DON'T use @otp_required here) ----
    is_otp_verified = True
    try:
        if hasattr(request.user, "is_verified") and callable(request.user.is_verified):
            is_otp_verified = bool(request.user.is_verified())
    except Exception:
        is_otp_verified = True  # fail-open

    if not is_otp_verified:
        messages.error(request, "Please complete 2-factor verification to place orders.")
        try:
            return redirect(reverse("two_factor:login"))
        except NoReverseMatch:
            return redirect("accounts:login")

    # ---- role gate ----
    if not _is_manager_or_admin(request.user):
        messages.error(request, "Only managers or admins can place purchase orders.")
        return redirect("inventory:stock_list")

    # ---- render page ----
    ctx = {}
    try:
        return render(request, "inventory/place_order.html", ctx)
    except TemplateDoesNotExist:
        return render(request, "inventory/place_order_fallback.html", ctx)
    # --- Agent detail + assignment ----------------------------------------------
    from django.shortcuts import get_object_or_404, render, redirect
    from django.contrib import messages
    from django.core.paginator import Paginator
    from django.db.models import Sum
    from django.db import transaction
    from django.utils import timezone
    from django.contrib.auth import get_user_model

    from .models import Location, AgentProfile, WalletTxn

    User = get_user_model()

    def _active_business(request):
        """Best-effort way to discover the tenant/business on the request."""
        return (
                getattr(request, "business", None)
                or getattr(request, "active_business", None)
                or getattr(getattr(request, "tenant", None), "business", None)
        )

    def _url_for_page(request, page_num: int) -> str:
        q = request.GET.copy()
        q["page"] = page_num
        sep = "&" if "?" in request.get_full_path() else "?"
        return f"{request.path}{sep}{q.urlencode()}"

    def agent_detail(request, agent_id: int):
        """
        Shows agent info + wallet + simple location assignment UI.
        Template: inventory/agent_detail.html
        """
        target = get_object_or_404(User, pk=agent_id)

        # Limit locations to the active business (if we can detect one)
        biz = _active_business(request)
        loc_qs = Location.objects.all().order_by("name")
        if biz:
            loc_qs = loc_qs.filter(business=biz)

        # Wallet numbers
        month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        lifetime_total = (WalletTxn.objects.filter(user=target)
                          .aggregate(s=Sum("amount"))["s"] or 0)
        monthly_total = (WalletTxn.objects.filter(user=target, created_at__gte=month_start)
                         .aggregate(s=Sum("amount"))["s"] or 0)
        monthly_adv = (WalletTxn.objects.filter(
            user=target, created_at__gte=month_start, reason="ADVANCE"
        ).aggregate(s=Sum("amount"))["s"] or 0)
        balance = lifetime_total  # credits minus debits

        # Paginated transactions
        txns = WalletTxn.objects.filter(user=target).order_by("-created_at")
        page_obj = Paginator(txns, 25).get_page(request.GET.get("page") or 1)

        ctx = {
            "target": target,
            "locations": list(loc_qs),
            "txns": page_obj.object_list,
            "page_obj": page_obj,
            "url_for": lambda p: _url_for_page(request, p),
            "balance": balance,
            "monthly_total": monthly_total,
            "monthly_adv": monthly_adv,
            "lifetime_total": lifetime_total,
        }
        return render(request, "inventory/agent_detail.html", ctx)

    @transaction.atomic
    def agent_assign_location(request, agent_id: int):
        """
        POST handler for the small assignment form in agent_detail.html.
        Redirects back to the detail page with a flash message.
        """
        if request.method != "POST":
            return redirect("inventory:agent_detail", agent_id=agent_id)

        target = get_object_or_404(User, pk=agent_id)
        loc_id = request.POST.get("location_id")
        if not loc_id:
            messages.error(request, "Choose a location.")
            return redirect("inventory:agent_detail", agent_id=agent_id)

        loc = get_object_or_404(Location, pk=loc_id)

        # Optional tenant safety: block cross-tenant assignment if we can detect biz
        biz = _active_business(request)
        if biz and loc.business_id and loc.business_id != getattr(biz, "id", None):
            messages.error(request, "That location does not belong to your business.")
            return redirect("inventory:agent_detail", agent_id=agent_id)

        # Ensure the agent has a profile, then update location
        profile, _created = AgentProfile.objects.get_or_create(
            user=target, defaults={"location": loc}
        )
        profile.location = loc
        profile.save()

        messages.success(request, f"Assigned {target.get_username()} to {loc.name}.")
        return redirect("inventory:agent_detail", agent_id=agent_id)

    # ------------------------------
    # PAGE: Add Product (manager/admin)
    # ------------------------------
    @login_required
    @require_business
    def product_create(request):
        """
        Form for managers to add new products.
        Supports both IMEI-based products (phones)
        and quantity-based items (liquor, groceries, pharmacy).
        """
        from .forms import ProductForm  # make sure you add this in forms.py

        if request.method == "POST":
            form = ProductForm(request.POST)
            if form.is_valid():
                product = form.save(commit=False)
                product.business = request.business  # tenant scope
                product.save()
                return redirect("inventory:stock_list")
        else:
            form = ProductForm()

        return render(request, "inventory/product_create.html", {"form": form})


# ---------------------------------------------------------------------------
# API: MARK SOLD
# ---------------------------------------------------------------------------

# inventory/views_api.py  (or wherever api_mark_sold lives)

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
import json

# assumes these helpers / models already exist in your codebase
# _require_active_business, _is_auditor, _model_has_field,
# _biz_filter_kwargs, _attach_business_kwargs, _audit,
# InventoryItem, Location, Sale

def _parse_sold_date(val):
    """
    Accepts 'YYYY-MM-DD' or returns today's local date.
    """
    if not val:
        return timezone.localdate()
    try:
        # Be generous about inputâ€”DateInput sends YYYY-MM-DD
        return timezone.datetime.strptime(str(val), "%Y-%m-%d").date()
    except Exception:
        return timezone.localdate()

def _sold_choice_for(model):
    """
    If the model defines a SOLD constant/choice (e.g. STATUS_SOLD / SOLD),
    use it. Otherwise fall back to literal 'SOLD'.
    """
    for attr in ("STATUS_SOLD", "STATE_SOLD", "STATUS__SOLD", "SOLD"):
        if hasattr(model, attr):
            return getattr(model, attr)
    # fall back to string
    return "SOLD"

from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils import timezone
from django.db.models import Q
import json


from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils import timezone

# ---------------------------
# tiny local helpers (single source of truth)
# ---------------------------

def _model_has_field(model, name: str) -> bool:
    try:
        model._meta.get_field(name)
        return True
    except Exception:
        return False

def _active_business_from_request(request):
    """Return (biz, biz_id) without relying on custom middleware."""
    biz = getattr(request, "business", None)
    return biz, getattr(biz, "id", None)

def _biz_filter_kwargs(model, biz_id):
    """Map a business id onto the model using common FK names."""
    names = {f.name for f in model._meta.get_fields()}
    if "business_id" in names:
        return {"business_id": biz_id}
    if "tenant_id" in names:
        return {"tenant_id": biz_id}
    if "store_id" in names:
        return {"store_id": biz_id}
    if "business" in names:
        return {"business_id": biz_id}
    return {}

def _sold_status_key(model):
    """
    Resolve the *internal* choice key for 'sold' on the model.status field.
    Works with TextChoices/choices list. Falls back to 'SOLD'.
    """
    try:
        f = model._meta.get_field("status")
        choices = getattr(f, "choices", None)
        if choices:
            for pair in choices:
                try:
                    key, label = pair
                except Exception:
                    key = getattr(pair, "value", None)
                    label = getattr(pair, "label", None) or getattr(pair, "name", None)
                if (label and "sold" in str(label).lower()) or (key and str(key).upper() == "SOLD"):
                    return key
    except Exception:
        pass
    return "SOLD"

def _bool_field_set(obj, name, value):
    if _model_has_field(obj.__class__, name):
        try:
            setattr(obj, name, value)
            return True
        except Exception:
            pass
    return False

def _parse_date(value):
    if not value:
        return timezone.localdate()
    try:
        # support "YYYY-MM-DD" or full ISO; strip time if present
        dt = timezone.datetime.fromisoformat(str(value))
        return dt.date()
    except Exception:
        return timezone.localdate()

def _get_item_for_probe_or_update(InventoryItem, biz_id, code):
    """
    Single fetch path used by both endpoints.
    Looks up by IMEI first, then by serial if present.
    Uses _base_manager + explicit business scoping.
    """
    base = InventoryItem._base_manager
    if biz_id is not None:
        base = base.filter(**_biz_filter_kwargs(InventoryItem, biz_id))

    # Decide which identifiers the model supports
    by = None
    if _model_has_field(InventoryItem, "imei") and code.isdigit():
        by = {"imei": code}
    elif _model_has_field(InventoryItem, "serial"):
        by = {"serial": code}

    if not by:
        return None

    try:
        return base.get(**by)
    except InventoryItem.DoesNotExist:
        return None

# ---------------------------
# PROBE: what is this codeâ€™s stock status?
# ---------------------------

@never_cache
def api_stock_status(request):
    """
    Return a normalized stock snapshot used by the scan-sold UI.
    """
    try:
        code = (request.GET.get("code") or request.GET.get("q") or "").strip()
    except Exception:
        code = ""

    if not code:
        return JsonResponse({"ok": False, "error": "Missing code"}, status=400)

    from inventory.models import InventoryItem

    _, biz_id = _active_business_from_request(request)
    item = _get_item_for_probe_or_update(InventoryItem, biz_id, code)
    if not item:
        return JsonResponse({"ok": True, "found": False, "code": code})

    sold_key = _sold_status_key(InventoryItem)
    status_val = getattr(item, "status", None)
    is_sold = str(status_val) == str(sold_key)

    data = {
        "ok": True,
        "found": True,
        "code": code,
        "status": str(status_val) if status_val is not None else None,
        "is_sold": is_sold,
        "sold_at": getattr(item, "sold_at", None).isoformat() if getattr(item, "sold_at", None) else None,
        "selling_price": getattr(item, "selling_price", None),
        "location_id": getattr(item, "current_location_id", None) or getattr(item, "location_id", None),
        # some UIs expect these mirrors:
        "in_stock": not is_sold,
        "is_active": bool(getattr(item, "is_active", True)),
    }
    return JsonResponse(data)

# ---------------------------
# SELL: mark item as SOLD
# ---------------------------

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from django.db import transaction
import json

# ---------- tiny helpers (kept local so this view is self-contained) ----------
def _model_has_field(model, name: str) -> bool:
    try:
        model._meta.get_field(name)
        return True
    except Exception:
        return False

def _bool_field_present(model, name: str) -> bool:
    return _model_has_field(model, name)

def _active_business_from_request(request):
    """Best-effort (replace with your global helper if you have one)."""
    biz = getattr(request, "business", None)
    return biz, getattr(biz, "id", None)

def _biz_filter_kwargs(model, biz_id):
    """Map business id onto common FK names the model may use."""
    names = {f.name for f in model._meta.get_fields()}
    if "business_id" in names:
        return {"business_id": biz_id}
    if "tenant_id" in names:
        return {"tenant_id": biz_id}
    if "store_id" in names:
        return {"store_id": biz_id}
    if "business" in names:
        return {"business_id": biz_id}
    return {}

def _sold_status_key(model):
    """Return the internal key for 'Sold' from choices; fall back sanely."""
    try:
        f = model._meta.get_field("status")
        choices = getattr(f, "choices", None)
        if choices:
            for pair in choices:
                try:
                    key, label = pair
                except Exception:
                    key = getattr(pair, "value", None)
                    label = getattr(pair, "label", None) or getattr(pair, "name", None)
                if label and "sold" in str(label).lower():
                    return key
    except Exception:
        pass
    # Fallback guesses (upper first tends to match TextChoices.value)
    return "SOLD"

def _parse_date(d):
    if not d:
        return timezone.localdate()
    try:
        # Accept YYYY-MM-DD or full ISO datetime; coerce to date
        return timezone.datetime.fromisoformat(str(d)).date()
    except Exception:
        return timezone.localdate()

# -----------------------------------------------------------------------------

@never_cache
@require_POST
@transaction.atomic
def api_mark_sold(request):
    """
    Atomically mark one item as SOLD (tenant-scoped) using a single UPDATE.
    Returns a normalized snapshot your probe understands.
    """
    # ---- Parse body (JSON or form) ----
    try:
        ctype = (request.headers.get("Content-Type") or request.content_type or "").lower()
        payload = json.loads(request.body or "{}") if "application/json" in ctype else request.POST
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON body."}, status=400)

    code = (payload.get("imei") or payload.get("serial") or payload.get("code") or "").strip()
    raw_price = payload.get("price", None)
    raw_loc = payload.get("location_id") or payload.get("location")
    sold_date_in = payload.get("sold_date") or payload.get("soldAt")

    if not code:
        return JsonResponse({"ok": False, "error": "Missing IMEI/serial."}, status=400)

    # ---- Validate price if provided ----
    price_val = None
    if raw_price not in (None, ""):
        try:
            price_val = float(raw_price)
            if price_val < 0:
                return JsonResponse({"ok": False, "error": "Price must be non-negative."}, status=400)
        except Exception:
            return JsonResponse({"ok": False, "error": "Invalid price format."}, status=400)

    sold_date = _parse_date(sold_date_in)

    # ---- Business context ----
    from inventory.models import InventoryItem
    try:
        from inventory.models import Location
    except Exception:
        Location = None  # type: ignore

    biz, biz_id = _active_business_from_request(request)
    if biz_id is None:
        return JsonResponse({"ok": False, "error": "No active business."}, status=403)

    # ---- Resolve SOLD key and location FK name ----
    sold_key = _sold_status_key(InventoryItem)

    loc_fk = None
    if _model_has_field(InventoryItem, "current_location"):
        loc_fk = "current_location_id"
    elif _model_has_field(InventoryItem, "location"):
        loc_fk = "location_id"

    # Optional: validate provided location belongs to this business
    loc_id = None
    if raw_loc not in (None, "", 0, "0"):
        try:
            loc_id = int(raw_loc)
        except Exception:
            return JsonResponse({"ok": False, "error": "Invalid location id."}, status=400)
        if Location is not None and loc_fk:
            names = {f.name for f in Location._meta.get_fields()}
            lqs = getattr(Location, "_base_manager", Location.objects).all()
            if "business_id" in names:
                lqs = lqs.filter(business_id=biz_id)
            elif "tenant_id" in names:
                lqs = lqs.filter(tenant_id=biz_id)
            elif "store_id" in names:
                lqs = lqs.filter(store_id=biz_id)
            if not lqs.filter(id=loc_id).exists():
                return JsonResponse({"ok": False, "error": "That location is not in your store."}, status=403)

    # ---- Build a tenant-scoped queryset via _base_manager ----
    scoped = InventoryItem._base_manager.filter(**_biz_filter_kwargs(InventoryItem, biz_id))

    # Find by IMEI first, otherwise by serial if present in the model
    find_q = None
    if _model_has_field(InventoryItem, "imei"):
        find_q = {"imei": code}
    elif _model_has_field(InventoryItem, "serial"):
        find_q = {"serial": code}
    else:
        return JsonResponse({"ok": False, "error": "Inventory model lacks imei/serial fields."}, status=500)

    # ---- Idempotency check: is it already SOLD? ----
    try:
        existing = scoped.only("id", "status", "sold_at", "selling_price", loc_fk or "id").get(**find_q)
        if str(getattr(existing, "status", "")) == str(sold_key):
            # Return the same normalized view
            return JsonResponse({
                "ok": True,
                "already_sold": True,
                "code": code,
                "status": str(existing.status),
                "is_sold": True,
                "sold_at": existing.sold_at.isoformat() if getattr(existing, "sold_at", None) else None,
                "selling_price": getattr(existing, "selling_price", None),
                "location_id": getattr(existing, loc_fk, None) if loc_fk else None,
                "in_stock": False,
                "is_active": bool(getattr(existing, "is_active", True)),
            })
    except InventoryItem.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Item not found in your store."}, status=404)

    # ---- Compose UPDATE fields (only those that exist on the model) ----
    update_fields = {}
    if _model_has_field(InventoryItem, "status"):
        update_fields["status"] = sold_key
    if _model_has_field(InventoryItem, "sold_at"):
        update_fields["sold_at"] = sold_date
    if _model_has_field(InventoryItem, "selling_price") and (price_val is not None):
        update_fields["selling_price"] = price_val
    if _bool_field_present(InventoryItem, "in_stock"):
        update_fields["in_stock"] = False
    if _bool_field_present(InventoryItem, "is_active"):
        update_fields["is_active"] = False
    if loc_fk and (loc_id is not None):
        update_fields[loc_fk] = loc_id

    # Safety: nothing to update?
    if not update_fields:
        return JsonResponse({"ok": False, "error": "No updatable fields found on model."}, status=500)

    # ---- Perform the UPDATE atomically and check the rowcount ----
    rows_changed = scoped.filter(**find_q).update(**update_fields)
    if rows_changed == 0:
        # Not found under this business after all
        return JsonResponse({"ok": False, "error": "Item not found or not in your store."}, status=404)

    # ---- Reload the row (via _base_manager) for the response snapshot ----
    item = scoped.get(**find_q)

    # Best-effort Sale row
    try:
        from sales.models import Sale
        sale_kwargs = {
            "item": item,
            "agent": request.user,
            "price": getattr(item, "selling_price", None) or (price_val or 0),
            "sold_at": getattr(item, "sold_at", sold_date),
        }
        sale_names = {f.name for f in Sale._meta.get_fields()}
        if "business_id" in sale_names:
            sale_kwargs["business_id"] = biz_id
        if "location_id" in sale_names and loc_fk:
            sale_kwargs["location_id"] = getattr(item, loc_fk, None)
        Sale.objects.create(**{k: v for k, v in sale_kwargs.items() if v is not None})
    except Exception:
        pass

    # ---- Normalized response (same shape your probe reads) ----
    resp = {
        "ok": True,
        "result": "sold",
        "code": code,
        "status": str(getattr(item, "status", "")),
        "is_sold": True,
        "sold_at": item.sold_at.isoformat() if getattr(item, "sold_at", None) else None,
        "selling_price": getattr(item, "selling_price", None),
        "location_id": getattr(item, loc_fk, None) if loc_fk else None,
        "in_stock": False if _bool_field_present(InventoryItem, "in_stock") else False,
        "is_active": bool(getattr(item, "is_active", True)),
        # Remove this block after confirming end-to-end:
        "debug": {"rows_changed": rows_changed, "loc_fk": loc_fk, "biz_id": biz_id},
    }
    return JsonResponse(resp)
# ---------------------------------------------------------------------------
# SAFE DEFAULT LOCATION PICKER + UTILITIES
# ---------------------------------------------------------------------------
# --- Safe renderer used by inventory_dashboard -----------------------------
import json
from django.http import HttpResponse
from django.shortcuts import render
from django.template.exceptions import TemplateDoesNotExist

def _render_dashboard_safe(request, context, today=None, mtd_count=0, all_time_count=0):
    """
    Render the dashboard template. If it's missing, return a minimal HTML fallback
    so the view never crashes.
    """
    # make sure key KPIs exist even if caller forgot to set them
    context = dict(context or {})
    context.setdefault("today_count", context.get("today_count", 0))
    context.setdefault("mtd_count", context.get("mtd_count", mtd_count))
    context.setdefault("all_time_count", context.get("all_time_count", all_time_count))

    try:
        return render(request, "inventory/dashboard.html", context)
    except TemplateDoesNotExist:
        # Fallback so you still see something while wiring templates
        kpis = {
            "today_count": context.get("today_count"),
            "mtd_count": context.get("mtd_count"),
            "all_time_count": context.get("all_time_count"),
            "period": context.get("period"),
            "range": context.get("range"),
        }
        html = f"""
        <html><head><title>Inventory Â· Dashboard (fallback)</title></head>
        <body style="font-family:system-ui,Segoe UI,Arial;margin:24px">
          <h2>Inventory Dashboard</h2>
          <p><em>Template <code>inventory/dashboard.html</code> not found. Showing fallback.</em></p>
          <pre>{json.dumps(kpis, indent=2)}</pre>
        </body></html>
        """
        return HttpResponse(html)

from django.db.models import QuerySet
from django.apps import apps

def _inv_base(qs: QuerySet, start_dt=None, end_dt=None, time_fields=("created_at",)):
    """
    Apply a standard inventory filter base:
      - optional date range across given time_fields
    Returns the filtered queryset.
    """
    if start_dt and end_dt:
        q = Q()
        for f in time_fields:
            q |= Q(**{f"{f}__gte": start_dt, f"{f}__lte": end_dt})
        qs = qs.filter(q)
    return qs

def _pick_manager(*models):
    """Return the first available .objects manager from the given model classes."""
    for m in models:
        if m is not None:
            mgr = getattr(m, "objects", None)
            if mgr is not None:
                return mgr
    return None

def _maybe_model(*model_paths):
    """
    Return the first existing model from the provided candidates.
    Accepts either 'app_label.Model' or just 'Model' (assumes 'inventory').
    """
    for m in model_paths:
        try:
            if "." in m:
                app_label, model_name = m.split(".", 1)
            else:
                app_label, model_name = "inventory", m
            Model = apps.get_model(app_label, model_name)
            if Model is not None:
                return Model
        except LookupError:
            continue
    return None

def _has_field(model, name: str) -> bool:
    return any(getattr(f, "name", None) == name for f in model._meta.get_fields())

def default_location_for_request(request):
    """
    Try hard to fetch a sensible default stock location for this tenant/user.
    Returns an instance or None. NEVER raises if the model doesn't exist.
    """
    LocationModel = _maybe_model(
        "inventory.Location",        # common
        "inventory.StockLocation",   # alt naming
        "inventory.Branch",          # some projects
        "core.Location"              # fallback if kept in core app
    )
    if not LocationModel:
        return None

    qs = _scoped(LocationModel.objects.all(), request)

    # Prefer explicit default flags if present
    for flag in ("is_default", "default", "is_primary"):
        if _has_field(LocationModel, flag):
            obj = qs.filter(**{flag: True}).first()
            if obj:
                return obj

    # If there's a user relation, try that
    user = getattr(request, "user", None)
    if user and _has_field(LocationModel, "user"):
        obj = qs.filter(user=user).first()
        if obj:
            return obj

    # Otherwise, just take the first visible location for this tenant
    return qs.first()

# ---------------------------------------------------------------------------
# ROLE HELPERS (light wrappers)
# ---------------------------------------------------------------------------

def _truthy(obj, *names, default=False):
    """Safely read any of the provided attribute names as a boolean."""
    for n in names:
        try:
            v = getattr(obj, n)
            if isinstance(v, bool):
                return v
            if isinstance(v, (int, str)):
                s = str(v).strip().lower()
                if s in ("1", "true", "yes", "y", "on"):
                    return True
                if s in ("0", "false", "no", "n", "off"):
                    return False
        except Exception:
            pass
    return default

def _user_roles(user):
    """
    Returns: (is_manager, is_auditor, can_stock_in)
    """
    if not user or not getattr(user, "is_authenticated", False):
        return (False, False, False)

    prof = getattr(user, "profile", None)

    # Manager heuristics
    is_manager = any([
        user.is_superuser,
        user.is_staff,
        user.groups.filter(name__in=["Manager", "Managers"]).exists(),
        _truthy(prof, "is_manager", "manager"),
        getattr(prof, "role", "").lower() == "manager",
    ])

    # Auditor heuristics (only matters when *not* manager)
    is_auditor = any([
        user.groups.filter(name__in=["Auditor", "Auditors"]).exists(),
        _truthy(prof, "is_auditor", "auditor"),
        getattr(prof, "role", "").lower() == "auditor",
    ]) and not is_manager

    # Explicit Django permissions also grant stock-in
    can_stock_in = any([
        is_manager,
        user.has_perm("inventory.add_inventoryitem"),
        user.has_perm("inventory.change_inventoryitem"),
    ])

    return (is_manager, is_auditor, can_stock_in)

def _is_admin(user):
    """Return True if the user is considered an admin in this system."""
    if not user or not user.is_authenticated:
        return False
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_staff", False))

def _can_edit_inventory(user):
    """
    Who can edit inventory?
    - superuser / staff
    - anyone with inventory edit perms (change/add/delete on InventoryItem or Stock)
    - optional: members of common manager groups
    """
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True

    candidate_perms = [
        "inventory.change_inventoryitem",
        "inventory.add_inventoryitem",
        "inventory.delete_inventoryitem",
        "inventory.change_stock",
        "inventory.add_stock",
        "inventory.delete_stock",
    ]
    for codename in candidate_perms:
        try:
            if user.has_perm(codename):
                return True
        except Exception:
            pass

    try:
        if user.groups.filter(name__in=[
            "Managers", "Inventory Managers", "Admin", "Auditors"
        ]).exists():
            return True
    except Exception:
        pass

    return False

# ---------------------------------------------------------------------------
# STOCK LIST (HTML + CSV + JSON)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# SIMPLE HTML PAGE (separate from API list)
# ---------------------------------------------------------------------------



@never_cache
@login_required
@require_http_methods(["GET"])
def export_csv(request):
    # Same filters/permissions as stock_list, but always returns CSV
    gate = _require_active_business(request)
    if gate:
        return gate
    biz, biz_id = _require_active_business(request)

    q = (request.GET.get("q") or "").strip()
    show_archived = request.GET.get("archived") == "1"
    status = (request.GET.get("status") or "").lower()  # "sold" | "all" | "in" | "in_stock" | ""

    has_sales_subq = Sale.objects.filter(item=OuterRef("pk"))
    if biz_id:
        has_sales_subq = has_sales_subq.filter(**_biz_filter_kwargs(Sale, biz_id))

    base_mgr = _inv_base(show_archived)
    qs = _scoped(
        base_mgr.all()
        .select_related("product", "current_location", "assigned_agent")
        .annotate(has_sales=Exists(has_sales_subq)),
        request,
    )

    # Permission scope
    if not _can_view_all(request.user):
        qs = qs.filter(assigned_agent=request.user)

    # Search (mirror stock_list)
    if q:
        qs = qs.filter(
            Q(imei__icontains=q)
            | Q(product__name__icontains=q)
            | Q(product__brand__icontains=q)
            | Q(product__model__icontains=q)
            | Q(product__code__icontains=q)  # keep same field used in stock_list
        )

    # Status filter (mirror stock_list)
    is_sold = Q(status="SOLD")
    if status == "sold":
        qs = qs.filter(is_sold)
    elif status in ("all",):
        pass
    else:  # default: in-stock
        qs = qs.exclude(is_sold)

    qs = qs.order_by("-received_at", "product__model")

    # Always return CSV
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="stock.csv"'
    writer = csv.writer(response)
    writer.writerow(["IMEI", "Product", "Status", "Order Price", "Selling Price", "Location", "Agent"])

    for it in qs:
        imei = it.imei or ""
        product = str(it.product) if it.product else ""
        status_text = "SOLD" if getattr(it, "status", "") == "SOLD" else "In stock"
        order_price = f"{(it.order_price or 0):,.0f}"
        selling_price = "-" if it.selling_price is None else f"{float(it.selling_price):,.0f}"
        location = it.current_location.name if getattr(it, "current_location_id", None) else "-"
        agent = it.assigned_agent.get_username() if getattr(it, "assigned_agent_id", None) else "-"
        writer.writerow([imei, product, status_text, order_price, selling_price, location, agent])

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
    profile = getattr(user, "profile", None)  # ok if you donâ€™t have a Profile model
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
    """
    Create a TimeLog from device/location data.
    Expects JSON (preferred) or form body with:
      - checkin_type: ARRIVAL | DEPARTURE (optional, defaults to ARRIVAL)
      - latitude / longitude (or lat / lon)
      - accuracy_m (or accuracy)
      - location_id (optional)
      - note (optional)
    """
    # Ensure there is an active business; the helper returns either an HttpResponse or (biz, biz_id)
    gate = _require_active_business(request)
    if hasattr(gate, "status_code"):  # redirect / error response
        return gate
    biz, biz_id = gate

    # ---- Parse payload (JSON or form) ----
    try:
        if (request.content_type or "").lower().find("application/json") != -1:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        else:
            # QueryDict -> plain dict-like access is OK
            payload = request.POST
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON body."}, status=400)

    # ---- Inputs ----
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

    # Optional sanity on ranges (only if provided)
    if lat is not None and not (-90.0 <= lat <= 90.0):
        return JsonResponse({"ok": False, "error": "Latitude out of range."}, status=400)
    if lon is not None and not (-180.0 <= lon <= 180.0):
        return JsonResponse({"ok": False, "error": "Longitude out of range."}, status=400)

    # ---- Resolve location ----
    loc = None
    loc_id = payload.get("location_id")
    if loc_id:
        try:
            loc = _scoped(Location.objects.all(), request).get(pk=int(loc_id))
        except Exception:
            return JsonResponse({"ok": False, "error": "Invalid location_id."}, status=400)
    if not loc:
        loc = _user_home_location(request.user)
        # Ignore locations not in the active business
        if loc and not _obj_belongs_to_active_business(loc, request):
            loc = None

    # ---- Distance / geofence ----
    dist = None
    within = False
    if loc and (loc.latitude is not None) and (loc.longitude is not None) and (lat is not None) and (lon is not None):
        try:
            dist = _haversine_m(lat, lon, float(loc.latitude), float(loc.longitude))
        except Exception:
            dist = None
        if dist is not None:
            # geofence radius + reported GPS accuracy (be generous)
            radius = (getattr(loc, "geofence_radius_m", None) or 150) + (acc or 0)
            within = dist <= radius

    # ---- Create log ----
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
        },
        status=201,
    )
# --- ADD (or keep) these imports at the top of inventory/views.py ---


from typing import Any, Iterable, Optional

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

# Defensive, tenant-scoped helpers (use your project's if present)
def _try_import(modpath: str, attr: str | None = None):
    import importlib
    try:
        mod = importlib.import_module(modpath)
        return getattr(mod, attr) if attr else mod
    except Exception:
        return None

scoped = _try_import("circuitcity.tenants.utils", "scoped") or \
         _try_import("tenants.utils", "scoped") or (lambda qs, _request: qs)

get_active_business = _try_import("circuitcity.tenants.utils", "get_active_business") or \
                      _try_import("tenants.utils", "get_active_business") or (lambda _r: None)

# Models (import defensively)
TimeLog = _try_import("inventory.models", "TimeLog") or _try_import("circuitcity.inventory.models", "TimeLog")
Location = _try_import("inventory.models", "Location") or _try_import("circuitcity.inventory.models", "Location")

# inventory/views.py

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render
from django.views.decorators.cache import never_cache

try:
    from .models import TimeLog  # type: ignore
except Exception:
    TimeLog = None  # type: ignore

# tenant scoping (safe no-op fallback)
try:
    from tenants.utils import scoped as _scoped  # type: ignore
except Exception:
    _scoped = lambda qs, _req: qs


def _can_view_all(user) -> bool:
    try:
        return bool(
            getattr(user, "is_superuser", False)
            or getattr(user, "is_staff", False)
            or getattr(getattr(user, "profile", None), "is_manager", False)
        )
    except Exception:
        return False


@never_cache
@login_required
def time_logs(request):
    """
    Show recent time logs.
    - Managers/staff/superusers: see all logs (scoped to business when possible).
    - Agents: only their own logs.
    - If scoping hides rows (e.g., logs lack business_id), fall back to unscoped.
    """
    if TimeLog is None:
        return render(
            request,
            "inventory/time_logs.html",
            {"logs": [], "page_obj": None, "url_for": (lambda *_a, **_k: "#")},
        )

    # Count all rows to detect over-strict scoping later
    try:
        total_rows = TimeLog.objects.count()
    except Exception:
        total_rows = 0

    base = _scoped(TimeLog.objects.select_related("user", "location"), request)

    # Role-based view
    if _can_view_all(request.user):
        qs = base.order_by("-logged_at")
    else:
        qs = base.filter(user=request.user).order_by("-logged_at")

    # If scoped QS is empty but there ARE rows, try a graceful fallback
    try:
        needs_fallback = (not qs.exists()) and (total_rows > 0)
    except Exception:
        needs_fallback = False

    if needs_fallback:
        unscoped = TimeLog.objects.select_related("user", "location")
        qs = unscoped.order_by("-logged_at") if _can_view_all(request.user) else unscoped.filter(
            user=request.user
        ).order_by("-logged_at")

    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    def url_for(page_number: int):
        params = request.GET.copy()
        params["page"] = str(page_number)
        return f"{request.path}?{params.urlencode()}"

    return render(
        request,
        "inventory/time_logs.html",
        {"logs": page_obj.object_list, "page_obj": page_obj, "url_for": url_for},
    )

# ------------- small helpers -------------
def _can_view_all(user) -> bool:
    """
    Managers / staff / superusers can see all logs; agents only see their own.
    """
    try:
        if not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        # common "manager" flag on profile (safe)
        prof = getattr(user, "profile", None)
        if prof and getattr(prof, "is_manager", False):
            return True
    except Exception:
        pass
    return False


def _paginate_qs(request, qs, per_page: int = 50):
    page_no = request.GET.get("page") or 1
    try:
        per_page = max(1, min(200, int(request.GET.get("per_page", per_page))))
    except Exception:
        pass
    paginator = Paginator(qs, per_page)
    try:
        page = paginator.page(page_no)
    except PageNotAnInteger:
        page = paginator.page(1)
    except EmptyPage:
        page = paginator.page(paginator.num_pages)
    return page


# ------------- PAGE VIEW: Time Logs -------------
@never_cache
@login_required
@require_http_methods(["GET"])
def time_logs(request):
    """
    Render the time logs table. Scopes to active business automatically (if your
    'scoped' helper applies it). Managers see all; agents see their own only.
    """
    # If the project doesn't have a TimeLog model yet, render the template with no rows.
    if TimeLog is None:
        return render(request, "inventory/time_logs.html", {"logs": [], "page_obj": None})

    # Base queryset (join common FKs for performance)
    try:
        qs = TimeLog.objects.all()
        try:
            qs = qs.select_related("user", "location")
        except Exception:
            pass
    except Exception:
        # Something odd with the model; fail open with empty list
        return render(request, "inventory/time_logs.html", {"logs": [], "page_obj": None})

    # Apply tenant/business scoping (your scoped() helper will do the right thing)
    qs = scoped(qs, request)

    # Agent vs Manager visibility
    if not _can_view_all(request.user):
        try:
            qs = qs.filter(user=request.user)
        except Exception:
            pass

    # Order newest first
    try:
        qs = qs.order_by("-logged_at")
    except Exception:
        try:
            qs = qs.order_by("-id")
        except Exception:
            pass

    # Paginate
    page_obj = _paginate_qs(request, qs, per_page=50)

    ctx = {
        "logs": list(page_obj.object_list),
        "page_obj": page_obj,
    }
    return render(request, "inventory/time_logs.html", ctx)


# ------------- (optional) PAGE VIEW: Time Check-in -------------
# If you donâ€™t already have a page view for the check-in screen, this renders
# templates/inventory/time_checkin.html and passes a default store/home location.
@never_cache
@login_required
@require_http_methods(["GET"])
def time_checkin_page(request):
    home_loc = None
    locations = []

    # Provide a few locations if your project has them
    if Location is not None:
        try:
            loc_qs = scoped(Location.objects.all().order_by("name"), request)
            locations = list(loc_qs[:50])
            # heuristic: pick the first as "home_loc"
            home_loc = locations[0] if locations else None
        except Exception:
            pass

    return render(request, "inventory/time_checkin.html", {
        "home_loc": home_loc,
        "locations": locations,
    })

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
    # Scoped wallet summary (WalletTransaction schema)
    target = request.user
    user_id = request.GET.get("user_id")
    if user_id:
        if not _is_manager_or_admin(request.user):
            return JsonResponse({"ok": False, "error": "Permission denied."}, status=403)
        try:
            target = User.objects.get(pk=int(user_id))
        except Exception:
            return JsonResponse({"ok": False, "error": "Unknown user_id."}, status=400)

    if WalletTransaction is not None:
        balance = _scoped(WalletTransaction.objects.filter(ledger="agent", agent=target), request).aggregate(s=Coalesce(Sum("amount"), Value(0)))["s"] or 0
    else:
        balance = 0

    year = request.GET.get("year")
    month = request.GET.get("month")
    data = {"ok": True, "user_id": target.id, "balance": float(balance or 0)}
    if year and month and WalletTransaction is not None:
        try:
            y, m = int(year), int(month)
            data["month_sum"] = _scoped(
                WalletTransaction.objects.filter(ledger="agent", agent=target, created_at__year=y, created_at__month=m),
                request,
            ).aggregate(s=Coalesce(Sum("amount"), Value(0)))["s"] or 0
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
    if WalletTransaction is None:
        return JsonResponse({"ok": False, "error": "Wallet models not installed."}, status=500)

    if not _is_admin(request.user):
        return JsonResponse({"ok": False, "error": "Admin only."}, status=403)

    # Ensure business to attach on create
    gate = _require_active_business(request)
    if gate:
        return gate
    biz, biz_id = _require_active_business(request)

    try:
        if request.content_type and "application/json" in request.content_type.lower():
            payload = json.loads(request.body or "{}")
        else:
            payload = request.POST
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON body."}, status=400)

    # Target agent
    try:
        target = User.objects.get(pk=int(payload.get("user_id") or payload.get("agent_id")))
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid or missing user_id/agent_id."}, status=400)

    # Amount
    try:
        amount = Decimal(str(payload.get("amount")))
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid amount."}, status=400)

    # Type (accept 'type' or legacy 'reason'); map to TxnType.* (lowercase)
    raw_type = (payload.get("type") or payload.get("reason") or "adjustment").strip().lower()
    allowed_types = {c[0] for c in (getattr(TxnType, "choices", []) or [])} or {
        "commission", "bonus", "deduction", "advance", "penalty", "payslip", "adjustment", "budget"
    }
    if raw_type not in allowed_types:
        return JsonResponse({"ok": False, "error": f"Invalid type. Allowed: {sorted(list(allowed_types))}"}, status=400)

    memo = (payload.get("memo") or payload.get("note") or "").strip()[:200]
    effective_date = (payload.get("effective_date") or "").strip() or None

    txn = WalletTransaction.objects.create(
        ledger="agent",
        agent=target,
        type=raw_type,
        amount=amount,
        note=memo,
        effective_date=effective_date or timezone.localdate(),
        created_by=request.user,
        **_attach_business_kwargs(WalletTransaction, biz_id),
    )

    # Return business-scoped balance
    new_balance = _scoped(WalletTransaction.objects.filter(ledger="agent", agent=target), request).aggregate(s=Coalesce(Sum("amount"), Value(0)))["s"] or 0
    return JsonResponse({"ok": True, "txn_id": txn.id, "balance": float(new_balance or 0)})

api_wallet_txn = api_wallet_add_txn

@never_cache
@login_required
@require_http_methods(["GET"])
def wallet_page(request):
    # Business gate
    gate = _require_active_business(request)
    if gate:
        return gate
    biz, biz_id = _require_active_business(request)

    target = request.user
    user_id = request.GET.get("user_id")
    if user_id and _is_manager_or_admin(request.user):
        try:
            target = User.objects.get(pk=int(user_id))
        except Exception:
            target = request.user

    today = timezone.localdate()

    if WalletTransaction is not None:
        life_qs = _scoped(WalletTransaction.objects.filter(ledger="agent", agent=target), request)
        balance = life_qs.aggregate(s=Coalesce(Sum("amount"), Value(0)))["s"] or 0
        month_sum = _scoped(
            WalletTransaction.objects.filter(ledger="agent", agent=target, created_at__year=today.year, created_at__month=today.month),
            request,
        ).aggregate(s=Coalesce(Sum("amount"), Value(0)))["s"] or 0
        recent_txns = _scoped(
            WalletTransaction.objects.select_related("agent", "created_by").filter(ledger="agent", agent=target).order_by("-created_at")[:50],
            request,
        )
        type_choices = list(getattr(WalletTransaction._meta.get_field("type"), "choices", []))
    else:
        balance = 0
        month_sum = 0
        recent_txns = []
        type_choices = []

    # Restrict agent list to current business if possible
    agents = []
    if _is_manager_or_admin(request.user):
        if biz_id:
            agents_qs = (  # heuristic: agents who hold items in this business
                InventoryItem.objects.filter(**_biz_filter_kwargs(InventoryItem, biz_id))
                .exclude(assigned_agent__isnull=True)
                .values("assigned_agent_id", "assigned_agent__username")
                .order_by("assigned_agent__username")
                .distinct()
            )
            agents = [{"id": r["assigned_agent_id"], "username": r["assigned_agent__username"]} for r in agents_qs]
        else:
            agents = list(User.objects.order_by("username").values("id", "username"))

    context = {
        "target": target,
        "balance": float(balance or 0),
        "month_sum": float(month_sum or 0),
        "recent_txns": recent_txns,
        "reasons": type_choices,  # template may still call this "reasons"
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
        # Archive fallback
        if hasattr(item, "is_active"):
            item.is_active = False
            item.save(update_fields=["is_active"])
            _audit(item, request.user, "ARCHIVE_FALLBACK", "ProtectedError: related sales exist; archived instead.")
            messages.info(request, "This item has sales, so it was archived instead of deleted.")
        else:
            messages.error(request, "This item has related sales and cannot be deleted.")
    return redirect("inventory:stock_list")

# -----------------------
# (continueâ€¦)
# -----------------------

from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.decorators.cache import never_cache
from django.contrib.auth.decorators import login_required
import importlib

def _try_call(module_path: str, attr: str, request):
    """Import module.attr and call it if callable; return response or None."""
    try:
        mod = importlib.import_module(module_path)
        fn = getattr(mod, attr, None)
        if callable(fn):
            return fn(request)
    except Exception:
        pass
    return None

@never_cache
@login_required
@require_GET
def restock_heatmap_api(request):
    """
    Delegates to any available implementation; otherwise returns a safe stub.
    Tries (in order):
      - inventory.api.restock_heatmap_api
      - inventory.api.api_stock_health
      - inventory.views_api.restock_heatmap_api
      - inventory.views_dashboard.restock_heatmap_api
    Always responds 200 on fallback so UI never 501s.
    """
    for module, attr in [
        ("inventory.api", "restock_heatmap_api"),
        ("inventory.api", "api_stock_health"),
        ("inventory.views_api", "restock_heatmap_api"),
        ("inventory.views_dashboard", "restock_heatmap_api"),
    ]:
        resp = _try_call(module, attr, request)
        if resp is not None:
            return resp

    # Safe fallback payload (UI-ready)
    return JsonResponse({"points": [], "generated_at": "ok"}, status=200)
# --- PART 2/3 end ---
# --- PART 3/3 BEGINS ---


# stdlib

from decimal import Decimal
from hashlib import md5
from datetime import datetime, timedelta, date, time as dtime



from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.mail import mail_admins
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import (
    Q, Sum, Value, Exists, OuterRef, F, Count, Case, When,
    DecimalField, ExpressionWrapper
)
from django.db.models.functions import Coalesce, Cast, TruncMonth
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods

# optional OTP decorator (be forgiving if package is absent)
try:
    from two_factor.decorators import otp_required  # django-two-factor-auth
except Exception:
    try:
        from django_otp.decorators import otp_required  # django-otp
    except Exception:
        def otp_required(view):
            return view

User = get_user_model()

# --- Defensive model + form imports (ok if missing) -------------------------
try:
    from .models import InventoryItem as InventoryItem
except Exception:
    InventoryItem = None  # type: ignore

try:
    from .models import Location as Location
except Exception:
    Location = None  # type: ignore

try:
    from .models import Product as Product
except Exception:
    Product = None  # type: ignore

try:
    from sales.models import Sale as Sale
except Exception:
    Sale = None  # type: ignore

try:
    from .models import TimeLog as TimeLog
except Exception:
    TimeLog = None  # type: ignore

try:
    from .models import WalletTransaction as WalletTransaction
except Exception:
    WalletTransaction = None  # type: ignore

try:
    from .models import TxnType as TxnType
except Exception:
    TxnType = None  # type: ignore

try:
    from .forms import InventoryItemForm
except Exception:
    InventoryItemForm = None  # type: ignore

# --- Helpers expected from other parts (we just call them) -------------------
# _require_active_business, _attach_business_kwargs, _biz_filter_kwargs,
# _model_has_field, _obj_belongs_to_active_business, _limit_form_querysets,
# _audit, _user_home_location, _can_view_all, _is_manager_or_admin,
# _is_admin, _scoped, _haversine_m, get_dashboard_cache_version,
# get_preset_window, _time_q_for

# -----------------------
# CSV Export
# -----------------------
@never_cache
@login_required
@require_http_methods(["GET"])
def export_csv(request):
    """
    Same filters/permissions as stock_list, but always returns CSV.
    Mirrors the robust logic used in PART 2 stock_list.
    """
    # Business gate (tuple-safe)
    gate = _require_active_business(request)
    if gate:
        return gate
    biz, biz_id = _require_active_business(request)

    if InventoryItem is None:
        # Nothing to export
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="stock.csv"'
        writer = csv.writer(response)
        writer.writerow(["IMEI", "Product", "Status", "Order Price", "Selling Price", "Location", "Agent"])
        return response

    # --- tiny locals that mirror stock_list ---
    def _has_field(model, name: str) -> bool:
        try:
            return any(getattr(f, "name", None) == name for f in model._meta.get_fields())
        except Exception:
            return False

    def _owner_q(model, user):
        names = [
            "assigned_agent", "assigned_to", "assignee",
            "owner", "user", "agent", "created_by", "received_by",
        ]
        q = Q(pk__in=[])  # false starter
        uid = getattr(user, "id", None)
        uname = getattr(user, "username", None)
        for nm in names:
            if _has_field(model, nm):
                q |= Q(**{nm: user})
                if uid is not None:
                    q |= Q(**{f"{nm}_id": uid})
                if uname:
                    q |= Q(**{f"{nm}__username": uname})
        return q

    # --- inputs (mirror stock_list) ---
    qtext         = (request.GET.get("q") or "").strip()
    show_archived = request.GET.get("archived") == "1"
    raw_status    = (request.GET.get("status") or "").lower()
    status        = raw_status if raw_status in {"sold", "all", "in", "in_stock"} else "in"

    # --- base queryset (like stock_list) ---
    mdl = InventoryItem
    qs = mdl._base_manager.all()  # avoid hidden default manager filters

    # Business filter (if model has it)
    fields = {f.name for f in mdl._meta.get_fields()}
    if biz_id and (("business" in fields) or ("business_id" in fields)):
        request.session["active_business_id"] = biz_id
        qs = qs.filter(business_id=biz_id)

    # Location scoping via session/querystring handled by _scoped already,
    # but we keep parity with stock_list by calling _scoped on the select_related queryset.
    qs = qs.select_related("product", "current_location", "location", "assigned_agent")
    if _has_field(mdl, "is_archived") and not show_archived:
        qs = qs.filter(is_archived=False)
    qs = _scoped(qs, request)

    # --- annotate has_sales like stock_list (best-effort) ---
    annotated_has_sales = False
    if Sale:
        sale_fk_options = ("item", "inventory_item", "stock")
        fk_name = next((fk for fk in sale_fk_options if hasattr(Sale, "_meta") and _has_field(Sale, fk)), None)
        if fk_name:
            subq = Sale.objects.filter(**{fk_name: OuterRef("pk")})
            if biz_id:
                subq = subq.filter(**_biz_filter_kwargs(Sale, biz_id))
            qs = qs.annotate(has_sales=Exists(subq))
            annotated_has_sales = True

    # --- permission scope (mirror stock_list's 'self' scope) ---
    if not _can_view_all(request.user):
        owner_q = _owner_q(mdl, request.user)
        qs = qs.filter(owner_q) if owner_q.children else qs.none()

    # --- sold detection (same set as PART 2) ---
    sold_like = {
        "SOLD","Sold","sold",
        "DISPATCHED","Dispatched","dispatched",
        "CHECKED_OUT","CHECKED-OUT","Checked_out","checked_out","checked-out",
        "OUT","Out","out",
        "DELIVERED","Delivered","delivered",
        "ISSUED","Issued","issued",
        "PAID","Paid","paid",
    }
    is_sold_q = Q(pk__in=[])
    if _has_field(mdl, "status"):
        is_sold_q |= Q(status__in=sold_like)
    if annotated_has_sales:
        is_sold_q |= Q(has_sales=True)

    # --- search (mirror stock_list) ---
    if qtext:
        search_q = Q()
        for fld in ("imei", "sku"):
            if _has_field(mdl, fld):
                search_q |= Q(**{f"{fld}__icontains": qtext})
        if _has_field(mdl, "product"):
            for pf in ("brand", "model", "name", "code"):
                search_q |= Q(**{f"product__{pf}__icontains": qtext})
        qs = qs.filter(search_q)

    # --- status filter (mirror stock_list) ---
    if status == "sold":
        qs = qs.filter(is_sold_q)
    elif status == "all":
        pass
    else:
        qs = qs.exclude(is_sold_q)

    # --- ordering (mirror stock_list) ---
    order_fields = []
    if _has_field(mdl, "received_at"):
        order_fields.append("-received_at")
    if _has_field(mdl, "product"):
        order_fields.append("product__model")
    if not order_fields:
        order_fields = ["-id"]
    qs = qs.order_by(*order_fields)

    # --- Always return CSV ---
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="stock.csv"'
    writer = csv.writer(response)
    writer.writerow(["IMEI", "Product", "Status", "Order Price", "Selling Price", "Location", "Agent"])

    for it in qs.iterator(chunk_size=1000):
        # compute sold flag like stock_list row builder
        sold_flag = (
            ((_has_field(mdl, "status") and getattr(it, "status", None) in sold_like))
            or (annotated_has_sales and getattr(it, "has_sales", False))
        )
        imei = getattr(it, "imei", "") or ""
        product = str(getattr(it, "product")) if getattr(it, "product_id", None) else ""
        status_text = "SOLD" if sold_flag else "In stock"
        order_price_val = getattr(it, "order_price", None)
        selling_price_val = getattr(it, "selling_price", None)
        order_price = "-" if order_price_val is None else f"{(order_price_val or Decimal('0')):,.0f}"
        selling_price = "-" if selling_price_val is None else f"{Decimal(selling_price_val):,.0f}"
        location = (
            getattr(getattr(it, "current_location", None), "name", "-")
            if getattr(it, "current_location_id", None)
            else getattr(getattr(it, "location", None), "name", "-") if getattr(it, "location_id", None) else "-"
        )
        agent = getattr(getattr(it, "assigned_agent", None), "username", "-") if getattr(it, "assigned_agent_id", None) else "-"
        writer.writerow([imei, product, status_text, order_price, selling_price, location, agent])

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
            if getattr(user, "defaultdevice", None) or (hasattr(user, "staticdevice_set") and user.staticdevice_set.exists()):
                enabled = True
                provider = provider or "TOTP"
    except Exception:
        pass

    return {
        "enabled": enabled,
        "provider": provider or ("TOTP" if enabled else None),
        "manage_url": getattr(settings, "TWO_FACTOR_MANAGE_URL", "/account/two-factor/"),
    }


@login_required
def settings_home(request):
    user = request.user
    profile = getattr(user, "profile", None)  # ok if you donâ€™t have a Profile model
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
    }
    return render(request, "inventory/settings.html", context)


@login_required
def settings_redirect(request):
    return redirect("accounts:settings_unified")


@never_cache
@login_required
@require_POST
def api_time_checkin(request):
    if TimeLog is None:
        return JsonResponse({"ok": False, "error": "Time logging is not available."}, status=500)

    # Ensure an active business and attach it to TimeLog when possible
    gate = _require_active_business(request)
    if gate:
        return gate
    biz, biz_id = _require_active_business(request)

    try:
        if request.content_type and "application/json" in request.content_type.lower():
            payload = json.loads(request.body or "{}")
        else:
            payload = request.POST
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON body."}, status=400)

    checkin_type = (payload.get("checkin_type") or payload.get("type") or "ARRIVAL").upper()
    if hasattr(TimeLog, "ARRIVAL") and hasattr(TimeLog, "DEPARTURE"):
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
    if loc_id and Location is not None:
        try:
            loc = _scoped(Location.objects.all(), request).get(pk=int(loc_id))
        except Exception:
            return JsonResponse({"ok": False, "error": "Invalid location_id."}, status=400)
    if not loc and Location is not None:
        loc = _user_home_location(request.user)
        if loc and not _obj_belongs_to_active_business(loc, request):
            loc = None  # ignore foreign-business locations

    dist = None
    within = False
    if loc and hasattr(loc, "latitude") and hasattr(loc, "longitude") and loc.latitude is not None and loc.longitude is not None and lat is not None and lon is not None:
        dist = _haversine_m(lat, lon, float(loc.latitude), float(loc.longitude))
        radius = (getattr(loc, "geofence_radius_m", None) or 150) + (acc or 0)
        within = dist <= radius

    tl_kwargs = dict(
        user=request.user,
        location=loc,
        checkin_type=checkin_type,
        latitude=lat,
        longitude=lon,
        accuracy_m=acc,
        distance_m=dist,
        within_geofence=within,
        note=(payload.get("note") or "").strip()[:200],
    )
    tl_kwargs.update(_attach_business_kwargs(TimeLog, biz_id))
    tl = TimeLog.objects.create(**tl_kwargs)

    return JsonResponse(
        {
            "ok": True,
            "id": tl.id,
            "logged_at": tl.logged_at.isoformat() if hasattr(tl, "logged_at") else timezone.now().isoformat(),
            "location": (getattr(loc, "name", None) if loc else None),
            "distance_m": dist,
            "within_geofence": within,
            "checkin_type": checkin_type,
        }
    )


# inventory/views.py (add/replace this section)



from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import render
from django.views.decorators.cache import never_cache

# --- Optional imports (fail-safe) ---
try:
    from .models import TimeLog, Location  # type: ignore
except Exception:
    TimeLog = None  # type: ignore
    Location = None  # type: ignore

try:
    # tenant-aware scoping
    from tenants.utils import scoped as _scoped  # type: ignore
except Exception:
    _scoped = lambda qs, _request: qs  # no-op fallback


def _can_view_all(user) -> bool:
    """Allow managers/staff/superusers to see all logs; agents see their own."""
    try:
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        profile = getattr(user, "profile", None)
        return bool(getattr(profile, "is_manager", False))
    except Exception:
        return False


@never_cache
@login_required
def time_logs(request):
    """
    Render the Time Logs page.
    - Managers/staff/superusers: all logs in scope
    - Agents: only their own logs
    - Paginates 50 per page
    """
    if TimeLog is None:
        # Safe fallback: render empty page if model doesn't exist
        return render(
            request,
            "inventory/time_logs.html",
            {"logs": [], "page_obj": None, "url_for": (lambda *_a, **_k: "#")},
        )

    # Scope logs to active business (if your project uses tenant scoping)
    base_qs = _scoped(TimeLog.objects.select_related("user", "location"), request)

    if _can_view_all(request.user):
        qs = base_qs.order_by("-logged_at")
    else:
        qs = base_qs.filter(user=request.user).order_by("-logged_at")

    # Pagination
    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Minimal url_for callable (used by template for pager links)
    def url_for(page_number: int):
        params = request.GET.copy()
        params["page"] = str(page_number)
        return f"{request.path}?{params.urlencode()}"

    return render(
        request,
        "inventory/time_logs.html",
        {
            "logs": page_obj.object_list,
            "page_obj": page_obj,
            "url_for": url_for,
        },
    )

@never_cache
@login_required
@require_GET
def api_wallet_summary(request):
    # Scoped wallet summary (WalletTransaction schema)
    target = request.user
    user_id = request.GET.get("user_id")
    if user_id:
        if not _is_manager_or_admin(request.user):
            return JsonResponse({"ok": False, "error": "Permission denied."}, status=403)
        try:
            target = User.objects.get(pk=int(user_id))
        except Exception:
            return JsonResponse({"ok": False, "error": "Unknown user_id."}, status=400)

    if WalletTransaction is not None:
        balance = _scoped(WalletTransaction.objects.filter(ledger="agent", agent=target), request).aggregate(s=Coalesce(Sum("amount"), Value(0)))["s"] or 0
    else:
        balance = 0

    year = request.GET.get("year")
    month = request.GET.get("month")
    data = {"ok": True, "user_id": target.id, "balance": float(balance or 0)}
    if year and month and WalletTransaction is not None:
        try:
            y, m = int(year), int(month)
            data["month_sum"] = _scoped(
                WalletTransaction.objects.filter(ledger="agent", agent=target, created_at__year=y, created_at__month=m),
                request,
            ).aggregate(s=Coalesce(Sum("amount"), Value(0)))["s"] or 0
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
    if WalletTransaction is None:
        return JsonResponse({"ok": False, "error": "Wallet models not installed."}, status=500)

    if not _is_admin(request.user):
        return JsonResponse({"ok": False, "error": "Admin only."}, status=403)

    # Ensure business to attach on create
    gate = _require_active_business(request)
    if gate:
        return gate
    biz, biz_id = _require_active_business(request)

    try:
        if request.content_type and "application/json" in request.content_type.lower():
            payload = json.loads(request.body or "{}")
        else:
            payload = request.POST
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON body."}, status=400)

    # Target agent
    try:
        target = User.objects.get(pk=int(payload.get("user_id") or payload.get("agent_id")))
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid or missing user_id/agent_id."}, status=400)

    # Amount
    try:
        amount = Decimal(str(payload.get("amount")))
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid amount."}, status=400)

    # Type (accept 'type' or legacy 'reason'); map to TxnType.* (lowercase)
    raw_type = (payload.get("type") or payload.get("reason") or "adjustment").strip().lower()
    allowed_types = {c[0] for c in (getattr(TxnType, "choices", []) or [])} or {
        "commission", "bonus", "deduction", "advance", "penalty", "payslip", "adjustment", "budget"
    }
    if raw_type not in allowed_types:
        return JsonResponse({"ok": False, "error": f"Invalid type. Allowed: {sorted(list(allowed_types))}"}, status=400)

    memo = (payload.get("memo") or payload.get("note") or "").strip()[:200]
    effective_date = (payload.get("effective_date") or "").strip() or None

    txn_kwargs = dict(
        ledger="agent",
        agent=target,
        type=raw_type,
        amount=amount,
        note=memo,
        effective_date=effective_date or timezone.localdate(),
        created_by=request.user,
    )
    txn_kwargs.update(_attach_business_kwargs(WalletTransaction, biz_id))
    txn = WalletTransaction.objects.create(**txn_kwargs)

    # Return business-scoped balance
    new_balance = _scoped(WalletTransaction.objects.filter(ledger="agent", agent=target), request).aggregate(s=Coalesce(Sum("amount"), Value(0)))["s"] or 0
    return JsonResponse({"ok": True, "txn_id": txn.id, "balance": float(new_balance or 0)})


api_wallet_txn = api_wallet_add_txn


@never_cache
@login_required
@require_http_methods(["GET"])
def wallet_page(request):
    # Business gate
    gate = _require_active_business(request)
    if gate:
        return gate
    biz, biz_id = _require_active_business(request)

    target = request.user
    user_id = request.GET.get("user_id")
    if user_id and _is_manager_or_admin(request.user):
        try:
            target = User.objects.get(pk=int(user_id))
        except Exception:
            target = request.user

    today = timezone.localdate()

    if WalletTransaction is not None:
        life_qs = _scoped(WalletTransaction.objects.filter(ledger="agent", agent=target), request)
        balance = life_qs.aggregate(s=Coalesce(Sum("amount"), Value(0)))["s"] or 0
        month_sum = _scoped(
            WalletTransaction.objects.filter(ledger="agent", agent=target, created_at__year=today.year, created_at__month=today.month),
            request,
        ).aggregate(s=Coalesce(Sum("amount"), Value(0)))["s"] or 0
        recent_txns = _scoped(
            WalletTransaction.objects.select_related("agent", "created_by").filter(ledger="agent", agent=target).order_by("-created_at")[:50],
            request,
        )
        try:
            type_choices = list(getattr(WalletTransaction._meta.get_field("type"), "choices", []))
        except Exception:
            type_choices = []
    else:
        balance = 0
        month_sum = 0
        recent_txns = []
        type_choices = []

    # Restrict agent list to current business if possible
    agents = []
    if _is_manager_or_admin(request.user) and InventoryItem is not None:
        if biz_id:
            agents_qs = (
                InventoryItem.objects.filter(**_biz_filter_kwargs(InventoryItem, biz_id))
                .exclude(assigned_agent__isnull=True)
                .values("assigned_agent_id", "assigned_agent__username")
                .order_by("assigned_agent__username")
                .distinct()
            )
            agents = [{"id": r["assigned_agent_id"], "username": r["assigned_agent__username"]} for r in agents_qs]
        else:
            agents = list(User.objects.order_by("username").values("id", "username"))

    context = {
        "target": target,
        "balance": float(balance or 0),
        "month_sum": float(month_sum or 0),
        "recent_txns": recent_txns,
        "reasons": type_choices,
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
# --- add this tiny helper once near the top of views.py (outside any view) ---
# ----------------------------------------------------------------------------



from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.cache import never_cache
from django.http import JsonResponse, HttpRequest
from django.db import transaction
from django.utils import timezone

# Reuse the single source of truth helpers
from inventory.utils import _normalize_code, get_instock_item_for_business


# --------------------------------------------------------------------
# Small local helpers (kept here to avoid coupling to other modules)
# --------------------------------------------------------------------
def _ok(data, status=200):
    return JsonResponse({"ok": True, **data}, status=status)

def _err(msg, status=400):
    return JsonResponse({"ok": False, "error": msg}, status=status)

def _current_business_from_request(request: HttpRequest):
    """
    Heuristics to locate the active business on the request/user.
    Adjust if you have a canonical accessor.
    """
    return (
        getattr(getattr(request.user, "agent_profile", None), "business", None)
        or getattr(getattr(request.user, "profile", None), "business", None)
        or getattr(request, "business", None)
        or getattr(getattr(request, "tenant", None), "business", None)
    )


# ====================================================================
# 1) Business-wide status check for Scan SOLD (location never blocks)
# ====================================================================
from django.views.decorators.http import require_GET

@never_cache
@require_GET
def api_stock_status(request):
    """
    Probe endpoint used by the scan UI.

    It reports in_stock for *this business* by looking at the same flags/fields
    the sale endpoint writes, using _base_manager + explicit business filtering.
    """
    code = (request.GET.get("code") or "").strip()
    raw_loc = request.GET.get("location_id") or request.GET.get("location")
    if not (code.isdigit() and len(code) == 15):
        return JsonResponse({"ok": False, "error": "IMEI must be exactly 15 digits."}, status=400)

    # helpers
    def _model_has_field(model, name: str) -> bool:
        try:
            model._meta.get_field(name)
            return True
        except Exception:
            return False

    def _require_active_business(_request):
        biz = getattr(_request, "business", None)
        biz_id = getattr(biz, "id", None)
        return biz, biz_id

    def _biz_filter_kwargs(model, biz_id):
        names = {f.name for f in model._meta.get_fields()}
        if "business_id" in names:
            return {"business_id": biz_id}
        if "tenant_id" in names:
            return {"tenant_id": biz_id}
        if "store_id" in names:
            return {"store_id": biz_id}
        if "business" in names:
            return {"business_id": biz_id}
        return {}

    def _sold_key_for(model):
        try:
            f = model._meta.get_field("status")
            choices = getattr(f, "choices", None)
            if choices:
                for pair in choices:
                    try:
                        key, label = pair
                    except Exception:
                        key = getattr(pair, "value", None)
                        label = getattr(pair, "label", None) or getattr(pair, "name", None)
                    if label and "sold" in str(label).lower():
                        return key
        except Exception:
            pass
        for guess in ("SOLD", "Sold", "sold", "S"):
            return guess

    # resolve models
    from inventory.models import InventoryItem

    # active business
    biz, biz_id = _require_active_business(request)
    if biz_id is None:
        return JsonResponse({"ok": False, "error": "No active business."}, status=403)

    # fetch via base manager + business filter
    qs = InventoryItem._base_manager.filter(**_biz_filter_kwargs(InventoryItem, biz_id))
    qs = qs.filter(imei=code)

    # optional location scoping (matches whichever FK exists)
    loc_id = None
    if raw_loc not in (None, "", 0, "0"):
        try:
            loc_id = int(raw_loc)
        except Exception:
            loc_id = None

    if loc_id is not None:
        if _model_has_field(InventoryItem, "current_location"):
            qs = qs.filter(current_location_id=loc_id)
        elif _model_has_field(InventoryItem, "location"):
            qs = qs.filter(location_id=loc_id)

    item = qs.first()
    if not item:
        # Not found in this business => not in stock for this business
        return JsonResponse({"ok": True, "exists": False, "in_stock": False})

    sold_key = _sold_key_for(InventoryItem)

    # Decide "in_stock" using the same single source of truth as mark_sold()
    status_raw = str(getattr(item, "status", ""))
    sold_flag = (status_raw == str(sold_key))
    in_stock_flag = True

    # If a boolean exists, prefer that
    if _model_has_field(InventoryItem, "in_stock"):
        in_stock_flag = bool(getattr(item, "in_stock", False))
    else:
        # derive: not sold, no sold_at, and (is_active if present)
        sold_at = getattr(item, "sold_at", None)
        is_active = getattr(item, "is_active", True)
        in_stock_flag = (not sold_flag) and (sold_at is None) and bool(is_active)

    # A mismatch means: item exists but not at the requested location (if location_id provided)
    mismatch = False
    if loc_id is not None:
        cur = getattr(item, "current_location_id", None)
        if cur is None:
            cur = getattr(item, "location_id", None)
        mismatch = (cur != loc_id)

    return JsonResponse({
        "ok": True,
        "exists": True,
        "imei": code,
        "in_stock": bool(in_stock_flag and not sold_flag),
        "status": status_raw,
        "sold_at": getattr(item, "sold_at", None).isoformat() if getattr(item, "sold_at", None) else None,
        "mismatch": bool(mismatch),
    })

# ====================================================================
# 2) Sell endpoint: auto-move (if needed) + mark SOLD atomically
# ====================================================================
@login_required
@require_http_methods(["POST"])
def scan_sold_submit(request: HttpRequest):
    """
    POST fields accepted:
      - code / imei
      - price / selling_price / final_price
      - sale_location_id / location / current_location
      - commission_percent (optional)
      - sold_date (optional; default now)

    Behavior:
      - Finds unsold item by IMEI anywhere in the business (locks row).
      - If stored elsewhere, writes StockMovement (if available) and sets item's location to sale location.
      - Marks as SOLD (supports either 'status' or 'sold_at' schema).
      - Creates a Sale row if your project has one.
    """
    # ---- code / imei
    raw = (request.POST.get("code") or request.POST.get("imei") or "").strip()
    if not raw:
        return _err("Missing code", status=400)
    code = _normalize_code(raw)

    # ---- price
    price_raw = (
        request.POST.get("price")
        or request.POST.get("selling_price")
        or request.POST.get("final_price")
        or "0"
    )
    try:
        price = float(price_raw)
        if price < 0:
            return _err("Price must be non-negative", status=400)
    except ValueError:
        return _err("Invalid price", status=400)

    # ---- sale location
    sale_loc_id = (
        request.POST.get("sale_location_id")
        or request.POST.get("location")
        or request.POST.get("current_location")
    )
    if not sale_loc_id:
        return _err("Missing sale location", status=400)

    commission_percent = request.POST.get("commission_percent") or None
    business = _current_business_from_request(request)
    if business is None:
        return _err("No business on session/user.", status=400)

    # Resolve models defensively
    try:
        from inventory.models import Location
    except Exception:
        Location = None
    try:
        from inventory.models import StockMovement
    except Exception:
        StockMovement = None
    try:
        from sales.models import Sale
    except Exception:
        try:
            from inventory.models import Sale
        except Exception:
            Sale = None

    # Validate the sale location if we have a Location model
    sale_loc = None
    if Location is not None:
        try:
            sale_loc = Location.objects.get(id=sale_loc_id, business=business)
        except Exception:
            return _err("Invalid sale location", status=400)

    with transaction.atomic():
        # Lock the row to avoid double-sell races
        item = get_instock_item_for_business(business, code, for_update=True)
        if not item:
            return _err("Item not found or already sold", status=404)

        # Determine which location field we use on the item
        item_loc_field = "current_location" if hasattr(item, "current_location") else ("location" if hasattr(item, "location") else None)
        item_loc_id = getattr(item, f"{item_loc_field}_id", None) if item_loc_field else None

        # Auto-move if needed (NEVER block sale if movement fails)
        if sale_loc is not None and item_loc_field and item_loc_id and int(item_loc_id) != int(sale_loc.id):
            if StockMovement is not None:
                try:
                    StockMovement.objects.create(
                        business=business if hasattr(StockMovement, "business") else None,
                        item=item if hasattr(StockMovement, "item") else None,
                        from_location=getattr(item, item_loc_field, None) if hasattr(StockMovement, "from_location") else None,
                        to_location=sale_loc if hasattr(StockMovement, "to_location") else None,
                        reason="auto-move-on-sale" if hasattr(StockMovement, "reason") else None,
                        moved_by=request.user if hasattr(StockMovement, "moved_by") else None,
                        moved_at=timezone.now() if hasattr(StockMovement, "moved_at") else None,
                    )
                except Exception:
                    # movement failed â€” do not block the sale
                    pass
            try:
                setattr(item, item_loc_field, sale_loc)
                item.save(update_fields=[item_loc_field])
            except Exception:
                pass

        # Mark SOLD (cover both schemas)
        updates = []
        if hasattr(item, "sold_at"):
            item.sold_at = timezone.now(); updates.append("sold_at")
        if hasattr(item, "sold_price"):
            item.sold_price = price; updates.append("sold_price")
        if hasattr(item, "sold_by"):
            item.sold_by = request.user; updates.append("sold_by")
        if hasattr(item, "status"):
            item.status = "SOLD"; updates.append("status")
        item.save(update_fields=list(set(updates)) if updates else None)

        # Create Sale record if present
        if Sale is not None:
            try:
                Sale.objects.create(
                    business=business if hasattr(Sale, "business") else None,
                    item=item if hasattr(Sale, "item") else None,
                    code=getattr(item, "imei", None) or getattr(item, "code", code) if hasattr(Sale, "code") else None,
                    price=price if hasattr(Sale, "price") else None,
                    location=sale_loc if hasattr(Sale, "location") else None,
                    sold_at=getattr(item, "sold_at", timezone.now()) if hasattr(Sale, "sold_at") else None,
                    sold_by=request.user if hasattr(Sale, "sold_by") else None,
                    commission_percent=commission_percent if hasattr(Sale, "commission_percent") else None,
                )
            except Exception:
                # Donâ€™t block the sale if Sale row fails
                pass

    return _ok({"sold": True, "code": code, "price": price})


# ====================================================================
# Your existing views (kept; minor safety imports added where needed)
# ====================================================================

@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def update_stock(request, pk):
    """
    Inventory Â· Update Stock
    - Scopes the item to the active business.
    - Only managers/admins can edit inventory (your existing _can_edit_inventory).
    - Admins can optionally bulk-propagate price fields across same product in the same business.
    - HTML by default; JSON only when explicitly requested.
    """
    from django.contrib import messages
    from django.http import JsonResponse
    from django.shortcuts import redirect, render, get_object_or_404
    from django.utils import timezone
    from django.core.mail import mail_admins

    # Guards for missing models/forms (assumes these references exist elsewhere)
    try:
        from inventory.models import InventoryItem
    except Exception:
        InventoryItem = None
    try:
        from inventory.forms import InventoryItemForm
    except Exception:
        InventoryItemForm = None

    # External helpers expected in your codebase
    from .views_helpers import _wants_json, _scoped, _can_edit_inventory, _audit, _is_agent_user, _is_admin  # adjust path if needed

    # Guards for missing models/forms
    if InventoryItem is None or InventoryItemForm is None:
        msg = "Inventory editing is not available."
        if _wants_json(request):
            return JsonResponse({"ok": False, "error": msg}, status=500)
        messages.error(request, msg)
        return redirect("inventory:stock_list")

    # Only load items from the active business
    item = get_object_or_404(_scoped(InventoryItem.objects, request), pk=pk)

    # Permission check
    if not _can_edit_inventory(request.user):
        msg = (
            f"EDIT attempt BLOCKED: user '{request.user.username}' tried to edit "
            f"item {item.imei or item.pk} at {timezone.now():%Y-%m-%d %H:%M}."
        )
        _audit(item, request.user, "EDIT_DENIED", "Insufficient permissions")
        try:
            mail_admins(subject="Edit attempt blocked", message=msg, fail_silently=True)
        except Exception:
            pass
        if _wants_json(request):
            return JsonResponse({"ok": False, "error": "Only managers/admins can edit inventory items."}, status=403)
        messages.error(request, "Only managers/admins can edit inventory items.")
        return redirect("inventory:stock_list")

    # -------------------- POST --------------------
    if request.method == "POST":
        form = InventoryItemForm(request.POST, instance=item, user=request.user)

        if not form.is_valid():
            if _wants_json(request):
                return JsonResponse({"ok": False, "errors": form.errors}, status=400)
            messages.error(request, "Please correct the errors below.")
            return render(request, "inventory/edit_stock.html", {"form": form, "item": item})

        # Enforce: only agent accounts can hold stock
        new_holder = form.cleaned_data.get("assigned_agent")
        if new_holder and not _is_agent_user(new_holder):
            msg = "Only agent accounts can hold stock. Choose a non-admin user with an AgentProfile."
            if _wants_json(request):
                return JsonResponse({"ok": False, "error": msg}, status=400)
            messages.error(request, msg)
            return render(request, "inventory/edit_stock.html", {"form": form, "item": item})

        changed_fields = list(form.changed_data)

        # Non-admins cannot change prices
        price_fields = {"order_price", "selling_price"}
        if (price_fields & set(changed_fields)) and not _is_admin(request.user):
            msg = "Only admins can edit order/selling prices."
            if _wants_json(request):
                return JsonResponse({"ok": False, "error": msg}, status=403)
            messages.error(request, msg)
            return render(request, "inventory/edit_stock.html", {"form": form, "item": item})

        # Keep old values for audit
        old_vals = {name: getattr(item, name) for name in changed_fields}

        saved_item = form.save()

        # Optional bulk price propagation (admins only)
        bulk_result = {"updated": 0, "fields": {}}
        if _is_admin(request.user):
            bulk_updates = {}
            if "order_price" in changed_fields:
                bulk_updates["order_price"] = form.cleaned_data.get("order_price")
            if "selling_price" in changed_fields:
                bulk_updates["selling_price"] = form.cleaned_data.get("selling_price")

            if bulk_updates:
                base_mgr = (
                    InventoryItem.active
                    if hasattr(InventoryItem, "active")
                    else InventoryItem.objects.filter(is_active=True)
                )
                qs = _scoped(base_mgr, request).filter(product=saved_item.product).exclude(pk=saved_item.pk)
                updated = qs.update(**bulk_updates)
                bulk_result = {"updated": int(updated), "fields": list(bulk_updates.keys())}

                if updated:
                    _audit(
                        saved_item,
                        request.user,
                        "BULK_PRICE_UPDATE",
                        f"Updated {updated} items for product '{saved_item.product}'. Fields: {bulk_updates}",
                    )
                    if not _wants_json(request):
                        messages.info(
                            request,
                            f"Applied {', '.join(bulk_updates.keys())} to {updated} other '{saved_item.product}' item(s).",
                        )

        # Audit the single edit
        details = "Changed fields:\n" + (
            "\n".join([f"{k}: {old_vals.get(k)} \u2192 {getattr(saved_item, k)}" for k in changed_fields])
            if changed_fields
            else "No field changes"
        )
        _audit(saved_item, request.user, "EDIT", details)

        if _wants_json(request):
            payload_item = {
                "id": saved_item.pk,
                "imei": getattr(saved_item, "imei", None),
                "product": str(getattr(saved_item, "product", "")) if getattr(saved_item, "product", None) else None,
                "order_price": getattr(saved_item, "order_price", None),
                "selling_price": getattr(saved_item, "selling_price", None),
                "assigned_agent": getattr(getattr(saved_item, "assigned_agent", None), "id", None),
            }
            return JsonResponse({
                "ok": True,
                "message": "Item updated.",
                "changed_fields": changed_fields,
                "bulk": bulk_result,
                "item": payload_item,
            })

        messages.success(request, "Item updated.")
        return redirect("inventory:stock_list")

    # -------------------- GET (render form) --------------------
    form = InventoryItemForm(instance=item, user=request.user)

    if _wants_json(request):
        payload_item = {
            "id": item.pk,
            "imei": getattr(item, "imei", None),
            "product": str(getattr(item, "product", "")) if getattr(item, "product", None) else None,
            "order_price": getattr(item, "order_price", None),
            "selling_price": getattr(item, "selling_price", None),
            "assigned_agent": getattr(getattr(item, "assigned_agent", None), "id", None),
        }
        return JsonResponse({
            "ok": True,
            "data": {
                "note": "update_stock ready",
                "item": payload_item,
                "can_edit_prices": bool(_is_admin(request.user)),
            }
        })

    return render(request, "inventory/edit_stock.html", {"form": form, "item": item})


@require_POST
@never_cache
@login_required
def delete_stock(request, pk):
    # Local imports to make this function self-contained
    from django.contrib import messages
    from django.shortcuts import redirect, get_object_or_404
    from django.utils import timezone
    from django.core.mail import mail_admins
    from django.db.models.deletion import ProtectedError

    # Expected helpers/models in your codebase
    try:
        from inventory.models import InventoryItem
    except Exception:
        InventoryItem = None
    from .views_helpers import _scoped, _is_admin, _audit  # adjust path if needed

    if InventoryItem is None:
        messages.error(request, "Inventory model not available.")
        return redirect("inventory:stock_list")

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
        # Archive fallback
        if hasattr(item, "is_active"):
            item.is_active = False
            item.save(update_fields=["is_active"])
            _audit(item, request.user, "ARCHIVE_FALLBACK", "ProtectedError: related sales exist; archived instead.")
            messages.info(request, "This item has sales, so it was archived instead of deleted.")
        else:
            messages.error(request, "This item has related sales and cannot be deleted.")
    return redirect("inventory:stock_list")


@never_cache
@login_required
def restock_heatmap_api(request):
    """
    Fallback for cc/urls.py when inventory.api.api_stock_health is missing.
    Delegates to inventory.api.restock_heatmap_api if available,
    otherwise returns an empty payload.
    """
    try:
        from . import api as api_mod  # type: ignore
        if hasattr(api_mod, "restock_heatmap_api"):
            return api_mod.restock_heatmap_api(request)  # type: ignore[attr-defined]
        if hasattr(api_mod, "api_stock_health"):
            return api_mod.api_stock_health(request)  # type: ignore[attr-defined]
    except Exception:
        pass
    return JsonResponse({"ok": True, "heatmap": []})

# (INTENTIONALLY no duplicate api_mark_sold / stock_list / export_csv definitions here;
# keep the versions you already pasted from PART 1 and PART 2.)


# -----------------------
# Dashboard & list
# -----------------------
from django.http import HttpResponseBase  # make sure this import exists

@login_required
def inventory_dashboard(request):
    # Require/resolve active business exactly once
    gate = _require_active_business(request)
    if isinstance(gate, HttpResponseBase):   # redirect/message case
        return gate
    try:
        biz, biz_id = gate                   # expected tuple
    except Exception:
        # Fallback: no active business tuple; be defensive
        biz, biz_id = (None, None)

    # NEW: calendar filter (range: all | 7d | month | day; day: YYYY-MM-DD)
    range_preset, day_str, start_dt, end_dt = get_preset_window(request, default_preset="month")

    # Back-compat: keep old ?period=month behavior if no new range supplied
    period = request.GET.get("period", "month")
    if request.GET.get("range"):
        period = {"7d": "7d", "all": "all", "day": "day"}.get(range_preset, "month")

    model_id = request.GET.get("model") or None
    today = timezone.localdate()
    tomorrow = today + timedelta(days=1)
    month_start = today.replace(day=1)

    # agent home location (for widening visibility)
    user_loc = _user_home_location(request.user)

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
        # WIDEN agent visibility: own items OR unassigned OR at agent's home location
        items_qs = _scoped(
            InventoryItem.objects.select_related("product", "assigned_agent", "current_location"),
            request,
        ).filter(
            Q(assigned_agent=request.user)
            | Q(assigned_agent__isnull=True)
            | (Q(current_location=user_loc) if user_loc else Q(pk__isnull=False) & Q(assigned_agent=request.user))
        )
        scope_label = "My stock (incl. unassigned & location)"

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

    # KPI: today + month + all-time (legacy)
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
    if time_q:
        rank_base = rank_base.filter(time_q)
    elif period == "month":
        rank_base = rank_base.filter(sold_at__gte=month_start)
    elif period == "7d":
        rank_base = rank_base.filter(sold_at__gte=timezone.now() - timedelta(days=7))

    commission_pct_dec = Cast(F("commission_pct"), pct_dec)
    commission_expr = ExpressionWrapper(
        Coalesce(F("price"), Value(0), output_field=dec2)
        * (Coalesce(commission_pct_dec, Value(0), output_field=pct_dec) / Value(100, output_field=pct_dec)),
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

    # Wallet summaries (decimal-safe)
    agent_wallet_summaries = {}
    agent_ids = [row["agent_id"] for row in agent_rank if row.get("agent_id")]
    if agent_ids and WalletTransaction is not None:
        w = _scoped(WalletTransaction.objects, request).filter(ledger="agent", agent_id__in=agent_ids)
        month_start_dt = timezone.make_aware(datetime.combine(month_start, dtime.min))
        today_dt = timezone.make_aware(datetime.combine(today, dtime.max))
        agent_wallet_rows = w.values("agent_id").annotate(
            balance=Coalesce(Sum("amount"), Value(0), output_field=dec2),
            lifetime_commission=Coalesce(Sum(Case(When(type="commission", then="amount"), default=Value(0), output_field=dec2)), Value(0), output_field=dec2),
            lifetime_advance=Coalesce(Sum(Case(When(type="advance", then="amount"), default=Value(0), output_field=dec2)), Value(0), output_field=dec2),
            lifetime_adjustment=Coalesce(Sum(Case(When(type="adjustment", then="amount"), default=Value(0), output_field=dec2)), Value(0), output_field=dec2),
            month_commission=Coalesce(Sum(Case(When(type="commission", created_at__gte=month_start_dt, created_at__lte=today_dt, then="amount"), default=Value(0), output_field=dec2)), Value(0), output_field=dec2),
            month_advance=Coalesce(Sum(Case(When(type="advance", created_at__gte=month_start_dt, created_at__lte=today_dt, then="amount"), default=Value(0), output_field=dec2)), Value(0), output_field=dec2),
            month_adjustment=Coalesce(Sum(Case(When(type="adjustment", created_at__gte=month_start_dt, created_at__lte=today_dt, then="amount"), default=Value(0), output_field=dec2)), Value(0), output_field=dec2),
        )
        for r in agent_wallet_rows:
            uid = r["agent_id"]
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

    # Rank by wallet balance (desc), then earnings, then total sales
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

    # ===== Revenue / Profit last 12 months (scoped to business) =====
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

    profit_expr_month = ExpressionWrapper(
        Coalesce(F("price"), Value(0), output_field=dec2)
        - Coalesce(F("item__order_price"), Value(0), output_field=dec2),
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
        base_items = _scoped(
            InventoryItem.objects.select_related("product", "assigned_agent", "current_location"),
            request,
        )
        items_scope = base_items.filter(
            Q(assigned_agent=request.user)
            | Q(assigned_agent__isnull=True)
            | (Q(current_location=user_loc) if user_loc else Q(pk__isnull=False) & Q(assigned_agent=request.user))
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
            "agent": row["assigned_agent__username"] or "â€”",
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

    # ===== Battery / Stock health =====
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

    if jug_count <= 10:
        stock_health = "Critical"
    elif jug_count <= 30:
        stock_health = "Low"
    else:
        stock_health = "Good"

    # Products dropdown (scoped)
    products = []
    if Product is not None:
        products_qs = _scoped(Product.objects.order_by("brand", "model", "variant"), request)
        products = products_qs.values("id", "brand", "model", "variant")

    # ===== Wallet (current user)
    def _sum(qs):
        return qs.aggregate(s=Coalesce(Sum("amount"), Value(0), output_field=dec2))["s"] or 0

    if WalletTransaction is not None:
        month_qs = _scoped(
            WalletTransaction.objects.filter(
                ledger="agent", agent=request.user, created_at__date__gte=month_start, created_at__date__lte=today
            ),
            request,
        )
        my_month_commission = _sum(month_qs.filter(type="commission"))
        my_month_advance = _sum(month_qs.filter(type="advance"))
        my_month_adjustment = _sum(month_qs.filter(type="adjustment"))
        life_qs = _scoped(WalletTransaction.objects.filter(ledger="agent", agent=request.user), request)
        my_life_commission = _sum(life_qs.filter(type="commission"))
        my_life_advance = _sum(life_qs.filter(type="advance"))
        my_life_adjustment = _sum(life_qs.filter(type="adjustment"))
        my_life_total = _sum(life_qs)
        my_balance = _sum(life_qs)
    else:
        my_month_commission = my_month_advance = my_month_adjustment = 0
        my_life_commission = my_life_advance = my_life_adjustment = my_life_total = 0
        my_balance = 0

    # NEW for UI: Profit Margin (% of selected period)
    profit_margin = int(round((pie_profit / pie_revenue) * 100)) if pie_revenue > 0 else 0

    context = {
        "range": range_preset,
        "filter_day": day_str or "",
        "filter_start": start_dt.isoformat() if start_dt else None,
        "filter_end": end_dt.isoformat() if end_dt else None,
        "period": period,
        "model_id": int(model_id) if model_id else None,
        "products": list(products),
        "agent_rank": agent_rank,
        "agent_wallet_summaries": agent_wallet_summaries,
        "labels_json": json.dumps(last_12_labels),
        "revenue_points_json": json.dumps(revenue_points),
        "profit_points_json": json.dumps(profit_points),
        "pie_data_json": json.dumps([pie_cost, pie_revenue, pie_profit]),
        "agent_rows": agent_rows,
        "jug_count": jug_count,
        "jug_fill_pct": jug_fill_pct,
        "jug_color": jug_color,
        "stock_health": stock_health,
        "is_manager_or_admin": _is_manager_or_admin(request.user),
        "today_count": today_count,
        "mtd_count": mtd_count,
        "all_time_count": all_time_count,
        "today_total": float(today_total or 0),
        "profit_margin": profit_margin,
        "window_count": window_count,
        "window_revenue": window_revenue,
        "kpis": {"scope": scope_label, "today_count": today_count, "month_count": mtd_count, "all_count": all_time_count},
        "wallet": {
            "balance": float(my_balance or 0),
            "month": {
                "commission": float(my_month_commission or 0),
                "advance": float(my_month_advance or 0),
                "adjustment": float(my_month_adjustment or 0),
                "total": float((my_month_commission or 0) + (my_month_advance or 0) + (my_month_adjustment or 0)),
                "month_label": month_start.strftime("%b %Y"),
            },
            "lifetime": {
                "commission": float(my_life_commission or 0),
                "advance": float(my_life_advance or 0),
                "adjustment": float(my_life_adjustment or 0),
                "total": float(my_life_total or 0),
            },
        },
    }

    # --- Feature flags & slide config
    context["PREDICTIVE_ENABLED"]   = bool(getattr(settings, "PREDICTIVE_ENABLED", True))
    context["THEME_ROTATE_ENABLED"] = False
    context["THEME_ROTATE_MS"]      = int(getattr(settings, "THEME_ROTATE_MS", 10000))
    context["THEME_DEFAULT"]        = str(getattr(settings, "THEME_DEFAULT", "style-1"))
    context["ROTATOR_MODE"]         = "off"
    context["DASHBOARD_SLIDES"] = [
        {"key": "trends", "title": "Sales Trends",
         "apis": ["/inventory/api_sales_trend/?period=7d&metric=count",
                  "/inventory/api_profit_bar/",
                  "/inventory/api_top_models/?period=today"]},
        {"key": "cash", "title": "Cash Overview", "apis": ["/inventory/api_cash_overview/"]},
        {"key": "agents", "title": "Agent Performance", "apis": ["/inventory/api_agent_trend/?months=6&metric=sales"]},
    ]

    cache.set(cache_key, context, 60)
    return _render_dashboard_safe(request, context, today, mtd_count, all_time_count)
# --- Wallet page (agent) ------------------------------------------------------
def wallet_page(request):
    """
    Simple read-only wallet page for a specific agent.
    Route: /inventory/wallet/?user=<id>
    """
    User = get_user_model()

    uid = request.GET.get("user") or request.GET.get("agent")
    if not uid:
        return redirect("/inventory/list/")

    target = get_object_or_404(User, pk=uid)

    # Lifetime balance
    balance = (
        WalletTxn.objects.filter(user=target)
        .aggregate(s=Sum("amount"))["s"] or 0
    )

    # Monthly stats
    today = timezone.localdate()
    month_start = today.replace(day=1)
    next_month = (month_start.replace(day=28) + timezone.timedelta(days=4)).replace(day=1)

    monthly_total = (
        WalletTxn.objects.filter(user=target, created_at__gte=month_start, created_at__lt=next_month)
        .aggregate(s=Sum("amount"))["s"] or 0
    )
    monthly_adv = (
        WalletTxn.objects.filter(
            user=target,
            created_at__gte=month_start, created_at__lt=next_month,
            reason="ADVANCE",
        ).aggregate(s=Sum("amount"))["s"] or 0
    )
    lifetime_total = balance

    # Paginated transactions
    txns_qs = WalletTxn.objects.filter(user=target).order_by("-created_at")
    paginator = Paginator(txns_qs, 25)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    def url_for(n):
        q = request.GET.copy()
        q["page"] = n
        return f"{request.path}?{q.urlencode()}"

    ctx = {
        "target": target,
        "balance": balance,
        "monthly_total": monthly_total,
        "monthly_adv": monthly_adv,
        "lifetime_total": lifetime_total,
        "txns": page_obj.object_list,
        "page_obj": page_obj,
        "url_for": url_for,
    }
    return render(request, "agents/wallet.html", ctx)
@with_active_location
def wallet_page(request):
    """
    Simple agent wallet ledger:
    - /inventory/wallet/?user=<id>  (defaults to current user)
    - shows monthly totals + paginated transactions
    """
    User = get_user_model()
    user_id = request.GET.get("user") or getattr(request.user, "id", None)
    target = get_object_or_404(User, id=user_id)

    # Totals
    now = timezone.localtime()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    txns_qs = WalletTxn.objects.filter(user=target).order_by("-created_at")

    def _sum(qs):
        from django.db.models import Sum
        return float(qs.aggregate(s=Sum("amount"))["s"] or 0)

    balance = _sum(txns_qs)
    monthly_total = _sum(txns_qs.filter(created_at__gte=month_start))
    monthly_adv = _sum(txns_qs.filter(created_at__gte=month_start, reason="ADVANCE"))
    lifetime_total = _sum(txns_qs)

    # Pagination
    page = int(request.GET.get("page", 1) or 1)
    pager = Paginator(txns_qs, 25)
    page_obj = pager.get_page(page)

    def url_for(n):
        q = request.GET.copy()
        q["page"] = n
        return f"{request.path}?{q.urlencode()}"

    ctx = {
        "target": target,
        "balance": balance,
        "monthly_total": monthly_total,
        "monthly_adv": monthly_adv,
        "lifetime_total": lifetime_total,
        "txns": page_obj.object_list,
        "page_obj": page_obj,
        "url_for": url_for,
    }
    return render(request, "agents/wallet.html", ctx)

# --- END PART 3/3 ---










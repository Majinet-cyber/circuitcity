# circuitcity/onboarding/views.py
from __future__ import annotations

from typing import Optional

from django.apps import apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse

# Forms may not exist yet in early scaffolding; import defensively.
try:
    from .forms import BusinessForm, make_inventory_item_form  # type: ignore
except Exception:  # pragma: no cover
    BusinessForm = None  # type: ignore

    def make_inventory_item_form():  # type: ignore
        return None


# -----------------------------
# Active-business helpers
# -----------------------------
# Prefer shared tenant helpers if present (thread-local + session), otherwise fall back to session.
try:
    from tenants.utils import set_active_business as _set_active_biz_util  # type: ignore
    from tenants.utils import get_active_business as _get_active_biz_util  # type: ignore
except Exception:  # pragma: no cover
    _set_active_biz_util = None
    _get_active_biz_util = None

SESSION_KEY = "active_business_id"


def _set_active_business(request: HttpRequest, biz) -> None:
    if _set_active_biz_util:
        try:
            _set_active_biz_util(request, biz)
            return
        except Exception:
            pass
    # Fallback: session only
    try:
        request.session[SESSION_KEY] = getattr(biz, "pk", None) if biz else None
        setattr(request, "business", biz)
    except Exception:
        pass


def _get_active_business(request: HttpRequest):
    if _get_active_biz_util:
        try:
            return _get_active_biz_util(request)
        except Exception:
            pass
    try:
        bid = request.session.get(SESSION_KEY)
    except Exception:
        bid = None
    if not bid:
        return None
    try:
        Business = apps.get_model("tenants", "Business")
        return Business.objects.filter(pk=bid).first()
    except Exception:
        return None


# -----------------------------
# Utilities
# -----------------------------
def _safe_reverse(name: str, default: str = "/") -> str:
    try:
        url = reverse(name)
        return url or default
    except NoReverseMatch:
        return default
    except Exception:
        return default


def _business_model():
    try:
        return apps.get_model("tenants", "Business")
    except Exception:
        return None


def _inventory_item_model():
    try:
        return apps.get_model("inventory", "InventoryItem")
    except Exception:
        return None


# -----------------------------
# Views
# -----------------------------
@login_required
def start(request: HttpRequest) -> HttpResponse:
    """
    Smart router: sends the user to the next onboarding step that applies.
    Order: OTP (if configured) -> Create Business -> Add Product -> Dashboard
    """
    # 1) Optional OTP check
    if not getattr(request.user, "is_otp_verified", True):
        url = _safe_reverse("accounts:otp_verify", "")
        if url and url != "/":
            return redirect(url)
        messages.info(request, "OTP step is not configured; skipping.")

    # 2) Business present?
    Business = _business_model()
    if Business is None:
        # Tenants app not ready â€” just go to dashboard/home if it exists
        return redirect(_safe_reverse("dashboard:home", "/"))

    fields = {f.name for f in getattr(Business, "_meta", []).get_fields()} if hasattr(Business, "_meta") else set()
    # Heuristics for ownership
    owner_qs = Business.objects.filter(owner=request.user) if "owner" in fields else Business.objects.none()
    has_any_biz: bool
    if "users" in fields:
        has_any_biz = owner_qs.exists() or Business.objects.filter(users=request.user).exists()
    else:
        has_any_biz = owner_qs.exists()

    if not has_any_biz:
        # No business -> create
        return redirect(_safe_reverse("onboarding:create_business", "/onboarding/"))

    # Set most recent as active if nothing active
    biz = _get_active_business(request)
    if not biz:
        # prefer user's latest, otherwise latest overall the user is related to
        biz = (owner_qs.order_by("-id").first() if owner_qs.exists()
               else Business.objects.order_by("-id").first())
        if biz:
            _set_active_business(request, biz)

    # 3) At least one inventory item?
    Inv = _inventory_item_model()
    if Inv is not None:
        inv_fields = {f.name for f in getattr(Inv, "_meta", []).get_fields()} if hasattr(Inv, "_meta") else set()
        try:
            if "business" in inv_fields and biz:
                has_item = Inv.objects.filter(business=biz).exists()
            else:
                has_item = Inv.objects.exists()
        except Exception:
            has_item = True  # if query fails, don't block onboarding
        if not has_item:
            return redirect(_safe_reverse("onboarding:add_product", "/onboarding/"))

    # 4) Done â†’ dashboard
    return redirect(_safe_reverse("dashboard:home", "/"))


@login_required
def create_business(request: HttpRequest) -> HttpResponse:
    Business = _business_model()
    if Business is None or BusinessForm is None:
        # If tenants or form not wired yet, just bounce to dashboard
        messages.info(request, "Business creation is not available yet.")
        return redirect(_safe_reverse("dashboard:home", "/"))

    if request.method == "POST":
        form = BusinessForm(request.POST)
        if form.is_valid():
            biz = form.save(commit=False)

            # Attach owner if model has it
            fields = {f.name for f in Business._meta.get_fields()}
            if "owner" in fields:
                setattr(biz, "owner", request.user)

            biz.save()

            # Add user to M2M if present
            if "users" in fields:
                try:
                    getattr(biz, "users").add(request.user)
                except Exception:
                    pass

            _set_active_business(request, biz)
            messages.success(request, f'Business â€œ{biz}â€ created.')
            return redirect(_safe_reverse("onboarding:add_product", "/"))
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = BusinessForm()

    # Render template if available, else inline fallback
    try:
        return render(request, "onboarding/create_business.html", {"form": form})
    except Exception:
        html = """
        <main style="max-width:720px;margin:2rem auto;font-family:system-ui,Segoe UI,Inter,Roboto,Arial">
          <h1>Create Business (stub)</h1>
          <p>The template <code>onboarding/create_business.html</code> is missing.</p>
          <p>Form fields:</p>
          <pre>{fields}</pre>
        </main>
        """.format(fields="\n".join(getattr(form, "fields", {}).keys()))
        return HttpResponse(html)


@login_required
def add_product(request: HttpRequest) -> HttpResponse:
    FormFactory = make_inventory_item_form()
    if FormFactory is None:
        messages.warning(request, "Inventory is not set up yet. You can continue without adding a product.")
        return redirect(_safe_reverse("dashboard:home", "/"))

    Form = FormFactory
    if request.method == "POST":
        form = Form(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            Model = obj.__class__

            # Attach business if field exists and we have an active business
            try:
                model_fields = {f.name for f in Model._meta.get_fields()}
            except Exception:
                model_fields = set()

            if "business" in model_fields:
                biz = _get_active_business(request)
                if biz:
                    try:
                        setattr(obj, "business", biz)
                    except Exception:
                        pass

            obj.save()
            messages.success(request, "First product added. You're all set!")
            return redirect(_safe_reverse("dashboard:home", "/"))
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = Form()

    # Render template if available, else inline fallback
    try:
        return render(request, "onboarding/add_product.html", {"form": form})
    except Exception:
        html = """
        <main style="max-width:720px;margin:2rem auto;font-family:system-ui,Segoe UI,Inter,Roboto,Arial">
          <h1>Add Product (stub)</h1>
          <p>The template <code>onboarding/add_product.html</code> is missing.</p>
          <p>Fields:</p>
          <pre>{fields}</pre>
        </main>
        """.format(fields="\n".join(getattr(form, "fields", {}).keys()))
        return HttpResponse(html)



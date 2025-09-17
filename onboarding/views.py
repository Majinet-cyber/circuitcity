# onboarding/views.py
from __future__ import annotations
from django.apps import apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse, NoReverseMatch
from django.utils import timezone

from .forms import BusinessForm, make_inventory_item_form

# If you have helpers for active business in session, reuse them:
def _set_active_business(request, biz):
    request.session["active_business_id"] = biz.pk
    # If your middleware uses 'request.business', it will populate next request


@login_required
def start(request):
    """
    Smart router: sends the user to the next onboarding step that applies.
    Order: OTP (if configured) -> Create Business -> Add Product -> Dashboard
    """
    # OTP step (optional): if you have an OTP verification flag on user/profile
    if not getattr(request.user, "is_otp_verified", True):
        try:
            return redirect(reverse("accounts:otp_verify"))
        except NoReverseMatch:
            messages.info(request, "OTP step is not configured; skipping.")
            # fall-through

    # Business?
    Business = apps.get_model("tenants", "Business")
    user_biz_qs = Business.objects.filter(owner=request.user) if "owner" in {f.name for f in Business._meta.get_fields()} else Business.objects.none()
    has_any_biz = user_biz_qs.exists() or Business.objects.filter(users=request.user).exists() if "users" in {f.name for f in Business._meta.get_fields()} else user_biz_qs.exists()
    if not has_any_biz:
        return redirect("onboarding:create_business")

    # Set the most recent business active (first time)
    biz = (user_biz_qs.order_by("-id").first() if user_biz_qs.exists() else Business.objects.order_by("-id").first())
    if biz:
        _set_active_business(request, biz)

    # Product?
    try:
        Inv = apps.get_model("inventory", "InventoryItem")
        item_qs = Inv.objects.filter(business=biz) if "business" in {f.name for f in Inv._meta.get_fields()} else Inv.objects.all()
        if not item_qs.exists():
            return redirect("onboarding:add_product")
    except Exception:
        # If inventory not ready, skip to dashboard
        pass

    # Done → dashboard
    return redirect("dashboard:home")


@login_required
def create_business(request):
    Business = apps.get_model("tenants", "Business")
    if request.method == "POST":
        form = BusinessForm(request.POST)
        if form.is_valid():
            biz = form.save(commit=False)
            # Safe owner assignment if model has owner/user field
            fns = {f.name for f in Business._meta.get_fields()}
            if "owner" in fns:
                setattr(biz, "owner", request.user)
            biz.save()
            # Add user to M2M if exists
            if "users" in fns:
                getattr(biz, "users").add(request.user)
            _set_active_business(request, biz)
            messages.success(request, f"Business “{biz}” created.")
            return redirect("onboarding:add_product")
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = BusinessForm()
    return render(request, "onboarding/create_business.html", {"form": form})


@login_required
def add_product(request):
    Form = make_inventory_item_form()
    if Form is None:
        messages.warning(request, "Inventory is not set up yet. You'll still be able to use other features.")
        return redirect("dashboard:home")

    if request.method == "POST":
        form = Form(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            # Attach business if field exists
            Model = obj.__class__
            if "business" in {f.name for f in Model._meta.get_fields()}:
                from django.apps import apps
                Biz = apps.get_model("tenants", "Business")
                active_id = request.session.get("active_business_id")
                if active_id:
                    biz = Biz.objects.filter(pk=active_id).first()
                    if biz:
                        setattr(obj, "business", biz)
            obj.save()
            messages.success(request, "First product added. You're all set!")
            return redirect("dashboard:home")
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = Form()
    return render(request, "onboarding/add_product.html", {"form": form})

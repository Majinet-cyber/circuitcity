# views_products_v2.py
# -------------------------------------------------------------------
# v2 product flows with a session-aware router and sane Scan IN guard
# -------------------------------------------------------------------

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

V2_LOADED = True

try:
    from core.decorators import manager_required  # type: ignore
except Exception:  # pragma: no cover
    def manager_required(fn):
        return fn

from .models import Product, InventoryItem

# -------------------------- business helpers ------------------------
try:
    from tenants.utils import get_active_business  # type: ignore
except Exception:  # pragma: no cover
    def get_active_business(_request):
        return getattr(_request, "business", None)

try:
    from .forms import _is_phone_business, get_product_qs_for_business  # type: ignore
except Exception:  # fallback
    def _is_phone_business(_biz) -> bool:  # type: ignore
        name = (getattr(_biz, "vertical", None) or getattr(_biz, "category", None) or "").strip().lower()
        return name not in {"clothing", "fashion", "apparel", "liquor", "bar", "pub"}

    def get_product_qs_for_business(_biz):  # type: ignore
        return Product.objects.all()

URL_NAME_PHONES   = "inventory:merch_product_new"
URL_NAME_LIQUOR   = "inventory:liquor_product_new_v2"
URL_NAME_CLOTHING = "inventory:clothing_product_new_v2"

# -------------------------- vertical helpers ------------------------
def _vertical_key(value: Optional[str]) -> str:
    v = (value or "").strip().lower()
    if v in {"clothing", "fashion", "apparel"}:
        return "clothing"
    if v in {"liquor", "bar", "pub"}:
        return "liquor"
    return "phones"

def _infer_vertical(request) -> str:
    """
    Order of truth:
      0) session flag set by our router earlier
      1) explicit path kwarg (?category or kwarg)
      2) business attributes
      3) default: phones
    """
    try:
        sess_v = (request.session.get("active_business_vertical") or "").strip().lower()
        if sess_v in {"phones", "clothing", "liquor"}:
            return sess_v
    except Exception:
        pass

    # from URL
    cat = None
    if getattr(request, "resolver_match", None):
        cat = request.resolver_match.kwargs.get("category")
    cat = (request.GET.get("category") or cat or "").strip().lower()
    if cat:
        return _vertical_key(cat)

    # from business
    biz = get_active_business(request)
    for attr in ("template_key", "vertical", "category", "industry", "type", "kind", "sector"):
        val = getattr(biz, attr, None)
        if isinstance(val, str) and val.strip():
            return _vertical_key(val)

    return "phones"

def _redirect_for_vertical(vertical: str):
    if vertical == "clothing":
        return URL_NAME_CLOTHING
    if vertical == "liquor":
        return URL_NAME_LIQUOR
    return URL_NAME_PHONES

# -------------------------- queryset scoping ------------------------
def _product_base_qs(request):
    biz = get_active_business(request)
    if hasattr(Product, "business_id"):
        if _is_phone_business(biz):
            return Product.objects.all()
        return Product.objects.filter(business_id=getattr(biz, "id", biz))
    return get_product_qs_for_business(biz)

def _assign_if_has(obj, field: str, value):
    if hasattr(obj, field):
        setattr(obj, field, value)

# ========================= PHONES v2 ===============================
BRAND_CHOICES: list[tuple[str, str]] = [
    ("Tecno", "Tecno"),
    ("Itel", "Itel"),
    ("Samsung", "Samsung"),
    ("Huawei", "Huawei"),
    ("iPhone", "iPhone"),
    ("Other", "Otherâ€¦"),
]
SPEC_SUGGESTIONS = ["64+2", "64+3", "128+4", "128+8", "256+8"]

def _inflate_phone(instance: Product, data: dict):
    brand = data.get("brand") or ""
    model_number = data.get("model_number") or ""
    phone_name = data.get("phone_name") or ""
    specs = data.get("specs") or ""
    price: Optional[Decimal] = data.get("price")

    _assign_if_has(instance, "brand", brand)
    for f in ("model_number", "model", "sku"):
        _assign_if_has(instance, f, model_number)

    if hasattr(instance, "phone_name"):
        instance.phone_name = phone_name
    elif hasattr(instance, "name"):
        instance.name = phone_name
    elif hasattr(instance, "title"):
        instance.title = phone_name
    else:
        _assign_if_has(instance, "variant", phone_name)

    _assign_if_has(instance, "specs", specs)

    if price is not None:
        for f in ("price", "sale_price", "cost_price"):
            if hasattr(instance, f):
                setattr(instance, f, price)
                break

def _initial_from_phone(p: Product) -> dict:
    def _get(*names: str, default: str = "") -> str:
        for n in names:
            if hasattr(p, n):
                v = getattr(p, n)
                if v:
                    return str(v)
        return default

    brand_val = _get("brand")
    if brand_val and brand_val not in dict(BRAND_CHOICES):
        brand_initial = "Other"
        brand_other = brand_val
    else:
        brand_initial = brand_val or ""
        brand_other = ""

    price_val = None
    for f in ("price", "sale_price", "cost_price"):
        if hasattr(p, f):
            v = getattr(p, f)
            if v not in (None, ""):
                price_val = v
                break

    return {
        "brand": brand_initial,
        "brand_other": brand_other,
        "model_number": _get("model_number", "model", "sku"),
        "phone_name": _get("phone_name", "name", "title", "variant"),
        "specs": _get("specs"),
        "price": price_val,
    }

class PhoneProductForm(forms.Form):
    brand = forms.ChoiceField(
        choices=BRAND_CHOICES,
        widget=forms.Select(attrs={"id": "id_brand_select", "class": "form-select input"})
    )
    model_number = forms.CharField(
        max_length=80, required=False,
        widget=forms.TextInput(attrs={"class": "form-control input", "placeholder": "e.g. A56, SM-A146B"})
    )
    specs = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control input", "list": "specs-list", "placeholder": "e.g. 128+4"})
    )
    phone_name = forms.CharField(
        max_length=120,
        widget=forms.TextInput(attrs={"class": "form-control input", "placeholder": "e.g. Spark Go 2024"})
    )
    price = forms.DecimalField(
        max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control input", "step": "0.01", "min": "0"})
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("brand") == "Other":
            other = (self.data.get("brand_other") or "").strip()
            if not other:
                self.add_error("brand", "Type a brand name for 'Other'.")
            else:
                cleaned["brand"] = other
        return cleaned

@login_required
@manager_required
def product_create_v2(request):
    qs = _product_base_qs(request)

    if request.method == "POST":
        form = PhoneProductForm(request.POST)
        if form.is_valid():
            p = Product()
            if hasattr(Product, "business_id"):
                biz = get_active_business(request)
                if biz is not None:
                    setattr(p, "business_id", getattr(biz, "id", biz))
            _inflate_phone(p, form.cleaned_data)
            try:
                p.save()
                messages.success(request, "Product saved.")
                return redirect(URL_NAME_PHONES)
            except IntegrityError:
                messages.error(request, "Could not save item due to a uniqueness constraint.")
    else:
        form = PhoneProductForm()

    products = qs.order_by("-id")[:50]
    ctx = {"form": form, "products": products, "specs_suggestions": SPEC_SUGGESTIONS, "vertical": "phones"}
    return render(request, "inventory/products/new_v2.html", ctx)

@login_required
@manager_required
def product_edit_v2(request, pk: int):
    qs = _product_base_qs(request)
    obj = get_object_or_404(qs, pk=pk)

    if request.method == "POST":
        form = PhoneProductForm(request.POST)
        if form.is_valid():
            _inflate_phone(obj, form.cleaned_data)
            try:
                obj.save()
                messages.success(request, "Product updated.")
                return redirect(URL_NAME_PHONES)
            except IntegrityError:
                messages.error(request, "Could not update item due to a uniqueness constraint.")
    else:
        form = PhoneProductForm(initial=_initial_from_phone(obj))

    products = qs.order_by("-id")[:50]
    ctx = {"form": form, "products": products, "specs_suggestions": SPEC_SUGGESTIONS, "vertical": "phones"}
    return render(request, "inventory/products/new_v2.html", ctx)

# ========================= DELETE (shared) =======================
@login_required
@manager_required
@require_POST
def product_delete_v2(request, pk: int):
    qs = _product_base_qs(request)
    product = get_object_or_404(qs, pk=pk)

    vertical = _infer_vertical(request)
    redirect_name = _redirect_for_vertical(vertical)

    if InventoryItem.objects.filter(product=product).exists():
        messages.error(request, "Can't delete: this product has stock or sales history.")
        return redirect(redirect_name)

    try:
        product.delete()
        messages.success(request, "Product deleted.")
    except ProtectedError:
        messages.error(request, "Can't delete this product because other records depend on it (e.g., inventory items).")

    return redirect(redirect_name)

# ========================= LIQUOR v2 =============================
class LiquorProductForm(forms.Form):
    liquor_name = forms.CharField(
        max_length=120,
        widget=forms.TextInput(attrs={"class": "form-control input", "placeholder": "e.g. Hunterâ€™s Gold"})
    )
    price_bottle = forms.DecimalField(
        max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control input", "step": "0.01", "min": "0"})
    )
    price_shot = forms.DecimalField(
        max_digits=12, decimal_places=2, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control input", "step": "0.01", "min": "0"})
    )
    shots_per_bottle = forms.IntegerField(
        min_value=1, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control input", "placeholder": "e.g. 25"})
    )
    qty_bottles = forms.IntegerField(
        min_value=0, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control input"})
    )

def _inflate_liquor(instance: Product, data: dict):
    if hasattr(instance, "liquor_name"):
        instance.liquor_name = data.get("liquor_name") or ""
    elif hasattr(instance, "name"):
        instance.name = data.get("liquor_name") or ""
    elif hasattr(instance, "title"):
        instance.title = data.get("liquor_name") or ""
    else:
        _assign_if_has(instance, "variant", data.get("liquor_name") or "")

    for field, value in (("price_bottle", data.get("price_bottle")),
                         ("price_shot", data.get("price_shot"))):
        if value is not None and hasattr(instance, field):
            setattr(instance, field, value)

    _assign_if_has(instance, "shots_per_bottle", data.get("shots_per_bottle"))
    _assign_if_has(instance, "qty_bottles", data.get("qty_bottles"))

@login_required
@manager_required
def product_create_liquor_v2(request):
    qs = _product_base_qs(request)

    if request.method == "POST":
        form = LiquorProductForm(request.POST)
        if form.is_valid():
            p = Product()
            if hasattr(Product, "business_id"):
                biz = get_active_business(request)
                if biz is not None:
                    setattr(p, "business_id", getattr(biz, "id", biz))
            _inflate_liquor(p, form.cleaned_data)
            try:
                p.save()
                messages.success(request, "Liquor item saved.")
                return redirect(URL_NAME_LIQUOR)
            except IntegrityError:
                messages.error(request, "Could not save item due to a uniqueness constraint.")
    else:
        form = LiquorProductForm()

    products = qs.order_by("-id")[:50]
    return render(request, "inventory/products/liquor_v2.html", {"form": form, "products": products, "vertical": "liquor"})

@login_required
@manager_required
def product_edit_liquor_v2(request, pk: int):
    qs = _product_base_qs(request)
    obj = get_object_or_404(qs, pk=pk)

    if request.method == "POST":
        form = LiquorProductForm(request.POST)
        if form.is_valid():
            _inflate_liquor(obj, form.cleaned_data)
            try:
                obj.save()
                messages.success(request, "Liquor item updated.")
                return redirect(URL_NAME_LIQUOR)
            except IntegrityError:
                messages.error(request, "Could not update item due to a uniqueness constraint.")
    else:
        def g(*names, default=None):
            for n in names:
                if hasattr(obj, n):
                    v = getattr(obj, n)
                    if v not in (None, ""):
                        return v
            return default

        initial = {
            "liquor_name": g("liquor_name", "name", "title", "variant", default=""),
            "price_bottle": g("price_bottle", default=None),
            "price_shot": g("price_shot", default=None),
            "shots_per_bottle": g("shots_per_bottle", default=None),
            "qty_bottles": g("qty_bottles", default=None),
        }
        form = LiquorProductForm(initial=initial)

    products = qs.order_by("-id")[:50]
    return render(request, "inventory/products/liquor_v2.html", {"form": form, "products": products, "vertical": "liquor"})

# ========================= CLOTHING v2 ===========================
class ClothingProductForm(forms.Form):
    product_name = forms.CharField(
        max_length=120,
        widget=forms.TextInput(attrs={"class": "form-control input", "placeholder": "e.g. Denim Jacket"})
    )
    size = forms.CharField(
        max_length=32, required=False,
        widget=forms.TextInput(attrs={"class": "form-control input", "placeholder": "e.g. M, 42, 32x30"})
    )
    price = forms.DecimalField(
        max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control input", "step": "0.01", "min": "0"})
    )

def _inflate_clothing(instance: Product, data: dict):
    name = data.get("product_name") or ""
    if hasattr(instance, "name"):
        instance.name = name
    elif hasattr(instance, "title"):
        instance.title = name
    else:
        _assign_if_has(instance, "variant", name)

    _assign_if_has(instance, "size", data.get("size") or "")

    price = data.get("price")
    if price is not None:
        for f in ("price", "sale_price", "cost_price"):
            if hasattr(instance, f):
                setattr(instance, f, price)
                break

def _initial_from_clothing(p: Product) -> dict:
    def g(*names, default=""):
        for n in names:
            if hasattr(p, n):
                v = getattr(p, n)
                if v not in (None, ""):
                    return v
        return default

    price_val = None
    for f in ("price", "sale_price", "cost_price"):
        if hasattr(p, f):
            v = getattr(p, f)
            if v not in (None, ""):
                price_val = v
                break

    return {
        "product_name": g("name", "title", "variant"),
        "size": g("size", default=""),
        "price": price_val,
    }

@login_required
@manager_required
def product_create_clothing_v2(request):
    qs = _product_base_qs(request)

    if request.method == "POST":
        form = ClothingProductForm(request.POST)
        if form.is_valid():
            obj = Product()
            if hasattr(Product, "business_id"):
                biz = get_active_business(request)
                if biz is not None:
                    setattr(obj, "business_id", getattr(biz, "id", biz))
            _inflate_clothing(obj, form.cleaned_data)
            try:
                obj.save()
                messages.success(request, "Clothing item saved.")
                return redirect(URL_NAME_CLOTHING)
            except IntegrityError:
                messages.error(request, "Could not save item due to a uniqueness constraint.")
    else:
        form = ClothingProductForm()

    products = qs.order_by("-id")[:50]
    return render(request, "inventory/add_product_clothing.html",
                  {"form": form, "products": products, "vertical": "clothing"})

@login_required
@manager_required
def product_edit_clothing_v2(request, pk: int):
    qs = _product_base_qs(request)
    obj = get_object_or_404(qs, pk=pk)

    if request.method == "POST":
        form = ClothingProductForm(request.POST)
        if form.is_valid():
            _inflate_clothing(obj, form.cleaned_data)
            try:
                obj.save()
                messages.success(request, "Clothing item updated.")
                return redirect(URL_NAME_CLOTHING)
            except IntegrityError:
                messages.error(request, "Could not update item due to a uniqueness constraint.")
    else:
        form = ClothingProductForm(initial=_initial_from_clothing(obj))

    products = qs.order_by("-id")[:50]
    return render(request, "inventory/add_product_clothing.html",
                  {"form": form, "products": products, "vertical": "clothing"})

# ========================= ROUTER ================================
# DO NOT DECORATE THIS (keeps it pure and avoids redirect loops)
def product_create_v2_router(request, category: str | None = None):
    chosen = _vertical_key(category) if category else _infer_vertical(request)

    # remember in session for future requests
    try:
        request.session["active_business_vertical"] = chosen
    except Exception:
        pass

    if chosen == "clothing":
        return product_create_clothing_v2(request)
    if chosen == "liquor":
        return product_create_liquor_v2(request)
    return product_create_v2(request)


# ========================= SCAN IN GUARD (exported) ==============
# If your urls.py imports and uses this, non-phone tenants will go to dashboard
def scan_in_guarded_view(request, *args, **kwargs):
    """Phones-only access to Scan IN. Others go back to dashboard."""
    biz = get_active_business(request)
    if not _is_phone_business(biz):
        messages.info(request, "Scan IN is for phone shops only.")
        return redirect("inventory:inventory_dashboard")
    # If you already have a Scan-IN page view elsewhere, call it here:
    return render(request, "inventory/scan_in.html", {})



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

from .authz import require_business_kind
from .business_kinds import BusinessKind

V2_LOADED = True

try:
    from core.decorators import manager_required  # type: ignore
except Exception:  # pragma: no cover
    def manager_required(fn):
        return fn

from .models import Product, InventoryItem, MerchProduct

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
        
        # Check for duplicate brand+model+specs combination
        brand = cleaned.get("brand", "").strip()
        model_number = cleaned.get("model_number", "").strip()
        specs = cleaned.get("specs", "").strip()
        
        if brand and model_number and specs:
            # Check if this combination already exists
            from inventory.models import Product
            from tenants.utils import get_active_business
            
            biz = None
            if hasattr(self, 'request'):
                biz = get_active_business(self.request)
            
            qs = Product.objects.filter(
                brand__iexact=brand,
                model__iexact=model_number,
                variant__iexact=specs,
            )
            
            if biz and hasattr(Product, 'business'):
                qs = qs.filter(business=biz)
            
            if qs.exists():
                existing = qs.first()
                raise forms.ValidationError(
                    f"A product with this combination already exists: {existing}. "
                    f"Please use a different brand, model, or specs combination."
                )
        
        return cleaned

@login_required
@manager_required
@require_business_kind(BusinessKind.PHONES)
def product_create_v2(request):
    qs = _product_base_qs(request)

    if request.method == "POST":
        form = PhoneProductForm(request.POST)
        form.request = request  # Pass request to form for validation
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
            except IntegrityError as e:
                # Catch any remaining IntegrityErrors (e.g., from unique 'code' field)
                if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
                    messages.error(request, 
                        "This product already exists. Please check the brand, model, and specs combination.")
                else:
                    messages.error(request, f"Could not save product: {str(e)}")
    else:
        form = PhoneProductForm()

    products = qs.order_by("-id")[:50]
    ctx = {"form": form, "products": products, "specs_suggestions": SPEC_SUGGESTIONS, "vertical": "phones"}
    return render(request, "inventory/products/new_v2.html", ctx)

@login_required
@manager_required
@require_business_kind(BusinessKind.PHONES)
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
@require_business_kind(BusinessKind.PHONES)
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
        widget=forms.TextInput(attrs={"class": "form-control input", "placeholder": "e.g. Hunter's Gold"})
    )
    category = forms.ChoiceField(
        choices=[("", "Select category")] + [("beer", "Beer"), ("cider", "Cider"), ("spirits", "Spirits"), ("wine", "Wine"), ("whiskey", "Whiskey"), ("other", "Other")],
        required=False,
        widget=forms.Select(attrs={"class": "form-control"})
    )
    has_shots = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_has_shots"})
    )
    shots_per_bottle = forms.IntegerField(
        min_value=1, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control input", "placeholder": "e.g. 25", "min": "1"})
    )
    barman_shots_reserved = forms.IntegerField(
        min_value=0, required=False, initial=2,
        widget=forms.NumberInput(attrs={"class": "form-control input", "placeholder": "2", "min": "0"})
    )
    price_bottle = forms.DecimalField(
        max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control input", "step": "0.01", "min": "0", "placeholder": "0.00"})
    )
    cost_per_bottle = forms.DecimalField(
        max_digits=12, decimal_places=2, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control input", "step": "0.01", "min": "0", "placeholder": "0.00"})
    )
    price_shot = forms.DecimalField(
        max_digits=12, decimal_places=2, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control input", "step": "0.01", "min": "0", "placeholder": "0.00"})
    )
    
    # Wine glass pricing
    has_glasses = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_has_glasses"}),
        label="Sell by glass (wine)"
    )
    glasses_per_bottle = forms.IntegerField(
        min_value=1, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control input", "placeholder": "e.g. 5", "min": "1"})
    )
    price_glass = forms.DecimalField(
        max_digits=12, decimal_places=2, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control input", "step": "0.01", "min": "0", "placeholder": "0.00"})
    )
    cost_per_glass = forms.DecimalField(
        max_digits=12, decimal_places=2, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control input", "step": "0.01", "min": "0", "placeholder": "0.00"})
    )
    
    qty_bottles = forms.IntegerField(
        min_value=0, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control input", "min": "0", "placeholder": "0"})
    )
    
    # Smart stock target fields
    target_bottles = forms.IntegerField(
        min_value=0, required=False, initial=0,
        widget=forms.NumberInput(attrs={"class": "form-control input", "min": "0", "placeholder": "0", "title": "Target stock level"})
    )
    auto_adjust_enabled = forms.BooleanField(
        required=False, initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        label="Enable smart auto-adjust"
    )
    auto_adjust_pct = forms.IntegerField(
        min_value=0, max_value=200, required=False, initial=20,
        widget=forms.NumberInput(attrs={"class": "form-control input", "min": "0", "max": "200", "placeholder": "20"})
    )
    
    def clean(self):
        cleaned_data = super().clean()
        has_shots = cleaned_data.get("has_shots")
        shots_per_bottle = cleaned_data.get("shots_per_bottle")
        price_shot = cleaned_data.get("price_shot")
        
        has_glasses = cleaned_data.get("has_glasses")
        glasses_per_bottle = cleaned_data.get("glasses_per_bottle")
        price_glass = cleaned_data.get("price_glass")
        
        # If has_shots is enabled, require shots_per_bottle and price_shot
        if has_shots:
            if not shots_per_bottle:
                raise forms.ValidationError("Shots per bottle is required when shot sales are enabled.")
            if not price_shot:
                raise forms.ValidationError("Price per shot is required when shot sales are enabled.")
        
        # If has_glasses is enabled, require glasses_per_bottle and price_glass
        if has_glasses:
            if not glasses_per_bottle:
                raise forms.ValidationError("Glasses per bottle is required when glass sales are enabled.")
            if not price_glass:
                raise forms.ValidationError("Price per glass is required when glass sales are enabled.")
        
        return cleaned_data

def _inflate_liquor(instance: Product, data: dict):
    """Map form data to MerchProduct/LiquorProduct instance"""
    # Map liquor_name to name field
    if hasattr(instance, "name"):
        instance.name = data.get("liquor_name") or ""
    elif hasattr(instance, "liquor_name"):
        instance.liquor_name = data.get("liquor_name") or ""
    elif hasattr(instance, "title"):
        instance.title = data.get("liquor_name") or ""
    else:
        _assign_if_has(instance, "variant", data.get("liquor_name") or "")

    # Category and shot configuration
    _assign_if_has(instance, "category", data.get("category") or "")
    _assign_if_has(instance, "has_shots", data.get("has_shots") or False)
    _assign_if_has(instance, "shots_per_bottle", data.get("shots_per_bottle"))
    _assign_if_has(instance, "barman_shots_reserved", data.get("barman_shots_reserved") or 2)
    
    # Prices - map to both possible field names
    price_bottle = data.get("price_bottle")
    if price_bottle is not None:
        _assign_if_has(instance, "price_per_bottle", price_bottle)
        _assign_if_has(instance, "price_bottle", price_bottle)
    
    price_shot = data.get("price_shot")
    if price_shot is not None:
        _assign_if_has(instance, "price_per_shot", price_shot)
        _assign_if_has(instance, "price_shot", price_shot)
    
    # Wine glass configuration and pricing
    _assign_if_has(instance, "has_glasses", data.get("has_glasses") or False)
    _assign_if_has(instance, "glasses_per_bottle", data.get("glasses_per_bottle"))
    
    price_glass = data.get("price_glass")
    if price_glass is not None:
        _assign_if_has(instance, "price_per_glass", price_glass)
        _assign_if_has(instance, "price_glass", price_glass)
    
    # Cost prices for profit tracking
    cost_per_bottle = data.get("cost_per_bottle")
    if cost_per_bottle is not None:
        _assign_if_has(instance, "cost_per_bottle", cost_per_bottle)
    
    cost_per_glass = data.get("cost_per_glass")
    if cost_per_glass is not None:
        _assign_if_has(instance, "cost_per_glass", cost_per_glass)
    
    # Smart stock targets
    target_bottles = data.get("target_bottles")
    if target_bottles is not None:
        _assign_if_has(instance, "target_bottles", target_bottles)
    
    auto_adjust_enabled = data.get("auto_adjust_enabled")
    if auto_adjust_enabled is not None:
        _assign_if_has(instance, "auto_adjust_enabled", auto_adjust_enabled)
    
    auto_adjust_pct = data.get("auto_adjust_pct")
    if auto_adjust_pct is not None:
        _assign_if_has(instance, "auto_adjust_pct", auto_adjust_pct)
    
    # Initial stock quantity (not a model field, handle separately if needed)
    # qty_bottles is not saved to the model directly in this flow

@login_required
@manager_required
@require_business_kind(BusinessKind.LIQUOR)
def product_create_liquor_v2(request):
    # Get active business
    business = get_active_business(request)
    
    # Try to seed liquor products if business has none yet
    try:
        from inventory.liquor_seed import should_seed_liquor_products, create_default_liquor_catalog
        if business and should_seed_liquor_products(business):
            create_default_liquor_catalog(business)
    except Exception:
        # Fail silently – we never want seeding to break the page
        pass
    
    qs = _product_base_qs(request)

    if request.method == "POST":
        # NEW: Barcode workflow
        has_barcode = request.POST.get("has_barcode", "no").strip()
        barcode_value = request.POST.get("barcode", "").strip()
        
        # NEW: Barcode validation (conditional)
        if has_barcode == "yes":
            if not barcode_value:
                messages.error(request, "Barcode is required when 'Has Barcode' is Yes.")
                # Re-render form with error
                form = LiquorProductForm(request.POST)
                products = LiquorProduct.objects.filter(
                    business=business,
                    is_archived=False,
                ).order_by("category", "name")
                try:
                    from core.decorators import _is_manager
                    is_manager = _is_manager(request.user)
                except (ImportError, AttributeError):
                    is_manager = request.user.is_staff or request.user.is_superuser
                return render(request, "inventory/products/liquor_v2.html", {
                    "form": form,
                    "products": products,
                    "vertical": "liquor",
                    "active_tab": "liquor_products",
                    "IS_MANAGER": is_manager,
                })
            
            from inventory.utils_barcodes import validate_barcode, normalize_barcode, find_by_barcode
            is_valid, error_msg = validate_barcode(barcode_value)
            if not is_valid:
                messages.error(request, f"Invalid barcode: {error_msg}")
                form = LiquorProductForm(request.POST)
                products = LiquorProduct.objects.filter(
                    business=business,
                    is_archived=False,
                ).order_by("category", "name")
                try:
                    from core.decorators import _is_manager
                    is_manager = _is_manager(request.user)
                except (ImportError, AttributeError):
                    is_manager = request.user.is_staff or request.user.is_superuser
                return render(request, "inventory/products/liquor_v2.html", {
                    "form": form,
                    "products": products,
                    "vertical": "liquor",
                    "active_tab": "liquor_products",
                    "IS_MANAGER": is_manager,
                })
            
            barcode_value = normalize_barcode(barcode_value)
            
            # Check for duplicate barcode in this business
            existing_products = find_by_barcode(barcode_value, business=business)
            if existing_products.exists():
                messages.error(
                    request,
                    f"Barcode {barcode_value} is already used by another product in your business. "
                    "Each barcode must be unique."
                )
                form = LiquorProductForm(request.POST)
                products = LiquorProduct.objects.filter(
                    business=business,
                    is_archived=False,
                ).order_by("category", "name")
                try:
                    from core.decorators import _is_manager
                    is_manager = _is_manager(request.user)
                except (ImportError, AttributeError):
                    is_manager = request.user.is_staff or request.user.is_superuser
                return render(request, "inventory/products/liquor_v2.html", {
                    "form": form,
                    "products": products,
                    "vertical": "liquor",
                    "active_tab": "liquor_products",
                    "IS_MANAGER": is_manager,
                })
        
        form = LiquorProductForm(request.POST)
        if form.is_valid():
            p = Product()
            if hasattr(Product, "business_id"):
                biz = get_active_business(request)
                if biz is not None:
                    setattr(p, "business_id", getattr(biz, "id", biz))
            _inflate_liquor(p, form.cleaned_data)
            
            # NEW: Store barcode if provided
            if has_barcode == "yes" and barcode_value:
                from inventory.utils_barcodes import set_barcode
                set_barcode(p, barcode_value)
            
            try:
                p.save()
                messages.success(request, "Liquor item saved.")
                return redirect(URL_NAME_LIQUOR)
            except IntegrityError:
                messages.error(
                    request, 
                    "A liquor product with this name already exists for your business. "
                    "Please use a different name or modify the existing product."
                )
    else:
        form = LiquorProductForm()

    # Query all liquor products for the business (non-archived)
    from inventory.models import LiquorProduct
    products = LiquorProduct.objects.filter(
        business=business,
        is_archived=False,
    ).order_by("category", "name")
    
    # Check if user is a manager
    try:
        from core.decorators import _is_manager
        is_manager = _is_manager(request.user)
    except (ImportError, AttributeError):
        is_manager = request.user.is_staff or request.user.is_superuser
    
    return render(request, "inventory/products/liquor_v2.html", {
        "form": form,
        "products": products,
        "vertical": "liquor",
        "active_tab": "liquor_products",
        "IS_MANAGER": is_manager,
    })

@login_required
@manager_required
@require_business_kind(BusinessKind.LIQUOR)
def product_edit_liquor_v2(request, pk: int):
    """Edit an existing liquor product"""
    business = get_active_business(request)
    
    # Get the product, ensuring it belongs to this business
    from inventory.models import LiquorProduct
    obj = get_object_or_404(LiquorProduct, pk=pk, business=business)

    if request.method == "POST":
        form = LiquorProductForm(request.POST)
        if form.is_valid():
            _inflate_liquor(obj, form.cleaned_data)
            try:
                obj.save()
                messages.success(request, f"Updated {obj.name}.")
                return redirect(URL_NAME_LIQUOR)
            except IntegrityError as e:
                if 'unique' in str(e).lower():
                    messages.error(request, "A product with this name already exists for your business.")
                else:
                    messages.error(request, "Could not update product due to a database constraint.")
    else:
        def g(*names, default=None):
            """Get first non-empty value from object attributes"""
            for n in names:
                if hasattr(obj, n):
                    v = getattr(obj, n)
                    if v not in (None, ""):
                        return v
            return default

        initial = {
            "liquor_name": g("name", "liquor_name", "title", "variant", default=""),
            "category": g("category", default=""),
            "has_shots": g("has_shots", default=False),
            "shots_per_bottle": g("shots_per_bottle", default=None),
            "barman_shots_reserved": g("barman_shots_reserved", default=2),
            "price_bottle": g("price_per_bottle", "price_bottle", default=None),
            "cost_per_bottle": g("cost_per_bottle", default=None),
            "price_shot": g("price_per_shot", "price_shot", default=None),
            "qty_bottles": None,  # Not stored in model, always blank for edits
            "target_bottles": g("target_bottles", default=0),
            "auto_adjust_enabled": g("auto_adjust_enabled", default=True),
            "auto_adjust_pct": g("auto_adjust_pct", default=20),
        }
        form = LiquorProductForm(initial=initial)

    # Get all liquor products for display
    products = LiquorProduct.objects.filter(
        business=business,
        is_archived=False,
    ).order_by("category", "name")
    
    # Check if user is a manager
    try:
        from core.decorators import _is_manager
        is_manager = _is_manager(request.user)
    except (ImportError, AttributeError):
        is_manager = request.user.is_staff or request.user.is_superuser
    
    return render(request, "inventory/products/liquor_v2.html", {
        "form": form,
        "products": products,
        "vertical": "liquor",
        "active_tab": "liquor_products",
        "IS_MANAGER": is_manager,
        "editing": obj,
    })

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
    confirm_high_price = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        label="I am sure about this high price",
        help_text="Check this if the price is intentionally high (above MK 1,000,000)"
    )
    
    def clean_price(self):
        """Validate that price is reasonable."""
        from decimal import Decimal
        
        price = self.cleaned_data.get('price')
        confirm = self.cleaned_data.get('confirm_high_price', False)
        
        # Define maximum reasonable price for clothing
        MAX_REASONABLE_PRICE = Decimal('1000000.00')  # MK 1 million
        
        if price and price > MAX_REASONABLE_PRICE and not confirm:
            raise forms.ValidationError(
                f"This price (MK {price:,.0f}) looks unusually high for clothing. "
                f"Typical max is MK {MAX_REASONABLE_PRICE:,.0f}. "
                "If correct, tick 'I am sure about this high price' and submit again."
            )
        
        return price

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
@require_business_kind(BusinessKind.CLOTHING)
def product_create_clothing_v2(request):
    business = get_active_business(request)
    
    # Build queryset for display
    products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.CLOTHING,
        is_archived=False
    ).order_by("-id")[:50]

    if request.method == "POST":
        form = ClothingProductForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            
            # Construct unique product name from product_name + size
            # This ensures each size variant gets a unique name
            base_name = data.get("product_name", "").strip()
            size = data.get("size", "").strip()
            
            if size:
                unique_name = f"{base_name} - {size}"
            else:
                unique_name = base_name
            
            # Use update_or_create for idempotent save
            obj, created = MerchProduct.objects.update_or_create(
                business=business,
                name=unique_name,
                defaults={
                    "kind": BusinessKind.CLOTHING,
                    "size": size,
                    "selling_price": data.get("price"),
                    "is_active": True,
                    "track_inventory": True,
                }
            )
            
            if created:
                messages.success(request, f"✅ Clothing product created: {unique_name}")
            else:
                messages.success(request, f"✅ Product already existed, details updated: {unique_name}")
            
            return redirect(URL_NAME_CLOTHING)
    else:
        form = ClothingProductForm()

    return render(request, "inventory/add_product_clothing.html",
                  {"form": form, "products": products, "vertical": "clothing", "active_tab": "clothing_add_product"})

@login_required
@manager_required
@require_business_kind(BusinessKind.CLOTHING)
def product_edit_clothing_v2(request, pk: int):
    business = get_active_business(request)
    
    # Get the specific product being edited
    obj = get_object_or_404(
        MerchProduct.objects.filter(business=business, kind=BusinessKind.CLOTHING),
        pk=pk
    )
    
    # Build queryset for display
    products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.CLOTHING,
        is_archived=False
    ).order_by("-id")[:50]

    if request.method == "POST":
        form = ClothingProductForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            
            # Update the existing product
            obj.size = data.get("size", "").strip()
            obj.selling_price = data.get("price")
            
            # Update name if product_name or size changed
            base_name = data.get("product_name", "").strip()
            size = obj.size
            
            if size:
                new_name = f"{base_name} - {size}"
            else:
                new_name = base_name
            
            # Check if name change would conflict
            if obj.name != new_name:
                existing = MerchProduct.objects.filter(
                    business=business,
                    name=new_name
                ).exclude(pk=obj.pk).first()
                
                if existing:
                    messages.error(
                        request,
                        f"A product with name '{new_name}' already exists. "
                        "Please use a different product name or size."
                    )
                else:
                    obj.name = new_name
                    obj.save()
                    messages.success(request, f"✅ Clothing item updated: {new_name}")
                    return redirect(URL_NAME_CLOTHING)
            else:
                obj.save()
                messages.success(request, f"✅ Clothing item updated: {obj.name}")
                return redirect(URL_NAME_CLOTHING)
    else:
        # Extract base name (remove size suffix if present)
        current_name = obj.name
        size = obj.size or ""
        
        if size and current_name.endswith(f" - {size}"):
            base_name = current_name[:-len(f" - {size}")]
        else:
            base_name = current_name
        
        form = ClothingProductForm(initial={
            "product_name": base_name,
            "size": size,
            "price": obj.selling_price,
        })

    return render(request, "inventory/add_product_clothing.html",
                  {"form": form, "products": products, "vertical": "clothing", "active_tab": "clothing_edit_product", "editing": True, "product_id": pk})

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



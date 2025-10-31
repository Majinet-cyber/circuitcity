# inventory/forms.py
from decimal import Decimal
from typing import Optional

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Product, Location, InventoryItem

# Optional import for Admin Purchase Orders (lives in wallet app)
try:
    from wallet.models import AdminPurchaseOrder, AdminPurchaseOrderItem
except Exception:  # pragma: no cover - if wallet not installed yet
    AdminPurchaseOrder = None
    AdminPurchaseOrderItem = None

# Try to use the robust default-location helper (safe if tenants.utils not present)
try:
    from tenants.utils import get_default_location_for
except Exception:  # pragma: no cover
    get_default_location_for = None  # type: ignore

# NEW: try to resolve the active business from request if not passed explicitly
try:
    # Prefer a utils location; fall back to middleware if that’s where yours lives.
    from tenants.utils import get_active_business as _get_active_business  # type: ignore
except Exception:
    try:
        from tenants.middleware import get_active_business as _get_active_business  # type: ignore
    except Exception:
        _get_active_business = None  # type: ignore

User = get_user_model()

# ---------------- IMEI helpers ----------------
IMEI_ERROR = "IMEI must be exactly 15 digits."


def _normalize_imei(v: str) -> str:
    """Keep digits only (some scanners add spaces/dashes)."""
    return "".join(ch for ch in (v or "") if ch.isdigit())


def _validate_imei_15(imei: str):
    if len(imei) != 15 or not imei.isdigit():
        raise ValidationError(IMEI_ERROR)


# ---------------- Base styled forms ----------------
class StyledForm(forms.Form):
    """
    Adds the .input class to all widgets automatically for consistent styling.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            css = f.widget.attrs.get("class", "")
            f.widget.attrs["class"] = (css + " input").strip()


class StyledModelForm(forms.ModelForm):
    """
    Same as StyledForm but for ModelForms.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            css = f.widget.attrs.get("class", "")
            f.widget.attrs["class"] = (css + " input").strip()


# ---------- Helpers for tenant-aware defaults ----------
def _default_location_for(user, business, qs):
    """
    Given a queryset of locations restricted to a business, pick the best default:
      1) user's AgentProfile.location (if within qs)
      2) a location whose name equals the business name
      3) first in queryset
    """
    # 1) Agent's home location
    try:
        if user is not None and hasattr(user, "agent_profile") and user.agent_profile.location_id:
            if qs.filter(id=user.agent_profile.location_id).exists():
                return user.agent_profile.location
    except Exception:
        pass

    # 2) Business name match (your "store name" default)
    try:
        if business is not None and getattr(business, "name", None):
            match = qs.filter(name=business.name).first()
            if match:
                return match
    except Exception:
        pass

    # 3) First available
    try:
        return qs.first()
    except Exception:
        return None


# ---------- Product scoping (stop cross-vertical leakage) ----------
def _is_phone_business(business) -> bool:
    """
    Return True if this tenant is a Phones/Mobile business and should
    see the shared phones catalog.
    """
    if not business:
        return False
    for attr in ("vertical", "category", "industry", "type", "kind"):
        val = getattr(business, attr, None)
        if isinstance(val, str) and val:
            v = val.strip().lower()
            if v in {"phone", "phones", "mobile", "mobiles", "electronics"}:
                return True
    return False


def get_product_qs_for_business(business):
    """
    If business is a 'phones' tenant -> shared catalog (all Products).
    Otherwise -> only products that exist in THIS tenant's inventory rows.
    """
    base = Product.objects.all()
    if _is_phone_business(business):
        return base.order_by("brand", "model", "variant", "id")

    return (
        base.filter(inventoryitem__business=business)
            .distinct()
            .order_by("brand", "model", "variant", "id")
    )


# ---------- Scan IN ----------
class ScanInForm(StyledForm):
    imei = forms.CharField(
        label="IMEI",
        max_length=15,
        help_text="Exactly 15 digits",
        widget=forms.TextInput(attrs={
            "autofocus": "autofocus",
            "inputmode": "numeric",
            "maxlength": "15",
            "minlength": "15",
            "pattern": r"\d{15}",
            "placeholder": "15-digit IMEI",
            "id": "id_imei",
        }),
    )
    product = forms.ModelChoiceField(
        queryset=Product.objects.none(),
        widget=forms.Select(attrs={"id": "id_product"})
    )
    order_price = forms.DecimalField(
        label="Order price",
        max_digits=12,
        decimal_places=2,
        required=False,
        help_text="If left blank, we’ll use the model’s default order price.",
        widget=forms.NumberInput(attrs={"id": "id_order_price", "step": "any"})
    )
    received_at = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "id": "id_received_at"}),
        label="Received date"
    )
    location = forms.ModelChoiceField(
        queryset=Location.objects.none(),
        required=False,
        empty_label="---------",
        widget=forms.Select(attrs={"id": "id_location"})
    )
    assigned_to_me = forms.BooleanField(
        label="Assign to me",
        required=False,
        initial=True
    )

    def __init__(self, *args, request=None, user=None, business=None, lock_location: bool = True, **kwargs):
        """
        Prefer passing request=… so we can resolve business + default location.
        For backward-compat, user/business still work.

        NEW:
        - If business is None and we have request + _get_active_business, derive it.
        - When lock_location=True (default), the select is disabled BUT a value is still
          submitted (handled in clean()) so your POST stays valid.
        """
        super().__init__(*args, **kwargs)

        # Resolve business from request if not explicitly passed
        if business is None and request is not None and _get_active_business:
            try:
                business = _get_active_business(request)
            except Exception:
                business = None

        # Product list
        self.fields["product"].queryset = get_product_qs_for_business(business)

        # Location list (restricted to business)
        loc_qs = Location.objects.all()
        if business is not None:
            loc_qs = loc_qs.filter(business=business)
        loc_qs = loc_qs.order_by("name")
        self.fields["location"].queryset = loc_qs

        # Default location: request-aware first, then legacy fallback
        initial_loc = None
        if request is not None and get_default_location_for:
            try:
                initial_loc = get_default_location_for(request)
            except Exception:
                initial_loc = None
        if not initial_loc:
            initial_loc = _default_location_for(user, business, loc_qs)

        # Store for clean() fallback and optionally lock the widget
        self._initial_location_obj = initial_loc
        if initial_loc:
            try:
                self.fields["location"].initial = initial_loc.id
            except Exception:
                pass

        if lock_location:
            # Lock visually; we'll still ensure a value posts in clean()
            self.fields["location"].widget.attrs["disabled"] = "disabled"

        # Auto-fill order_price from selected product (initial render only)
        try:
            product = self.initial.get("product") or self.data.get("product")
            if product and not self.initial.get("order_price") and not self.data.get("order_price"):
                if isinstance(product, Product):
                    self.fields["order_price"].initial = product.cost_price
                else:
                    p = Product.objects.filter(pk=product).only("cost_price").first()
                    if p:
                        self.fields["order_price"].initial = p.cost_price
        except Exception:
            pass

    def clean_imei(self):
        raw = self.cleaned_data.get("imei", "")
        imei = _normalize_imei(raw)
        _validate_imei_15(imei)
        return imei

    def clean_order_price(self):
        price = self.cleaned_data.get("order_price")
        if price is not None and price < 0:
            raise ValidationError("Order price cannot be negative.")
        return price

    def clean(self):
        cleaned = super().clean()
        # If location was disabled, browsers won’t POST its value; ensure it’s set.
        if not cleaned.get("location"):
            if self._initial_location_obj is not None:
                cleaned["location"] = self._initial_location_obj
        product = cleaned.get("product")
        price: Optional[Decimal] = cleaned.get("order_price")
        if price in (None, ""):
            if product:
                cleaned["order_price"] = product.cost_price or Decimal("0.00")
            else:
                raise ValidationError("Select a product model to auto-fill the order price.")
        return cleaned


# ---------- Scan SOLD ----------
class ScanSoldForm(StyledForm):
    imei = forms.CharField(
        label="IMEI",
        max_length=15,
        help_text="Exactly 15 digits",
        widget=forms.TextInput(attrs={
            "autofocus": "autofocus",
            "inputmode": "numeric",
            "maxlength": "15",
            "minlength": "15",
            "pattern": r"\d{15}",
            "placeholder": "15-digit IMEI",
            "id": "id_imei",
        }),
    )
    sold_at = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "id": "id_sold_at"}),
        label="Sold date"
    )
    price = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"id": "id_price", "step": "any", "min": "0"})
    )
    commission_pct = forms.DecimalField(
        label="Commission %",
        max_digits=5,
        decimal_places=2,
        initial=0,
        widget=forms.NumberInput(attrs={"id": "id_commission_pct", "step": "any", "min": "0", "max": "100"})
    )
    location = forms.ModelChoiceField(
        queryset=Location.objects.none(),
        widget=forms.Select(attrs={"id": "id_location"})
    )

    def __init__(self, *args, request=None, user=None, business=None, **kwargs):
        """
        Prefer passing request=… so we can use tenants.utils.get_default_location_for().
        For backward-compat, user/business still work.

        NEW:
        - If business is None and we have request + _get_active_business, derive it.
        """
        super().__init__(*args, **kwargs)

        # Resolve business if not provided
        if business is None and request is not None and _get_active_business:
            try:
                business = _get_active_business(request)
            except Exception:
                business = None

        loc_qs = Location.objects.all()
        if business is not None:
            loc_qs = loc_qs.filter(business=business)
        loc_qs = loc_qs.order_by("name")
        self.fields["location"].queryset = loc_qs

        # Default location: request-aware first, then legacy fallback
        initial_loc = None
        if request is not None and get_default_location_for:
            try:
                initial_loc = get_default_location_for(request)
            except Exception:
                initial_loc = None
        if not initial_loc:
            initial_loc = _default_location_for(user, business, loc_qs)

        if initial_loc:
            try:
                self.fields["location"].initial = initial_loc.id
            except Exception:
                pass

    def clean_imei(self):
        raw = self.cleaned_data.get("imei", "")
        imei = _normalize_imei(raw)
        _validate_imei_15(imei)
        return imei

    def clean_price(self):
        price = self.cleaned_data.get("price")
        if price is None or price <= 0:
            raise ValidationError("Price must be greater than 0.")
        return price

    def clean_commission_pct(self):
        pct = self.cleaned_data.get("commission_pct")
        if pct is None:
            return pct
        if pct < 0 or pct > 100:
            raise ValidationError("Commission % must be between 0 and 100.")
        return pct


# ---------- Edit stock (ModelForm) ----------
class InventoryItemForm(forms.ModelForm):
    """
    - IMEI & Product are shown but locked (identity fields).
    - order_price & selling_price are editable only by staff.
    - If a staff user updates either price, all items of the same Product
      get updated in one go (bulk UPDATE).
    """
    class Meta:
        model = InventoryItem
        fields = [
            "imei", "product", "status",
            "order_price", "selling_price",
            "current_location", "assigned_agent",
            "received_at",
        ]
        widgets = {
            "received_at": forms.DateInput(attrs={"type": "date", "class": "input"}),
            "order_price": forms.NumberInput(attrs={"step": "0.01", "class": "input"}),
            "selling_price": forms.NumberInput(attrs={"step": "0.01", "class": "input"}),
            "imei": forms.TextInput(attrs={
                "inputmode": "numeric",
                "maxlength": "15",
                "minlength": "15",
                "pattern": r"\d{15}",
                "placeholder": "15-digit IMEI",
                "class": "input",
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        for name, field in self.fields.items():
            field.widget.attrs.setdefault("class", "input")

        self.fields["imei"].disabled = True
        self.fields["product"].disabled = True

        if not (self.user and self.user.is_staff):
            self.fields["order_price"].disabled = True
            self.fields["selling_price"].disabled = True

    def clean(self):
        cleaned = super().clean()
        if not (self.user and self.user.is_staff):
            for f in ("order_price", "selling_price"):
                if f in self.changed_data:
                    self.add_error(f, "Only admins can edit prices.")
        return cleaned

    @transaction.atomic
    def save(self, commit=True):
        instance = super().save(commit=commit)

        if self.user and self.user.is_staff and self.instance.pk:
            to_update = {}
            if "order_price" in self.changed_data:
                to_update["order_price"] = self.cleaned_data.get("order_price")
            if "selling_price" in self.changed_data:
                to_update["selling_price"] = self.cleaned_data.get("selling_price")
            if to_update:
                InventoryItem.objects.filter(product=instance.product).update(**to_update)

        return instance


# ---------- Product model price quick edit (optional use in Stock List) ----------
class ProductPriceForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["brand", "model", "variant", "cost_price", "sale_price"]
        widgets = {
            "brand": forms.TextInput(attrs={"class": "input"}),
            "model": forms.TextInput(attrs={"class": "input"}),
            "variant": forms.TextInput(attrs={"class": "input"}),
            "cost_price": forms.NumberInput(attrs={"step": "0.01", "class": "input"}),
            "sale_price": forms.NumberInput(attrs={"step": "0.01", "class": "input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["brand"].disabled = True
        self.fields["model"].disabled = True
        self.fields["variant"].disabled = True


# ---------- Place Order (Admin) ----------
class PurchaseOrderHeaderForm(forms.ModelForm if AdminPurchaseOrder else forms.Form):
    """
    Header for AdminPurchaseOrder. Uses MWK by default.
    """
    if AdminPurchaseOrder:
        class Meta:
            model = AdminPurchaseOrder
            fields = [
                "supplier_name", "supplier_email", "supplier_phone",
                "agent_name", "notes", "currency", "tax",
            ]
            widgets = {
                "supplier_name": forms.TextInput(attrs={"class": "input", "placeholder": "Supplier or Company"}),
                "supplier_email": forms.EmailInput(attrs={"class": "input", "placeholder": "supplier@example.com"}),
                "supplier_phone": forms.TextInput(attrs={"class": "input", "placeholder": "+265... (WhatsApp ok)"}),
                "agent_name": forms.TextInput(attrs={"class": "input", "placeholder": "If sending to a specific agent"}),
                "notes": forms.Textarea(attrs={"rows": 3, "class": "input", "placeholder": "Notes for supplier / delivery"}),
                "currency": forms.TextInput(attrs={"class": "input", "placeholder": "MWK"}),
                "tax": forms.NumberInput(attrs={"step": "0.01", "class": "input"}),
            }
    else:
        supplier_name = forms.CharField(max_length=120, required=False)
        supplier_email = forms.EmailField(required=False)
        supplier_phone = forms.CharField(max_length=40, required=False)
        agent_name = forms.CharField(max_length=120, required=False)
        notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 3, "class": "input"}), required=False)
        currency = forms.CharField(max_length=8, initial="MWK", required=False)
        tax = forms.DecimalField(max_digits=14, decimal_places=2, required=False, initial=Decimal("0.00"))


class PurchaseOrderItemForm(StyledForm):
    product = forms.ModelChoiceField(
        queryset=Product.objects.none(),
        widget=forms.Select(attrs={"class": "input"})
    )
    quantity = forms.IntegerField(min_value=1, initial=1, widget=forms.NumberInput(attrs={"class": "input"}))
    unit_price = forms.DecimalField(
        max_digits=12, decimal_places=2, required=False,
        widget=forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
        help_text="If blank, uses the model’s default order price."
    )

    def __init__(self, *args, business=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = get_product_qs_for_business(business)

    def clean(self):
        cleaned = super().clean()
        product: Optional[Product] = cleaned.get("product")
        qty = cleaned.get("quantity")
        up: Optional[Decimal] = cleaned.get("unit_price")

        if not product:
            raise ValidationError("Select a product.")
        if not qty or qty < 1:
            raise ValidationError("Quantity must be at least 1.")

        if up in (None, ""):
            cleaned["unit_price"] = product.cost_price or Decimal("0.00")
        elif up < 0:
            raise ValidationError("Unit price cannot be negative.")

        return cleaned

    def to_model_kwargs(self):
        c = self.cleaned_data
        return {
            "product": c["product"],
            "quantity": c["quantity"],
            "unit_price": c["unit_price"],
        }


# ---------- Agent password reset (forms) ----------
class AgentForgotForm(StyledForm):
    email = forms.EmailField(
        label="Your email",
        widget=forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@example.com"})
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return email
        if user.is_staff or user.groups.filter(name="Admin").exists():
            raise ValidationError("Admins must reset via admin.")
        return email


class AgentResetConfirmForm(StyledForm):
    email = forms.EmailField(
        label="Your email",
        widget=forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@example.com"})
    )
    code = forms.CharField(
        label="Reset code",
        max_length=6, min_length=6,
        widget=forms.TextInput(attrs={
            "inputmode": "numeric",
            "maxlength": "6",
            "placeholder": "6-digit code",
            "autocomplete": "one-time-code",
        })
    )
    new_password1 = forms.CharField(
        label="New password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )
    new_password2 = forms.CharField(
        label="Confirm new password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )

    def clean(self):
        cleaned = super().clean()
        pw1 = cleaned.get("new_password1")
        pw2 = cleaned.get("new_password2")
        if pw1 and pw2 and pw1 != pw2:
            raise ValidationError("Passwords do not match.")
        if pw1:
            validate_password(pw1)
        return cleaned


# ---------- Auth (custom login form) ----------
class CCAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            "class": "input",
            "autofocus": "autofocus",
            "autocomplete": "username",
            "placeholder": "your.username",
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "input",
            "autocomplete": "current-password",
            "placeholder": "•••••••••",
            "id": "password-input",
        })
    )
    remember_me = forms.BooleanField(
        required=False, initial=False, label="Stay signed in for 14 days"
    )


# ---------- Phase 6: CSV Import (products + opening stock) ----------
class CSVImportForm(StyledForm):
    """
    Upload a CSV with headers:
    required: product_code, product_name, location, quantity
    optional: serial_or_imei, cost_price, sale_price
    """
    csv_file = forms.FileField(
        label="CSV file",
        widget=forms.FileInput(attrs={"accept": ".csv", "class": "input"})
    )
    create_missing_products = forms.BooleanField(
        required=False, initial=True,
        label="Create products that don't exist"
    )

    def clean_csv_file(self):
        f = self.cleaned_data.get("csv_file")
        if not f:
            return f
        if f.size == 0:
            raise ValidationError("The uploaded file is empty.")
        return f


# =====================================================================
#               NEW: Merchandise product create forms (SAFE)
# =====================================================================

# We *dynamically* choose fields that actually exist on your models.
from django.apps import apps  # noqa: F401 (kept for installations that need it)
from django.forms import inlineformset_factory, formset_factory  # noqa: F401


def _model_fields(model) -> set[str]:
    try:
        return {f.name for f in model._meta.get_fields()}
    except Exception:
        return set()


def _intersect_fields(model, desired: list[str]) -> list[str]:
    actual = _model_fields(model)
    keep = [f for f in desired if f in actual]
    if keep:
        return keep
    # Minimum sensible fallback if none of the desired names exist.
    for minimal in (["name", "price"], ["name"], ["title"]):
        if all(m in actual for m in minimal):
            return minimal
    # last resort: avoid exploding by returning an empty list; caller handles fallback
    return []


# Try to find your child model for per-pack prices
try:
    from .models import ProductUnitPrice as _UnitPriceModel  # label, multiplier, price, product FK
except Exception:
    try:
        from .models import UnitPrice as _UnitPriceModel
    except Exception:
        _UnitPriceModel = None

# ---------------- Product Create (safe ModelForm or fallback Form) ----------------
# Fields you *might* have across installations. We intersect with the real model.
_DESIRED_PRODUCT_FIELDS = [
    # generic / earlier schema candidates
    "business", "name", "kind", "sku",
    "track_inventory", "scan_required",
    "has_shots", "shots_per_bottle", "base_unit",
    # phone-ish / liquor-ish optional fields
    "brand", "model", "specs", "phone_name",
    "liquor_name", "price_bottle", "price_shot", "qty_bottles",
    # prices commonly on Product
    "cost_price", "sale_price", "price",
]

_PRODUCT_FIELDS = _intersect_fields(Product, _DESIRED_PRODUCT_FIELDS)

if _PRODUCT_FIELDS:
    class MerchProductForm(StyledModelForm):
        """
        Generic product creator used on /inventory/products/new/.
        Only includes fields that actually exist on your Product model.
        """
        class Meta:
            model = Product
            fields = _PRODUCT_FIELDS
            widgets = {
                **({"business": forms.HiddenInput()} if "business" in _PRODUCT_FIELDS else {}),
                **({"name": forms.TextInput(attrs={"class": "input", "placeholder": "Product name"})}
                   if "name" in _PRODUCT_FIELDS else {}),
                **({"kind": forms.TextInput(attrs={"class": "input", "placeholder": "Category / kind"})}
                   if "kind" in _PRODUCT_FIELDS else {}),
                **({"sku": forms.TextInput(attrs={"class": "input", "placeholder": "SKU / code"})}
                   if "sku" in _PRODUCT_FIELDS else {}),
                **({"shots_per_bottle": forms.NumberInput(attrs={"class": "input", "min": "1"})}
                   if "shots_per_bottle" in _PRODUCT_FIELDS else {}),
                **({"base_unit": forms.TextInput(attrs={"class": "input", "placeholder": "unit, bottle, shot…"})}
                   if "base_unit" in _PRODUCT_FIELDS else {}),
                **({"cost_price": forms.NumberInput(attrs={"class": "input", "step": "0.01"})}
                   if "cost_price" in _PRODUCT_FIELDS else {}),
                **({"sale_price": forms.NumberInput(attrs={"class": "input", "step": "0.01"})}
                   if "sale_price" in _PRODUCT_FIELDS else {}),
                **({"price": forms.NumberInput(attrs={"class": "input", "step": "0.01"})}
                   if "price" in _PRODUCT_FIELDS else {}),
            }

        def clean(self):
            cleaned = super().clean()
            # If your schema supports shots, enforce dependency
            if "has_shots" in self.fields and cleaned.get("has_shots"):
                if "shots_per_bottle" in self.fields and not cleaned.get("shots_per_bottle"):
                    self.add_error("shots_per_bottle", "Required when 'has shots' is on.")
                if "base_unit" in self.fields and not cleaned.get("base_unit"):
                    cleaned["base_unit"] = "shot"
            return cleaned
else:
    class MerchProductForm(StyledForm):
        name = forms.CharField(label="Product name", max_length=120, required=True)
        price = forms.DecimalField(label="Price", max_digits=12, decimal_places=2, required=False)


# ---------------- UnitPrice FormSet (safe) ----------------
if _UnitPriceModel is not None:
    _DESIRED_UNITPRICE_FIELDS = ["label", "multiplier", "price", "product"]
    _UNITPRICE_FIELDS = _intersect_fields(_UnitPriceModel, _DESIRED_UNITPRICE_FIELDS)

    if _UNITPRICE_FIELDS:
        class _UnitPriceModelForm(StyledModelForm):
            class Meta:
                model = _UnitPriceModel
                fields = _UNITPRICE_FIELDS
                widgets = {
                    **({"label": forms.TextInput(attrs={"class": "input", "placeholder": "e.g., Bottle / Dozen"})}
                       if "label" in _UNITPRICE_FIELDS else {}),
                    **({"multiplier": forms.NumberInput(attrs={"class": "input", "min": "1"})}
                       if "multiplier" in _UNITPRICE_FIELDS else {}),
                    **({"price": forms.NumberInput(attrs={"class": "input", "step": "0.01"})}
                       if "price" in _UNITPRICE_FIELDS else {}),
                }

        try:
            from django.forms import modelformset_factory
            MerchUnitPriceFormSet = modelformset_factory(
                _UnitPriceModel, form=_UnitPriceModelForm, extra=1, can_delete=True
            )
        except Exception:
            class _UP(StyledForm):
                label = forms.CharField(max_length=60)
                multiplier = forms.IntegerField(min_value=1, initial=1)
                price = forms.DecimalField(max_digits=12, decimal_places=2)
            from django.forms import formset_factory as _fsf  # local alias to be explicit
            MerchUnitPriceFormSet = _fsf(_UP, extra=1, can_delete=True)
    else:
        class _UP(StyledForm):
            label = forms.CharField(max_length=60)
            multiplier = forms.IntegerField(min_value=1, initial=1)
            price = forms.DecimalField(max_digits=12, decimal_places=2)
        from django.forms import formset_factory as _fsf
        MerchUnitPriceFormSet = _fsf(_UP, extra=1, can_delete=True)
else:
    class _UP(StyledForm):
        label = forms.CharField(max_length=60)
        multiplier = forms.IntegerField(min_value=1, initial=1)
        price = forms.DecimalField(max_digits=12, decimal_places=2)
    from django.forms import formset_factory as _fsf
    MerchUnitPriceFormSet = _fsf(_UP, extra=1, can_delete=True)


# =====================================================================
#                           NEW: Location form
# =====================================================================
class BizLocationForm(StyledModelForm):
    """
    Create/edit a shop/branch location.
    Matches your Location model fields:
      - name, city, latitude, longitude, geofence_radius_m, is_default
    """
    class Meta:
        model = Location
        fields = ["name", "city", "latitude", "longitude", "geofence_radius_m", "is_default"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Branch or shop name"}),
            "city": forms.TextInput(attrs={"placeholder": "City / town"}),
            "latitude": forms.NumberInput(attrs={"step": "any", "inputmode": "decimal", "placeholder": "-13.9623"}),
            "longitude": forms.NumberInput(attrs={"step": "any", "inputmode": "decimal", "placeholder": "33.7741"}),
            "geofence_radius_m": forms.NumberInput(attrs={"min": "10", "step": "1", "placeholder": "150"}),
        }

    def clean_latitude(self):
        lat = self.cleaned_data.get("latitude")
        if lat in (None, ""):
            return lat
        try:
            lat = float(lat)
        except Exception:
            raise ValidationError("Latitude must be a number.")
        if lat < -90 or lat > 90:
            raise ValidationError("Latitude must be between -90 and 90.")
        return lat

    def clean_longitude(self):
        lng = self.cleaned_data.get("longitude")
        if lng in (None, ""):
            return lng
        try:
            lng = float(lng)
        except Exception:
            raise ValidationError("Longitude must be a number.")
        if lng < -180 or lng > 180:
            raise ValidationError("Longitude must be between -180 and 180.")
        return lng

    def clean_geofence_radius_m(self):
        r = self.cleaned_data.get("geofence_radius_m")
        if r in (None, ""):
            return 150  # sensible default for your model
        try:
            r = int(r)
        except Exception:
            raise ValidationError("Radius must be a whole number of meters.")
        if r < 10 or r > 10000:
            raise ValidationError("Radius should be between 10m and 10,000m.")
        return r

    def clean(self):
        cleaned = super().clean()
        lat = cleaned.get("latitude")
        lng = cleaned.get("longitude")
        # allow saving a location without GPS, but if one provided, require both
        if (lat is None) ^ (lng is None):
            raise ValidationError("Provide both latitude and longitude, or leave both blank.")
        return cleaned


# =====================================================================
# NEW: Polished Product form for phones (brand dropdown + editable specs)
#      Maps onto your actual Product model columns safely.
#      Intended for: /inventory/merch/products/new/v2/ views
# =====================================================================

# Dropdown choices and specs suggestions
PHONE_BRANDS = ["Tecno", "Itel", "Samsung", "Huawei", "iPhone"]
SPECS_SUGGESTIONS = ["64+2", "64+3", "128+4", "128+8", "256+8"]


class ProductForm(StyledModelForm):
    """
    UX-polished creator:
      - Brand: dropdown (with Other handled in template JS if you prefer)
      - Specs: editable text with <datalist> suggestions (64+2 ... 256+8)
      - Model number, Phone name, Price: free inputs

    This ModelForm adds *extra* fields that might not exist 1:1 in your DB.
    In save(), we map them onto whichever Product columns you actually have:
      - brand -> brand (if exists)
      - model_number -> model (else sku if present)
      - phone_name -> name (else variant if present)
      - price -> price (else sale_price)
      - specs -> specs (if your model has it; else ignored safely)
    """
    # UI fields (always shown)
    brand = forms.ChoiceField(
        choices=[("", "— Select brand —")] + [(b, b) for b in PHONE_BRANDS] + [("Other", "Other…")],
        required=False,
        widget=forms.Select(attrs={"id": "id_brand_select"})
    )
    model_number = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g., KB8, A17, SM-A145F"})
    )
    specs = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g., 128+4", "list": "specs-list"})
    )
    phone_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g., Tecno Pop 7"})
    )
    price = forms.DecimalField(
        required=False, max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0"})
    )

    class Meta:
        model = Product
        # Keep real model fields minimal so ModelForm is valid; we only use extra fields above and map them manually
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # If editing, prefill UI fields from whichever columns exist
        obj = self.instance if getattr(self, "instance", None) and self.instance.pk else None
        if obj:
            mf = _model_fields(Product)
            if "brand" in mf and obj.brand:
                self.fields["brand"].initial = obj.brand
            if "model" in mf and getattr(obj, "model", None):
                self.fields["model_number"].initial = getattr(obj, "model")
            elif "sku" in mf and getattr(obj, "sku", None):
                self.fields["model_number"].initial = getattr(obj, "sku")
            if "specs" in mf and getattr(obj, "specs", None):
                self.fields["specs"].initial = getattr(obj, "specs")
            # Prefer a human name column if available
            for name_col in ("name", "phone_name", "variant", "title"):
                if name_col in mf and getattr(obj, name_col, None):
                    self.fields["phone_name"].initial = getattr(obj, name_col)
                    break
            for price_col in ("price", "sale_price", "cost_price"):
                if price_col in mf and getattr(obj, price_col, None):
                    self.fields["price"].initial = getattr(obj, price_col)
                    break

    def clean_price(self):
        val = self.cleaned_data.get("price")
        if val is not None and val < 0:
            raise ValidationError("Price must be ≥ 0.")
        return val

    def save(self, commit=True):
        """
        Map UI fields to whatever columns exist on Product.
        """
        obj = super().save(commit=False)
        data = self.cleaned_data
        mf = _model_fields(Product)

        # brand
        if "brand" in mf and data.get("brand"):
            setattr(obj, "brand", data["brand"])

        # model number -> model/sku
        if data.get("model_number"):
            if "model" in mf:
                setattr(obj, "model", data["model_number"])
            elif "sku" in mf:
                setattr(obj, "sku", data["model_number"])

        # specs (only if column exists)
        if "specs" in mf and data.get("specs"):
            setattr(obj, "specs", data["specs"])

        # phone name -> prefer 'name', else 'phone_name', else 'variant', else 'title'
        if data.get("phone_name"):
            for name_col in ("name", "phone_name", "variant", "title"):
                if name_col in mf:
                    setattr(obj, name_col, data["phone_name"])
                    break

        # price -> prefer 'price', else 'sale_price'
        if data.get("price") is not None:
            if "price" in mf:
                setattr(obj, "price", data["price"])
            elif "sale_price" in mf:
                setattr(obj, "sale_price", data["price"])

        if commit:
            obj.save()
        return obj

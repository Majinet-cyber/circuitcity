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


# ---------- Scan IN ----------
class ScanInForm(StyledForm):
    """
    Order price is now OPTIONAL for scan-in. If omitted, it auto-fills from the
    selected product's model price (Product.cost_price).
    """
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
        }),
    )
    product = forms.ModelChoiceField(
        queryset=Product.objects.all().order_by("brand", "model", "variant")
    )
    # Optional; will default from Product.cost_price when missing
    order_price = forms.DecimalField(
        label="Order price",
        max_digits=12,
        decimal_places=2,
        required=False,
        help_text="If left blank, we’ll use the model’s default order price."
    )
    received_at = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}), label="Received date"
    )
    location = forms.ModelChoiceField(
        queryset=Location.objects.all().order_by("name")
    )
    assigned_to_me = forms.BooleanField(label="Assign to me", required=False, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ensure selects also get the .input class
        self.fields["product"].widget.attrs.setdefault("class", "input")
        self.fields["location"].widget.attrs.setdefault("class", "input")

        # Try to set an initial order_price from product if available
        # Works for initial render when a product is pre-selected server-side
        try:
            product = self.initial.get("product") or self.data.get("product")
            if product and not self.initial.get("order_price") and not self.data.get("order_price"):
                if isinstance(product, Product):
                    self.fields["order_price"].initial = product.cost_price
                else:
                    # product id in POST/GET
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
        """
        If no order_price provided, take it from the selected product’s cost_price.
        """
        price = self.cleaned_data.get("order_price")
        if price is not None and price < 0:
            raise ValidationError("Order price cannot be negative.")
        return price

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get("product")
        price: Optional[Decimal] = cleaned.get("order_price")
        if price in (None, ""):
            if product:
                cleaned["order_price"] = product.cost_price or Decimal("0.00")
            else:
                # Keep a clear error message if product missing (shouldn’t happen due to field)
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
        }),
    )
    sold_at = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}), label="Sold date"
    )
    # Selling price MUST be entered at scan sold
    price = forms.DecimalField(max_digits=12, decimal_places=2)
    commission_pct = forms.DecimalField(label="Commission %", max_digits=5, decimal_places=2, initial=0)
    location = forms.ModelChoiceField(
        queryset=Location.objects.all().order_by("name")
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["location"].widget.attrs.setdefault("class", "input")

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
        # Accept the current user so we can enforce permissions and bulk updates
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Apply input class to any remaining widgets
        for name, field in self.fields.items():
            field.widget.attrs.setdefault("class", "input")

        # Identity fields are always locked
        self.fields["imei"].disabled = True
        self.fields["product"].disabled = True

        # Prices are staff-only editable
        if not (self.user and self.user.is_staff):
            self.fields["order_price"].disabled = True
            self.fields["selling_price"].disabled = True

    def clean(self):
        cleaned = super().clean()
        # Guard against HTML tampering by non-staff users
        if not (self.user and self.user.is_staff):
            price_fields = {"order_price", "selling_price"}
            if any(f in self.changed_data for f in price_fields):
                # Add field-level errors for clarity
                for f in price_fields:
                    if f in self.changed_data:
                        self.add_error(f, "Only admins can edit prices.")
        return cleaned

    @transaction.atomic
    def save(self, commit=True):
        """
        Save the instance, then if staff changed price fields, propagate
        the new values to all InventoryItem rows with the same Product.
        """
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
    """
    Lets an admin/manager quickly adjust the default model prices:
    - cost_price → used as the default order price (scan-in + place order)
    - sale_price → optional default selling price reference
    """
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
        # Make identity fields read-only to avoid accidental edits in quick forms
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
        # Fallback form if wallet app not present (keeps page functional)
        supplier_name = forms.CharField(max_length=120, required=False)
        supplier_email = forms.EmailField(required=False)
        supplier_phone = forms.CharField(max_length=40, required=False)
        agent_name = forms.CharField(max_length=120, required=False)
        notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 3, "class": "input"}), required=False)
        currency = forms.CharField(max_length=8, initial="MWK", required=False)
        tax = forms.DecimalField(max_digits=14, decimal_places=2, required=False, initial=Decimal("0.00"))


class PurchaseOrderItemForm(StyledForm):
    """
    One line in the Place Order form. If unit_price is omitted, it auto-fills
    from Product.cost_price (the model order price).
    """
    product = forms.ModelChoiceField(
        queryset=Product.objects.all().order_by("brand", "model", "variant"),
        widget=forms.Select(attrs={"class": "input"})
    )
    quantity = forms.IntegerField(min_value=1, initial=1, widget=forms.NumberInput(attrs={"class": "input"}))
    unit_price = forms.DecimalField(
        max_digits=12, decimal_places=2, required=False,
        widget=forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
        help_text="If blank, uses the model’s default order price."
    )

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
        """
        Helper to convert the cleaned form into kwargs suitable for
        AdminPurchaseOrderItem.objects.create(...)
        """
        c = self.cleaned_data
        return {
            "product": c["product"],
            "quantity": c["quantity"],
            "unit_price": c["unit_price"],
            # line_total computed in model.save() if not provided
        }


# ---------- Agent password reset (forms) ----------
class AgentForgotForm(StyledForm):
    """Request a reset code. Always 'succeeds' to avoid user enumeration."""
    email = forms.EmailField(
        label="Your email",
        widget=forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@example.com"})
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        # If the user exists and is admin/staff, block this flow
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return email  # don't reveal existence
        if user.is_staff or user.groups.filter(name="Admin").exists():
            raise ValidationError("Admins must reset via admin.")
        return email


class AgentResetConfirmForm(StyledForm):
    """Enter email + 6-digit code + new password."""
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
    """
    Used by LoginView so we can style fields without calling as_widget(attrs=...) in the template.
    Also includes an optional 'remember_me' checkbox (handled in CCLoginView if you use it).
    """
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
            "placeholder": "••••••••",
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
        # Lightweight content-type / size checks (main limits live in settings)
        if f.size == 0:
            raise ValidationError("The uploaded file is empty.")
        # Many browsers send 'text/csv' or 'application/vnd.ms-excel' for CSV
        return f

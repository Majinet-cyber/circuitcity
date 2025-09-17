# layby/forms.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from random import randint
from typing import Iterable, List, Optional, Tuple

from django import forms
from django.apps import apps
from django.utils import timezone

from .models import LaybyOrder

# -------- inventory helpers --------

_PRICE_FIELDS = ("price", "selling_price", "unit_price", "retail_price", "amount")
_NAME_FIELDS = ("name", "model_name", "title", "model")
_SKU_FIELDS = ("sku", "code", "barcode")


def _first_attr(obj, names: Iterable[str], default=None):
    for n in names:
        if hasattr(obj, n):
            return getattr(obj, n)
    return default


@dataclass
class StockRow:
    name: str
    sku: str
    price: Decimal


def _discover_inventory_queryset():
    """
    Find a reasonable stock list model in the inventory app.
    Returns (qs, model) or (None, None).
    """
    try:
        inv = apps.get_app_config("inventory")
    except Exception:
        return None, None

    candidates = []
    for m in inv.get_models():
        fset = {f.name for f in m._meta.get_fields()}
        if any(n in fset for n in _NAME_FIELDS):
            score = 0
            score += 1 if any(s in fset for s in _SKU_FIELDS) else 0
            score += 1 if any(p in fset for p in _PRICE_FIELDS) else 0
            candidates.append((score, m))

    if not candidates:
        return None, None

    candidates.sort(key=lambda x: x[0], reverse=True)
    model = candidates[0][1]

    try:
        qs = model._default_manager.all()
        if "is_active" in {f.name for f in model._meta.get_fields()}:
            qs = qs.filter(is_active=True)
        return qs[:500], model
    except Exception:
        return None, None


def _rows_from_qs(qs) -> List[StockRow]:
    rows: List[StockRow] = []
    for obj in qs:
        name = _first_attr(obj, _NAME_FIELDS, str(obj)) or ""
        sku = _first_attr(obj, _SKU_FIELDS, "") or ""
        price = _first_attr(obj, _PRICE_FIELDS, Decimal("0"))
        try:
            price = Decimal(price)
        except Exception:
            price = Decimal("0")
        rows.append(StockRow(name=name, sku=str(sku), price=price))
    rows.sort(key=lambda r: (r.name.lower(), r.sku))
    return rows


def _pack_value(row: StockRow) -> str:
    # sku|name|price
    return f"{row.sku}|{row.name}|{row.price}"


def _unpack_value(value: str) -> Tuple[str, str, Decimal]:
    parts = (value or "").split("|", 2)
    if len(parts) != 3:
        return "", value or "", Decimal("0")
    sku, name, price_s = parts
    try:
        price = Decimal(price_s)
    except Exception:
        price = Decimal("0")
    return sku, name, price


# -------- form --------

class LaybyOrderForm(forms.ModelForm):
    """
    Shows a `product` ChoiceField sourced from inventory.
    The choice fills hidden item_name / sku / total_price.

    Also *optionally* exposes extra customer fields if your LaybyOrder model
    defines them: id_number, id_photo, kin1_name/phone, kin2_name/phone.
    """

    product = forms.ChoiceField(label="Product (from stock)")

    class Meta:
        model = LaybyOrder
        fields = [
            "customer_name",
            "customer_phone",
            "product",        # virtual field (ChoiceField) – not on model
            "item_name",      # hidden; set from product
            "sku",            # hidden; set from product
            "term_months",
            "total_price",    # hidden; set from product
            "deposit_amount",
        ]
        widgets = {
            "customer_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Customer full name"}),
            "customer_phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. 0999 000 000", "inputmode": "tel"}),
            "item_name": forms.HiddenInput(),
            "sku": forms.HiddenInput(),
            "term_months": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 12}),
            "total_price": forms.HiddenInput(),
            "deposit_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": 0}),
        }

    # ---- dynamic field injection for optional model columns ----
    OPTIONAL_FIELDS = [
        ("id_number", forms.TextInput(attrs={"class": "form-control", "placeholder": "National ID / Passport"})),
        ("id_photo", forms.ClearableFileInput(attrs={"class": "form-control"})),
        ("kin1_name", forms.TextInput(attrs={"class": "form-control", "placeholder": "Kin #1 full name"})),
        ("kin1_phone", forms.TextInput(attrs={"class": "form-control", "placeholder": "Kin #1 phone", "inputmode": "tel"})),
        ("kin2_name", forms.TextInput(attrs={"class": "form-control", "placeholder": "Kin #2 full name"})),
        ("kin2_phone", forms.TextInput(attrs={"class": "form-control", "placeholder": "Kin #2 phone", "inputmode": "tel"})),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Populate product choices from inventory
        qs, _model = _discover_inventory_queryset()
        choices: List[Tuple[str, str]] = [("", "— Select a product —")]
        if qs is not None:
            rows = _rows_from_qs(qs)
            for r in rows:
                label = f"{r.name} ({r.sku}) – {r.price}"
                choices.append((_pack_value(r), label))
        else:
            self.fields["product"].disabled = True
            choices = [("", "No stock list found (install inventory app)")]
        self.fields["product"].choices = choices

        # If LaybyOrder has any of the optional fields, add them to the form
        model_field_names = {f.name for f in LaybyOrder._meta.get_fields()}
        for fname, widget in self.OPTIONAL_FIELDS:
            if fname in model_field_names:
                # Insert just before term_months for a nicer flow
                self.fields[fname] = forms.CharField(required=(fname != "id_photo"), widget=widget, label=fname.replace("_", " ").title())
                if fname == "id_photo":
                    # Use FileField when present on model; required=False to allow mobile-first capture later
                    self.fields[fname] = forms.FileField(required=False, widget=widget, label="Photo of ID")

                # Keep Meta.fields ordering + inject this field logically
                if fname not in self._meta.fields:
                    insert_at = self._meta.fields.index("term_months")
                    self._meta.fields = self._meta.fields[:insert_at] + [fname] + self._meta.fields[insert_at:]

    # ---- validators ----
    def clean_term_months(self):
        v = self.cleaned_data.get("term_months") or 0
        try:
            v = int(v)
        except Exception:
            v = 0
        if v < 1 or v > 12:
            raise forms.ValidationError("Layby Term must be between 1 and 12 months.")
        return v

    def clean(self):
        cleaned = super().clean()

        selected = cleaned.get("product") or ""
        sku, name, price = _unpack_value(selected)
        if name:
            cleaned["item_name"] = name
        if sku:
            cleaned["sku"] = sku
        if price and (cleaned.get("total_price") in (None, "", 0, Decimal("0"))):
            cleaned["total_price"] = price

        total = cleaned.get("total_price") or Decimal("0")
        dep = cleaned.get("deposit_amount") or Decimal("0")
        try:
            if dep > total:
                self.add_error("deposit_amount", "Deposit cannot exceed total price.")
        except Exception:
            pass
        return cleaned

    # ---- utilities for save() ----
    @staticmethod
    def _agent_field_name() -> Optional[str]:
        names = {f.name for f in LaybyOrder._meta.get_fields()}
        if "agent" in names:
            return "agent"
        if "created_by" in names:
            return "created_by"
        return None

    @staticmethod
    def _make_ref() -> str:
        # AH + 4 digits; retry a few times for uniqueness
        for _ in range(10):
            ref = f"AH{randint(0, 9999):04d}"
            if not LaybyOrder.objects.filter(ref=ref).exists():
                return ref
        return "AH" + timezone.now().strftime("%H%M")

    def save(self, user=None, commit=True):
        inst: LaybyOrder = super().save(commit=False)

        if not getattr(inst, "ref", None):
            inst.ref = self._make_ref()

        if user is not None:
            f = self._agent_field_name()
            if f and not getattr(inst, f, None):
                setattr(inst, f, user)

        if commit:
            inst.save()

            # If optional fields exist on the model, assign from cleaned_data (already handled by ModelForm)
            # No extra work needed here because ModelForm took care of model-bound fields.

        return inst

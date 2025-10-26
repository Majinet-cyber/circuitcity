# onboarding/forms.py
from __future__ import annotations
from django import forms
from django.apps import apps

# Business form
Business = apps.get_model("tenants", "Business")

class BusinessForm(forms.ModelForm):
    class Meta:
        model = Business
        fields = ["name"]  # keep minimal/safe
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Your business name"})
        }

def make_inventory_item_form():
    """
    Create a dynamic ModelForm for inventory.InventoryItem with safe, common fields.
    """
    Model = apps.get_model("inventory", "InventoryItem")
    if not Model:
        return None
    wanted = ["name", "sku", "imei", "sale_price", "cost_price", "quantity", "location"]
    have = {f.name for f in Model._meta.get_fields()}
    fields = [f for f in wanted if f in have] or [next(iter(have - {"id"}))]  # at least 1 editable field

    Meta = type("Meta", (), {"model": Model, "fields": fields})
    Form = type("InventoryItemForm", (forms.ModelForm,), {"Meta": Meta})
    # add basic bootstrap widgets
    for f in fields:
        try:
            Form.base_fields[f].widget.attrs.update({"class": "form-control"})
        except Exception:
            pass
    return Form



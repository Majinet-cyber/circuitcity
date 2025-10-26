# inventory/views_products_v2.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Exists, OuterRef
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect
from .models import Product, InventoryItem

@login_required
def product_delete_v2(request, pk: int):
    """
    Hard-delete a Product only if it has no InventoryItem rows.
    If related rows exist (or ON DELETE is protected), show a friendly error.
    """
    if request.method != "POST":
        messages.error(request, "Use the Delete button (POST).")
        return redirect("inventory:merch_product_new")

    obj = get_object_or_404(Product, pk=pk)

    # Block deletes if any inventory rows reference this product
    if InventoryItem.objects.filter(product=obj).exists():
        messages.error(
            request,
            "Can't delete this product: it has stock or sales history."
        )
        return redirect("inventory:merch_product_new")

    try:
        obj.delete()
        messages.success(request, "Product deleted.")
    except ProtectedError:
        messages.error(
            request,
            "Can't delete this product because other records depend on it."
        )

    return redirect("inventory:merch_product_new")



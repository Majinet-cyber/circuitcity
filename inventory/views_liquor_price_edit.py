# inventory/views_liquor_price_edit.py
"""
Price edit functionality for liquor products (manager-only).
"""
from __future__ import annotations

from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods

from core.decorators import manager_required
from tenants.decorators import require_business_access as require_business
from tenants.middleware import get_active_business
from inventory.models import MerchProduct
from inventory.business_kinds import BusinessKind


@login_required
@manager_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
@require_http_methods(["GET", "POST"])
def edit_liquor_price(request: HttpRequest, product_id: int) -> HttpResponse:
    """
    Edit prices for a liquor product (manager-only).

    Allows editing:
    - price_per_bottle
    - price_per_shot
    - price_per_glass
    - cost_per_bottle
    - cost_per_shot
    - cost_per_glass
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("liquor:sell")

    product = get_object_or_404(MerchProduct, pk=product_id, business=business, kind=BusinessKind.LIQUOR)

    if request.method == "POST":
        try:
            with transaction.atomic():
                # Update bottle prices
                if "price_per_bottle" in request.POST:
                    price = request.POST.get("price_per_bottle", "").strip()
                    if price:
                        product.price_per_bottle = Decimal(price)

                if "cost_per_bottle" in request.POST:
                    cost = request.POST.get("cost_per_bottle", "").strip()
                    if cost:
                        product.cost_per_bottle = Decimal(cost)

                # Update shot prices
                if "price_per_shot" in request.POST:
                    price = request.POST.get("price_per_shot", "").strip()
                    if price:
                        product.price_per_shot = Decimal(price)

                if "cost_per_shot" in request.POST:
                    cost = request.POST.get("cost_per_shot", "").strip()
                    if cost:
                        product.cost_per_shot = Decimal(cost)

                # Update glass prices
                if "price_per_glass" in request.POST:
                    price = request.POST.get("price_per_glass", "").strip()
                    if price:
                        product.price_per_glass = Decimal(price)

                if "cost_per_glass" in request.POST:
                    cost = request.POST.get("cost_per_glass", "").strip()
                    if cost:
                        product.cost_per_glass = Decimal(cost)

                product.save()

            messages.success(request, f"✅ Prices updated for {product.name}")
            return redirect("liquor:sell")

        except Exception as e:
            messages.error(request, f"❌ Error updating prices: {str(e)}")
            return redirect("liquor:edit_price", product_id=product_id)

    # GET: Show edit form
    context = {
        "product": product,
        "business": business,
        "page_title": f"Edit Prices - {product.name}",
    }

    return render(request, "inventory/liquor/edit_price.html", context)


@login_required
@manager_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
@require_http_methods(["POST"])
def api_edit_liquor_price(request: HttpRequest, product_id: int) -> JsonResponse:
    """
    API endpoint for quick price edits (AJAX).
    """
    business = get_active_business(request)
    if not business:
        return JsonResponse({"error": "No active business"}, status=400)

    product = get_object_or_404(MerchProduct, pk=product_id, business=business, kind=BusinessKind.LIQUOR)

    try:
        import json

        if request.content_type and "json" in request.content_type.lower():
            data = json.loads(request.body.decode("utf-8"))
        else:
            data = request.POST.dict()

        with transaction.atomic():
            updated_fields = []

            # Update prices based on provided data
            for field in [
                "price_per_bottle",
                "price_per_shot",
                "price_per_glass",
                "cost_per_bottle",
                "cost_per_shot",
                "cost_per_glass",
            ]:
                if field in data:
                    value = data[field]
                    if value is not None and value != "":
                        try:
                            setattr(product, field, Decimal(str(value)))
                            updated_fields.append(field)
                        except Exception:
                            pass

            if updated_fields:
                product.save(update_fields=updated_fields)
                return JsonResponse(
                    {
                        "success": True,
                        "message": f"Updated {len(updated_fields)} price(s)",
                        "product": {
                            "id": product.id,
                            "name": product.name,
                            "price_per_bottle": str(product.price_per_bottle) if product.price_per_bottle else None,
                            "price_per_shot": str(product.price_per_shot) if product.price_per_shot else None,
                            "price_per_glass": str(product.price_per_glass) if product.price_per_glass else None,
                        },
                    }
                )
            else:
                return JsonResponse({"error": "No valid prices provided"}, status=400)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

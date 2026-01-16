# inventory/verticals/farm_assets.py
"""
Farm Assets view for tracking farm equipment, tools, and infrastructure.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.models_farm import FarmAsset, FarmAssetCondition
from tenants.utils import require_business
from inventory.verticals import base


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
@require_http_methods(["GET", "POST"])
def assets_landing(request: HttpRequest) -> HttpResponse:
    """
    Farm Assets landing page with quick-add form.
    Handles both display and POST submission for adding assets.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    if request.method == "POST":
        # Process asset creation
        try:
            asset_type = request.POST.get("asset_type", "").strip()
            asset_name = request.POST.get("asset_name", "").strip()
            quantity = int(request.POST.get("quantity", 1) or 1)
            
            # Parse value (optional)
            value_str = request.POST.get("value", "").strip()
            value_mwk = None
            if value_str:
                try:
                    value_mwk = Decimal(value_str)
                except (InvalidOperation, ValueError):
                    pass
            
            # Parse purchase date (optional)
            purchase_date = request.POST.get("purchase_date") or None
            
            condition = request.POST.get("condition", FarmAssetCondition.GOOD)
            notes = request.POST.get("notes", "").strip()
            
            if not asset_name:
                messages.error(request, "Asset name is required.")
            else:
                # Create the asset
                asset = FarmAsset.objects.create(
                    business=business,
                    asset_type=asset_type or "other",
                    name=asset_name,
                    quantity=quantity,
                    value_mwk=value_mwk,
                    purchase_date=purchase_date,
                    condition=condition,
                    notes=notes,
                    created_by=request.user,
                )
                messages.success(
                    request,
                    f"✅ Asset '{asset.name}' added successfully! (Qty: {asset.quantity})"
                )
                return redirect("verticals:farm_assets")
        
        except Exception as e:
            messages.error(request, f"Error adding asset: {e}")
    
    # Get existing assets for display
    assets = FarmAsset.objects.filter(business=business, is_active=True).order_by("-created_at")
    
    # Group assets by type for summary
    asset_summary = {}
    for asset in assets:
        if asset.asset_type not in asset_summary:
            asset_summary[asset.asset_type] = {"count": 0, "total_value": Decimal("0")}
        asset_summary[asset.asset_type]["count"] += asset.quantity
        if asset.value_mwk:
            asset_summary[asset.asset_type]["total_value"] += asset.value_mwk * asset.quantity
    
    ctx.update({
        "active_tab": "assets",
        "hero_title": "Farm Assets",
        "hero_blurb": "Track your farm equipment, tools, and infrastructure",
        "assets": assets,
        "asset_summary": asset_summary,
        "total_assets": sum(a.quantity for a in assets),
        "total_value": sum((a.value_mwk or Decimal("0")) * a.quantity for a in assets),
    })
    
    return render(request, "verticals/farm/assets_landing.html", ctx)

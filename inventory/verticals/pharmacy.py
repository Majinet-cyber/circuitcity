from __future__ import annotations

from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render

from tenants.models import Business
from tenants.utils import require_business

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind

# Use the comprehensive pharmacy dashboard from views_pharmacy
from inventory.views_pharmacy import pharmacy_dashboard
from inventory.models_pharmacy import PharmacyBatch


@login_required
@require_business
@require_business_kind(BusinessKind.PHARMACY)
def dashboard(request):
    """Pharmacy dashboard - delegates to views_pharmacy.pharmacy_dashboard"""
    return pharmacy_dashboard(request)


@login_required
@require_business
@require_business_kind(BusinessKind.PHARMACY)
def hub(request):
    """
    Pharmacy & Cosmetics Hub - Navigation center for the pharmacy vertical.
    Shows tiles/cards for accessing key features: dashboard, stock-in, sell, batches, etc.
    """
    business: Business = request.business
    
    # Get basic counts for display
    batches = PharmacyBatch.objects.filter(
        business=business,
        is_archived=False
    ).select_related("merch_product")
    
    total_batches = batches.count()
    total_stock_value = sum(b.stock_value_selling for b in batches)
    
    # Products count
    from inventory.models import MerchProduct
    products_count = MerchProduct.objects.filter(
        business=business,
        kind="pharmacy",
        is_active=True
    ).count()
    
    ctx = {
        "total_batches": total_batches,
        "total_stock_value": total_stock_value,
        "products_count": products_count,
    }
    
    return render(request, "verticals/pharmacy/hub.html", ctx)


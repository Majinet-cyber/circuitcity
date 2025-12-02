from __future__ import annotations

from django.contrib.auth.decorators import login_required

from tenants.utils import require_business

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind

# Use the comprehensive pharmacy dashboard from views_pharmacy
from inventory.views_pharmacy import pharmacy_dashboard


@login_required
@require_business
@require_business_kind(BusinessKind.PHARMACY)
def dashboard(request):
    """Pharmacy dashboard - delegates to views_pharmacy.pharmacy_dashboard"""
    return pharmacy_dashboard(request)


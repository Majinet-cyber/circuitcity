# circuitcity/inventory/views_sell.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

# --- Try to import a Location model (keep app import-safe) --------------------
# Adjust the import order if your Location model lives elsewhere.
try:
    from sales.models import Location  # common placement
except Exception:  # pragma: no cover
    try:
        from inventory.models import Location  # fallback if you keep it here
    except Exception:  # pragma: no cover
        Location = None  # type: ignore


@dataclass(frozen=True)
class UILocation:
    id: int
    name: str


def _get_locations_for_ui(request: HttpRequest) -> List[UILocation]:
    """
    Return a light list of locations for the dropdown.
    If there is no Location model, return an empty list (UI should handle it).
    """
    if Location is None:
        return []

    qs = Location.objects.all()

    # If you scope locations by business/tenant, add your filters here, e.g.:
    # biz = getattr(request, "biz", None)
    # if biz is not None and hasattr(Location, "business"):
    #     qs = qs.filter(business=biz)

    qs = qs.order_by("name")
    return [UILocation(id=loc.id, name=str(loc)) for loc in qs]


def _pick_default_location(locs: List[UILocation]) -> Optional[int]:
    """
    Choose a sensible default location id for the form.
    Currently: first in list, or None if no locations exist.
    """
    return locs[0].id if locs else None


@login_required
@require_GET
def sell_quick_page(request: HttpRequest) -> HttpResponse:
    """
    A minimal Sell page that posts directly to /inventory/api/mark-sold/
    and trusts the API response (no follow-up stock-status probe).

    Context provided to the template:
      - locations: [{id, name}, ...]
      - location_default: int | None
    """
    locations = _get_locations_for_ui(request)
    context = {
        "locations": locations,
        "location_default": _pick_default_location(locations),
    }
    return render(request, "inventory/sell_quick.html", context)

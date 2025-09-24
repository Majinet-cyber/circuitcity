from django.utils import timezone
from typing import Tuple, Dict
from .scope import active_scope
from .models import Business, Location  # adjust if your names differ

def resolve_active_context(request) -> Tuple[Dict, Dict]:
    biz_id, loc_id = active_scope(request)

    biz = Business.objects.filter(id=biz_id).first() if biz_id else None
    loc = Location.objects.filter(id=loc_id).first() if loc_id else None

    # Stamp onto request so templates/other views can reuse
    request.business = biz
    request.business_id = getattr(biz, "id", None)
    request.active_location = loc
    request.active_location_id = getattr(loc, "id", None)

    locations = []
    if biz:
        locations = list(
            Location.objects.filter(business=biz).values("id", "name")
        )

    today = timezone.now().date().isoformat()

    boot = {
        "ok": True,
        "data": {
            "note": "ready",
            "sold_date_default": today,
            "commission_default": 0.0,
            "location_default": getattr(loc, "id", None),
            "auto_submit_default": False,
            "locations": locations,
        },
    }
    ctx = {
        "business": biz,
        "active_location": loc,
        "locations": locations,
        "today": today,
        "commission_default": 0.0,
        "auto_submit_default": False,
    }
    return boot, ctx

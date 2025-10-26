from __future__ import annotations

from django.utils import timezone

def _get_business_from_request(request):
    """
    Best-effort way to find the active business for this request.
    - Prefer request.business (set by your tenants middleware/context processor)
    - Fallback to the first active membership for the logged-in user
    """
    biz = getattr(request, "business", None)
    if biz:
        return biz

    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return None

    try:
        from tenants.models import Membership  # local import to avoid circulars at startup
        mem = (
            Membership.objects.filter(user=user, is_active=True)
            .select_related("business")
            .order_by("created_at")
            .first()
        )
        return mem.business if mem else None
    except Exception:
        return None


def trial_banner(request):
    """
    Provides trial information for templates. Safe no-op if there is no business or subscription.
    Context keys returned:
      - trial_banner: {
            "show": bool,               # whether to show a trial banner
            "status": str,              # subscription status
            "days_left": int,           # days remaining in trial (0 if not trial)
            "trial_end": datetime|None, # when the trial ends
            "is_active_now": bool,      # allowed to use app (trial/grace/active)
        }
      - subscription: the subscription object (when available), for templates that need it
    """
    ctx = {}
    try:
        biz = _get_business_from_request(request)
        if not biz:
            return ctx

        sub = getattr(biz, "subscription", None)
        if not sub:
            return ctx

        # Safely compute days left (method exists in our model)
        try:
            days_left = sub.days_left_in_trial()
        except Exception:
            days_left = 0

        show = getattr(sub, "is_trial", False) or (getattr(sub, "status", "").lower() == "trial" and days_left > 0)

        ctx["trial_banner"] = {
            "show": bool(show),
            "status": getattr(sub, "status", ""),
            "days_left": int(days_left or 0),
            "trial_end": getattr(sub, "trial_end", None),
            "is_active_now": bool(getattr(sub, "is_active_now", lambda: False)()),
        }
        ctx["subscription"] = sub
    except Exception:
        # Never let context processors break page rendering
        pass

    return ctx



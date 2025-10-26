# tenants/middleware_autoselect.py
from __future__ import annotations

from django.utils.deprecation import MiddlewareMixin

class AutoSelectSingleBusinessMiddleware(MiddlewareMixin):
    """
    If the user is authenticated and has exactly one ACTIVE Membership,
    pre-load request.active_business and session['active_business_id'].

    This runs BEFORE any "require-active-business" middleware so we don't get
    redirected to /tenants/choose/ for no reason.
    """

    def process_request(self, request):
        try:
            user = getattr(request, "user", None)
            if not (user and user.is_authenticated):
                return  # nothing to do

            # If already set, leave it alone.
            if getattr(request, "active_business", None) or request.session.get("active_business_id"):
                return

            # We import lazily to avoid circulars at startup.
            from tenants.models import Membership

            qs = (
                Membership.objects
                .filter(user=user)
                .select_related("business")
            )

            # Be tolerant of different status fields â€” look for typical ones.
            fields = {f.name for f in Membership._meta.fields}
            for flag in ("is_active", "active", "accepted", "status"):
                if flag in fields:
                    try:
                        if flag == "status":
                            qs = qs.exclude(status__in=["REJECTED", "PENDING", "INACTIVE"])
                        else:
                            qs = qs.filter(**{flag: True})
                    except Exception:
                        pass

            count = qs.count()
            if count != 1:
                return

            m = qs.first()
            biz = getattr(m, "business", None)
            if not biz:
                return

            # Prime both request and session so downstream code is happy.
            request.active_business = biz
            request.active_business_id = getattr(biz, "id", None)
            request.session["active_business_id"] = getattr(biz, "id", None)
            request.session["biz_id"] = getattr(biz, "id", None)
        except Exception:
            # Never block requests if anything goes wrong.
            return



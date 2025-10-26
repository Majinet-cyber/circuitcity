# billing/views_admin.py
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone

from .models import BusinessSubscription

@login_required
@permission_required("billing.view_businesssubscription", raise_exception=True)
def hq_subscriptions(request):
    """
    Superusers (and staff with the view permission) see ALL subscriptions.
    Regular users see only their own business' subscription.
    """
    q = (request.GET.get("q") or "").strip()

    qs = BusinessSubscription.objects.select_related("business", "plan").order_by(
        "-started_at", "-created_at"
    )

    user = request.user
    if not user.is_superuser:
        # Try to scope to the userâ€™s business if present
        user_business = getattr(user, "business", None)
        if not user_business:
            profile = getattr(user, "profile", None)
            user_business = getattr(profile, "business", None) if profile else None
        if user_business:
            qs = qs.filter(business=user_business)
        else:
            qs = qs.none()

    if q:
        qs = qs.filter(
            Q(business__name__icontains=q)
            | Q(plan__name__icontains=q)
            | Q(plan__code__icontains=q)
            | Q(status__icontains=q)
        )

    context = {
        "subs": qs,
        "total": qs.count(),
        "now": timezone.now(),
        "query": q,
    }
    return render(request, "billing/hq_subscriptions.html", context)



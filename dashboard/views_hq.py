from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Prefetch
from django.shortcuts import render

from billing.models import BusinessSubscription
from tenants.models import Business

@staff_member_required
def hq_subscriptions(request):
    q = (request.GET.get("q") or "").strip()
    subs = BusinessSubscription.objects.select_related("business", "plan").order_by("-created_at")
    if q:
        subs = subs.filter(business__name__icontains=q) | subs.filter(plan__name__icontains=q)  # simple OR

    return render(request, "hq/subscriptions.html", {"subs": subs, "q": q})



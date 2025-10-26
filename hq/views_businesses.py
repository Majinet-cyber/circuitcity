from django.db.models import Sum, Count, Q, F, DecimalField
from django.db.models.functions import Coalesce
from tenants.models import Business
from billing.models import Subscription, Invoice

def businesses(request):
    qs = Business.objects.order_by("name")
    q = request.GET.get("q")
    if q:
        qs = qs.filter(name__icontains=q)

    # annotate KPIs
    qs = qs.annotate(
        active_subs=Count("subscription", filter=Q(subscription__status="active")),
        invoices_total=Coalesce(Sum("invoice__amount", output_field=DecimalField()), 0),
        mrr_sum=Coalesce(Sum("subscription__plan__price_mwk",
                             filter=Q(subscription__status="active")), 0)
    )
    return render(request, "hq/businesses.html", {"businesses": qs})



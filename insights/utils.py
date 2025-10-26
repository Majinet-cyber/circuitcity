# insights/utils.py
from django.utils import timezone
from billing.models import Invoice
from sales.models import Sale  # your app; adjust

def kpi_insights_for(user):
    """Return a list of short strings."""
    biz = getattr(getattr(user, "profile", None), "active_business", None)
    if not biz: return []
    now = timezone.now()
    start_m = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start_prev = (start_m - timezone.timedelta(days=1)).replace(day=1)
    this_rev = Invoice.paid.filter(business=biz, paid_at__gte=start_m).sum_amount()
    prev_rev = Invoice.paid.filter(business=biz, paid_at__gte=start_prev, paid_at__lt=start_m).sum_amount()
    msgs = []
    if prev_rev and this_rev > prev_rev:
        msgs.append(f"Youâ€™re above last month already. (+MWK {int(this_rev - prev_rev):,})")
    profit = getattr(Sale.objects.for_business(biz).month(now), "profit", 0)
    if profit and profit >= 4_000_000:
        msgs.append("Did you know? Youâ€™ve made MWK 4,000,000+ in profit this month ðŸŽ‰")
    return msgs[:2]



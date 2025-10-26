import datetime as dt
from django.utils.timezone import now
from inventory.models import StockLedger, Sku, Sale

def _predicted_stockouts(business_id, horizon_days=7):
    # naive: daily avg sales last 30 days vs current qty
    cutoff = now() - dt.timedelta(days=30)
    qs = (Sale.objects.filter(business_id=business_id, ts__gte=cutoff)
          .values('sku_id').annotate(sold=Sum('qty')))
    sold_map = {x['sku_id']: (x['sold']/30.0) for x in qs}
    alerts = []
    for sku in Sku.objects.filter(business_id=business_id):
        dly = sold_map.get(sku.id, 0.0)
        if dly <= 0: continue
        days_left = (sku.qty_on_hand or 0) / dly
        if days_left < horizon_days:
            alerts.append({
              "sev": "warning" if days_left>2 else "danger",
              "msg": f"{sku.name}: {days_left:.1f} days left Â· restock soon",
            })
    return alerts[:6]

def cfo_alerts(business_id):
    alerts = _predicted_stockouts(business_id)
    if not alerts:
        alerts = [{"sev":"ok","msg":"All good â€” no stockouts predicted."}]
    return alerts

def gamified_messages(business_id):
    today = now().date()
    best_day = (Sale.objects.filter(business_id=business_id)
               .values('ts__date').annotate(total=Sum('amount'))
               .order_by('-total').first())
    msgs = []
    if best_day:
        msgs.append({"title":"ðŸ”¥ Best Day Ever",
                     "text": f"You smashed {best_day['total']:,} MK on {best_day['ts__date']}!"})
    streak = (Sale.objects.filter(business_id=business_id, ts__date__gte=today-dt.timedelta(days=6))
              .values('ts__date').distinct().count())
    if streak >= 3:
        msgs.append({"title":"âš¡ Streak On", "text": f"{streak} selling days this week. Keep it going!"})
    if not msgs:
        msgs = [{"title":"OK", "text":"Youâ€™re on track. Aim for +10% this week."}]
    return msgs[:5]



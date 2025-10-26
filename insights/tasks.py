from celery import shared_task
from django.utils import timezone
from django.db.models import Count, Sum, F
from datetime import timedelta, date
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives

from inventory.models import Sale, Store, Product, Agent  # adjust paths
from .models import (DailyKPI, ForecastRun, ForecastItem,
                     InventoryPolicy, ReorderAdvice,
                     Notification, LeaderboardSnapshot, EmailReportLog, Badge, AgentBadge)
from .services import (ema_with_weekday, percentile_bounds, current_on_hand, week_start)

@shared_task
def forecast_daily():
    run = ForecastRun.objects.create()
    # build series per (store, product) from DailyKPI (last 60â€“90 days)
    horizon = 14
    today = timezone.localdate()
    start_d = today - timedelta(days=60)
    pairs = DailyKPI.objects.filter(d__gte=start_d)\
            .values_list("store_id","product_id").distinct()

    for store_id, product_id in pairs:
        rows = list(DailyKPI.objects.filter(store_id=store_id, product_id=product_id, d__gte=start_d)
                    .order_by("d").values_list("d","units"))
        series_by_day = [ (d.weekday(), float(u)) for d,u in rows ]
        yhat_next = ema_with_weekday(series_by_day, alpha=0.30)
        units_only = [u for _,u in series_by_day]
        lo, hi = percentile_bounds(units_only, 0.2, 0.8)

        # save horizon (flat forecast for now)
        for i in range(1, horizon+1):
            the_date = today + timedelta(days=i)
            ForecastItem.objects.update_or_create(
                run=run, store_id=store_id, product_id=product_id, date=the_date,
                defaults={"yhat": yhat_next, "ylo": lo, "yhi": hi, "mape": None},
            )
        # compute reorder advice
        on_hand = current_on_hand(store_id, product_id)
        mu = max(0.1, yhat_next)
        # policy defaults
        lead = 7; z = 1.28
        rop = mu*lead + z*( (hi-lo)/2.0 )*(lead**0.5)
        recommend = max(0.0, mu*(lead+7) - on_hand)
        ReorderAdvice.objects.update_or_create(
            store_id=store_id, product_id=product_id,
            defaults={"reorder_point": round(rop), "recommend_qty": round(recommend)}
        )

@shared_task
def alerts_low_stock():
    today = timezone.localdate()
    for adv in ReorderAdvice.objects.select_related("product","store"):
        on_hand = current_on_hand(adv.store_id, adv.product_id)
        if on_hand < adv.reorder_point:
            title = f"Low stock: {adv.product.name}"
            body = f"On-hand {on_hand} < ROP {int(adv.reorder_point)}. Recommend order: {int(adv.recommend_qty)}."
            # send to store manager(s) â†’ adjust how you identify managers/users
            for user in adv.store.managers.all():  # if you have M2M managers
                Notification.objects.create(user=user, kind="low_stock", title=title, body=body, severity="warn")

@shared_task
def nudges_hourly():
    start = week_start(timezone.now())
    rows = (Sale.objects.filter(sold_at__date__gte=start)
            .values("agent_id","agent__name")
            .annotate(units=Count("id"),
                      revenue=Sum("sale_price"),
                      profit=Sum(F("sale_price")-F("cost_price")))
            .order_by("-units"))
    rows = [{"agent_id":r["agent_id"], "name":r["agent__name"], "units":r["units"],
             "revenue":float(r["revenue"] or 0), "profit":float(r["profit"] or 0)} for r in rows]

    if not rows: return
    top_units = rows[0]["units"]

    for r in rows:
        delta = max(0, top_units - r["units"])
        if 0 < delta <= 2:
            # notify that agent
            try:
                agent = Agent.objects.get(id=r["agent_id"])
                Notification.objects.create(
                    user=agent.user, kind="nudge", severity="info",
                    title="ðŸ† Almost there!", body=f"Youâ€™re {delta} phones away from #1 this week!"
                )
            except Agent.DoesNotExist:
                pass

@shared_task
def weekly_reports():
    # Example: one email per manager summarizing their stores
    from inventory.models import Manager  # adjust if different
    this_week_start = week_start(timezone.now())
    this_week_end = this_week_start + timedelta(days=6)
    for m in Manager.objects.all():
        ctx = build_weekly_ctx_for_manager(m, this_week_start, this_week_end)  # Youâ€™ll add this helper
        html = render_to_string("emails/weekly_report.html", ctx)
        text = f"Weekly summary for {m.name} ({this_week_start}â€“{this_week_end}). Open in Circuit City."
        msg = EmailMultiAlternatives(
            subject=f"Circuit City: Weekly report ({this_week_start}â€“{this_week_end})",
            body=text, from_email="no-reply@circuitcity", to=[m.email]
        )
        msg.attach_alternative(html, "text/html"); msg.send()
        EmailReportLog.objects.create(report_key=ctx["key"], sent_to=m.email, meta={"store_ids": ctx["store_ids"]})



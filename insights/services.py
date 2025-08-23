import pandas as pd
from django.db.models import Sum, F
from django.utils import timezone
from datetime import timedelta
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from .models import Forecast

# Adjust imports to your schema
from inventory.models import Sale, Product, Stock  # assume Stock keeps on-hand qty

def daily_sales_qs(product: Product|None=None):
    qs = Sale.objects.all()
    if product:
        qs = qs.filter(product=product)
    # created_at -> date, sum quantities + revenue
    agg = (qs.values("created_at__date")
             .annotate(units=Sum("quantity"), revenue=Sum("amount"))
             .order_by("created_at__date"))
    df = pd.DataFrame(list(agg))
    if df.empty:
        return pd.DataFrame(columns=["date","units","revenue"])
    df.rename(columns={"created_at__date":"date"}, inplace=True)
    return df

def forecast_product(product: Product|None, horizon_days=7):
    df = daily_sales_qs(product)
    if df.empty:
        return []

    # ensure daily continuity
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").asfreq("D").fillna(0)

    # Exponential Smoothing (additive seasonality weekly if enough data)
    seasonal = "add" if len(df)>=21 else None
    model = ExponentialSmoothing(df["units"], trend="add", seasonal=seasonal, seasonal_periods=7 if seasonal else None)
    fit = model.fit(optimized=True)
    future = fit.forecast(horizon_days)
    results = []
    for i, (d, units) in enumerate(future.items()):
        units = max(0, round(float(units)))
        revenue = 0
        if product and hasattr(product, "selling_price") and product.selling_price:
            revenue = units * float(product.selling_price)
        results.append({"date": d.date(), "predicted_units": units, "predicted_revenue": revenue})
    return results

def compute_and_store_all(horizon_days=7):
    # overall (None) plus per product (limit to top 50 recent movers for speed)
    top_ids = (Sale.objects.values("product_id")
               .annotate(u=Sum("quantity")).order_by("-u")[:50]
              )
    product_ids = [r["product_id"] for r in top_ids if r["product_id"]]
    products = list(Product.objects.filter(id__in=product_ids))
    products.append(None)  # overall

    all_rows = 0
    for prod in products:
        rows = forecast_product(prod, horizon_days=horizon_days)
        for r in rows:
            Forecast.objects.update_or_create(
                product=prod, date=r["date"],
                defaults={"predicted_units": r["predicted_units"],
                          "predicted_revenue": r["predicted_revenue"]})
            all_rows += 1
    return all_rows

def stockout_and_restock(product: Product, horizon_days=7, lead_days=3):
    """Compute naive stockout and restock qty from forecast + current stock."""
    try:
        stock = Stock.objects.get(product=product)  # adjust to your schema
        on_hand = int(stock.quantity_on_hand)
    except Stock.DoesNotExist:
        on_hand = 0

    fut = list(Forecast.objects.filter(product=product, date__gte=timezone.now().date(),
                                       date__lte=timezone.now().date()+timedelta(days=horizon_days))
                                 .order_by("date")
                                 .values("date","predicted_units"))
    remaining = on_hand
    stockout_date = None
    for row in fut:
        remaining -= int(row["predicted_units"])
        if remaining <= 0:
            stockout_date = row["date"]
            break

    # Suggested restock = coverage for horizon + safety 20%
    needed = max(0, -remaining)
    safety = int(0.2 * sum(r["predicted_units"] for r in fut))
    suggested = needed + safety

    # if lead time > 0 and we expect stockout before lead time, mark urgent
    urgent = stockout_date and stockout_date <= (timezone.now().date() + timedelta(days=lead_days))
    return {"on_hand": on_hand, "stockout_date": stockout_date, "suggested_restock": suggested, "urgent": urgent}

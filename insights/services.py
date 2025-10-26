import math
from datetime import timedelta, date
from typing import Optional, List, Tuple, Dict

import pandas as pd
from django.db.models import Sum, F, Value, DecimalField
from django.db.models.functions import TruncDate, Coalesce
from django.utils import timezone

# Optional: statsmodels (fallback to EMA if not installed / too little data)
try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing  # type: ignore
    _HAS_STATSMODELS = True
except Exception:  # pragma: no cover
    ExponentialSmoothing = None  # type: ignore
    _HAS_STATSMODELS = False

# Models
from .models import (
    Forecast,              # legacy/simple table (product, date, predicted_units, predicted_revenue)
    DailyKPI, ForecastRun, ForecastItem,
    ReorderAdvice,
)
# Adjust imports to your schema
from inventory.models import Sale, Product, Stock  # If names differ, keep string FKs in models and adjust here.


# ============================================================
# Field resolution helpers (robust across slightly different schemas)
# ============================================================

def _field_exists(model, field_name: str) -> bool:
    return any(f.name == field_name for f in model._meta.get_fields())

def _pick_field(model, candidates: List[str]) -> Optional[str]:
    for c in candidates:
        if _field_exists(model, c):
            return c
    return None

def _product_price(product: Optional[Product]) -> float:
    if not product:
        return 0.0
    for name in ["selling_price", "sale_price", "price", "unit_price"]:
        if hasattr(product, name) and getattr(product, name) is not None:
            try:
                return float(getattr(product, name))
            except Exception:
                pass
    return 0.0


# ============================================================
# Basic time helpers
# ============================================================

def week_start(dt) -> date:
    d = timezone.localdate() if hasattr(dt, "tzinfo") else date.today()
    # If dt is a datetime, prefer its date in local tz
    try:
        d = timezone.localdate(dt)
    except Exception:
        pass
    return (d - timedelta(days=d.weekday()))


# ============================================================
# Lightweight EMA utilities (fallback when statsmodels not used)
# ============================================================

def ema(series: List[float], alpha: float = 0.30) -> float:
    if not series:
        return 0.0
    f = float(series[0])
    for y in series[1:]:
        f = alpha * float(y) + (1.0 - alpha) * f
    return f

def ema_with_weekday(series_by_day: List[Tuple[int, float]], alpha: float = 0.30) -> float:
    """
    series_by_day: list of (dow, units). Returns forecast for next day.
    """
    if not series_by_day:
        return 0.0
    units_only = [float(u) for _, u in series_by_day]
    base = ema(units_only, alpha=alpha)
    # weekday multipliers
    sums = [1e-6] * 7
    cnts = [1e-6] * 7
    for dow, u in series_by_day:
        sums[dow] += float(u)
        cnts[dow] += 1.0
    avg = max(1e-6, sum(units_only) / max(1.0, len(units_only)))
    mult = [(sums[i] / cnts[i]) / avg for i in range(7)]
    next_dow = (date.today().weekday() + 1) % 7
    return base * mult[next_dow]

def percentile_bounds(series: List[float], lo=0.2, hi=0.8) -> Tuple[float, float]:
    if not series:
        return (0.0, 0.0)
    s = sorted(series)
    def pick(p):
        i = max(0, min(len(s) - 1, int(p * (len(s) - 1))))
        return float(s[i])
    return (pick(lo), pick(hi))


# ============================================================
# Data access helpers
# ============================================================

def _sale_date_field() -> str:
    return _pick_field(Sale, ["sold_at", "created_at", "timestamp", "date"]) or "created_at"

def _sale_qty_field() -> str:
    return _pick_field(Sale, ["quantity", "qty", "units", "count"]) or "quantity"

def _sale_amount_field() -> Optional[str]:
    return _pick_field(Sale, ["amount", "total_amount", "sale_price", "total", "price"])

def _stock_qty_field() -> str:
    return _pick_field(Stock, ["quantity_on_hand", "qty_on_hand", "on_hand", "quantity", "qty", "stock"]) or "quantity"

def _stock_store_field() -> Optional[str]:
    return _pick_field(Stock, ["store", "location", "branch"])


# ============================================================
# Public: Daily sales DataFrame (date, units, revenue)
# ============================================================

def daily_sales_qs(product: Optional[Product] = None) -> pd.DataFrame:
    """
    Returns a DataFrame with columns: date, units, revenue
    """
    dfield = _sale_date_field()
    qfield = _sale_qty_field()
    afield = _sale_amount_field()

    qs = Sale.objects.all()
    if product:
        qs = qs.filter(product=product)

    ann = {"d": TruncDate(dfield), "units": Sum(F(qfield))}
    if afield:
        ann["revenue"] = Coalesce(Sum(F(afield)), Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)))
    else:
        ann["revenue"] = Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))

    agg = (qs.annotate(**{"d": ann["d"]})
             .values("d")
             .annotate(units=ann["units"], revenue=ann["revenue"])
             .order_by("d"))

    df = pd.DataFrame(list(agg))
    if df.empty:
        return pd.DataFrame(columns=["date", "units", "revenue"])
    df.rename(columns={"d": "date"}, inplace=True)
    return df


# ============================================================
# Forecasting (per product) â€” statsmodels (if available) else EMA
# ============================================================

def _forecast_series(units_series: pd.Series, horizon_days: int) -> List[float]:
    # Use Holt-Winters if available and data sufficient; else EMA flat
    if _HAS_STATSMODELS and len(units_series) >= 7:
        seasonal = "add" if len(units_series) >= 21 else None
        model = ExponentialSmoothing(
            units_series,
            trend="add",
            seasonal=seasonal,
            seasonal_periods=(7 if seasonal else None),
        )
        fit = model.fit(optimized=True)
        future = fit.forecast(horizon_days)
        return [max(0.0, float(x)) for x in future.values.tolist()]
    # Fallback: constant EMA level
    level = ema([float(x) for x in units_series.tolist()], alpha=0.30)
    return [max(0.0, level)] * horizon_days


def forecast_product(product: Optional[Product], horizon_days: int = 7) -> List[Dict]:
    """
    Compute horizon forecast for a single product (or None for overall).
    Returns list of {date, predicted_units, predicted_revenue}
    """
    df = daily_sales_qs(product)
    if df.empty:
        return []

    # Ensure daily continuity
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").asfreq("D").fillna(0)

    units_forecast = _forecast_series(df["units"], horizon_days=horizon_days)
    start = (df.index.max() + pd.Timedelta(days=1)).date()
    price = _product_price(product)

    results = []
    for i in range(horizon_days):
        d = start + timedelta(days=i)
        units = int(round(units_forecast[i]))
        revenue = units * price
        results.append({"date": d, "predicted_units": units, "predicted_revenue": revenue})
    return results


def compute_and_store_all(horizon_days: int = 7, top_n: int = 50) -> int:
    """
    Legacy path: writes forecasts into the simple Forecast table.
    - Forecast per top-N products by recent quantity
    - Also writes an 'overall' (product=None) series
    """
    qfield = _sale_qty_field()
    top_ids_qs = (Sale.objects.values("product_id")
                  .annotate(u=Sum(F(qfield)))
                  .order_by("-u"))[:top_n]
    product_ids = [r["product_id"] for r in top_ids_qs if r["product_id"]]
    products = list(Product.objects.filter(id__in=product_ids))
    products.append(None)  # overall

    all_rows = 0
    for prod in products:
        rows = forecast_product(prod, horizon_days=horizon_days)
        for r in rows:
            Forecast.objects.update_or_create(
                product=prod, date=r["date"],
                defaults={
                    "predicted_units": r["predicted_units"],
                    "predicted_revenue": r["predicted_revenue"],
                },
            )
            all_rows += 1
    return all_rows


# ============================================================
# Stockout and restock suggestion (legacy/simple)
# ============================================================

def _on_hand_for_product(product: Product) -> int:
    qty_field = _stock_qty_field()
    # Sum across all stock rows for this product (handles multi-store schemas)
    agg = (Stock.objects.filter(product=product)
           .aggregate(q=Coalesce(Sum(F(qty_field)), Value(0))))
    try:
        return int(agg["q"] or 0)
    except Exception:
        return 0

def stockout_and_restock(product: Product, horizon_days: int = 7, lead_days: int = 3) -> Dict:
    """Compute naive stockout date and restock qty using Forecast + current stock."""
    on_hand = _on_hand_for_product(product)

    today = timezone.localdate()
    fut = list(
        Forecast.objects.filter(
            product=product, date__gte=today, date__lte=today + timedelta(days=horizon_days)
        )
        .order_by("date")
        .values("date", "predicted_units")
    )

    remaining = on_hand
    stockout_date = None
    for row in fut:
        remaining -= int(row["predicted_units"] or 0)
        if remaining <= 0:
            stockout_date = row["date"]
            break

    fut_sum = sum(int(r["predicted_units"] or 0) for r in fut)
    needed = max(0, -remaining)          # if negative remaining, we ran out within horizon
    safety = int(0.2 * fut_sum)          # 20% safety
    suggested = needed + safety

    urgent = bool(stockout_date and stockout_date <= (today + timedelta(days=lead_days)))
    return {
        "on_hand": on_hand,
        "stockout_date": stockout_date,
        "suggested_restock": int(suggested),
        "urgent": urgent,
    }


# ============================================================
# Premium path: generate ForecastRun/ForecastItem + ReorderAdvice
# ============================================================

def _series_by_day_from_dailykpi(store_id: int, product_id: int, days_back: int = 60) -> List[Tuple[int, float]]:
    start_d = timezone.localdate() - timedelta(days=days_back)
    rows = (DailyKPI.objects
            .filter(store_id=store_id, product_id=product_id, d__gte=start_d)
            .order_by("d")
            .values_list("d", "units"))
    return [(d.weekday(), float(u or 0.0)) for d, u in rows]

def _current_on_hand(store_id: int, product_id: int) -> int:
    qty_field = _stock_qty_field()
    store_field = _stock_store_field()
    qs = Stock.objects.filter(product_id=product_id)
    if store_field:
        qs = qs.filter(**{f"{store_field}_id": store_id})
    agg = qs.aggregate(q=Coalesce(Sum(F(qty_field)), Value(0)))
    try:
        return int(agg["q"] or 0)
    except Exception:
        return 0

def compute_premium_run(horizon_days: int = 14, days_back: int = 60, alpha: float = 0.30) -> Dict:
    """
    Premium path: writes into ForecastRun/ForecastItem and ReorderAdvice
    using EMA + weekday seasonality and simple inventory policy.
    """
    run = ForecastRun.objects.create(horizon_days=horizon_days, algo="ema_weekday")
    today = timezone.localdate()

    # Distinct (store, product) pairs that have DailyKPI in the window
    pairs = (DailyKPI.objects
             .filter(d__gte=today - timedelta(days=days_back))
             .values_list("store_id", "product_id")
             .distinct())

    n_items = 0
    n_advice = 0

    for store_id, product_id in pairs:
        series_by_day = _series_by_day_from_dailykpi(store_id, product_id, days_back=days_back)
        if not series_by_day:
            continue

        # Forecast level for "tomorrow"
        yhat_next = ema_with_weekday(series_by_day, alpha=alpha)
        units_only = [u for _, u in series_by_day]
        lo, hi = percentile_bounds(units_only, 0.2, 0.8)

        # Save flat horizon (simple baseline)
        for i in range(1, horizon_days + 1):
            the_date = today + timedelta(days=i)
            ForecastItem.objects.update_or_create(
                run=run, store_id=store_id, product_id=product_id, date=the_date,
                defaults={"yhat": float(yhat_next), "ylo": float(lo), "yhi": float(hi), "mape": None},
            )
            n_items += 1

        # Reorder advice (ROP = Î¼*L + z*Ïƒ*sqrt(L)), with Ïƒ â‰ˆ (hi-lo)/2
        on_hand = _current_on_hand(store_id, product_id)
        mu = max(0.1, float(yhat_next))
        lead = 7.0
        z = 1.28  # ~90% service level
        sigma = max(0.0, (hi - lo) / 2.0)
        rop = mu * lead + z * sigma * (lead ** 0.5)
        recommend = max(0.0, mu * (lead + 7.0) - on_hand)

        ReorderAdvice.objects.update_or_create(
            store_id=store_id,
            product_id=product_id,
            defaults={"reorder_point": round(rop), "recommend_qty": round(recommend)},
        )
        n_advice += 1

    return {"run_id": run.id, "items_saved": n_items, "advice_saved": n_advice}



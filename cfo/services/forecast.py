from datetime import date, timedelta
from decimal import Decimal
from django.db.models import Sum
from ..models import CashLedger, ForecastSnapshot

SAFETY_INFLOW = Decimal("0.90")
SAFETY_OUTFLOW = Decimal("1.10")

def moving_average(values, window=14):
    if not values: return Decimal("0")
    tail = values[-window:] if len(values) > window else values
    return sum(tail) / Decimal(len(tail))

def compute_forecast(horizon_days=30, opening_balance=Decimal("0")):
    today = date.today()
    start = today - timedelta(days=90)
    inflows = list(CashLedger.objects.filter(date__gte=start, entry_type="inflow").values_list("amount", flat=True))
    outflows = list(CashLedger.objects.filter(date__gte=start, entry_type="outflow").values_list("amount", flat=True))

    avg_in = moving_average(inflows)
    avg_out = moving_average(outflows)

    proj_in = (avg_in * Decimal(horizon_days)) * SAFETY_INFLOW
    proj_out = (avg_out * Decimal(horizon_days)) * SAFETY_OUTFLOW

    net = opening_balance + proj_in - proj_out
    daily_out = (avg_out * SAFETY_OUTFLOW) if avg_out else Decimal("0.01")
    runway_days = int((opening_balance / daily_out)) if daily_out > 0 else horizon_days

    snap = ForecastSnapshot.objects.create(
        as_of_date=today,
        horizon_days=horizon_days,
        opening_balance=opening_balance,
        projected_inflows=proj_in,
        projected_outflows=proj_out,
        projected_runway_days=max(runway_days, 0),
        method="moving_avg",
        params={"window_days": 14, "safety_in": str(SAFETY_INFLOW), "safety_out": str(SAFETY_OUTFLOW)}
    )
    return snap

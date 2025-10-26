from __future__ import annotations

from math import pow
from typing import Any, Dict, List, Tuple
import random
import statistics
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone

from .models import Scenario, SimulationRun


# ============================================================
# Core deterministic simulation (kept from your version)
# ============================================================
def _simulate(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extended deterministic simulator with simple P&L and cash flow.

    Assumptions (intentionally simple):
      - Demand baseline: 10 units/day, compounded by demand_growth_pct per day.
      - Price: base_price * (1 + price_change_pct at t0).
      - Elasticity: +1% price => -0.5% demand (constant elasticity).
      - Inventory: sell from stock; when stock <= reorder_point, place order (reorder_qty=50)
                   that arrives after lead_time_days.
      - P&L recognition on sell (revenue and COGS).
      - Cash timing:
          * Revenue collected after AR days.
          * Inventory purchases (based on arrivals) paid after AP days.
          * Opex and Tax paid same day (simplification).
    """
    name = payload.get("name", "Ad-hoc")

    # Demand / price knobs
    growth = float(payload.get("demand_growth_pct", 0.0)) / 100.0
    price_delta = float(payload.get("price_change_pct", 0.0)) / 100.0
    base_price = float(payload.get("base_price", 100.0))
    unit_cost = float(payload.get("unit_cost", 60.0))

    # Inventory policy
    lead = int(payload.get("lead_time_days", 7))
    rp = int(payload.get("reorder_point", 10))
    stock = int(payload.get("initial_stock", 50))
    horizon = int(payload.get("horizon_days", 30))

    # P&L & cashflow knobs
    op_ex_pct = float(payload.get("op_ex_pct_of_revenue", 10.0)) / 100.0
    tax_rate = float(payload.get("tax_rate_pct", 25.0)) / 100.0
    ar_days = int(payload.get("ar_days", 7))
    ap_days = int(payload.get("ap_days", 7))
    cash = float(payload.get("opening_cash", 0.0))

    # Derived
    base_demand = 10.0
    price = base_price * (1.0 + price_delta)
    demand_multiplier = 1.0 - (price_delta * 0.5)  # simple elasticity

    arrivals: Dict[int, int] = {}        # day -> qty arriving into stock
    payments_ap: Dict[int, float] = {}   # day -> cash out after AP
    receipts_ar: Dict[int, float] = {}   # day -> cash in after AR
    reorder_qty = 50

    # Cumulative P&L trackers
    revenue_cum = 0.0
    cogs_cum = 0.0
    opex_cum = 0.0
    op_profit_cum = 0.0
    tax_cum = 0.0
    gross_profit_cum = 0.0

    series = []
    stockouts = 0

    for day in range(1, horizon + 1):
        # Inventory arriving today
        arrive_qty = arrivals.get(day, 0)
        stock += arrive_qty

        # Demand
        demand_today = base_demand * pow(1.0 + growth, day - 1) * demand_multiplier
        demand_int = int(round(demand_today))

        # Sales
        sold = min(stock, demand_int)
        stock -= sold

        # P&L recognition
        revenue = sold * price
        cogs = sold * unit_cost
        gross_profit = revenue - cogs
        opex = op_ex_pct * revenue
        op_profit = gross_profit - opex
        tax = tax_rate * op_profit if op_profit > 0 else 0.0

        # Cash timing:
        if revenue > 0:
            collect_day = day + ar_days
            receipts_ar[collect_day] = receipts_ar.get(collect_day, 0.0) + revenue

        if arrive_qty > 0:
            pay_day = day + ap_days
            payments_ap[pay_day] = payments_ap.get(pay_day, 0.0) + (arrive_qty * unit_cost)

        cash_out_same_day = opex + tax

        # Reorder policy
        if stock <= rp:
            arrive_day = day + lead
            arrivals[arrive_day] = arrivals.get(arrive_day, 0) + reorder_qty

        if sold < demand_int:
            stockouts += 1

        # Apply today's scheduled cash flows
        cash_in_today = receipts_ar.get(day, 0.0)
        cash_out_ap_today = payments_ap.get(day, 0.0)
        cash += cash_in_today
        cash -= (cash_out_ap_today + cash_out_same_day)

        # Cumulate P&L
        revenue_cum += revenue
        cogs_cum += cogs
        opex_cum += opex
        op_profit_cum += op_profit
        tax_cum += tax
        gross_profit_cum += gross_profit

        series.append({
            "day": day,
            "demand": round(demand_today, 2),
            "sold": sold,
            "stock": stock,
            "revenue": round(revenue, 2),
            "cogs": round(cogs, 2),
            "gross_profit": round(gross_profit, 2),
            "opex": round(opex, 2),
            "op_profit": round(op_profit, 2),
            "tax": round(tax, 2),
            "cash_in": round(cash_in_today, 2),
            "cash_out": round(cash_out_ap_today + cash_out_same_day, 2),
            "cash_cum": round(cash, 2),
            "revenue_cum": round(revenue_cum, 2),
            "gross_profit_cum": round(gross_profit_cum, 2),
            "op_profit_cum": round(op_profit_cum, 2),
        })

    kpis = {
        "price": round(price, 2),
        "unit_cost": round(unit_cost, 2),
        "revenue_total": round(revenue_cum, 2),
        "cogs_total": round(cogs_cum, 2),
        "gross_profit_total": round(gross_profit_cum, 2),
        "opex_total": round(opex_cum, 2),
        "op_profit_total": round(op_profit_cum, 2),
        "tax_total": round(tax_cum, 2),
        "ending_cash": round(cash, 2),
        "stockouts_days": stockouts,
    }
    return {"name": name, "series": series, "kpis": kpis}


# ============================================================
# Persistence helpers (legacy-friendly)
# ============================================================
def _create_run(scenario: Scenario, result: Dict[str, Any]) -> SimulationRun:
    """Create a SimulationRun on either `results_json` or legacy `result_json`."""
    field_name = "results_json" if hasattr(SimulationRun, "results_json") else "result_json"
    return SimulationRun.objects.create(**{"scenario": scenario, field_name: result})


def _get_results_json(run: SimulationRun) -> Dict[str, Any]:
    """Read results payload from either `results_json` or legacy `result_json`."""
    return getattr(run, "results_json", None) or getattr(run, "result_json", {}) or {}


# ============================================================
# Lightweight AI Forecasting (no heavy deps)
# ============================================================
def _safe_daily_sales_history(days_back: int = 365) -> List[Tuple[int, float]]:
    """
    Try to pull daily sales quantities for the last N days from sales.Sale.
    Falls back to empty if the app/model isn't present.
    Returns a list of (day_index, quantity) where day_index starts at 0 for the earliest day.
    """
    try:
        from sales.models import Sale  # type: ignore
    except Exception:
        return []

    start = timezone.now().date() - timedelta(days=days_back)
    qs = (Sale.objects
          .filter(created_at__date__gte=start)
          .values_list("created_at__date", "quantity"))

    buckets: Dict[str, float] = {}
    for d, qty in qs:
        key = d.isoformat()
        buckets[key] = buckets.get(key, 0.0) + float(qty or 0)

    # Normalize into a continuous daily series
    out: List[Tuple[int, float]] = []
    day = start
    idx = 0
    while day <= timezone.now().date():
        key = day.isoformat()
        out.append((idx, buckets.get(key, 0.0)))
        idx += 1
        day += timedelta(days=1)
    return out


def _linear_trend_forecast(history: List[Tuple[int, float]], days: int) -> List[float]:
    """
    Very small linear regression (least squares) without numpy.
    history: [(t, y)], t = 0..N-1; returns next `days` predicted y (>= 0).
    """
    if len(history) < 7:
        # Not enough history, flat forecast from mean
        mean = statistics.fmean(y for _, y in history) if history else 0.0
        return [max(mean, 0.0)] * days

    xs = [t for t, _ in history]
    ys = [y for _, y in history]
    n = float(len(xs))
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = (sxy / sxx) if sxx else 0.0
    intercept = mean_y - slope * mean_x

    last_t = xs[-1] if xs else 0
    preds: List[float] = []
    for i in range(1, days + 1):
        t = last_t + i
        yhat = intercept + slope * t
        preds.append(max(yhat, 0.0))
    return preds


def _exp_smooth(series: List[float], alpha: float = 0.35) -> List[float]:
    """Single exponential smoothing for stabilization."""
    if not series:
        return []
    s: List[float] = [series[0]]
    for x in series[1:]:
        s.append(alpha * x + (1 - alpha) * s[-1])
    return s


def _ai_demand_forecast(days: int = 90) -> List[Dict[str, float]]:
    """
    Produce a simple yet robust demand forecast for the next N days:
      - Pulls up to 365 days of daily sales.
      - Uses linear trend + exponential smoothing.
      - Falls back to zeros if no history.
    Returns [{day: 1..N, predicted_sales: float}, ...]
    """
    hist = _safe_daily_sales_history(365)
    if not hist:
        return [{"day": i, "predicted_sales": 0.0} for i in range(1, days + 1)]

    trend = _linear_trend_forecast(hist, days)
    smoothed = _exp_smooth(trend, alpha=0.35)
    # smoothed may be shorter than days if trend is empty; guard:
    if not smoothed:
        smoothed = [0.0] * days

    return [{"day": i + 1, "predicted_sales": round(max(v, 0.0), 2)} for i, v in enumerate(smoothed[:days])]


# ============================================================
# Monte Carlo risk simulation (no numpy)
# ============================================================
def _monte_carlo(payload: Dict[str, Any], iterations: int = 500) -> Dict[str, Any]:
    """
    Randomize demand/price/cost around the provided payload to estimate profit distribution.
    Returns P10/P50/P90 of total operating profit over the horizon, plus a small sample distribution.
    """
    base_units_day = float(payload.get("baseline_units_day")) if "baseline_units_day" in payload else None
    if base_units_day is None:
        # Derive daily baseline from monthly units if available
        monthly_units = float(payload.get("baseline_monthly_units", 300.0))
        base_units_day = monthly_units / 30.0

    price = float(payload.get("base_price", 100.0)) * (1.0 + float(payload.get("price_change_pct", 0.0)) / 100.0)
    unit_cost = float(payload.get("unit_cost", 60.0))
    opex_pct = float(payload.get("op_ex_pct_of_revenue", 10.0)) / 100.0
    horizon_days = int(payload.get("horizon_days", 30))

    results: List[float] = []

    # Reasonable volatilities (tweakable)
    demand_sigma = 0.15  # 15% std dev
    price_sigma = 0.08   # 8%
    cost_sigma = 0.05    # 5%

    for _ in range(int(iterations)):
        total_revenue = 0.0
        total_cogs = 0.0
        total_opex = 0.0

        for _d in range(horizon_days):
            # Gaussian multiplicative shocks
            dm = random.gauss(1.0, demand_sigma)
            pm = random.gauss(1.0, price_sigma)
            cm = random.gauss(1.0, cost_sigma)

            sold = max(base_units_day * dm, 0.0)
            p = max(price * pm, 0.01)
            c = max(unit_cost * cm, 0.0)

            rev = sold * p
            cogs = sold * c
            opex = opex_pct * rev

            total_revenue += rev
            total_cogs += cogs
            total_opex += opex

        op_profit = total_revenue - total_cogs - total_opex
        results.append(op_profit)

    if not results:
        return {"p10": 0.0, "p50": 0.0, "p90": 0.0, "distribution_sample": []}

    results_sorted = sorted(results)
    def pct(p: float) -> float:
        k = max(min(int(round(p * (len(results_sorted) - 1))), len(results_sorted) - 1), 0)
        return round(results_sorted[k], 2)

    return {
        "p10": pct(0.10),
        "p50": pct(0.50),
        "p90": pct(0.90),
        "distribution_sample": [round(x, 2) for x in results_sorted[::max(1, len(results_sorted)//200)]],
    }


# ============================================================
# API views
# ============================================================
@require_POST
@login_required
def run_simulation(request: HttpRequest):
    """
    POST JSON to run a deterministic simulation.
    Allows optional scenario_id hydration; returns JSON result and (if scenario_id provided) persists a SimulationRun.
    """
    import json
    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    # If scenario_id is provided, hydrate with DB values unless overridden
    scenario = None
    base: Dict[str, Any] = {}
    scenario_id = body.get("scenario_id")
    if scenario_id:
        try:
            scenario = Scenario.objects.get(id=scenario_id, owner=request.user)
        except Scenario.DoesNotExist:
            return JsonResponse({"error": "Scenario not found."}, status=404)

        # Safe getattr wrapper
        def _attr(obj, name, default):
            try:
                return getattr(obj, name)
            except Exception:
                return default

        base = {
            "name": _attr(scenario, "name", "Scenario"),
            "demand_growth_pct": _attr(scenario, "demand_growth_pct", 0.0),
            "price_change_pct": _attr(scenario, "price_change_pct", 0.0),
            "base_price": _attr(scenario, "base_price", 100.0),
            "unit_cost": _attr(scenario, "unit_cost", 60.0),
            "lead_time_days": _attr(scenario, "lead_time_days", 7),
            "reorder_point": _attr(scenario, "reorder_point", 10),
            "initial_stock": _attr(scenario, "initial_stock", 50),
            "horizon_days": _attr(scenario, "horizon_days", 30),
            "op_ex_pct_of_revenue": _attr(scenario, "op_ex_pct_of_revenue", 10.0),
            "tax_rate_pct": _attr(scenario, "tax_rate_pct", 25.0),
            "ar_days": _attr(scenario, "ar_days", 7),
            "ap_days": _attr(scenario, "ap_days", 7),
            "opening_cash": _attr(scenario, "opening_cash", 0.0),
            # Derived convenience: make daily baseline explicit for Monte Carlo (optional)
            "baseline_units_day": (_attr(scenario, "baseline_monthly_units", 300.0) or 300.0) / 30.0,
            "baseline_monthly_units": _attr(scenario, "baseline_monthly_units", 300.0),
        }

    # Merge: request body overrides scenario/default values
    merged: Dict[str, Any] = {**base, **body}

    # Compute and (optionally) persist
    result = _simulate(merged)

    if scenario is not None:
        try:
            _create_run(scenario, result)
        except Exception:
            pass  # Do not block the response on persistence errors

    return JsonResponse(result, status=200)


@require_GET
@login_required
def list_runs(request: HttpRequest):
    """
    Return up to 50 most recent runs (latest first) for the current user.
    """
    qs = (
        SimulationRun.objects.select_related("scenario")
        .filter(scenario__owner=request.user)
        .order_by("-created_at")[:50]
    )
    data = [
        {
            "id": r.id,
            "scenario": r.scenario.name,
            "created_at": r.created_at.isoformat(),
            "kpis": (_get_results_json(r) or {}).get("kpis", {}),
        }
        for r in qs
    ]
    return JsonResponse(data, safe=False)


# ---------------- AI Forecast endpoint ----------------
@require_GET
@login_required
def ai_forecast_api(request: HttpRequest, pk: int):
    """
    Returns an AI-style demand forecast for the next horizon (days) of the scenario,
    plus the deterministic baseline for easy overlay on the frontend.
    """
    try:
        sc = Scenario.objects.get(id=pk, owner=request.user)
    except Scenario.DoesNotExist:
        return JsonResponse({"error": "Scenario not found."}, status=404)

    horizon_days = int(getattr(sc, "horizon_days", 30) or 30)

    # Deterministic baseline (re-using your engine with minimal inputs)
    baseline_payload = {
        "name": getattr(sc, "name", "Scenario"),
        "demand_growth_pct": float(getattr(sc, "demand_growth_pct", 0.0) or 0.0),
        "price_change_pct": float(getattr(sc, "price_change_pct", 0.0) or 0.0),
        "base_price": float(getattr(sc, "base_price", 100.0) or 100.0),
        "unit_cost": float(getattr(sc, "unit_cost", 60.0) or 60.0),
        "lead_time_days": int(getattr(sc, "lead_time_days", 7) or 7),
        "reorder_point": int(getattr(sc, "reorder_point", 10) or 10),
        "initial_stock": int(getattr(sc, "initial_stock", 50) or 50),
        "horizon_days": horizon_days,
        "op_ex_pct_of_revenue": float(getattr(sc, "op_ex_pct_of_revenue", 10.0) or 10.0),
        "tax_rate_pct": float(getattr(sc, "tax_rate_pct", 25.0) or 25.0),
        "ar_days": int(getattr(sc, "ar_days", 7) or 7),
        "ap_days": int(getattr(sc, "ap_days", 7) or 7),
        "opening_cash": float(getattr(sc, "opening_cash", 0.0) or 0.0),
    }
    baseline = _simulate(baseline_payload)

    # AI-style forecast (demand only; frontend can map to revenue via price)
    forecast = _ai_demand_forecast(days=horizon_days)

    return JsonResponse(
        {"ok": True, "scenario_id": sc.id, "baseline": baseline, "forecast": forecast},
        status=200,
    )


# ---------------- Monte Carlo endpoint ----------------
@require_POST
@login_required
def monte_carlo_api(request: HttpRequest):
    """
    POST JSON with scenario_id (optional) + knobs to compute risk bands:
      {
        "scenario_id": 123,            # optional: hydrate from DB
        "iterations": 800,             # optional, default 500
        ... any knobs like base_price, unit_cost, baseline_monthly_units ...
      }
    Responds with P10/P50/P90 of total operating profit for the horizon.
    """
    import json
    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    iterations = int(body.get("iterations", 500))
    base: Dict[str, Any] = {}

    scenario_id = body.get("scenario_id")
    if scenario_id:
        try:
            sc = Scenario.objects.get(id=scenario_id, owner=request.user)
        except Scenario.DoesNotExist:
            return JsonResponse({"error": "Scenario not found."}, status=404)

        def _attr(obj, name, default):
            try:
                return getattr(obj, name)
            except Exception:
                return default

        base = {
            "baseline_monthly_units": _attr(sc, "baseline_monthly_units", 300.0),
            "baseline_units_day": (_attr(sc, "baseline_monthly_units", 300.0) or 300.0) / 30.0,
            "base_price": _attr(sc, "base_price", 100.0),
            "price_change_pct": _attr(sc, "price_change_pct", 0.0),
            "unit_cost": _attr(sc, "unit_cost", 60.0),
            "op_ex_pct_of_revenue": _attr(sc, "op_ex_pct_of_revenue", 10.0),
            "horizon_days": _attr(sc, "horizon_days", 30),
        }

    merged = {**base, **body}
    bands = _monte_carlo(merged, iterations=max(100, min(iterations, 5000)))

    return JsonResponse({"ok": True, "bands": bands}, status=200)



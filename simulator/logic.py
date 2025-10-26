# simulator/logic.py
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from math import pow
from typing import Dict, Any, List


def _D(x) -> Decimal:
    """Safe Decimal ctor."""
    if isinstance(x, Decimal):
        return x
    try:
        return Decimal(str(x))
    except Exception:
        return Decimal(0)


def _q2(x: Decimal) -> Decimal:
    """Quantize to 2dp for stable currency math."""
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def run_deterministic(s: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic daily simulator compatible with the front-end templates.

    INPUT (dict):
      baseline_monthly_units (int/float)   -> baseline demand per month
      avg_unit_price (float)               -> price per unit
      variable_cost_pct (float, 0..100)    -> % of price that's variable cost
      monthly_fixed_costs (float)          -> fixed opex per month
      monthly_growth_pct (float, 0..100)   -> % demand growth per month
      months (int)                         -> months to simulate (1..60 recommended)

    OPTIONAL (for richer KPIs, gracefully defaults if missing):
      tax_rate_pct (float, 0..100)         -> tax % on positive operating profit
      opening_cash (float)                 -> initial cash

    OUTPUT (dict):
      {
        "series": [ { "day": int,
                      "sold": float,
                      "stock": float,  # placeholder (0.0) until inventory is modeled
                      "revenue_cum": float,
                      "gross_profit_cum": float,
                      "op_profit_cum": float,
                      "cash_cum": float } ... ],
        "kpis": {
            "price": float,
            "unit_cost": float,
            "revenue_total": float,
            "gross_profit_total": float,
            "op_profit_total": float,
            "tax_total": float,
            "ending_cash": float,
            "stockouts_days": int
        }
      }
    """
    # ---- Inputs & defaults ----
    months = int(s.get("months", 12))
    months = max(1, months)

    baseline_monthly_units = _D(s.get("baseline_monthly_units", 0))
    price = _D(s.get("avg_unit_price", 0))
    var_pct = _D(s.get("variable_cost_pct", 0)) / Decimal(100)
    monthly_fixed = _D(s.get("monthly_fixed_costs", 0))
    monthly_growth = _D(s.get("monthly_growth_pct", 0)) / Decimal(100)

    tax_rate = _D(s.get("tax_rate_pct", 0)) / Decimal(100)
    opening_cash = _D(s.get("opening_cash", 0))

    # Convert to daily figures (use 30-day months for simplicity)
    DAYS_PER_MONTH = Decimal(30)
    total_days = int(months * int(DAYS_PER_MONTH))

    daily_units0 = (baseline_monthly_units / DAYS_PER_MONTH)
    # Compound conversion: (1+gm)^(1/30) - 1
    if monthly_growth > 0:
        daily_growth = Decimal(pow(float(Decimal(1) + monthly_growth), 1.0 / float(DAYS_PER_MONTH))) - Decimal(1)
    else:
        daily_growth = Decimal(0)

    daily_fixed = (monthly_fixed / DAYS_PER_MONTH)

    unit_cost = _q2(price * var_pct)  # displayed KPI
    # running cumulatives
    cum_revenue = Decimal(0)
    cum_gp = Decimal(0)
    cum_op = Decimal(0)
    cum_tax = Decimal(0)
    cash = opening_cash

    series: List[Dict[str, Any]] = []
    stockouts_days = 0  # placeholder until inventory is modeled

    # ---- Sim loop (daily) ----
    for d in range(1, total_days + 1):
        # demand growth compounded daily
        # sold_d = daily_units0 * (1+daily_growth)^(d-1)
        if daily_growth:
            sold = daily_units0 * Decimal(pow(float(Decimal(1) + daily_growth), d - 1))
        else:
            sold = daily_units0

        sold = sold.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # P&L for the day
        revenue = _q2(sold * price)
        var_cost = _q2(sold * unit_cost)
        gp = _q2(revenue - var_cost)
        opex = _q2(daily_fixed)
        op_profit = _q2(gp - opex)

        # tax on positive operating profit only
        day_tax = _q2(op_profit * tax_rate) if op_profit > 0 and tax_rate > 0 else Decimal(0)
        net_cash_flow = _q2(op_profit - day_tax)

        # update cumulatives
        cum_revenue = _q2(cum_revenue + revenue)
        cum_gp = _q2(cum_gp + gp)
        cum_op = _q2(cum_op + op_profit)
        cum_tax = _q2(cum_tax + day_tax)
        cash = _q2(cash + net_cash_flow)

        # Placeholder 'stock' metric (0.0) to satisfy UI; inventory can be added later
        series.append({
            "day": d,
            "sold": float(sold),
            "stock": 0.0,
            "revenue_cum": float(cum_revenue),
            "gross_profit_cum": float(cum_gp),
            "op_profit_cum": float(cum_op),
            "cash_cum": float(cash),
        })

    # ---- KPIs (totals) ----
    kpis = {
        "price": float(price),
        "unit_cost": float(unit_cost),
        "revenue_total": float(cum_revenue),
        "gross_profit_total": float(cum_gp),
        "op_profit_total": float(cum_op),
        "tax_total": float(cum_tax),
        "ending_cash": float(cash),
        "stockouts_days": int(stockouts_days),
    }

    return {"series": series, "kpis": kpis}



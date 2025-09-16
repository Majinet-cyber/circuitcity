from decimal import Decimal

def run_deterministic(s: dict):
    """
    s is a dict with keys:
      baseline_monthly_units, avg_unit_price, variable_cost_pct, monthly_fixed_costs, monthly_growth_pct, months
    Returns dict containing arrays for charts and summary KPIs.
    """
    months = int(s["months"])
    units0 = Decimal(s["baseline_monthly_units"])
    price = Decimal(s["avg_unit_price"])
    var_pct = Decimal(s["variable_cost_pct"]) / Decimal(100)
    fixed = Decimal(s["monthly_fixed_costs"])
    growth = Decimal(s["monthly_growth_pct"]) / Decimal(100)

    labels, units, revenue, cogs, gross_profit, net_profit = [], [], [], [], [], []
    u = units0
    for m in range(1, months + 1):
        labels.append(f"M{m}")
        # update units with growth after month 1
        if m > 1:
            u = (u * (Decimal(1) + growth)).quantize(Decimal("1.00"))
        units.append(float(u))

        rev = (u * price)
        cost = (rev * var_pct)
        gp = (rev - cost)
        np = (gp - fixed)

        revenue.append(float(rev))
        cogs.append(float(cost + fixed))
        gross_profit.append(float(gp))
        net_profit.append(float(np))

    return {
        "labels": labels,
        "series": {
            "Units": units,
            "Revenue": revenue,
            "COGS+Fixed": cogs,
            "Gross Profit": gross_profit,
            "Net Profit": net_profit,
        },
        "summary": {
            "total_revenue": float(sum(revenue)),
            "total_net_profit": float(sum(net_profit)),
            "last_month_net_profit": float(net_profit[-1]),
            "breakeven_month": _breakeven_month(net_profit),
        },
    }

def _breakeven_month(net_profit):
    for i, v in enumerate(net_profit, start=1):
        if v >= 0:
            return i
    return None

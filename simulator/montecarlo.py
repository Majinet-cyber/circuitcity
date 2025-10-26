import numpy as np

def monte_carlo_simulation(payload, iterations=1000):
    """
    Run a Monte Carlo simulation based on baseline payload.
    Varies demand, price, and cost by random Gaussian noise.
    Returns percentile bands for revenue and stockouts.
    """
    base_units = payload["baseline_monthly_units"]
    avg_price = payload["avg_unit_price"]
    var_cost = payload["variable_cost_pct"]
    months = payload["months"]

    results = []
    for _ in range(iterations):
        # Random demand + price variations (~Â±15%)
        demand_mult = np.random.normal(1.0, 0.15)
        price_mult = np.random.normal(1.0, 0.1)
        variable_cost_mult = np.random.normal(1.0, 0.05)

        demand = base_units * demand_mult
        price = avg_price * price_mult
        cost = price * var_cost * variable_cost_mult

        revenue = demand * price * months
        profit = revenue - (cost * demand * months)

        results.append(profit)

    # Calculate confidence intervals
    return {
        "p10": round(np.percentile(results, 10), 2),
        "p50": round(np.percentile(results, 50), 2),
        "p90": round(np.percentile(results, 90), 2),
        "distribution": results[:200],  # sample for visualization
    }



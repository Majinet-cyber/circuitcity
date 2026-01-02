"""
Utility functions for the Business Simulator on the public home page.

This simulator is purely illustrative and does NOT interact with 
real business data, wallets, costs, or inventory models.
"""


def simulator_defaults():
    """
    Return default values for the Business Simulator.

    Returns:
        dict: Default values for customers, average_sale, and cost_pct
    """
    return {
        "customers": 100,
        "average_sale": 10000,  # MWK
        "cost_pct": 40,  # 40% of revenue
    }


def simulator_compute(customers, average_sale, cost_pct):
    """
    Compute revenue, costs, and profit for the Business Simulator.

    Formula:
        revenue = customers * average_sale
        costs = revenue * (cost_pct / 100.0)
        profit = revenue - costs

    Args:
        customers: Number of customers per month (int or float)
        average_sale: Average spend per customer in MWK (int or float)
        cost_pct: Costs as percentage of revenue (0-100)

    Returns:
        tuple: (revenue, costs, profit) as floats
    """
    revenue = float(customers) * float(average_sale)
    costs = revenue * (float(cost_pct) / 100.0)
    profit = revenue - costs

    return revenue, costs, profit

# hq/plans.py
"""
HQ plans - imports from centralized billing.pricing for consistency.
"""
from dataclasses import dataclass
from typing import Optional

# Import centralized pricing configuration
try:
    from billing.pricing import PLANS as BILLING_PLANS, TRIAL_DAYS
    
    @dataclass(frozen=True)
    class Plan:
        code: str
        label: str
        price_mwk: int
        max_agents: Optional[int]  # None = unlimited
    
    # Convert billing plans to HQ format
    PLANS = {
        code: Plan(
            code=plan.code,
            label=plan.name,
            price_mwk=int(plan.amount),
            max_agents=plan.max_agents if plan.max_agents != -1 else None
        )
        for code, plan in BILLING_PLANS.items()
    }
    
    TRIAL_DAYS_DEFAULT = TRIAL_DAYS
    
except ImportError:
    # Fallback for backward compatibility
    @dataclass(frozen=True)
    class Plan:
        code: str
        label: str
        price_mwk: int
        max_agents: Optional[int]  # None = unlimited

    PLANS = {
        "starter": Plan("starter", "Starter", 20000, 3),
        "growth":  Plan("growth",  "Growth",  60000, 15),
        "pro":     Plan("pro",     "Pro",     120000, None),
    }
    
    TRIAL_DAYS_DEFAULT = 30

def plan_for(code: str) -> Plan:
    return PLANS[code]



# hq/plans.py
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class Plan:
    code: str
    label: str
    price_mwk: int
    max_agents: Optional[int]  # None = unlimited

PLANS = {
    "starter": Plan("starter", "Starter", 20000, 0),     # 1 manager, 1 store; no agents
    "pro":     Plan("pro",     "Pro",     35000, 5),     # up to 5 agents
    "promax":  Plan("promax",  "Pro Max", 50000, None),  # unlimited
}

TRIAL_DAYS_DEFAULT = 30

def plan_for(code: str) -> Plan:
    return PLANS[code]



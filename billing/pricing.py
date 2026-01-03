"""
Billing pricing configuration - SINGLE SOURCE OF TRUTH

All plan prices and limits must be defined here and imported elsewhere.
This prevents pricing drift between homepage, checkout, and internal systems.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class PlanConfig:
    """Plan configuration with pricing and limits."""

    code: str
    name: str
    amount: Decimal  # Monthly price in MWK
    currency: str
    max_stores: int  # -1 for unlimited
    max_agents: int  # -1 for unlimited
    description: str
    features: list[str]


# ====================================================================
# PRODUCTION PRICING - SINGLE SOURCE OF TRUTH
# ====================================================================
PLANS = {
    "starter": PlanConfig(
        code="starter",
        name="Starter",
        amount=Decimal("20000.00"),
        currency="MWK",
        max_stores=1,
        max_agents=3,
        description="Perfect for small shops and solo entrepreneurs",
        features=[
            "Up to 500 stock items",
            "1 location",
            "3 agents / team members",
            "Basic inventory tracking",
            "Sales reports & analytics",
            "Mobile app access",
            "Email support",
        ],
    ),
    "growth": PlanConfig(
        code="growth",
        name="Growth",
        amount=Decimal("60000.00"),
        currency="MWK",
        max_stores=5,
        max_agents=15,
        description="For growing businesses with multiple locations",
        features=[
            "Up to 2,000 stock items",
            "Up to 5 locations",
            "15 agents / team members",
            "Advanced inventory tracking",
            "Sales, profit & agent reports",
            "Agent wallet & commission management",
            "Layby / installment payments",
            "Priority email support",
            "WhatsApp notifications",
        ],
    ),
    "pro": PlanConfig(
        code="pro",
        name="Pro",
        amount=Decimal("120000.00"),
        currency="MWK",
        max_stores=-1,  # Unlimited
        max_agents=-1,  # Unlimited
        description="For established businesses needing full control",
        features=[
            "Unlimited stock items",
            "Unlimited locations",
            "Unlimited agents",
            "All Growth features",
            "AI-powered insights & recommendations",
            "HQ Command Center dashboard",
            "Advanced analytics & forecasting",
            "Custom integrations",
            "Dedicated account manager",
            "24/7 priority support",
        ],
    ),
}

# Legacy alias for backward compatibility (dict-style access for HQ views)
# HQ views expect dict with keys like "starter", "pro", "promax"
# Each value is a dict with: code, name, amount, max_agents, max_stores
PLAN_CATALOG = {
    "starter": {
        "code": "starter",
        "name": "Starter",
        "amount": Decimal("20000.00"),
        "max_agents": 3,  # Up to 3 agents
        "max_stores": 1,  # 1 store
    },
    "growth": {
        "code": "growth",
        "name": "Growth",
        "amount": Decimal("60000.00"),
        "max_agents": 15,  # Up to 15 agents
        "max_stores": 5,  # Up to 5 stores
    },
    "pro": {
        "code": "pro",
        "name": "Pro",
        "amount": Decimal("120000.00"),
        "max_agents": None,  # Unlimited
        "max_stores": None,  # Unlimited
    },
}

# Trial configuration
TRIAL_DAYS = 30


def get_plan(code: str) -> Optional[PlanConfig]:
    """Get plan configuration by code."""
    return PLANS.get(code)


def get_all_plans() -> list[PlanConfig]:
    """Get all available plans in recommended order."""
    return [PLANS["starter"], PLANS["growth"], PLANS["pro"]]


def format_price(amount: Decimal, currency: str = "MWK") -> str:
    """Format price for display."""
    if currency == "MWK":
        return f"MWK {amount:,.0f}"
    return f"{currency} {amount:,.2f}"

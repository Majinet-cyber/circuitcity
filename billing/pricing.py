"""
Billing pricing configuration - SINGLE SOURCE OF TRUTH

All plan prices and limits must be defined here and imported elsewhere.
This prevents pricing drift between homepage, checkout, and internal systems.

Currency:
  Primary display: MWK (Malawian Kwacha)
  Secondary display: USD (approximate, for international reference)
  Exchange rate: USD_TO_MWK is a static approximation. Real rates vary.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

# ---------------------------------------------------------------------------
# Exchange rate configuration
# ---------------------------------------------------------------------------
# Static approximation. Update when Malawi Reserve Bank rate changes significantly.
# As of April 2026, 1 USD ≈ 1,730 MWK (mid-market estimate).
USD_TO_MWK = Decimal("1730")
USD_RATE_NOTE = "USD equivalent is approximate and may vary with exchange rate."


def mwk_to_usd(mwk_amount: Decimal) -> int:
    """Convert MWK to approximate USD, rounded to nearest dollar."""
    if not mwk_amount:
        return 0
    return int(round(mwk_amount / USD_TO_MWK))


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

    @property
    def amount_usd(self) -> int:
        """Approximate USD equivalent, rounded to nearest dollar."""
        return mwk_to_usd(self.amount)

    @property
    def amount_formatted(self) -> str:
        """MWK-formatted price, e.g. 'MWK 20,000'."""
        return f"MWK {self.amount:,.0f}"

    @property
    def amount_usd_formatted(self) -> str:
        """USD-formatted approximate price, e.g. '≈ USD 12'."""
        return f"≈ USD {self.amount_usd:,}"


# ====================================================================
# PRODUCTION PRICING - SINGLE SOURCE OF TRUTH
# ====================================================================
# NOTE: "records" = products/members/livestock/crops depending on vertical
#       "team seats" = staff members (trainers, assistants, attendants)
PLANS = {
    "starter": PlanConfig(
        code="starter",
        name="Starter",
        amount=Decimal("20000.00"),
        currency="MWK",
        max_stores=1,
        max_agents=3,
        description="Perfect for small businesses and solo entrepreneurs",
        features=[
            "Up to 500 records",
            "1 location",
            "3 team seats",
            "Basic inventory & records tracking",
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
            "Up to 2,000 records",
            "Up to 5 locations",
            "15 team seats",
            "Advanced tracking & smart prompts",
            "Sales, profit & team reports",
            "Wallet & commission management",
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
            "Unlimited records",
            "Unlimited locations",
            "Unlimited team seats",
            "All Growth features",
            "Smart recommendations & prompts",
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


def format_price_with_usd(amount: Decimal, currency: str = "MWK") -> dict:
    """
    Return a dict with both MWK and USD representations.

    Returns:
        {
            "mwk": "MWK 20,000",
            "usd": "≈ USD 12",
            "note": "USD equivalent is approximate...",
        }
    """
    return {
        "mwk": format_price(amount, currency),
        "usd": f"≈ USD {mwk_to_usd(amount):,}",
        "note": USD_RATE_NOTE,
    }

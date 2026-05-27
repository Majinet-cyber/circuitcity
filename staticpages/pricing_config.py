"""
Emajinet Pricing Configuration — Single Source of Truth.

Edit prices, features, and labels here. Templates and views read from this
module so you never have to hunt through HTML to update a price.
"""

# ---------------------------------------------------------------------------
# Currency display helper
# ---------------------------------------------------------------------------
CURRENCY = "MWK"


def fmt(amount):
    """Format an integer MWK amount as a human-readable string."""
    if amount is None:
        return "Custom"
    return f"{CURRENCY} {amount:,}"


# ---------------------------------------------------------------------------
# Pricing tiers
# ---------------------------------------------------------------------------
PRICING_TIERS = [
    {
        "id": "starter",
        "name": "Starter",
        "badge": None,
        "tagline": "For small businesses getting started.",
        "price_monthly": 20000,
        "price_display": fmt(20000),
        "price_usd": "12",
        "price_note": "per month",
        "cta_label": "Start 30-Day Trial",
        "cta_url": "/accounts/signup/?plan=starter",
        "highlight": False,
        "users": 3,
        "trial_days": 30,
        "features": [
            "Up to 3 team seats",
            "Up to 500 records",
            "1 location",
            "Basic inventory & records tracking",
            "Sales reports & analytics",
            "Mobile app access",
            "Email support",
            "30-day free trial",
        ],
        "missing": [
            "Multiple locations",
            "Marketplace listing",
            "Advanced analytics",
            "HQ Command Center",
        ],
        "icon": "bi-shop",
        "color": "#059669",
    },
    {
        "id": "growth",
        "name": "Growth",
        "badge": "Most Popular",
        "tagline": "For growing businesses with multiple locations.",
        "price_monthly": 60000,
        "price_display": fmt(60000),
        "price_usd": "37",
        "price_note": "per month",
        "cta_label": "Start 30-Day Trial",
        "cta_url": "/accounts/signup/?plan=growth",
        "highlight": True,
        "users": 15,
        "trial_days": 30,
        "features": [
            "15 team seats",
            "Up to 2,000 records",
            "Up to 5 locations",
            "Advanced tracking & smart prompts",
            "Sales, profit & team reports",
            "Wallet & commission management",
            "Layby / installment payments",
            "WhatsApp notifications",
            "Priority email support",
            "30-day free trial",
        ],
        "missing": [
            "Unlimited locations",
            "HQ Command Center",
            "Custom integrations",
        ],
        "icon": "bi-graph-up-arrow",
        "color": "#059669",
    },
    {
        "id": "pro",
        "name": "Pro",
        "badge": None,
        "tagline": "For established businesses needing full control.",
        "price_monthly": 120000,
        "price_display": fmt(120000),
        "price_usd": "73",
        "price_note": "per month",
        "cta_label": "Start 30-Day Trial",
        "cta_url": "/accounts/signup/?plan=pro",
        "highlight": False,
        "users": None,
        "trial_days": 30,
        "features": [
            "Unlimited team seats",
            "Unlimited records",
            "Unlimited locations",
            "All Growth features",
            "Smart recommendations & prompts",
            "HQ Command Center dashboard",
            "Advanced analytics & forecasting",
            "Custom integrations",
            "Dedicated account manager",
            "24/7 priority support",
            "30-day free trial",
        ],
        "missing": [],
        "icon": "bi-building",
        "color": "#1e40af",
    },
]

# ---------------------------------------------------------------------------
# Industry solution cards (used on landing page & vertical landing pages)
# ---------------------------------------------------------------------------
INDUSTRY_SOLUTIONS = [
    {
        "id": "retail",
        "name": "Emajinet Retail",
        "icon": "🛒",
        "pain": "You don't know which products are dead stock and which are making you money.",
        "solution": "See profit per item, track fast movers, get low-stock alerts before customers notice.",
        "verticals": ["grocery", "hardware", "cement"],
        "color": "#059669",
    },
    {
        "id": "pharmacy",
        "name": "Emajinet Pharmacy",
        "icon": "💊",
        "pain": "Expired medicines, wrong stock counts, and cash you can't trace.",
        "solution": "Expiry tracking, batch management, and daily cash reconciliation built in.",
        "verticals": ["pharmacy"],
        "color": "#0891b2",
    },
    {
        "id": "farm",
        "name": "Emajinet Farm",
        "icon": "🌾",
        "pain": "Season ends but you don't know if you made a profit or a loss.",
        "solution": "Track crop expenses, harvest yields, and season-level profitability automatically.",
        "verticals": ["farm"],
        "color": "#65a30d",
    },
    {
        "id": "gym",
        "name": "Emajinet Gym",
        "icon": "💪",
        "pain": "Members go months without paying. You only notice when cash is tight.",
        "solution": "Membership tracking, payment reminders, and check-in logs that keep you paid.",
        "verticals": ["gym"],
        "color": "#dc2626",
    },
    {
        "id": "solar",
        "name": "Emajinet Solar",
        "icon": "⚡",
        "pain": "You install systems but can't prove energy performance or predict maintenance.",
        "solution": "IoT-ready dashboards, energy economics, and maintenance scheduling.",
        "verticals": ["energy"],
        "color": "#d97706",
    },
    {
        "id": "fashion",
        "name": "Emajinet Fashion",
        "icon": "👔",
        "pain": "Stock comes in mixed sizes and colours. You sell blind and lose on markdowns.",
        "solution": "Variant-aware inventory (size + colour), reorder alerts, and margin tracking.",
        "verticals": ["clothing"],
        "color": "#7c3aed",
    },
    {
        "id": "bar_liquor",
        "name": "Emajinet Bar & Liquor",
        "icon": "🍺",
        "pain": "Bottles disappear, credit customers don't pay, and end-of-day doesn't balance.",
        "solution": "Per-bottle tracking, bar credit control, and shift reconciliation so nothing slips.",
        "verticals": ["liquor"],
        "color": "#b45309",
    },
    {
        "id": "manufacturing",
        "name": "Emajinet Manufacturing",
        "icon": "🏭",
        "pain": "You produce goods but can't see true production cost, waste levels, or profit per batch.",
        "solution": "Bill of materials costing, batch tracking, raw material consumption, and output profitability.",
        "verticals": ["manufacturing"],
        "color": "#475569",
    },
]

# ---------------------------------------------------------------------------
# WhatsApp benefit categories (used in landing page section)
# ---------------------------------------------------------------------------
WHATSAPP_BENEFITS = [
    {
        "icon": "bi-bar-chart-fill",
        "title": "Daily Sales Summary",
        "description": "Get your sales total, top products, and profit for the day — straight to WhatsApp every evening.",
    },
    {
        "icon": "bi-exclamation-triangle-fill",
        "title": "Low Stock Alerts",
        "description": "Know before you run out. Get notified the moment any item drops below its minimum level.",
    },
    {
        "icon": "bi-cart-check-fill",
        "title": "Order Alerts",
        "description": "Every new marketplace order triggers an instant WhatsApp notification so you never miss a sale.",
    },
    {
        "icon": "bi-clock-history",
        "title": "Payment Reminders",
        "description": "Automated WhatsApp follow-ups for overdue credit customers — no awkward chasing required.",
    },
    {
        "icon": "bi-file-earmark-text-fill",
        "title": "Quotation Sharing",
        "description": "Send professional PDF quotations and invoices directly from Emajinet to your customer's phone.",
    },
    {
        "icon": "bi-person-check-fill",
        "title": "Owner Reports",
        "description": "Weekly performance reports sent to the owner even when they're not at the shop.",
    },
]

# ---------------------------------------------------------------------------
# Placeholder testimonials (swap real customer data here later)
# ---------------------------------------------------------------------------
TESTIMONIALS = [
    {
        "id": 1,
        "name": "Grace Nyirenda",
        "business_type": "Grocery Store, Lilongwe",
        "quote": "Before Emajinet I was guessing my profit every month. Now I see it every morning on WhatsApp. I made better decisions in 3 months than in 3 years.",
        "avatar_initials": "GN",
        "avatar_color": "#059669",
        "video_url": None,
        "rating": 5,
    },
    {
        "id": 2,
        "name": "Joseph Banda",
        "business_type": "Pharmacy, Blantyre",
        "quote": "Stock was always a mess. Items expiring, others running out, cash missing. Emajinet sorted all three in the first week.",
        "avatar_initials": "JB",
        "avatar_color": "#0891b2",
        "video_url": None,
        "rating": 5,
    },
    {
        "id": 3,
        "name": "Chisomo Phiri",
        "business_type": "Gym Owner, Mzuzu",
        "quote": "My members used to dodge payments for months. The automatic WhatsApp reminders changed everything. Collections went up 40%.",
        "avatar_initials": "CP",
        "avatar_color": "#7c3aed",
        "video_url": None,
        "rating": 5,
    },
    {
        "id": 4,
        "name": "Mercy Kamanga",
        "business_type": "Clothing Store, Zomba",
        "quote": "Now I know exactly which sizes sell fastest and which are sitting. I stopped ordering the wrong things and my cash improved.",
        "avatar_initials": "MK",
        "avatar_color": "#dc2626",
        "video_url": None,
        "rating": 5,
    },
]

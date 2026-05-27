"""
Shared content structure for HQ Staff Onboarding Guide.
This ensures HTML and PDF versions stay in sync.
"""

HQ_ONBOARDING_CONTENT = [
    {
        "type": "title",
        "text": "HQ Staff Onboarding Guide",
    },
    {
        "type": "alert",
        "style": "danger",
        "icon": "shield-exclamation",
        "title": "HQ Staff Access",
        "text": "This guide is for HQ staff and platform administrators only. You have access to sensitive business data and system controls. Always handle this access with care and professionalism.",
    },
    {
        "type": "heading",
        "level": 2,
        "text": "What is the HQ Portal?",
    },
    {
        "type": "paragraph",
        "text": "The HQ portal provides superuser capabilities to manage the entire Emajinet platform. As HQ staff, you have visibility across all businesses, subscriptions, agents, and system-wide analytics.",
    },
    {
        "type": "heading",
        "level": 2,
        "text": "Getting Started",
    },
    {
        "type": "heading",
        "level": 3,
        "text": "1. Accessing HQ",
    },
    {
        "type": "list",
        "items": [
            "Log in with your HQ staff credentials",
            "Navigate to /hq/ or click HQ Admin in the main menu",
            "You'll see the HQ Dashboard with platform-wide metrics",
        ],
    },
    {
        "type": "alert",
        "style": "warning",
        "text": "Security Note: HQ access is restricted. Never share HQ credentials.",
    },
    {
        "type": "heading",
        "level": 3,
        "text": "2. HQ Dashboard Overview",
    },
    {
        "type": "paragraph",
        "text": "The HQ Dashboard shows:",
    },
    {
        "type": "list",
        "items": [
            "Total Businesses: All registered merchants",
            "Active Subscriptions: Paying customers",
            "Monthly Revenue: Platform subscription income",
            "Total Agents: All users across all businesses",
            "System Health: Performance and uptime metrics",
        ],
    },
    {
        "type": "heading",
        "level": 2,
        "text": "Core HQ Functions",
    },
    {
        "type": "heading",
        "level": 3,
        "text": "🏢 Business Management",
    },
    {
        "type": "paragraph",
        "text": "Purpose: Oversee all merchant accounts on the platform.",
    },
    {
        "type": "paragraph",
        "text": "View: /hq/businesses/",
    },
    {
        "type": "paragraph",
        "text": "Key Information:",
    },
    {
        "type": "list",
        "items": [
            "Business name and contact",
            "Business vertical (phones, pharmacy, liquor, etc.)",
            "Status (Pending, Active, Suspended)",
            "Subscription tier",
            "Contract status (signed/not signed)",
            "Created date and activity",
        ],
    },
    {
        "type": "paragraph",
        "text": "Actions:",
    },
    {
        "type": "list",
        "items": [
            "Approve New Businesses: Review and activate pending businesses",
            "View Business Details: Click on any business to see locations, team members, subscription history, sales and inventory summary, and audit logs",
            "Suspend Businesses: Temporarily disable access for non-payment or violations",
            "Manage Contracts: Upload signed merchant agreements",
        ],
    },
    {
        "type": "heading",
        "level": 3,
        "text": "📄 Merchant Contracts",
    },
    {
        "type": "paragraph",
        "text": "Purpose: Store and manage signed contracts with merchants.",
    },
    {
        "type": "paragraph",
        "text": "View: /hq/contracts/",
    },
    {
        "type": "paragraph",
        "text": "Workflow:",
    },
    {
        "type": "list",
        "items": [
            "Download Template: Go to Contracts → Template, download the standard merchant contract PDF",
            "Send to Merchant: Email the contract to the business owner, request signature",
            "Upload Signed Contract: Click on business name, upload the signed PDF file, add notes",
            "Track Status: Signed (green badge) or Not Signed (red badge)",
        ],
    },
    {
        "type": "heading",
        "level": 3,
        "text": "💳 Subscription Management",
    },
    {
        "type": "paragraph",
        "text": "Purpose: Manage platform subscriptions and billing.",
    },
    {
        "type": "paragraph",
        "text": "View: /hq/subscriptions/",
    },
    {
        "type": "paragraph",
        "text": "Subscription Tiers:",
    },
    {
        "type": "list",
        "items": [
            "Trial: 14-day free trial (new businesses)",
            "Starter: Basic features for small shops",
            "Professional: Advanced analytics and reporting",
            "Enterprise: Full platform access with priority support",
        ],
    },
    {
        "type": "heading",
        "level": 3,
        "text": "📊 Analytics & Reporting",
    },
    {
        "type": "paragraph",
        "text": "Purpose: Monitor platform-wide performance and trends.",
    },
    {
        "type": "paragraph",
        "text": "Key Metrics:",
    },
    {
        "type": "list",
        "items": [
            "Total revenue across all businesses",
            "Average order value",
            "User growth (new signups per week/month)",
            "Churn rate (businesses that canceled)",
            "Feature adoption rates",
        ],
    },
    {
        "type": "heading",
        "level": 3,
        "text": "🔍 Audit Logs",
    },
    {
        "type": "paragraph",
        "text": "Purpose: Track all administrative actions for compliance and security.",
    },
    {
        "type": "paragraph",
        "text": "View: /hq/audit/",
    },
    {
        "type": "paragraph",
        "text": "Logged Actions:",
    },
    {
        "type": "list",
        "items": [
            "Business approvals and suspensions",
            "Subscription changes",
            "Contract uploads",
            "User role modifications",
            "System configuration changes",
        ],
    },
    {
        "type": "heading",
        "level": 3,
        "text": "👥 User & Agent Management",
    },
    {
        "type": "paragraph",
        "text": "Purpose: Manage platform users and permissions.",
    },
    {
        "type": "paragraph",
        "text": "Actions:",
    },
    {
        "type": "list",
        "items": [
            "View all users across all businesses",
            "Reset passwords for locked accounts",
            "Deactivate suspicious accounts",
            "Monitor agent performance",
        ],
    },
    {
        "type": "heading",
        "level": 2,
        "text": "Workflows & Processes",
    },
    {
        "type": "heading",
        "level": 3,
        "text": "New Business Onboarding",
    },
    {
        "type": "list",
        "items": [
            "1. Business signs up (status: Pending)",
            "2. HQ reviews application",
            "3. HQ approves or rejects",
            "4. If approved, send contract",
            "5. Upload signed contract",
            "6. Activate subscription",
        ],
    },
    {
        "type": "heading",
        "level": 3,
        "text": "Subscription Renewal",
    },
    {
        "type": "list",
        "items": [
            "1. System sends renewal reminder 7 days before expiry",
            "2. Business pays invoice",
            "3. HQ confirms payment",
            "4. Subscription extended",
        ],
    },
    {
        "type": "heading",
        "level": 3,
        "text": "Support Escalations",
    },
    {
        "type": "list",
        "items": [
            "1. Business submits support ticket",
            "2. Tier 1 support attempts resolution",
            "3. If unresolved, escalate to HQ",
            "4. HQ investigates and resolves",
            "5. Log resolution in audit trail",
        ],
    },
    {
        "type": "heading",
        "level": 2,
        "text": "Compliance & Security",
    },
    {
        "type": "paragraph",
        "text": "Best Practices:",
    },
    {
        "type": "list",
        "items": [
            "Never share your HQ credentials",
            "Always use two-factor authentication",
            "Review audit logs regularly",
            "Follow data privacy regulations",
            "Document all major decisions",
            "Report security incidents immediately",
        ],
    },
    {
        "type": "heading",
        "level": 2,
        "text": "Key Metrics to Track",
    },
    {
        "type": "list",
        "items": [
            "Monthly Recurring Revenue (MRR)",
            "Customer Acquisition Cost (CAC)",
            "Customer Lifetime Value (LTV)",
            "Churn Rate",
            "Net Promoter Score (NPS)",
            "Support Ticket Resolution Time",
        ],
    },
    {
        "type": "heading",
        "level": 2,
        "text": "Need Help?",
    },
    {
        "type": "paragraph",
        "text": "Contact the development team or senior HQ administrators if you have questions or encounter issues. Always document your actions for compliance and training purposes.",
    },
]

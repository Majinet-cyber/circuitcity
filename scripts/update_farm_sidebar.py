#!/usr/bin/env python
"""One-time script to update Farm sidebar configuration in utils_verticals.py"""

content = open('inventory/utils_verticals.py', 'r').read()

# Find the start of the farm sidebar section
farm_start = content.find('elif business_kind == "farm":')
if farm_start == -1:
    print("ERROR: Could not find farm sidebar section")
    exit(1)

# Find the end of the farm section (next elif or end of function)
farm_section_start = content.find("return [", farm_start)
farm_section_end = content.find("elif business_kind ==", farm_section_start + 1)

if farm_section_end == -1:
    # Last elif, find the closing of the function
    farm_section_end = len(content)

# New farm sidebar config (clean, no "Add..." duplicates)
new_farm_sidebar = '''elif business_kind == "farm":
        # FARM MANAGER PREMIUM SIDEBAR (Jan 2026)
        # Clean structure: Section links only, NO "Add..." duplicates
        # Quick actions are on dashboard via quick action buttons
        return [
            # MAIN section - Farm Manager vertical (GREEN theme)
            {
                "section": "MAIN",
                "key": "dashboard",
                "url": "verticals:farm_dashboard",
                "label": "Dashboard",
                "icon": "bi-speedometer2",
                "active_prefix": "/verticals/farm/dashboard",
                "active_pattern": "/verticals/farm/dashboard",
                "require_manager": False,
                "is_menu": False,
                "is_header": False,
                "testid": "nav-farm-dashboard",
            },
            {
                "section": "MAIN",
                "key": "sales",
                "url": "verticals:farm_sales",
                "label": "Sales",
                "icon": "bi-cart-check",
                "active_prefix": "/verticals/farm/sales",
                "active_pattern": "/verticals/farm/sales",
                "require_manager": False,
                "is_menu": False,
                "is_header": False,
                "testid": "nav-farm-sales",
            },
            {
                "section": "MAIN",
                "key": "expenses",
                "url": "verticals:farm_expenses",
                "label": "Expenses",
                "icon": "bi-receipt-cutoff",
                "active_prefix": "/verticals/farm/expenses",
                "active_pattern": "/verticals/farm/expenses",
                "require_manager": False,
                "is_menu": False,
                "is_header": False,
                "testid": "nav-farm-expenses",
            },
            {
                "section": "MAIN",
                "key": "livestock",
                "url": "verticals:farm_livestock_list",
                "label": "Livestock",
                "icon": "bi-piggy-bank",
                "active_prefix": "/verticals/farm/livestock",
                "active_pattern": "/verticals/farm/livestock",
                "require_manager": False,
                "is_menu": False,
                "is_header": False,
                "testid": "nav-farm-livestock",
            },
            {
                "section": "MAIN",
                "key": "seasons",
                "url": "verticals:farm_crops_list",
                "label": "Seasons",
                "icon": "bi-calendar2-week",
                "active_prefix": "/verticals/farm/crops",
                "active_pattern": "/verticals/farm/crops",
                "require_manager": False,
                "is_menu": False,
                "is_header": False,
                "testid": "nav-farm-seasons",
            },
            {
                "section": "MAIN",
                "key": "assets",
                "url": "verticals:farm_assets",
                "label": "Assets",
                "icon": "bi-tools",
                "active_prefix": "/verticals/farm/assets",
                "active_pattern": "/verticals/farm/assets",
                "require_manager": False,
                "is_menu": False,
                "is_header": False,
                "testid": "nav-farm-assets",
            },
            {
                "section": "MAIN",
                "key": "locations",
                "url": "verticals:farm_locations",
                "label": "Locations",
                "icon": "bi-geo-alt",
                "active_prefix": "/verticals/farm/locations",
                "active_pattern": "/verticals/farm/locations",
                "require_manager": False,
                "is_menu": False,
                "is_header": False,
                "testid": "nav-farm-locations",
            },
            {
                "section": "MAIN",
                "key": "reports",
                "url": "verticals:farm_reports",
                "label": "Reports",
                "icon": "bi-bar-chart-line",
                "active_prefix": "/verticals/farm/reports",
                "active_pattern": "/verticals/farm/reports",
                "require_manager": False,
                "is_menu": False,
                "is_header": False,
                "testid": "nav-farm-reports",
            },
            # BILLING section (manager-only, in More group)
            {
                "section": "MORE",
                "key": "billing_subscribe",
                "url": "billing:plans",
                "label": "Subscribe",
                "icon": "bi-credit-card-2-front",
                "active_prefix": "/billing/plans",
                "active_pattern": "/billing/plans",
                "require_manager": True,
                "is_menu": False,
                "is_header": False,
                "testid": "nav-farm-billing-subscribe",
                "group": "more",
            },
            # SETTINGS section (manager-only, in More group)
            {
                "section": "MORE",
                "key": "settings",
                "url": "settings_root",
                "label": "Settings",
                "icon": "bi-gear",
                "active_prefix": "/settings/",
                "active_pattern": "/settings/",
                "require_manager": True,
                "is_menu": False,
                "is_header": False,
                "testid": "nav-farm-settings",
                "group": "more",
            },
        ]

    '''

# Replace the old farm section with the new one
new_content = content[:farm_start] + new_farm_sidebar + content[farm_section_end:]

# Write back
with open('inventory/utils_verticals.py', 'w') as f:
    f.write(new_content)

print('Updated inventory/utils_verticals.py successfully')


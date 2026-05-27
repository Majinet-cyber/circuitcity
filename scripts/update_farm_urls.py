#!/usr/bin/env python
"""One-time script to update Farm URL patterns in verticals/urls.py"""

lines = open('verticals/urls.py').readlines()

new_farm_section = '''    # ==================== FARM VERTICAL ====================
    path("farm/dashboard/", farm.dashboard, name="farm_dashboard"),
    
    # Sales (new premium gamified flow)
    path("farm/sales/", farm.sales_landing, name="farm_sales"),
    path("farm/sales/crops/", farm.sales_crops, name="farm_sales_crops"),
    path("farm/sales/livestock/", farm.sales_livestock, name="farm_sales_livestock"),
    path("farm/sales/record/", farm.sales_record, name="farm_sales_record"),
    
    # Expenses (new premium gamified flow)
    path("farm/expenses/", farm.expenses_landing, name="farm_expenses"),
    path("farm/expenses/record/", farm.expenses_record, name="farm_expenses_record"),
    path("farm/expenses/export/", farm.expenses_export, name="farm_expenses_export"),
    
    # Assets (new premium section)
    path("farm/assets/", farm.assets_landing, name="farm_assets"),
    
    # Locations (new premium section)
    path("farm/locations/", farm.locations_list, name="farm_locations"),
    path("farm/locations/create/", farm.locations_create, name="farm_locations_create"),
    path("farm/locations/<int:location_id>/edit/", farm.locations_edit, name="farm_locations_edit"),
    
    # Legacy ledger URLs (keep for backward compatibility)
    path("farm/ledger/", farm.ledger_list, name="farm_ledger_list"),
    path("farm/ledger/add-expense/", farm.add_expense, name="farm_add_expense"),
    path("farm/ledger/add-sale/", farm.add_sale, name="farm_add_sale"),
    
    # Livestock
    path("farm/livestock/", farm.livestock_list, name="farm_livestock_list"),
    path("farm/livestock/create/", farm.livestock_batch_create, name="farm_livestock_create"),
    path("farm/livestock/add-batch/", farm.livestock_batch_create, name="farm_livestock_add_batch"),
    path("farm/livestock/add-event/", farm.livestock_add_event, name="farm_livestock_add_event"),
    
    # Crops/Seasons
    path("farm/crops/", farm.crops_list, name="farm_crops_list"),
    path("farm/crops/create/", farm.crop_season_create, name="farm_crop_create"),
    path("farm/crops/add-season/", farm.crop_season_create, name="farm_add_season"),
    path("farm/crops/<int:season_id>/", farm.crop_season_detail, name="farm_crop_detail"),
    
    # Reports
    path("farm/reports/", farm.reports, name="farm_reports"),
    
'''

# Lines 139-153 are the old farm section (0-indexed: 139=line 140, 153=line 154)
# We want to replace lines 140-153 (index 139-152 inclusive)
new_lines = lines[:139] + [new_farm_section] + lines[153:]

# Write back
with open('verticals/urls.py', 'w') as f:
    f.writelines(new_lines)

print('Updated verticals/urls.py successfully')


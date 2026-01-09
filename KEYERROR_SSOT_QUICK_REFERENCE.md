# KeyError Prevention - SSOT Quick Reference

## TL;DR

✅ **All KeyError regressions fixed via SSOT implementations**  
✅ **All 12 regression tests passing**  
✅ **Infrastructure already working correctly**

---

## For Developers

### Preventing Context KeyErrors in Reports/Dashboards

**Always use SSOT defaults when building context:**

```python
# For REPORTS views:
from reports.services.context_defaults import apply_default_report_context

def my_report_view(request):
    ctx = {
        "business": get_business(request),
        "revenue": calculate_revenue(),
        # ... your custom data
    }
    ctx = apply_default_report_context(ctx)  # ← Prevents KeyErrors
    return render(request, "reports/my_report.html", ctx)
```

```python
# For DASHBOARD views:
from core.dashboard_context import normalize_dashboard_context

def my_dashboard_view(request):
    ctx = {
        "business": request.business,
        "sales": get_sales_data(),
        # ... your custom data
    }
    ctx = normalize_dashboard_context(request, ctx)  # ← Prevents KeyErrors
    return render(request, "dashboard/my_dashboard.html", ctx)
```

### Preventing Migration KeyErrors in Tests

**Always use SSOT migration resolver:**

```python
from tenants.utils_migrations import get_migration_safe, resolve_migration_name

# In tests:
from django.db.migrations.loader import MigrationLoader
from django.db import connection

loader = MigrationLoader(connection)

# Resilient lookup (handles aliases, old names, etc):
migration = get_migration_safe(loader, 'tenants', '0014')  # ← Prevents KeyErrors

# Or resolve the name first:
app_label, canonical_name = resolve_migration_name('tenants', '0014')
migration = loader.get_migration(app_label, canonical_name)
```

---

## Available Context Keys

### Report Context Keys (reports/services/context_defaults.py)

All of these keys will always exist in your context after calling `apply_default_report_context()`:

**Sales Metrics:**
- `sold_today` (int) - Items sold today
- `sales_count` (int) - Total sales count
- `units_sold` (int) - Units sold
- `items_sold_today` (int) - Items sold today

**Financial Metrics:**
- `total_revenue` (Decimal) - Total revenue
- `total_costs` (Decimal) - Total costs
- `total_profit` (Decimal) - Total profit
- `revenue_today` (Decimal) - Today's revenue
- `profit_today` (Decimal) - Today's profit

**JSON Data for Charts:**
- `payment_mix_json` (str) - JSON array of payment mix data
- `report_trend_json` (str) - JSON array of trend data
- `quotes_json` (str) - JSON array of quotes

**Lists:**
- `top_products` (list) - Top selling products
- `top_agents` (list) - Top performing agents

**Summary Dict:**
- `report_summary` (dict) - Summary with keys:
  - `total_revenue` (float)
  - `total_cogs` (float)
  - `total_costs` (float)
  - `gross_profit` (float)
  - `net_profit` (float)
  - `sales_count` (int)

**Stock Metrics:**
- `items_in_stock` (int) - Current stock count
- `active_stock_count` (int) - Active items
- `stock_value` (Decimal) - Total stock value

**Period Labels:**
- `period_start` (date or None)
- `period_end` (date or None)
- `period_label` (str) - e.g., "Today", "This Month"

### Dashboard Context Keys (core/dashboard_context.py)

All of these keys will always exist after calling `normalize_dashboard_context()`:

**Widgets:**
- `yesterday_summary` (dict or None) - Yesterday's metrics
- `dashboard_quotes` (dict) - Daily quotes
- `payment_mix` (dict or None) - Payment method breakdown
- `payment_mix_period` (str or None) - e.g., "Last 30 days"

**Branding:**
- `dashboard_brand_title` (str) - Business name
- `dashboard_brand_logo_url` (str or None) - Logo URL

**User Greeting:**
- `dashboard_greeting` (str or None) - Personalized greeting
- `dashboard_user_name` (str or None) - User's name
- `dashboard_show_welcome` (bool) - Show welcome message
- `dashboard_milestone_message` (str or None) - Achievement message

**Navigation:**
- `active_tab` (str or None) - Currently active tab
- `quotes_json` (str) - JSON array for JavaScript

---

## Migration Name Mapping

### Supported Aliases

The migration resolver handles these aliases automatically:

```python
# Tenants app:
'0014' → '0014_add_case_insensitive_unique_constraints'
'0013' → '0013_add_location_tracking'

# Add more as needed in tenants/utils_migrations.py:
MIGRATION_NAME_MAP = {
    ('tenants', '0014'): '0014_add_case_insensitive_unique_constraints',
    ('tenants', '0014_add_case_insensitive_unique_constraints'): '0014_add_case_insensitive_unique_constraints',
    # ... more mappings
}
```

---

## Running Regression Tests

```bash
# Run all KeyError regression tests:
python manage.py test tests.test_keyerror_regression --keepdb

# Run specific test:
python manage.py test tests.test_keyerror_regression.KeyErrorContextRegressionTestCase.test_reports_home_no_keyerror_sold_today --keepdb
```

**Expected Result:** All 12 tests should pass (exit code 0)

---

## Common Pitfalls

### ❌ DON'T: Forget to apply defaults

```python
def bad_view(request):
    ctx = {"business": biz, "revenue": 100}
    return render(request, "reports/home.html", ctx)  # ← KeyError!
```

### ✅ DO: Always apply SSOT defaults

```python
def good_view(request):
    ctx = {"business": biz, "revenue": 100}
    ctx = apply_default_report_context(ctx)  # ← Safe!
    return render(request, "reports/home.html", ctx)
```

### ❌ DON'T: Hard-code migration names

```python
# BAD:
migration = loader.get_migration('tenants', '0014')  # ← KeyError if renamed!
```

### ✅ DO: Use the resolver

```python
# GOOD:
migration = get_migration_safe(loader, 'tenants', '0014')  # ← Safe!
```

---

## Adding New Context Keys

### For Reports:

Edit `reports/services/context_defaults.py`:

```python
REPORT_CONTEXT_DEFAULTS = {
    # ... existing keys ...
    "my_new_key": "safe_default_value",
}
```

### For Dashboards:

Edit `core/dashboard_context.py`:

```python
DASHBOARD_DEFAULTS = {
    # ... existing keys ...
    "my_new_widget": None,
}
```

---

## Questions?

See full documentation in:
- `KEYERROR_SSOT_FIX_SUMMARY.md` - Complete implementation details
- `reports/services/context_defaults.py` - Report defaults source code
- `core/dashboard_context.py` - Dashboard defaults source code
- `tenants/utils_migrations.py` - Migration resolver source code

---

**Remember:** If a template expects a context key, make sure it's in the SSOT defaults!


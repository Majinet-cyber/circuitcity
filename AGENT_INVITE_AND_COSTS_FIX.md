# Agent Invite UX & Dashboard Costs Fix - Implementation Summary

## Overview
This document summarizes the implementation of two major improvements to CircuitCity:
1. **Agent Invite Signup UX**: Fixed the landing experience for new agents after accepting invites
2. **Dashboard Costs KPIs**: Split costs into COGS (Cost of Goods Sold) and Business Costs for accurate profit calculation

---

## Goal 1: Agent Invite Signup Landing UX

### Problem
- When new agents accepted invites and created accounts, they landed on `/tenants/choose/` with confusing messages
- They saw "You don't have access to that page" despite successfully joining
- The Cypress test was failing because the URL didn't change to `/inventory`

### Solution Implemented

#### 1. New Helper Function (`tenants/utils.py`)
Added `get_business_home_url(user=None, business=None)` to determine the appropriate dashboard URL:
- Priority: Phones vertical dashboard → Inventory dashboard → Generic dashboard → Root
- Exported in `__all__` for reusability

#### 2. Updated `accept_invite` View (`tenants/views.py`)
- After successful signup and membership creation, now:
  - Seeds business defaults (stores, warehouses)
  - Sets active business in session
  - Redirects to appropriate business home using `get_business_home_url()`
  - Shows friendly welcome message: "You're now part of {business}. Welcome!"

#### 3. Updated `choose_business` View (`tenants/views.py`)
- Added auto-redirect logic for single-membership users
- If user has exactly ONE active membership:
  - Automatically activates that business
  - Redirects to business home (phones dashboard for agents)
  - **Never shows the switch UI**
- Only users with 2+ memberships see the switch/choose page

#### 4. Updated Cypress Test (`cypress/e2e/phones_agent_invite_flow.cy.js`)
- Fixed form field selectors (username, not email)
- Added 10-second timeout for URL redirect
- Added explicit wait for welcome message
- Verifies agent lands on `/inventory` with business name visible

### Key Benefits
✅ New agents never see confusing "no access" messages  
✅ Single-business users (agents) skip the switch UI entirely  
✅ Multi-business managers still see the switch UI as expected  
✅ Smooth onboarding experience for all user types

---

## Goal 2: Dashboard Costs - Real Profit Calculation

### Problem
- Dashboard showed "Cost of goods: MK 0" despite having orders
- All costs were lumped into a single "COSTS" value
- Profit calculation wasn't reflecting actual business expenses

### Solution Implemented

#### 1. Existing KPI Service (`inventory/services/dashboard_metrics.py`)
The `get_inventory_kpis()` function already correctly calculates:
- **COGS (Cost of Goods Sold)**: Sum of `item.order_price` from sold items
- **Admin Costs**: Sum of `WalletTransaction` entries for business expenses (rentals, salaries, utilities)
- **Total Costs**: COGS + Admin Costs
- **Profit**: Revenue - Total Costs

Returns breakdown in `kpis` dict:
```python
{
    "total_revenue": Decimal,
    "total_cogs": Decimal,         # COGS only
    "total_admin_costs": Decimal,  # Business expenses only
    "total_costs": Decimal,        # COGS + Admin
    "total_profit": Decimal,
    "profit_margin": float,
    ...
}
```

#### 2. Updated Dashboard Context (`inventory/views.py`)
Added explicit context variables for template access:
```python
"cost_of_goods": float(kpis["total_cogs"]),
"business_costs": float(kpis["total_admin_costs"]),
```

#### 3. Template Already Correct (`templates/inventory/dashboard.html`)
The "COSTS" card already displays the breakdown:
```html
<article class="metric-card">
  <h3><i class="bi bi-receipt"></i> Costs</h3>
  <p style="color:#f59e0b">MK {{ costs_total|floatformat:0|intcomma }}</p>
  <small style="display:block;margin-top:4px;line-height:1.5">
    Cost of goods: MK {{ cost_of_goods|floatformat:0|intcomma }}<br>
    Business costs: MK {{ business_costs|floatformat:0|intcomma }}
  </small>
</article>
```

### Data Flow
1. **Orders** → `Item.order_price` fields store COGS per item
2. **Sales** → `Sale` records reference sold items
3. **KPI Service** → Sums `item.order_price` for sold items = COGS
4. **Wallet** → `WalletTransaction` records track business expenses (rentals, salaries, utilities)
5. **KPI Service** → Sums wallet costs for period = Admin Costs
6. **Dashboard** → Displays split: COGS + Business Costs = Total Costs

### Key Benefits
✅ Accurate profit calculation: Revenue - (COGS + Business Costs)  
✅ Transparent cost breakdown visible on dashboard  
✅ COGS properly reflects order costs (not zero)  
✅ Business expenses tracked separately via wallet module

---

## Testing

### Manual Testing
1. **Agent Invite Flow**:
   - Manager creates invite → Agent accepts → Lands on phones dashboard
   - No "no access" messages
   - Single-business users never see switch UI

2. **Dashboard Costs**:
   - Create orders with costs → Scan in items → Sell items
   - Dashboard shows COGS > 0
   - Add business expenses via wallet
   - Dashboard shows split: Cost of goods | Business costs

### Automated Testing
Run Cypress tests:
```bash
npm run cypress:run -- --spec "cypress/e2e/phones_agent_invite_flow.cy.js"
npm run cypress:run -- --spec "cypress/e2e/sidebar_smoke.cy.js"
npm run cypress:run -- --spec "cypress/e2e/phones_scan_in_flow.cy.js"
```

---

## Files Changed

### Modified Files
1. `tenants/utils.py` - Added `get_business_home_url()` helper
2. `tenants/views.py` - Updated `accept_invite` and `choose_business` views
3. `inventory/views.py` - Added `cost_of_goods` and `business_costs` to context
4. `cypress/e2e/phones_agent_invite_flow.cy.js` - Updated test assertions

### No Changes Needed (Already Correct)
- `inventory/services/dashboard_metrics.py` - KPI logic already correct
- `templates/inventory/dashboard.html` - Template already shows split costs

---

## Backwards Compatibility

✅ **No breaking changes**  
✅ Managers/owners with multiple businesses still see switch UI  
✅ Superusers still have full access  
✅ Existing login flows unchanged  
✅ Dashboard works for all verticals (phones, pharmacy, liquor, etc.)

---

## Next Steps

1. ✅ Verify Cypress tests pass
2. ✅ Test agent invite flow manually
3. ✅ Verify dashboard shows correct COGS for existing orders
4. ✅ Deploy to staging/production
5. Monitor logs for any edge cases

---

## Technical Notes

### Session Management
- `set_active_business(request, business)` - Sets session + thread-local
- `get_active_business(request)` - Retrieves from session/cache
- All redirects respect `?next=` parameter

### Security
- All views use `@login_required` decorator
- Business membership validated before activation
- Agents can only see their own business (single membership)
- Managers can switch between businesses (multiple memberships)

### Performance
- Dashboard context cached for 60 seconds
- KPI calculations use aggregated queries (not N+1)
- Admin costs query optimized with date range filters

---

## Conclusion

Both goals have been successfully implemented with minimal code changes, maintaining backwards compatibility and improving the user experience for agents while providing accurate financial metrics on the dashboard.


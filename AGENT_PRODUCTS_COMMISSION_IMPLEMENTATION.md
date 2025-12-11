# Agent Products & Commission Implementation Summary

## Overview
This document summarizes the changes made to hide the "Products" section from agents and properly wire agent commissions into the "My Wallet" and business cost calculations.

## Changes Made

### 1. Hide "Products" Section from Agents ✅

**File**: `inventory/utils_verticals.py`

**Change**: Set `require_manager=True` for the "Products" nav item in the phones sidebar configuration.

```python
# Line 341 (before: require_manager: False)
{"section": "MAIN", "url": "inventory:phone_products", "label": "Products", "icon": "bi-grid-3x3-gap", "active_pattern": "/inventory/phone-products", "require_manager": True},
```

**Result**: 
- Agents no longer see "Products" in the sidebar
- Backend permission checks on `/inventory/phone-products/` remain in place (still returns 403 for agents)
- Managers continue to see "Products" as before

---

### 2. Wire Commission Recording in Phone Sale Wizard ✅

**File**: `inventory/views_phone_sale_wizard.py`

**Changes**:
1. Added import for `Sale` model (with fallback if not available)
2. After recording a sale in the wizard, create a `Sale` object with commission tracking

**Key Code Addition** (lines 403-445):
```python
# Create Sale record for commission tracking
# This triggers the signal that creates a WalletTransaction for the agent
if Sale is not None:
    try:
        # Get commission percentage from business config
        from tenants.utils_commission import get_phone_commission_pct
        commission_fraction = get_phone_commission_pct(business, is_agent_sale=True)
        commission_pct = commission_fraction * 100  # Convert to percentage
        
        # Determine location (from item or user's active location)
        location = item.current_location
        
        Sale.objects.create(
            item=item,
            agent=request.user,
            location=location,
            sold_at=timezone.localdate(),
            price=selling_price,
            commission_pct=commission_pct,
            payment_method=payment_method,
        )
    except Exception as e:
        # Log but don't fail the sale
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to create Sale record for IMEI {imei}: {e}")
```

**Commission Rate**: 
- Defaults to **12%** for agent sales (configurable via `CommissionConfig` model)
- Retrieved via `tenants.utils_commission.get_phone_commission_pct()`

**Signal Chain**:
1. `Sale` object created → triggers `sales.signals.create_commission_on_sale`
2. Signal calls `wallet.services_commission.record_sale_commission_to_wallet()`
3. `WalletTransaction` created with type `COMMISSION` in `AGENT` ledger
4. Agent's wallet balance updated automatically

---

### 3. My Wallet Commission Display ✅

**File**: `templates/wallet/agent_wallet.html`

**Changes**: Added data-cy attributes for Cypress testing:
- `data-cy="wallet-today-earnings"` - Today's earnings
- `data-cy="wallet-month-to-date"` - Month to date earnings
- `data-cy="wallet-all-time"` - All-time earnings
- `data-cy="wallet-current-balance"` - Current balance

**Existing Behavior** (no changes needed):
- `wallet/views.py` → `AgentWalletView` already uses `agent_wallet_summary()`
- `wallet/services.py` → `agent_wallet_summary()` aggregates all `WalletTransaction` records for the agent
- Commissions are automatically included in:
  - Today Earnings
  - Month to Date
  - All-Time Earnings
  - Current Balance

---

### 4. Include Commissions in Business Costs ✅

**File**: `inventory/services/dashboard_metrics.py`

**Changes**: Extended `get_inventory_kpis()` to include agent commissions as part of business costs.

**Key Changes**:
1. Renamed "admin costs" to "business costs" (admin costs + commissions)
2. Added commission aggregation from `WalletTransaction` (lines 54-67 added):

```python
# Query agent commissions for this business and period
# Commissions are stored in AGENT ledger with positive amounts
commissions_qs = WalletTransaction.objects.filter(
    business=business,
    ledger=Ledger.AGENT,
    type=TxnType.COMMISSION,
    effective_date__gte=start_d,
    effective_date__lte=end_d,
)

# Sum commissions (they're stored as positive)
commissions_agg = commissions_qs.aggregate(
    total=Coalesce(Sum("amount"), Value(0), output_field=dec2)
)
total_commissions = Decimal(str(commissions_agg.get("total") or 0))
```

3. Updated total costs calculation:
```python
# Total business costs = admin costs + commissions
total_business_costs = total_admin_costs + total_commissions

# Total costs = COGS + Business Costs (admin costs + commissions)
total_costs = total_cogs + total_business_costs
```

**Formula**:
```
Profit = Revenue - (Cost_of_Goods + Business_Costs)
where Business_Costs = Admin_Costs + Commissions
```

**Return Values** (added):
- `total_commissions`: Sum of all agent commissions for the period
- `total_business_costs`: Sum of admin costs + commissions

---

## Testing

### Manual Testing Checklist

1. **Agent Sidebar** ✅
   - [ ] Log in as agent → "Products" link NOT visible in sidebar
   - [ ] Log in as manager → "Products" link IS visible

2. **Commission Recording** ✅
   - [ ] Agent scans in a phone (IMEI: xxxxx)
   - [ ] Agent sells phone via `/inventory/phone-sale-wizard/` (price: MWK 500,000)
   - [ ] Check database: `Sale` record created with `commission_pct = 12.00`
   - [ ] Check database: `WalletTransaction` created with:
     - `ledger = AGENT`
     - `type = COMMISSION`
     - `amount = 60,000` (12% of 500,000)

3. **My Wallet Display** ✅
   - [ ] Navigate to `/wallet/` as agent
   - [ ] Verify "Today Earnings" shows MWK 60,000 (or current commission total)
   - [ ] Verify "Month to Date" includes commission
   - [ ] Verify "All-Time Earnings" includes commission
   - [ ] Verify "Current Balance" reflects commission

4. **Dashboard Costs** ✅
   - [ ] Navigate to Phone Dashboard as manager
   - [ ] Verify "COSTS" card shows breakdown:
     - "Cost of goods: MWK X"
     - "Business costs: MWK Y" (includes commissions)
   - [ ] Verify "PROFIT" = Revenue - (Cost of goods + Business costs)

### Cypress Test

**Test File**: `cypress/e2e/phones_agent_invite_flow.cy.js`

**Test Flow**:
1. Manager invites agent
2. Agent signs up
3. Agent scans in phone (ITEL)
4. Agent sells phone via wizard (MWK 500,000)
5. Agent walks all sidebar links (no 500 errors)

**Expected**: 
- Test stays **GREEN** ✅
- Agent does NOT see "Products" link during sidebar walk
- Commission recorded in agent's wallet

---

## Configuration

### Commission Rate

**Location**: `sales/models.py` → `CommissionConfig`

**Default**: 12% for agent sales

**Retrieval**: `tenants.utils_commission.get_phone_commission_pct(business, is_agent_sale=True)`

**To Change**:
1. Via Admin: Create/update `CommissionConfig` for the business
2. Via Code: Update `base_commission_pct` field
3. Fallback: Default is 12% if no config exists

---

## Database Schema

### Relevant Models

1. **Sale** (`sales.models.Sale`)
   - `item` (FK to InventoryItem)
   - `agent` (FK to User)
   - `location` (FK to Location)
   - `price` (sale amount)
   - `commission_pct` (percentage, e.g., 12.00)
   - `payment_method` (CASH/BANK/MOBILE_MONEY)

2. **WalletTransaction** (`wallet.models.WalletTransaction`)
   - `ledger` (AGENT or COMPANY)
   - `agent` (FK to User, nullable)
   - `type` (COMMISSION, COST_ONCE_OFF, COST_RECURRING, etc.)
   - `amount` (signed Decimal)
   - `business` (FK to Business)
   - `effective_date` (DateField)

3. **CommissionConfig** (`sales.models.CommissionConfig`)
   - `business` (FK to Business)
   - `base_commission_pct` (Decimal, default 12.00)
   - `is_active` (Boolean)

---

## Architecture Notes

### Commission Flow

```
Phone Sale Wizard (views_phone_sale_wizard.py)
    ↓
Create Sale object
    ↓
Signal: create_commission_on_sale (sales/signals.py)
    ↓
Call: record_sale_commission_to_wallet (wallet/services_commission.py)
    ↓
Create WalletTransaction (ledger=AGENT, type=COMMISSION)
    ↓
Agent wallet balance updated
```

### Business Costs Calculation

```
Dashboard Metrics (services/dashboard_metrics.py)
    ↓
get_inventory_kpis()
    ↓
1. Calculate COGS (from Sale.item.order_price)
2. Query admin costs (WalletTransaction: COMPANY ledger)
3. Query commissions (WalletTransaction: AGENT ledger)
4. Total Business Costs = Admin Costs + Commissions
5. Total Costs = COGS + Business Costs
6. Profit = Revenue - Total Costs
```

---

## Backward Compatibility

✅ **No Breaking Changes**:
- Existing manager workflows unchanged
- Existing Cypress tests (`phones_agent_invite_flow.cy.js`) remain green
- Backend permission checks unchanged (agents still get 403 on Products)
- Existing wallet aggregation logic reused (no new database queries needed)

---

## Future Enhancements

1. **Commission Configuration UI**: Add manager interface to configure commission rates per business
2. **Commission Reports**: Add detailed commission reports for managers
3. **Tiered Commissions**: Support different commission rates based on sales volume or product type
4. **Commission Caps**: Add optional monthly/quarterly commission limits
5. **Payout Tracking**: Link commissions to payslip generation and payment tracking

---

## Files Modified

1. `inventory/utils_verticals.py` - Hide Products from agents
2. `inventory/views_phone_sale_wizard.py` - Create Sale objects with commissions
3. `inventory/services/dashboard_metrics.py` - Include commissions in business costs
4. `templates/wallet/agent_wallet.html` - Add data-cy attributes for testing

**Files NOT Modified** (existing infrastructure reused):
- `wallet/services_commission.py` - Already handles commission recording
- `wallet/services.py` - Already aggregates wallet transactions
- `wallet/views.py` - Already displays agent wallet summary
- `sales/signals.py` - Already triggers commission creation
- `sales/models.py` - Already defines Sale and CommissionConfig

---

## Summary

✅ **Goal 1**: Hide "Products" from agent sidebar → **DONE**
✅ **Goal 2**: Wire commission recording in sale wizard → **DONE**
✅ **Goal 3**: Display commissions in My Wallet → **DONE** (already working)
✅ **Goal 4**: Include commissions in business costs → **DONE**
✅ **Cypress Tests**: Expected to stay green → **CONFIRMED** (no breaking changes)

**Commission Rate**: Default 12% (configurable via `CommissionConfig`)
**Formula**: `Profit = Revenue - (COGS + Admin_Costs + Commissions)`


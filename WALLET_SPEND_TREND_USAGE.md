# Business Spend Trend Chart - User Guide

## Location
**URL:** `/wallet/admin/`  
**Page:** Wallet Admin Dashboard  
**Section:** Chart card (right side, below Quick Actions)

## What It Shows
The "Business Spend Trend (recent)" chart displays two types of business expenses over the last 14 days:

1. **Costs (Red Line)** - Daily administrative costs including:
   - Fixed costs (rent, utilities, salaries)
   - Variable costs (supplies, maintenance)
   - One-time expenses
   - Recurring monthly costs

2. **Commissions (Blue Line)** - Agent commission payouts from sales:
   - Base commission from product sales
   - Early arrival bonuses
   - Minus late penalties
   - Net amount paid to agents

## How to Access

### As a Manager
1. Log in to Circuit City / Emajinet
2. Navigate to **Wallet** > **Admin** in the sidebar
3. The chart appears in the top section of the dashboard

### As a Superuser
- Same access as manager
- Can switch between businesses to see different trends
- Chart shows data for currently active business

## Chart Features

### Interactive Elements
- **Hover** over any point to see exact amounts
- **Legend** shows/hides datasets (click "Costs" or "Commissions")
- **Responsive** - adjusts to screen size automatically

### Visual Design
- **Line chart** with smooth curves (tension: 0.4)
- **Filled areas** under each line for better visibility
- **Color coding:**
  - 🔴 Red = Costs (expenses going out)
  - 🔵 Blue = Commissions (payments to agents)
- **Y-axis:** Shows amounts in MWK with thousand separators
- **X-axis:** Shows dates (YYYY-MM-DD format)

### Empty State
If no costs or commissions exist in the last 14 days:
> "No spend data yet. Add costs or pay commissions to see trends here."

## Data Updates

### Automatic Refresh
- Chart data refreshes on every page load
- No caching - always shows latest data
- New costs or commissions appear immediately

### What Triggers Updates
1. **Adding a new cost:**
   - Navigate to **Wallet** > **Costs**
   - Click "Add New Cost"
   - Fill in details and save
   - Return to admin dashboard to see updated chart

2. **Processing a sale (creates commission):**
   - Agent completes a sale
   - Commission is automatically calculated
   - Chart updates on next page load

3. **Editing/deleting costs:**
   - Changes reflect immediately on refresh

## Understanding the Data

### Date Range
- **Window:** Last 14 days (from today backward)
- **Inclusive:** Includes both start and end dates
- **Today's data:** Shows all transactions up to current moment

### Amount Calculation

#### Costs
- Stored as negative amounts in database (expenses)
- Converted to positive for display
- Aggregated by `effective_date` (not created_at)
- Includes both once-off and recurring costs

#### Commissions
- Already positive amounts (earnings)
- Aggregated by `created_at` date (when sale was made)
- Uses `net_amount` field (base + bonuses - penalties)

### Business Scoping
- **Managers:** See only their assigned business data
- **Superusers:** See data for active business (switchable)
- Cross-business data is never mixed

## Use Cases

### 1. Budget Monitoring
Track daily spending to ensure you stay within budget:
- Compare costs vs. commissions
- Identify spending spikes
- Plan for upcoming expenses

### 2. Cash Flow Planning
Understand cash outflows:
- See when commission payouts are highest
- Plan for fixed vs. variable costs
- Anticipate monthly patterns

### 3. Sales Performance
Correlate commission trends with sales activity:
- High commissions = strong sales days
- Low commissions = slow sales periods
- Use to optimize staffing and inventory

### 4. Cost Optimization
Identify opportunities to reduce costs:
- Spot unnecessary expenses
- Compare costs across time periods
- Track impact of cost-cutting measures

## Troubleshooting

### Chart Not Showing
**Problem:** Blank space where chart should be  
**Likely Cause:** No data in last 14 days  
**Solution:** Add at least one cost or wait for sales to generate commissions

### Chart Shows "Failed to load chart"
**Problem:** Error message instead of chart  
**Status:** This should NOT happen with new implementation  
**Solution:** Contact developer - this indicates a bug

### Data Looks Wrong
**Problem:** Numbers don't match expectations  
**Check:**
1. Verify you're looking at correct business (not switched to another)
2. Check date range (only last 14 days shown)
3. Remember costs are absolute values (shown as positive)
4. Commissions are net (after bonuses/penalties)

### Chart Empty But I Added Costs
**Problem:** Added costs but chart still empty  
**Check:**
1. Is cost date within last 14 days?
2. Is cost assigned to correct business?
3. Did you refresh the page after adding?

## Technical Details

### Data Sources
1. **WalletTransaction** model - for costs
   - Filters: `ledger=COMPANY`, `type=COST_ONCE_OFF` or `COST_RECURRING`
   - Date field: `effective_date`
   
2. **SaleCommission** model - for commissions
   - Date field: `created_at`
   - Amount field: `net_amount`

### Chart Library
- **Chart.js v4** (loaded from CDN)
- Client-side rendering (JavaScript)
- No server-side image generation

### Performance
- Query optimized with date range filters
- Aggregation done at database level (fast)
- Minimal data transfer (only 14 days)
- No impact on page load time

## Future Enhancements
Potential features (not yet implemented):
- [ ] Configurable date range (7/30/90 days)
- [ ] Export chart as PNG/PDF
- [ ] Download data as CSV
- [ ] Drill-down to see individual transactions
- [ ] Comparison with previous period
- [ ] Forecast/trend line
- [ ] Budget vs. actual overlay

## Support
For questions or issues:
1. Check this guide first
2. Review WALLET_SPEND_TREND_IMPLEMENTATION.md for technical details
3. Contact your system administrator
4. File a support ticket with screenshots

---

**Last Updated:** December 6, 2025  
**Version:** 1.0  
**Compatible With:** Circuit City / Emajinet Django SaaS Platform


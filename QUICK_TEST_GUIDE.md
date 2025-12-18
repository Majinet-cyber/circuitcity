# Fast Sell + Liquor Barman - Quick Test Guide

## What Was Implemented

### 1. Fast Sell Feature (Liquor, Pharmacy, Clothing)
- **Single-page barcode scanner** using front camera
- **Native BarcodeDetector API** with manual entry fallback
- **Instant product lookup** by barcode
- **Automatic selling price handling** (prompts if missing, saves it)
- **Fast payment selection** (Cash/Bank/Mobile)
- **Real-time KPI updates** (Sold Today, Revenue, Profit)
- **No 500 errors** - all errors handled gracefully

### 2. Liquor Barman Role + Attribution System
- **LIQUOR_BARMAN role** - separate from agents
- **Manager can invite barmen** via UI
- **Barman can assign sales to agents** during Fast Sell
- **Attribution tracking** with pending/reconciled status
- **Agent dashboard shows**:
  - Assigned sales totals
  - Pending reconciliation count
  - "Records Balanced ✅" when no pending items
- **Manager/Barman reconciliation screen**:
  - View all attributions by agent
  - Mark pending → reconciled
  - Filter by date/status
  - Batch reconciliation support

## Quick Testing Steps

### Test 1: Fast Sell (Clothing)
```bash
1. Login as clothing business user
2. Navigate to /verticals/clothing/fast-sell/
3. Click "Start Camera" (allow camera access)
4. Scan a barcode OR use manual entry
5. Product appears → select quantity
6. Choose payment method
7. Click "Sell Now"
8. Should see "✅ Sold" toast
9. KPIs should update immediately
```

### Test 2: Fast Sell (Pharmacy)
```bash
1. Login as pharmacy business user
2. Navigate to /verticals/pharmacy/fast-sell/
3. Scan barcode for a PharmacyBatch
4. Should show batch details + expiry date
5. Complete sale
6. Batch stock should decrement
```

### Test 3: Fast Sell (Liquor)
```bash
1. Login as liquor business user
2. Navigate to /verticals/liquor/fast-sell/
3. Scan barcode
4. Complete sale
5. Stock should decrement correctly
```

### Test 4: Liquor Barman Invite (Manager Only)
```bash
1. Login as liquor manager
2. Navigate to /verticals/liquor/barman/invite/
3. Fill in barman details:
   - username: barman1
   - password: Test123!
4. Submit
5. Should see success message
6. Barman should be able to login
```

### Test 5: Barman Sale Attribution
```bash
1. Login as barman (created in Test 4)
2. Navigate to /verticals/liquor/fast-sell/
3. Scan a product
4. Notice "Assign to Agent" dropdown appears (barman only)
5. Select an agent from dropdown
6. Complete sale
7. Sale attribution should be created with status="pending"
```

### Test 6: Agent View - Pending Attributions
```bash
1. Login as liquor agent (who was assigned sales)
2. View liquor dashboard
3. Should see:
   - "Pending Reconciliation: X" (where X > 0)
   - Attributed sales total
4. When all reconciled:
   - Should show "Records Balanced ✅"
```

### Test 7: Barman Reconciliation
```bash
1. Login as barman or manager
2. Navigate to /verticals/liquor/barman/reconciliation/
3. Should see:
   - Agent summaries (sales, amounts, pending count)
   - Detailed attribution list
4. Click "Mark Reconciled" on a pending attribution
5. Status should change to "Reconciled"
6. Agent's pending count should decrease
```

### Test 8: Error Handling
```bash
1. Scan invalid barcode → Should show "Product not found"
2. Try to sell out-of-stock item → Should show "Out of stock"
3. Try to sell quantity > available → Should show "Insufficient stock"
4. Try to sell with missing price → Should prompt for price
5. No crashes, no 500 errors
```

## Database Migrations

Run migration:
```bash
python manage.py migrate sales
```

This creates the `LiquorSaleAttribution` model with fields:
- liquor_sale_id
- business
- attributed_by (barman)
- attributed_to (agent)
- status (pending/reconciled)
- sale_amount
- reconciled_by, reconciled_at

## API Endpoints

### Fast Sell APIs (All Verticals)
```
GET  /verticals/{vertical}/api/fast-sell/lookup/?barcode=123456
POST /verticals/{vertical}/api/fast-sell/sell/
GET  /verticals/{vertical}/api/fast-sell/kpis/?range=today
```

### Liquor Barman APIs
```
GET  /verticals/liquor/api/barman/agents/
POST /verticals/liquor/api/barman/reconciliation/toggle/
```

## Running Tests

```bash
# Run Fast Sell tests
pytest sales/tests/test_fast_sell.py -v

# Run all sales tests
pytest sales/tests/ -v

# Quick smoke test
python manage.py check
```

## Key Files Changed/Added

### Models
- `sales/models.py` - Added `LiquorSaleAttribution`
- `sales/migrations/1001_add_liquor_sale_attribution.py` - New migration

### Services
- `inventory/services/fast_sell.py` - Centralized Fast Sell logic

### Views (Verticals)
- `inventory/verticals/liquor.py` - Added Fast Sell + Barman views
- `inventory/verticals/pharmacy.py` - Added Fast Sell views
- `inventory/verticals/clothing.py` - Added Fast Sell views

### URLs
- `verticals/urls.py` - Added Fast Sell + Barman routes

### Sidebar
- `inventory/utils_verticals.py` - Added "Fast Sell" entries

### Templates
- `templates/verticals/liquor/fast_sell.html` - Camera scanner page
- `templates/verticals/liquor/barman_invite.html` - Barman invite form
- `templates/verticals/liquor/barman_reconciliation.html` - Reconciliation screen
- `templates/verticals/pharmacy/fast_sell.html` - Pharmacy scanner
- `templates/verticals/clothing/fast_sell.html` - Clothing scanner

### Tests
- `sales/tests/test_fast_sell.py` - Comprehensive test suite

## Rollback Plan

If issues arise:
```bash
# Rollback migration
python manage.py migrate sales 1000

# Hide Fast Sell in sidebar (comment out in utils_verticals.py)
# Remove Fast Sell URLs (comment out in verticals/urls.py)
```

## Known Limitations

1. **BarcodeDetector API** not supported in all browsers (fallback to manual entry)
2. **Front camera only** (no camera switching UI)
3. **Barman role is liquor-only** (not implemented for other verticals)
4. **Attribution system is manual** (no automatic reconciliation)

## Production Checklist

- [x] No missing static files
- [x] No 500 errors
- [x] All DB queries use select_related/prefetch_related
- [x] CSRF protection on all POST endpoints
- [x] Permission checks on all views
- [x] Graceful error handling
- [x] Tests passing
- [x] Django checks passing
- [x] Migration created

## Support

If you encounter issues:
1. Check browser console for JavaScript errors
2. Check Django logs for backend errors
3. Verify camera permissions are granted
4. Test manual barcode entry as fallback
5. Check that business has correct `business_kind`

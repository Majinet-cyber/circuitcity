# Quick Test Guide: Phones Dashboard Fixes

## 🚀 Quick Start

```bash
# 1. Run automated tests
pytest inventory/tests/test_phones_agent_scoping.py -v

# 2. Start dev server
python manage.py runserver

# 3. Open browser to http://localhost:8000
```

---

## A) Test Custom Date Filter

### As Manager:
1. Login as manager (is_staff=True user)
2. Navigate to `/inventory/verticals/phones/`
3. Click **"Custom"** button in date range filter
   - ✅ Date inputs should appear immediately
4. Select start/end dates → Click **"Apply"**
   - ✅ Dashboard should reload with custom date range
5. Click **"Cancel"**
   - ✅ Date inputs should hide
6. Click browser **Back** button, then **Forward**
   - ✅ Custom button should still work (bfcache test)

### Edge Cases:
```
# Invalid dates (should fall back to MTD, not crash)
/inventory/verticals/phones/?range=custom&start=invalid&end=invalid

# Missing dates (should fall back to MTD)
/inventory/verticals/phones/?range=custom

# Valid custom range
/inventory/verticals/phones/?range=custom&start=2025-12-01&end=2025-12-17
```

---

## B) Test Agent Scoping

### Setup Test Data:

```python
# In Django shell: python manage.py shell
from django.contrib.auth import get_user_model
from inventory.models import InventoryItem, Product, Location
from tenants.models import Business, BusinessKind
from decimal import Decimal

User = get_user_model()

# Create test users
manager = User.objects.create_user(username='manager', password='test123', is_staff=True)
agent1 = User.objects.create_user(username='agent1', password='test123', is_staff=False)
agent2 = User.objects.create_user(username='agent2', password='test123', is_staff=False)

# Get/create business and location
business = Business.objects.filter(kind=BusinessKind.PHONES).first()
location = Location.objects.filter(business=business).first()
product = Product.objects.filter(business=business).first()

# Create sales for agent1 (2 sales, 120k revenue)
InventoryItem.objects.create(
    business=business,
    product=product,
    current_location=location,
    assigned_agent=agent1,
    status="SOLD",
    sold_at=timezone.now(),
    order_price=Decimal("50000"),
    selling_price=Decimal("60000"),
)

InventoryItem.objects.create(
    business=business,
    product=product,
    current_location=location,
    assigned_agent=agent1,
    status="SOLD",
    sold_at=timezone.now(),
    order_price=Decimal("50000"),
    selling_price=Decimal("60000"),
)

# Create sales for agent2 (1 sale, 80k revenue)
InventoryItem.objects.create(
    business=business,
    product=product,
    current_location=location,
    assigned_agent=agent2,
    status="SOLD",
    sold_at=timezone.now(),
    order_price=Decimal("70000"),
    selling_price=Decimal("80000"),
)

print("✅ Test data created!")
print(f"Agent1 should see: 2 units, MK 120,000")
print(f"Agent2 should see: 1 unit, MK 80,000")
print(f"Manager should see: 3 units, MK 200,000")
```

### Test Manager View:

1. Login as **manager** (username: manager, password: test123)
2. Navigate to `/inventory/verticals/phones/`
3. Check KPIs:
   - ✅ **Units Sold:** 3
   - ✅ **Revenue:** MK 200,000
   - ✅ **Stock on hand:** All agents' stock combined
4. Check top agents leaderboard:
   - ✅ Should show both agent1 and agent2

### Test Agent View:

1. Logout, login as **agent1** (username: agent1, password: test123)
2. Navigate to `/inventory/verticals/phones/`
3. Check KPIs:
   - ✅ **Units Sold:** 2 (only agent1's sales)
   - ✅ **Revenue:** MK 120,000 (only agent1's revenue)
   - ✅ **Stock on hand:** Only agent1's stock
4. Check top agents leaderboard:
   - ✅ Should still be visible (agents can see ranking)

5. Logout, login as **agent2** (username: agent2, password: test123)
6. Navigate to `/inventory/verticals/phones/`
7. Check KPIs:
   - ✅ **Units Sold:** 1 (only agent2's sales)
   - ✅ **Revenue:** MK 80,000 (only agent2's revenue)
   - ✅ **Stock on hand:** Only agent2's stock

---

## C) Test Mobile Overflow Protection

### Desktop Browser (Chrome DevTools):

1. Open `/inventory/verticals/phones/` as any user
2. Press **F12** → Toggle device toolbar (Ctrl+Shift+M)
3. Set device to:
   - **iPhone SE** (375px)
   - **Custom:** 360px width

### Test Scenarios:

**Dashboard KPI Cards:**
```
Navigate to: /inventory/verticals/phones/

✅ Check: Revenue card (e.g., "MK 1,234,567")
   - Number should truncate with "..." if too long
   - Hover → tooltip shows full value
   - No horizontal scroll

✅ Check: All KPI cards stack vertically (1 column)
✅ Check: No numbers break out of cards
```

**Agent Wallet:**
```
Navigate to: /wallet/agent_wallet/

✅ Check: "Month to Date" card
   - "MK 987,654" should truncate if needed
   - Hover → tooltip shows full value

✅ Check: Transaction table
   - Amount column uses responsive sizing
   - No horizontal scroll on table

✅ Check: All 4 KPI cards fit in viewport
```

**Agent Dashboard:**
```
Navigate to: /agent_dashboard/ (or wherever it's mounted)

✅ Check: "My Sales Value" card
   - "MK 1,500,000" should truncate if needed
   - Hover → tooltip shows full value

✅ Check: "My Commission" card
   - Large commission amounts don't overflow
```

### Mobile Devices (Real Testing):

**Test on actual devices if available:**
- [ ] iPhone SE (375px) - Safari
- [ ] Android phone (360px) - Chrome
- [ ] iPad (768px) - Safari
- [ ] Samsung Galaxy (414px) - Chrome

**Check:**
- No horizontal scroll
- All numbers readable
- Tooltips work on long-press (mobile)
- Cards stack properly (1 column on phone)

---

## D) Automated Tests

### Run Full Test Suite:

```bash
# All phones scoping tests
pytest inventory/tests/test_phones_agent_scoping.py -v

# Specific test categories
pytest inventory/tests/test_phones_agent_scoping.py::TestVisibilityScoping -v
pytest inventory/tests/test_phones_agent_scoping.py::TestStockScoping -v
pytest inventory/tests/test_phones_agent_scoping.py::TestSalesScoping -v
pytest inventory/tests/test_phones_agent_scoping.py::TestPhonesDashboardIntegration -v

# Run with coverage
pytest inventory/tests/test_phones_agent_scoping.py --cov=inventory.utils_scope --cov=inventory.verticals.phones --cov-report=html
```

### Expected Output:

```
================================ test session starts =================================
inventory/tests/test_phones_agent_scoping.py::TestVisibilityScoping::test_manager_visibility PASSED
inventory/tests/test_phones_agent_scoping.py::TestVisibilityScoping::test_agent_visibility PASSED
inventory/tests/test_phones_agent_scoping.py::TestVisibilityScoping::test_unauthenticated_visibility PASSED
inventory/tests/test_phones_agent_scoping.py::TestStockScoping::test_manager_sees_all_stock PASSED
inventory/tests/test_phones_agent_scoping.py::TestStockScoping::test_agent_sees_only_own_stock PASSED
inventory/tests/test_phones_agent_scoping.py::TestSalesScoping::test_manager_sees_all_sales PASSED
inventory/tests/test_phones_agent_scoping.py::TestSalesScoping::test_agent_sees_only_own_sales PASSED
inventory/tests/test_phones_agent_scoping.py::TestPhonesDashboardIntegration::test_dashboard_loads_for_manager PASSED
inventory/tests/test_phones_agent_scoping.py::TestPhonesDashboardIntegration::test_dashboard_loads_for_agent PASSED
inventory/tests/test_phones_agent_scoping.py::TestPhonesDashboardIntegration::test_custom_date_filter_with_valid_dates PASSED
inventory/tests/test_phones_agent_scoping.py::TestPhonesDashboardIntegration::test_custom_date_filter_with_invalid_dates PASSED
inventory/tests/test_phones_agent_scoping.py::TestPhonesDashboardIntegration::test_agent_kpis_show_only_own_data PASSED

================================ 12 passed in 2.34s ==================================
```

---

## E) Regression Testing

### Other Verticals (Should Be Unaffected):

```bash
# Quick smoke test on other verticals
# Navigate to each and verify no errors:

✅ Clothing: /inventory/verticals/clothing/
✅ Liquor: /inventory/verticals/liquor/
✅ Pharmacy: /inventory/verticals/pharmacy/
✅ Gym: /inventory/verticals/gym/

# Check:
- Pages load without errors
- Date filters still work
- KPIs display correctly
- No console errors
```

---

## F) Performance Testing

### Check Query Count:

```python
# In Django shell with debug toolbar
from django.test.utils import override_settings
from django.db import connection
from django.test import RequestFactory
from inventory.verticals.phones import dashboard

@override_settings(DEBUG=True)
def test_query_count():
    factory = RequestFactory()
    request = factory.get('/inventory/verticals/phones/')
    request.user = User.objects.get(username='manager')
    request.business = Business.objects.filter(kind=BusinessKind.PHONES).first()
    
    with connection.queries as queries:
        dashboard(request)
    
    print(f"Query count: {len(queries)}")
    for i, q in enumerate(queries, 1):
        print(f"{i}. {q['sql'][:100]}...")
    
    # Should be < 15 queries (ideally < 10)
    assert len(queries) < 15, f"Too many queries: {len(queries)}"

test_query_count()
```

---

## G) Browser Compatibility

### Test in Multiple Browsers:

- [ ] **Chrome** (latest) - Desktop + Mobile
- [ ] **Firefox** (latest) - Desktop + Mobile
- [ ] **Safari** (latest) - Desktop + Mobile (iOS)
- [ ] **Edge** (latest) - Desktop
- [ ] **Safari iOS** (iPhone)
- [ ] **Chrome Android** (Samsung/Pixel)

### Check:
- Custom date filter works (all events fire correctly)
- Date picker appears (native browser date input)
- Mobile overflow protection applied
- No console errors

---

## ✅ Final Acceptance Checklist

### Custom Date Filter:
- [ ] Opens on first click (no delay)
- [ ] Works after browser back/forward
- [ ] Works with HTMX partial updates (if applicable)
- [ ] Invalid dates fall back to MTD (no crash)
- [ ] Date picker visible and focusable

### Agent Scoping:
- [ ] Managers see global totals (all agents)
- [ ] Agents see only their own totals
- [ ] Agent leaderboard visible to agents
- [ ] Stock counts match expected values
- [ ] Sales revenue matches expected values

### Mobile Overflow:
- [ ] No horizontal scroll on 360px screens
- [ ] KPI values never overflow cards
- [ ] Tooltips show full values
- [ ] Wallet page safe on mobile
- [ ] Agent dashboard safe on mobile

### Tests:
- [ ] All automated tests pass
- [ ] No regressions in other verticals
- [ ] No linting errors
- [ ] Performance acceptable (< 15 queries)

### Documentation:
- [ ] Implementation summary written
- [ ] Test guide complete
- [ ] Deployment checklist ready

---

## 🐛 Common Issues

### Issue: Custom filter doesn't open

**Cause:** JavaScript not initialized  
**Fix:** Check browser console for errors, ensure IDs match

### Issue: Agent sees other agents' data

**Cause:** `is_staff` flag incorrect  
**Fix:** Verify user.is_staff=False for agents

### Issue: Numbers still overflow on mobile

**Cause:** `cc-amount` class not applied  
**Fix:** Add `cc-amount` class + `title` attribute to all amounts

### Issue: Tests fail with "Business not found"

**Cause:** Test fixtures incomplete  
**Fix:** Ensure business with `kind=PHONES` exists in test DB

---

## 📞 Support

If issues persist after following this guide:

1. Check `PHONES_AGENT_SCOPING_AND_CUSTOM_FILTER_FIX.md` for detailed implementation notes
2. Review test output for specific failures
3. Check browser console for JavaScript errors
4. Verify database has correct test data

---

**Last Updated:** December 17, 2025  
**Version:** 1.0

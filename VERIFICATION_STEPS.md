# Verification Steps

## Prerequisites
```bash
# 1. Apply migrations
python manage.py makemigrations inventory
python manage.py migrate inventory

# 2. Verify migrations are applied
python manage.py showmigrations inventory
# Look for [X] next to 0031 and 0037

# 3. Run Django checks
python manage.py check

# 4. (Optional) Run tests
python manage.py test inventory.tests.test_verticals_liquor
```

---

## Feature 1: Editable Liquor Stock Targets

### Test 1.1: View Stock Overview
1. Navigate to: `http://localhost:8000/liquor/stock/`
2. **Expected**: Page loads without errors
3. **Expected**: See category batteries (Beer, Cider, Spirits, Wine, etc.)
4. **Expected**: Each battery shows:
   - Current stock / Target bottles
   - Percentage bar (green/yellow/red)
   - SKU count
   - Days in stock

### Test 1.2: Edit Category Target (Manager Only)
1. Log in as a **manager** user
2. Navigate to: `http://localhost:8000/liquor/stock/`
3. **Expected**: See "Edit" button next to each category target
4. Click "Edit" button on Beer category
5. **Expected**: Modal opens with current target pre-filled
6. Change target from 600 to 800
7. Click "Update Target"
8. **Expected**: 
   - Modal closes
   - Page reloads
   - Beer target now shows "800 bottles"
   - Percentage recalculated based on new target
9. Check browser console: **No JavaScript errors**
10. Check Django logs: **No Python errors**

### Test 1.3: Edit Target Validation
1. Click "Edit" on any category
2. Enter negative number (e.g., -50)
3. Try to submit
4. **Expected**: Browser validation prevents submission
5. Enter valid number (e.g., 500)
6. Submit
7. **Expected**: Success

### Test 1.4: Auto-Adjust Targets
1. As manager, navigate to: `http://localhost:8000/liquor/stock/`
2. Click "Auto-Adjust Targets" button
3. **Expected**: One of:
   - Success message: "Auto-adjusted targets for N product(s) based on recent sales data."
   - Info message: "No products required target adjustment at this time."
4. **Expected**: No errors in logs
5. Check database:
   ```sql
   SELECT name, target_bottles, auto_adjust_enabled, auto_adjust_pct 
   FROM inventory_merchproduct 
   WHERE kind = 'liquor' AND is_active = TRUE;
   ```
6. **Expected**: Products with `auto_adjust_enabled=True` have updated `target_bottles`

### Test 1.5: Multi-Tenant Isolation
1. Switch to Business A
2. Set Beer target to 500
3. Switch to Business B
4. **Expected**: Beer target is different (not 500)
5. Set Beer target to 700 for Business B
6. Switch back to Business A
7. **Expected**: Beer target is still 500
8. **Expected**: No data leakage between businesses

---

## Feature 2: Active Tab Fix

### Test 2.1: Liquor Inventory Dashboard
1. Navigate to: `http://localhost:8000/liquor/inventory/`
2. **Expected**: Page loads without errors
3. **Expected**: See inventory dashboard with:
   - Total SKUs
   - Total Bottles
   - Out of Stock count
   - Category batteries
4. Check Django logs: **No `active_tab` errors**
5. Check browser console: **No JavaScript errors**

### Test 2.2: Template Robustness
1. Open Django shell:
   ```bash
   python manage.py shell
   ```
2. Test template rendering:
   ```python
   from django.template import Template, Context
   from django.test import RequestFactory
   from inventory.views_liquor_inventory import liquor_inventory_dashboard
   
   # Create a mock request
   factory = RequestFactory()
   request = factory.get('/liquor/inventory/')
   
   # Test that template handles missing active_tab
   template = Template("{% with tab=active_tab|default:'inventory' %}{{ tab }}{% endwith %}")
   context = Context({})  # No active_tab
   result = template.render(context)
   print(result)  # Should print: inventory
   ```
3. **Expected**: No errors, prints "inventory"

---

## Feature 3: Warranty Expiration Fix

### Test 3.1: Database Schema
1. Check database schema:
   ```bash
   python manage.py dbshell
   ```
2. Run SQL:
   ```sql
   PRAGMA table_info(inventory_inventoryitem);
   ```
3. **Expected**: See `warranty_expiration` column in output
4. **Expected**: Column type is DATE, nullable

### Test 3.2: Stock List View
1. Navigate to: `http://localhost:8000/inventory/list/`
2. **Expected**: Page loads without errors
3. **Expected**: See list of inventory items
4. Check Django logs: **No `warranty_expiration` column errors**

### Test 3.3: Stock List with Filters
1. Navigate to: `http://localhost:8000/inventory/list/?category=spirits`
2. **Expected**: Page loads, filtered by spirits
3. Navigate to: `http://localhost:8000/inventory/list/?status=sold`
4. **Expected**: Page loads, showing sold items
5. **Expected**: No database errors in logs

### Test 3.4: Warranty Field Access
1. Open Django shell:
   ```bash
   python manage.py shell
   ```
2. Test field access:
   ```python
   from inventory.models import InventoryItem
   
   # Get first item
   item = InventoryItem.objects.first()
   
   # Access warranty_expiration
   print(item.warranty_expiration)  # Should work, may be None
   
   # Set warranty_expiration
   from datetime import date, timedelta
   item.warranty_expiration = date.today() + timedelta(days=365)
   item.save()
   
   # Verify
   item.refresh_from_db()
   print(item.warranty_expiration)  # Should print the date
   ```
3. **Expected**: No errors, field accessible

---

## Integration Tests

### Test I.1: Full Liquor Workflow
1. Log in as manager
2. Navigate to liquor dashboard: `/liquor/`
3. Click "Stock Overview"
4. Edit Beer target to 1000
5. Click "Auto-Adjust Targets"
6. Navigate to "Inventory Hub"
7. **Expected**: All pages load without errors
8. **Expected**: Data is consistent across pages

### Test I.2: Bartender Permissions
1. Log in as bartender (non-manager)
2. Navigate to: `/liquor/stock/`
3. **Expected**: No "Edit" buttons visible
4. Try to access: `/liquor/stock/category/beer/update-target/` (POST)
5. **Expected**: 403 Forbidden or redirect to login

### Test I.3: API Endpoint Security
1. Open browser DevTools > Network tab
2. As manager, edit a category target
3. Inspect the POST request to `/liquor/stock/category/beer/update-target/`
4. **Expected**: CSRF token present in headers
5. Try to replay request without CSRF token
6. **Expected**: 403 Forbidden

---

## Performance Tests

### Test P.1: Stock Overview Load Time
1. Navigate to: `/liquor/stock/`
2. Open DevTools > Network tab
3. Reload page
4. **Expected**: Page loads in < 2 seconds
5. Check Django Debug Toolbar (if installed):
   - SQL queries: < 20 queries
   - No N+1 query issues

### Test P.2: Auto-Adjust Performance
1. Create 100+ liquor products (use Django shell or admin)
2. Click "Auto-Adjust Targets"
3. **Expected**: Completes in < 10 seconds
4. Check logs for query count
5. **Expected**: Reasonable number of queries (not 100+)

---

## Error Handling Tests

### Test E.1: Invalid Category
1. Try to access: `/liquor/stock/category/invalid/update-target/`
2. **Expected**: 400 Bad Request with error message

### Test E.2: Invalid Target Value
1. Edit category target
2. Use browser DevTools to bypass client-side validation
3. Submit negative value
4. **Expected**: 400 Bad Request with error message

### Test E.3: Missing Business
1. Log out
2. Try to access: `/liquor/stock/`
3. **Expected**: Redirect to login or business selection

---

## Browser Compatibility

Test in multiple browsers:
- [ ] Chrome/Edge (Chromium)
- [ ] Firefox
- [ ] Safari (if available)

For each browser:
1. Navigate to `/liquor/stock/`
2. Edit a category target
3. **Expected**: Modal opens and closes correctly
4. **Expected**: AJAX submission works
5. **Expected**: No console errors

---

## Mobile Responsiveness

Test on mobile devices or browser DevTools mobile emulation:
1. Navigate to `/liquor/stock/`
2. **Expected**: Batteries stack vertically on small screens
3. Click "Edit" button
4. **Expected**: Modal is readable and usable
5. Submit form
6. **Expected**: Works correctly

---

## Regression Tests

Ensure existing functionality still works:

### R.1: Liquor Sales
1. Navigate to: `/liquor/sell/`
2. Record a sale
3. **Expected**: Sale recorded successfully
4. Check stock overview
5. **Expected**: Stock levels updated

### R.2: Liquor Credits
1. Navigate to: `/liquor/credits/`
2. Create a credit
3. Submit payment
4. **Expected**: Credit workflow works

### R.3: Liquor Shifts
1. Start a shift
2. Record sales
3. Close shift
4. **Expected**: Shift workflow works

---

## Cleanup

After testing, you may want to:
1. Reset test data:
   ```bash
   python manage.py flush --noinput
   python manage.py loaddata initial_data.json
   ```
2. Reset migrations (if needed):
   ```bash
   python manage.py migrate inventory zero
   python manage.py migrate inventory
   ```

---

## Success Criteria

All three features are working if:
- ✅ Stock overview loads without errors
- ✅ Category targets can be edited via UI
- ✅ Auto-adjust updates targets based on sales
- ✅ Liquor inventory dashboard loads without `active_tab` errors
- ✅ Stock list loads without `warranty_expiration` errors
- ✅ All existing liquor functionality still works
- ✅ Multi-tenant isolation is maintained
- ✅ No security vulnerabilities introduced

---

## Troubleshooting

### Issue: "No such column: warranty_expiration"
**Solution**: Run migrations:
```bash
python manage.py migrate inventory
```

### Issue: "active_tab not found in context"
**Solution**: Check that view passes `active_tab` in context dict (line 159 of `views_liquor_inventory.py`)

### Issue: "Edit button not visible"
**Solution**: Ensure user is logged in as manager, check `is_manager` function

### Issue: "AJAX request fails with 403"
**Solution**: Check CSRF token is present in request headers

### Issue: "Targets not updating"
**Solution**: Check browser console for JavaScript errors, verify URL pattern is correct

---

## Reporting Issues

If you encounter issues, please provide:
1. Django version: `python manage.py version`
2. Python version: `python --version`
3. Database: SQLite/PostgreSQL/MySQL
4. Browser and version
5. Full error traceback from Django logs
6. Steps to reproduce
7. Expected vs. actual behavior


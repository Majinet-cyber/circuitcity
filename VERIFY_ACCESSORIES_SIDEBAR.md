# Verification Guide: Accessories Sidebar Fix

## Quick Verification Steps

### 1. Visual Inspection (Manual Test)

```bash
# Start the Django development server
python manage.py runserver
```

Then visit these URLs and verify the sidebar contains "Accessories" and "Stock In Accessories":

1. **http://localhost:8000/inventory/scan-in/** (Scan IN page)
   - ✅ Should see "Accessories" in MAIN section
   - ✅ Should see "Stock In Accessories" in MAIN section

2. **http://localhost:8000/inventory/verticals/phones/** (Phones Dashboard)
   - ✅ Should see "Accessories" in MAIN section
   - ✅ Should see "Stock In Accessories" in MAIN section

3. **http://localhost:8000/inventory/phone-sale-wizard/** (Scan & Sell)
   - ✅ Should see "Accessories" in MAIN section
   - ✅ Should see "Stock In Accessories" in MAIN section

4. **http://localhost:8000/inventory/list/** (Stock)
   - ✅ Should see "Accessories" in MAIN section
   - ✅ Should see "Stock In Accessories" in MAIN section

### 2. Check HTML Selectors (Browser DevTools)

Open browser DevTools (F12) and run:

```javascript
// Should find the Accessories link
document.querySelector('[data-testid="nav-phones-accessories"]')
// Should return: <a class="navlink" href="/verticals/phones/accessories/" ...>

// Should find the Stock In Accessories link
document.querySelector('[data-testid="nav-phones-accessories-stockin"]')
// Should return: <a class="navlink" href="/verticals/phones/accessories/stock-in/" ...>
```

Both should return valid anchor elements, not `null`.

### 3. Click Test (Manual)

1. Login as manager or agent
2. Navigate to `/inventory/scan-in/`
3. Click **"Accessories"** in the sidebar
   - ✅ Should navigate to `/verticals/phones/accessories/`
   - ✅ Should load accessories dashboard without 500 error
4. Click **"Stock In Accessories"** in the sidebar
   - ✅ Should navigate to `/verticals/phones/accessories/stock-in/`
   - ✅ Should load accessories stock-in wizard without 500 error

### 4. Automated Tests (Cypress)

```bash
# Run sidebar smoke test
npx cypress run --spec "cypress/e2e/sidebar_smoke.cy.js"
# Expected: ✅ PASS (no 500 errors, accessories items found and clicked)

# Run accessories smoke test
npx cypress run --spec "cypress/e2e/accessories_smoke.cy.js"
# Expected: ✅ PASS (accessories links clickable, flows work)
```

### 5. Python Unit Test (Django Shell)

```bash
python manage.py shell
```

```python
from inventory.utils_verticals import get_vertical_sidebar_items

# Get phones sidebar items
items = get_vertical_sidebar_items("phones")

# Find accessories items
accessories = [item for item in items if item['key'] == 'accessories']
stockin = [item for item in items if item['key'] == 'accessories_stock_in']

# Verify accessories item
assert len(accessories) == 1, "Should have exactly 1 accessories item"
acc = accessories[0]
assert acc['label'] == 'Accessories'
assert acc['section'] == 'MAIN'
assert acc['url'] == 'verticals:phones_accessories_dashboard'
assert acc['testid'] == 'nav-phones-accessories'
print("✅ Accessories item configured correctly")

# Verify stock-in item
assert len(stockin) == 1, "Should have exactly 1 stock-in accessories item"
sto = stockin[0]
assert sto['label'] == 'Stock In Accessories'
assert sto['section'] == 'MAIN'
assert sto['url'] == 'verticals:phones_accessories_stock_in'
assert sto['testid'] == 'nav-phones-accessories-stockin'
print("✅ Stock In Accessories item configured correctly")

print("\n✅ ALL CHECKS PASSED - Accessories sidebar items are properly configured!")
```

Expected output:
```
✅ Accessories item configured correctly
✅ Stock In Accessories item configured correctly

✅ ALL CHECKS PASSED - Accessories sidebar items are properly configured!
```

## Troubleshooting

### Issue: Items not appearing in sidebar

**Check 1:** Verify you're on a Phones page
```python
# In Django shell
from tenants.models import Business
from inventory.utils_verticals import get_vertical_kind

biz = Business.objects.first()
print(get_vertical_kind(biz))
# Should print: "phones"
```

**Check 2:** Verify URL names exist
```bash
python manage.py show_urls | grep accessories
```
Should show:
```
/verticals/phones/accessories/                                phones_accessories_dashboard
/verticals/phones/accessories/stock-in/                       phones_accessories_stock_in
```

**Check 3:** Check context processor is loaded
In `settings.py`, verify `tenants.context_processors.business_context` is in `TEMPLATES['OPTIONS']['context_processors']`.

### Issue: Cypress tests failing

**Check selectors in browser:**
```javascript
// Verify both selectors exist
console.log(document.querySelector('[data-testid="nav-phones-accessories"]'));
console.log(document.querySelector('[data-testid="nav-phones-accessories-stockin"]'));
```

Both should return anchor elements. If `null`, check that:
1. You're logged in as a user with business access
2. The business kind is "phones"
3. The sidebar template is being used (not a custom layout)

### Issue: 500 errors when clicking links

**Check URL routing:**
```bash
python manage.py shell
```
```python
from django.urls import reverse
print(reverse('verticals:phones_accessories_dashboard'))
# Should print: /verticals/phones/accessories/

print(reverse('verticals:phones_accessories_stock_in'))
# Should print: /verticals/phones/accessories/stock-in/
```

If `NoReverseMatch` error, check that:
1. `verticals/urls.py` has the URL patterns defined
2. `inventory/verticals/phones.py` exports the view functions
3. `inventory/verticals/phones_accessories.py` exists and has the views

## Success Criteria Checklist

- [ ] Accessories appears in sidebar on all Phones pages
- [ ] Stock In Accessories appears in sidebar on all Phones pages
- [ ] Both items have correct `data-testid` attributes
- [ ] Both items are visible to Admin AND Agents (no require_manager flag)
- [ ] Clicking Accessories loads `/verticals/phones/accessories/` without errors
- [ ] Clicking Stock In Accessories loads `/verticals/phones/accessories/stock-in/` without errors
- [ ] Items appear in MAIN section (with Dashboard, Analytics, Stock, etc.)
- [ ] Items do NOT appear in other verticals (Gym, Liquor, etc.)
- [ ] Cypress sidebar_smoke.cy.js passes
- [ ] Cypress accessories_smoke.cy.js passes

## Files Changed (for rollback if needed)

1. `inventory/utils_verticals.py` (lines 352-353)
2. `templates/partials/sidebar.html` (multiple lines - added data-testid attributes)
3. `cypress/e2e/sidebar_smoke.cy.js` (added explicit assertions)
4. `ACCESSORIES_SIDEBAR_FIX.md` (this summary doc)
5. `VERIFY_ACCESSORIES_SIDEBAR.md` (this verification guide)


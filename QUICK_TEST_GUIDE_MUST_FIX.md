# Quick Test Guide: MUST FIX Issues

**Fast manual testing guide for all 3 fixes**

---

## 🛡️ MUST FIX 1: CSRF Fix

### Test 1: Sale Wizard CSRF Cookie
```bash
# 1. Login as agent/manager
# 2. Navigate to phone sale wizard
# 3. Open DevTools > Application > Cookies
# 4. Verify "cc_csrftoken" cookie exists
```

**Expected**: ✅ Cookie is set on GET request

### Test 2: POST Request Works
```bash
# 1. Complete a sale through wizard
# 2. Fill out all steps and submit final form
# 3. Check response
```

**Expected**: ✅ No 403 CSRF error, sale completes successfully

### Test 3: Branded CSRF Failure Page
```python
# Simulate CSRF failure in Django shell
from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()
client = Client()
user = User.objects.first()
client.force_login(user)

# Try POST without CSRF token
response = client.post('/inventory/phone-sale-wizard/', {'test': 'data'})
print(response.status_code)  # Should be 403
print(b"Security Check Failed" in response.content)  # Should be True
```

**Expected**: ✅ Branded page shown, not Django debug screen

---

## 🎨 MUST FIX 2: Clothing Fast Sell Fix

### Test 1: Fast Sell Loads (200 not 500)
```bash
# 1. Login as agent with clothing business
# 2. Navigate to /verticals/clothing/fast-sell/
# 3. Check page loads without errors
```

**Expected**: ✅ Page returns 200, no 500 error

### Test 2: Complete a Sale
```bash
# 1. On fast sell page, click "Open Barcode Scanner"
# 2. Scan a barcode (or manually enter product)
# 3. Select quantity and payment method
# 4. Click "Complete Sale"
```

**Expected**: ✅ Sale completes, KPIs update, no template errors

### Test 3: Payment Mix Bar Renders
```bash
# 1. On fast sell page, after product is scanned
# 2. Verify payment method selector appears
# 3. Try switching between Single Method and Payment Mix
```

**Expected**: ✅ Payment bar renders without VariableDoesNotExist errors

---

## 📂 MUST FIX 3: Sidebar "More" Section

### Test 1: Manager Sees "More" Section
```bash
# 1. Login as MANAGER
# 2. Check sidebar
# 3. Look for "More" section with chevron icon
# 4. Click to expand
```

**Expected**: 
- ✅ "More" section visible
- ✅ Expands smoothly (Bootstrap collapse)
- ✅ Chevron rotates 180° on expand
- ✅ Contains: Reports, Products, Admin Wallet, Costs, Simulator, Agents, Locations, Data Backup, Choose Plan, Orders

### Test 2: Agent Does NOT See Manager-Only Items
```bash
# 1. Login as AGENT (not manager)
# 2. Check sidebar
# 3. Expand "More" section (if visible)
```

**Expected**:
- ✅ Agent sees "More" section BUT
- ✅ Manager-only items are HIDDEN (Reports, Admin Wallet, Costs, etc)
- ✅ OR "More" section is completely hidden

### Test 3: Main Sidebar is Clean
```bash
# 1. Check MAIN section items
# 2. Count visible items (before "More")
```

**Expected**:
- ✅ MAIN section: ~5-6 items (Dashboard, Analytics, Stock, Scan IN, Scan & Sell, Time Logs)
- ✅ Not button-heavy (previously had 10+ items)

### Test 4: Active Highlighting Still Works
```bash
# 1. Navigate to different pages (Dashboard, Stock, etc)
# 2. Check sidebar highlights active page
```

**Expected**: ✅ Active page is highlighted correctly

### Test 5: Mobile Nav Unaffected
```bash
# 1. Resize browser to mobile width (<768px)
# 2. Check mobile bottom nav bar
# 3. Verify all links work
```

**Expected**: ✅ Mobile nav unchanged, no regressions

---

## 🧪 Run Automated Tests

```bash
# Run all MUST FIX tests
python manage.py test tests.test_must_fix_issues --verbosity=2

# Run specific test class
python manage.py test tests.test_must_fix_issues.CSRFFailureViewTests -v2
python manage.py test tests.test_must_fix_issues.ClothingFastSellTests -v2
python manage.py test tests.test_must_fix_issues.SidebarMoreGatingTests -v2
```

**Expected**: All 10 tests pass ✅

---

## 🚀 Production Smoke Test Checklist

Before deploying to production, verify:

### CSRF
- [ ] Sale wizard loads without errors
- [ ] CSRF cookie is set on GET
- [ ] POST requests work (complete a sale)
- [ ] If CSRF fails, branded page is shown (not Django debug)

### Clothing Fast Sell
- [ ] Fast sell page returns 200 (not 500)
- [ ] Can complete a sale
- [ ] Payment mix bar renders
- [ ] No console errors

### Sidebar
- [ ] "More" section appears for managers
- [ ] Expands/collapses smoothly
- [ ] Reports is inside "More"
- [ ] Agents don't see manager-only items
- [ ] Main sidebar feels clean (not button-heavy)
- [ ] Active highlighting works
- [ ] Mobile nav unaffected

---

## 🐛 Troubleshooting

### CSRF Issues
**Problem**: Still getting 403 CSRF errors  
**Solution**: 
1. Check `@ensure_csrf_cookie` decorator is on GET views
2. Verify `{% csrf_token %}` in all POST forms
3. Check browser cookies (should see `cc_csrftoken`)
4. Verify `CSRF_TRUSTED_ORIGINS` includes your domain

### Clothing Fast Sell 500
**Problem**: Still getting 500 error  
**Solution**:
1. Check Django logs for exact error
2. Verify `base.base_context(request)` is being called
3. Check all partials used in template have required context variables
4. Add more defensive `ctx.setdefault()` calls

### Sidebar "More" Not Showing
**Problem**: "More" section not visible  
**Solution**:
1. Check `get_vertical_sidebar_items()` returns items with `section="MORE"`
2. Verify items have `group="more"` field
3. Check template loops through sections correctly
4. Inspect HTML for `id="sidebarMore"` element

### Sidebar "More" Not Collapsing
**Problem**: "More" section doesn't collapse/expand  
**Solution**:
1. Verify Bootstrap JS is loaded
2. Check console for JS errors
3. Verify `data-bs-toggle="collapse"` and `data-bs-target="#sidebarMore"` attributes
4. Check Bootstrap version (should be 5.x)

---

## 📊 Success Criteria

### CSRF Fix
- ✅ Zero 403 CSRF errors on sale wizard
- ✅ Branded error page if CSRF fails
- ✅ Technical details hidden in production

### Clothing Fast Sell
- ✅ Returns 200 (not 500)
- ✅ Can complete sales
- ✅ No template errors

### Sidebar
- ✅ Main sidebar: 5-6 items (clean)
- ✅ "More" section: 10 manager tools
- ✅ Smooth collapse animation
- ✅ Agents don't see manager items

---

**All tests passing? Deploy to production! 🚀**


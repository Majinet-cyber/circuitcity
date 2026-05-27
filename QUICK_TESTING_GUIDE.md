# Quick Testing Guide - Circuit City Restoration

## 🚀 Quick Test (5 Minutes)

### 1. Liquor Stock Gating (2 min)
```
1. Login → Go to Liquor → Sell
2. Select any category (Beer, Wine, etc.)
3. Look for products with "Out of Stock" badge
4. Try clicking out-of-stock product → Should see alert
5. Select in-stock product → Complete sale
6. Refresh page → Stock should be reduced
✅ PASS if out-of-stock products cannot be sold
```

### 2. Credit Sales (2 min)
```
1. Go to Liquor → Sell
2. Select product and quantity
3. Change "Payment Type" to "Credit Sale"
4. Enter customer name: "Test Customer"
5. Submit sale
6. Go to Liquor → Credits
7. Verify "Test Customer" appears in list
8. Dashboard → Revenue should NOT include this amount yet
✅ PASS if credit appears but revenue unchanged
```

### 3. Credit Clearing (1 min)
```
1. Go to Liquor → Credits
2. Find "Test Customer" credit
3. Click "Clear" button
4. Confirm in modal
5. Go to Dashboard
6. Revenue should now include the cleared amount
✅ PASS if revenue increases after clearing
```

---

## 🎨 Visual Checks (2 Minutes)

### Home Page
```
1. Go to Dashboard home
2. Resize browser to narrow width
3. Check for horizontal scroll bar
✅ PASS if no horizontal scroll
```

### Clothing Dashboard
```
1. Go to Clothing → Dashboard
2. Scroll to "Recent Sales" section
3. Should see bar chart (not list)
✅ PASS if bar chart displays
```

### Debug Labels
```
1. Visit Liquor → Scan In
2. Visit Clothing → Scan In
3. Should see NO green "WIZARD ACTIVE" banners
✅ PASS if no debug banners visible
```

---

## ⚠️ Known Limitations

- **Phones Wizard:** Not implemented (deferred to Phase 2)
- **Barcode Scanner:** Not implemented (deferred to Phase 2)
- **Shot Sales:** Stock tracking for shots not yet implemented (bottles only)

---

## 🐛 If Something Breaks

### Liquor Sell Not Working
- Check: Is product in stock? (quantity_in_stock > 0)
- Check: Browser console for JavaScript errors
- Check: Server logs for Python errors

### Credit Not Appearing
- Check: Customer name was entered
- Check: Sale type was set to "Credit"
- Check: Business/location scope correct

### Revenue Not Updating After Clear
- Check: User has manager role
- Check: Credit status changed to "SETTLED"
- Check: Wallet entry created
- Try: Refresh dashboard page

---

## 📊 Success Metrics

After deployment, verify:
- [ ] 0 stock items cannot be sold (100% enforcement)
- [ ] Credit sales tracked separately from revenue
- [ ] Analytics page loads in < 2 seconds
- [ ] No horizontal scroll on any page
- [ ] No debug banners visible

---

**Total Testing Time:** ~10 minutes  
**Critical Tests:** 3  
**Visual Checks:** 3  
**Risk Level:** LOW


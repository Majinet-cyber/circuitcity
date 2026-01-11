# Cement Fixes — Quick Reference Card

## ✅ What Was Fixed

| Issue | Fix | Files Changed |
|-------|-----|---------------|
| **NoReverseMatch crash** | Fixed 18 redirect calls to use `reverse()` + querystring | `inventory/verticals/cement.py` |
| **Missing Stock button** | Added Stock button to sidebar config | `inventory/utils_verticals.py` |
| **Paint duplicates** | Implemented variation grouping (Paint 1L/4L/20L → "Paint" + size picker) | `inventory/utils_product_variations.py`<br>`inventory/verticals/cement.py`<br>`templates/verticals/cement/stock_in.html` |

---

## 🧪 Run Tests

```bash
python manage.py test tests.test_cement_fixes --verbosity=2
```

**Expected:** All tests pass ✅

---

## 🔗 URLs to Test

| Feature | URL | Expected |
|---------|-----|----------|
| Dashboard | `/verticals/cement/dashboard/` | Shows sidebar with Stock In/Sell/Stock/Costs |
| Stock In | `/cement/stock-in/` | 3-step flow works, no crashes |
| Sell | `/cement/sell/` | 3-step flow works, no crashes |
| Stock List | `/cement/stock/` | Shows all products |
| Costs | `/cement/costs/` | Shows cost list + add form |
| Analytics | `/cement/analytics/` | Shows analytics dashboard |

---

## 📋 Sidebar Items (Cement Vertical)

**MAIN Section:**
1. Dashboard
2. Stock In
3. Sell
4. **Stock** ← NEWLY ADDED
5. Costs
6. Admin Wallet (manager-only)
7. Analytics
8. Locations (manager-only)

**Mobile Nav (Bottom Bar):**
- Home
- Stock In
- Sell
- Products
- More

---

## 🎨 Paint Variation UI

**Before Fix:**
```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ Paint 1L    │  │ Paint 4L    │  │ Paint 20L   │  ← 3 separate cards
└─────────────┘  └─────────────┘  └─────────────┘
```

**After Fix:**
```
┌─────────────────────┐
│  Paint              │  ← Single card
│  🏷️ 3 sizes         │
│  Click to choose    │
└─────────────────────┘
         ↓ (click)
┌─────────────────────────────────────┐
│  Choose Paint Size:                 │
│  ┌─────┐  ┌─────┐  ┌──────┐       │
│  │ 1L  │  │ 4L  │  │ 20L  │       │  ← Unique sizes only
│  └─────┘  └─────┘  └──────┘       │
│  ← Back                             │
└─────────────────────────────────────┘
```

---

## 🔧 How Variation Grouping Works

1. **Extract Base Name:**
   - "Paint 1L" → "Paint"
   - "Paint 4L" → "Paint"
   - "Dangote Cement 50kg" → "Dangote Cement"

2. **Group Products:**
   ```python
   grouped = group_products_by_base_name(products)
   # {"Paint": [paint_1l, paint_4l, paint_20l]}
   ```

3. **Show Unique Variations:**
   - Uses `spec_label` field (e.g., "1L", "4L")
   - Falls back to extracting from name
   - Removes duplicates
   - Sorts numerically

---

## 💡 Adding New Size-Based Products

**Example: Adding Nails (2inch, 4inch, 6inch)**

1. **Create Products with spec_label:**
   ```python
   MerchProduct.objects.create(
       business=business,
       name="Nails 2inch",
       spec_label="2inch",  # ← Important!
       kind=BusinessKind.CEMENT,
   )
   ```

2. **Automatic Grouping:**
   - System detects "Nails" as base name
   - Groups all "Nails Xinch" products
   - Shows single "Nails" card with size picker

3. **No Code Changes Needed:**
   - Variation utilities work automatically
   - Template handles grouping
   - Just set `spec_label` correctly

---

## 🚨 Important Notes

1. **Always use `reverse()` for redirects with querystrings:**
   ```python
   # ❌ WRONG
   return redirect("cement:stock_in?step=2")
   
   # ✅ CORRECT
   return redirect(f"{reverse('cement:stock_in')}?step=2")
   ```

2. **Set `spec_label` for size-based products:**
   ```python
   product.spec_label = "1L"  # Not "1 Litre" or "1L Paint"
   ```

3. **Variation grouping requires consistent naming:**
   - "Paint 1L", "Paint 4L" ✅
   - "1L Paint", "4L Paint" ✅
   - "Paint (1 Litre)", "Paint (4 Litres)" ❌ (won't group)

---

## 📞 Troubleshooting

### Issue: Sidebar buttons not showing
**Solution:** Check business `business_kind` field = "cement" (exact lowercase)

### Issue: Paint still shows as duplicates
**Solution:** Ensure products have `spec_label` set or size in name ("Paint 1L")

### Issue: NoReverseMatch still happening
**Solution:** Check all redirects use `reverse()` pattern, not string concatenation

---

**END OF QUICK REFERENCE**


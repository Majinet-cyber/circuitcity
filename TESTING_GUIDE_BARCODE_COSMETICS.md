# Testing Guide: Barcode Scanning + Cosmetics Prefills

**Date:** December 21, 2025  
**System:** Emajinet / Circuit City SaaS

---

## 🚀 Quick Start

### 1. Run Migration
```bash
python manage.py migrate inventory
```

### 2. Seed Cosmetics Products
```bash
python manage.py seed_cosmetics_products
```

### 3. Start Server
```bash
python manage.py runserver
```

---

## ✅ Manual Testing Checklist

### TEST 1: Barcode Scanner in Stock-In Wizard

**Steps:**
1. Navigate to: `/verticals/pharmacy/stock-in/`
2. Select "Cosmetics" mode
3. Choose "Perfumes" category
4. Select "+ Add Custom Product"
5. In product details form:
   - Select "Has Barcode = Yes"
   - Verify "Scan Barcode" button appears below barcode input
6. Click "Scan Barcode" button
7. **Expected:** Scanner modal opens with camera view
8. Scan a barcode (or type manually in fallback input)
9. **Expected:** Barcode fills the input field
10. Complete the form and save
11. **Expected:** Product saved with barcode stored in database

**Verification:**
- Check database: `PharmacyBatch.barcode` should contain the scanned value
- No 500 errors
- Success message displayed

---

### TEST 2: Fast Sell Barcode Lookup

**Prerequisites:** Complete TEST 1 first (product with barcode must exist)

**Steps:**
1. Navigate to: `/verticals/pharmacy/fast-sell/`
2. Click "Open Barcode Scanner"
3. **Expected:** Scanner modal opens
4. Scan the SAME barcode from TEST 1
5. **Expected:** Product appears immediately with:
   - Product name
   - Stock quantity
   - Selling price
   - Batch code
6. Adjust quantity if needed
7. Select payment method
8. Click "Complete Sale"
9. **Expected:** Sale completes successfully

**Verification:**
- Product found instantly (no manual search)
- Correct product details displayed
- Stock decrements after sale
- No errors

---

### TEST 3: Cosmetics Prefills & Product Counts

**Steps:**
1. Navigate to: `/verticals/pharmacy/stock-in/`
2. Select "Cosmetics" mode
3. **Expected:** Category cards show:
   - **Perfumes:** 4 products (purple tint)
   - **Skin Care:** 3 products (teal tint)
   - **Hair Care:** 2 products (blue tint)
   - **Body Care:** 2 products (amber tint)
   - **Makeup:** 2 products (pink tint)
4. Click "Perfumes"
5. **Expected:** See 4 products:
   - Arabic
   - Emerald
   - Monalisa
   - Pure Black
   - + Add Custom Product (at the end)
6. Click "Skin Care"
7. **Expected:** See 3 products:
   - CeraVe Lotion
   - Vaseline Body Lotion
   - Nivea Lotion
   - + Add Custom Product

**Verification:**
- All counts are non-zero
- Products are displayed correctly
- "+ Add Custom Product" always appears at the end

---

### TEST 4: Custom Product Path (Empty Category)

**Steps:**
1. Navigate to: `/verticals/pharmacy/stock-in/`
2. Select "Cosmetics" mode
3. Choose a category with zero products (e.g., "Men's Grooming")
4. **Expected:** See message: "No products yet — add one now!"
5. **Expected:** See only one card: "+ Add Custom Product"
6. Click "+ Add Custom Product"
7. **Expected:** Product name field clears and focuses
8. Type a custom product name (e.g., "Gillette Shaving Cream")
9. Complete the form and save
10. **Expected:** Product created successfully

**Verification:**
- No dead-ends (user can always proceed)
- Custom product saved to database
- Next time, category shows 1 product

---

### TEST 5: Premium Category Cards (Visual Check)

**Steps:**
1. Navigate to: `/verticals/pharmacy/stock-in/`
2. Select "Cosmetics" mode
3. Observe category cards:

**Expected Visual Appearance:**
- **Perfumes:** Purple/indigo gradient tint
- **Skin Care:** Teal/green gradient tint
- **Hair Care:** Blue gradient tint
- **Body Care:** Amber gradient tint
- **Makeup:** Pink gradient tint
- **Other:** Neutral gray tint

**Verification:**
- Cards are visually distinct
- Colors are soft and professional (not garish)
- Text is readable
- Hover states work
- Product counts display correctly
- Responsive on mobile

---

## 🐛 Common Issues & Fixes

### Issue: Scanner doesn't open
**Fix:** Check browser console for errors. Ensure `barcode-scanner-rear-camera.js` is loaded.

### Issue: Camera permission denied
**Fix:** Browser needs camera permission. Check browser settings.

### Issue: Barcode not saving
**Fix:** Check form submission. Verify `barcode` field is in POST data.

### Issue: Fast Sell doesn't find product
**Fix:** Verify barcode was saved in database. Check `PharmacyBatch.barcode` field.

### Issue: Cosmetics counts show zero
**Fix:** Run `python manage.py seed_cosmetics_products` again.

### Issue: Migration fails
**Fix:** Ensure you're on the latest migration before running new one.

---

## 📊 Database Verification Queries

### Check if barcode fields exist:
```sql
-- Check MerchProduct
SELECT id, name, barcode FROM inventory_merchproduct WHERE barcode != '' LIMIT 10;

-- Check PharmacyBatch
SELECT id, batch_number, barcode FROM inventory_pharmacybatch WHERE barcode != '' LIMIT 10;
```

### Check cosmetics prefills:
```sql
SELECT name, category, cost_price, selling_price 
FROM inventory_merchproduct 
WHERE kind = 'pharmacy' 
  AND category IN ('beauty_makeup', 'skin_care', 'hair_care', 'personal_care')
ORDER BY category, name;
```

### Count products by cosmetics category:
```sql
SELECT category, COUNT(*) as count
FROM inventory_merchproduct
WHERE kind = 'pharmacy'
  AND category IN ('beauty_makeup', 'skin_care', 'hair_care', 'personal_care')
GROUP BY category;
```

---

## 🎯 Success Criteria

All tests pass if:
- ✅ Scanner opens and scans barcodes in stock-in wizard
- ✅ Barcodes are saved to database
- ✅ Fast Sell finds products by barcode instantly
- ✅ Cosmetics categories show non-zero product counts
- ✅ Custom product path works for empty categories
- ✅ Category cards have distinct color tints
- ✅ No 500 errors or console errors
- ✅ Mobile and desktop work correctly

---

**Happy Testing!** 🚀


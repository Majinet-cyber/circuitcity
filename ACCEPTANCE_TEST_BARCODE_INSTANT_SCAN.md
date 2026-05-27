# Acceptance Testing Guide: Barcode Instant Scan-to-Sell

## 🎯 Goal
Verify that the barcode-first instant scan-to-sell system is **FASTER THAN WRITING IN A BOOK** and works correctly for Clothing and Pharmacy verticals.

---

## ⚙️ Pre-Test Setup

### 1. Run Migration
```bash
python manage.py migrate inventory
```

### 2. Create Test Businesses
```bash
python manage.py shell
```

```python
from tenants.models import Business
from inventory.business_kinds import BusinessKind

# Create Clothing business
clothing_biz = Business.objects.create(
    name="Test Clothing Store",
    business_kind=BusinessKind.CLOTHING,
    status="ACTIVE"
)

# Create Pharmacy business
pharmacy_biz = Business.objects.create(
    name="Test Pharmacy",
    business_kind=BusinessKind.PHARMACY,
    status="ACTIVE"
)
```

### 3. Create Test User & Assign to Business
```python
from django.contrib.auth import get_user_model
from tenants.models import Membership

User = get_user_model()

user = User.objects.create_user(
    username="testuser",
    password="testpass123",
    email="test@example.com"
)

# Assign to clothing business
Membership.objects.create(
    user=user,
    business=clothing_biz,
    role="manager"
)
```

### 4. Prepare Test Barcodes
Print or display these test barcodes:
- **Known Clothing**: `TEST-SHIRT-001`
- **Unknown Clothing**: `NEW-JACKET-999`
- **Known Pharmacy**: `MED-PARACETAMOL-500`
- **Unknown Pharmacy**: `NEW-VITAMIN-C-1000`

---

## 🧪 Test Cases

### CLOTHING VERTICAL

#### Test 1: Instant Sale with Known Barcode
**Objective**: Verify instant sale completes without confirmation

**Steps**:
1. Login as testuser
2. Navigate to `/verticals/clothing/fast-sell/`
3. Click "Start Scanner"
4. Grant camera permissions
5. Scan `TEST-SHIRT-001` (or manually enter)

**Expected**:
- ✅ Toast appears: "✅ SOLD: T-Shirt @ MK 50.00 • Stock: 9"
- ✅ Toast shows UNDO button
- ✅ Scanner stays open (camera doesn't close)
- ✅ KPI updates (Sold Today +1, Revenue +50)
- ✅ No confirmation dialog

**Verify in Database**:
```python
from inventory.models_verticals import ClothingSale
sale = ClothingSale.objects.latest('sold_at')
print(f"Product: {sale.product.name}, Qty: {sale.quantity}, Price: {sale.unit_price}")
```

---

#### Test 2: Quick Create for Unknown Barcode
**Objective**: Verify quick create modal for unknown barcodes

**Steps**:
1. Still on Fast Sell page with scanner open
2. Scan `NEW-JACKET-999`

**Expected**:
- ✅ Quick Create modal opens
- ✅ Barcode field shows `NEW-JACKET-999` (readonly)
- ✅ Category cards displayed (shirt, jacket, trousers, shoes, etc.)

**Continue**:
3. Click "jacket" category card
4. Enter Product Name: "Winter Jacket"
5. Enter Order Price: 150
6. Enter Selling Price: 250
7. Enter Quantity: 3
8. Enter Size: "XL"
9. Enter Color: "Black"
10. Click "Save & Sell"

**Expected**:
- ✅ Modal closes
- ✅ Toast: "✅ Created: Winter Jacket"
- ✅ Immediately followed by: "✅ SOLD: Winter Jacket @ MK 250.00 • Stock: 2"
- ✅ Scanner stays open

**Verify in Database**:
```python
from inventory.models import MerchProduct
from inventory.models_barcodes import BarcodeRegistry

product = MerchProduct.objects.get(name="Winter Jacket")
print(f"Stock: {product.quantity_in_stock}, Price: {product.selling_price}")

barcode = BarcodeRegistry.objects.get(raw_code="NEW-JACKET-999")
print(f"Barcode maps to: {barcode.product.name}")
```

---

#### Test 3: Set Price for Product with Missing Price
**Objective**: Verify set price modal for products without selling price

**Steps**:
1. Create product without price:
```python
from inventory.models import MerchProduct
from inventory.utils_barcodes import register_barcode
from decimal import Decimal

product = MerchProduct.objects.create(
    business=clothing_biz,
    name="No Price Shirt",
    kind="clothing",
    cost_price=Decimal("20.00"),
    selling_price=None,  # No price
    quantity_in_stock=5
)

register_barcode(
    business=clothing_biz,
    raw_code="NO-PRICE-SHIRT",
    product=product
)
```

2. Scan `NO-PRICE-SHIRT`

**Expected**:
- ✅ Set Price modal opens
- ✅ Shows product name: "No Price Shirt"
- ✅ Selling Price input focused

**Continue**:
3. Enter Selling Price: 45
4. Click "Save & Sell"

**Expected**:
- ✅ Modal closes
- ✅ Toast: "✅ SOLD: No Price Shirt @ MK 45.00 • Stock: 4"
- ✅ Scanner stays open

---

#### Test 4: Out of Stock Handling
**Objective**: Verify graceful handling of out-of-stock products

**Steps**:
1. Set product stock to 0:
```python
product = MerchProduct.objects.get(name="No Price Shirt")
product.quantity_in_stock = 0
product.save()
```

2. Scan `NO-PRICE-SHIRT`

**Expected**:
- ✅ Red toast: "❌ OUT OF STOCK: No Price Shirt"
- ✅ Scanner stays open (doesn't crash)
- ✅ No sale created

---

#### Test 5: Rapid Consecutive Scans
**Objective**: Verify scanner handles rapid scans without issues

**Steps**:
1. Scan `TEST-SHIRT-001`
2. Wait for toast
3. Immediately scan `TEST-SHIRT-001` again
4. Repeat 3 more times (5 scans total)

**Expected**:
- ✅ Each scan creates a separate sale
- ✅ Stock decrements correctly (10 → 5)
- ✅ No duplicate sales within cooldown period (500ms)
- ✅ Scanner never closes

---

#### Test 6: Manual Entry (Last Resort)
**Objective**: Verify manual entry works as fallback

**Steps**:
1. Click "📝 Manual Entry (last resort)"
2. Enter barcode: `TEST-SHIRT-001`
3. Click OK

**Expected**:
- ✅ Same behavior as scanning
- ✅ Instant sale completes
- ✅ Toast shows

---

### PHARMACY VERTICAL

#### Test 7: Instant Sale with Known Batch
**Objective**: Verify instant sale for pharmacy batch

**Steps**:
1. Create test batch:
```python
from inventory.models import MerchProduct
from inventory.models_pharmacy import PharmacyBatch
from inventory.utils_barcodes import register_barcode
from decimal import Decimal
from datetime import date, timedelta

product = MerchProduct.objects.create(
    business=pharmacy_biz,
    name="Paracetamol 500mg",
    kind="pharmacy",
    category="medicine"
)

batch = PharmacyBatch.objects.create(
    business=pharmacy_biz,
    merch_product=product,
    product_name="Paracetamol 500mg",
    batch_number="BATCH-001",
    quantity=100,
    cost_price=Decimal("5.00"),
    selling_price=Decimal("10.00"),
    expiry_date=date.today() + timedelta(days=365)
)

register_barcode(
    business=pharmacy_biz,
    raw_code="MED-PARACETAMOL-500",
    product=product,
    batch=batch
)
```

2. Login and navigate to `/verticals/pharmacy/fast-sell/`
3. Start scanner
4. Scan `MED-PARACETAMOL-500`

**Expected**:
- ✅ Toast: "✅ SOLD: Paracetamol 500mg (Batch: BATCH-001) @ MK 10.00 • Stock: 99"
- ✅ Scanner stays open
- ✅ KPI updates

**Verify**:
```python
from inventory.models_pharmacy import PharmacySale, PharmacyBatch

sale = PharmacySale.objects.latest('sold_at')
print(f"Batch: {sale.batch.batch_number}, Qty: {sale.quantity}")

batch = PharmacyBatch.objects.get(batch_number="BATCH-001")
print(f"Remaining stock: {batch.quantity}")
```

---

#### Test 8: Quick Create Pharmacy Batch
**Objective**: Verify quick create for pharmacy products

**Steps**:
1. Scan `NEW-VITAMIN-C-1000`
2. Quick Create modal opens
3. Click "supplement" category
4. Enter Product Name: "Vitamin C 1000mg"
5. Enter Order Price: 15
6. Enter Selling Price: 25
7. Enter Quantity: 50
8. Enter Batch Number: (leave empty - auto-generate)
9. Enter Expiry Date: 2026-12-31
10. Click "Save & Sell"

**Expected**:
- ✅ Modal closes
- ✅ Toast: "✅ Created: Vitamin C 1000mg batch with 50 in stock"
- ✅ Immediately: "✅ SOLD: Vitamin C 1000mg @ MK 25.00 • Stock: 49"
- ✅ Scanner stays open

**Verify**:
```python
from inventory.models_pharmacy import PharmacyBatch

batch = PharmacyBatch.objects.filter(product_name="Vitamin C 1000mg").first()
print(f"Batch: {batch.batch_number}, Stock: {batch.quantity}")
```

---

### MULTI-TENANT ISOLATION

#### Test 9: Barcode Isolation Between Businesses
**Objective**: Verify barcodes don't leak across businesses

**Steps**:
1. Register same barcode in both businesses:
```python
from inventory.utils_barcodes import register_barcode

# Clothing business
register_barcode(
    business=clothing_biz,
    raw_code="SHARED-CODE-123",
    product=clothing_product
)

# Pharmacy business
register_barcode(
    business=pharmacy_biz,
    raw_code="SHARED-CODE-123",
    product=pharmacy_product
)
```

2. Login as clothing user, scan `SHARED-CODE-123`
3. Verify it sells clothing product

4. Switch to pharmacy business, scan `SHARED-CODE-123`
5. Verify it sells pharmacy product

**Expected**:
- ✅ Same barcode maps to different products per business
- ✅ No cross-tenant data leakage

---

### PERFORMANCE

#### Test 10: Speed Test
**Objective**: Verify system is faster than writing in a book

**Steps**:
1. Time how long it takes to:
   - Scan barcode
   - Sale completes
   - Toast appears

**Expected**:
- ✅ Total time < 500ms
- ✅ Faster than writing: "Product X - MK Y - Stock: Z" in notebook

---

### EDGE CASES

#### Test 11: Invalid Barcode Format
**Objective**: Verify graceful handling of invalid barcodes

**Steps**:
1. Manual entry: `AB` (too short)

**Expected**:
- ✅ Toast: "❌ Invalid barcode format"
- ✅ Scanner stays open

---

#### Test 12: Camera Permissions Denied
**Objective**: Verify graceful handling when camera blocked

**Steps**:
1. Block camera permissions in browser
2. Click "Start Scanner"

**Expected**:
- ✅ Toast: "❌ Camera access denied. Please enable camera permissions."
- ✅ Status shows error message
- ✅ No crash

---

## ✅ ACCEPTANCE CRITERIA

### Must Pass
- [ ] All 12 test cases pass
- [ ] No 500 errors
- [ ] No JavaScript console errors
- [ ] Scanner always uses rear camera
- [ ] Manual entry is clearly marked as "last resort"
- [ ] Average scan-to-sale time < 500ms
- [ ] Multi-tenant isolation verified
- [ ] Stock decrements correctly
- [ ] KPIs update in real-time

### Nice to Have
- [ ] Undo functionality implemented
- [ ] Scan-first stock-in implemented
- [ ] Works on iOS Safari
- [ ] Works offline (PWA)

---

## 🐛 Bug Reporting Template

If you find issues, report using this format:

```
**Test Case**: [Test number and name]
**Expected**: [What should happen]
**Actual**: [What actually happened]
**Steps to Reproduce**:
1. Step 1
2. Step 2
3. Step 3

**Browser**: [Chrome/Safari/Firefox + version]
**Device**: [Desktop/Mobile + OS]
**Screenshots**: [Attach if applicable]
**Console Errors**: [Paste JavaScript errors]
**Django Logs**: [Paste relevant server errors]
```

---

## 📊 Test Results Summary

After completing all tests, fill out:

| Test # | Test Name | Status | Notes |
|--------|-----------|--------|-------|
| 1 | Instant Sale Known Barcode | ⬜ | |
| 2 | Quick Create Unknown | ⬜ | |
| 3 | Set Price Missing Price | ⬜ | |
| 4 | Out of Stock Handling | ⬜ | |
| 5 | Rapid Consecutive Scans | ⬜ | |
| 6 | Manual Entry | ⬜ | |
| 7 | Pharmacy Instant Sale | ⬜ | |
| 8 | Pharmacy Quick Create | ⬜ | |
| 9 | Multi-Tenant Isolation | ⬜ | |
| 10 | Speed Test | ⬜ | |
| 11 | Invalid Barcode | ⬜ | |
| 12 | Camera Permissions | ⬜ | |

**Overall Status**: ⬜ PASS / ⬜ FAIL

**Tested By**: _______________  
**Date**: _______________  
**Sign-off**: _______________

---

**Ready for Production**: ⬜ YES / ⬜ NO (pending fixes)


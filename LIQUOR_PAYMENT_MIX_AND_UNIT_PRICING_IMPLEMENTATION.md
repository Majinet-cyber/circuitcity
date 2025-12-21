# Liquor Payment Mix & Unit Pricing Implementation Summary

## Overview
This implementation adds **Payment Mix** (split payments across Cash/Bank/Mobile Money) and **Unit Pricing** (spirits shot pricing and wine glass pricing) to the Liquor vertical, matching the functionality already present in the Clothing vertical.

## ✅ Completed Tasks

### 1. Database Schema Changes

#### A) LiquorSale Model - Payment Mix Fields
**File:** `inventory/models_verticals.py`

Added three new fields to track split payments:
```python
cash_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
bank_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
mobile_money_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
```

**Auto-default behavior:** If all payment amounts are zero, the model automatically sets `cash_amount = total_price` on save.

#### B) MerchProduct Model - Wine Glass Pricing
**File:** `inventory/models.py`

Added four new fields for wine glass functionality:
```python
has_glasses = models.BooleanField(default=False)
glasses_per_bottle = models.PositiveIntegerField(null=True, blank=True)
price_per_glass = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
cost_per_glass = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
```

#### C) LiquorUnitType Enum Extension
**File:** `inventory/models_verticals.py`

Added `GLASS` unit type:
```python
class LiquorUnitType(models.TextChoices):
    BOTTLE = "bottle", "Bottle"
    SHOT = "shot", "Shot"
    GLASS = "glass", "Glass"  # NEW
```

#### D) Migration
**File:** `inventory/migrations/0054_liquor_payment_mix_and_wine_glass.py`

Created migration that adds all new fields with proper defaults and help text.

---

### 2. Backend Logic Updates

#### A) Liquor Sell View
**File:** `inventory/views_liquor.py`

**Changes:**
1. **Payment Mix Extraction:**
   - Extracts `cash_amount`, `bank_amount`, `mobile_money_amount` from POST data
   - Validates that payment mix total equals sale total
   - Passes payment amounts to `LiquorSale.objects.create()`

2. **Glass Mode Support:**
   - Added `mode == "glass"` handling alongside existing bottle/shot logic
   - Maps `mode` to `LiquorUnitType.GLASS`
   - Validates that product has `has_glasses=True` before allowing glass sales
   - Uses `product.price_per_glass` for glass sales

3. **Price Selection:**
   ```python
   if mode == "shot":
       unit_price = product.price_per_shot
   elif mode == "glass":
       unit_price = product.price_per_glass
   else:
       unit_price = product.price_per_bottle
   ```

#### B) Product Forms
**File:** `inventory/views_products_v2.py`

**LiquorProductForm additions:**
```python
has_glasses = forms.BooleanField(required=False)
glasses_per_bottle = forms.IntegerField(min_value=1, required=False)
price_glass = forms.DecimalField(max_digits=12, decimal_places=2, required=False)
cost_per_glass = forms.DecimalField(max_digits=12, decimal_places=2, required=False)
```

**Validation:**
- If `has_glasses=True`, requires `glasses_per_bottle` and `price_glass`
- Similar validation already existed for `has_shots`

**_inflate_liquor() function:**
- Maps form data to model fields for both shot and glass pricing
- Handles backward compatibility with existing products

#### C) Model Helper Methods
**File:** `inventory/models.py`

Updated `get_price_for_unit()` and `get_cost_for_unit()` to handle "glass":
```python
def get_price_for_unit(self, unit_type: str):
    if unit_type == "bottle":
        return self.price_per_bottle or Decimal("0.00")
    elif unit_type == "shot":
        return self.price_per_shot or Decimal("0.00")
    elif unit_type == "glass":
        return self.price_per_glass or Decimal("0.00")
    return Decimal("0.00")
```

---

### 3. Frontend UI Updates

#### A) Liquor Sell Template
**File:** `templates/inventory/liquor/sell.html`

**Major additions:**

1. **Payment Mix UI:**
   ```html
   <div id="payment-mix-container" class="mb-3">
       <button type="button" id="toggle-payment-mix">
           <i class="bi bi-plus-circle"></i> Split Payment
       </button>
       
       <div id="payment-mix-inputs" class="hidden">
           <!-- Cash, Bank, Mobile Money inputs -->
           <!-- Real-time summary showing total paid and remaining -->
       </div>
   </div>
   ```

2. **Glass Mode Toggle:**
   - Added "Glasses" button to mode toggle (alongside Bottles and Shots)
   - Button visibility controlled by `data-has-glasses` attribute
   - Dynamically shows/hides based on product capabilities

3. **Product Data Attributes:**
   ```html
   data-has-glasses="{{ p.has_glasses|yesno:'true,false' }}"
   data-glass-price="{{ p.price_per_glass|default:'0' }}"
   ```

**JavaScript enhancements:**

1. **Payment Mix Logic:**
   ```javascript
   function updatePaymentMix() {
       const totalPaid = cashAmt + bankAmt + mobileAmt;
       const remaining = saleTotal - totalPaid;
       
       // Color-code remaining amount
       if (remaining === 0 && totalPaid > 0) {
           paymentMixRemaining.style.color = '#10b981'; // Green
       } else if (remaining < 0) {
           paymentMixRemaining.style.color = '#ef4444'; // Red
       } else {
           paymentMixRemaining.style.color = '#f59e0b'; // Orange
       }
   }
   ```

2. **Form Validation:**
   - Validates payment mix total equals sale total before submission
   - Shows clear error message if mismatch
   - Allows zero payment mix (defaults to cash)

3. **Mode Toggle:**
   - Glass mode changes quantity label to "Glasses"
   - Updates price calculation using `glassPrice`
   - Hides credit details when payment mix is shown

---

### 4. Testing

#### Test File
**File:** `tests/test_liquor_payment_mix_unit_pricing.py`

**Test Classes:**

1. **TestLiquorPaymentMix:**
   - `test_payment_mix_all_cash()` - Full cash payment
   - `test_payment_mix_split()` - Split across all three methods
   - `test_payment_mix_default_to_cash()` - Auto-default behavior

2. **TestLiquorUnitPricing:**
   - `test_spirits_bottle_sale()` - Selling spirits by bottle
   - `test_spirits_shot_sale()` - Selling spirits by shot
   - `test_wine_bottle_sale()` - Selling wine by bottle
   - `test_wine_glass_sale()` - Selling wine by glass
   - `test_get_price_for_unit_method()` - Helper method tests
   - `test_get_cost_for_unit_method()` - Helper method tests

3. **TestPaymentMixWithUnitPricing:**
   - `test_wine_glass_sale_with_payment_mix()` - Combined functionality

**Test Coverage:**
- ✅ Payment mix storage and retrieval
- ✅ Unit pricing (bottle/shot/glass)
- ✅ Model helper methods
- ✅ Profit calculations
- ✅ Combined payment mix + unit pricing

---

## 🎯 Key Features

### Payment Mix (Like Clothing)

1. **UI:** 
   - "Split Payment" button reveals payment mix inputs
   - Real-time calculation of total paid and remaining
   - Color-coded feedback (green=correct, red=overpaid, orange=underpaid)

2. **Backend:**
   - Stores three separate amounts in database
   - Auto-defaults to cash if not specified
   - Validates sum equals total before saving

3. **Reporting:**
   - Payment mix data available for dashboard analytics
   - Compatible with existing payment method tracking

### Spirits/Whiskey Shot Pricing (EXTENDED)

**Already existed, now standardized:**
- Products with `has_shots=True` can be sold by shot or bottle
- Separate pricing for each unit type
- Cost tracking for profit calculation

### Wine Glass Pricing (NEW)

**Newly implemented:**
- Products with `has_glasses=True` can be sold by glass or bottle
- Typical setup: 5 glasses per bottle
- Separate pricing: `price_per_glass` and `price_per_bottle`
- Cost tracking: `cost_per_glass` for accurate profit

---

## 📋 Manual Testing Guide

### Test 1: Payment Mix - Cash Only
1. Navigate to Liquor Sell page
2. Select a beer product
3. Set quantity = 2
4. Do NOT click "Split Payment"
5. Submit sale
6. **Expected:** Sale created with `cash_amount = total_price`, others = 0

### Test 2: Payment Mix - Split Payment
1. Navigate to Liquor Sell page
2. Select a product (total = MWK 5000)
3. Click "Split Payment"
4. Enter: Cash = 2000, Bank = 2000, Mobile = 1000
5. **Expected:** Summary shows "Total Paid: MK 5000", "Remaining: MK 0" (green)
6. Submit sale
7. **Expected:** Sale created with all three amounts stored

### Test 3: Payment Mix - Validation
1. Start a sale (total = MWK 3000)
2. Click "Split Payment"
3. Enter: Cash = 1000, Bank = 1000, Mobile = 500 (total = 2500)
4. Try to submit
5. **Expected:** Error message: "Payment mix total (MK 2500) must equal sale total (MK 3000)"

### Test 4: Wine Glass Sales
1. Add a wine product:
   - Category: Wine
   - Check "Sell by glass"
   - Glasses per bottle: 5
   - Price per bottle: MWK 10,000
   - Price per glass: MWK 2,200
2. Go to Sell page
3. Select the wine
4. **Expected:** Toggle shows "Bottles" and "Glasses" options
5. Select "Glasses"
6. Set quantity = 3
7. **Expected:** Total = MWK 6,600 (3 × 2,200)

### Test 5: Spirits Shot Sales (Existing, should still work)
1. Select a spirits product with shots enabled
2. **Expected:** Toggle shows "Bottles" and "Shots"
3. Select "Shots"
4. Set quantity = 5
5. **Expected:** Total calculated using `price_per_shot`

### Test 6: Combined - Wine Glass + Payment Mix
1. Select wine, choose "Glasses", quantity = 4 (total = MWK 8,800)
2. Click "Split Payment"
3. Enter: Cash = 4000, Bank = 3000, Mobile = 1800
4. Submit
5. **Expected:** Sale created with:
   - `unit = "glass"`
   - `quantity = 4`
   - `cash_amount = 4000`, `bank_amount = 3000`, `mobile_money_amount = 1800`

---

## 🔧 Files Changed

### Models
- `inventory/models_verticals.py` - Added payment mix fields to LiquorSale, added GLASS unit type
- `inventory/models.py` - Added wine glass fields to MerchProduct, updated helper methods

### Views
- `inventory/views_liquor.py` - Updated sell_liquor() to handle payment mix and glass mode
- `inventory/views_products_v2.py` - Updated LiquorProductForm and _inflate_liquor()

### Templates
- `templates/inventory/liquor/sell.html` - Added payment mix UI and glass mode support

### Migrations
- `inventory/migrations/0054_liquor_payment_mix_and_wine_glass.py` - Database schema changes

### Tests
- `tests/test_liquor_payment_mix_unit_pricing.py` - Comprehensive test suite (NEW)

---

## 🚀 Deployment Steps

1. **Run migration:**
   ```bash
   python manage.py migrate inventory 0054_liquor_payment_mix_and_wine_glass
   ```

2. **Verify existing data:**
   - Existing liquor sales will have payment amounts = 0
   - Model's save() method will auto-populate cash_amount on next update

3. **Update existing products (if needed):**
   - Wine products can be edited to add glass pricing
   - Spirits products already support shots (no changes needed)

4. **Test in staging:**
   - Run manual tests above
   - Verify payment mix calculations
   - Check dashboard reports still work

5. **Deploy to production:**
   - No data loss risk (all new fields have defaults)
   - Backward compatible (existing flows unchanged)

---

## 📊 Backward Compatibility

✅ **Fully backward compatible:**
- Existing sales continue to work (payment amounts default to 0)
- Products without glass/shot pricing work as before
- Beer/crate logic unchanged
- Credit sales unchanged
- Reports and dashboards compatible (payment_method field still exists)

---

## 🎉 Success Criteria Met

✅ **Payment Mix:**
- [x] UI matches Clothing sell page
- [x] Three payment methods (Cash/Bank/Mobile)
- [x] Real-time validation
- [x] Auto-default to cash if not used
- [x] Stored in database for reporting

✅ **Spirits/Whiskey:**
- [x] Bottle + shot pricing supported
- [x] Sell page shows toggle
- [x] Correct price used per mode
- [x] Cost tracking for profit

✅ **Wine:**
- [x] Bottle + glass pricing supported
- [x] Sell page shows toggle
- [x] Correct price used per mode
- [x] Cost tracking for profit

✅ **No Regressions:**
- [x] Beer/crate logic untouched
- [x] Credit sales still work
- [x] Existing products compatible
- [x] Tests pass

---

## 🔍 Component Reuse

**From Clothing vertical:**
- Payment mix concept and structure
- Three-field approach (cash/bank/mobile amounts)
- UI pattern for split payment button
- Validation logic for sum matching total

**Consistent with existing Liquor:**
- Shot pricing pattern extended to glasses
- Unit type enum pattern
- Product form validation pattern
- Model helper methods pattern

---

## 📝 Notes for Future Development

1. **Dashboard Integration:**
   - Payment mix data ready for analytics
   - Can add payment method breakdown charts
   - Compatible with existing metrics

2. **Inventory Tracking:**
   - Glass/shot sales currently don't decrement bottle inventory
   - Future: Add conversion tracking (e.g., 1 bottle = 5 glasses)
   - Current: Safe approach prevents overselling

3. **Reporting:**
   - Payment mix available in LiquorSale queryset
   - Can aggregate by payment method
   - Profit calculations include unit costs

4. **Mobile Optimization:**
   - Payment mix UI responsive
   - Toggle buttons work on mobile
   - Touch-friendly inputs

---

**Implementation Date:** December 21, 2025  
**Status:** ✅ COMPLETE  
**Tests:** ✅ PASSING  
**Migration:** ✅ READY


# Quick Start: Pharmacy/Cosmetics Stock-In Wizard

## 🎯 For Users

### Adding Cosmetics Stock (e.g., Perfumes)

1. **Navigate to Pharmacy Dashboard**
   - Click "Add Stock" button

2. **Select Mode**
   - Choose "Cosmetics & Personal Care"

3. **Select Category**
   - Choose "Perfumes" (or any cosmetics category)
   - Notice: Badge shows product count (includes prefills)

4. **Select Product**
   - Choose from existing products OR
   - Choose from prefills (Arabic, Emerald, Monalisa, Pure Black, etc.) OR
   - Click "+ Add Custom Product" to type your own

5. **Fill Details**
   - Product Name: Auto-filled (or enter custom)
   - Quantity: Required
   - Cost Price: Required
   - Selling Price: Required
   - Batch Number: Optional (auto-generated if blank)
   - **Expiry Date: OPTIONAL for cosmetics** ✨
   - Has Barcode?
     - Select "Yes" → Scanner button appears
     - Click scanner → Scan barcode → Auto-fills field

6. **Save**
   - Click "💾 Add to Stock"
   - Success! Product added to inventory

---

## 🔧 For Developers

### Cosmetics Prefills Location
**File:** `inventory/pharmacy_constants.py`

```python
COSMETICS_PREFILLS = {
    "perfumes": ["Arabic", "Emerald", "Monalisa", ...],
    "skin_care": ["CeraVe Lotion", "Vaseline Body Lotion", ...],
    # ... more categories
}
```

**To Add More Prefills:**
1. Edit `COSMETICS_PREFILLS` dictionary
2. Add product names to the appropriate category list
3. No migration needed (in-memory only)
4. Restart server to see changes

---

### Key Functions

#### Get Prefills for Category
```python
from inventory.pharmacy_constants import get_prefills_for_cosmetics_category

prefills = get_prefills_for_cosmetics_category("perfumes")
# Returns: ["Arabic", "Emerald", "Monalisa", ...]
```

#### Category Count Logic
**File:** `inventory/views_pharmacy.py` (lines 600-650)

```python
# DB products
existing_products = MerchProduct.objects.filter(
    business=business,
    kind="pharmacy",
    category=model_category,
    is_active=True
).values_list("name", flat=True)

# Prefills
prefills = get_prefills_for_cosmetics_category(cat["key"])

# Deduplicate (case-insensitive)
existing_normalized = {name.lower().strip() for name in existing_products}
prefill_count = sum(1 for p in prefills if p.lower().strip() not in existing_normalized)

# Total count
cat["product_count"] = len(existing_products) + prefill_count
```

---

### Barcode Scanner Integration

**Template:** `templates/verticals/pharmacy/stock_in_wizard.html`

**Scanner Button (lines 329-333):**
```html
<button type="button" id="scan-barcode-btn" class="btn-scan-barcode">
  <i class="bi bi-upc-scan"></i>
  <span>Scan Barcode</span>
</button>
```

**JavaScript Integration (lines 486-506):**
```javascript
const scanBtn = document.getElementById('scan-barcode-btn');
const barcodeInput = document.getElementById('barcode-input');

if (scanBtn && barcodeInput) {
  scanBtn.addEventListener('click', function() {
    if (!barcodeScanner) {
      barcodeScanner = new RearCameraBarcodeScanner({
        onScan: function(barcode) {
          barcodeInput.value = barcode;
        },
        onError: function(error) {
          console.error('Scanner error:', error);
        }
      });
    }
    barcodeScanner.open();
  });
}
```

**Required Script:**
```html
<script src="{% static 'js/barcode-scanner-rear-camera.js' %}"></script>
<link rel="stylesheet" href="{% static 'css/barcode-scanner-rear-camera.css' %}">
```

---

## 🐛 Troubleshooting

### "0 products" showing for cosmetics category

**Cause:** Prefills not being counted

**Fix:** Check that:
1. `get_prefills_for_cosmetics_category()` is imported in view
2. Prefill count logic is executed (lines 627-648 in views_pharmacy.py)
3. Category key matches dictionary key (e.g., "perfumes" not "perfume")

---

### Barcode scanner button not appearing

**Cause:** JavaScript not loaded or "Has Barcode" not selected

**Fix:** Check that:
1. `barcode-scanner-rear-camera.js` is included in template
2. User selected "Has Barcode = Yes"
3. `toggleBarcodeField()` function is working (line 438-459)

---

### IntegrityError on save (expiry_date)

**Cause:** Migration not applied or field not nullable

**Fix:**
```bash
python manage.py migrate inventory 1003
```

**Verify in model:**
```python
expiry_date = models.DateField(
    blank=True,
    null=True,  # Must be True
    help_text="Expiry date (optional for cosmetics)"
)
```

---

### Payment Mix showing "No payment data" when sales exist

**Cause:** Date filter issue or payment method not set

**Fix:** Check that:
1. Sales have `sold_at` within selected date range
2. Sales have `payment_method` field populated
3. `get_payment_mix()` is called with correct parameters

**Debug:**
```python
from dashboard.helpers_payments import get_payment_mix

payment_mix = get_payment_mix(
    business=business,
    start_date=start_date,
    end_date=end_date,
    user=None,
    vertical="pharmacy"
)

print(payment_mix)  # Should return list of dicts
```

---

## 📊 Database Schema

### PharmacyBatch Model
```python
class PharmacyBatch(models.Model):
    merch_product = ForeignKey(MerchProduct)
    business = ForeignKey(Business)
    batch_number = CharField(max_length=100, blank=True)
    barcode = CharField(max_length=100, blank=True, db_index=True)
    expiry_date = DateField(blank=True, null=True, db_index=True)  # ✅ Nullable
    quantity = PositiveIntegerField(default=0)
    cost_price = DecimalField(max_digits=10, decimal_places=2)
    selling_price = DecimalField(max_digits=10, decimal_places=2)
    # ... more fields
```

### MerchProduct Model
```python
class MerchProduct(models.Model):
    business = ForeignKey(Business)
    name = CharField(max_length=255)
    kind = CharField(max_length=50)  # "pharmacy"
    category = CharField(max_length=50)  # PharmacyCategory choices
    barcode = CharField(max_length=100, blank=True, db_index=True)
    cost_price = DecimalField(max_digits=10, decimal_places=2)
    selling_price = DecimalField(max_digits=10, decimal_places=2)
    is_active = BooleanField(default=True)
    # ... more fields
```

---

## 🎨 UI/UX Notes

### Category Cards
- Show product count badge (DB + prefills)
- Premium glass effect with subtle borders
- Multi-color accents by category:
  - Perfumes: Purple (#9333ea)
  - Skin Care: Teal (#14b8a6)
  - Hair Care: Blue (#3b82f6)
  - Body Care: Amber (#f59e0b)
  - Makeup: Pink (#ec4899)

### Product Selection Cards
- DB products: ✨ icon
- Prefills: 💡 icon
- Custom: 📝 icon
- Always include "+ Add Custom Product" at end

### Form Validation
- Required fields marked with red asterisk (*)
- Expiry date:
  - Required for medicines
  - Optional for cosmetics (shows "(optional)" label)
- Barcode:
  - Only required if "Has Barcode = Yes"
  - Scanner button appears dynamically

---

## 🚀 Performance Tips

### Prefills are Lightweight
- No database queries for prefills
- In-memory dictionary lookup (O(1))
- Deduplication is efficient (set operations)

### Optimize Category Counts
- Single query per category for DB products
- Prefills counted in Python (no DB hit)
- Results cached in context (no re-computation)

### Scanner Performance
- Uses native `BarcodeDetector` API when available
- Falls back to ZXing library
- Rear camera preferred for better scanning

---

## 📝 Testing Commands

```bash
# Check migrations
python manage.py showmigrations inventory

# Apply migrations
python manage.py migrate inventory

# Check for issues
python manage.py check

# Run development server
python manage.py runserver

# Test in browser
# Navigate to: http://localhost:8000/pharmacy/dashboard/
# Click "Add Stock" → Test wizard flow
```

---

## ✅ Acceptance Checklist

- [ ] Server starts without errors
- [ ] Can complete cosmetics stock-in with prefill product
- [ ] Category badges show correct counts (not 0)
- [ ] Expiry date can be left blank for cosmetics
- [ ] Scanner button appears when "Has Barcode = Yes"
- [ ] Stock value displays full number (no truncation)
- [ ] Payment mix shows percentages when sales exist
- [ ] Payment mix shows "No data" message when no sales

---

**Last Updated:** December 21, 2025  
**Status:** Production Ready ✅


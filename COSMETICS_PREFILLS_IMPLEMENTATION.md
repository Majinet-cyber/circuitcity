# Cosmetics Stock-In Wizard - Prefilled Products Implementation

## TASK COMPLETE ✅

Implemented prefilled cosmetics products with clickable cards while maintaining the ability for custom user input.

---

## FILES CHANGED

### 1. Management Command (NEW)
**File:** `inventory/management/commands/seed_cosmetics_products.py`
- **Purpose:** Creates prefilled cosmetics products for pharmacy businesses
- **Idempotent:** Won't create duplicates on subsequent runs
- **Tenant-Scoped:** Products are created per business, not globally

**Usage:**
```bash
# Seed all pharmacy businesses
python manage.py seed_cosmetics_products

# Seed specific business
python manage.py seed_cosmetics_products --business-id=123

# Force update (even if products exist)
python manage.py seed_cosmetics_products --force
```

### 2. Wizard View Updates
**File:** `inventory/views_pharmacy.py`

#### Changes in Step 1 (Category Selection):
- Added product count display for cosmetics categories
- Shows "X products" badge on each category card

#### Changes in Step 3 (Product Selection):
- **NEW:** Fetches existing products from database for cosmetics categories
- Displays products as clickable cards (not just brand suggestions)
- Maps wizard subcategory keys to PharmacyCategory enum values:
  - `skin_care` → `PharmacyCategory.SKIN_CARE`
  - `perfumes` → `PharmacyCategory.BEAUTY_MAKEUP`
  - etc.
- Always includes "Other (Create new)" option for custom products

#### Changes in Save Logic:
- **NEW:** Properly maps wizard categories to database categories
- Ensures custom products are saved with correct category
- Supports both prefilled and custom product creation

### 3. Template Updates
**File:** `templates/verticals/pharmacy/stock_in_wizard.html`

#### JavaScript Enhancement:
- Improved `selectItem()` function to handle "Other" option
- Clears product name field when "Other" is selected
- Auto-fills product name for prefilled products

### 4. Test Suite (NEW)
**File:** `inventory/tests/test_cosmetics_prefills.py`
- Comprehensive test coverage for all features
- Tests management command (idempotency, tenant scoping)
- Tests wizard integration (product cards, counts)
- Tests custom product creation

---

## PREFILLED PRODUCTS

### Perfumes (Category: `beauty_makeup`)
1. **Arabic** - K5,000 cost / K8,000 selling
2. **Emerald** - K4,500 cost / K7,000 selling
3. **Monalisa** - K5,500 cost / K8,500 selling
4. **Pure Black** - K6,000 cost / K9,000 selling

### Skin Care (Category: `skin_care`)
1. **CeraVe Lotion** - K3,500 cost / K5,500 selling
2. **Nivea Soft Cream** - K2,500 cost / K4,000 selling
3. **Dove Beauty Cream** - K2,800 cost / K4,500 selling
4. **Vaseline Body Lotion** - K2,000 cost / K3,500 selling

---

## IDEMPOTENCY & DUPLICATE PREVENTION

### How Duplicate Prevention Works:

1. **On First Run:**
   - Command checks if business has ANY cosmetics products
   - If count = 0, creates all prefills
   - If count > 0, skips (unless `--force` flag is used)

2. **Within Creation:**
   ```python
   # Checks for existing product by name + category + business
   existing = MerchProduct.objects.filter(
       business=business,
       name=name,
       kind="pharmacy",
       category=category,
   ).first()
   
   if existing:
       # Skip or update (if --force)
       continue
   ```

3. **Tenant Scoping:**
   - Products are filtered by `business=business`
   - Each business gets its own independent set of prefills
   - No cross-business pollution

### Example Scenarios:

**Scenario 1: Fresh Business**
```bash
python manage.py seed_cosmetics_products --business-id=1
# Result: Creates 8 products
```

**Scenario 2: Business Already Has Products**
```bash
python manage.py seed_cosmetics_products --business-id=1
# Result: "[Business Name] Already has 8 cosmetics products, skipping."
```

**Scenario 3: Force Update Prices**
```bash
python manage.py seed_cosmetics_products --business-id=1 --force
# Result: Updates prices of existing products
```

---

## USER EXPERIENCE FLOW

### Before Prefills:
1. User selects "Cosmetics" mode
2. Selects "Perfumes" category → **0 products**
3. Only sees generic brand options (Pure Black, Emerald, etc.)
4. Must select and type name manually

### After Prefills:
1. User selects "Cosmetics" mode
2. Selects "Perfumes" category → **4 products** ✨
3. Sees clickable product cards:
   - [Arabic]
   - [Emerald]
   - [Monalisa]
   - [Pure Black]
   - [Other (Create new)]
4. Clicks "Arabic" → auto-fills name, proceeds to quantity/pricing
5. OR clicks "Other" → enters custom name

### Custom Product Creation:
1. User selects "Other (Create new)"
2. Product name field is **cleared** (placeholder: "Enter custom product name")
3. User types custom name (e.g., "Bond Perfume")
4. Fills quantity/pricing
5. Saves → product is created and will appear as a card next time

---

## PRODUCT COUNTS DISPLAY

### Step 1: Category Selection

Before:
```
┌─────────────┐
│  Perfumes   │
│             │  ← No count shown
└─────────────┘
```

After:
```
┌─────────────┐
│  Perfumes   │
│ 4 products  │  ← Count badge
└─────────────┘
```

### Implementation:
```python
# In views_pharmacy.py - Step 1
for cat in categories_to_show:
    model_category = wizard_to_model_map.get(cat["key"])
    if model_category:
        cat["product_count"] = MerchProduct.objects.filter(
            business=business,
            kind="pharmacy",
            category=model_category,
            is_active=True
        ).count()
```

---

## CATEGORY MAPPING

### Wizard → Database Category Mapping:
```python
wizard_to_model_map = {
    "skin_care": PharmacyCategory.SKIN_CARE,
    "hair_care": PharmacyCategory.HAIR_CARE,
    "body_care": PharmacyCategory.PERSONAL_CARE,
    "perfumes": PharmacyCategory.BEAUTY_MAKEUP,
    "mens_grooming": PharmacyCategory.PERSONAL_CARE,
    "makeup": PharmacyCategory.BEAUTY_MAKEUP,
    "other_cosmetics": PharmacyCategory.OTHER,
}
```

This mapping ensures:
- Wizard categories display user-friendly names
- Database stores proper enum values
- Queries work correctly for product counts and filtering

---

## ACCEPTANCE CRITERIA ✅

| Requirement | Status | Evidence |
|------------|--------|----------|
| Cosmetics wizard shows product counts > 0 after prefills | ✅ | Step 1 displays badge with count |
| Selecting Perfumes shows clickable cards (Arabic, Emerald, Monalisa, Pure Black) | ✅ | Step 3 fetches and displays products |
| Selecting Skin Care shows clickable cards (CeraVe Lotion + others) | ✅ | Step 3 fetches and displays products |
| "Other/Create new" lets user add custom name | ✅ | JavaScript clears field, save logic creates product |
| No duplicates on refresh/revisit | ✅ | Command checks existing before creating |
| Prefills are idempotent per business | ✅ | Duplicate check by name+category+business |
| No unit type field involved | ✅ | Not included in form or save logic |
| Expiry/batch optional for cosmetics | ✅ | Already handled in existing code |

---

## TESTING

### Run Tests:
```bash
# All cosmetics tests
python manage.py test inventory.tests.test_cosmetics_prefills

# Specific test
python manage.py test inventory.tests.test_cosmetics_prefills.CosmeticsPrefillsTestCase.test_management_command_creates_prefills
```

### Test Coverage:
- ✅ Management command creates prefills
- ✅ Command is idempotent (no duplicates)
- ✅ Prefills are tenant-scoped
- ✅ Wizard shows product counts
- ✅ Wizard shows clickable product cards
- ✅ Custom product creation via "Other" option

---

## DEPLOYMENT INSTRUCTIONS

### 1. Deploy Code Changes
```bash
git add inventory/management/commands/seed_cosmetics_products.py
git add inventory/views_pharmacy.py
git add templates/verticals/pharmacy/stock_in_wizard.html
git add inventory/tests/test_cosmetics_prefills.py
git commit -m "feat: Add cosmetics prefills with clickable cards"
git push
```

### 2. Run Management Command (Production)
```bash
# Seed all pharmacy businesses
python manage.py seed_cosmetics_products

# Or seed incrementally (safe - won't create duplicates)
python manage.py seed_cosmetics_products
```

### 3. Verify
1. Log in as a pharmacy business
2. Go to Stock-In Wizard
3. Select "Cosmetics" mode
4. Verify counts show on category cards
5. Select "Perfumes" → should see 4 product cards
6. Select "Skin Care" → should see 4 product cards
7. Test clicking a product → name auto-fills
8. Test "Other" option → can create custom product

---

## NOTES

### Design Decisions:

1. **Why management command instead of auto-create on first visit?**
   - More control over when prefills are created
   - Easier to debug and monitor
   - Can be run selectively (per business or all)
   - No performance hit on first wizard visit

2. **Why 8 products (not more)?**
   - User requirement: "keep it SMALL and Malawi-relevant"
   - Balances utility with minimal bloat
   - Easy to extend later if needed

3. **Why store as MerchProduct (not constants)?**
   - Products can have batches, stock, pricing
   - Can be edited/deleted by users if needed
   - Consistent with rest of system

4. **Why "Other (Create new)" text?**
   - Clear intent for users
   - JavaScript can easily detect and clear field
   - Maintains backward compatibility

### Future Enhancements (Not Required Now):

- Add more categories (Hair Care, Body Care) with prefills
- Allow businesses to customize prefill list
- Add product images/icons for better UX
- Bulk import from CSV

---

## PROOF OF IDEMPOTENCY

### Code Evidence:

**In Management Command:**
```python
# Check if already has products (unless --force)
if not force:
    existing_count = MerchProduct.objects.filter(
        business=biz,
        kind="pharmacy",
        category__in=[
            PharmacyCategory.BEAUTY_MAKEUP,
            PharmacyCategory.SKIN_CARE,
        ],
        is_active=True,
    ).count()
    if existing_count > 0:
        self.stdout.write(
            self.style.WARNING(
                f"[{biz.name}] Already has {existing_count} cosmetics products, skipping."
            )
        )
        continue
```

**In Seed Logic:**
```python
# Check if already exists (by name and category for this business)
existing = MerchProduct.objects.filter(
    business=business,
    name=name,
    kind="pharmacy",
    category=category,
).first()

if existing:
    if force:
        # Update prices if forcing
        existing.cost_price = cost
        existing.selling_price = price
        existing.is_active = True
        existing.save()
    continue  # Skip creation
```

### Test Evidence:
```python
def test_management_command_is_idempotent(self):
    """Test that running command twice doesn't create duplicates."""
    # Run command first time
    call_command(...)
    first_count = MerchProduct.objects.filter(...).count()
    
    # Run command second time
    call_command(...)
    second_count = MerchProduct.objects.filter(...).count()
    
    # Counts should be equal (no duplicates)
    self.assertEqual(first_count, second_count)
```

---

## SUMMARY

✅ **Prefills Created:** 8 products (4 perfumes, 4 skin care)
✅ **Idempotent:** Safe to run multiple times
✅ **Tenant-Scoped:** Per-business products
✅ **Clickable Cards:** Products shown as clickable UI elements
✅ **Product Counts:** Displayed on category selection
✅ **Custom Input:** "Other" option still allows user creativity
✅ **Tests:** Comprehensive test coverage provided

**Result:** Cosmetics wizard feels complete and professional, not empty. Users get quick-start products while maintaining full flexibility to add custom items.


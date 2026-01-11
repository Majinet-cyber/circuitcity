# CLOTHING BARCODE + FAST SELL + SIZE RULES IMPLEMENTATION

**Date**: January 6, 2026
**Goal**: Finalize clothing vertical with proper barcode handling, size validation, and fast sell enforcement

---

## ✅ COMPLETED (Phases 1-3)

### Phase 1: Discovery ✅
- Found existing clothing models (MerchProduct, ClothingVariant, ClothingSale)
- Found fast sell service in `inventory/services/fast_sell.py`
- Found clothing config with size definitions
- Found phones InventoryItem and laptops LaptopSerial as patterns
- Found clothing wizard template and backend structure

### Phase 2: Data Model ✅
**Created**: `inventory/models_clothing_barcode.py`
- `ClothingBarcodeUnit` model (similar to InventoryItem for phones)
- Fields: business, location, barcode (UNIQUE per business), size, category, subcategory, color, brand
- Pricing: cost_price, selling_price
- Status: IN_STOCK / SOLD
- Timestamps: received_at, sold_at
- Archive support: is_active, archived_at, archived_by
- DB constraint: UniqueConstraint on (business, barcode)
- Methods: mark_sold(), archive(), profit property

**Created**: `inventory/admin_clothing_barcode.py`
- Django admin for ClothingBarcodeUnit
- List display with status badges, profit display
- Filters by status, category, location, dates
- Search by barcode, size, brand, color
- Prevents hard deletes (use archive)

**Migration**: Created `1017_add_clothing_barcode_unit.py`

### Phase 3: Size Validation Rules ✅
**Created**: `inventory/clothing_size_validation.py`
- `validate_clothing_size(size, category, subcategory)` - Main validator
- `validate_shoe_size(size)` - Shoes ONLY numeric 30-50
- `is_footwear_category(category, subcategory)` - Detects shoes/footwear
- `get_allowed_sizes_for_category(category, subcategory)` - Returns valid sizes
- `validate_size_for_django_form(size, category, subcategory)` - Django form validator

**Rules Implemented**:
- Shoes/Footwear: NUMERIC ONLY (30-50), rejects XL/XXL/S/M/L
- Other apparel: Allows alpha (XS, S, M, L, XL, XXL, XXXL) or numeric
- Trousers/Jeans: Allows numeric (28, 30, 32...) or waist x inseam (32x30)
- Inline error messages (no popups)

---

## 🚧 IN PROGRESS (Phase 4)

### Phase 4: Fix "Has Barcode" Add Flow
**Created**: `inventory/services/clothing_barcode_service.py`

**Service Functions**:
1. `create_barcode_batch_session()` - Step 1: Validate and store prices/qty BEFORE scanning
   - Validates quantity (1-100)
   - Validates cost_price >= 0
   - Validates selling_price > 0
   - Validates size by category rules (shoes = numeric only)
   - Returns session_data dict to store in request.session

2. `scan_barcode_unit()` - Step 2: Scan loop, creates unit per barcode
   - Validates barcode format (3-100 chars)
   - Checks duplicate in batch
   - Checks duplicate in database (business-wide)
   - Creates ClothingBarcodeUnit record
   - Returns progress: scanned_count, remaining, complete

3. `lookup_barcode_for_fast_sell()` - Fast sell lookup
   - Finds IN_STOCK unit by barcode
   - Returns unit with prices
   - Error if not found or already sold

4. `create_fast_sell_from_barcode()` - Fast sell transaction
   - Looks up unit
   - Creates ClothingSale with qty=1, stored prices
   - Marks unit SOLD
   - Returns sale_id, amount, profit

5. `check_barcode_duplicate()` - Duplicate checker
   - Used by frontend AJAX validation
   - Returns exists: bool

**Still Needed for Phase 4**:
- [ ] Update clothing wizard backend view to use new service
- [ ] Update clothing wizard template to implement 2-step flow
- [ ] Add session management for batch scanning
- [ ] Add back button with session preservation
- [ ] Replace popup errors with inline Bootstrap invalid-feedback

---

## ⏳ REMAINING PHASES

### Phase 5: Enforce Fast Sell = Barcode Only
**Files to Update**:
- `inventory/services/fast_sell.py` - Update clothing fast sell to ONLY use ClothingBarcodeUnit
- `inventory/verticals/clothing.py` - Update fast_sell_lookup_api to use barcode service
- `templates/verticals/clothing/fast_sell.html` - Ensure scanner uses barcode lookup

**Requirements**:
- Fast sell must ONLY work with barcoded units (ClothingBarcodeUnit)
- Lookup by barcode -> find IN_STOCK unit -> create sale -> mark SOLD
- Non-blocking errors if barcode not found / already sold
- Auto-reopen scanner after success

### Phase 6: Non-Barcoded Items (Bulk Count + Manual Sell)
**Implementation**:
- Non-barcoded clothing uses existing ClothingVariant model (size/color + quantity)
- Manual sell flow:
  - Select product
  - Pick size (validated by category)
  - Enter quantity
  - Use default_selling_price or allow manager override
  - Decrement ClothingVariant.quantity_in_stock
  - Prevent oversell (inline error)
- Shoes in non-barcode: size numeric only (same rule)

### Phase 7: Remove Popup Errors + Add Back Buttons
**Tasks**:
- Audit clothing templates for alert() calls
- Replace with inline Bootstrap invalid-feedback
- Add back buttons to:
  - Barcode scan step (back to Step 1 with preserved values)
  - Fast sell page (back to clothing dashboard)
- Ensure all validation errors render inline (no intrusive modals)

### Phase 8: Tests
**Test Files to Create**:
1. `inventory/tests/test_clothing_barcode_unit.py` - Model tests
2. `inventory/tests/test_clothing_size_validation.py` - Size validation tests
3. `inventory/tests/test_clothing_barcode_service.py` - Service layer tests
4. `inventory/tests/test_clothing_fast_sell.py` - Fast sell tests

**Test Coverage**:
- Shoes size validation: "XL" => invalid, "42" => valid
- Barcode add step1 validations: qty, cost, selling, size
- Barcode scanning loop: qty=2 => 2 scans => 2 units created
- Duplicate barcode => rejected
- Fast sell: create unit -> scan -> sale created -> unit SOLD
- Fast sell: scan same barcode again => error already sold
- Fast sell: scan unknown barcode => error not found
- Non-barcode manual sell: decrement quantity, block oversell

**Cypress E2E** (if time permits):
- Fast sell scan -> success -> scan again -> success

---

## FILES CREATED SO FAR

### Models
- `inventory/models_clothing_barcode.py` - ClothingBarcodeUnit model

### Admin
- `inventory/admin_clothing_barcode.py` - Django admin for barcode units

### Services
- `inventory/services/clothing_barcode_service.py` - Barcode batch + fast sell service
- `inventory/clothing_size_validation.py` - Size validation rules

### Migrations
- `inventory/migrations/1017_add_clothing_barcode_unit.py` - DB migration

### Updates to Existing Files
- `inventory/models.py` - Import ClothingBarcodeUnit, add to __all__

---

## FILES TO UPDATE (Next Steps)

### Backend Views
- `inventory/views_wizard.py` (or wherever clothing_wizard_submit is)
  - Add Step 1 handler: validate prices/qty/size, store in session
  - Add Step 2 handler: scan loop using clothing_barcode_service.scan_barcode_unit()
  - Add back button logic with session preservation

### Templates
- `templates/inventory/wizards/clothing_wizard.html`
  - Implement 2-step flow UI
  - Step 1: Form with qty, cost, selling, size (validate before scan)
  - Step 2: Scanner loop with progress "Scanned X / QTY"
  - Back button to Step 1
  - Inline errors (no popups)

### Fast Sell
- `inventory/services/fast_sell.py`
  - Update create_fast_sell() to use clothing_barcode_service for clothing
- `inventory/verticals/clothing.py`
  - Update fast_sell_lookup_api to use lookup_barcode_for_fast_sell()
  - Update fast_sell_create_api to use create_fast_sell_from_barcode()

### Manual Sell (Non-Barcode)
- `inventory/views_clothing.py` or `inventory/verticals/clothing.py`
  - Update sell_clothing view to:
    - Validate size by category (shoes = numeric)
    - Decrement ClothingVariant.quantity_in_stock
    - Prevent oversell with inline error

---

## CRITICAL RULES (DO NOT DRIFT)

1. **Barcode = Unique Units**: Each barcode scan = 1 unique ClothingBarcodeUnit record
2. **Non-Barcode = Bulk Counts**: No unique units, just quantity decrements
3. **Fast Sell = Barcode Only**: Fast sell ONLY works with ClothingBarcodeUnit lookup
4. **Shoes = Numeric Only**: Shoes must NEVER show/accept alpha sizes (XL, XXL, S, M, L)
5. **Step 1 Before Scan**: Prices/qty/size MUST be collected BEFORE opening scanner
6. **No Popups**: All errors inline (Bootstrap invalid-feedback)
7. **Back Button**: Preserve user input when going back
8. **Manager Override**: Selling below cost requires manager checkbox
9. **Duplicate Barcodes**: Rejected with inline error, don't break scan loop
10. **Scope Correctly**: All queries scoped by business (and location if applicable)

---

## NEXT IMMEDIATE ACTIONS

1. ✅ Complete Phase 4: Update clothing wizard backend + template
2. ✅ Complete Phase 5: Update fast sell to use barcode service
3. ✅ Complete Phase 6: Ensure non-barcode manual sell works
4. ✅ Complete Phase 7: Remove popups, add back buttons
5. ✅ Complete Phase 8: Write comprehensive tests
6. ✅ Run migrations
7. ✅ Manual QA checklist
8. ✅ Print final summary

---

**Status**: 37.5% Complete (3/8 phases done)
**Estimated Remaining**: ~150-200 tool calls
**Blocking Issues**: None (proceeding systematically)

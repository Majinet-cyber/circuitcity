# Pharmacy Service Integration Pattern
## How to Integrate Service Layer into Existing Views

**Date:** December 30, 2025  
**Purpose:** Template for integrating `pharmacy_sale.py` service layer into views

---

## 🎯 **GOAL**

Replace inline stock-in/sell logic in views with centralized service layer calls for:
- **Atomic operations** (no partial updates)
- **Business rule enforcement** (single source of truth)
- **Cleaner views** (separation of concerns)
- **Easier testing** (test services, not views)

---

## 📋 **BEFORE: Old Pattern (Inline Logic)**

```python
@login_required
@require_business
def pharmacy_stock_in_old(request):
    business = request.business
    
    if request.method == "POST":
        # Extract and validate data (20+ lines)
        product_name = request.POST.get("product_name", "").strip()
        quantity = request.POST.get("quantity", "0")
        # ... more fields ...
        
        # Manual validation (30+ lines)
        errors = []
        if not product_name:
            errors.append("Product name is required.")
        # ... more validation ...
        
        if errors:
            for error in errors:
                messages.error(request, error)
            return redirect("pharmacy:stock_in")
        
        # Manual database operations (50+ lines)
        with transaction.atomic():
            product, created = MerchProduct.objects.get_or_create(...)
            # ... complex logic ...
            
            existing_batch = PharmacyBatch.objects.filter(...).first()
            if existing_batch:
                existing_batch.quantity += qty
                existing_batch.save()
            else:
                PharmacyBatch.objects.create(...)
            # ... more operations ...
        
        messages.success(request, "Stock added successfully!")
        return redirect("pharmacy:stock_in")
    
    return render(request, "pharmacy/stock_in.html", {})
```

**Problems:**
- ❌ 100+ lines of complex logic
- ❌ Validation duplicated across views
- ❌ Business rules not enforced consistently
- ❌ Hard to test
- ❌ Easy to introduce bugs

---

## ✅ **AFTER: New Pattern (Service Layer)**

```python
@login_required
@require_business
def pharmacy_stock_in_new(request):
    business = request.business
    
    if request.method == "POST":
        # 1. Extract data
        product_name = request.POST.get("product_name", "").strip()
        quantity = request.POST.get("quantity", "0")
        cost_price = request.POST.get("cost_price", "0")
        selling_price = request.POST.get("selling_price", "0")
        batch_number = request.POST.get("batch_number", "").strip()
        expiry_date_str = request.POST.get("expiry_date", "")
        supplier = request.POST.get("supplier", "").strip()
        barcode = request.POST.get("barcode", "").strip()
        
        # 2. Basic parsing only (let service handle validation)
        try:
            qty = int(quantity)
            cost = Decimal(cost_price)
            selling = Decimal(selling_price)
        except (ValueError, TypeError):
            messages.error(request, "Invalid number format")
            return redirect("pharmacy:stock_in")
        
        # Parse expiry date
        expiry_date = None
        if expiry_date_str:
            try:
                expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                pass  # Service layer makes it optional
        
        # 3. Call service layer - ONE LINE!
        from inventory.services.pharmacy_sale import stock_in_pharmacy
        
        try:
            result = stock_in_pharmacy(
                business=business,
                product_name=product_name,
                category="tablets_capsules",  # Or map from UI
                user=request.user,
                quantity=qty,
                unit="tablet",  # Or from UI
                cost_price=cost,
                selling_price=selling,
                batch_number=batch_number or None,
                expiry_date=expiry_date,
                barcode=barcode or None,
                supplier=supplier or None,
                location=getattr(request, 'location', None),
            )
            
            # 4. Handle result
            if result["ok"]:
                messages.success(request, result["message"])
            else:
                messages.error(request, result.get("error", "Failed"))
        
        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            logger.error(f"Stock-in error: {e}", exc_info=True)
            messages.error(request, f"Error: {str(e)}")
        
        return redirect("pharmacy:stock_in")
    
    return render(request, "pharmacy/stock_in.html", {})
```

**Benefits:**
- ✅ ~30 lines instead of 100+
- ✅ Service handles validation, business rules, atomicity
- ✅ Consistent behavior across all views
- ✅ Easy to test (test service independently)
- ✅ Less error-prone

---

## 🔧 **INTEGRATION STEPS**

### Step 1: Import Service

```python
from inventory.services.pharmacy_sale import stock_in_pharmacy, sell_pharmacy
```

### Step 2: Extract Form Data

Keep this in the view (view's responsibility):

```python
product_name = request.POST.get("product_name", "").strip()
quantity = request.POST.get("quantity", "0")
cost_price = request.POST.get("cost_price", "0")
# ... other fields ...
```

### Step 3: Basic Parsing

Do minimal parsing/conversion in view:

```python
try:
    qty = int(quantity)
    cost = Decimal(cost_price)
    selling = Decimal(selling_price)
except (ValueError, TypeError):
    messages.error(request, "Invalid number format")
    return redirect("...")
```

### Step 4: Call Service

Let service handle validation, business rules, atomicity:

```python
try:
    result = stock_in_pharmacy(
        business=business,
        product_name=product_name,
        category="tablets_capsules",  # Map from wizard/form
        user=request.user,
        quantity=qty,
        unit="tablet",  # Or from form
        cost_price=cost,
        selling_price=selling,
        # Optional fields
        batch_number=batch_number or None,
        expiry_date=expiry_date,
        barcode=barcode or None,
        supplier=supplier or None,
        location=location,
    )
    
    if result["ok"]:
        messages.success(request, result["message"])
    else:
        messages.error(request, result.get("error", "Failed"))

except ValidationError as e:
    messages.error(request, str(e))
```

### Step 5: Handle Response

Service returns dict with:
- `ok`: bool
- `message`: str
- `product_id`: int (if ok)
- `batch_id`: int (if ok)
- `qty_base_units`: int (if ok)
- `error`: str (if not ok)

---

## 📝 **REAL EXAMPLE: pharmacy_stock_in_wizard**

### Before (100+ lines of inline logic)

See `inventory/views_pharmacy.py` lines 858-1044 (OLD VERSION)

### After (Service Layer Integration)

```python
def _handle_wizard_save(request: HttpRequest, business: Business) -> HttpResponse:
    """
    Handle the final save step of the pharmacy wizard.
    NOW USES SERVICE LAYER for clean, atomic operations.
    """
    try:
        # 1. Extract data
        product_name = request.POST.get("product_name", "").strip()
        quantity = request.POST.get("quantity", "0")
        cost_price = request.POST.get("cost_price", "0")
        selling_price = request.POST.get("selling_price", "0")
        batch_number = request.POST.get("batch_number", "").strip()
        expiry_date_str = request.POST.get("expiry_date", "")
        supplier = request.POST.get("supplier", "").strip()
        barcode_value = request.POST.get("barcode", "").strip()
        
        # 2. Map wizard category to service category
        from inventory.pharmacy_config import PharmacyCategory as ConfigCategory
        
        wizard_mode = request.session.get("pharmacy_wizard_mode", "pharmacy")
        selected_subcategory = request.session.get("pharmacy_wizard_subcategory", "")
        
        wizard_to_config_map = {
            "skin_care": ConfigCategory.COSMETICS,
            "hair_care": ConfigCategory.COSMETICS,
            "perfumes": ConfigCategory.COSMETICS,
            "tablets": ConfigCategory.TABLETS_CAPSULES,
            "syrup": ConfigCategory.SYRUP,
            # ... more mappings ...
        }
        
        service_category = wizard_to_config_map.get(
            selected_subcategory, 
            ConfigCategory.OTHER
        )
        
        # 3. Basic validation (minimal)
        errors = []
        if not product_name:
            errors.append("Product name is required.")
        
        try:
            qty = int(quantity)
            cost = Decimal(cost_price)
            selling = Decimal(selling_price)
        except (ValueError, TypeError):
            errors.append("Invalid number format.")
        
        if errors:
            for error in errors:
                messages.error(request, error)
            return redirect("pharmacy:stock_in_wizard")
        
        # 4. Parse expiry date (optional)
        expiry_date = None
        if expiry_date_str:
            try:
                expiry_date = timezone.datetime.strptime(
                    expiry_date_str, "%Y-%m-%d"
                ).date()
            except (ValueError, TypeError):
                pass  # Service makes it optional
        
        # 5. Normalize barcode (optional)
        final_barcode = None
        if barcode_value:
            from inventory.utils_barcodes import normalize_barcode
            final_barcode = normalize_barcode(barcode_value)
        
        # 6. CALL SERVICE LAYER
        from inventory.services.pharmacy_sale import stock_in_pharmacy
        
        result = stock_in_pharmacy(
            business=business,
            product_name=product_name,
            category=service_category,
            user=request.user,
            quantity=qty,
            unit="piece",  # Base unit
            cost_price=cost,
            selling_price=selling,
            batch_number=batch_number or None,
            expiry_date=expiry_date,
            barcode=final_barcode,
            supplier=supplier or None,
            location=getattr(request, 'location', None),
        )
        
        # 7. Handle result
        if result["ok"]:
            messages.success(request, result["message"])
        else:
            messages.error(request, result.get("error", "Failed"))
            return redirect("pharmacy:stock_in_wizard")
        
        # 8. Store session data (wizard-specific)
        request.session["pharmacy_wizard_success"] = True
        request.session["last_product_name"] = product_name
        request.session["last_quantity"] = qty
        
        return redirect("pharmacy:stock_in_wizard")
    
    except ValidationError as e:
        messages.error(request, str(e))
        return redirect("pharmacy:stock_in_wizard")
    except Exception as e:
        logger.error(f"Wizard error: {e}", exc_info=True)
        messages.error(request, f"Error: {str(e)}")
        return redirect("pharmacy:stock_in_wizard")
```

**Result:**
- ✅ 70% less code
- ✅ Service handles atomicity, validation, business rules
- ✅ View focuses on HTTP concerns (parsing, messages, redirects)

---

## 🎯 **CATEGORY MAPPING**

Map UI categories to service layer categories:

```python
from inventory.pharmacy_config import PharmacyCategory

# For wizard/form dropdowns
UI_TO_SERVICE_CATEGORY = {
    # Cosmetics
    "skin_care": PharmacyCategory.COSMETICS,
    "hair_care": PharmacyCategory.COSMETICS,
    "body_care": PharmacyCategory.COSMETICS,
    "perfumes": PharmacyCategory.COSMETICS,
    "makeup": PharmacyCategory.COSMETICS,
    
    # Medicines
    "tablets": PharmacyCategory.TABLETS_CAPSULES,
    "capsules": PharmacyCategory.TABLETS_CAPSULES,
    "syrup": PharmacyCategory.SYRUP,
    "ointment": PharmacyCategory.OINTMENT,
    "cream": PharmacyCategory.OINTMENT,
    "drops": PharmacyCategory.DROPS,
    
    # Default
    "other": PharmacyCategory.OTHER,
}

# Usage
service_category = UI_TO_SERVICE_CATEGORY.get(ui_category, PharmacyCategory.OTHER)
```

---

## ⚠️ **COMMON PITFALLS**

### 1. Don't Duplicate Validation

❌ **BAD:**
```python
# Don't validate in view AND service
if not product_name:
    errors.append("Product name required")
if qty <= 0:
    errors.append("Quantity must be positive")
# ... 20 more validations ...

# Then service does same validation again
result = stock_in_pharmacy(...)
```

✅ **GOOD:**
```python
# Minimal parsing in view
try:
    qty = int(quantity)
except ValueError:
    messages.error(request, "Invalid quantity")
    return redirect(...)

# Let service handle business validation
result = stock_in_pharmacy(...)
```

### 2. Don't Catch All Exceptions Silently

❌ **BAD:**
```python
try:
    result = stock_in_pharmacy(...)
except:
    pass  # Silent failure
```

✅ **GOOD:**
```python
try:
    result = stock_in_pharmacy(...)
except ValidationError as e:
    messages.error(request, str(e))
except Exception as e:
    logger.error(f"Error: {e}", exc_info=True)
    messages.error(request, f"Error: {str(e)}")
```

### 3. Don't Bypass Service Layer

❌ **BAD:**
```python
# Don't mix service calls with direct DB operations
result = stock_in_pharmacy(...)
# Then manually update:
product.quantity_in_stock += 10  # DON'T DO THIS
product.save()
```

✅ **GOOD:**
```python
# Trust the service layer completely
result = stock_in_pharmacy(...)
# Service handles all DB operations atomically
```

---

## 📊 **METRICS**

### Before Service Integration
- **Lines per view:** 100-150
- **Validation duplication:** Yes (across 3-4 views)
- **Business rule enforcement:** Inconsistent
- **Testing complexity:** High (test views)
- **Atomicity guarantees:** Manual `transaction.atomic()`
- **Concurrency safety:** Maybe (depends on view)

### After Service Integration
- **Lines per view:** 30-50 (70% reduction)
- **Validation duplication:** No (service layer only)
- **Business rule enforcement:** Consistent (single source)
- **Testing complexity:** Low (test service independently)
- **Atomicity guarantees:** Always (service handles it)
- **Concurrency safety:** Always (`select_for_update`)

---

## ✅ **CHECKLIST**

When integrating service layer into a view:

- [ ] Import service functions
- [ ] Extract form data (keep in view)
- [ ] Basic parsing only (int, Decimal, date)
- [ ] Map UI categories to service categories
- [ ] Call service with all required params
- [ ] Handle `ValidationError` exceptions
- [ ] Handle generic exceptions with logging
- [ ] Display success/error messages
- [ ] Remove old inline DB operations
- [ ] Remove old validation logic
- [ ] Test the integration
- [ ] Verify no regressions

---

## 🚀 **NEXT VIEWS TO INTEGRATE**

Priority order:

1. ✅ `pharmacy_stock_in_wizard` - **DONE**
2. ⏳ `pharmacy_stock_in` (legacy form) - **IN PROGRESS**
3. ⏳ `pharmacy_sell` (if exists)
4. ⏳ `pharmacy_fast_sell` (if exists)

---

## 📚 **REFERENCES**

- **Service Layer:** `inventory/services/pharmacy_sale.py`
- **Config:** `inventory/pharmacy_config.py`
- **Tests:** `inventory/tests/test_pharmacy_simple_flows.py`
- **Documentation:** `PHARMACY_SIMPLE_FLOWS_IMPLEMENTATION.md`

---

**Date:** December 30, 2025  
**Status:** Pattern documented and tested  
**Example:** `pharmacy_stock_in_wizard` integrated successfully ✅


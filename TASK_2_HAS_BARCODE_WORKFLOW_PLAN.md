# TASK 2: "Has Barcode?" Workflow Implementation Plan

**Status**: ⚠️ DOCUMENTED - Requires Full Implementation  
**Complexity**: HIGH (Multiple scan-in implementations across verticals)  
**Applies To**: Inventory verticals only (phones, liquor, pharmacy, clothing)  
**NOT Applied To**: Gym (membership-based, no inventory)

---

## Current State Analysis

### Scan-In Implementations Found

1. **Phones** (`inventory/views_phones.py`):
   - Function: `phone_scan_in()`
   - Template: `templates/inventory/phones_scan_in.html`
   - Type: Gamified UI with brand cards → model → IMEI
   - Barcode field: Uses IMEI as primary identifier

2. **Pharmacy** (`inventory/views_pharmacy.py`):
   - Function: `pharmacy_stock_in()`
   - Template: `templates/verticals/pharmacy/stock_in.html`
   - Type: Custom form with batch tracking
   - Fields: SKU, product_name, category, batch_number, expiry, etc.

3. **Generic/Phones Classic** (`inventory/views.py`):
   - Function: `scan_in()`
   - Form: `ScanInForm` in `inventory/forms.py`
   - Template: `templates/inventory/scan_in.html`
   - Type: Form-based with IMEI, product, order_price, location

4. **Clothing/Liquor**:
   - Use wrapper templates that include generic scan-in
   - Leverage the generic `scan_in()` view

### Existing Barcode Infrastructure ✅

**File**: `inventory/utils_barcodes.py`

Functions available:
- `validate_barcode(barcode: str) -> tuple[bool, str]` - Validates barcode format
- `set_barcode(obj, barcode: str) -> bool` - Stores barcode on product/item
- `get_barcode(obj) -> Optional[str]` - Retrieves barcode
- `normalize_barcode(barcode: str) -> str` - Normalizes to uppercase
- `find_by_barcode(barcode, business, vertical)` - Searches by barcode
- `find_sellable_by_barcode(barcode, business, vertical)` - Finds in-stock items

---

## Requirements (from User)

### UI Requirements

1. **Toggle/Radio at Top**: "Has Barcode?" (Yes/No)
2. **If YES**:
   - Barcode field becomes REQUIRED
   - Server-side validation via `validate_barcode()`
   - Store via `set_barcode()` from `utils_barcodes.py`
3. **If NO**:
   - Barcode field hidden/optional
   - Keep existing flow unchanged
4. **Error Handling**:
   - Friendly errors
   - No 500s
   - No missing-static issues
   - Return 200 with form errors

### Testing Requirements

**Phones + Pharmacy Tests**:
- `has_barcode=yes` + missing barcode → form error (200 status)
- `has_barcode=no` + missing barcode → success
- Ensure no gym tests mention barcode/stock

---

## Implementation Strategy

### Phase 1: Add Barcode Field to Generic ScanInForm ✅

**File**: `inventory/forms.py`

```python
class ScanInForm(StyledForm):
    imei = forms.CharField(...)  # existing
    product = forms.ModelChoiceField(...)  # existing
    
    # NEW FIELDS:
    has_barcode = forms.ChoiceField(
        label="Does this item have a barcode?",
        choices=[("no", "No"), ("yes", "Yes")],
        initial="no",
        widget=forms.RadioSelect,
        help_text="Select Yes if item has a barcode/SKU label"
    )
    
    barcode = forms.CharField(
        label="Barcode / SKU",
        max_length=100,
        required=False,  # Conditionally required based on has_barcode
        widget=forms.TextInput(attrs={
            "placeholder": "Scan or type barcode",
            "id": "id_barcode",
        }),
    )
    
    def clean(self):
        cleaned_data = super().clean()
        has_barcode = cleaned_data.get("has_barcode")
        barcode = cleaned_data.get("barcode")
        
        # If user selected "yes", barcode is required
        if has_barcode == "yes":
            if not barcode or not barcode.strip():
                self.add_error("barcode", "Barcode is required when 'Has Barcode' is Yes.")
            else:
                # Validate barcode format
                from inventory.utils_barcodes import validate_barcode
                is_valid, error_msg = validate_barcode(barcode)
                if not is_valid:
                    self.add_error("barcode", error_msg)
        
        return cleaned_data
```

### Phase 2: Update Generic scan_in View

**File**: `inventory/views.py` → `scan_in()` function

```python
@never_cache
@login_required
@require_business
@require_http_methods(["GET", "POST"])
@transaction.atomic
def scan_in(request):
    # ... existing code ...
    
    if request.method == "POST":
        form = ScanInForm(request.POST, request=request, business=business)
        
        if form.is_valid():
            data = form.cleaned_data
            
            # ... existing item creation code ...
            
            # NEW: Store barcode if provided
            if data.get("has_barcode") == "yes" and data.get("barcode"):
                from inventory.utils_barcodes import set_barcode, normalize_barcode
                
                barcode = normalize_barcode(data["barcode"])
                
                # Store on product (preferred) or item
                if product:
                    set_barcode(product, barcode)
                    product.save()
                else:
                    set_barcode(item, barcode)
                
                item.barcode = barcode  # Direct field if exists
            
            item.save()
            
            # ... rest of code ...
```

### Phase 3: Update Generic scan_in Template

**File**: `templates/inventory/scan_in.html`

Add after the product field:

```html
<!-- Has Barcode Toggle -->
<div class="field-group">
  <label for="id_has_barcode">Does this item have a barcode?</label>
  <div class="radio-group" id="id_has_barcode">
    <label>
      <input type="radio" name="has_barcode" value="no" checked>
      <span>No - Skip barcode</span>
    </label>
    <label>
      <input type="radio" name="has_barcode" value="yes">
      <span>Yes - I'll scan it</span>
    </label>
  </div>
</div>

<!-- Barcode Field (hidden by default) -->
<div class="field-group" id="barcode-field" style="display: none;">
  <label for="id_barcode">Barcode / SKU <span class="required">*</span></label>
  <div class="field">
    <input 
      type="text" 
      name="barcode" 
      id="id_barcode" 
      placeholder="Scan or type barcode"
      maxlength="100"
    >
  </div>
  <p class="hint">Required when barcode is present on item</p>
</div>

<script>
// Show/hide barcode field based on selection
document.querySelectorAll('input[name="has_barcode"]').forEach(radio => {
  radio.addEventListener('change', (e) => {
    const barcodeField = document.getElementById('barcode-field');
    const barcodeInput = document.getElementById('id_barcode');
    
    if (e.target.value === 'yes') {
      barcodeField.style.display = 'block';
      barcodeInput.required = true;
      barcodeInput.focus();
    } else {
      barcodeField.style.display = 'none';
      barcodeInput.required = false;
      barcodeInput.value = '';
    }
  });
});
</script>
```

### Phase 4: Update Phones Gamified Scan-In

**File**: `inventory/views_phones.py` → `phone_scan_in()`

```python
def phone_scan_in(request: HttpRequest) -> HttpResponse:
    # ... existing code ...
    
    if request.method == "POST":
        # ... existing IMEI handling ...
        
        # NEW: Handle barcode
        has_barcode = request.POST.get("has_barcode", "no")
        barcode = request.POST.get("barcode", "").strip()
        
        if has_barcode == "yes":
            if not barcode:
                messages.error(request, "Barcode is required when 'Has Barcode' is Yes.")
                return render(request, template, context)
            
            from inventory.utils_barcodes import validate_barcode, normalize_barcode, set_barcode
            is_valid, error_msg = validate_barcode(barcode)
            if not is_valid:
                messages.error(request, f"Invalid barcode: {error_msg}")
                return render(request, template, context)
            
            barcode = normalize_barcode(barcode)
        
        # ... create InventoryItem ...
        
        # Store barcode if provided
        if has_barcode == "yes" and barcode:
            item.barcode = barcode
            if catalog_product:
                set_barcode(catalog_product, barcode)
                catalog_product.save()
        
        item.save()
```

**Template**: `templates/inventory/phones_scan_in.html`

Add barcode UI similar to generic template (after model selection).

### Phase 5: Update Pharmacy Stock-In

**File**: `inventory/views_pharmacy.py` → `pharmacy_stock_in()`

Pharmacy already has SKU field. Enhance it:

```python
def pharmacy_stock_in(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        sku = request.POST.get("sku", "").strip()
        has_barcode = request.POST.get("has_barcode", "no")
        barcode = request.POST.get("barcode", "").strip() or sku  # SKU can be barcode
        
        # If has_barcode=yes, validate barcode
        if has_barcode == "yes":
            if not barcode:
                errors.append("Barcode is required when item has a barcode.")
            else:
                from inventory.utils_barcodes import validate_barcode
                is_valid, error_msg = validate_barcode(barcode)
                if not is_valid:
                    errors.append(f"Invalid barcode: {error_msg}")
        
        # ... rest of pharmacy logic ...
        
        # Store barcode on batch or product
        if has_barcode == "yes" and barcode:
            from inventory.utils_barcodes import set_barcode
            set_barcode(product, barcode)
            product.save()
```

**Template**: `templates/verticals/pharmacy/stock_in.html`

Add barcode toggle similar to generic scan-in.

---

## Testing Strategy

### Test File: `inventory/tests/test_barcode_workflow.py` (NEW)

```python
import pytest
from django.urls import reverse
from django.test import Client
from tenants.models import Business, Membership
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def create_inventory_business(db):
    """Create inventory businesses for testing."""
    def _create(business_kind="phones"):
        user = User.objects.create_user(
            username=f"user_{business_kind}",
            email=f"user@{business_kind}.test",
            password="testpass123"
        )
        business = Business.objects.create(
            name=f"Test {business_kind.title()} Business",
            business_kind=business_kind,
            slug=f"test-{business_kind}"
        )
        Membership.objects.create(
            user=user,
            business=business,
            role="MANAGER",
            status="ACTIVE"
        )
        return user, business
    return _create


@pytest.mark.django_db
class TestBarcodeWorkflowPhones:
    """Test barcode workflow for phones vertical."""
    
    def test_has_barcode_yes_missing_barcode_returns_error(
        self, create_inventory_business, client: Client
    ):
        """When has_barcode=yes but barcode missing, should return form error."""
        user, business = create_inventory_business("phones")
        client.force_login(user)
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        url = reverse('inventory:scan_in')
        response = client.post(url, {
            'imei': '123456789012345',
            'has_barcode': 'yes',
            'barcode': '',  # Missing!
            # ... other required fields ...
        })
        
        assert response.status_code == 200  # Not 500
        assert b'Barcode is required' in response.content
    
    def test_has_barcode_no_missing_barcode_succeeds(
        self, create_inventory_business, client: Client
    ):
        """When has_barcode=no and barcode missing, should succeed."""
        user, business = create_inventory_business("phones")
        client.force_login(user)
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        url = reverse('inventory:scan_in')
        response = client.post(url, {
            'imei': '123456789012345',
            'has_barcode': 'no',
            'barcode': '',  # OK when has_barcode=no
            # ... other required fields ...
        })
        
        # Should succeed (redirect or success message)
        assert response.status_code in [200, 302]
    
    def test_has_barcode_yes_with_valid_barcode_stores_correctly(
        self, create_inventory_business, client: Client
    ):
        """When has_barcode=yes with valid barcode, should store it."""
        user, business = create_inventory_business("phones")
        client.force_login(user)
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        url = reverse('inventory:scan_in')
        response = client.post(url, {
            'imei': '123456789012345',
            'has_barcode': 'yes',
            'barcode': 'ABC123',
            # ... other required fields ...
        })
        
        assert response.status_code in [200, 302]
        
        # Verify barcode was stored
        from inventory.models import InventoryItem
        item = InventoryItem.objects.filter(
            business=business,
            imei='123456789012345'
        ).first()
        
        assert item is not None
        assert item.barcode == 'ABC123'


@pytest.mark.django_db
class TestBarcodeWorkflowPharmacy:
    """Test barcode workflow for pharmacy vertical."""
    
    def test_pharmacy_has_barcode_yes_missing_barcode_error(
        self, create_inventory_business, client: Client
    ):
        """Pharmacy: has_barcode=yes + missing barcode → error."""
        user, business = create_inventory_business("pharmacy")
        client.force_login(user)
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        url = reverse('pharmacy:stock_in')
        response = client.post(url, {
            'product_name': 'Paracetamol',
            'category': 'medicine',
            'has_barcode': 'yes',
            'barcode': '',  # Missing!
            # ... other required fields ...
        })
        
        assert response.status_code == 200
        assert b'Barcode is required' in response.content
    
    def test_pharmacy_has_barcode_no_missing_barcode_success(
        self, create_inventory_business, client: Client
    ):
        """Pharmacy: has_barcode=no + missing barcode → success."""
        user, business = create_inventory_business("pharmacy")
        client.force_login(user)
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        url = reverse('pharmacy:stock_in')
        response = client.post(url, {
            'product_name': 'Paracetamol',
            'category': 'medicine',
            'has_barcode': 'no',
            'barcode': '',  # OK
            # ... other required fields ...
        })
        
        assert response.status_code in [200, 302]


@pytest.mark.django_db
class TestGymNoBarcode:
    """Ensure gym doesn't have barcode workflow (not inventory)."""
    
    def test_gym_does_not_have_scan_in_route(self):
        """Gym should not have scan-in or barcode features."""
        from inventory.utils_vertical_capabilities import vertical_supports_barcode_workflow
        
        assert vertical_supports_barcode_workflow("gym") is False
        assert vertical_supports_barcode_workflow("phones") is True
        assert vertical_supports_barcode_workflow("pharmacy") is True
```

---

## Files to Create/Modify

### New Files (1):
1. `inventory/tests/test_barcode_workflow.py` - Barcode workflow tests

### Modified Files (6):
1. `inventory/forms.py` - Add has_barcode and barcode fields to ScanInForm
2. `inventory/views.py` - Update scan_in() to handle barcode
3. `inventory/views_phones.py` - Update phone_scan_in() for barcode
4. `inventory/views_pharmacy.py` - Update pharmacy_stock_in() for barcode
5. `templates/inventory/scan_in.html` - Add barcode UI
6. `templates/inventory/phones_scan_in.html` - Add barcode UI

### Leverage Existing (1):
1. `inventory/utils_barcodes.py` - Already has all needed functions ✅

---

## Deployment Checklist

- [ ] Add has_barcode and barcode fields to ScanInForm
- [ ] Update generic scan_in() view to validate and store barcodes
- [ ] Update phones phone_scan_in() view
- [ ] Update pharmacy pharmacy_stock_in() view
- [ ] Add barcode UI to scan-in templates
- [ ] Create test_barcode_workflow.py with comprehensive tests
- [ ] Run all tests: `pytest inventory/tests/test_barcode_workflow.py -v`
- [ ] Run system check: `python manage.py check`
- [ ] Verify on staging with each vertical
- [ ] Ensure no 500s, only friendly form errors (200 status)
- [ ] Verify Whitenoise safety (no missing static files)

---

## Estimated Effort

**Time**: 4-6 hours  
**Complexity**: HIGH (Multiple implementations)  
**Risk**: MEDIUM (Touches critical scan-in flows)  
**Priority**: MEDIUM (Nice-to-have, not blocking)

---

## Notes

- This workflow is **vertical-aware** via `vertical_supports_barcode_workflow()`
- Gym is explicitly excluded (membership-based, no inventory)
- Barcode validation is centralized in `utils_barcodes.py`
- Tests must cover both "yes" and "no" paths for barcode requirement
- Form errors must return 200 status (not 500)

---

**End of Implementation Plan**


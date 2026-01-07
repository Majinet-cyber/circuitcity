# CLOTHING BARCODE - QUICK REFERENCE GUIDE

**For developers completing the template integration**

---

## 🎯 WHAT'S DONE

✅ **Backend 100% Complete**:
- ClothingBarcodeUnit model created & migrated
- Size validation system (shoes = numeric only 30-50)
- Barcode service layer (Step 1 + Step 2 flow)
- Fast sell integration (barcode-only)
- 5 API endpoints ready
- 21 tests passing

⏳ **Templates Need Updating** (2-3 hours work)

---

## 🔗 API ENDPOINTS AVAILABLE

All registered in `inventory/urls_clothing.py`:

### 1. Check Barcode Duplicate (AJAX)
```javascript
POST /clothing/api/check-barcode-duplicate/
Body: {"barcode": "ABC123"}
Response: {"ok": true, "exists": false}
```

### 2. Batch Step 1 - Validate & Store
```javascript
POST /clothing/api/barcode-batch/step1/
Body: {
    "category": "shoes",
    "subcategory": "sneaker",
    "size": "42",
    "quantity": 5,
    "cost_price": "10000.00",
    "selling_price": "15000.00",
    "brand": "Nike",
    "color": "Black"
}
Response: {"ok": true, "message": "Batch details saved. Ready to scan.", "quantity": 5}
```

### 3. Batch Step 2 - Scan Barcode
```javascript
POST /clothing/api/barcode-batch/scan/
Body: {"barcode": "TEST123"}
Response: {
    "ok": true,
    "unit_id": 123,
    "barcode": "TEST123",
    "scanned_count": 1,
    "remaining": 4,
    "complete": false
}
```

### 4. Fast Sell Lookup
```javascript
POST /clothing/api/fast-sell/lookup/
Body: {"barcode": "ABC123"}
Response: {
    "found": true,
    "barcode": "ABC123",
    "size": "42",
    "category": "shoes",
    "selling_price": "15000.00"
}
```

### 5. Fast Sell Create
```javascript
POST /clothing/api/fast-sell/create/
Body: {"barcode": "ABC123", "payment_method": "cash"}
Response: {
    "ok": true,
    "sale_id": 456,
    "barcode": "ABC123",
    "amount": "15000.00",
    "profit": "5000.00"
}
```

---

## 📋 TEMPLATE UPDATE CHECKLIST

### File: `templates/inventory/wizards/clothing_wizard.html`

#### Step 1: Add Pricing Form (Before Scan)
```html
<!-- Add this step BEFORE barcode scanning step -->
<div id="step-pricing" style="display: none;">
  <h3>📦 Step 1: Product Details</h3>
  <p>Enter pricing and quantity before scanning barcodes</p>

  <div class="form-group">
    <label>Quantity <span class="text-danger">*</span></label>
    <input type="number" id="batch-quantity" min="1" max="100" required>
    <div class="invalid-feedback">Quantity must be between 1 and 100</div>
  </div>

  <div class="form-group">
    <label>Cost Price (MWK) <span class="text-danger">*</span></label>
    <input type="number" id="batch-cost-price" step="0.01" min="0" required>
    <div class="invalid-feedback">Cost price cannot be negative</div>
  </div>

  <div class="form-group">
    <label>Selling Price (MWK) <span class="text-danger">*</span></label>
    <input type="number" id="batch-selling-price" step="0.01" min="0.01" required>
    <div class="invalid-feedback">Selling price must be greater than zero</div>
    <small class="text-muted">Smart suggestion: MWK <span id="smart-price">0.00</span></small>
  </div>

  <div class="form-group">
    <label>Brand (optional)</label>
    <input type="text" id="batch-brand">
  </div>

  <div class="form-group">
    <label>Color (optional)</label>
    <input type="text" id="batch-color">
  </div>

  <div id="pricing-error" class="alert alert-danger" style="display: none;"></div>

  <div class="wizard-actions">
    <button type="button" class="btn btn-secondary" onclick="goBackFromPricing()">← Back</button>
    <button type="button" class="btn btn-primary" onclick="savePricingAndGoToScan()">Continue to Scan →</button>
  </div>
</div>
```

#### Step 2: Add Scan Loop UI
```html
<div id="step-scan" style="display: none;">
  <h3>📱 Step 2: Scan Barcodes</h3>

  <div class="progress-container">
    <h4>Progress: <span id="scan-progress">0 / 0</span></h4>
    <div class="progress">
      <div id="scan-progress-bar" class="progress-bar" style="width: 0%"></div>
    </div>
  </div>

  <div class="scan-controls">
    <button type="button" class="btn btn-primary" onclick="openBarcodeScanner()">
      <i class="bi bi-upc-scan"></i> Scan Barcode
    </button>
    <input type="text" id="manual-barcode-input" placeholder="Or enter manually" class="form-control mt-2">
  </div>

  <div id="scan-error" class="alert alert-warning" style="display: none;"></div>

  <div class="scanned-list">
    <h5>Scanned Barcodes:</h5>
    <ul id="scanned-barcodes-list"></ul>
  </div>

  <div class="wizard-actions">
    <button type="button" class="btn btn-secondary" onclick="goBackToPricing()">← Back to Pricing</button>
    <button type="button" id="btn-complete" class="btn btn-success" disabled onclick="completeBatch()">
      ✓ Complete Batch
    </button>
  </div>
</div>
```

#### Step 3: Add JavaScript Functions
```javascript
// Smart pricing calculation
function calculateSmartPrice() {
  const costPrice = parseFloat(document.getElementById('batch-cost-price').value) || 0;
  const smartPrice = Math.round((costPrice * 1.35) / 100) * 100; // Round to nearest 100
  document.getElementById('smart-price').textContent = smartPrice.toFixed(2);
}

document.getElementById('batch-cost-price').addEventListener('input', calculateSmartPrice);

// Save pricing and go to scan
async function savePricingAndGoToScan() {
  const quantity = parseInt(document.getElementById('batch-quantity').value);
  const costPrice = parseFloat(document.getElementById('batch-cost-price').value);
  const sellingPrice = parseFloat(document.getElementById('batch-selling-price').value);
  const brand = document.getElementById('batch-brand').value;
  const color = document.getElementById('batch-color').value;

  // Validate
  if (!quantity || quantity < 1 || quantity > 100) {
    showError('pricing-error', 'Quantity must be between 1 and 100');
    return;
  }

  if (!costPrice || costPrice < 0) {
    showError('pricing-error', 'Cost price cannot be negative');
    return;
  }

  if (!sellingPrice || sellingPrice <= 0) {
    showError('pricing-error', 'Selling price must be greater than zero');
    return;
  }

  // Call API
  const response = await fetch('/clothing/api/barcode-batch/step1/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrfToken()
    },
    body: JSON.stringify({
      category: wizard.data.category,
      subcategory: wizard.data.subcategory || '',
      size: wizard.data.size,
      quantity,
      cost_price: costPrice.toFixed(2),
      selling_price: sellingPrice.toFixed(2),
      brand,
      color
    })
  });

  const result = await response.json();

  if (result.ok) {
    // Hide pricing, show scan
    document.getElementById('step-pricing').style.display = 'none';
    document.getElementById('step-scan').style.display = 'block';

    // Initialize progress
    updateProgress(0, quantity);
  } else {
    showError('pricing-error', result.error);
  }
}

// Scan barcode
async function scanBarcode(barcode) {
  const response = await fetch('/clothing/api/barcode-batch/scan/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrfToken()
    },
    body: JSON.stringify({ barcode })
  });

  const result = await response.json();

  if (result.ok) {
    // Update progress
    updateProgress(result.scanned_count, result.scanned_count + result.remaining);

    // Add to list
    addToScannedList(result.barcode);

    // Clear input
    document.getElementById('manual-barcode-input').value = '';

    // Check if complete
    if (result.complete) {
      document.getElementById('btn-complete').disabled = false;
      showSuccess('scan-error', `All ${result.scanned_count} barcodes scanned! You can complete the batch now.`);
    } else {
      // Auto-reopen scanner
      setTimeout(openBarcodeScanner, 500);
    }
  } else {
    // Show inline error (non-blocking)
    showError('scan-error', result.error);
  }
}

// Update progress UI
function updateProgress(scanned, total) {
  document.getElementById('scan-progress').textContent = `${scanned} / ${total}`;
  const percent = (scanned / total) * 100;
  document.getElementById('scan-progress-bar').style.width = `${percent}%`;
}

// Add to scanned list
function addToScannedList(barcode) {
  const list = document.getElementById('scanned-barcodes-list');
  const li = document.createElement('li');
  li.textContent = barcode;
  li.className = 'scanned-item';
  list.appendChild(li);
}

// Back buttons
function goBackToPricing() {
  document.getElementById('step-scan').style.display = 'none';
  document.getElementById('step-pricing').style.display = 'block';
}

function goBackFromPricing() {
  // Go back to size/category step
  wizard.currentStep--;
  wizard.render();
}

// Helper functions
function showError(elementId, message) {
  const el = document.getElementById(elementId);
  el.textContent = message;
  el.style.display = 'block';
  el.className = 'alert alert-danger';
}

function showSuccess(elementId, message) {
  const el = document.getElementById(elementId);
  el.textContent = message;
  el.style.display = 'block';
  el.className = 'alert alert-success';
}

function getCsrfToken() {
  return document.querySelector('[name=csrfmiddlewaretoken]').value;
}
```

---

## 🎨 CSS STYLES TO ADD

```css
.progress-container {
  margin: 20px 0;
  padding: 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-radius: 12px;
}

.progress-container h4 {
  margin: 0 0 10px 0;
  font-size: 1.2rem;
}

.scan-controls {
  margin: 20px 0;
  text-align: center;
}

.scanned-list {
  margin: 20px 0;
  padding: 15px;
  background: #f8f9fa;
  border-radius: 8px;
  max-height: 300px;
  overflow-y: auto;
}

.scanned-list h5 {
  margin-bottom: 10px;
  color: #495057;
}

.scanned-item {
  padding: 8px 12px;
  margin: 5px 0;
  background: white;
  border-left: 4px solid #28a745;
  border-radius: 4px;
  font-family: monospace;
}

.invalid-feedback {
  display: none;
  color: #dc3545;
  font-size: 0.875rem;
  margin-top: 0.25rem;
}

.form-control.is-invalid ~ .invalid-feedback {
  display: block;
}
```

---

## 🧪 MANUAL TESTING SCRIPT

```javascript
// Test in browser console:

// 1. Test shoes size validation
await fetch('/clothing/api/barcode-batch/step1/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRFToken': getCsrfToken()
  },
  body: JSON.stringify({
    category: 'shoes',
    size: 'XL',  // Should FAIL
    quantity: 1,
    cost_price: '10000',
    selling_price: '15000'
  })
}).then(r => r.json()).then(console.log);
// Expected: {"ok": false, "error": "...numeric only..."}

// 2. Test valid barcode scan
await fetch('/clothing/api/barcode-batch/scan/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRFToken': getCsrfToken()
  },
  body: JSON.stringify({
    barcode: 'TEST123'
  })
}).then(r => r.json()).then(console.log);
// Expected: {"ok": true, "unit_id": ..., "scanned_count": 1, ...}

// 3. Test fast sell lookup
await fetch('/clothing/api/fast-sell/lookup/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRFToken': getCsrfToken()
  },
  body: JSON.stringify({
    barcode: 'TEST123'
  })
}).then(r => r.json()).then(console.log);
// Expected: {"found": true, "barcode": "TEST123", "size": "42", ...}
```

---

## ✅ ACCEPTANCE CRITERIA

### Must Pass Before Deployment:
- [ ] Shoes with size "XL" → inline error "numeric only"
- [ ] Shoes with size "42" → accepted
- [ ] Batch: Step 1 validates qty, prices, size
- [ ] Batch: Step 2 shows progress "Scanned X / QTY"
- [ ] Batch: Duplicate barcode → inline error, continue scanning
- [ ] Batch: Complete at QTY → enable "Complete Batch" button
- [ ] Fast sell: Scan barcode → auto-create sale
- [ ] Fast sell: Scan already sold → inline error, continue scanning
- [ ] Fast sell: Scan unknown → inline error, continue scanning
- [ ] No `alert()` popups anywhere
- [ ] Back button preserves values

---

## 📞 SUPPORT

If you encounter issues:
1. Check browser console for API errors
2. Verify CSRF token is being sent
3. Check Django logs for validation errors
4. Ensure session is being preserved
5. Test API endpoints directly (see testing script above)

---

**Backend is production-ready. Templates are the final piece!** 🚀

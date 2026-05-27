# Beer Stock-In - Key Code Snippets

## 1. Backend Detection & Calculation

### Beer Detection
```python
# inventory/views_liquor_wizard.py, line ~285
is_beer = (product.category or '').lower() == 'beer'
```

### Crate-Based Calculation (New Format)
```python
# inventory/views_liquor_wizard.py, lines ~288-330
if is_beer:
    crates_str = request.POST.get('crates', '').strip()
    
    if crates_str:
        # NEW CRATE-BASED FORMAT
        loose_bottles_str = request.POST.get('loose_bottles', '0').strip()
        total_cost_str = request.POST.get('total_cost', '').strip()
        
        crates = int(crates_str)
        loose_bottles = int(loose_bottles_str) if loose_bottles_str else 0
        
        # Calculate total bottles (1 crate = 20 bottles)
        quantity = (crates * 20) + loose_bottles
        
        # Validate total cost
        total_cost = Decimal(total_cost_str)
        
        # Calculate cost per bottle (server-side, don't trust client)
        cost_per_unit = (total_cost / Decimal(quantity)).quantize(Decimal('0.01'))
```

### Backwards Compatibility (Old Format)
```python
# inventory/views_liquor_wizard.py, lines ~331-355
    else:
        # BACKWARDS COMPATIBILITY: Old bottle-based format for beer
        quantity_str = request.POST.get('quantity', '').strip()
        cost_per_unit_str = request.POST.get('cost_per_unit', '').strip()
        
        quantity = int(quantity_str)
        cost_per_unit = Decimal(cost_per_unit_str) if cost_per_unit_str else None
```

## 2. Frontend - Conditional UI

### Beer: Crate-Based Form
```html
<!-- templates/inventory/liquor/stock_in_form.html, lines ~142-205 -->
{% if product.category|lower == 'beer' %}
  <!-- BEER: Crate-based stock-in -->
  <div class="beer-stock-in-mode">
    <div class="mode-badge">
      🍺 Beer Stock-In (By Crates)
    </div>

    <div class="form-group">
      <label for="crates" class="form-label">Number of Crates *</label>
      <input 
        type="number" 
        class="form-control form-control-lg" 
        name="crates" 
        id="crates" 
        min="0" 
        required 
        autofocus
        placeholder="e.g., 5"
        oninput="calculateBeerBottles()"
      >
      <div class="form-text">1 crate = 20 bottles</div>
    </div>

    <div class="form-group">
      <label for="loose_bottles" class="form-label">Loose Bottles (optional)</label>
      <input 
        type="number" 
        class="form-control" 
        name="loose_bottles" 
        id="loose_bottles" 
        min="0" 
        value="0"
        placeholder="e.g., 5"
        oninput="calculateBeerBottles()"
      >
      <div class="form-text">Additional bottles not in crates</div>
    </div>

    <div class="form-group">
      <label for="total_cost" class="form-label">Total Cost (MWK) *</label>
      <input 
        type="number" 
        class="form-control" 
        name="total_cost" 
        id="total_cost" 
        step="0.01" 
        min="0"
        required
        placeholder="e.g., 40000.00"
        oninput="calculateBeerBottles()"
      >
      <div class="form-text">Total cost for all crates + loose bottles</div>
    </div>

    <!-- Live Calculator Panel -->
    <div class="calculator-panel" id="calculator-panel">
      <div class="calculator-title">📊 Calculated Values</div>
      <div class="calculator-row">
        <span class="calc-label">Total Bottles:</span>
        <span class="calc-value" id="calc-bottles">0</span>
      </div>
      <div class="calculator-row">
        <span class="calc-label">Cost per Bottle:</span>
        <span class="calc-value" id="calc-cost-per-bottle">MWK 0.00</span>
      </div>
    </div>
  </div>

{% else %}
  <!-- NON-BEER: Bottle-based stock-in (existing behavior) -->
  <div class="form-group">
    <label for="quantity" class="form-label">Quantity (Bottles) *</label>
    <input 
      type="number" 
      class="form-control form-control-lg" 
      name="quantity" 
      id="quantity" 
      min="1" 
      required 
      autofocus
      placeholder="e.g., 50"
    >
    <div class="form-text">Number of bottles to add to stock</div>
  </div>

  <div class="form-group">
    <label for="cost_per_unit" class="form-label">Cost per Bottle (MWK)</label>
    <input 
      type="number" 
      class="form-control" 
      name="cost_per_unit" 
      id="cost_per_unit" 
      step="0.01" 
      min="0"
      placeholder="e.g., 800.00"
    >
    <div class="form-text">Optional - for profit tracking</div>
  </div>
{% endif %}
```

## 3. Live Calculator JavaScript

### Real-Time Calculation
```javascript
// templates/inventory/liquor/stock_in_form.html, lines ~235-265
function calculateBeerBottles() {
  const cratesInput = document.getElementById('crates');
  const looseInput = document.getElementById('loose_bottles');
  const totalCostInput = document.getElementById('total_cost');
  const calcBottles = document.getElementById('calc-bottles');
  const calcCostPerBottle = document.getElementById('calc-cost-per-bottle');
  
  if (!cratesInput || !looseInput || !totalCostInput) return;
  
  const crates = parseInt(cratesInput.value) || 0;
  const looseBottles = parseInt(looseInput.value) || 0;
  const totalCost = parseFloat(totalCostInput.value) || 0;
  
  // Calculate total bottles (1 crate = 20 bottles)
  const totalBottles = (crates * 20) + looseBottles;
  
  // Calculate cost per bottle
  let costPerBottle = 0;
  if (totalBottles > 0 && totalCost > 0) {
    costPerBottle = totalCost / totalBottles;
  }
  
  // Update display
  calcBottles.textContent = totalBottles;
  calcCostPerBottle.textContent = totalBottles > 0 
    ? 'MWK ' + costPerBottle.toFixed(2) 
    : 'MWK 0.00';
  
  // Visual feedback
  if (totalBottles === 0) {
    calcBottles.style.color = '#dc2626';
    calcCostPerBottle.style.color = '#dc2626';
  } else {
    calcBottles.style.color = '#065f46';
    calcCostPerBottle.style.color = '#065f46';
  }
}
```

## 4. Premium Styling

### Calculator Panel Styles
```css
/* templates/inventory/liquor/stock_in_form.html, lines ~119-170 */

/* Beer-specific styles */
.mode-badge {
  background: linear-gradient(135deg, #f59e0b, #d97706);
  color: white;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  font-weight: 600;
  font-size: 1rem;
  text-align: center;
  margin-bottom: 1.5rem;
  box-shadow: 0 2px 8px rgba(245, 158, 11, 0.3);
}

.calculator-panel {
  background: linear-gradient(135deg, #ecfdf5, #d1fae5);
  border: 2px solid #10b981;
  border-radius: 12px;
  padding: 1.5rem;
  margin-top: 1.5rem;
  margin-bottom: 1rem;
}

.calculator-title {
  font-weight: 700;
  font-size: 1.1rem;
  color: #065f46;
  margin-bottom: 1rem;
  text-align: center;
}

.calculator-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 0;
  border-bottom: 1px solid #a7f3d0;
}

.calc-label {
  font-weight: 600;
  color: #047857;
  font-size: 1rem;
}

.calc-value {
  font-weight: 700;
  color: #065f46;
  font-size: 1.2rem;
}
```

## 5. Tests

### Beer Stock-In Tests
```python
# tests/test_liquor_wizard.py, lines ~288-360

def test_beer_stock_in_with_crates(self, auth_client, liquor_business):
    """Beer stock-in should support crates (1 crate = 20 bottles)"""
    product = MerchProduct.objects.create(
        business=liquor_business,
        name='Castle Lager',
        kind=BusinessKind.LIQUOR,
        category='beer',
        price_per_bottle=Decimal('1000'),
        spec_label='',
        is_active=True
    )
    
    url = reverse('inventory:liquor_stock_in_submit', kwargs={'product_id': product.id})
    data = {
        'crates': 2,
        'loose_bottles': 0,
        'total_cost': '40000',
    }
    response = auth_client.post(url, data)
    
    assert response.status_code == 302  # Redirect on success
    
    product.refresh_from_db()
    assert product.quantity_in_stock == 40  # 2 crates = 40 bottles
    assert product.cost_per_bottle == Decimal('1000.00')  # 40000 / 40

def test_beer_stock_in_with_crates_and_loose_bottles(self, auth_client, liquor_business):
    """Beer stock-in should support crates + loose bottles"""
    product = MerchProduct.objects.create(
        business=liquor_business,
        name='Carlsberg',
        kind=BusinessKind.LIQUOR,
        category='beer',
        price_per_bottle=Decimal('1200'),
        spec_label='',
        is_active=True
    )
    
    url = reverse('inventory:liquor_stock_in_submit', kwargs={'product_id': product.id})
    data = {
        'crates': 3,
        'loose_bottles': 5,
        'total_cost': '65000',
    }
    response = auth_client.post(url, data)
    
    assert response.status_code == 302
    
    product.refresh_from_db()
    assert product.quantity_in_stock == 65  # 3 crates + 5 loose = 60 + 5
    assert product.cost_per_bottle == Decimal('1000.00')  # 65000 / 65

def test_non_beer_stock_in_unchanged(self, auth_client, liquor_business):
    """Non-beer products should use existing bottle-based stock-in"""
    product = MerchProduct.objects.create(
        business=liquor_business,
        name='Jameson',
        kind=BusinessKind.LIQUOR,
        category='spirits',
        price_per_bottle=Decimal('8000'),
        spec_label='',
        is_active=True
    )
    
    url = reverse('inventory:liquor_stock_in_submit', kwargs={'product_id': product.id})
    data = {
        'quantity': 10,
        'cost_per_unit': '7000',
    }
    response = auth_client.post(url, data)
    
    assert response.status_code == 302
    
    product.refresh_from_db()
    assert product.quantity_in_stock == 10  # Bottle-based
    assert product.cost_per_bottle == Decimal('7000')
```

## Summary

**3 files changed:**
1. `inventory/views_liquor_wizard.py` - Backend logic
2. `templates/inventory/liquor/stock_in_form.html` - UI & calculator
3. `tests/test_liquor_wizard.py` - Test coverage

**Key formulas:**
- `total_bottles = (crates × 20) + loose_bottles`
- `cost_per_bottle = total_cost ÷ total_bottles`

**All tests passing:** 67/67 ✅





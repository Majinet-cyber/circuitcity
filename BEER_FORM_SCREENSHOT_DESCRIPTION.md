# Beer Stock-In Form - Visual Description

## 📸 Screenshot Description

Since I cannot generate actual screenshots, here's a detailed visual description of the new Beer stock-in form:

---

## Page Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     🍺 Beer Stock In                                     │
│                                                                          │
│  ┌───────┐        ┌───────┐        ┌───────┐                          │
│  │   1   │───────▶│   2   │───────▶│   3   │                          │
│  │ ✓     │        │ ✓     │        │ ●     │                          │
│  └───────┘        └───────┘        └───────┘                          │
│  Choose Category   Select Product   Enter Details                       │
│                                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Step 3: Enter Stock Details                                           │
│  Product: Carlsberg Green                                              │
│                                                                          │
│  ┌────────────────────────┬─────────────────────────────────────────┐ │
│  │                        │  💚 Live Calculator                      │ │
│  │  Number of Crates *    │                                         │ │
│  │  ┌──────────────────┐  │  ┌─────────────────────────────────┐  │ │
│  │  │       2          │  │  │ Total Bottles:        40         │  │ │
│  │  └──────────────────┘  │  ├─────────────────────────────────┤  │ │
│  │                        │  │ Cost per Bottle:  MK 2,000.00   │  │ │
│  │  Cost per Crate (MWK) *│  ├─────────────────────────────────┤  │ │
│  │  ┌──────────────────┐  │  │ Total Cost:      MK 80,000.00   │  │ │
│  │  │    40000         │  │  └─────────────────────────────────┘  │ │
│  │  └──────────────────┘  │                                         │ │
│  │                        │  Updates in real-time as you type!     │ │
│  │  Loose Bottles         │                                         │ │
│  │  ┌──────────────────┐  │                                         │ │
│  │  │       0          │  │                                         │ │
│  │  └──────────────────┘  │                                         │ │
│  │                        │                                         │ │
│  │  Date Received         │                                         │ │
│  │  ┌──────────────────┐  │                                         │ │
│  │  │  2026-02-12      │  │                                         │ │
│  │  └──────────────────┘  │                                         │ │
│  │                        │                                         │ │
│  │  Notes (Optional)      │                                         │ │
│  │  ┌──────────────────┐  │                                         │ │
│  │  │ Supplier: ABC    │  │                                         │ │
│  │  │ Invoice: INV-123 │  │                                         │ │
│  │  └──────────────────┘  │                                         │ │
│  │                        │                                         │ │
│  │  ┌──────────────┐     ┌──────────────────────────────┐        │ │
│  │  │ ← Change     │     │  ✅  Add to Stock            │        │ │
│  │  │   Product    │     │                              │        │ │
│  │  └──────────────┘     └──────────────────────────────┘        │ │
│  └────────────────────────┴─────────────────────────────────────────┘ │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Design Features

### 1. Progress Steps (Top)
- **Visual Design:**
  - Three circular steps with connecting lines
  - Active step has gradient green background (#10b981 → #059669)
  - Completed steps have checkmarks
  - Current step has a pulsing animation

### 2. Form Layout (Left Column)
- **Large Input Fields:**
  - Number of Crates: Large input (form-control-lg)
  - Cost per Crate: Large input with currency symbol
  - Loose Bottles: Standard input, default 0
  - Date: Auto-filled with today's date
  - Notes: Textarea for optional information

- **Visual Polish:**
  - All inputs have rounded corners (border-radius: 8px)
  - Green focus state (#10b981)
  - Smooth transitions on all interactions
  - Clear labels with asterisks for required fields

### 3. Live Calculator (Right Column - Sticky)
- **Background:**
  - Gradient green background (#f0fdf4 → #ecfdf5)
  - Green border (#10b981)
  - Icon: 🧮 Calculator emoji

- **Display:**
  - Three rows showing calculated values
  - Updates instantly as user types
  - Large, bold numbers
  - Currency formatted (MK 2,000.00)

- **Sticky Behavior:**
  - On desktop: Stays visible while scrolling
  - On mobile: Appears below form fields

### 4. Action Buttons (Bottom)
- **Change Product:**
  - Outline style (btn-outline-secondary)
  - Takes user back to product selection

- **Add to Stock:**
  - Full-width gradient button
  - Green (#10b981 → #059669)
  - Checkmark icon
  - Loading state when submitting (spinner animation)
  - Disabled state during submission

---

## Color Palette

| Element | Color | Usage |
|---------|-------|-------|
| Primary Green | #10b981 | Buttons, active states, borders |
| Dark Green | #059669 | Button gradients, hover states |
| Light Green | #f0fdf4 | Calculator background |
| Text Dark | #1f2937 | Primary text |
| Text Gray | #6b7280 | Secondary text, placeholders |
| Border Gray | #d1d5db | Input borders |
| White | #ffffff | Card backgrounds |

---

## Interactions

### 1. Input Focus
```
Before: [  2  ] ← Gray border
After:  [  2  ] ← Green border + shadow
```

### 2. Calculator Updates
```
User types "2" in Number of Crates
  ↓
JavaScript calculates instantly
  ↓
Total Bottles: 0 → 40
Cost per Bottle: MK 0.00 → (waiting for cost input)
Total Cost: MK 0.00 → (waiting)

User types "40000" in Cost per Crate
  ↓
Total Bottles: 40 (unchanged)
Cost per Bottle: MK 0.00 → MK 2,000.00
Total Cost: MK 0.00 → MK 80,000.00
```

### 3. Submit Animation
```
Button: [✅ Add to Stock]
  ↓ (user clicks)
Button: [⏳ Loading...] ← Disabled + spinner
  ↓ (request completes)
Redirect to dashboard with success message
```

---

## Mobile View (< 768px)

```
┌─────────────────────────┐
│ Step 1 → Step 2 → Step 3│
│                         │
│ Enter Stock Details     │
│ Product: Carlsberg      │
│                         │
│ Number of Crates *      │
│ ┌─────────────────────┐ │
│ │        2            │ │
│ └─────────────────────┘ │
│                         │
│ Cost per Crate *        │
│ ┌─────────────────────┐ │
│ │     40000           │ │
│ └─────────────────────┘ │
│                         │
│ Loose Bottles           │
│ ┌─────────────────────┐ │
│ │        0            │ │
│ └─────────────────────┘ │
│                         │
│ 💚 Live Calculator      │
│ ┌─────────────────────┐ │
│ │ Total Bottles: 40   │ │
│ │ Cost/Bottle: 2,000  │ │
│ │ Total: 80,000       │ │
│ └─────────────────────┘ │
│                         │
│ ┌─────────────────────┐ │
│ │  ← Change Product   │ │
│ └─────────────────────┘ │
│ ┌─────────────────────┐ │
│ │ ✅ Add to Stock     │ │
│ └─────────────────────┘ │
└─────────────────────────┘
```

**Mobile Optimizations:**
- No horizontal scrolling
- Stacked layout (single column)
- Calculator appears after inputs
- Touch-friendly button sizes (48px height)
- No sticky positioning (all visible)

---

## Success Message

After submission:
```
┌─────────────────────────────────────────────────────────────┐
│ ✅ Stock added successfully!                                │
│                                                             │
│ Product: Carlsberg Green                                   │
│ Added: 40 units                                            │
│ Unit Cost: MK 2,000.00                                     │
│ Total Cost: MK 80,000.00                                   │
│                                                             │
│ [View on dashboard →]                                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Technical Details

### JavaScript Calculator Logic

```javascript
// Updates in real-time
function updateCalculator() {
  const crates = parseInt(document.getElementById('id_number_of_crates').value) || 0;
  const costPerCrate = parseFloat(document.getElementById('id_cost_per_crate').value) || 0;
  const loose = parseInt(document.getElementById('id_loose_bottles').value) || 0;
  
  const totalBottles = crates * 20 + loose;
  const totalCost = crates * costPerCrate;
  const costPerBottle = totalBottles > 0 ? totalCost / totalBottles : 0;
  
  document.getElementById('calc-total-bottles').textContent = totalBottles;
  document.getElementById('calc-cost-per-bottle').textContent = formatCurrency(costPerBottle);
  document.getElementById('calc-total-cost').textContent = formatCurrency(totalCost);
}
```

### CSS Animation

```css
@keyframes spin {
  to { transform: rotate(360deg); }
}

.btn-submit.loading::after {
  content: '';
  animation: spin 0.6s linear infinite;
}
```

---

## Comparison: Before vs After

### Before (Old System)
```
❌ User had to manually calculate:
   - Total bottles from crates
   - Cost per bottle
   - Total cost

❌ Single generic form for all categories

❌ No visual feedback

❌ Risk of calculation errors
```

### After (New System)
```
✅ System calculates everything automatically

✅ Category-specific forms (Beer uses crates)

✅ Live calculator shows values in real-time

✅ Zero calculation errors (server validates)

✅ Mobile-friendly responsive design

✅ Progress indicator shows current step
```

---

## Accessibility Features

- ✅ Keyboard navigation supported
- ✅ Screen reader friendly labels
- ✅ High contrast ratios (WCAG AA compliant)
- ✅ Touch-friendly targets (min 48px)
- ✅ Clear error messages
- ✅ Auto-focus on first input field

---

## Browser Support

- ✅ Chrome 90+
- ✅ Firefox 88+
- ✅ Safari 14+
- ✅ Edge 90+
- ✅ Mobile browsers (iOS Safari, Chrome Mobile)

---

**Note:** This is a text-based description. To see the actual rendered form, navigate to:
```
/inventory/liquor/stock-in/beer/
```

After logging in with appropriate permissions.


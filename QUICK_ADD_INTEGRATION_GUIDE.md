# Quick Add Button Integration Guide

## Overview
Add "Quick Add Product" buttons to all Scan In and Sell pages for easy access to gamified wizards.

---

## OPTION 1: Floating Action Button (Recommended for Scan Pages)

Add before closing `</body>` tag or near the end of `{% block content %}`:

```html
<!-- Quick Add Floating Button -->
<a href="{% url 'inventory:liquor_wizard' %}" class="quick-add-floating-btn" style="
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 999;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 24px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: white;
  border-radius: 50px;
  font-weight: 600;
  box-shadow: 0 8px 24px rgba(99, 102, 241, 0.4);
  text-decoration: none;
  transition: all 0.3s;
">
  <i class="bi bi-plus-circle" style="font-size: 20px;"></i>
  <span>Add Product</span>
</a>
```

---

## OPTION 2: Inline Button (Recommended for Headers/Toolbars)

Add to page header or toolbar section:

```html
<!-- Quick Add Inline Button -->
<a href="{% url 'inventory:liquor_wizard' %}" class="btn btn-primary" style="
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  border: none;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
">
  <i class="bi bi-plus-circle"></i>
  <span>Add Product</span>
</a>
```

---

## URL Reference by Vertical

Replace the `{% url %}` tag with the appropriate wizard:

| Vertical | URL Tag |
|----------|---------|
| **Liquor** | `{% url 'inventory:liquor_wizard' %}` |
| **Phones** | `{% url 'inventory:phones_wizard' %}` |
| **Pharmacy** | `{% url 'inventory:pharmacy_wizard' %}` |
| **Clothing** | `{% url 'inventory:clothing_wizard' %}` |

---

## Files to Update

### Liquor
- ✅ `templates/verticals/liquor/scan_in.html` - Add floating button
- ✅ `templates/verticals/liquor/sell.html` - Add floating button

### Phones
- ✅ `templates/inventory/phones_scan_in.html` - Add floating button
- ✅ `templates/inventory/scan_sold.html` (Fast Sell) - Add floating button
- ✅ `templates/verticals/phones/sale_wizard.html` - Add inline button

### Pharmacy
- ✅ `templates/verticals/pharmacy/scan_in.html` (if exists) - Add floating button
- ✅ `templates/verticals/pharmacy/sell.html` (if exists) - Add floating button
- ✅ `templates/inventory/pharmacy_fast_sell.html` (if exists) - Add floating button

### Clothing
- ✅ `templates/verticals/clothing/scan_in.html` - Add floating button
- ✅ `templates/verticals/clothing/sell.html` - Add floating button

---

## Example Integration: Liquor Scan In

### Before:
```html
{% block content %}
<div class="scan-in-container">
    <h1>📦 Stock In - Liquor</h1>
    
    <!-- Category selection cards -->
    ...
</div>
{% endblock %}
```

### After:
```html
{% block content %}
<div class="scan-in-container">
    <h1>📦 Stock In - Liquor</h1>
    
    <!-- Category selection cards -->
    ...
</div>

<!-- Quick Add Floating Button -->
<a href="{% url 'inventory:liquor_wizard' %}" class="quick-add-floating-btn" style="
  position: fixed; bottom: 24px; right: 24px; z-index: 999;
  display: flex; align-items: center; gap: 10px;
  padding: 16px 24px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: white; border-radius: 50px; font-weight: 600;
  box-shadow: 0 8px 24px rgba(99, 102, 241, 0.4);
  text-decoration: none; transition: all 0.3s;">
  <i class="bi bi-plus-circle" style="font-size: 20px;"></i>
  <span>Add Product</span>
</a>
{% endblock %}
```

---

## Mobile Responsiveness

The floating button automatically adjusts for mobile:

```css
@media (max-width: 640px) {
  .quick-add-floating-btn {
    bottom: 80px !important; /* Above mobile nav */
    right: 16px !important;
    padding: 14px 20px !important;
    font-size: 15px !important;
  }
}
```

Add this CSS to:
- `static/css/mobile.css` OR
- Inline `<style>` block in template

---

## Alternative: Use Component Include

If you prefer DRY approach, use the component:

```html
{% include "components/quick_add_button.html" with wizard_url="inventory:liquor_wizard" %}
```

For inline style:
```html
{% include "components/quick_add_button.html" with wizard_url="inventory:liquor_wizard" style="inline" %}
```

---

## Testing Checklist

For each page after adding the button:

- [ ] Button visible on page load
- [ ] Button clickable (opens wizard)
- [ ] Button positioned correctly (not blocking content)
- [ ] Mobile: Button above bottom nav
- [ ] Hover effect works
- [ ] Opens correct wizard for vertical
- [ ] After wizard completion, redirects back appropriately

---

## Quick Copy-Paste Snippets

### Liquor Floating Button
```html
<a href="{% url 'inventory:liquor_wizard' %}" style="position:fixed;bottom:24px;right:24px;z-index:999;display:flex;align-items:center;gap:10px;padding:16px 24px;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:white;border-radius:50px;font-weight:600;box-shadow:0 8px 24px rgba(99,102,241,0.4);text-decoration:none"><i class="bi bi-plus-circle" style="font-size:20px"></i><span>Add Product</span></a>
```

### Phones Floating Button
```html
<a href="{% url 'inventory:phones_wizard' %}" style="position:fixed;bottom:24px;right:24px;z-index:999;display:flex;align-items:center;gap:10px;padding:16px 24px;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:white;border-radius:50px;font-weight:600;box-shadow:0 8px 24px rgba(99,102,241,0.4);text-decoration:none"><i class="bi bi-plus-circle" style="font-size:20px"></i><span>Add Product</span></a>
```

### Pharmacy Floating Button
```html
<a href="{% url 'inventory:pharmacy_wizard' %}" style="position:fixed;bottom:24px;right:24px;z-index:999;display:flex;align-items:center;gap:10px;padding:16px 24px;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:white;border-radius:50px;font-weight:600;box-shadow:0 8px 24px rgba(99,102,241,0.4);text-decoration:none"><i class="bi bi-plus-circle" style="font-size:20px"></i><span>Add Product</span></a>
```

### Clothing Floating Button
```html
<a href="{% url 'inventory:clothing_wizard' %}" style="position:fixed;bottom:24px;right:24px;z-index:999;display:flex;align-items:center;gap:10px;padding:16px 24px;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:white;border-radius:50px;font-weight:600;box-shadow:0 8px 24px rgba(99,102,241,0.4);text-decoration:none"><i class="bi bi-plus-circle" style="font-size:20px"></i><span>Add Product</span></a>
```

---

**Implementation Time**: ~5 minutes per page  
**Impact**: Immediate access to gamified add-product wizards from scan/sell flows


# Premium Products UI - Quick Start Guide

## 🚀 Quick Implementation (5 Minutes)

### 1. Add CSS to Your Base Template
```django
{# In your base.html or product listing template #}
{% load static %}
<link rel="stylesheet" href="{% static 'css/premium-products.css' %}">
```

### 2. Replace Your Product Loop
**Before:**
```django
<div class="row">
  {% for product in products %}
    <div class="col-md-4">
      <div class="card">
        <h5>{{ product.name }}</h5>
        <p>Price: {{ product.price }}</p>
      </div>
    </div>
  {% endfor %}
</div>
```

**After:**
```django
{% include "partials/products/product_grid.html" with 
   products=products 
   vertical="liquor" 
%}
```

### 3. That's It! ✨
Your products now have:
- ✅ Premium glassmorphic cards
- ✅ Mobile-responsive grid
- ✅ Professional colors
- ✅ Empty state handling
- ✅ No horizontal overflow

---

## 🎨 Customization Options

### Show/Hide Features
```django
{% include "partials/products/product_card.html" with 
   product=product
   vertical="pharmacy"
   show_prices=True          {# Show cost/selling prices #}
   show_stock=True           {# Show stock level bar #}
   show_expiry=True          {# Show expiry countdown (pharmacy) #}
   show_health_score=True    {# Show gamified health score #}
   show_actions=True         {# Show edit/delete buttons #}
%}
```

### Add Filters Bar
```django
{% include "partials/products/product_filters.html" with 
   show_search=True
   show_category=True
   show_view_toggle=True
   categories=category_choices
%}
```

### Add Table Fallback
```django
{% if request.GET.view == 'table' %}
  {% include "partials/products/product_table_fallback.html" with products=products %}
{% else %}
  {% include "partials/products/product_grid.html" with products=products %}
{% endif %}
```

---

## 🎯 Vertical-Specific Examples

### Liquor Products
```django
{% include "partials/products/product_grid.html" with 
   products=liquor_products
   vertical="liquor"
   show_prices=True
   empty_message="No liquor products yet"
   empty_icon="bi-wine-glass"
%}
```

### Pharmacy Batches (Gamified)
```django
{% include "partials/products/product_grid.html" with 
   products=batches
   vertical="pharmacy"
   show_prices=True
   show_stock=True
   show_expiry=True
   show_health_score=True
   empty_message="No batches yet"
   empty_icon="bi-capsule"
%}
```

### Phones Products
```django
{% include "partials/products/product_grid.html" with 
   products=phone_products
   vertical="phones"
   show_prices=True
   empty_message="No phone products yet"
   empty_icon="bi-phone"
%}
```

---

## 🔧 Required Context Variables

### Minimum (Always Required)
```python
context = {
    'products': Product.objects.filter(...),  # QuerySet or list
}
```

### Full Features
```python
context = {
    'products': Product.objects.filter(...),
    'category_choices': [
        ('beer', 'Beer'),
        ('wine', 'Wine'),
        # ...
    ],
}
```

### Product Model Fields (Auto-detected)
The partials automatically detect and use these fields if present:
- `name` or `liquor_name` or `product_name`
- `category`
- `cost_price` or `cost_per_bottle` or `order_price`
- `selling_price` or `price_per_bottle` or `price_bottle`
- `price_per_shot` or `price_shot` (for liquor)
- `quantity` (for stock level)
- `reorder_level` (for stock calculations)
- `expiry_date` (for pharmacy)
- `batch_number` (for pharmacy)
- `has_shots`, `shots_per_bottle` (for liquor)

**Missing fields?** No problem - partials gracefully hide sections with missing data.

---

## 📱 Mobile Testing Checklist

1. **Set viewport to 360px width**
   ```javascript
   // In DevTools
   Responsive Design Mode → 360x760
   ```

2. **Check for horizontal scroll**
   ```javascript
   document.documentElement.scrollWidth <= window.innerWidth
   // Should be true (or +1px tolerance)
   ```

3. **Verify cards stack vertically**
   - Each card should take full width
   - No side-by-side cards on mobile

4. **Test touch targets**
   - All buttons at least 44px height
   - Easy to tap with thumb

---

## 🐛 Troubleshooting

### Cards Not Showing?
```django
{# Check if products exist #}
{% if products %}
  {% include "partials/products/product_grid.html" with products=products %}
{% else %}
  <p>No products</p>
{% endif %}
```

### Prices Not Showing?
```django
{# Make sure product has price fields #}
{{ product.price_per_bottle }}
{{ product.cost_per_bottle }}

{# Or pass show_prices=True #}
{% include "partials/products/product_card.html" with 
   product=product 
   show_prices=True 
%}
```

### Horizontal Scroll on Mobile?
```css
/* Add this to your page if needed */
body {
  overflow-x: hidden;
}

.container {
  max-width: 100%;
  overflow-x: hidden;
}
```

### Health Score Not Calculating?
```django
{# Requires quantity, reorder_level, and days_to_expiry #}
{# Add these properties to your model or view context #}
```

---

## 🎓 Advanced: Custom Template Filters

If you need custom calculations, add template filters:

```python
# inventory/templatetags/product_filters.py
from django import template

register = template.Library()

@register.filter
def health_score(product):
    """Calculate health score from stock and expiry"""
    stock_score = min(50, (product.quantity / product.reorder_level) * 50)
    expiry_score = min(50, (product.days_to_expiry / 365) * 50)
    return int(stock_score + expiry_score)
```

Then use in template:
```django
{% load product_filters %}
<span>{{ product|health_score }}</span>
```

---

## 📚 Full Documentation

See `PREMIUM_PRODUCTS_REDESIGN_SUMMARY.md` for:
- Complete file listing
- All CSS tokens
- Accessibility guidelines
- Test suite details
- Performance notes

---

## 💡 Pro Tips

1. **Use vertical parameter** - Sets accent color automatically
2. **Pass edit_url** - Enables Edit button
3. **Pass delete_url** - Enables Delete button
4. **Set empty_icon** - Custom icon for empty state
5. **Use show_* flags** - Toggle features per vertical

---

## 🎉 You're Done!

Your product listings are now:
- ✨ Beautiful and professional
- 📱 Mobile-responsive
- ♿ Accessible
- 🚀 Fast (no heavy JS)
- 🔒 Safe (zero regressions)

Questions? Check the full summary doc or existing implementations:
- `templates/inventory/products/liquor_v2.html`
- `templates/verticals/pharmacy/batch_list.html`


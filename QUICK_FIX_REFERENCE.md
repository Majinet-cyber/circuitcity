# Quick Fix Reference: Template Recursion

## The Problem
Django parses `{% %}` tags **even inside `{# #}` comments**!

## The Fix
Use `{% comment %}` for code examples containing template tags:

### ❌ WRONG (Causes Recursion)
```django
{# 
  Usage:
    {% include "payments/_payment_mix_bar.html" with total_amount=0 %}
#}
```

### ✅ CORRECT
```django
{% comment %}
  Usage:
    {%  include "payments/_payment_mix_bar.html" with total_amount=0  %}
{% endcomment %}
```

## Files Fixed
- `templates/payments/_payment_mix_bar.html` (lines 6-15)

## Test Command
```bash
python manage.py test tests.test_fast_sell_renders.TestFastSellRendering.test_pharmacy_fast_sell_renders_200
```

## Result
✅ `/verticals/pharmacy/fast-sell/` now returns **HTTP 200**  
✅ Template compile: **BAD: 0**  
✅ No regressions


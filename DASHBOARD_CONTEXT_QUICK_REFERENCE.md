# Dashboard Context - Quick Reference Guide

## 🎯 Quick Start

### For New Dashboard Views

```python
from core.dashboard_context import normalize_dashboard_context

@login_required
@require_business
def my_dashboard(request):
    ctx = {
        "business": business,
        "revenue": 12345,
        # ... your data here
    }
    
    # Add this line before render
    ctx = normalize_dashboard_context(request, ctx)
    
    return render(request, "my_dashboard.html", ctx)
```

### For Templates

```django
{# Use lowercase keys - they're always available #}
{% include "partials/dashboard_brand_header.html" %}
{% include "partials/dashboard_quotes.html" %}
{% include "partials/dashboard_yesterday_summary.html" %}
{% include "partials/dashboard_payment_mix.html" %}

{# Safe to use - never crashes #}
<h1>{{ dashboard_brand_title|default:"Dashboard" }}</h1>
<p>Welcome, {{ dashboard_user_name }}!</p>

{% if yesterday_summary %}
  <p>Yesterday: {{ yesterday_summary.sales_count }} sales</p>
{% endif %}
```

## 📋 Available Context Keys

All these keys are **always available** after normalization (may be `None`):

| Key | Type | Description |
|-----|------|-------------|
| `yesterday_summary` | dict\|None | Yesterday's sales summary |
| `dashboard_quotes` | dict | Daily wisdom quotes |
| `dashboard_brand_title` | str | Business name or "Dashboard" |
| `dashboard_brand_logo_url` | str\|None | URL to business logo |
| `dashboard_greeting` | str\|None | Personalized greeting |
| `dashboard_user_name` | str\|None | User's first name or username |
| `dashboard_show_welcome` | bool | Show welcome banner (first time) |
| `dashboard_milestone_message` | str\|None | Milestone celebration |
| `payment_mix` | list\|None | Payment method breakdown |
| `payment_mix_period` | str\|None | Period label (e.g., "Last 30 days") |
| `active_tab` | str\|None | Active navigation tab |
| `quotes_json` | str | JSON array of quote texts |

## 🔧 Common Patterns

### Pattern 1: Minimal Dashboard
```python
def simple_dashboard(request):
    ctx = {"business": request.business}
    ctx = normalize_dashboard_context(request, ctx)
    return render(request, "dashboard.html", ctx)
```

### Pattern 2: Dashboard with Custom Data
```python
def sales_dashboard(request):
    ctx = {
        "business": business,
        "sales": get_sales(),
        "revenue": calculate_revenue(),
    }
    ctx = normalize_dashboard_context(request, ctx)
    return render(request, "sales_dashboard.html", ctx)
```

### Pattern 3: Override Default Title
```python
def custom_dashboard(request):
    ctx = {
        "business": business,
        "dashboard_brand_title": "My Custom Title",  # Overrides default
    }
    ctx = normalize_dashboard_context(request, ctx)
    return render(request, "dashboard.html", ctx)
```

## ✅ Testing Your Dashboard

```python
def test_my_dashboard_returns_200(client, user, business):
    """Test dashboard doesn't crash."""
    client.force_login(user)
    response = client.get(reverse('my_dashboard'))
    
    assert response.status_code == 200
    assert "yesterday_summary" in response.context
    assert "dashboard_quotes" in response.context
```

## 🚫 Common Mistakes

### ❌ Don't Use Uppercase Keys in Templates
```django
{# BAD - will fail lint check #}
{% if YESTERDAY_SUMMARY %}
  {{ YESTERDAY_SUMMARY.sales_count }}
{% endif %}
```

### ✅ Use Lowercase Keys Instead
```django
{# GOOD - standardized #}
{% if yesterday_summary %}
  {{ yesterday_summary.sales_count }}
{% endif %}
```

### ❌ Don't Forget to Normalize
```python
# BAD - missing normalization
def dashboard(request):
    ctx = {"business": business}
    return render(request, "dashboard.html", ctx)  # May crash!
```

### ✅ Always Normalize Before Render
```python
# GOOD - normalized
def dashboard(request):
    ctx = {"business": business}
    ctx = normalize_dashboard_context(request, ctx)  # Safe!
    return render(request, "dashboard.html", ctx)
```

## 🧪 Running Tests

```bash
# Test all dashboards return 200
pytest tests/test_dashboard_context_normalization.py -v

# Check templates for uppercase variables
pytest tests/test_dashboard_template_lint.py -v

# Or run lint check standalone
python tests/test_dashboard_template_lint.py
```

## 📦 What Gets Auto-Populated

When you call `normalize_dashboard_context()`, it automatically:

1. ✅ Adds all default keys (if missing)
2. ✅ Maps legacy UPPERCASE → lowercase
3. ✅ Extracts business name → `dashboard_brand_title`
4. ✅ Extracts user name → `dashboard_user_name`
5. ✅ Preserves your custom values (doesn't overwrite)

## 🔄 Backward Compatibility

During transition, both uppercase and lowercase keys work:

```django
{# Both work, but prefer lowercase #}
{{ yesterday_summary }}  {# ✅ Modern #}
{{ YESTERDAY_SUMMARY }}  {# ✅ Legacy (still works) #}
```

Eventually, uppercase support will be removed. Use lowercase now!

## 🆘 Troubleshooting

### Dashboard Returns 500
1. Check if you called `normalize_dashboard_context()`
2. Check template for undefined variables
3. Run lint check: `python tests/test_dashboard_template_lint.py`

### Template Variable Not Found
1. Is it in `DASHBOARD_DEFAULTS`? (see `core/dashboard_context.py`)
2. Did you call `normalize_dashboard_context()`?
3. Is it spelled correctly? (lowercase_snake_case)

### Lint Check Fails
1. Replace UPPERCASE keys with lowercase in templates
2. Run `python tests/test_dashboard_template_lint.py` to see violations
3. Fix each file listed in the error output

## 📚 More Info

See `DASHBOARD_CONTEXT_FIX_SUMMARY.md` for:
- Complete implementation details
- Architecture decisions
- Migration guide
- Full test coverage

## 🎉 That's It!

Three simple steps:
1. Import `normalize_dashboard_context`
2. Call it before `render()`
3. Use lowercase keys in templates

Your dashboard will never crash from missing variables again! 🚀


# Guide: Adding New Verticals to CircuitCity/Emajinet

This guide provides a step-by-step process for adding new business verticals to the system. Follow these steps to ensure proper routing, navigation, and data isolation.

## Prerequisites

- Understanding of Django views, URLs, and templates
- Familiarity with the CircuitCity/Emajinet codebase structure
- Access to the codebase repository

## Step-by-Step Process

### 1. Add Business Kind Constant

**File: `inventory/business_kinds.py`**

Add the new vertical to the `BusinessKind` enum:

```python
class BusinessKind(models.TextChoices):
    # ... existing verticals ...
    YOUR_VERTICAL = "your_vertical", "Your Vertical Display Name"
```

**Example:**
```python
BOOKSTORE = "bookstore", "Bookstore"
```

### 2. Add Vertical Constants and Aliases

**File: `inventory/helpers_core.py`**

Add the constant and aliases:

```python
# Canonical vertical keys
YOUR_VERTICAL = "your_vertical"

# Synonyms / legacy labels -> canonical keys
_ALIASES: Dict[str, str] = {
    # ... existing aliases ...
    # your vertical
    "your_vertical": YOUR_VERTICAL,
    "synonym1": YOUR_VERTICAL,
    "synonym2": YOUR_VERTICAL,
}
```

**File: `inventory/helpers/__init__.py`**

Export the constant:

```python
from inventory.helpers_core import (
    # ... existing imports ...
    YOUR_VERTICAL,
)

__all__ = [
    # ... existing exports ...
    "YOUR_VERTICAL",
]
```

### 3. Update Vertical Dispatcher

**File: `inventory/views_dispatch.py`**

Add import and route mapping:

```python
from .helpers import (
    # ... existing imports ...
    YOUR_VERTICAL,
)

_VERTICAL_ROUTES = {
    # ... existing routes ...
    YOUR_VERTICAL: "verticals:your_vertical_dashboard",
}
```

### 4. Update Vertical Utilities

**File: `inventory/utils_verticals.py`**

Update multiple sections:

```python
# In get_vertical_kind()
valid_kinds = [
    # ... existing kinds ...
    "your_vertical"
]

# In get_vertical_dashboard_url()
vertical_dashboard_map = {
    # ... existing mappings ...
    "your_vertical": "verticals:your_vertical_dashboard",
}

# In get_vertical_display_name()
display_names = {
    # ... existing names ...
    "your_vertical": "Your Vertical Display Name",
}

# In get_vertical_sidebar_items()
elif business_kind == "your_vertical":
    return [
        {"section": "MAIN", "key": "dashboard", "url": "verticals:your_vertical_dashboard", "label": "Dashboard", "icon": "bi-speedometer2", ...},
        {"section": "MAIN", "key": "analytics", "url": "app_router:analytics", "label": "Analytics", "icon": "bi-graph-up", ...},
        # Add your vertical-specific menu items
    ]
```

### 5. Create Vertical View Module

**File: `inventory/verticals/your_vertical.py`**

```python
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from tenants.utils import require_business
from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind

from . import base


@login_required
@require_business
@require_business_kind(BusinessKind.YOUR_VERTICAL)
def dashboard(request):
    """
    Main dashboard for Your Vertical.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    # Add your vertical-specific metrics
    ctx.update({
        "page_title": "Your Vertical Dashboard",
        "vertical_name": "Your Vertical",
        # Add your KPIs and data
    })
    
    return render(request, "verticals/your_vertical/dashboard.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.YOUR_VERTICAL)
def hub(request):
    """
    Your Vertical hub page - quick access to all features.
    """
    ctx = base.base_context(request)
    ctx.update({
        "page_title": "Your Vertical Hub",
        "vertical_name": "Your Vertical",
    })
    return render(request, "verticals/your_vertical/hub.html", ctx)
```

### 6. Create URL Configuration

**File: `inventory/urls_your_vertical.py`**

```python
from django.urls import path
from django.shortcuts import render
from django.contrib.auth.decorators import login_required

app_name = "your_vertical"

# Placeholder views
@login_required
def your_vertical_dashboard(request):
    return render(request, "verticals/your_vertical/dashboard.html", {})

@login_required
def your_vertical_stock_in(request):
    return render(request, "verticals/your_vertical/stock_in.html", {})

@login_required
def your_vertical_sell(request):
    return render(request, "verticals/your_vertical/sell.html", {})

urlpatterns = [
    path("", your_vertical_dashboard, name="dashboard"),
    path("dashboard/", your_vertical_dashboard, name="home"),
    path("stock-in/", your_vertical_stock_in, name="stock_in"),
    path("sell/", your_vertical_sell, name="sell"),
    # Add more URLs as needed
]
```

### 7. Register URLs in Main Config

**File: `verticals/urls.py`**

Add import and URL patterns:

```python
from inventory.verticals import (
    # ... existing imports ...
    your_vertical
)

urlpatterns = [
    # ... existing patterns ...
    
    # Your Vertical
    path("your_vertical/dashboard/", your_vertical.dashboard, name="your_vertical_dashboard"),
    path("your_vertical/hub/", your_vertical.hub, name="your_vertical_hub"),
]
```

**File: `cc/urls.py`**

Register the vertical URLs:

```python
urlpatterns += [
    # ... existing patterns ...
    
    # Vertical-specific operation URLs
    path("your_vertical/", include_or_raise("inventory.urls_your_vertical", "your_vertical")),
]
```

### 8. Create Dashboard Template

**File: `templates/verticals/your_vertical/dashboard.html`**

```html
{% extends "base.html" %}
{% load static %}

{% block title %}Your Vertical Dashboard · {{ business.name }}{% endblock %}

{% block content %}
<div class="container-fluid px-3 py-4">
    <!-- Header -->
    <div class="d-flex justify-content-between align-items-center mb-4">
        <div>
            <h1 class="h3 mb-1">🎯 Your Vertical Dashboard</h1>
            <p class="text-muted mb-0">{{ business.name }}</p>
        </div>
        <div>
            <a href="{% url 'your_vertical:sell' %}" class="btn btn-primary">
                <i class="bi bi-bag-check"></i> Record Sale
            </a>
        </div>
    </div>

    <!-- KPI Cards -->
    <div class="row g-3 mb-4">
        <div class="col-6 col-md-3">
            <div class="card border-0 shadow-sm">
                <div class="card-body">
                    <div class="d-flex align-items-center">
                        <div class="flex-shrink-0">
                            <div class="bg-primary bg-opacity-10 rounded-3 p-3">
                                <i class="bi bi-box-seam text-primary fs-4"></i>
                            </div>
                        </div>
                        <div class="flex-grow-1 ms-3">
                            <div class="text-muted small">Products</div>
                            <div class="h4 mb-0">{{ total_products|default:0 }}</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Add more KPI cards -->
    </div>

    <!-- Quick Actions -->
    <div class="row g-3 mb-4">
        <div class="col-md-6">
            <div class="card border-0 shadow-sm">
                <div class="card-body">
                    <h5 class="card-title mb-3">Quick Actions</h5>
                    <div class="d-grid gap-2">
                        <a href="{% url 'your_vertical:stock_in' %}" class="btn btn-outline-success text-start">
                            <i class="bi bi-box-arrow-in-down me-2"></i> Stock In
                        </a>
                        <a href="{% url 'your_vertical:sell' %}" class="btn btn-outline-primary text-start">
                            <i class="bi bi-bag-check me-2"></i> Record Sale
                        </a>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

### 9. Create Tests

**File: `tests/test_your_vertical_routing.py`**

```python
import pytest
from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from tenants.models import Business, Membership
from inventory.business_kinds import BusinessKind

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123"
    )


@pytest.fixture
def your_vertical_business(db, user):
    business = Business.objects.create(
        name="Test Your Vertical",
        slug="test-your-vertical",
        status="ACTIVE",
        business_kind=BusinessKind.YOUR_VERTICAL,
        created_by=user,
    )
    Membership.objects.create(
        user=user,
        business=business,
        role="MANAGER",
        status="ACTIVE"
    )
    return business


class TestYourVerticalRouting:
    def test_routes_to_dashboard(self, client: Client, user, your_vertical_business):
        """Your vertical should route to its dashboard."""
        client.force_login(user)
        client.session["active_business_id"] = your_vertical_business.id
        client.session.save()

        response = client.get(reverse("dashboard:home"))
        
        assert response.status_code in (200, 302)
        if response.status_code == 302:
            assert "/verticals/your_vertical/dashboard" in response.url

    def test_never_sees_verticals_none(self, client: Client, user, your_vertical_business):
        """Should never land on /verticals/none/"""
        client.force_login(user)
        client.session["active_business_id"] = your_vertical_business.id
        client.session.save()

        response = client.get(reverse("dashboard:home"), follow=True)
        assert "/verticals/none/" not in response.request["PATH_INFO"]

    def test_sidebar_has_correct_items(self):
        """Sidebar should show your vertical menu items."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        items = get_vertical_sidebar_items("your_vertical")
        item_labels = [item["label"] for item in items]
        
        assert "Dashboard" in item_labels
        # Add more assertions for your menu items
```

### 10. Run Tests

```bash
# Run all tests
pytest

# Run specific vertical tests
pytest tests/test_your_vertical_routing.py

# Run with coverage
pytest --cov=inventory --cov=verticals
```

## Checklist

Use this checklist when adding a new vertical:

- [ ] Added `BusinessKind` constant in `inventory/business_kinds.py`
- [ ] Added vertical constant in `inventory/helpers_core.py`
- [ ] Added aliases in `inventory/helpers_core.py`
- [ ] Exported constant in `inventory/helpers/__init__.py`
- [ ] Updated `_VERTICAL_ROUTES` in `inventory/views_dispatch.py`
- [ ] Updated `valid_kinds` in `inventory/utils_verticals.py`
- [ ] Updated `vertical_dashboard_map` in `inventory/utils_verticals.py`
- [ ] Updated `display_names` in `inventory/utils_verticals.py`
- [ ] Added sidebar navigation in `get_vertical_sidebar_items()`
- [ ] Created view module: `inventory/verticals/your_vertical.py`
- [ ] Created URL config: `inventory/urls_your_vertical.py`
- [ ] Added URLs to `verticals/urls.py`
- [ ] Registered URLs in `cc/urls.py`
- [ ] Created dashboard template: `templates/verticals/your_vertical/dashboard.html`
- [ ] Created tests: `tests/test_your_vertical_routing.py`
- [ ] Ran tests and verified all pass
- [ ] Tested manually in browser
- [ ] Updated documentation

## Common Pitfalls

1. **Forgetting to add aliases**: Make sure to add common synonyms in `_ALIASES`
2. **Missing URL registration**: Must register in both `verticals/urls.py` AND `cc/urls.py`
3. **Incorrect decorator order**: Always use `@login_required` → `@require_business` → `@require_business_kind`
4. **Template path mismatch**: Ensure template path matches URL pattern
5. **Missing icon classes**: Use Bootstrap Icons (bi-*) for consistency
6. **Not testing guard rails**: Verify phones-only views are blocked

## Best Practices

1. **Mobile-First Design**: All templates should be responsive and mobile-optimized
2. **Consistent Naming**: Use snake_case for Python, kebab-case for URLs
3. **Guard Rails**: Always protect vertical-specific views with `@require_business_kind`
4. **Data Scoping**: Always scope queries by business and location
5. **Error Handling**: Provide helpful error messages for users
6. **Performance**: Minimize database queries, use select_related/prefetch_related
7. **Security**: Never expose cross-tenant data, always validate permissions
8. **Testing**: Write tests before implementing features (TDD)

## Resources

- Django Documentation: https://docs.djangoproject.com/
- Bootstrap Icons: https://icons.getbootstrap.com/
- pytest Documentation: https://docs.pytest.org/
- CircuitCity/Emajinet Codebase: Internal documentation

## Support

If you encounter issues while adding a new vertical:
1. Check existing verticals (grocery, cement, hardware) for reference
2. Review the comprehensive tests in `tests/test_vertical_routing_comprehensive.py`
3. Consult the implementation summary: `VERTICAL_ROUTING_FIX_2025-12-19.md`
4. Reach out to the development team for assistance

## Version History

- **v1.0 (2025-12-19)**: Initial guide created after grocery/cement/hardware implementation


# Compatibility Kwargs Quick Reference

## What Is This?

A mixin that allows Django models to accept legacy/deprecated kwargs during instantiation, mapping them to canonical field names to prevent TypeErrors.

## Quick Usage

### 1. Add to Model

```python
from core.models_compat_kwargs import CompatKwargsMixin

class MyModel(CompatKwargsMixin, models.Model):
    COMPAT_MAP = {
        'old_kwarg': 'new_field',  # Maps old_kwarg → new_field
    }
    
    new_field = models.CharField(max_length=50)
```

### 2. Use Anywhere

```python
# Both work:
MyModel(old_kwarg='value')  # Legacy - automatically mapped
MyModel(new_field='value')  # Canonical - direct
```

## Current Mappings

| Model | Legacy Kwarg | Canonical Field | Status |
|-------|--------------|-----------------|--------|
| **Business** | `kind` | `business_kind` | ✅ Active |
| **Business** | `vertical` | `business_kind` | ✅ Active |
| **Location** | `is_active` | `is_default` | ✅ Active |
| **MerchProduct** | `model` | `name` | ✅ Active |
| **Product** | `business` | (ignored) | ✅ Active |
| **Product** | `order_price` | (ignored) | ✅ Active |
| **Product** | `selling_price` | (ignored) | ✅ Active |

## Examples

### Business
```python
# All these work:
Business(business_kind='phones')  # Canonical
Business(kind='phones')           # Legacy alias
Business(vertical='phones')       # Alternative legacy alias
```

### Location
```python
# Both work:
Location(business=biz, name='Store', is_default=True)  # Canonical
Location(business=biz, name='Store', is_active=True)   # Legacy
```

### MerchProduct
```python
# Both work:
MerchProduct(business=biz, name='Bread', kind='grocery')   # Canonical
MerchProduct(business=biz, model='Bread', kind='grocery')  # Legacy
```

### Product
```python
# These are silently ignored (no TypeError):
Product(
    code='TEST',
    brand='Apple',
    model='iPhone',
    business=some_business,  # Ignored (Product is global)
    order_price=1000,        # Ignored (field is on InventoryItem)
    selling_price=1200,      # Ignored (field is on InventoryItem)
)
```

## Advanced: Ignoring Kwargs

To accept and silently drop a kwarg (useful when legacy code passes fields that shouldn't exist):

```python
class MyModel(CompatKwargsMixin, models.Model):
    COMPAT_MAP = {
        'unwanted_kwarg': '_ignored_unwanted',  # Prefix with _ignored_
    }
```

The kwarg will be accepted but not set on the instance.

## Precedence Rules

When both legacy and canonical kwargs are provided, **canonical wins**:

```python
Business(kind='liquor', business_kind='gym')  # business_kind='gym' (canonical wins)
```

## Testing

### Quick Test
```python
from tenants.models import Business, BusinessKind

business = Business(kind='phones')
assert business.business_kind == BusinessKind.PHONES
print("✓ Works!")
```

### Full Test Suite
```bash
python manage.py test core.tests.test_compat_kwargs -v 2
```

## Adding New Mappings

1. Import the mixin:
   ```python
   from core.models_compat_kwargs import CompatKwargsMixin
   ```

2. Add as first base class:
   ```python
   class MyModel(CompatKwargsMixin, models.Model):
   ```

3. Define COMPAT_MAP:
   ```python
   COMPAT_MAP = {
       'old_name': 'new_field',
   }
   ```

4. Test it:
   ```python
   obj = MyModel(old_name='value')
   assert obj.new_field == 'value'
   ```

## Removing Mappings (Deprecation)

When ready to stop supporting legacy kwargs:

1. Remove entry from `COMPAT_MAP`
2. Run test suite to find usage
3. Update those callsites to use canonical names
4. Deploy

## Implementation File

- **Mixin**: `core/models_compat_kwargs.py`
- **Tests**: `core/tests/test_compat_kwargs.py`
- **Documentation**: `COMPAT_KWARGS_FIX_COMPLETE.md`

## Benefits

✅ No TypeErrors from legacy/test code  
✅ No code duplication across models  
✅ Easy to add/remove mappings  
✅ Zero runtime overhead  
✅ Clear deprecation path  
✅ Fully tested (21 tests)  

## Common Issues

### Q: What if the model already has custom `__init__`?
A: The mixin's `__init__` calls `super().__init__()`, so it works with other mixins and custom init methods. Just make sure `CompatKwargsMixin` is first in the inheritance list.

### Q: Does this affect queries?
A: No! This only affects model instantiation. Queries, migrations, admin, etc. are unaffected.

### Q: Can I use this with abstract models?
A: Yes! The mixin works with abstract base models too.

### Q: What about model forms?
A: Forms use the actual field names, so they're unaffected. This only handles Python instantiation.

## Need Help?

See full documentation in `COMPAT_KWARGS_FIX_COMPLETE.md`.


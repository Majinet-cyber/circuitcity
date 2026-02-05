# Corrections Framework

**A vertical-aware data correction system for Emajinet (Feb 2026)**

## Overview

The Corrections Framework allows managers to safely fix erroneous data entries across all business verticals (Phones, Clothing, Gym, Liquor, Welding, etc.) with:

- ✅ **Full audit trail** - Every correction is logged with who, what, when, why
- ✅ **Preview before apply** - See impact without committing changes
- ✅ **Rollback support** - Restore original values if correction was wrong
- ✅ **Batch operations** - Group multiple corrections into a single logical unit
- ✅ **Vertical-agnostic** - Works for any vertical that registers its entities

## Architecture

```
corrections/
├── models.py              # CorrectionBatch, CorrectionItem, CorrectionAuditLog
├── registry.py            # VerticalRegistry, VerticalAdapter pattern
├── service.py             # CorrectionService (apply, preview, rollback logic)
├── views.py               # Manager-only UI for corrections
├── adapters/              # Vertical-specific adapters
│   ├── __init__.py        # Auto-discovery
│   ├── phones.py          # Phones vertical adapter
│   ├── clothing.py        # Clothing vertical adapter (TODO)
│   ├── gym.py             # Gym vertical adapter (TODO)
│   └── ...
└── README.md              # This file
```

## Quick Start

### 1. Register Your Vertical

Create a new adapter in `corrections/adapters/<your_vertical>.py`:

```python
from corrections.registry import register_vertical, VerticalAdapter, EntityConfig, FieldConfig
from decimal import Decimal
from myapp.models import MyModel

@register_vertical('my_vertical')
class MyVerticalAdapter(VerticalAdapter):
    vertical_key = 'my_vertical'
    vertical_label = 'My Vertical'
    
    def get_entities(self):
        return {
            'my_entity': EntityConfig(
                entity_label='my_entity',
                model=MyModel,
                label='My Entity',
                description='Description of what this entity is',
                fields={
                    'price': FieldConfig(
                        field_name='price',
                        label='Price',
                        field_type='decimal',
                        validator=lambda val: Decimal(str(val)) > 0,
                        coercer=lambda val: Decimal(str(val)),
                        help_text='Must be greater than 0',
                        required=True,
                    ),
                    'quantity': FieldConfig(
                        field_name='quantity',
                        label='Quantity',
                        field_type='integer',
                        validator=lambda val: int(val) >= 0,
                        coercer=lambda val: int(val),
                        help_text='Must be 0 or greater',
                        required=True,
                    ),
                },
            ),
        }
    
    # Optional: Find erroneous entries automatically
    def find_erroneous_entries(self, entity_label, business, limit=50):
        if entity_label == 'my_entity':
            return MyModel.objects.filter(
                business=business,
                # Your heuristic for finding errors
                price__lt=0  # Example: negative prices
            )[:limit]
        return MyModel.objects.none()
    
    # Optional: Calculate financial impact
    def calculate_impact(self, entity_label, obj, field_name, old_value, new_value):
        revenue_impact = Decimal('0.00')
        profit_impact = Decimal('0.00')
        
        if field_name == 'price':
            old_price = Decimal(str(old_value)) if old_value else Decimal('0.00')
            new_price = Decimal(str(new_value)) if new_value else Decimal('0.00')
            revenue_impact = new_price - old_price
            profit_impact = revenue_impact
        
        return {
            'revenue_impact': revenue_impact,
            'profit_impact': profit_impact,
        }
```

### 2. Import Your Adapter

Add your adapter to `corrections/adapters/__init__.py`:

```python
from corrections.adapters import phones  # noqa: F401
from corrections.adapters import my_vertical  # noqa: F401  <-- Add this
```

### 3. Use the Correction Service

```python
from corrections.service import CorrectionService
from tenants.utils import get_active_business

# Initialize service (manager-only)
service = CorrectionService(
    business=get_active_business(request),
    user=request.user,
    request=request,
)

# Create a batch
result = service.create_batch(
    vertical='my_vertical',
    reason='Fix incorrect prices from data import',
    notes='Batch correction for Feb 2026 import',
)
batch = result.batch

# Add correction items
result = service.add_items(
    batch=batch,
    items=[
        {
            'entity_label': 'my_entity',
            'object_id': 123,
            'field_name': 'price',
            'new_value': '50000',
        },
        {
            'entity_label': 'my_entity',
            'object_id': 124,
            'field_name': 'quantity',
            'new_value': 10,
        },
    ],
)

# Preview impact (no commit)
result = service.preview_batch(batch)
print(f"Revenue impact: {batch.revenue_impact}")
print(f"Profit impact: {batch.profit_impact}")

# Apply corrections (transactional)
result = service.apply_batch(batch)
if result.success:
    print(f"Applied {batch.items_applied} corrections")
else:
    print(f"Errors: {result.errors}")

# Rollback if needed
result = service.rollback_batch(batch)
```

## Field Types

The framework supports these field types:

| Type | Example | Validator | Coercer |
|------|---------|-----------|---------|
| `string` | `"ABC123"` | Length, format checks | `str().strip()` |
| `integer` | `42` | Range checks | `int()` |
| `decimal` | `"50000.00"` | Positive, min/max | `Decimal()` |
| `boolean` | `True` | N/A | `bool()` |
| `date` | `"2026-02-05"` | Date format | `datetime.date` |
| `datetime` | `"2026-02-05T10:30:00"` | Datetime format | `datetime.datetime` |

## Workflow

1. **Draft** → Manager creates batch, adds items
2. **Preview** → Manager previews impact (revenue, profit)
3. **Applied** → Manager applies batch (atomic transaction)
4. **(Optional) Rolled Back** → Manager restores original values

## Security

- Only managers can create/apply corrections
- Every action is audited (CorrectionAuditLog)
- All corrections are reversible (rollback)
- IP address and user agent tracked for forensics

## Database Schema

### CorrectionBatch
- `business` - ForeignKey to Business
- `vertical` - Vertical slug (phones, clothing, gym, etc.)
- `status` - DRAFT, PREVIEW, APPLIED, ROLLED_BACK, FAILED
- `created_by`, `applied_by`, `rolled_back_by` - ForeignKeys to User
- `reason` - Required text explaining why corrections are needed
- `revenue_impact`, `profit_impact` - Computed sums

### CorrectionItem
- `batch` - ForeignKey to CorrectionBatch
- `entity_label` - Entity from vertical adapter (e.g., "sale", "member")
- `model_name` - Full model name (e.g., "inventory.InventoryItem")
- `object_id` - ID of the object being corrected
- `field_name` - Field being corrected
- `old_value` - Original value (JSON)
- `new_value` - New value (JSON)
- `revenue_impact`, `profit_impact` - Per-item impact
- `applied_at`, `rolled_back_at` - Timestamps

### CorrectionAuditLog
- `business`, `batch`, `item` - ForeignKeys
- `performed_by` - ForeignKey to User
- `action` - Action performed (e.g., "batch_created", "batch_applied")
- `details` - JSON dict of action details
- `ip_address`, `user_agent` - Request metadata

## Example: Phones Vertical

See `corrections/adapters/phones.py` for a complete example.

Phones registers these entities:
- `phone_sale` - Sold phones (InventoryItem where status=SOLD)
- `phone_stock` - Stock-in records (InventoryItem where status=IN_STOCK)
- `accessory_product` - Accessory master data
- `accessory_stock` - Accessory stock levels

Fields:
- `selling_price`, `order_price` - Pricing corrections
- `imei` - IMEI corrections with uniqueness validation
- `payment_method` - Payment method corrections
- `qty_on_hand`, `avg_cost` - Stock corrections

## Migration from Legacy System

The Phones vertical previously had a standalone correction system in:
- `inventory/models_data_correction.py`
- `inventory/services_data_correction.py`
- `inventory/views_data_correction.py`

This legacy system is now superseded by the generic corrections framework.

**Migration strategy:**
1. Keep legacy system for backward compatibility
2. New corrections use the generic framework
3. UI shows both legacy and new corrections
4. Gradually migrate legacy corrections to new system

## Testing

Run corrections tests:

```bash
pytest corrections/tests/
```

Run E2E tests:

```bash
npx cypress run --spec "cypress/e2e/corrections/**/*.cy.js"
```

## UI

The corrections UI is built with Django templates and Bootstrap 5:

- **Dashboard** - Search, filter, and preview corrections
- **Batch Creator** - Add items to a batch
- **Preview Modal** - Show impact before applying
- **Audit Trail** - Full history of all corrections
- **Rollback UI** - One-click rollback of applied batches

## Contributing

### Adding a New Vertical

1. Create `corrections/adapters/<vertical>.py`
2. Implement `VerticalAdapter` subclass
3. Use `@register_vertical('<vertical>')` decorator
4. Import in `corrections/adapters/__init__.py`
5. Add tests in `corrections/tests/test_<vertical>.py`
6. Document entities and fields in this README

### Code Style

- Follow PEP 8
- Use type hints
- Write docstrings for all public methods
- Add tests for all new features

## FAQ

**Q: Can I correct data across multiple verticals in one batch?**
A: No, each batch is tied to a single vertical. Create separate batches for different verticals.

**Q: What happens if a correction fails mid-batch?**
A: The service uses atomic transactions. If any item fails, the entire batch is rolled back. Failed items are marked with error messages.

**Q: Can I preview a correction without being a manager?**
A: No, only managers can create, preview, and apply corrections for security and audit reasons.

**Q: How do I find records that need correction?**
A: Implement `find_erroneous_entries()` in your vertical adapter with heuristics (e.g., negative prices, duplicate IMEIs).

**Q: Can I rollback a correction multiple times?**
A: No, once rolled back, a batch cannot be re-applied. You must create a new batch.

**Q: How long are audit logs kept?**
A: Forever. Audit logs are never deleted to maintain compliance and forensic trail.

## License

Internal use only. © Emajinet 2026.


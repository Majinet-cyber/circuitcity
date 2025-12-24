# Quick Reference: Rollback & Pricing System

## 🚀 Quick Start

### Rollback a Phone Sale
```python
from sales.services.rollback import RollbackService, RollbackError

try:
    rollback = RollbackService.rollback_sale(
        sale=sale,
        user=request.user,
        business=business,
        reason="RETURNED",
        refunded=True,
        refunded_amount=Decimal("1500000"),
        return_to_stock=True,
        notes="Customer returned phone"
    )
    print(f"✅ Rolled back: {rollback.pk}")
except RollbackError as e:
    print(f"❌ Failed: {e}")
```

### Rollback a Liquor Sale
```python
from sales.services.rollback_verticals import LiquorRollbackService

result = LiquorRollbackService.rollback_liquor_sale(
    sale_id=123,
    user=request.user,
    business=business,
    reason="DAMAGED",
    return_to_stock=True
)
```

### Validate Selling Price
```python
from inventory.utils_pricing import validate_selling_price

validation = validate_selling_price(
    selling_price=Decimal("1500000"),
    cost_price=Decimal("1200000"),
    suggested_price=Decimal("1600000")
)

if not validation['valid']:
    print("❌ Price blocked")
for warning in validation['warnings']:
    print(f"⚠️ {warning}")
if validation['feedback']:
    print(f"✅ {validation['feedback']}")
```

### Format Currency
```python
from inventory.utils_pricing import format_currency, parse_currency_input

# Display
formatted = format_currency(Decimal("2000000"))  # "MK 2,000,000.00"

# Parse user input
amount = parse_currency_input("MK 2,000,000")  # Decimal("2000000")
```

---

## 📋 Common Tasks

### Check if User Can Rollback
```python
from sales.services.rollback import RollbackService

can_rollback, error_msg = RollbackService.can_rollback(
    sale=sale,
    user=request.user,
    business=business
)

if can_rollback:
    # Show rollback button
else:
    # Show error: error_msg
```

### Get Rollback History
```python
from sales.services.rollback import RollbackService

rollbacks = RollbackService.get_rollback_history(
    business=business,
    limit=30
)

for rb in rollbacks:
    print(f"Sale #{rb.sale_id} - {rb.get_reason_display()}")
```

### Get Rollback Stats
```python
from sales.services.rollback import RollbackService

stats = RollbackService.get_rollback_stats(
    business=business,
    days=30
)

print(f"Total rollbacks: {stats['total_rollbacks']}")
print(f"Total refunded: MK {stats['total_refunded']:,.2f}")
```

---

## 🎨 Template Usage

### Add Rollback Button
```django
{% load rollback_helpers %}

<!-- Simple -->
{% rollback_button sale request.user business "phones" %}

<!-- Manual -->
{% can_rollback_sale sale request.user business as can_rollback %}
{% if can_rollback %}
    <a href="{% url 'sales:rollback_confirm' sale.id %}" class="btn btn-danger">
        Rollback Sale
    </a>
{% endif %}
```

### Format Currency in Template
```django
{% load rollback_helpers %}

<!-- Price with commas -->
{{ sale.price|format_currency }}  <!-- MK 2,000,000.00 -->

<!-- Number with commas -->
{{ quantity|format_number }}  <!-- 1,500 -->
```

---

## 🔧 Configuration

### Rollback Reasons
```python
from sales.models import RollbackReason

REASONS = [
    ("DAMAGED", "Damaged Product"),
    ("RETURNED", "Customer Return"),
    ("ERROR", "Data Entry Error"),
    ("OTHER", "Other Reason"),
]
```

### Permission Roles
```python
MANAGER_ROLES = ["MANAGER", "OWNER", "ADMIN"]
AGENT_ROLLBACK_WINDOW = timedelta(minutes=10)
```

---

## 🐛 Debugging

### Check if Sale is Rolled Back
```python
if sale.is_rolled_back:
    print(f"Rolled back at: {sale.rolled_back_at}")
    print(f"Rolled back by: {sale.rolled_back_by}")
    print(f"Reason: {sale.rollback_reason}")
```

### View Logs
```bash
# Watch rollback activity
tail -f /var/log/circuitcity/app.log | grep -i rollback

# Watch errors
tail -f /var/log/circuitcity/app.log | grep -i error
```

### Database Queries
```sql
-- Recent rollbacks
SELECT * FROM sales_sale_rollback 
ORDER BY created_at DESC 
LIMIT 10;

-- Rollback stats by reason
SELECT 
    rollback_reason,
    COUNT(*) as count,
    SUM(refunded_amount) as total_refunded
FROM inventory_liquorsale
WHERE is_rolled_back = TRUE
GROUP BY rollback_reason;
```

---

## ⚠️ Common Errors

### "Sale has already been rolled back"
**Cause:** Trying to rollback a sale that's already rolled back.
**Solution:** This is normal (idempotent). Just inform user it's already done.

### "Agents can only rollback their own sales"
**Cause:** Agent trying to rollback another agent's sale.
**Solution:** Only managers can rollback other people's sales.

### "Agents can only rollback sales within 10 minutes"
**Cause:** Agent trying to rollback old sale.
**Solution:** Ask manager to rollback.

### "Refunded amount cannot exceed sale price"
**Cause:** Refund amount > sale price.
**Solution:** Validate refund amount in form.

---

## 📊 Testing

### Test Rollback Idempotency
```python
# First rollback
rollback1 = RollbackService.rollback_sale(sale, user, business, "RETURNED")

# Second rollback (should return same record)
rollback2 = RollbackService.rollback_sale(sale, user, business, "RETURNED")

assert rollback1.pk == rollback2.pk  # Same rollback record
```

### Test Price Validation
```python
# Below cost
validation = validate_selling_price(
    selling_price=Decimal("1000"),
    cost_price=Decimal("1500")
)
assert len(validation['warnings']) > 0
assert "below cost" in validation['warnings'][0].lower()

# Good margin
validation = validate_selling_price(
    selling_price=Decimal("1500"),
    cost_price=Decimal("1000")
)
assert validation['profit_margin_pct'] == Decimal("50.00")
assert "Great profit margin" in validation['feedback']
```

---

## 🔐 Security

### Permission Checks (Server-Side)
```python
# ALWAYS check permissions server-side
from tenants.models import Membership

membership = Membership.objects.get(user=user, business=business)
role = membership.role.upper()

if role not in ["MANAGER", "OWNER", "ADMIN"]:
    raise PermissionDenied("Only managers can rollback")
```

### Audit Trail
```python
# Every rollback is logged
rollback = SaleRollback.objects.get(pk=123)
print(f"Who: {rollback.created_by}")
print(f"When: {rollback.created_at}")
print(f"Why: {rollback.get_reason_display()}")
print(f"What: Sale #{rollback.sale_id}")
print(f"Refunded: MK {rollback.refunded_amount:,.2f}")
```

---

## 💡 Best Practices

### 1. Always Use Services (Not Direct DB)
```python
# ❌ BAD
sale.is_rolled_back = True
sale.save()

# ✅ GOOD
RollbackService.rollback_sale(sale, user, business, reason)
```

### 2. Always Catch Specific Exceptions
```python
# ❌ BAD
try:
    rollback_sale(...)
except Exception:
    pass  # Silent failure

# ✅ GOOD
try:
    rollback_sale(...)
except RollbackError as e:
    messages.error(request, f"❌ {e}")
    logger.error(f"Rollback failed: {e}", exc_info=True)
```

### 3. Always Format Numbers for Display
```python
# ❌ BAD
f"Price: {price}"  # "Price: 2000000"

# ✅ GOOD
format_currency(price)  # "MK 2,000,000.00"
```

### 4. Always Validate Prices
```python
# ❌ BAD
if selling_price > 0:
    create_sale(...)

# ✅ GOOD
validation = validate_selling_price(selling_price, cost_price)
if not validation['valid']:
    return error
for warning in validation['warnings']:
    show_warning(warning)
create_sale(...)
```

---

## 📞 Support

- **Documentation:** ROLLBACK_PRICING_UX_IMPLEMENTATION.md
- **Deployment:** DEPLOYMENT_CHECKLIST.md
- **Architecture:** ARCHITECTURE_DIAGRAM.md
- **Tests:** test_rollback_implementation.py

---

## 🎯 Key Takeaways

1. **Idempotent** - Safe to retry operations
2. **Transactional** - All-or-nothing
3. **Auditable** - Full trail for compliance
4. **User-Friendly** - Clear messages and feedback
5. **Secure** - Permission checks enforced
6. **Zero HTTP 500s** - All errors handled gracefully

---

*Last Updated: December 24, 2025*

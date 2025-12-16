# Quick Reference: Mobile Table Slider & Commission Settings

## 🚀 Quick Start

### Deployment (3 Steps)
```bash
# 1. Run migration
python manage.py migrate sales 1000

# 2. Verify (all businesses get default settings)
python manage.py shell
>>> from sales.models import CommissionConfig
>>> from tenants.models import Business
>>> for biz in Business.objects.all():
...     config = CommissionConfig.ensure_config(biz)
...     print(f"{biz.name}: enabled={config.commissions_enabled}, mode={config.commission_mode}")

# 3. Test
python manage.py test tests.test_table_slider_and_commissions
```

---

## 📱 Feature 1: Mobile Table Slider

### What It Does
- Makes stock table horizontally scrollable on mobile
- Shows "Swipe to see more →" hint when table overflows
- Opens actions in modal (no clipped dropdowns)

### Where to See It
1. Login as manager
2. Go to `/inventory/list/?view=all`
3. View on mobile device (<992px width)
4. Swipe left/right to see all columns

### Testing
```python
# Test that slider exists
self.assertContains(response, 'data-cc-table-slider')
self.assertContains(response, 'cc-table-slider-container')
```

---

## 💰 Feature 2: Commission Settings

### What It Does
- Managers can choose: **Percentage** or **Fixed Amount** per sale
- Managers can toggle commissions **ON/OFF**
- Agents see "Commissions Disabled" when OFF

### Where to Configure
1. Login as manager
2. Go to **Agents** tab
3. Click **Configure** in "Commission Settings" card
4. Toggle ON/OFF, select mode, enter value
5. Click **Save Settings**

### Defaults (Auto-Applied to All Businesses)
- ✅ Enabled: `True`
- 📊 Mode: `PERCENT`
- 💵 Rate: `12.00%`
- 🔢 Fixed: `MWK 2,000`

### Commission Calculation

**Mode: PERCENT**
```python
commission = sale_price × (base_commission_pct / 100)
# Example: 600,000 × 0.12 = 72,000 MWK
```

**Mode: FIXED**
```python
commission = fixed_commission_amount
# Example: 2,000 MWK (regardless of sale price)
```

**Disabled:**
```python
commission = 0  # No wallet transaction created
```

---

## 🧪 Testing

### Run All Tests
```bash
python manage.py test tests.test_table_slider_and_commissions -v 2
```

### Run Specific Test
```bash
python manage.py test tests.test_table_slider_and_commissions.CommissionSettingsTests.test_percent_commission_calculation
```

### Expected Results
```
14 tests, 0 failures, 0 errors
✅ All tests passing
```

---

## 🔧 Configuration

### Get Commission Config (Python)
```python
from sales.models import CommissionConfig

# For a business
config = CommissionConfig.get_active(business)

if config and config.commissions_enabled:
    if config.commission_mode == 'FIXED':
        commission = config.fixed_commission_amount
    else:
        commission = sale_price * (config.base_commission_pct / 100)
```

### Update Settings (Shell)
```bash
python manage.py shell
>>> from sales.models import CommissionConfig
>>> from tenants.models import Business
>>> biz = Business.objects.get(slug='my-shop')
>>> config = CommissionConfig.ensure_config(biz)
>>> config.commissions_enabled = False
>>> config.save()
```

---

## 🐛 Troubleshooting

### Issue: Swipe hint stuck
```bash
# Clear browser cache
# Force refresh: Ctrl+Shift+R (Windows) / Cmd+Shift+R (Mac)
```

### Issue: Modal not opening
```javascript
// Check Bootstrap loaded
console.log(typeof bootstrap); // Should log "object"

// Check function exists
console.log(typeof showMobileActionsModal); // Should log "function"
```

### Issue: Commission still created when disabled
```python
# Verify setting
>>> config = CommissionConfig.get_active(business)
>>> print(config.commissions_enabled)  # Should be False

# Check recent sales
>>> from wallet.models import WalletTransaction, TxnType
>>> txns = WalletTransaction.objects.filter(
...     type=TxnType.COMMISSION,
...     business=business
... ).order_by('-created_at')[:5]
>>> for t in txns: print(t.amount, t.created_at)
```

### Issue: Agent sees commissions when disabled
```bash
# Clear Django cache
python manage.py clearcache

# Clear template cache
>>> from django.core.cache import cache
>>> cache.clear()
```

---

## 📊 Key Metrics to Monitor

### Commission Settings Changes
```python
# Track in admin or custom report
from sales.models import CommissionConfig
configs = CommissionConfig.objects.filter(
    updated_at__gte=timezone.now() - timedelta(days=7)
).select_related('business')
```

### Sales Without Commission (When Disabled)
```python
from sales.models import Sale
from wallet.models import WalletTransaction, TxnType

sales_without_commission = Sale.objects.exclude(
    id__in=WalletTransaction.objects.filter(
        type=TxnType.COMMISSION
    ).values_list('meta__sale_id', flat=True)
).filter(created_at__gte=timezone.now() - timedelta(days=1))
```

---

## 🔒 Security & Permissions

### Manager-Only Actions
- ✅ View commission settings
- ✅ Update commission settings
- ✅ Toggle commissions ON/OFF

### Agent Actions
- ✅ View own earnings (if enabled)
- ❌ View commission settings
- ❌ Modify commission settings

### Multi-Tenant Isolation
```python
# Each business has independent settings
>>> biz1_config = CommissionConfig.get_active(business1)
>>> biz2_config = CommissionConfig.get_active(business2)
>>> biz1_config.commissions_enabled = False
>>> biz1_config.save()
>>> # business2 settings remain unchanged
```

---

## 📝 Cheat Sheet

### Commission Modes

| Mode | Calculation | Example |
|------|-------------|---------|
| **PERCENT** | `sale × rate / 100` | 600k × 12% = 72k |
| **FIXED** | `fixed_amount` | 2,000 per sale |
| **DISABLED** | `0` | No commission |

### Mobile Table Slider

| Device | Behavior |
|--------|----------|
| **Desktop (≥992px)** | Normal table, no changes |
| **Tablet/Phone (<992px)** | Horizontal scroll, swipe hint, modal actions |

### Default Settings

| Field | Default Value |
|-------|---------------|
| `commissions_enabled` | `True` ✅ |
| `commission_mode` | `'PERCENT'` |
| `base_commission_pct` | `12.00` |
| `fixed_commission_amount` | `2000.00` |

---

## 📞 Support

### Quick Fixes
1. **Clear cache:** `python manage.py clearcache`
2. **Restart server:** `Ctrl+C`, then `python manage.py runserver`
3. **Hard refresh browser:** `Ctrl+Shift+R` (Windows) / `Cmd+Shift+R` (Mac)

### Still Having Issues?
1. Check logs: `tail -f logs/django.log`
2. Run tests: `python manage.py test tests.test_table_slider_and_commissions`
3. Verify migration: `python manage.py showmigrations sales`

---

## ✅ Acceptance Checklist

### Before Deployment
- [ ] Run all tests (14/14 passing)
- [ ] Test on actual mobile device
- [ ] Verify manager can update settings
- [ ] Verify agent sees "disabled" message
- [ ] Check desktop layout unchanged
- [ ] Backup database

### After Deployment
- [ ] Verify migration applied: `python manage.py showmigrations sales`
- [ ] Check all businesses have config: `CommissionConfig.objects.count() == Business.objects.count()`
- [ ] Test creating sale with commissions ON
- [ ] Test creating sale with commissions OFF
- [ ] Verify mobile table scrolls properly
- [ ] Monitor error logs for 24 hours

---

**Last Updated:** December 16, 2025  
**Status:** ✅ Production Ready


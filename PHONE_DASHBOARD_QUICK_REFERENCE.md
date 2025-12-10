# Phone Dashboard - Quick Reference

**Last Updated:** December 10, 2025  
**Status:** ✅ Production Ready

---

## 🚀 Quick Access

**URL:** `/inventory/verticals/phones/`  
**URL Name:** `inventory_verticals:phones_dashboard`  
**View:** `inventory/verticals/phones.py::dashboard()`  
**Template:** `templates/verticals/phones/dashboard.html`

---

## 📊 What It Shows

### Business KPIs (Date-Filtered)
1. **Stock on Hand** - Current phones in inventory
2. **Units Sold** - Phones sold in selected period
3. **Revenue** - Total sales amount
4. **Costs** - COGS + Business expenses
5. **Profit** - Revenue - Costs
6. **Profit Margin** - (Profit / Revenue) × 100

### Payment Mix
- **Cash** - MK amount + percentage
- **Bank** - MK amount + percentage
- **Mobile Money** - MK amount + percentage
- Visual bar chart showing breakdown

### Additional Insights
- Sales trend (last 30 days)
- Fast-moving models (top 5)
- Top agents (top 5)
- Sales by phone model
- Best sales day

---

## 🔧 How Data Updates

### When You Sell a Phone
```
1. Scan & Sell wizard
   ↓
2. Select payment method (Cash/Bank/Mobile)
   ↓
3. Sale recorded:
   - InventoryItem.status = "SOLD"
   - InventoryItem.sold_at = now()
   - InventoryItem.payment_method = selected method
   ↓
4. Dashboard auto-updates:
   ✅ Revenue ↑
   ✅ Units Sold ↑
   ✅ Stock ↓
   ✅ Payment Mix recalculates
```

### When You Add Business Costs
```
1. Admin Wallet → Add Cost (Rent/Salaries/etc.)
   ↓
2. Set effective_date (must be in date range)
   ↓
3. Dashboard includes in Costs:
   ✅ Business Costs ↑
   ✅ Total Costs ↑
   ✅ Profit ↓
```

---

## 🎯 Date Range Filters

| Filter | Description | URL Parameter |
|--------|-------------|---------------|
| **Today** | Sales from current day only | `?range=today` |
| **Last 7 Days** | Sales from past week | `?range=7d` |
| **This Month** (MTD) | From start of month to today | `?range=mtd` (default) |
| **Custom** | User picks start/end dates | `?range=custom&start=YYYY-MM-DD&end=YYYY-MM-DD` |

---

## 📁 Key Files

```
inventory/
├── urls_verticals.py          # Routes /inventory/verticals/phones/ → phones.dashboard
├── verticals/
│   ├── phones.py              # Main dashboard view logic
│   └── base.py                # phone_sales_metrics() helper
├── utils_verticals.py         # Sidebar config (Phone + Inventory Dashboard)
└── tests/
    └── test_phone_dashboard_metrics.py  # Test suite

templates/
└── verticals/
    └── phones/
        └── dashboard.html      # Dashboard UI
```

---

## 🧪 Running Tests

```bash
# All phone dashboard tests
python manage.py test inventory.tests.test_phone_dashboard_metrics

# Specific test
python manage.py test inventory.tests.test_phone_dashboard_metrics.PhoneDashboardMetricsTestCase.test_phones_dashboard_payment_mix

# With verbose output
python manage.py test inventory.tests.test_phone_dashboard_metrics -v 2
```

**Expected Output:**
```
✅ test_phones_dashboard_accessible
✅ test_phones_dashboard_metrics_zero_when_no_sales
✅ test_phones_dashboard_metrics_update_after_sale
✅ test_phones_dashboard_stock_decreases_after_sale
✅ test_phones_dashboard_date_filter_today
✅ test_phones_dashboard_date_filter_7d
✅ test_phones_dashboard_includes_business_costs
✅ test_phones_dashboard_zero_margin_when_revenue_is_zero
✅ test_phones_dashboard_payment_mix  (NEW)
✅ test_phone_business_redirects_to_phones_dashboard_after_login

Ran 10 tests in X.XXXs
OK
```

---

## 🐛 Troubleshooting

### Dashboard Shows MK 0 for Everything

**Check:**
1. Are there phones with `status="SOLD"`?
2. Do sold items have `sold_at` timestamp?
3. Is date range too narrow? (Try "This Month")
4. Is business scoped correctly in session?

**Debug Query:**
```python
from inventory.models import InventoryItem
phones_sold = InventoryItem.objects.filter(
    business=your_business,
    status="SOLD",
    sold_at__isnull=False
)
print(f"Total sold: {phones_sold.count()}")
```

---

### Payment Mix Shows 0%

**Check:**
1. Do sold items have `payment_method` field set?
2. Is wizard setting payment method correctly?

**Debug Query:**
```python
from inventory.models import InventoryItem
from django.db.models import Count

mix = InventoryItem.objects.filter(
    business=your_business,
    status="SOLD"
).values('payment_method').annotate(count=Count('id'))

print(mix)
# Expected: [{'payment_method': 'CASH', 'count': 5}, ...]
```

---

### Business Costs Not Showing

**Check:**
1. Are costs added via Admin Wallet?
2. Is `effective_date` within selected range?
3. Is cost type `COST_ONCE_OFF` or `COST_RECURRING`?
4. Is ledger set to `Ledger.COMPANY`?

**Debug Query:**
```python
from wallet.models import WalletTransaction, Ledger, TxnType
from datetime import date

costs = WalletTransaction.objects.filter(
    business=your_business,
    ledger=Ledger.COMPANY,
    type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING],
    effective_date__gte=date.today().replace(day=1)
)
print(f"Costs this month: {costs.count()}")
```

---

## 🔐 Security Notes

### CSRF Tokens
- **Date Range Filter:** Uses `GET` method (no CSRF needed)
- **Sales Forms:** Use `POST` method (CSRF token required)
- All POST forms include `{% csrf_token %}`

### Permissions
- Dashboard requires:
  - `@login_required` - User must be logged in
  - `@require_business` - Active business in session
  - `@require_business_kind(BusinessKind.PHONES)` - Business must be phone vertical

---

## 📱 Mobile Support

Dashboard is fully responsive:

- **Desktop (≥1024px):** 3-5 column grid
- **Tablet (768-1023px):** 2-3 column grid
- **Mobile (<768px):** Single column stack

**Test on mobile:**
```
1. Open dashboard on phone
2. Check all cards visible
3. Verify date filter buttons wrap nicely
4. Test custom date picker usability
5. Confirm charts render correctly
```

---

## 🎨 Customization

### Change Colors

**File:** `templates/verticals/phones/dashboard.html`

```css
/* Revenue card */
.metric-card.revenue { background: linear-gradient(135deg, #10b981, #059669); }

/* Costs card */
.metric-card.costs { background: linear-gradient(135deg, #f59e0b, #d97706); }

/* Profit card */
.metric-card.profit { background: linear-gradient(135deg, #3b82f6, #2563eb); }
```

### Add New KPI Card

**File:** `inventory/verticals/phones.py`

1. Calculate metric in `dashboard()` view:
```python
# Add to dashboard_kpis dict
dashboard_kpis['new_metric'] = your_calculation
```

2. Display in template:
```html
<article class="metric-card">
  <h3><i class="bi bi-icon-name"></i> New Metric</h3>
  <p>{{ dashboard_kpis.new_metric }}</p>
  <small>description</small>
</article>
```

---

## 🔄 Comparison: Phone vs Inventory Dashboard

| Feature | Phone Dashboard | Inventory Dashboard |
|---------|----------------|---------------------|
| **URL** | `/inventory/verticals/phones/` | `/inventory/dashboard/` |
| **Scope** | Phone vertical only | All products |
| **Payment Mix** | ✅ Yes | ❌ No |
| **Date Filtering** | ✅ Yes (4 options) | ✅ Yes (3 options) |
| **Business Costs** | ✅ Integrated | ✅ Integrated |
| **Top Agents** | ✅ Yes | ✅ Yes (generic) |
| **Sidebar Position** | First | Second |

**Both dashboards coexist!** Phone Dashboard for phone-specific insights, Inventory Dashboard for generic stock management.

---

## ✅ Health Check

Quick checklist to verify dashboard is working:

```
✅ URL accessible: /inventory/verticals/phones/
✅ No 500 errors
✅ No linter errors: python -m pylint inventory/verticals/phones.py
✅ Tests pass: python manage.py test inventory.tests.test_phone_dashboard_metrics
✅ Sidebar shows both dashboards
✅ Date filters work
✅ Payment mix displays correctly
✅ Mobile responsive
```

---

## 📞 Support

**Common Questions:**

**Q: How do I add a phone sale?**  
A: Use "Scan & Sell" from sidebar → Enter IMEI → Set price → Select payment method

**Q: Can I filter by agent?**  
A: Not yet - future enhancement. Currently shows all agents in "Top Agents" section.

**Q: Why is profit negative?**  
A: Business costs (rent, salaries) are higher than profit margin. Review pricing or reduce overhead.

**Q: Can I export metrics?**  
A: Not yet - future enhancement. Currently view-only.

---

## 🎯 Next Steps

1. ✅ **Phone Dashboard Complete** - Working with real data
2. ⏳ **Monitor Usage** - Track user engagement
3. ⏳ **Gather Feedback** - Ask agents/managers for improvements
4. ⏳ **Iterate** - Add features based on feedback

---

**Quick Reference Version:** 1.0  
**Full Documentation:** See `PHONE_DASHBOARD_IMPLEMENTATION_SUMMARY.md`  
**Status:** ✅ Production Ready


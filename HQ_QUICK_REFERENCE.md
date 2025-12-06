# HQ Admin Quick Reference Guide

## 🚀 Quick Start

### Access HQ Admin
1. Log in as staff user (`is_staff=True` or `is_superuser=True`)
2. Navigate to `/hq/` or `/hq/dashboard/`

---

## 📊 Key Features

### 1. Audit Logs
**URL:** `/audit/logs/`

**Purpose:** Track all HQ staff activity (proves transparency - no snooping merchant data)

**Features:**
- View all staff actions (VIEW_PAGE, EXPORT_CSV, UPDATE_SUBSCRIPTION, etc.)
- Filter by: Date range, Business, User, Action
- Export to CSV (respects filters)
- Pagination (50 per page)

**Example Actions Logged:**
```
VIEW_PAGE          → Accessed HQ dashboard
VIEW_PAGE          → Viewed business detail: ABC Corp
EXTEND_SUBSCRIPTION → Extended subscription by 30 days for business ABC Corp
REVOKE_SUBSCRIPTION → Revoked subscription for business XYZ Ltd
EXPORT_CSV         → Exported subscriptions list
```

---

### 2. Business Management
**URL:** `/hq/businesses/`

**Business Detail:** `/hq/businesses/<id>/`

**Membership Controls:**

#### Extend Membership
1. Click "➕ Add Days" button
2. Enter number of days (positive to add, negative to subtract)
3. Confirm
4. Subscription extended immediately
5. Audit log created

**URL Pattern:** `/hq/subscriptions/<pk>/extend/?days=30`

#### Revoke Membership
1. Click "🚫 Revoke/Disable" button
2. Confirm warning
3. Subscription status → Canceled
4. Business loses access (gated by existing middleware)
5. Audit log created

**URL Pattern:** `/hq/subscriptions/<pk>/revoke/`

#### Re-activate Membership
1. (Only visible for canceled subscriptions)
2. Click "✅ Re-activate" button
3. Confirm
4. Subscription status → Active (30 days)
5. Business regains access
6. Audit log created

**URL Pattern:** `/hq/subscriptions/<pk>/activate/`

---

### 3. Subscription Management
**URL:** `/hq/subscriptions/`

**Status Badges:**
- 🟢 **Active** - Subscription active, period not ended
- 🔵 **Trial** - In trial period, shows days left
- 🔴 **Canceled** - Revoked/canceled by HQ or customer
- ⚫ **Expired** - Trial or period ended
- 🟡 **Grace** - Past due but in grace period

**Filters:**
- Status (trial, active, grace, expired, canceled)
- Search (business name, plan name)

**Quick Actions:**
- Extend (inline button)
- Revoke (inline button)
- View details (click business name)

---

### 4. Dashboard
**URL:** `/hq/dashboard/`

**Summary Cards:**
- Total Businesses
- New Businesses (7d)
- Active Subscriptions
- **MRR** (Monthly Recurring Revenue) - sum of active plan amounts
- Open Invoices (count & total)
- Agents (total & new in 30d)
- Stock In/Out (7d)

**Charts:**
- Monthly Sales (year selector)
- New Agent Onboardings
- Wallet Income (custom date range)

**AI Insights:**
Real-time recommendations based on your data:
- 🔴 High Priority: "Collect 5 open invoices — total MWK 250,000"
- 🟡 Medium: "Stock outpaced intake this week. Reorder."
- 🔵 Low: "No new agents in 30d. Consider referral push."
- 🟢 Good: "Healthy cashflow. Consider investing."

**Top Performers:**
Top 10 agents by sales count and revenue

---

## 🔐 Permissions

### Who Can Access HQ?
- ✅ Staff users (`is_staff=True`)
- ✅ Superusers (`is_superuser=True`)
- ❌ Regular merchants/managers
- ❌ Agents

### Audit Log Visibility
- **HQ sees:** Only staff/superuser activity
- **Merchants see:** Nothing (HQ is separate)
- **Purpose:** Transparency - prove HQ doesn't snoop merchant data

---

## 🧪 Testing

### Run Tests
```bash
# Test audit logs
python manage.py test audit.tests

# Test membership controls
python manage.py test hq.tests_membership_controls

# Run all tests
python manage.py test
```

### Manual Test Checklist
```
□ Access /hq/dashboard/ → Dashboard loads
□ Access /audit/logs/ → Audit logs display
□ View business → Subscription info shown
□ Click "Add Days" → Modal opens
□ Add 30 days → Subscription extended
□ Check audit logs → EXTEND_SUBSCRIPTION logged
□ Click "Revoke" → Subscription canceled
□ Check audit logs → REVOKE_SUBSCRIPTION logged
□ Export CSV → Download works
□ Filter logs → Filters apply correctly
```

---

## 📝 Common Tasks

### Task 1: Extend a Trial by 30 Days
1. Go to `/hq/businesses/`
2. Click on business name
3. In Membership section, click "➕ Add Days"
4. Enter `30` in the modal
5. Click "Extend"
6. ✅ Trial extended

### Task 2: Revoke Access for Non-Payment
1. Go to `/hq/businesses/`
2. Click on business name
3. Click "🚫 Revoke/Disable"
4. Confirm the warning
5. ✅ Subscription canceled, business loses access

### Task 3: Export Last Week's Audit Logs
1. Go to `/audit/logs/`
2. Set Start Date: 7 days ago
3. Set End Date: Today
4. Click "Export CSV"
5. ✅ CSV downloaded with filtered logs

### Task 4: Find All Subscription Extensions
1. Go to `/audit/logs/`
2. In Action filter, type: `EXTEND`
3. Press Enter
4. ✅ Only extension actions shown

### Task 5: Review Platform Activity
1. Go to `/hq/dashboard/`
2. Review summary cards
3. Check AI Insights for recommendations
4. Go to `/audit/logs/` for detailed activity
5. ✅ Full visibility into platform health

---

## ⚠️ Important Notes

### Guards & Safety
- ✅ Cannot extend subscriptions with paid invoices (locked)
- ✅ All actions create audit logs (cannot hide activity)
- ✅ All actions require staff permissions
- ✅ Graceful error handling (audit logs never block requests)

### Best Practices
1. **Before revoking:** Check if it's a payment issue or abuse
2. **When extending:** Document reason in notes
3. **Regular audits:** Review logs weekly for anomalies
4. **Monitor MRR:** Track trends, not just absolute numbers
5. **Check AI insights:** Act on high-priority items first

### What NOT to Do
- ❌ Don't manipulate subscriptions with active payments
- ❌ Don't revoke without documenting reason
- ❌ Don't extend indefinitely without plan
- ❌ Don't ignore audit logs (they're your audit trail)

---

## 🆘 Troubleshooting

### "Cannot extend: subscription is locked"
**Cause:** Business has paid invoices  
**Solution:** This is intentional - contact billing team

### "No audit logs found"
**Cause:** Filters too restrictive OR no staff activity yet  
**Solution:** Remove filters, verify staff users exist

### "Subscription not showing"
**Cause:** Business may not have subscription  
**Solution:** Create subscription via `/hq/subscriptions/` or Django Admin

### "Membership controls not visible"
**Cause:** Not logged in as staff user  
**Solution:** Verify `is_staff=True` in user profile

---

## 📚 Related Documentation

- **Full Implementation Summary:** `HQ_ADMIN_IMPLEMENTATION_SUMMARY.md`
- **Reports System:** `REPORTS_IMPLEMENTATION_SUMMARY.md`
- **Quick Start:** `REPORTS_QUICK_START.md`

---

**Last Updated:** December 6, 2025  
**Version:** 1.0  
**Status:** ✅ Production Ready


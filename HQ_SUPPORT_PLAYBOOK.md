# HQ Support Playbook

## Overview

This document provides operational workflows and best practices for HQ staff using the **Overwatch / Support Console** to manage multi-tenant businesses, subscriptions, user access, and operational issues.

---

## 🎯 Core Principles

1. **Audit Everything**: Every HQ action MUST create a `SupportActionLog` entry
2. **Require Reasons**: All destructive actions require a "reason" field explaining why
3. **Safe by Default**: Use double confirms for destructive operations
4. **Tenant Isolation**: Always verify you're operating on the correct business
5. **Never Rewrite History**: Use compensating transactions, not edits
6. **Preserve Data**: Prefer soft deletes and archive over hard deletes

---

## 🏢 Business Management

### Accessing the Business Directory

1. Navigate to `/hq/directory/`
2. Use global search to find businesses by:
   - Business name
   - Owner email
   - Slug/identifier
3. Apply filters for:
   - Status (Active/Pending/Suspended)
   - Subscription status (Trial/Active/Canceled/Expired)
   - Vertical (Phone Shop/Retail/Pharmacy/Gym/etc.)
   - Expiring soon (within 7 days)

### Business Command Center

Access: `/hq/businesses/<id>/command-center/`

**Tabs:**
- **Overview**: Financial summary, sales, agents, stock, pinned notes
- **Subscription**: Payment history, subscription changes, billing details
- **Users**: User accounts, login security status, session management
- **Data**: Inventory, stock levels, archived items
- **Sales**: Recent sales, wallet transactions, revenue
- **Health**: System health, performance metrics, error logs
- **Tickets**: Support tickets for this business
- **Audit**: Complete audit trail of HQ actions

---

## 💳 Subscription Management

### Subscription Status Definitions

| Status | Meaning | Access Allowed? |
|--------|---------|-----------------|
| **trial** | In trial period | ✅ Yes |
| **active** | Paid and current | ✅ Yes |
| **grace** | Past due but in grace period | ✅ Yes (limited) |
| **past_due** | Payment failed, grace expired | ❌ No |
| **canceled** | Manually canceled by HQ | ❌ No |
| **expired** | Period ended, not renewed | ❌ No |

### Common Workflows

#### 1. Extend Subscription Days

**When to use**: Business needs more time, payment processing delay, goodwill gesture

**How to**:
```
1. Go to Business Command Center → Subscription tab
2. Click "Extend Subscription" button
3. Enter number of days (positive to add, negative to subtract)
4. Enter reason: "Payment processing delay - extending 7 days"
5. Confirm
```

**What happens**:
- Adds days to `trial_end` (if trial) or `current_period_end` (if active)
- Updates `next_billing_date`
- Creates `SupportActionLog` entry with before/after state
- Business regains access immediately

**Code**:
```python
from billing.models_extensions import extend_subscription_days

extend_subscription_days(
    subscription,
    days=30,
    reason="Goodwill gesture for technical issues",
    actor=request.user
)
```

---

#### 2. Suspend Subscription (Temporary Lock)

**When to use**: Suspected fraud, terms violation, non-payment (but want to preserve data)

**How to**:
```
1. Go to Business Command Center → Subscription tab
2. Click "Suspend" button
3. Enter reason: "Suspected fraudulent activity - investigating"
4. Optionally set suspension duration (0 = indefinite)
5. Type business name to confirm
6. Click "Suspend"
```

**What happens**:
- Sets `status` to `canceled`
- Sets `canceled_at` and `canceled_by`
- Blocks business access immediately (gating middleware enforces)
- Data is preserved (can be reactivated later)
- Creates audit log

**Code**:
```python
from billing.models_extensions import suspend_subscription

suspend_subscription(
    subscription,
    reason="TOS violation - manual review required",
    actor=request.user,
    days=7  # Optional: auto-unsuspend after 7 days
)
```

**Important**: Suspension is reversible - use this for temporary locks

---

#### 3. Revoke Subscription (Hard Stop)

**When to use**: Confirmed fraud, permanent termination, severe TOS violation

**How to**:
```
1. Go to Business Command Center → Subscription tab
2. Click "Revoke Subscription" button
3. Enter reason: "Confirmed fraudulent chargebacks"
4. Type "DELETE" or business name to confirm
5. Click "Revoke"
```

**What happens**:
- Sets `status` to `canceled`
- Sets `current_period_end` to now (immediate revocation)
- Blocks business access immediately
- Data is preserved but access is terminated
- Creates audit log

**Code**:
```python
from billing.models_extensions import revoke_subscription

revoke_subscription(
    subscription,
    reason="Confirmed fraud - chargebacks filed",
    actor=request.user
)
```

**Difference from Suspend**: Revoke is intended as permanent (though technically reversible)

---

#### 4. Activate Subscription

**When to use**: Reactivate canceled/suspended business after resolution

**How to**:
```
1. Go to Business Command Center → Subscription tab
2. Click "Activate" button
3. Enter number of days to activate for (default: 30)
4. Enter reason: "Issue resolved - payment received"
5. Click "Activate"
```

**What happens**:
- Sets `status` to `active`
- Sets `current_period_start` to now
- Sets `current_period_end` to now + days
- Clears `canceled_at` and `canceled_by`
- Business regains access immediately
- Creates audit log

**Code**:
```python
from billing.models_extensions import activate_subscription

activate_subscription(
    subscription,
    days=30,
    reason="Payment received - reactivating for 30 days",
    actor=request.user
)
```

---

#### 5. Change Plan/Tier

**When to use**: Business upgrades/downgrades, plan migration

**How to**:
```
1. Go to Business Command Center → Subscription tab
2. Click "Change Plan" button
3. Select new plan (Starter/Pro/Pro Max)
4. Enter reason: "Upgrade requested by customer"
5. Confirm
```

**What happens**:
- Updates `plan` foreign key to new plan
- New limits apply immediately
- Creates audit log
- Does NOT change billing cycle or extend subscription

**Code**:
```python
from billing.models_extensions import set_subscription_plan

set_subscription_plan(
    subscription,
    plan_code="pro",
    reason="Customer upgraded to Pro plan",
    actor=request.user
)
```

---

## 🔐 Login & Account Support

### Finding Users

Access: `/hq/businesses/<id>/account-support/`

Shows all users (members) of the business with:
- Login security status (locked, hard blocked, fail count)
- Last login time
- Active sessions count
- Role (Owner/Manager/Agent)

### Common Workflows

#### 1. Unlock Account (Clear Login Lockouts)

**When to use**: User locked out after failed login attempts

**How to**:
```
1. Go to Account Support tab
2. Find user in list
3. Click "Unlock Account"
4. Enter reason: "Customer requested unlock after forgotten password"
5. Confirm
```

**What happens**:
- Resets `LoginSecurity` counters (stage=0, fail_count=0)
- Clears `locked_until` and `hard_blocked`
- User can log in immediately
- Creates audit log

**Code**:
```python
login_sec.note_success()  # Built-in method that resets all counters
```

---

#### 2. Force Logout All Sessions

**When to use**: Security incident, stolen device, user requests logout

**How to**:
```
1. Go to Account Support tab
2. Find user
3. Click "Force Logout"
4. Enter reason: "Security incident - device reported stolen"
5. Confirm
```

**What happens**:
- Invalidates all active sessions for that user
- User must log in again
- Creates audit log

**Note**: Current implementation sets unusable password to invalidate sessions. In production, you'd decode sessions to find and delete specific user sessions.

---

#### 3. Generate Password Reset Link

**When to use**: User forgot password and cannot receive email, phone unavailable

**How to**:
```
1. Go to Account Support tab
2. Find user
3. Click "Reset Password"
4. Enter reason: "User cannot access email - reset requested via phone"
5. Copy generated reset link
6. Send link to user via verified channel (SMS, in-person, etc.)
```

**What happens**:
- Creates `PasswordResetCode` with 24-hour expiration
- Generates secure reset URL
- Displays link to HQ admin (not emailed automatically)
- Creates audit log

**Security**: Always verify user identity before sharing reset link

---

#### 4. Resend OTP

**When to use**: User didn't receive OTP email, OTP expired

**How to**:
```
1. Go to Account Support tab
2. Find user
3. Click "Resend OTP"
4. Enter reason: "OTP not received - resending"
5. Confirm
```

**What happens**:
- Creates new `EmailOTP` with 10-minute expiration
- Sends OTP email (in production setup)
- Creates audit log

---

## 📦 Data Recovery & Operational Fixes

### Inventory/Stock Recovery

#### 1. Search for Stock

**Access**: `/hq/businesses/<id>/command-center/?tab=data`

**Search by**:
- IMEI (for phones)
- Barcode
- Batch number
- Product name

#### 2. Archive Stock (Soft Delete)

**When to use**: Stock is damaged, returned, or no longer available but need to preserve record

**How to**:
```
1. Find stock item
2. Click "Archive"
3. Enter reason: "Damaged in transit - archived pending disposal"
4. Confirm
```

**What happens**:
- Sets `archived=True` on stock item
- Item no longer shows in active inventory
- Can be restored later if needed
- Creates audit log

---

#### 3. Restore Archived Stock

**When to use**: Item was archived by mistake, item is back in inventory

**How to**:
```
1. Go to Data tab → Archived Items
2. Find item
3. Click "Restore"
4. Enter reason: "Item found in warehouse - restoring"
5. Confirm
```

**What happens**:
- Sets `archived=False`
- Item appears in active inventory again
- Creates audit log

---

#### 4. Reverse Accidental Stock-In or Sale

**Important**: DO NOT edit the original transaction. Use compensating entries.

**For Stock-In Reversal**:
```python
# Create compensating "stock out" entry
InventoryItem.objects.create(
    business=business,
    product=product,
    quantity=-original_quantity,  # Negative
    note="Reversal of accidental stock-in on 2025-12-13",
    created_by=request.user
)
```

**For Sale Reversal**:
```python
# Create refund/return sale
Sale.objects.create(
    business=business,
    amount=-original_sale.amount,  # Negative
    note=f"Refund for sale #{original_sale.id}",
    created_by=request.user
)

# Restore stock
# ... (return items to inventory)
```

**Why not edit?**: Editing destroys audit trail and breaks accounting integrity

---

#### 5. Fix Duplicate Entries

**When to use**: Same stock item entered twice by mistake

**Approach**:
1. Identify the duplicate (verify with business)
2. Archive the duplicate (soft delete)
3. If quantities were split, adjust remaining item's quantity
4. Create audit log explaining which was kept and why

**Code**:
```python
duplicate_item.archived = True
duplicate_item.save()

# Log in audit trail
InventoryAudit.objects.create(
    business=business,
    item=duplicate_item,
    action="ARCHIVE_FALLBACK",
    by_user=request.user,
    details=f"Duplicate of item #{original_item.id} - archived"
)
```

---

#### 6. Hard Delete (Last Resort Only)

**⚠️ Extreme Caution Required**

**When to use**: 
- Test data that must be purged
- Confirmed fraudulent entries
- Compliance requirement (e.g., GDPR right to be forgotten)

**Process**:
1. Verify with senior staff/legal
2. Take database backup
3. Document exactly what will be deleted and why
4. Create audit log BEFORE deleting
5. Perform deletion
6. Verify cascade effects

**Never delete**:
- Financial transactions with actual money involved
- Anything referenced by invoices or payments
- Historical sales data

---

## 💰 Payments & Billing Support

### Viewing Payment History

Access: `/hq/businesses/<id>/command-center/?tab=subscription`

Shows:
- All invoices (paid, pending, failed)
- Payment attempts and status
- Wallet transactions

### Common Workflows

#### 1. Record Manual Payment

**When to use**: Payment made via bank transfer, cash, or offline method

**How to**:
```
1. Go to Subscription tab
2. Click "Record Manual Payment"
3. Enter amount
4. Enter payment method (Bank Transfer/Cash/Other)
5. Enter transaction reference
6. Enter reason: "Bank transfer received - reference #12345"
7. Confirm
```

**What happens**:
- Creates `WalletTransaction` with type `MANUAL_PAYMENT`
- Extends subscription by appropriate days based on amount
- Marks any pending invoice as `PAID`
- Creates audit log

**Code**:
```python
from billing.models_extensions import extend_subscription_days

# Record payment
WalletTransaction.objects.create(
    business=business,
    ledger="COMPANY",
    type="MANUAL_PAYMENT",
    amount=amount,
    note=f"Manual payment: {reason}",
    reference=transaction_ref,
    created_by=request.user
)

# Extend subscription
days = int(amount / subscription.plan.amount * 30)  # Proportional
extend_subscription_days(subscription, days, reason, request.user)
```

---

#### 2. Apply Credit/Discount

**When to use**: Goodwill gesture, service outage compensation, promotional credit

**How to**:
```
1. Go to Sales & Wallet tab
2. Click "Apply Credit"
3. Enter amount (positive = credit to business)
4. Enter reason: "Compensation for service outage on 2025-12-10"
5. Confirm
```

**What happens**:
- Creates adjustment transaction in wallet
- Balance increases for business
- Creates audit log
- Does NOT automatically extend subscription (do separately if needed)

**Code**:
```python
WalletTransaction.objects.create(
    business=business,
    ledger="COMPANY",
    type="ADJUSTMENT",
    amount=Decimal("50000.00"),  # Credit
    note="Service outage compensation",
    created_by=request.user
)
```

---

#### 3. Refund Payment

**When to use**: Overcharge, subscription canceled mid-period, billing error

**Process**:
1. Verify refund is justified
2. Process refund via original payment method (Stripe/Pesapal/etc.)
3. Record refund transaction
4. Do NOT edit original payment
5. Create audit log

**Code**:
```python
# Create refund transaction
WalletTransaction.objects.create(
    business=business,
    ledger="COMPANY",
    type="REFUND",
    amount=-original_amount,  # Negative
    note=f"Refund for payment #{payment_id}",
    reference=refund_reference,
    created_by=request.user
)
```

---

#### 4. Resend Receipt/Invoice

**When to use**: Customer didn't receive invoice email

**How to**:
```
1. Go to Subscription tab
2. Find invoice in list
3. Click "Resend"
4. Verify email address
5. Confirm
```

**What happens**:
- Regenerates invoice PDF
- Sends email to business owner
- Creates audit log

---

## 🎫 Support Tickets & Notes

### Creating a Support Ticket

**When to use**: 
- Customer reports issue via email/phone
- Proactive HQ investigation
- Incident tracking

**How to**:
```
1. Go to Business Command Center → Tickets tab
2. Click "Create Ticket"
3. Fill in:
   - Title: Short description
   - Category: Login/Payment/Data/Bug/Feature/Other
   - Priority: Low/Medium/High/Urgent
   - Description: Detailed issue description
4. Optionally assign to HQ staff member
5. Create
```

**Ticket gets**:
- Auto-generated ticket number (e.g., `HQ-20251213-0042`)
- Status: Open
- Timestamps

### Adding Timeline Notes

```
1. Open ticket
2. Click "Add Note"
3. Select note type: Comment/Status Change/Action Taken
4. Mark as internal if not for customer viewing
5. Save
```

### Closing Tickets

```
1. Open ticket
2. Add final note: "Issue resolved - extended subscription 7 days"
3. Change status to "Resolved" or "Closed"
4. Save
```

**Tip**: Mark ticket as "Resolved" when fixed, "Closed" when customer confirms

---

### Pinned Business Notes

**When to use**: Record special arrangements, quirks, or important context

**Examples**:
- "Manual billing arrangement - invoices sent via email"
- "Owner often forgets OTP - verify via phone"
- "Located in remote area - allows 48h grace for payments"

**How to**:
```
1. Go to Business Command Center → Overview tab
2. Scroll to Pinned Notes section
3. Click "Add Note"
4. Enter title and content
5. Save
```

**Notes are**:
- Visible to all HQ staff
- Shown prominently on business detail page
- NOT visible to business users

---

## 🔍 Audit Trail

### Accessing Audit Logs

**Global**: `/audit/logs/`
**Per Business**: `/hq/businesses/<id>/command-center/?tab=audit`

### Filtering Logs

```
- Date range: Start date → End date
- Business: Select from dropdown
- Action type: Filter by specific action
- User: Filter by HQ staff member
```

### Exporting to CSV

```
1. Apply desired filters
2. Click "Export CSV"
3. CSV includes all filtered logs
4. Filename format: audit_logs_YYYYMMDD_YYYYMMDD.csv
```

### What Gets Logged

**All HQ actions log**:
- Actor (who performed it)
- Business (which business)
- Action type (EXTEND_SUBSCRIPTION, UNLOCK_ACCOUNT, etc.)
- Reason (required explanation)
- Payload before/after (state changes)
- Entity type and ID (what was affected)
- IP address and user agent
- Timestamp

**Logged Actions**:
- Subscription changes (extend, revoke, suspend, activate, change plan)
- Login/account actions (unlock, reset password, force logout, resend OTP)
- Data operations (archive, restore, delete)
- Payment recording (manual payment, credit, refund)
- Ticket creation and updates
- Business note creation

---

## 🚨 Emergency Procedures

### Business Completely Locked Out (No Access)

```
1. Verify business identity via phone/email
2. Check subscription status
3. If expired/canceled:
   - Record why (payment failed? manual cancel?)
   - If legitimate, activate for 7-30 days
   - Enter reason in audit log
4. If user locked out:
   - Check LoginSecurity status
   - Unlock account
   - Generate password reset link if needed
5. If technical issue:
   - Create support ticket
   - Escalate to engineering
   - Extend subscription as compensation
```

### Suspected Fraud

```
1. DO NOT ALERT BUSINESS
2. Document evidence
3. Suspend subscription immediately
4. Reason: "Suspected fraudulent activity - under investigation"
5. Review transaction history
6. Check wallet for suspicious activity
7. Escalate to senior staff/legal
8. If confirmed: Revoke subscription
9. If false alarm: Activate + compensate
```

### Payment Dispute/Chargeback

```
1. Check payment history
2. Gather evidence (invoices, usage logs, audit trail)
3. Suspend subscription pending resolution
4. Reason: "Payment dispute - chargeback filed"
5. Work with payment processor
6. If resolved in our favor: Reactivate
7. If resolved against us: Refund and optionally reactivate
8. If fraudulent chargeback: Revoke subscription
```

### Data Loss/Corruption

```
1. DO NOT PANIC
2. Check if data is archived (not deleted)
3. If archived: Restore from archive
4. If deleted recently: Check database backups
5. Document exactly what was lost
6. Create incident ticket
7. Notify business owner
8. Restore from backup if possible
9. Compensate appropriately (extend subscription, credit)
10. Document in audit log
```

---

## ✅ Checklist: Before Making HQ Changes

- [ ] Verified correct business (check business name and ID)
- [ ] Verified authorization (am I allowed to do this?)
- [ ] Understood the request (what does the business actually need?)
- [ ] Prepared a clear reason statement
- [ ] Checked for side effects (will this break something?)
- [ ] Ready to create audit log
- [ ] Confirmed action is reversible (or have backup plan)
- [ ] Business is aware (if appropriate)

---

## 📊 Reporting & Metrics

### Key Metrics to Track

- Failed payments (last 7 days)
- Subscriptions expiring soon (next 7 days)
- Open support tickets
- Average ticket resolution time
- Suspended/revoked businesses
- Trial-to-paid conversion rate
- Churn rate
- MRR (Monthly Recurring Revenue)

**Access**: HQ Dashboard (`/hq/dashboard/`)

---

## 🆘 Escalation

**When to escalate**:
- Legal/compliance issues
- Confirmed fraud
- Data breach suspicions
- Complex technical issues beyond HQ scope
- Payment disputes over $X amount
- Requests for permanent data deletion

**How to escalate**:
1. Create detailed support ticket
2. Mark priority as "Urgent"
3. Assign to senior staff
4. Document all context
5. Do NOT take irreversible actions without approval

---

## 📝 Best Practices Summary

1. **Always provide reasons** - Future you will thank you
2. **Use compensating transactions** - Never rewrite history
3. **Soft delete by default** - Archive, don't destroy
4. **Verify before acting** - Check business name/ID
5. **Document in tickets** - Create paper trail
6. **Check audit logs** - Learn from past actions
7. **Test on staging first** - If unsure, try on test business
8. **Ask for help** - Better to escalate than make mistake
9. **Communicate clearly** - Keep business informed
10. **Review regularly** - Check open tickets and alerts daily

---

## 🔗 Quick Links

- HQ Dashboard: `/hq/dashboard/`
- Business Directory: `/hq/directory/`
- Audit Logs: `/audit/logs/`
- Support Tickets: `/hq/tickets/` (if implemented)

---

**Last Updated**: December 2025  
**Version**: 1.0  
**Owner**: HQ Support Team



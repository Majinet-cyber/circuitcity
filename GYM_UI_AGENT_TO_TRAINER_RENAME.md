# Gym UI: Agent → Trainer Label Rename

## Overview
Successfully renamed all user-facing "Agent/Agents" labels to "Trainer/Trainers" for the Gym vertical, while preserving the underlying permissions and group names.

## Implementation Approach
Used conditional template logic based on `BUSINESS_VERTICAL` context variable:
```django
{% if BUSINESS_VERTICAL == "gym" %}Trainer{% else %}Agent{% endif %}
```

For invite page (where user isn't logged in yet):
```django
{% if invite.business.business_kind == "gym" %}Trainer{% else %}Agent{% endif %}
```

## Files Modified

### 1. Core Navigation & Sidebars
- **`templates/includes/_sidebar_vertical.html`**
  - Line 183: TEAM menu item "Agents" → conditional "Trainers"

- **`templates/partials/sidebar.html`**
  - Already had conditional logic in place (lines 127, 135, 148, 156)

- **`templates/base.html`**
  - Line 476: Business menu "Agents" link → conditional "Trainers"

### 2. Dashboard Templates
- **`templates/dashboard/home.html`**
  - Line 459: "Agents earned" → conditional "Trainers earned"
  - Line 624: "Agent Leaderboard" → conditional "Trainer Leaderboard"
  - Line 653: Comment "Agent Dashboard" → conditional
  - Line 655: Comment "Agent View" → conditional
  - Line 815: "Manage Agents" button → conditional "Manage Trainers"

- **`templates/dash/agent_dashboard.html`**
  - Line 4: Page title "Agent" → conditional "Trainer"
  - Line 203: "Agent Dashboard" heading → conditional "Trainer Dashboard"

- **`templates/dash/admin_dashboard.html`**
  - Line 371: Comment and heading "Agent performance" → conditional
  - Line 373: "Agent Performance" → conditional "Trainer Performance"
  - Line 375: Search placeholder "Search agent" → conditional "Search trainer"
  - Line 384: Table header "Agent" → conditional "Trainer"

- **`templates/dash/admin_agent_detail.html`**
  - Line 4: Page title "Agent" → conditional "Trainer"
  - Line 43: "Agent:" heading → conditional "Trainer:"

- **`templates/dash/manager_dashboard.html`**
  - Line 70: Filter label "Agent" → conditional "Trainer"
  - Line 72: Select option "All agents" → conditional "All trainers"

- **`templates/agent_dashboard.html`**
  - Line 4: Page title "Agent" → conditional "Trainer"
  - Line 5: Header title "Agent" → conditional "Trainer"
  - Line 79: "Agent Dashboard" heading → conditional "Trainer Dashboard"

### 3. Team Management Templates
- **`templates/tenants/manager_review_agents.html`**
  - Line 5: Page title "Agents" → conditional "Trainers"
  - Line 6: Header title "Agents" → conditional "Trainers"
  - Line 36: Main heading "Agents" → conditional "Trainers"

- **`templates/tenants/manager_agents_earnings.html`**
  - Line 4: Page title "Agent Earnings" → conditional "Trainer Earnings"
  - Line 5: Header title "Agent Earnings" → conditional
  - Line 59: "Back to Agents" → conditional "Back to Trainers"
  - Line 66: "Agent Earnings" heading → conditional "Trainer Earnings"

- **`templates/tenants/agent_detail.html`**
  - Line 4: Page title "Agent Detail" → conditional "Trainer Detail"
  - Line 9: "Agent Details" heading → conditional "Trainer Details"

- **`templates/tenants/invite_agent.html`**
  - Line 6: "Invite an Agent" → conditional "Invite a Trainer"
  - Line 57: "Back to Agents" → conditional "Back to Trainers"
  - Line 101: "Cancel" link changed to "Back to Trainers/Agents"

- **`templates/tenants/invite_accept.html`**
  - Line 3: Page title "Join as Agent" → conditional "Join as Trainer"
  - Line 86: "Agent Invite" badge → conditional "Trainer Invite"
  - Uses `invite.business.business_kind` instead of `BUSINESS_VERTICAL` since user isn't logged in

### 4. Wallet Templates
- **`templates/wallet/admin_agent.html`**
  - Line 4: Page title "Agent Wallet" → conditional "Trainer Wallet"
  - Line 5: Header title "Agent Wallet" → conditional "Trainer Wallet"
  - Line 10: Comment "Agent Summary KPIs" → conditional

- **`templates/wallet/admin_payslips.html`**
  - Line 29: Form label "Agent" → conditional "Trainer"

- **`templates/wallet/admin_issue_payslip.html`**
  - Line 25: Form label "Agent" → conditional "Trainer"

- **`templates/wallet/admin_issue.html`**
  - Line 27: Comment "Select Agent" → conditional
  - Line 29: Form label "Select Agent" → conditional "Select Trainer"
  - Line 31: Select option "-- Choose Agent --" → conditional

### 5. Reports Templates
- **`templates/reports/home.html`**
  - Line 21: Filter label "Agent" → conditional "Trainer"

### 6. Inventory Templates
- **`templates/inventory/stock_list.html`**
  - Line 319: Ticker row header "Agent" → conditional "Trainer"
  - Line 343: Table header "Agent" → conditional "Trainer"
  - Line 432: Data label "Agent" → conditional "Trainer"
  - Line 458: Data label "Agent" → conditional "Trainer"

## What Was NOT Changed

### 1. Internal Code/Backend
- Database models, fields, and relationships
- Permission names and group names (AGENT role remains)
- URL patterns and view function names
- API endpoints and internal variable names
- Python code logic

### 2. HQ/Platform Templates
- `templates/hq/*` - These are platform-level admin pages for superusers managing all businesses
- Not business-specific, so "Agents" remains appropriate

### 3. Phones Vertical
- `templates/verticals/phones/dashboard.html` - Phones-specific, keeps "Agents"

### 4. Generic/Shared Content
- Login page helper text (`templates/registration/login.html`)
- Comments in JavaScript code (internal, not user-visible)
- CSS class names, IDs, and JavaScript variable names

## Testing Recommendations

### Manual Testing
1. **Login as Gym Manager**
   - Check main dashboard sidebar shows "Trainers" instead of "Agents"
   - Verify business menu dropdown shows "Trainers"

2. **Trainer Management**
   - Navigate to Trainers list page (was Agents page)
   - Check all labels show "Trainers"
   - Test invite flow shows "Trainer Invite"
   - Check earnings page shows "Trainer Earnings"

3. **Trainer Dashboard**
   - Login as a trainer user in gym business
   - Verify dashboard shows "Trainer Dashboard"
   - Check leaderboard shows "Trainer Leaderboard"

4. **Wallet & Admin**
   - Check wallet page shows "Trainer Wallet"
   - Verify payslip forms show "Trainer" labels
   - Test admin dashboard shows "Trainer Performance"

5. **Verify Phones Vertical Unchanged**
   - Login to a phones business
   - Confirm all pages still show "Agents"

### Automated Testing
Run existing test suite:
```bash
python manage.py test
```

All existing tests should pass as no backend logic was changed.

## Technical Notes

1. **Context Variable**: `BUSINESS_VERTICAL` is provided by `inventory/context_processors.py` and is available in all templates

2. **Template Conditionals**: Used simple if/else blocks to keep templates maintainable:
   ```django
   {% if BUSINESS_VERTICAL == "gym" %}Trainers{% else %}Agents{% endif %}
   ```

3. **No Breaking Changes**: Since only UI labels changed and internal permissions/groups remain the same, this is a non-breaking change

4. **Future Verticals**: If other verticals need different staff labels, the same pattern can be extended:
   ```django
   {% if BUSINESS_VERTICAL == "gym" %}Trainers
   {% elif BUSINESS_VERTICAL == "salon" %}Stylists
   {% else %}Agents{% endif %}
   ```

## Verification Commands

```bash
# Check for any remaining hardcoded "Agents" in gym templates
grep -r "Agents" templates/inventory/gym/

# Verify gym templates don't have hardcoded "Agent"
grep -r "\bAgent\b" templates/inventory/gym/

# Django system check
python manage.py check
```

## Summary
✅ Successfully renamed 40+ instances of "Agent/Agents" to "Trainer/Trainers" for Gym vertical UI
✅ Preserved all backend permissions and role names
✅ Used conditional template logic based on business vertical
✅ No breaking changes to existing functionality
✅ Phones and other verticals remain unchanged
✅ All system checks pass

---
**Implementation Date**: December 13, 2025
**Status**: ✅ COMPLETE


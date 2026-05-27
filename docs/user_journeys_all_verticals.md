# User Journeys - All Verticals (Circuit City / Emajinet SaaS)

**Document Purpose**: Complete specification of all user journeys for all verticals (Admin + Agent roles). This serves as the test coverage specification for automated smoke tests.

**Last Updated**: December 22, 2025  
**Status**: Production System Documentation

---

## Table of Contents

1. [Global Journeys (All Verticals)](#global-journeys)
2. [HQ Platform Admin Journey](#hq-platform-admin-journey)
3. [Phones Vertical](#phones-vertical)
4. [Pharmacy Vertical](#pharmacy-vertical)
5. [Clothing Vertical](#clothing-vertical)
6. [Liquor Vertical](#liquor-vertical)
7. [Gym Vertical](#gym-vertical)
8. [Role Definitions](#role-definitions)
9. [Test Coverage Matrix](#test-coverage-matrix)

---

## Global Journeys

These journeys apply to **every business vertical** regardless of the business type.

### 1. Onboarding Journey (HQ Admin / Platform Owner)

**Actor**: Platform Administrator (is_staff=True or is_superuser=True)

**Steps**:

1. **Create Business**
   - Navigate to: `/hq/businesses/`
   - Click "Add New Business"
   - Fill form: name, slug, business_kind (phones/pharmacy/clothing/liquor/gym)
   - Submit
   - **Pass Condition**: Business appears in business list, can be clicked to view details

2. **Create HQ Location**
   - Navigate to business detail page
   - Click "Add Location"
   - Fill form: location name, address
   - Set as headquarters (HQ): checkbox
   - **Pass Condition**: Location created, marked as HQ

3. **Create Additional Locations** (if multi-location)
   - Repeat location creation for branches
   - **Pass Condition**: Multiple locations visible, each with correct business association

4. **Invite Manager**
   - Navigate to: `/tenants/manager/agents/` or business agents page
   - Click "Invite Manager"
   - Enter email, assign role: MANAGER
   - **Pass Condition**: Invitation sent, pending membership created

5. **Invite Agent**
   - Navigate to: `/tenants/manager/agents/`
   - Click "Invite Agent"
   - Enter email, assign role: AGENT, select location
   - **Pass Condition**: Invitation sent, agent assigned to location

6. **Assign Roles/Permissions**
   - Via Django Admin: `/admin/auth/group/`
   - Create group: `biz:{BUSINESS_ID}:MANAGER` or `biz:{BUSINESS_ID}:AGENT`
   - Assign user to group
   - **Pass Condition**: User can access business dashboard with correct permissions

7. **Verify Context Switching**
   - If user belongs to multiple businesses:
     - Click business switcher (top-right)
     - Select different business
     - **Pass Condition**: Sidebar updates, dashboard shows correct business data

8. **Verify Location Switching** (for agents)
   - If agent assigned to multiple locations:
     - Switch location via location selector
     - **Pass Condition**: Data scoped to selected location

---

### 2. Core System Journeys (All Roles)

#### A. Authentication & Session Management

**Login Journey**:
1. Navigate to: `/login/` or `/accounts/login/`
2. Enter valid credentials
3. **Pass Condition**: Redirected to dashboard, session established

**OTP/2FA Journey** (if enabled):
1. After login, system sends OTP (email/SMS)
2. Enter OTP code
3. **Pass Condition**: 2FA verified, access granted

**Password Change**:
1. Navigate to: `/accounts/password/change/`
2. Enter current password, new password
3. Submit
4. **Pass Condition**: Password updated, can login with new password

**Logout**:
1. Click user avatar → Logout
2. **Pass Condition**: Session cleared, redirected to login page

#### B. Profile & Settings

**Profile Management**:
1. Navigate to: `/accounts/profile/` or settings
2. Update name, avatar, contact info
3. **Pass Condition**: Changes saved, reflected in UI

**Business Settings** (Manager only):
1. Navigate to business settings
2. Update currency, timezone, business details
3. **Pass Condition**: Settings saved

#### C. Session Management

**View Active Sessions**:
1. Navigate to: `/accounts/sessions/` (if exists)
2. View list of active sessions
3. **Pass Condition**: Current session and other devices shown

**Revoke Session**:
1. Click "Revoke" on a session
2. **Pass Condition**: Session terminated, device logged out

---

## HQ Platform Admin Journey

**Actor**: Platform Administrator (is_staff=True or is_superuser=True)

**Sidebar Links** (from `/hq/` sidebar):

### MAIN Navigation

1. **HQ Dashboard**
   - URL: `/hq/` or `/hq/home/`
   - **Expected**: Overview of all businesses, subscriptions, revenue metrics
   - **Pass Condition**: KPI cards visible, no 500 errors

2. **Businesses**
   - URL: `/hq/businesses/`
   - **Expected**: List of all businesses with filters
   - **Pass Condition**: Business list loads, can view/edit businesses

3. **Subscriptions**
   - URL: `/hq/subscriptions/`
   - **Expected**: List of active subscriptions
   - **Pass Condition**: Subscription list loads with status

4. **Invoices**
   - URL: `/billing/invoices/`
   - **Expected**: Invoice list for all businesses
   - **Pass Condition**: Invoice list renders

5. **Agents**
   - URL: `/hq/agents/`
   - **Expected**: Platform-wide agent list
   - **Pass Condition**: Agent list loads

6. **Stock Trends** (if exists)
   - URL: `/hq/stock-trends/`
   - **Expected**: Cross-business stock analytics
   - **Pass Condition**: Charts/graphs render

7. **Analytics**
   - URL: `/hq/analytics/`
   - **Expected**: Platform-wide analytics dashboard
   - **Pass Condition**: KPIs and charts load

### Support & Monitoring

8. **Tickets**
   - URL: `/support/hq/tickets/`
   - **Expected**: Support ticket queue
   - **Pass Condition**: Ticket list loads

9. **Audit Logs**
   - URL: `/audit/logs/`
   - **Expected**: System audit trail
   - **Pass Condition**: Log entries visible with filters

### Admin Tools

10. **Django Admin**
    - URL: `/admin/`
    - **Expected**: Django admin interface
    - **Pass Condition**: Admin index loads

11. **Logout**
    - URL: `/logout/`
    - **Expected**: User logged out
    - **Pass Condition**: Redirected to login

---

## Phones Vertical

**Business Kind**: `phones` (default vertical, uses core `/inventory/` routes)

### Admin Journey

**Sidebar Links**:

#### MAIN Section

1. **Dashboard**
   - URL: `/inventory/verticals/phones/dashboard/`
   - **Expected**: Phone store KPIs (revenue, stock count, top models, agent performance)
   - **Pass Condition**: Dashboard loads, KPI cards visible, no template errors

2. **Analytics**
   - URL: `/app/analytics/`
   - **Expected**: Advanced analytics with charts (sales trends, profit margins)
   - **Pass Condition**: Charts render, no 500 errors

3. **Stock**
   - URL: `/inventory/list/`
   - **Expected**: List of all phone inventory items (IMEI-tracked)
   - **Pass Condition**: Stock list table loads, can filter/search

4. **Scan IN**
   - URL: `/inventory/scan/`
   - **Expected**: Scan IMEI to add new phone stock
   - **Pass Condition**: Scanner interface loads, can enter IMEI

5. **Scan & Sell**
   - URL: `/inventory/phone-sale-wizard/`
   - **Expected**: Scan IMEI to sell phone (wizard flow)
   - **Pass Condition**: Wizard loads, can scan/select phone

#### LAYBY Section

6. **Layby**
   - URL: `/layby/` or `/layby/dashboard/`
   - **Expected**: Layby orders dashboard (installment payments)
   - **Pass Condition**: Layby dashboard loads with orders

#### MORE Section (Collapsible)

7. **Wallet** (all users)
   - URL: `/wallet/` or `/wallet/agent/`
   - **Expected**: Agent wallet showing commissions, withdrawals
   - **Pass Condition**: Wallet balance visible

8. **Time Logs** (all users)
   - URL: `/inventory/time/logs/`
   - **Expected**: Time clock logs (clock-in/out)
   - **Pass Condition**: Log list loads

9. **Reports** (Manager only)
   - URL: `/reports/`
   - **Expected**: Report dashboard
   - **Pass Condition**: Report list/dashboard loads

10. **Simulator** (all users)
    - URL: `/simulator/business/`
    - **Expected**: Business simulator tool
    - **Pass Condition**: Simulator interface loads

11. **Products** (Manager only)
    - URL: `/inventory/phone-products/`
    - **Expected**: Product catalog (phone models)
    - **Pass Condition**: Product list loads, can add/edit

12. **Admin Wallet** (Manager only)
    - URL: `/wallet/admin/`
    - **Expected**: Admin view of all wallets
    - **Pass Condition**: Wallet list loads

13. **Costs** (Manager only)
    - URL: `/wallet/admin/costs/`
    - **Expected**: Business expenses list
    - **Pass Condition**: Cost list loads, can add expenses

14. **Agents** (Manager only)
    - URL: `/tenants/manager/agents/`
    - **Expected**: Agent management page
    - **Pass Condition**: Agent list loads, can invite/edit

15. **Locations** (Manager only)
    - URL: `/tenants/manager/locations/`
    - **Expected**: Location management
    - **Pass Condition**: Location list loads

16. **Data Backup** (Manager only)
    - URL: `/backups/`
    - **Expected**: Database backup interface
    - **Pass Condition**: Backup list/options load

17. **Choose Plan** (Manager only)
    - URL: `/billing/plans/`
    - **Expected**: Subscription plan selection
    - **Pass Condition**: Plans display

18. **Orders** (Manager only)
    - URL: `/inventory/orders/`
    - **Expected**: Purchase orders list
    - **Pass Condition**: Order list loads

### Agent Journey

**Agent sees same sidebar EXCEPT**:
- **Excludes** (require_manager=True): Reports, Products, Admin Wallet, Costs, Agents, Locations, Data Backup, Choose Plan, Orders
- **Includes**: Dashboard, Analytics, Stock, Scan IN, Scan & Sell, Layby, Wallet, Time Logs, Simulator

**Key Actions**:

1. **View Agent Dashboard**
   - Same dashboard but filtered to agent's sales/performance
   - **Pass Condition**: Agent-scoped KPIs visible

2. **Scan IN Stock**
   - Can add new phones to inventory
   - **Pass Condition**: IMEI scanned, stock added

3. **Make Sale**
   - Use "Scan & Sell" wizard
   - Select phone (IMEI), enter customer details, payment
   - **Pass Condition**: Sale created, commission recorded, stock updated

4. **View Wallet**
   - Check commission balance
   - **Pass Condition**: Wallet shows earnings

5. **Clock In/Out**
   - Use Time Logs
   - **Pass Condition**: Time log entry created

---

## Pharmacy Vertical

**Business Kind**: `pharmacy`

### Admin Journey

**Sidebar Links**:

#### MAIN Section

1. **Dashboard**
   - URL: `/dashboard/` (pharmacy vertical context)
   - **Expected**: Pharmacy KPIs (revenue, low stock alerts, expiring batches)
   - **Pass Condition**: Dashboard loads with pharmacy-specific widgets

2. **Analytics**
   - URL: `/app/analytics/`
   - **Expected**: Sales trends, top products
   - **Pass Condition**: Charts render

3. **Fast Sell**
   - URL: `/verticals/pharmacy/fast-sell/`
   - **Expected**: Barcode scan + instant sell interface
   - **Pass Condition**: Scanner loads, can scan/sell

4. **Pharmacy & Cosmetics Hub**
   - URL: `/verticals/pharmacy/hub/`
   - **Expected**: Central hub with quick actions (stock-in, sell, batches)
   - **Pass Condition**: Hub page loads with action cards

5. **Stock In**
   - URL: `/pharmacy/stock-in/`
   - **Expected**: Wizard to add new pharmacy products with batch/expiry
   - **Pass Condition**: Stock-in form loads

6. **Sell**
   - URL: `/pharmacy/sell/`
   - **Expected**: Manual sell form (non-fast-sell)
   - **Pass Condition**: Sell form loads

7. **Batches**
   - URL: `/pharmacy/batches/`
   - **Expected**: List of product batches with expiry dates
   - **Pass Condition**: Batch list loads, shows expiring items

#### MORE Section (same as Phones, excluding Products/Orders)

8. Wallet (all users)
9. Time Logs (all users)
10. Reports (Manager only)
11. Simulator (all users)
12. Admin Wallet (Manager only)
13. Costs (Manager only)
14. Agents (Manager only)
15. Locations (Manager only)
16. Data Backup (Manager only)
17. Choose Plan (Manager only)

### Agent Journey

**Agent sees**: Dashboard, Analytics, Fast Sell, Hub, Stock In, Sell, Batches, Wallet, Time Logs, Simulator

**Key Actions**:

1. **Fast Sell**
   - Scan barcode → auto-fill product → select quantity → complete sale
   - **Pass Condition**: Sale created, stock decremented

2. **Stock In**
   - Add product with batch number and expiry date
   - **Pass Condition**: Stock increased, batch tracked

3. **View Expiring Batches**
   - Navigate to Batches page
   - Filter by "Near Expiry"
   - **Pass Condition**: Expiring products highlighted

---

## Clothing Vertical

**Business Kind**: `clothing`

### Admin Journey

**Sidebar Links**:

#### MAIN Section

1. **Dashboard**
   - URL: `/verticals/clothing/dashboard/`
   - **Expected**: Clothing store KPIs (revenue, stock by size/category, top items)
   - **Pass Condition**: Dashboard loads with clothing metrics

2. **Analytics**
   - URL: `/app/analytics/`
   - **Expected**: Sales trends
   - **Pass Condition**: Charts render

3. **Fast Sell**
   - URL: `/verticals/clothing/fast-sell/`
   - **Expected**: Barcode scan + instant sell
   - **Pass Condition**: Scanner interface loads

4. **Clothing Hub**
   - URL: `/verticals/clothing/hub/`
   - **Expected**: Hub with quick actions
   - **Pass Condition**: Hub page loads

5. **Add Product**
   - URL: `/inventory/wizard/clothing/`
   - **Expected**: Product creation wizard (name, size, color, price)
   - **Pass Condition**: Wizard loads, can create product

6. **Scan IN**
   - URL: `/verticals/clothing/scan-in/`
   - **Expected**: Scan barcodes to add stock
   - **Pass Condition**: Scanner loads

7. **Sell**
   - URL: `/verticals/clothing/sell/`
   - **Expected**: Manual sell form
   - **Pass Condition**: Sell form loads

#### MORE Section (same as Pharmacy + Orders)

8. Wallet (all users)
9. Time Logs (all users)
10. Reports (Manager only)
11. Simulator (all users)
12. Admin Wallet (Manager only)
13. Costs (Manager only)
14. Agents (Manager only)
15. Locations (Manager only)
16. Data Backup (Manager only)
17. Choose Plan (Manager only)
18. **Orders** (Manager only)
    - URL: `/inventory/orders/`
    - **Expected**: Purchase orders
    - **Pass Condition**: Order list loads

### Agent Journey

**Agent sees**: Dashboard, Analytics, Fast Sell, Hub, Add Product, Scan IN, Sell, Wallet, Time Logs, Simulator

**Key Actions**:

1. **Fast Sell**
   - Scan barcode → sell clothing item
   - **Pass Condition**: Sale recorded

2. **Add Product**
   - Create new clothing product (size/color variants)
   - **Pass Condition**: Product created

3. **Scan IN Stock**
   - Scan clothing items into inventory
   - **Pass Condition**: Stock added

---

## Liquor Vertical

**Business Kind**: `liquor`

### Admin Journey

**Sidebar Links**:

#### MAIN Section

1. **Dashboard**
   - URL: `/verticals/liquor/dashboard/`
   - **Expected**: Liquor store KPIs (bottle sales, shot sales, credits outstanding)
   - **Pass Condition**: Dashboard loads with liquor metrics

2. **Analytics**
   - URL: `/app/analytics/`
   - **Expected**: Sales trends
   - **Pass Condition**: Charts render

3. **Liquor Hub**
   - URL: `/liquor/inventory/`
   - **Expected**: Hub with stock overview
   - **Pass Condition**: Hub page loads

4. **Stock**
   - URL: `/liquor/stock/`
   - **Expected**: Stock list (bottles/crates)
   - **Pass Condition**: Stock list loads

5. **Add Product**
   - URL: `/inventory/wizard/liquor/`
   - **Expected**: Liquor product creation (bottle/shot config)
   - **Pass Condition**: Wizard loads

6. **Scan In**
   - URL: `/liquor/scan-in/`
   - **Expected**: Scan liquor products into stock
   - **Pass Condition**: Scanner loads

7. **Sell**
   - URL: `/liquor/sell/`
   - **Expected**: Sell bottles/shots (barman attribution)
   - **Pass Condition**: Sell form loads

#### MONEY Section

8. **Credits**
   - URL: `/liquor/credits/`
   - **Expected**: Customer credit ledger (bar tabs)
   - **Pass Condition**: Credit list loads

#### MORE Section (same as Phones, excluding Layby)

9. Wallet (all users)
10. Time Logs (all users)
11. Reports (Manager only)
12. Simulator (all users)
13. Admin Wallet (Manager only)
14. Costs (Manager only)
15. Agents (Manager only)
16. Locations (Manager only)
17. Data Backup (Manager only)
18. Choose Plan (Manager only)

### Agent Journey

**Agent sees**: Dashboard, Analytics, Hub, Stock, Add Product, Scan In, Sell, Credits, Wallet, Time Logs, Simulator

**Key Actions**:

1. **Sell Bottle**
   - Navigate to Sell page
   - Select product (bottle)
   - Record barman (agent)
   - **Pass Condition**: Sale created, stock decremented

2. **Sell Shot**
   - Sell individual shots
   - Track shot count per bottle
   - **Pass Condition**: Shot sold, bottle stock updated

3. **Manage Credits**
   - View customer credits
   - Record credit sale
   - **Pass Condition**: Credit entry created

---

## Gym Vertical

**Business Kind**: `gym` (membership-based, **NO inventory/fast-sell**)

### Admin Journey

**Sidebar Links**:

#### MAIN Section

1. **Dashboard**
   - URL: `/verticals/gym/dashboard/`
   - **Expected**: Gym KPIs (active members, revenue, new sign-ups, arrears)
   - **Pass Condition**: Dashboard loads with membership metrics

2. **Analytics**
   - URL: `/app/analytics/`
   - **Expected**: Membership trends (no stock analytics)
   - **Pass Condition**: Charts render

3. **Members**
   - URL: `/gym/members/`
   - **Expected**: Member list (active/archived)
   - **Pass Condition**: Member list loads

4. **Member Check-ins**
   - URL: `/gym/checkin/`
   - **Expected**: Check-in interface for daily gym entry
   - **Pass Condition**: Check-in page loads, can record check-in

#### MORE Section (same as others, but "Agents" displays as "Trainers" in Gym)

5. Wallet (all users)
6. Time Logs (all users)
7. Reports (Manager only)
8. Simulator (all users)
9. Admin Wallet (Manager only)
10. Costs (Manager only)
11. **Trainers** (Manager only) - Label changes from "Agents" in gym context
    - URL: `/tenants/manager/agents/`
    - **Expected**: Trainer management
    - **Pass Condition**: Trainer list loads
12. Locations (Manager only)
13. Data Backup (Manager only)
14. Choose Plan (Manager only)

### Agent (Trainer) Journey

**Agent sees**: Dashboard, Analytics, Members, Member Check-ins, Wallet, Time Logs, Simulator

**Key Actions**:

1. **View Members**
   - Browse member list
   - **Pass Condition**: Member list loads

2. **Record Check-in**
   - Member arrives at gym
   - Scan membership card or select member
   - Record check-in
   - **Pass Condition**: Check-in logged

3. **Add New Member**
   - Navigate to Members → Add Member
   - Enter member details, payment plan
   - **Pass Condition**: Member created, active status

4. **Record Payment**
   - Navigate to member detail
   - Record 30-day payment
   - **Pass Condition**: Payment logged, next payment date updated

---

## Role Definitions

### Platform Roles

- **HQ Admin / Platform Owner**: `is_staff=True` or `is_superuser=True`
  - Access: Full HQ sidebar, all businesses
  - Django Admin access

### Business Roles

Determined by Django Groups with pattern: `biz:{BUSINESS_ID}:{ROLE}`

- **OWNER**: Business owner (implies manager privileges)
- **MANAGER**: Can manage business, see all reports, invite agents
- **AGENT**: Limited access, can sell/stock-in, no access to costs/reports/agents
- **AUDITOR**: Read-only access to reports
- **BAR_MANAGER**: Liquor-specific team lead role

**Role Hierarchy**:
- `is_owner` → implies `is_manager`
- `is_manager` → can see `require_manager=True` sidebar items
- `is_agent` → `require_manager=False` items only
- Managers are **NEVER** agents (even if AGENT group assigned)

---

## Test Coverage Matrix

### Smoke Tests Required

| Vertical | Admin Sidebar Links | Agent Sidebar Links | Stock-in Flow | Sell Flow | Critical Workflow |
|----------|---------------------|---------------------|---------------|-----------|-------------------|
| **HQ**   | 11 links            | N/A                 | N/A           | N/A       | Business creation |
| **Phones** | 18 links (7 main + 11 more) | 10 links | IMEI scan-in | Phone sale wizard | End-to-end sale |
| **Pharmacy** | 17 links (7 main + 10 more) | 10 links | Batch stock-in | Fast sell | Batch tracking |
| **Clothing** | 18 links (7 main + 11 more) | 10 links | Barcode scan-in | Fast sell | Size/color sale |
| **Liquor** | 18 links (8 main + 10 more) | 11 links | Crate scan-in | Bottle/shot sell | Credit management |
| **Gym** | 14 links (4 main + 10 more) | 7 links | **N/A** (membership-based) | **N/A** | Member check-in, payment |

### Critical "Never 500" Pages

These pages must **NEVER** return 500 errors:

1. All dashboard pages (every vertical)
2. All sidebar navigation links (all roles)
3. Fast Sell pages (pharmacy, clothing)
4. Scan IN pages (all verticals except gym)
5. Sell pages (all verticals except gym)
6. Member management (gym)
7. Wallet pages (all users)
8. Reports (managers)

### Django URL Resolution Tests

Test that **every** named URL in `get_vertical_sidebar_items()` can be reversed without `NoReverseMatch`:

- `verticals:gym_dashboard`
- `verticals:clothing_dashboard`
- `verticals:liquor_dashboard`
- `verticals:pharmacy_dashboard`
- `inventory_verticals:phones_dashboard`
- `app_router:analytics`
- `wallet:agent_wallet`
- `wallet:admin_home`
- `reports:home`
- `simulator:business_home`
- `tenants:manager_review_agents`
- `tenants:manager_locations`
- `backups:manager_list`
- `billing:plans`
- `inventory:orders_list`
- etc. (full list in `inventory/utils_verticals.py`)

---

## Test Implementation Strategy

### 1. Django Test Client Smoke Tests

**Purpose**: Fast route validation, catches URL resolution errors

**Coverage**:
- Login as admin → reverse() every sidebar URL → assert HTTP 200 or 302
- Login as agent → reverse() every non-manager URL → assert HTTP 200 or 302
- Test for each vertical (5 verticals × 2 roles = 10 test classes)

**Files**:
- `tests/smoke/test_sidebar_routes_admin.py`
- `tests/smoke/test_sidebar_routes_agent.py`

### 2. Playwright Click Smoke Tests

**Purpose**: True UI click regression protection, catches template errors

**Coverage**:
- Login as admin → navigate to dashboard → locate sidebar → click every link → assert no "Server Error (500)"
- Login as agent → same flow
- Screenshot on failure

**Files**:
- `tests/e2e/test_sidebar_clicks_admin.py`
- `tests/e2e/test_sidebar_clicks_agent.py`
- `tests/e2e/helpers/sidebar.py` (utilities)

### 3. Core Workflow Smoke Tests

**Purpose**: Validate critical business logic

**Coverage**:
- **Stock-in**: Add one item per vertical → assert stock increased
- **Sell**: Sell one item per vertical → assert sale created, stock decreased, revenue increased
- **Dashboard KPI**: After sale, reload dashboard → assert KPI updated

**Files**:
- `tests/smoke/test_core_workflows.py`

### 4. HQ Smoke Tests

**Purpose**: Platform admin regression protection

**Coverage**:
- Login as staff → click all HQ sidebar links → assert no 500

**Files**:
- `tests/smoke/test_hq_sidebar.py` (may already exist as `test_hq_smoke.py`)

---

## Pass/Fail Criteria

### ✅ PASS Conditions

1. **All sidebar links load** (HTTP 200 or 302 redirect)
2. **No "Server Error (500)" text** in response
3. **No NoReverseMatch exceptions**
4. **No template syntax errors**
5. **Stock-in increases stock count**
6. **Sell creates sale record and decreases stock**
7. **Dashboard KPIs update after sale**
8. **Role-based access control works** (agents can't see manager-only pages)

### ❌ FAIL Conditions

1. **Any 500 error** on sidebar navigation
2. **NoReverseMatch** when reversing named URLs
3. **Template does not exist** errors
4. **Broken includes** (missing partials)
5. **Stock-in does not increase stock**
6. **Sell does not create sale**
7. **Manager-only pages accessible to agents**

---

## Maintenance Notes

**Update Triggers**:

This document must be updated when:

1. New vertical added (update sidebar items)
2. New sidebar link added (update test coverage)
3. URL pattern changes (update named URLs)
4. Role logic changes (update access control tests)
5. Critical workflow changes (update workflow tests)

**Ownership**: Engineering Team  
**Review Frequency**: Every sprint / before major releases

---

**END OF DOCUMENT**


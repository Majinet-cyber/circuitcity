# TengaSale Cypress E2E Tests

## Overview

TengaSale uses [Cypress](https://cypress.io) for end-to-end browser testing of critical user flows.

The tests cover:
- Public site (visitor, no login)
- Customer payment portal (`/pay/`)
- Underwriter review flow (`/sales/`)
- HQ command center (`/hq/`)
- Security and role isolation

---

## Prerequisites

- **Node.js** ≥ 18
- **TengaSale Django server running** on `http://localhost:8000`
- Test users seeded in the database (see below)

### Seed test users

```bash
cd tengasale
python manage.py seed_tengasale_users
# or use the Django admin to create:
# underwriter1 / testpass123 (role: underwriter)
# merchant1    / testpass123 (role: merchant)
# hqadmin      / testpass123 (role: hq)
```

### Seed review questions (structured questionnaires)

```bash
python manage.py seed_review_questions
```

### Seed demo contract

```bash
python manage.py seed_portal_demo
```

---

## Setup

Install Cypress and dependencies:

```bash
# From the TengaSale project root (where package.json lives)
npm install
```

---

## Running Tests

### Open Cypress UI (interactive mode)

```bash
npx cypress open
```

This opens the Cypress Test Runner in your browser where you can run tests interactively.

### Run all tests headlessly

```bash
npx cypress run
```

### Run in Chrome specifically

```bash
npx cypress run --browser chrome
```

### Run a specific spec file

```bash
npx cypress run --spec "cypress/e2e/03_underwriter_flow.cy.js"
```

---

## Test Files

| File | Description |
|------|-------------|
| `cypress/e2e/01_public_site.cy.js` | Public website, landing page, legal pages |
| `cypress/e2e/02_customer_payment_portal.cy.js` | `/pay/` — search, contract view, mock payment |
| `cypress/e2e/03_underwriter_flow.cy.js` | `/sales/` — underwriter review, field marking, wallet |
| `cypress/e2e/04_hq_dashboard.cy.js` | `/hq/` — dashboard KPIs |
| `cypress/e2e/04_hq_flow.cy.js` | `/hq/` — commissions, reports, simulations, safe operations |
| `cypress/e2e/05_security.cy.js` | Role isolation, data masking, access control |
| `cypress/e2e/06_merchant_flow.cy.js` | Merchant dashboard, application submission, role isolation |
| `cypress/e2e/07_commission_flow.cy.js` | Commission wallet, WHT display, security isolation |

---

## Configuration

Edit `cypress.config.js` to update:
- `baseUrl` (default: `http://localhost:8000`)
- Test user credentials (`env` section)
- Demo contract numbers

---

## `data-testid` Attributes Used

The following `data-testid` attributes are used in the Cypress tests and must be present in templates:

| `data-testid` | Location |
|---------------|----------|
| `claim-next` | `sales/home.html` — Claim Next button |
| `field-mark-button` | Review summary pages — Mark field button |
| `approve-application` | Confirm approve page |
| `payment-search` | `/pay/` — search input |
| `make-payment` | Contract payment page |
| `hq-dashboard` | `/hq/` dashboard container |
| `underwriter-wallet` | `/sales/wallet/` container |
| `commission-row` | Wallet earnings rows |
| `arrears-deduction-row` | Wallet deductions rows |
| `merchant-payout-row` | HQ merchant payout rows |
| `daily-sales-chart` | HQ dashboard chart |
| `daily-payments-chart` | HQ dashboard chart |

---

## Known Limitations

- Tests require a running Django dev server (`python manage.py runserver`)
- Tests require seeded demo data
- Some tests may fail if the database is empty (no contracts, no applications)
- Cypress cannot test file uploads in all browsers without workarounds
- Video recording is disabled by default (set `video: true` in `cypress.config.js` to enable)

---

## CI Integration

To run in CI (GitHub Actions, GitLab CI, etc.):

```yaml
# Example GitHub Actions step
- name: Run Cypress E2E
  run: |
    cd tengasale && python manage.py runserver &
    sleep 5
    cd ..
    npx cypress run --headless
```

---

## Troubleshooting

- **Login fails:** Check that test users are seeded with correct credentials
- **Base URL wrong:** Update `baseUrl` in `cypress.config.js`
- **Tests timeout:** Increase `defaultCommandTimeout` in `cypress.config.js`
- **CSRF errors:** Cypress handles CSRF tokens automatically via form submissions

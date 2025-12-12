# CI/CD Setup Summary

## Overview

This project now has two GitHub Actions workflows for continuous integration:

1. **Django Tests** - Unit tests with PostgreSQL
2. **Cypress E2E** - End-to-end browser tests against a live Django server

Both workflows run automatically on:
- Push to `main` and `mobile-layout-v1` branches
- Pull requests targeting `main` and `mobile-layout-v1` branches

---

## Workflow Files

### 1. `.github/workflows/django-tests.yml`

**Purpose:** Runs Django unit tests with a PostgreSQL database

**What it does:**
- Sets up Python 3.12
- Installs dependencies from `requirements.txt`
- Spins up PostgreSQL 16 service
- Runs database migrations
- Executes `python manage.py test`

**Environment Variables:**
- `POSTGRES_DB=circuitcity`
- `POSTGRES_USER=ccuser`
- `POSTGRES_PASSWORD=testpassword`
- `POSTGRES_HOST=localhost`
- `POSTGRES_PORT=5432`

**No secrets required** - uses test credentials only

---

### 2. `.github/workflows/cypress-e2e.yml`

**Purpose:** Runs Cypress end-to-end tests against a real Django development server

**What it does:**
- Sets up Python 3.12 and Node.js 20
- Installs Python dependencies
- Spins up PostgreSQL 16 service
- Runs database migrations
- Starts Django dev server on `http://127.0.0.1:8000`
- Installs Cypress and Node dependencies
- Runs Cypress tests including:
  - `cypress/e2e/sidebar_smoke.cy.js`
  - `cypress/e2e/phones_scan_in_flow.cy.js`
  - `cypress/e2e/phones_agent_invite_flow.cy.js`
  - (and any other tests in the `cypress/e2e/` directory)

**Artifacts:**
- Uploads Cypress screenshots on test failure
- Uploads Cypress videos (always) for debugging

**Environment Variables (same as django-tests.yml):**
- `POSTGRES_DB=circuitcity`
- `POSTGRES_USER=ccuser`
- `POSTGRES_PASSWORD=testpassword`
- `POSTGRES_HOST=localhost`
- `POSTGRES_PORT=5432`

**Required GitHub Secrets:**

⚠️ **You MUST configure these secrets in your GitHub repository:**

1. `CYPRESS_TEST_EMAIL` - Email address for test user authentication
2. `CYPRESS_TEST_PASSWORD` - Password for test user authentication

These are used by the `cy.loginAsOwner()` custom command in your Cypress tests.

---

## Setting Up GitHub Secrets

To configure the required secrets:

1. Go to your GitHub repository
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add each secret:
   - Name: `CYPRESS_TEST_EMAIL`
     Value: `<your-test-email>`
   - Name: `CYPRESS_TEST_PASSWORD`
     Value: `<your-test-password>`

**Important:** These credentials should correspond to a valid user in your Django application that has the necessary permissions to perform the actions tested in your Cypress specs.

---

## How Cypress Environment Variables Work

When you set GitHub Actions environment variables with the `CYPRESS_` prefix:

```yaml
env:
  CYPRESS_TEST_EMAIL: ${{ secrets.CYPRESS_TEST_EMAIL }}
  CYPRESS_TEST_PASSWORD: ${{ secrets.CYPRESS_TEST_PASSWORD }}
```

Cypress automatically maps them to `Cypress.env()`:

- `CYPRESS_TEST_EMAIL` → `Cypress.env('TEST_EMAIL')`
- `CYPRESS_TEST_PASSWORD` → `Cypress.env('TEST_PASSWORD')`

Your existing `cy.loginAsOwner()` command already uses `Cypress.env('TEST_EMAIL')` and `Cypress.env('TEST_PASSWORD')`, so no changes are needed to your test code.

---

## Viewing Workflow Results

### In GitHub UI:

1. Go to your repository on GitHub
2. Click the **Actions** tab
3. You'll see:
   - Recent workflow runs
   - Status (✅ passed, ❌ failed, 🟡 in progress)
   - Click any run to see detailed logs

### For Failed E2E Tests:

1. Navigate to the failed workflow run
2. Scroll to **Artifacts** section at the bottom
3. Download:
   - `cypress-screenshots` (if test failed)
   - `cypress-videos` (always captured)
4. Review videos/screenshots to debug failures

---

## Local Testing vs CI

### Database Configuration:

Your `cc/settings.py` supports multiple database configurations:

1. **TESTING mode** (when running `python manage.py test`): Uses SQLite
2. **DATABASE_URL set**: Uses dj-database-url to parse connection string
3. **USE_LOCAL_SQLITE=True**: Uses local SQLite
4. **Default**: Uses PostgreSQL with these env vars:
   - `POSTGRES_DB` or `DB_NAME` (default: `circuitcity`)
   - `POSTGRES_USER` or `DB_USER` (default: `ccuser`)
   - `POSTGRES_PASSWORD` or `DB_PASSWORD`
   - `POSTGRES_HOST` or `DB_HOST` (default: `127.0.0.1`)
   - `POSTGRES_PORT` or `DB_PORT` (default: `5432`)

**CI uses the POSTGRES_* environment variables** to ensure consistency with the PostgreSQL service container.

---

## Troubleshooting

### Django Tests Failing

1. Check the test output in the GitHub Actions log
2. Verify migrations are up to date
3. Ensure all test dependencies are in `requirements.txt`

### Cypress Tests Failing

1. **Server didn't start:**
   - Check the "Start Django development server" step logs
   - Ensure migrations succeeded
   - Look for port conflicts or startup errors

2. **Authentication errors:**
   - Verify `CYPRESS_TEST_EMAIL` and `CYPRESS_TEST_PASSWORD` secrets are set correctly
   - Ensure the test user exists and has proper permissions

3. **Element not found:**
   - Download the Cypress videos/screenshots from artifacts
   - Check if UI changes broke selectors
   - Verify the application loads correctly in CI environment

### Debugging Tips:

- Add `DEBUG: 1` to the workflow env block temporarily to see more Django output
- Check PostgreSQL connection by adding a test query step
- Use `npx cypress run --record` if you have Cypress Dashboard set up

---

## Files Modified/Created

### Created:
- `.github/workflows/django-tests.yml` - Django unit tests workflow
- `.github/workflows/cypress-e2e.yml` - Cypress E2E tests workflow
- `CI_SETUP_SUMMARY.md` - This documentation file

### Not Modified:
- No changes to Django application code, models, or views
- No changes to Cypress test files
- No changes to `cc/settings.py` (existing env var support is sufficient)

---

## Next Steps

1. ✅ Set up the required GitHub secrets (`CYPRESS_TEST_EMAIL`, `CYPRESS_TEST_PASSWORD`)
2. ✅ Push these changes to `main` or create a PR
3. ✅ Watch the Actions tab to see your first CI run
4. ✅ Fix any test failures that appear in CI but not locally

---

## Questions?

If you encounter issues:

1. Check the GitHub Actions logs for detailed error messages
2. Compare local vs CI environment variables
3. Ensure test data setup is consistent between local and CI
4. Review downloaded Cypress artifacts (videos/screenshots)

Happy testing! 🚀


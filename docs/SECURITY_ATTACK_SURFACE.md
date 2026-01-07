# Security Attack Surface Map

**Generated:** 2026-01-02  
**Application:** CircuitCity (Emajinet) - Multi-tenant POS & Inventory System  
**Framework:** Django 4.2+

---

## Executive Summary

This document maps all externally reachable endpoints, authentication flows, tenant-scoped resources, file operations, and third-party integrations that constitute the application's attack surface.

### Risk Profile
- **Tenant Isolation Critical:** Multi-tenant SaaS with shared database
- **Payment Processing:** Handles subscription payments via Stripe, Pesapal, PayChangu
- **File Uploads:** Avatar images, data exports, backup archives
- **Sensitive Data:** Business financials, inventory, customer records, PII
- **External Integrations:** SendGrid (email), Twilio (SMS), WhatsApp, Payment webhooks

---

## 1. Environments

### 1.1 Local Development
- **Domain:** `localhost:8000`, `127.0.0.1:8000`
- **Database:** SQLite (`db.sqlite3`)
- **Debug Mode:** `DEBUG=True`
- **SSL:** Disabled
- **Email:** Console backend

### 1.2 Staging
- **Domain:** `emajinet-staging.onrender.com`
- **Database:** PostgreSQL (Render managed)
- **Debug Mode:** `DEBUG=False`
- **SSL:** Enabled (via Render proxy)
- **Email:** SendGrid

### 1.3 Production
- **Domains:** `emajinet.africa`, `www.emajinet.africa`
- **Database:** PostgreSQL (Render managed)
- **Debug Mode:** `DEBUG=False`
- **SSL:** Enforced (HSTS enabled)
- **Email:** SendGrid

---

## 2. Authentication & Authorization Endpoints

### 2.1 Login / Signup
- `POST /accounts/login/` - Username/password authentication
- `POST /accounts/signup/` - Multi-step manager registration wizard
- `POST /accounts/signup/verify-email/` - Email OTP verification
- `POST /accounts/signup/manager/` - Legacy single-page signup
- `GET|POST /accounts/logout/` - Session termination

**Risk:** Brute-force attacks, credential stuffing, account enumeration

**Current Protections:**
- Password complexity requirements (StrongPasswordValidator)
- Email OTP verification for new signups
- Session-based authentication

**Gaps:**
- ⚠️ No rate limiting on login endpoint
- ⚠️ No account lockout after failed attempts
- ⚠️ Timing attacks possible (different responses for valid/invalid users)

---

### 2.2 Two-Factor Authentication (2FA)
- `POST /accounts/2fa/challenge/` - SMS OTP challenge after password login
- `POST /accounts/2fa/sms/enable/start/` - Request SMS 2FA enrollment
- `POST /accounts/2fa/sms/enable/verify/` - Verify OTP to enable 2FA
- `POST /accounts/2fa/sms/disable/start/` - Request 2FA removal
- `POST /accounts/2fa/sms/disable/verify/` - Verify OTP to disable 2FA

**Risk:** SMS OTP brute-force, SIM swapping, toll fraud

**Current Protections:**
- Twilio Verify API for OTP delivery
- OTP expiration (10 minutes)

**Gaps:**
- ⚠️ No rate limiting on OTP request endpoints (toll fraud risk)
- ⚠️ No rate limiting on OTP verify endpoints (brute-force)
- ⚠️ No audit log for 2FA enable/disable events

---

### 2.3 Password Reset
- `POST /accounts/password/forgot/` - Request password reset (email OTP)
- `POST /accounts/password/reset/` - Verify OTP + set new password

**Risk:** Account takeover via email OTP compromise

**Current Protections:**
- Email OTP (10 minute TTL)
- Requires knowledge of username or email

**Gaps:**
- ⚠️ No rate limiting on reset request (email spam)
- ⚠️ No rate limiting on verify endpoint (OTP brute-force)
- ⚠️ No notification to user when password is changed

---

### 2.4 OTP API Endpoints (Email)
- `POST /accounts/auth/otp/request/` - Request email OTP
- `POST /accounts/auth/otp/verify/` - Verify email OTP

**Risk:** Email flooding, OTP brute-force

**Current Protections:**
- OTP expiration

**Gaps:**
- ⚠️ No rate limiting (per-IP or per-email)
- ⚠️ No CAPTCHA or other abuse prevention

---

### 2.5 Session Management
- `POST /accounts/settings/sessions/terminate-others/` - Terminate all other sessions
- `GET /accounts/settings/sessions/` - View active sessions

**Current Protections:**
- Session expiry (4 hours)
- HttpOnly, Secure, SameSite=Lax cookies
- Session rotation on login

**Gaps:**
- ⚠️ No session binding (IP/User-Agent validation)
- ⚠️ Session IDs not rotated on privilege escalation

---

## 3. Tenant-Scoped Resources (IDOR Risks)

All resources below MUST enforce tenant isolation. Any failure allows cross-tenant data access.

### 3.1 Core Business Data
- **Business:** `/tenants/businesses/<id>/` (Business profile)
- **Locations:** `/inventory/locations/<id>/` (Store locations)
- **Memberships:** `/tenants/memberships/<id>/` (Team members)

### 3.2 Inventory Management
- **Phone Inventory:** `/inventory/phones/<id>/`
- **Products:** `/inventory/products/<id>/`
- **Vertical Products:**
  - Liquor: `/liquor/products/<id>/`
  - Gym: `/gym/members/<id>/`
  - Pharmacy: `/pharmacy/batches/<id>/`
  - Clothing: `/inventory/clothing/items/<id>/`

### 3.3 Sales & Transactions
- **Sales:** `/sales/<id>/`
- **Wallet Transactions:** `/wallet/transactions/<id>/`
- **Layby Orders:** `/layby/orders/<id>/`

### 3.4 Reporting & Analytics
- **Exports:** `/exports/inventory.csv`, `/wallet/export/activity/`
- **Backups:** `/backups/manager/<snapshot_id>/download/`

**Critical Risk:** IDOR (Insecure Direct Object References)

**Current Protections:**
- Tenant resolution middleware (`TenantResolutionMiddleware`)
- Role resolution middleware (`RoleResolutionMiddleware`)
- `@require_business` decorator on views

**Gaps to Test:**
- ⚠️ Are all queries filtered by `business=` or `location=`?
- ⚠️ Can an agent from Business A access Business B's data by guessing IDs?
- ⚠️ Are exported files scoped to tenant (no cross-tenant leakage)?
- ⚠️ Are backup downloads properly gated?

---

## 4. File Upload Endpoints

### 4.1 Avatar Uploads
- `POST /accounts/avatar/me/` - Upload own avatar
- `POST /accounts/avatar/<agent_id>/` - Upload avatar for agent (admin only)

**Accepted Types:** Images (JPEG, PNG, WEBP)  
**Max Size:** Enforced by `validate_file_size` (check actual limit)  
**Storage:** `MEDIA_ROOT/avatars/`

**Risk:** Malicious file upload, path traversal, XSS (if served unsafely)

**Current Protections:**
- `AvatarForm` with `validate_mime()` and `process_avatar()`
- Re-encodes images to safe format/size
- Admin-only for other users

**Gaps:**
- ⚠️ Are filenames sanitized (no path traversal)?
- ⚠️ Are avatars served with correct `Content-Type` headers?
- ⚠️ Are avatars served from authenticated endpoint or public static?

---

### 4.2 Data Exports / Backups
- `POST /backups/manager/generate/` - Generate full business backup (ZIP)
- `GET /backups/manager/<snapshot_id>/download/` - Download backup ZIP
- `GET /backups/manager/<snapshot_id>/pdf/` - Download backup report PDF
- `GET /wallet/export/activity/` - Agent activity CSV export

**File Types:** ZIP (backups), CSV (exports), PDF (reports)  
**Storage:** `MEDIA_ROOT/backups/YYYY/MM/`

**Risk:** Information disclosure, tenant leakage, SSRF (if PDFs fetch external resources)

**Current Protections:**
- Manager-only access (`@manager_required`)
- Per-tenant exports (filtered by `business=`)

**Gaps:**
- ⚠️ Are download URLs authenticated (not guessable)?
- ⚠️ Are download URLs time-limited (signed URLs)?
- ⚠️ Do exported files contain tenant ID watermark?
- ⚠️ Are PDFs generated safely (no SSRF, no secret leakage)?

---

## 5. Payment & Webhook Endpoints

### 5.1 Stripe
- `POST /billing/stripe/checkout/` - Initiate Stripe checkout
- `GET /billing/stripe/success/` - Return after successful payment
- `POST /billing/stripe/webhook/` - Stripe webhook (signature verified)

**Webhook Events:**
- `checkout.session.completed` - Activate subscription
- `invoice.payment_succeeded` - Renew subscription

**Security:**
- ✅ Signature verification (`STRIPE_WEBHOOK_SECRET`)
- ✅ CSRF exempt (required for external webhooks)
- ✅ Idempotency via `external_id` logging

**Gaps:**
- ⚠️ Replay attack prevention (check event timestamp?)
- ⚠️ Webhook rate limiting (DDoS risk)

---

### 5.2 Pesapal
- `POST /billing/pesapal/checkout/` - Initiate Pesapal payment
- `GET /billing/pesapal/callback/` - User return after payment
- `POST /billing/pesapal/ipn/` - Pesapal IPN (Instant Payment Notification)

**Security:**
- ✅ OAuth 2.0 token-based auth with Pesapal API
- ⚠️ IPN signature verification status unknown

**Gaps:**
- ⚠️ Is IPN signature verified?
- ⚠️ Replay attack prevention?
- ⚠️ Rate limiting on IPN endpoint?

---

### 5.3 PayChangu (Mobile Money - Malawi)
- `POST /billing/paychangu/initiate/` - Initiate mobile money payment
- `POST /billing/paychangu/webhook/` - PayChangu webhook (signature verified)
- `GET /billing/paychangu/return/` - User return after payment
- `GET /billing/paychangu/callback/` - Alternative callback endpoint

**Security:**
- ✅ Signature verification (`PAYCHANGU_WEBHOOK_SECRET`)
- ✅ CSRF exempt (required for external webhooks)
- ✅ Webhook event logging

**Gaps:**
- ⚠️ Replay attack prevention
- ⚠️ Webhook rate limiting

---

### 5.4 Layby Payment Webhook (Internal?)
- `POST /layby/api/payment/webhook/` - Layby payment webhook

**Security:**
- ✅ Webhook secret verification
- ⚠️ Source unclear (internal or external?)

---

## 6. API Endpoints (Internal)

### 6.1 Barcode / Product APIs
- `POST /inventory/api/barcode/lookup/` - Lookup product by barcode
- `POST /inventory/api/barcode/quick-create/` - Create product on-the-fly
- `POST /inventory/api/product/create/` - Create new product
- `POST /inventory/api/product/update-price/` - Update product price

**Auth Required:** Yes (`@require_business`)  
**Risk:** Price manipulation, unauthorized product creation

**Gaps:**
- ⚠️ Rate limiting (abuse prevention)
- ⚠️ Input validation (barcode format, price ranges)
- ⚠️ Audit logging for price changes

---

### 6.2 Stock & Analytics APIs
- `GET /inventory/api/stock-status/` - Get stock status
- `GET /inventory/api/restock-heatmap/` - Restock recommendations
- `POST /api/global-search/` - Global search across SKUs, agents, invoices

**Auth Required:** Yes  
**Risk:** Information disclosure, data mining

**Gaps:**
- ⚠️ Rate limiting
- ⚠️ Pagination limits (prevent large exports via API)
- ⚠️ Response filtering (no internal IDs/schemas leaked)

---

### 6.3 Admin / HQ APIs
- `/admin/` - Django admin panel
- `/hq/` - HQ admin dashboard
- `/hq/subscriptions/` - Manage business subscriptions
- `/hq/businesses/<id>/` - View business details

**Auth Required:** Superuser / HQ staff only  
**Risk:** Full application compromise if breached

**Gaps:**
- ⚠️ Is Django admin accessible in production? (Should be hidden or IP-restricted)
- ⚠️ Are HQ endpoints properly gated (`@hq_admin_required`)?
- ⚠️ MFA enforcement for HQ admins?

---

## 7. Public / Unauthenticated Endpoints

### 7.1 Marketing Pages
- `GET /` - Smart redirect (marketing page or dashboard)
- `GET /landing/` - Public marketing/home page
- `GET /home/` - Global home alias

### 7.2 Static Assets
- `/static/` - CSS, JS, images
- `/media/` - Uploaded files (avatars, exports)

**Risk:** Information disclosure via directory listing

**Current Protections:**
- WhiteNoise for static files
- `WHITENOISE_INDEX_FILE = False` (no directory listing)

**Gaps:**
- ⚠️ Are media files served via authenticated view or direct static access?
- ⚠️ Are media uploads stored outside web root?

---

### 7.3 SEO / Bots
- `GET /robots.txt` - Robots.txt
- `GET /sitemap.xml` - XML sitemap
- `GET /favicon.ico` - Favicon

**Risk:** Low (intentionally public)

---

## 8. Debug / Dev-Only Endpoints

**⚠️ CRITICAL:** These MUST be disabled in production

- `GET /__whoami__` - Diagnostic info (DEBUG only)
- `GET /__render_login__` - Test login template (DEBUG only)
- `GET /__render_reports__` - Test reports template (DEBUG only)
- `GET /__grep_soon__` - Grep codebase for TODOs (DEBUG only)
- `GET /accounts/login/_which/` - Template probe (DEBUG only)
- `GET /accounts/__e2e__/latest-otp/` - E2E test OTP bypass (DEBUG/E2E only)
- `GET /accounts/__e2e__/verify-otp-bypass/` - E2E OTP bypass (DEBUG/E2E only)
- `GET /accounts/__e2e__/seed-business/` - E2E test data seed (DEBUG/E2E only)

**Status:** ✅ Gated by `if settings.DEBUG:` or `if settings.DEBUG or getattr(settings, "E2E_TESTING", False):`

**Verification Needed:**
- ⚠️ Confirm `E2E_TESTING` is NEVER set in production

---

## 9. Third-Party Integrations

### 9.1 SendGrid (Email)
- **Used For:** Transactional emails (OTP, password reset, invoices, backup reports)
- **API Key:** `SENDGRID_API_KEY` (environment variable)
- **Risk:** Phishing, email spoofing if key compromised

**Security:**
- ✅ Domain verification (emajinet.africa)
- ⚠️ Key rotation policy?

---

### 9.2 Twilio (SMS OTP)
- **Used For:** SMS-based Two-Factor Authentication
- **Credentials:** `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_VERIFY_SERVICE_SID`
- **Risk:** Toll fraud, SMS phishing

**Security:**
- ✅ Twilio Verify API (managed OTP service)
- ⚠️ Rate limiting on OTP requests?

---

### 9.3 WhatsApp (Notifications)
- **Used For:** Manager/agent notifications (sales, alerts)
- **Credentials:** `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`
- **API:** Facebook Graph API v21.0
- **Risk:** Notification spam, phishing

**Security:**
- ⚠️ Webhook verification (if receiving WhatsApp messages)?
- ⚠️ Rate limiting on outbound messages?

---

### 9.4 Payment Gateways
See Section 5 (Payment & Webhook Endpoints)

---

## 10. Sensitive Data Flows

### 10.1 Secrets in Environment
**Stored in `.env` (local) or Render environment variables (production):**
- `DJANGO_SECRET_KEY`
- `DATABASE_URL`
- `SENDGRID_API_KEY`
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_VERIFY_SERVICE_SID`
- `WHATSAPP_ACCESS_TOKEN`
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`
- `PESAPAL_CONSUMER_KEY`, `PESAPAL_CONSUMER_SECRET`
- `PAYCHANGU_SECRET_KEY`, `PAYCHANGU_WEBHOOK_SECRET`

**Gaps:**
- ⚠️ Are these secrets rotated periodically?
- ⚠️ Are they excluded from logs (check logging config)?
- ⚠️ Is `.env` in `.gitignore`? (Verify)

---

### 10.2 PII / Financial Data
**User PII:**
- User emails, phone numbers, names
- Business names, addresses
- Agent work logs (GPS coordinates)

**Financial Data:**
- Wallet transaction amounts
- Sales records (prices, commissions)
- Subscription payments (amounts, dates)

**Sensitive Business Data:**
- Inventory counts, costs, profit margins
- Agent commission rates
- Customer membership details (gym)

**Gaps:**
- ⚠️ Are these redacted in logs?
- ⚠️ Are backups encrypted at rest?
- ⚠️ Data retention policy defined?

---

## 11. Known Security Measures (Current)

### ✅ Implemented
1. **HTTPS Enforcement:** HSTS enabled in production
2. **Secure Cookies:** HttpOnly, Secure, SameSite=Lax
3. **CSRF Protection:** Django CSRF middleware enabled
4. **Password Hashing:** PBKDF2 (Django default)
5. **Password Policy:** Strong password validator (12+ chars, mixed case, digit, symbol)
6. **Content Security:** `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`
7. **Referrer Policy:** `same-origin`
8. **Session Expiry:** 4 hours absolute timeout
9. **Database SSL:** Enforced in production (Postgres `sslmode=require`)
10. **Webhook Signatures:** Verified for Stripe, PayChangu
11. **Tenant Middleware:** Scopes requests to active business
12. **Role Middleware:** Resolves user role before views execute
13. **Subscription Gate:** Blocks expired accounts

---

## 12. Critical Security Gaps (Prioritized)

### 🔴 High Severity
1. **No Rate Limiting:** Login, OTP, password reset, webhooks, APIs
2. **IDOR Testing Needed:** Verify tenant isolation on ALL resources
3. **Admin Panel Exposure:** Django admin accessible at `/admin/` (should hide or IP-restrict)
4. **Debug Endpoints:** Verify `E2E_TESTING` never set in production
5. **Secrets Rotation:** No documented rotation policy
6. **Payment Webhook Replay:** No timestamp validation
7. **File Download URLs:** Not signed/time-limited

### 🟡 Medium Severity
8. **Session Binding:** No IP/User-Agent validation
9. **Audit Logging:** Incomplete (no 2FA changes, no price edit logs)
10. **Email Enumeration:** Different responses for valid/invalid users
11. **Error Responses:** May leak stack traces (verify handlers)
12. **Static Analysis:** No automated security scanning in CI
13. **Dependency Audits:** No pip-audit in CI
14. **PII Redaction:** No confirmed log sanitization

### 🟢 Low Severity
15. **WhatsApp Rate Limiting:** Prevent notification spam
16. **Backup Encryption:** Backups stored unencrypted
17. **PDF Generation:** Potential SSRF if loading external resources

---

## 13. Attack Scenarios to Test

### Scenario 1: Cross-Tenant Data Access (IDOR)
**Attack:** Agent from Business A guesses ID of product in Business B  
**Test:** `GET /inventory/products/999/` (where 999 belongs to another tenant)  
**Expected:** 404 Not Found (not 403 Forbidden, to prevent enumeration)

### Scenario 2: Brute-Force Login
**Attack:** Automated login attempts with common passwords  
**Test:** 100 POST requests to `/accounts/login/` in 10 seconds  
**Expected:** Rate limit triggered, account locked or CAPTCHA required  
**Current:** ❌ No rate limiting

### Scenario 3: OTP Brute-Force
**Attack:** Try all 6-digit OTP codes (000000-999999)  
**Test:** 1,000,000 POST requests to `/accounts/auth/otp/verify/`  
**Expected:** Rate limit, OTP invalidation after N failures  
**Current:** ❌ No rate limiting

### Scenario 4: Webhook Replay Attack
**Attack:** Capture legitimate webhook, replay it 100 times  
**Test:** POST same Stripe webhook event repeatedly  
**Expected:** Idempotency check rejects duplicates  
**Current:** ⚠️ Unclear (event ID logged, but timestamp not checked)

### Scenario 5: Malicious File Upload
**Attack:** Upload PHP web shell disguised as image  
**Test:** POST `/accounts/avatar/me/` with `.php` file  
**Expected:** File rejected, or re-encoded to safe image format  
**Current:** ✅ `process_avatar()` re-encodes (good!)

### Scenario 6: Price Manipulation
**Attack:** Manager sets negative price or astronomically high price  
**Test:** POST `/inventory/api/product/update-price/` with `price=-1000`  
**Expected:** Validation error  
**Current:** ⚠️ Unclear (check `MIN_PHONE_SELLING_PRICE_MK` enforcement)

### Scenario 7: Privilege Escalation
**Attack:** Agent modifies request to access manager-only endpoint  
**Test:** Agent user calls `POST /backups/manager/generate/`  
**Expected:** 403 Forbidden  
**Current:** ✅ `@manager_required` decorator (verify applied everywhere)

### Scenario 8: Admin Panel Brute-Force
**Attack:** Brute-force Django admin login  
**Test:** Automated POST requests to `/admin/login/`  
**Expected:** Rate limit, IP block, or admin disabled in production  
**Current:** ⚠️ Admin panel may be public

---

## 14. Compliance & Best Practices

### OWASP Top 10 (2021) Status

| Risk | Status | Notes |
|------|--------|-------|
| **A01: Broken Access Control** | ⚠️ **Needs Testing** | Tenant isolation critical; IDOR tests required |
| **A02: Cryptographic Failures** | ✅ **Good** | HTTPS enforced, passwords hashed, DB SSL |
| **A03: Injection** | ⚠️ **Needs Review** | Django ORM prevents SQL injection; verify no raw queries |
| **A04: Insecure Design** | ⚠️ **In Progress** | This security review addresses design gaps |
| **A05: Security Misconfiguration** | ⚠️ **Partial** | Admin panel may be exposed, no rate limiting |
| **A06: Vulnerable Components** | ❌ **Needs Fix** | No dependency scanning in CI |
| **A07: Auth Failures** | ⚠️ **Partial** | No rate limiting, weak session binding |
| **A08: Data Integrity Failures** | ⚠️ **Partial** | Webhook signatures good; replay prevention needed |
| **A09: Logging Failures** | ⚠️ **Needs Review** | Audit logging incomplete; PII redaction unclear |
| **A10: SSRF** | ⚠️ **Needs Review** | PDF generation, WhatsApp API calls |

---

## 15. Next Steps (Phase 1+)

This attack surface map informs the security hardening phases:

1. **Phase 1:** Hide framework fingerprints, harden headers, custom error pages
2. **Phase 2:** Comprehensive IDOR testing, enforce tenant isolation everywhere
3. **Phase 3:** Rate limiting, pagination limits, API response cleanup
4. **Phase 4:** Input validation, output encoding, SSRF protection
5. **Phase 5:** Rate limiting implementation (login, OTP, webhooks)
6. **Phase 6:** Secure file uploads/downloads, signed URLs
7. **Phase 7:** Secrets rotation, PII redaction, payment audit
8. **Phase 8:** Automated scanning (pip-audit, bandit, ZAP)
9. **Phase 9:** Documentation, verification, handoff

---

**Document Version:** 1.0  
**Last Updated:** 2026-01-02  
**Author:** Security Review Team  
**Classification:** Internal Use Only


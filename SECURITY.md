# Security Policy & Procedures

**Application:** CircuitCity (Emajinet)  
**Last Updated:** 2026-01-02  
**Classification:** Internal Use Only

---

## Table of Contents

1. [Overview](#overview)
2. [Environments](#environments)
3. [Security Checks](#security-checks)
4. [Responsible Disclosure](#responsible-disclosure)
5. [Incident Response](#incident-response)
6. [Security Contacts](#security-contacts)

---

## Overview

This document outlines security procedures, checks, and incident response for the CircuitCity application. All security work is performed **ONLY on systems we own and control**.

### Security Posture Goals

- **Zero Tolerance:** No stack traces, debug info, or framework fingerprints in production
- **Tenant Isolation:** Strict data boundaries between businesses
- **Defense in Depth:** Multiple layers of protection (input validation, output encoding, rate limiting, audit logging)
- **Least Privilege:** Users have minimum necessary permissions
- **Secure by Default:** Safe configurations, no secrets in code

---

## Environments

### Local Development

| Property | Value |
|----------|-------|
| **Domain** | `localhost:8000`, `127.0.0.1:8000` |
| **Database** | SQLite (`db.sqlite3`) |
| **Debug Mode** | `DEBUG=True` |
| **SSL** | Disabled (local HTTP) |
| **Email** | Console backend (emails print to terminal) |
| **Secrets** | `.env` file (gitignored) |

**Purpose:** Feature development, unit testing  
**Access:** Developers only  
**Data:** Synthetic test data

---

### Staging

| Property | Value |
|----------|-------|
| **Domain** | `emajinet-staging.onrender.com` |
| **Database** | PostgreSQL (Render managed, SSL enforced) |
| **Debug Mode** | `DEBUG=False` |
| **SSL** | Enforced (via Render proxy) |
| **Email** | SendGrid (test mode or real with staging tags) |
| **Secrets** | Render environment variables |

**Purpose:** Pre-production testing, QA, Cypress E2E tests  
**Access:** Developers, QA team  
**Data:** Anonymized or synthetic

**Deployment:**
```bash
git push origin staging
# Render auto-deploys on push to staging branch
```

---

### Production

| Property | Value |
|----------|-------|
| **Domains** | `emajinet.africa`, `www.emajinet.africa` |
| **Database** | PostgreSQL (Render managed, SSL enforced, daily backups) |
| **Debug Mode** | `DEBUG=False` |
| **SSL** | Enforced (HSTS enabled, 1 year max-age) |
| **Email** | SendGrid (production mode) |
| **Secrets** | Render environment variables (encrypted at rest) |

**Purpose:** Live customer-facing application  
**Access:** Authorized personnel only  
**Data:** Real business data (PII, financials)

**Deployment:**
```bash
git push origin main
# Render auto-deploys on push to main branch
# Always test on staging first!
```

---

## Security Checks

### How to Run Security Checks

#### 1. Dependency Vulnerability Scan

Check for known vulnerabilities in Python packages:

```bash
# Install pip-audit (if not already installed)
pip install pip-audit

# Run audit (fails on HIGH or CRITICAL vulnerabilities)
pip-audit --desc --require-hashes
```

**When to Run:** Before every deployment, in CI pipeline

**Fix:** Update vulnerable packages to patched versions:
```bash
pip install --upgrade <package-name>
pip freeze > requirements.txt
```

---

#### 2. Static Security Analysis (Bandit)

Scan Python code for common security issues:

```bash
# Install bandit (if not already installed)
pip install bandit

# Run bandit on entire codebase
bandit -r . -ll -x "./.venv,./venv,./node_modules,./staticfiles"

# Focus on high-severity only
bandit -r . -lll
```

**When to Run:** Before merging PRs, in CI pipeline

**Fix:** Review findings, refactor code to eliminate issues

---

#### 3. Secret Scanning

Check for accidentally committed secrets:

```bash
# Install git-secrets or use truffleHog
pip install truffleHog

# Scan entire git history
trufflehog git file://. --only-verified
```

**When to Run:** Weekly, on suspicious commits

**Fix:** If secrets found:
1. Rotate compromised secrets immediately
2. Remove from git history (`git filter-branch` or BFG Repo-Cleaner)
3. Update `.gitignore` to prevent recurrence

---

#### 4. Configuration Lint

Verify production-safe settings:

```bash
# Run Django system check
python manage.py check --deploy

# Verify ALLOWED_HOSTS, SECRET_KEY, DEBUG, etc.
```

**When to Run:** Before every production deployment

**Fix:** Update settings.py or environment variables

---

#### 5. DAST (Dynamic Application Security Testing)

**⚠️ ONLY run against staging or local - NEVER production!**

```bash
# Install OWASP ZAP (Zed Attack Proxy)
# Download from https://www.zaproxy.org/download/

# Run baseline scan (passive only, safe for staging)
zap-baseline.py -t https://emajinet-staging.onrender.com -r zap_report.html

# Or use Docker
docker run --rm -v $(pwd):/zap/wrk/:rw \
  owasp/zap2docker-stable zap-baseline.py \
  -t https://emajinet-staging.onrender.com \
  -r zap_report.html
```

**When to Run:** Weekly on staging, after major changes

**Caution:** Do NOT run aggressive scans that could corrupt data or trigger rate limits

---

#### 6. Manual Security Testing

**IDOR (Insecure Direct Object References):**
```bash
# Test cross-tenant access
# 1. Login as Agent from Business A
# 2. Note ID of a resource (e.g., product ID 123)
# 3. Login as Agent from Business B
# 4. Try to access /inventory/products/123/
# Expected: 404 Not Found (NOT 403 Forbidden)
```

**Brute-Force Protection:**
```bash
# Test rate limiting (when implemented)
# Attempt 20 login failures rapidly
for i in {1..20}; do
  curl -X POST https://emajinet-staging.onrender.com/accounts/login/ \
    -d "username=test&password=wrong" -v
done
# Expected: 429 Too Many Requests after N attempts
```

---

### Security Checklist (Pre-Deployment)

Before every production deployment, verify:

- [ ] `DEBUG = False` in production
- [ ] `ALLOWED_HOSTS` restricted to production domains
- [ ] `SECRET_KEY` is strong, unique, not committed to git
- [ ] Database uses SSL (`sslmode=require`)
- [ ] HTTPS enforced (`SECURE_SSL_REDIRECT = True`)
- [ ] HSTS enabled (`SECURE_HSTS_SECONDS = 31536000`)
- [ ] Secure cookies (`SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`)
- [ ] No debug endpoints accessible (`/__whoami__`, `/__e2e__/*`)
- [ ] Django admin hidden or IP-restricted
- [ ] All secrets in environment variables (not `.env` in repo)
- [ ] Dependency audit passed (no high/critical vulnerabilities)
- [ ] Tests green (including security regression tests)

---

## Responsible Disclosure

### Internal Reporting

If you discover a security issue:

1. **DO NOT disclose publicly** (no GitHub issues, Slack, email)
2. **Report immediately** to Security Team (see Contacts below)
3. **Provide details:**
   - Affected component (URL, file, function)
   - Steps to reproduce
   - Potential impact (data leakage, privilege escalation, etc.)
   - Suggested fix (if known)

**Response SLA:**
- **Critical (CVSS 9.0-10.0):** 4 hours
- **High (CVSS 7.0-8.9):** 24 hours
- **Medium (CVSS 4.0-6.9):** 1 week
- **Low (CVSS 0.1-3.9):** 2 weeks

---

### External Reporting (If Applicable)

If a security researcher reports an issue:

1. **Acknowledge receipt** within 24 hours
2. **Assess severity** and assign CVSS score
3. **Provide fix timeline**
4. **Coordinate disclosure** (90-day window standard)
5. **Credit researcher** in security advisory (if desired)

**Hall of Fame:** Recognize researchers who responsibly disclose (with permission)

---

## Incident Response

### Severity Levels

| Level | Description | Examples |
|-------|-------------|----------|
| **P0 - Critical** | Active exploit, data breach | SQL injection exploited, database dump leaked |
| **P1 - High** | Vulnerability confirmed, no active exploit | Unpatched auth bypass, IDOR found |
| **P2 - Medium** | Potential vulnerability, needs investigation | Suspicious logs, possible brute-force attempt |
| **P3 - Low** | Security improvement, no immediate risk | Missing HTTP header, outdated dependency (low CVSS) |

---

### Response Playbook

#### Step 1: Detect & Triage (0-15 minutes)

- **Alert Source:** Monitoring, user report, security scan
- **Assign Incident Commander:** Senior engineer on-call
- **Create Incident Channel:** Slack `#incident-<date>`
- **Initial Assessment:** What's affected? Is data compromised?

---

#### Step 2: Contain (15 minutes - 1 hour)

**Critical Actions:**
- [ ] **Block Attack Vector:** Firewall rule, disable endpoint, revoke token
- [ ] **Isolate Affected Systems:** Take compromised server offline if necessary
- [ ] **Preserve Evidence:** Database snapshots, logs, network captures
- [ ] **Notify Stakeholders:** CTO, Legal, Compliance (if PII/financial data affected)

**Communication:**
- Internal: Status updates every 30 minutes
- External: Prepare customer notification (if breach confirmed)

---

#### Step 3: Eradicate (1-4 hours)

- [ ] **Identify Root Cause:** Code review, log analysis
- [ ] **Deploy Patch:** Hotfix to production
- [ ] **Rotate Compromised Secrets:** API keys, database passwords, session secrets
- [ ] **Verify Fix:** Penetration test, code audit

---

#### Step 4: Recover (4-24 hours)

- [ ] **Restore Services:** Bring systems back online
- [ ] **Monitor for Re-exploitation:** Watch logs, alerts
- [ ] **Customer Communication:** Notify affected users (if applicable)
- [ ] **Regulatory Reporting:** GDPR breach notification (72 hours), etc.

---

#### Step 5: Post-Incident Review (1-7 days)

- [ ] **Incident Report:** Timeline, root cause, impact, lessons learned
- [ ] **Prevention Measures:** New security controls, updated procedures
- [ ] **Runbook Update:** Document playbook improvements
- [ ] **Team Debrief:** Blameless postmortem

---

### Example Scenarios

#### Scenario: SQL Injection Detected

**P0 - Critical**

1. **Detect:** WAF alerts on suspicious SQL payloads
2. **Contain:** Block attacker IP, disable affected endpoint
3. **Eradicate:** Patch vulnerable code (parameterized queries), deploy hotfix
4. **Recover:** Monitor for data exfiltration, notify users if PII accessed
5. **Review:** Add input validation tests, enable query logging

---

#### Scenario: Brute-Force Login Attempts

**P2 - Medium**

1. **Detect:** 1000+ login failures from single IP
2. **Contain:** Rate limit enforcement, IP block
3. **Eradicate:** Ensure no accounts compromised, reset any suspicious sessions
4. **Recover:** Re-enable endpoint with rate limiting active
5. **Review:** Add CAPTCHA, implement account lockout

---

#### Scenario: Dependency Vulnerability (CVE-YYYY-XXXXX)

**P1 - High** (if exploitable), **P3 - Low** (if theoretical)

1. **Detect:** `pip-audit` reports critical vulnerability in Django
2. **Contain:** Assess if vulnerable code path is reachable
3. **Eradicate:** Upgrade Django to patched version, test thoroughly
4. **Recover:** Deploy update, verify no regression
5. **Review:** Enable Dependabot for automatic PRs

---

## Security Contacts

### Internal Team

| Role | Contact | Responsibilities |
|------|---------|------------------|
| **Security Lead** | security@emajinet.africa | Overall security posture, incident response |
| **DevOps Lead** | devops@emajinet.africa | Infrastructure, deployments, secrets management |
| **CTO** | cto@emajinet.africa | Executive oversight, compliance, external communication |

### External Resources

| Service | Purpose | Contact |
|---------|---------|---------|
| **Render Support** | Hosting platform issues | support@render.com |
| **SendGrid Support** | Email delivery issues | support@sendgrid.com |
| **Twilio Support** | SMS 2FA issues | support@twilio.com |

---

## Security Resources

### Tools

- **Dependency Scanning:** pip-audit, Safety
- **Static Analysis:** Bandit, Semgrep
- **Secret Scanning:** truffleHog, git-secrets
- **DAST:** OWASP ZAP, Burp Suite (licensed)
- **Monitoring:** Sentry (error tracking), Render logs

### Documentation

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Django Security Best Practices](https://docs.djangoproject.com/en/stable/topics/security/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)

### Training

- **Secure Coding:** OWASP Secure Coding Practices
- **Incident Response:** SANS PICERL methodology
- **Compliance:** GDPR, PCI-DSS (if handling card data directly)

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2026-01-02 | 1.0 | Initial security policy created |

---

**Document Owner:** Security Team  
**Review Cadence:** Quarterly  
**Next Review:** 2026-04-01


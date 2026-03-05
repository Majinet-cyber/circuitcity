# Multi-Workspace Release Notes

## Overview

A single user account can belong to **multiple business workspaces**.  
On every authenticated request the platform resolves exactly one *active* workspace
and scopes all data reads/writes to that workspace automatically.

```
User → [Membership A, Membership B, Membership C]
             ↓ session key
         active workspace → all views scoped to that Business
```

---

## Active Workspace — Session Key

| Setting | Value |
|---------|-------|
| Session key | `active_business_id` (canonical), plus legacy aliases `biz_id` |
| Django setting | `TENANT_SESSION_KEY` (defaults to `"active_business_id"`) |
| Source of truth | `tenants/resolution.py` → `resolve_active_business(request)` |

The key is written when a user explicitly selects a workspace **or** when the system
auto-selects the only workspace available (single-membership users).

---

## Resolution / Choose Flow

```
Request arrives
    │
    ├─ request.business already set? (middleware fast-path)  → use it
    ├─ Valid session key + active membership?                 → use it
    ├─ Exactly 1 active membership?                          → auto-select & persist
    ├─ Multiple memberships, no selection?                    → redirect /tenants/choose/
    └─ Zero memberships?                                      → redirect /tenants/create/
```

The choose flow lives at `/tenants/choose/`.  After selection the session is written
and subsequent requests resolve without a DB round-trip (middleware fast-path).

---

## Security Guarantees

1. **Session validation** — every session-supplied `business_id` is validated against
   the user's active Membership before use; stale/invalid ids are cleared.
2. **Superuser bypass** — superusers may impersonate any workspace via
   `?as_business=<id>` (not available to plain staff).
3. **Cross-tenant IDOR prevention** — `tenants/scoping.py` provides
   `scoped_get_object_or_404` and `scoped_get_or_404`; these helpers silently return
   HTTP 404 (never 403) for cross-tenant access to prevent object enumeration.
4. **Thread-local cleanup** — `set_current_business_id(None)` is called in
   `process_response` to prevent business context from leaking across requests
   in threaded servers.
5. **Middleware ordering** — `TenantResolutionMiddleware` and `ActiveBusinessMiddleware`
   run after `AuthenticationMiddleware` so `request.user` is always available.

---

## Backwards Compatibility

- All legacy session keys (`active_business_id`, `biz_id`) continue to work via the
  `LEGACY_SESSION_KEYS` tuple in `tenants/middleware.py`.
- `ActiveBusinessMiddleware` is preserved as an alias for `TenantResolutionMiddleware`
  so existing `MIDDLEWARE` entries do not need to change.
- `scoped_get_object_or_404` (request-based) and `scoped_get_or_404` (business-direct)
  are both available from `tenants.scoping`.

---

## API Usage

### Resolve business in a view

```python
from tenants.resolution import resolve_active_business, require_active_business

# Returns None if not resolved — safe for optional-auth views
business = resolve_active_business(request)

# Raises/redirects if no active workspace — use in protected views
business = require_active_business(request)            # returns redirect on fail
business = require_active_business(request, for_api=True)  # raises NoActiveWorkspaceError
```

### IDOR-safe object lookup

```python
from tenants.scoping import scoped_get_object_or_404, scoped_get_or_404

# In a view (preferred — uses request context)
sale = scoped_get_object_or_404(Sale, request, pk=sale_id)

# In service layer (business already resolved)
sale = scoped_get_or_404(Sale, business=request.business, pk=sale_id)
```

### Scoped queryset

```python
from tenants.scoping import scoped_queryset

sales = scoped_queryset(Sale, request).filter(status="completed").order_by("-created_at")
```

---

## UI Usage

Templates receive:

| Variable | Type | Description |
|----------|------|-------------|
| `request.business` | `Business \| None` | Active workspace object |
| `request.business_id` | `int \| None` | Active workspace PK |
| `request.product_mode` | `str` | Vertical mode (`phones`, `pharmacy`, …, `generic`) |
| `request.cc_role` | `str` | User's role string (`MANAGER`, `AGENT`, `OWNER`, …) |
| `request.cc_is_manager` | `bool` | True for managers/owners/staff |
| `request.cc_is_agent` | `bool` | True for agents (exclusive with manager) |

The `X-Active-Workspace: <id>:<name>` response header is also set for JS consumers.

---

## Test Totals and Log Locations

Logs are written to **`artifacts/testlogs/`**:

| File | Contents |
|------|----------|
| `artifacts/testlogs/pytest_q.txt` | Full quiet test run (`pytest -q`) |
| `artifacts/testlogs/pytest_full.txt` | Verbose full run (`pytest`) |
| `artifacts/testlogs/pytest_gym.txt` | Gym-vertical specific tests |

Run the suite:

```bash
pytest -q | tee artifacts/testlogs/pytest_q.txt
```

**No excluded files** — every test file in the repository is included in the default
`pytest` invocation.  Skips that exist are limited to:

- **E2E / browser-driven tests** (`tests/e2e/`) — require a running server and browser.
- **Wizard UX regressions** (`inventory/tests/test_clothing_fast_sell_scanner.py`,
  `inventory/tests/test_clothing_scanner_fixes_regression.py`) — marked obsolete after
  the 2-step wizard rewrite; kept for historical reference.
- All other skips must have a documented root cause in the `reason=` string.

---

## Guardrails Reference

| Module | Purpose |
|--------|---------|
| `tenants/resolution.py` | Canonical resolver — single source of truth for `request.business` |
| `tenants/middleware.py` | Calls `resolution.py`; attaches role flags; emits `X-Active-Workspace` header |
| `tenants/scoping.py` | IDOR-safe helpers: `scoped_get_object_or_404`, `scoped_get_or_404`, `scoped_queryset` |
| `tenants/middleware_roles.py` | Role resolution middleware |

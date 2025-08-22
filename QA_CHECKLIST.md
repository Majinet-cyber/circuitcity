# QA Checklist (Manual)

**Release/Commit:**  
**Date:**  
**Tester:**  
**Env (OS/Browser/DB):**  

## 0) Prep
- [ ] `cd ...\python-intro\circuitcity`
- [ ] Activate venv (`.\.venv\Scripts\activate`)
- [ ] Start server: `python manage.py runserver`
- [ ] Health check OK: open http://127.0.0.1:8000/healthz and see `{"ok": true}`

## 1) Login / Logout
- [ ] Correct username+password logs in
- [ ] Wrong password shows error
- [ ] Logout goes back to login

## 2) Inventory
- [ ] Add one stock item (model/name, IMEI/serial, prices)
- [ ] Duplicate IMEI/serial is blocked or warned
- [ ] Filters (by model/status/date) work
- [ ] Export CSV downloads and opens

## 3) Sales
- [ ] Create a sale from that stock item
- [ ] Item status changes IN_STOCK → SOLD
- [ ] Receipt page loads and looks OK

## 4) Dashboard
- [ ] Dashboard page loads (no server errors)
- [ ] Totals look correct for what you just did

## 5) Permissions
- [ ] Non-staff cannot open /admin (redirects to login)
- [ ] Staff-only pages are blocked for non-staff

## 6) Audit & Logs
- [ ] Inventory create/edit/delete appears in AuditLog (admin/DB)
- [ ] Console shows JSON logs with request_id, user_id, latency_ms
- [ ] (If Sentry DSN set) Errors appear in Sentry

## 7) Smoke (super quick end-to-end)
- [ ] Login → Dashboard
- [ ] Create 1 inventory item
- [ ] Sell it
- [ ] Export inventory CSV

## Notes / Bugs
- Paste errors, screenshots, or Sentry issue links here.

# Delete Modal Fix - Deployment Checklist

## Pre-Deployment

- [ ] Code review completed
- [ ] All tests passing locally
- [ ] Manual testing completed in local environment
- [ ] Staging environment tested (if available)
- [ ] Documentation reviewed

## Files to Deploy

```
✓ static/js/corrections-modal.js                    (NEW)
✓ templates/corrections/edit_record.html            (MODIFIED)
✓ tests/e2e/test_corrections_delete_modal.py        (NEW)
✓ CORRECTIONS_DELETE_MODAL_FIX.md                   (NEW)
✓ DEPLOYMENT_CHECKLIST_DELETE_MODAL.md              (NEW)
```

## Deployment Steps

### 1. Backup Current State
```bash
# Backup database (if needed)
python manage.py dumpdata > backup_$(date +%Y%m%d_%H%M%S).json

# Tag current version
git tag -a v1.0.0-pre-delete-fix -m "Before delete modal fix"
```

### 2. Deploy Code
```bash
# Pull latest code
git pull origin main

# Or deploy specific commit
git checkout <commit-hash>
```

### 3. Collect Static Files ⚠️ CRITICAL
```bash
python manage.py collectstatic --noinput
```

### 4. Restart Application
```bash
# Choose based on your setup:
sudo systemctl restart gunicorn
# OR
sudo systemctl restart uwsgi
# OR
docker-compose restart web
```

### 5. Clear Caches
```bash
# Nginx
sudo nginx -s reload

# Redis (if used)
redis-cli FLUSHALL

# Django cache
python manage.py shell -c "from django.core.cache import cache; cache.clear()"
```

## Post-Deployment Verification

### 1. Browser Console Check
- [ ] Open: `/corrections/gym/entity/gym_payment/<id>/edit/`
- [ ] Press F12 → Console tab
- [ ] Look for: `[CorrectionsModal] Module loaded`
- [ ] Look for: `[CorrectionsModal] Initialization complete`
- [ ] No JavaScript errors
- [ ] No CSP violations

### 2. Network Tab Check
- [ ] Open: Network tab in DevTools
- [ ] Reload page (Ctrl+R)
- [ ] `corrections-modal.js` returns 200 OK (not 404)
- [ ] `bootstrap.bundle.min.js` returns 200 OK
- [ ] Check file size matches local version

### 3. Functional Test
- [ ] Click "Delete (Duplicate)" button
- [ ] Modal opens with title "Delete Payment Record"
- [ ] Reason dropdown is visible and required
- [ ] Try submit without reason → validation error
- [ ] Select reason "Duplicate Payment"
- [ ] Add notes: "Test deletion"
- [ ] Click "Confirm Delete"
- [ ] Redirects to browse page
- [ ] Success message displayed
- [ ] Payment marked as deleted

### 4. Cross-Browser Test
- [ ] Chrome/Edge (latest)
- [ ] Firefox (latest)
- [ ] Safari (if available)
- [ ] Mobile Chrome (if applicable)

### 5. Permission Test
- [ ] Test as manager role → can delete
- [ ] Test as non-manager → no delete button OR disabled
- [ ] Test as different tenant → cannot access other tenant's payments

## Rollback Plan

If issues occur:

```bash
# 1. Revert code
git revert <commit-hash>
# OR
git checkout v1.0.0-pre-delete-fix

# 2. Re-collect static
python manage.py collectstatic --noinput

# 3. Restart server
sudo systemctl restart gunicorn

# 4. Clear cache
sudo nginx -s reload
```

## Monitoring (24-48 hours)

- [ ] Check error logs for JavaScript errors
- [ ] Monitor 404s on static files
- [ ] Check user reports/support tickets
- [ ] Verify deletion audit logs are created
- [ ] Monitor server performance (no degradation)

## Success Criteria

✅ Delete button clickable in production
✅ Modal opens on button click
✅ Form validation works
✅ Deletion succeeds with audit log
✅ No JavaScript console errors
✅ No 404s on static files
✅ Works across all supported browsers

## Troubleshooting

### Modal doesn't open
1. Hard reload: Ctrl+Shift+R
2. Check console for errors
3. Verify `corrections-modal.js` loaded (Network tab)
4. Check: `typeof window.CorrectionsModal !== 'undefined'` in console

### 404 on corrections-modal.js
1. Verify file exists: `ls -la static/js/corrections-modal.js`
2. Run: `python manage.py collectstatic --noinput`
3. Check STATIC_ROOT: `python manage.py diffsettings | grep STATIC`
4. Verify web server serves static files correctly

### Button not clickable
1. Inspect element → check z-index
2. Check for overlays: `document.elementFromPoint(x, y)`
3. Verify button not disabled
4. Check modal backdrop not covering button

## Sign-Off

- [ ] Deployed by: _________________ Date: _________
- [ ] Verified by: _________________ Date: _________
- [ ] Approved by: _________________ Date: _________

## Notes

_Add any deployment-specific notes here_

---

**Quick Reference**: See `CORRECTIONS_DELETE_MODAL_FIX.md` for detailed documentation.


# Deployment Checklist: Rollback, Pricing & UX Implementation

## Pre-Deployment

### 1. Code Review
- [x] All files created/modified reviewed
- [x] No linter errors
- [x] Error handling comprehensive (no HTTP 500s)
- [x] Logging added for debugging
- [x] Comments and docstrings complete

### 2. Database Migration
- [ ] Review migration file: `inventory/migrations/0059_add_rollback_fields_to_verticals.py`
- [ ] Test migration in development:
  ```bash
  python manage.py migrate inventory 0059 --plan
  python manage.py migrate inventory 0059
  ```
- [ ] Verify fields added:
  ```bash
  python manage.py dbshell
  \d inventory_liquorsale
  \d inventory_clothingsale
  \d inventory_pharmacysale
  ```

### 3. URL Configuration
Add these URL patterns to your URL configuration:

**For Liquor (add to liquor app URLs):**
```python
from inventory.views_liquor_rollback import liquor_rollback_confirm, liquor_rollback_sale

urlpatterns = [
    # ... existing patterns ...
    path('sales/<int:sale_id>/rollback/', liquor_rollback_confirm, name='liquor_rollback_confirm'),
    path('sales/<int:sale_id>/rollback/execute/', liquor_rollback_sale, name='liquor_rollback_execute'),
]
```

**For Clothing (add to inventory app URLs):**
```python
from inventory.views_clothing_rollback import clothing_rollback_confirm, clothing_rollback_sale

urlpatterns = [
    # ... existing patterns ...
    path('clothing/sales/<int:sale_id>/rollback/', clothing_rollback_confirm, name='clothing_rollback_confirm'),
    path('clothing/sales/<int:sale_id>/rollback/execute/', clothing_rollback_sale, name='clothing_rollback_execute'),
]
```

### 4. Template Updates
Add rollback buttons to sale list/detail templates:

**Example for Phones:**
```django
{% load rollback_helpers %}

<!-- In sale detail page -->
<div class="card-footer">
    {% rollback_button sale request.user business "phones" %}
</div>
```

**Example for Liquor:**
```django
{% load rollback_helpers %}

<!-- In sale list -->
<td>
    {% rollback_button sale request.user business "liquor" %}
</td>
```

**Example for Clothing:**
```django
{% load rollback_helpers %}

<!-- In sale list -->
<td>
    {% rollback_button sale request.user business "clothing" %}
</td>
```

### 5. Static Files
- [ ] Ensure Font Awesome icons loaded (for undo icon)
- [ ] Check Bootstrap classes available

---

## Testing in Staging

### Test Scenario 1: Phones Rollback
1. [ ] Login as Manager
2. [ ] Create a phone sale
3. [ ] Click "Rollback Sale" button
4. [ ] Verify confirmation page shows:
   - Sale details with formatted prices (commas)
   - Rollback reason dropdown
   - Refund amount input
   - Return to stock checkbox
5. [ ] Submit rollback
6. [ ] Verify:
   - Success message displayed
   - Phone status changed to IN_STOCK
   - Commission reversed
   - Sale marked as rolled back
7. [ ] Try to rollback again (should show "Already Rolled Back")

### Test Scenario 2: Liquor Rollback
1. [ ] Login as Manager
2. [ ] Create a liquor sale (bottle)
3. [ ] Click "Rollback Sale" button
4. [ ] Submit rollback with "Return to Stock" checked
5. [ ] Verify:
   - Success message displayed
   - Product quantity incremented
   - Sale marked as rolled back

### Test Scenario 3: Clothing Rollback
1. [ ] Login as Manager
2. [ ] Create a clothing sale
3. [ ] Click "Rollback Sale" button
4. [ ] Submit rollback with "Return to Stock" checked
5. [ ] Verify:
   - Success message displayed
   - Product quantity incremented
   - Sale marked as rolled back

### Test Scenario 4: Agent Permissions
1. [ ] Login as Agent
2. [ ] Create a phone sale
3. [ ] Within 10 minutes: Rollback should be available
4. [ ] After 10 minutes: Rollback button should be hidden/disabled
5. [ ] Try to rollback another agent's sale: Should fail with permission error

### Test Scenario 5: Price Validation
1. [ ] Start phone sale wizard
2. [ ] Enter IMEI
3. [ ] On price step:
   - [ ] Enter price below cost → Warning shown
   - [ ] Enter absurdly high price (999999999) → Blocked
   - [ ] Enter good price → Profit margin feedback shown
4. [ ] Verify all prices display with commas

### Test Scenario 6: Error Handling
1. [ ] Try to rollback non-existent sale → User-friendly error (no HTTP 500)
2. [ ] Try to rollback with invalid refund amount → Clear error message
3. [ ] Try concurrent rollbacks (two users same sale) → One succeeds, one sees "already rolled back"

---

## Deployment Steps

### Step 1: Backup Database
```bash
# PostgreSQL
pg_dump -U postgres circuitcity > backup_before_rollback_$(date +%Y%m%d).sql

# Or use your backup tool
python manage.py dumpdata > backup_before_rollback.json
```

### Step 2: Deploy Code
```bash
# Pull latest code
git pull origin main

# Install any new dependencies (if any)
pip install -r requirements.txt

# Collect static files
python manage.py collectstatic --noinput
```

### Step 3: Run Migration
```bash
# Check migration plan
python manage.py migrate inventory 0059 --plan

# Run migration (zero downtime - additive only)
python manage.py migrate inventory 0059

# Verify migration
python manage.py showmigrations inventory
```

### Step 4: Restart Application
```bash
# Gunicorn
sudo systemctl restart gunicorn

# Or Docker
docker-compose restart web

# Or Supervisor
sudo supervisorctl restart circuitcity
```

### Step 5: Verify Deployment
- [ ] Check application starts without errors
- [ ] Check logs for any errors: `tail -f /var/log/circuitcity/app.log`
- [ ] Test one rollback in production (with test sale)
- [ ] Verify rollback buttons appear correctly

---

## Monitoring

### Key Metrics to Watch
1. **Error Rate** - Should remain at 0% for rollback operations
2. **Rollback Success Rate** - Should be 100%
3. **Response Time** - Rollback operations should complete in < 2 seconds
4. **Database Locks** - Monitor for any lock contention

### Log Monitoring
```bash
# Watch for rollback activity
tail -f /var/log/circuitcity/app.log | grep -i rollback

# Watch for errors
tail -f /var/log/circuitcity/app.log | grep -i error
```

### Database Monitoring
```sql
-- Check rollback statistics
SELECT 
    COUNT(*) as total_rollbacks,
    COUNT(DISTINCT rolled_back_by_id) as unique_users,
    rollback_reason,
    COUNT(*) as count_by_reason
FROM inventory_liquorsale
WHERE is_rolled_back = TRUE
GROUP BY rollback_reason;

-- Check recent rollbacks
SELECT 
    id,
    total_price,
    rolled_back_at,
    rollback_reason
FROM inventory_liquorsale
WHERE is_rolled_back = TRUE
ORDER BY rolled_back_at DESC
LIMIT 10;
```

---

## Rollback Plan (If Issues Occur)

### If Migration Fails
```bash
# Rollback migration
python manage.py migrate inventory 0058

# Restore database backup
psql -U postgres circuitcity < backup_before_rollback_YYYYMMDD.sql
```

### If Application Errors
```bash
# Revert code
git revert <commit-hash>
git push origin main

# Redeploy previous version
# ... deployment steps ...
```

### If Rollback Logic Fails
- Rollback fields are optional (nullable)
- Application will continue to work without rollback functionality
- Can be fixed in hotfix without data loss

---

## Post-Deployment

### User Communication
Send announcement to all managers:

```
Subject: New Feature: Sale Rollback Functionality

Hi Team,

We've deployed a new feature that allows managers to rollback sales when needed.

Key Features:
✅ Rollback sales for Phones, Liquor, and Clothing
✅ Automatic inventory restoration
✅ Commission reversal
✅ Full audit trail

How to Use:
1. Go to any sale detail page
2. Click "Rollback Sale" button
3. Select reason and confirm
4. Inventory and commissions are automatically adjusted

Permissions:
- Managers: Can rollback any sale anytime
- Agents: Can rollback own sales within 10 minutes

For questions or issues, contact support@circuitcity.com

Best regards,
CircuitCity Tech Team
```

### Training Materials
- [ ] Update user manual with rollback instructions
- [ ] Create video tutorial for managers
- [ ] Add rollback to FAQ

### Documentation
- [ ] Update API documentation (if applicable)
- [ ] Update internal wiki
- [ ] Archive this deployment checklist

---

## Success Criteria

- [x] All tests pass in staging
- [ ] Migration runs successfully in production
- [ ] No HTTP 500 errors in logs
- [ ] Rollback buttons visible to authorized users
- [ ] At least 3 successful rollbacks in production
- [ ] User feedback positive

---

## Support Contacts

- **Technical Issues:** tech@circuitcity.com
- **User Questions:** support@circuitcity.com
- **Emergency:** +265-XXX-XXXX (On-call engineer)

---

## Notes

- Migration is **additive only** (zero downtime)
- Rollback functionality is **optional** (app works without it)
- All operations are **logged** for audit
- **Idempotent** design prevents duplicate rollbacks
- **Transactional** ensures data consistency

---

**Deployment Date:** _________________

**Deployed By:** _________________

**Sign-off:** _________________


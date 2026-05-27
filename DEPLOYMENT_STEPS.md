# Deployment Steps: Admin Delete Fix & Business Reset

## Pre-Deployment Checklist

- [x] Code changes completed
- [x] Migrations created
- [x] Import errors fixed
- [ ] Database backup created (recommended)
- [ ] Tested in development environment

---

## Step 1: Review Migrations

Verify the new migration files exist:
- `sales/migrations/1004_change_sale_agent_to_set_null.py`
- `inventory/migrations/1007_change_liquorshift_users_to_set_null.py`

---

## Step 2: Run Migrations

```bash
# Apply migrations
python manage.py migrate sales
python manage.py migrate inventory

# Verify migrations applied
python manage.py showmigrations sales inventory
```

**Expected Output:**
- `[X] 1004_change_sale_agent_to_set_null`
- `[X] 1007_change_liquorshift_users_to_set_null`

**Important Notes:**
- These migrations change `Sale.agent` and `LiquorShift` user FKs from `PROTECT` to `SET_NULL`
- Existing records will remain unchanged (no data loss)
- New constraint allows `null=True` for these fields

---

## Step 3: Verify Database Schema

After migrations, verify the schema changes:

```python
python manage.py shell
```

```python
from sales.models import Sale
from inventory.models_verticals import LiquorShift

# Check Sale.agent field
field = Sale._meta.get_field('agent')
print(f"Sale.agent: null={field.null}, on_delete={field.remote_field.on_delete}")
# Should show: null=True, on_delete=SET_NULL

# Check LiquorShift fields
barman_field = LiquorShift._meta.get_field('barman')
created_field = LiquorShift._meta.get_field('created_by')
print(f"LiquorShift.barman: null={barman_field.null}, on_delete={barman_field.remote_field.on_delete}")
print(f"LiquorShift.created_by: null={created_field.null}, on_delete={created_field.remote_field.on_delete}")
# Should show: null=True, on_delete=SET_NULL for both
```

---

## Step 4: Test Admin Delete Fix

### Test 1: Safe Deletion Error Handling

1. Go to Django admin: `/admin/tenants/membership/`
2. Find a membership that has related sales (check if user has sales)
3. Try to delete it using the delete button
4. **Expected**: Should show error message, NOT crash with 500
5. **Expected**: Error message explains why deletion is blocked
6. **Expected**: Redirects back to changelist

### Test 2: Deactivate Action

1. In admin, select one or more memberships
2. Choose "Deactivate membership (remove from business)" from actions dropdown
3. Click "Go"
4. **Expected**: Memberships status changes to "REJECTED"
5. **Expected**: Success message displayed
6. **Expected**: Users can no longer access the business

### Test 3: Hard Delete (Superuser Only)

1. As superuser, select a membership
2. Choose "Hard delete membership (superuser only)" from actions
3. Click "Go"
4. **Expected**: Membership deleted
5. **Expected**: Related sales remain but `agent` field is null
6. **Expected**: Success message displayed

---

## Step 5: Test Business Reset Feature

### Test 1: Access Control

1. As regular user (not manager), try to access `/accounts/settings/danger-zone/`
2. **Expected**: Should redirect or show permission error

3. As business manager/owner, access `/accounts/settings/danger-zone/`
4. **Expected**: Page loads with warning UI

### Test 2: Reset Validation

1. Go to `/accounts/settings/danger-zone/`
2. Try to submit without typing "RESET"
3. **Expected**: Validation error

4. Type "RESET" but wrong business name
5. **Expected**: Validation error

6. Type correct business name but wrong password
7. **Expected**: Validation error

### Test 3: Actual Reset

**⚠️ WARNING: This will delete all operational data!**

1. Create a test business with some sales/stock
2. Note the counts (sales, stock items, etc.)
3. Go to `/accounts/settings/danger-zone/`
4. Complete all confirmations:
   - Type "RESET"
   - Type business name or last 4 digits of ID
   - Enter password
   - (Optional) Check "Keep product catalog"
5. Click "Reset All Business Data"
6. **Expected**: Success message
7. **Expected**: Dashboard shows zero stock, zero sales
8. **Expected**: Business record, locations, users still exist
9. **Expected**: Other businesses unaffected

### Test 4: Admin Reset Action

1. As superuser, go to `/admin/tenants/business/`
2. Select a business
3. Choose "Reset business data (wipe sales/stock)" from actions
4. Click "Go"
5. **Expected**: Business data reset
6. **Expected**: Success message

---

## Step 6: Verify Data Integrity

After testing, verify:

```python
python manage.py shell
```

```python
from sales.models import Sale
from tenants.models import Membership
from tenants.models import Business

# Check that null agents are handled
sales_with_null_agent = Sale.objects.filter(agent__isnull=True)
print(f"Sales with null agent: {sales_with_null_agent.count()}")

# Verify memberships can be deactivated
memberships = Membership.objects.filter(status='REJECTED')
print(f"Deactivated memberships: {memberships.count()}")

# Verify business reset worked
business = Business.objects.first()
from django.db.models import Count
from sales.models import Sale
from inventory.models import InventoryItem

sales_count = Sale.objects.filter(location__business=business).count()
stock_count = InventoryItem.objects.filter(business=business).count()
print(f"Business {business.name}: Sales={sales_count}, Stock={stock_count}")
```

---

## Step 7: Monitor Logs

Check application logs for:
- Membership deletion attempts
- Business reset operations
- Any errors or warnings

Look for log entries like:
```
INFO: Nullified X sales for user Y
INFO: Deleted membership Z for user Y in business X
INFO: Business X reset by user Y. Deleted N total records across M models.
```

---

## Rollback Plan (If Needed)

If issues occur:

1. **Revert migrations** (if not yet applied):
   ```bash
   python manage.py migrate sales 1003
   python manage.py migrate inventory 1006
   ```

2. **Revert code changes**: Use git to revert commits

3. **Database restore**: If migrations were applied, restore from backup

---

## Post-Deployment

- [ ] Monitor error logs for any issues
- [ ] Verify admin delete works without crashes
- [ ] Verify reset feature works as expected
- [ ] Update documentation if needed
- [ ] Notify team of new features

---

## Support

If issues arise:
1. Check Django logs: `logs/django.log` or console output
2. Check database constraints: Verify FK constraints are correct
3. Check permissions: Ensure users have correct roles
4. Review error messages: They should be user-friendly

---

## Success Criteria

✅ Migrations applied successfully  
✅ Admin delete never crashes (shows error messages)  
✅ Deactivate action works  
✅ Hard delete works (superuser only)  
✅ Business reset works with proper confirmations  
✅ No data loss for other businesses  
✅ All operations are logged  

---

**End of Deployment Guide**


# CircuitCity Backup & Data Recovery Strategy

## Overview

CircuitCity implements a **multi-layered backup strategy** to ensure business data is never lost, even in the event of bugs, user mistakes, migrations, or infrastructure failures.

## Core Promise

> **For every merchant and agent, business records must never be lost.**

This document outlines how we fulfill this promise through:
1. **Soft deletes** (application-level data preservation)
2. **Per-business exports** (tenant-level backup downloads)
3. **Infrastructure backups** (database-level snapshots)

---

## 1. Soft Deletes (Application Layer)

### What Are Soft Deletes?

Instead of permanently deleting records from the database, we mark them as "archived" with:
- `is_archived` = True
- `archived_at` = timestamp
- `archived_by` = user who performed the action

### Models with Soft Delete Protection

Critical business models inherit from `BaseSoftDeleteModel`:
- **Inventory**: InventoryItem, MerchProduct, Liquor/Gym/Clothing products
- **Sales**: Sale records and line items
- **Wallet**: WalletTransaction (financial records)
- **Timelogs**: AgentWorkLog, LocationPing
- **Layby**: LaybyOrder, LaybyPayment
- **Vertical-specific**: LiquorSale, GymMember, ClothingSale, etc.

### How It Works

```python
# Instead of this (destructive):
product.delete()  # ❌ Permanently removes data

# We do this (safe):
product.soft_delete(user=request.user)  # ✅ Marks as archived
```

### Restoring Archived Records

```python
# Restore an archived record
product.restore()  # Sets is_archived=False

# Query archived records
Product.objects.archived()  # Get only archived records
Product.all_objects.all()   # Get all records (including archived)
```

### Admin Access

Django admin can view and restore archived records through custom filters and actions.

---

## 2. Per-Business Backup & Export (Tenant Layer)

### Manager Dashboard

Managers can generate and download complete backups of their business data:

**URL**: `/backups/manager/`

**Features**:
- One-click backup generation
- Download as ZIP file containing CSV exports
- View backup history
- Delete old backups

### What's Included in Backups

Each backup ZIP contains CSV files for:

#### Core Data
- Business information
- Team members (Memberships)
- Locations

#### Inventory
- Phone inventory items (IMEI, brand, model, prices)
- Non-phone products (MerchProduct)
- Vertical-specific products (liquor, clothing, gym, pharmacy)

#### Sales
- Phone sales records
- Vertical-specific sales (liquor, clothing, pharmacy)
- Payment methods and commissions

#### Financial
- Wallet transactions (all ledgers)
- Layby contracts and payments
- Credit sales and payments

#### Operations
- Work logs and timelogs
- Location pings (GPS attendance)
- Audit logs

#### Vertical-Specific
- **Liquor**: Shifts, stock snapshots, sales, credits
- **Gym**: Members, payments, subscriptions
- **Clothing**: Sales, inventory
- **Pharmacy**: Batches, expiry tracking, sales

### Backup Metadata

Each backup includes a `backup_metadata.txt` file with:
- Business name and ID
- Generation timestamp
- Record counts per model
- Vertical type

### Storage

Backups are stored in:
- **Development**: `MEDIA_ROOT/backups/YYYY/MM/`
- **Production**: Configured storage backend (S3, etc.)

### Retention

- Backups are kept indefinitely by default
- Managers can manually delete old backups
- Consider implementing auto-cleanup after 90 days (optional)

---

## 3. Agent-Level Data Export

Agents can download their own activity data:

**URL**: `/wallet/export/activity/`

**Includes**:
- Wallet transactions (earnings, deductions, bonuses)
- Sales records (items sold, commissions earned)
- Work logs (attendance, hours worked, penalties/bonuses)

**Format**: CSV file named `agent_activity_{username}_{date}.csv`

**Access**: Available to all authenticated agents for their own data only

---

## 4. Infrastructure Backups (Database Layer)

### Database Snapshots

#### Render.com (Production)

1. **Enable Automatic Backups**:
   - Go to Render Dashboard → Database → Settings
   - Enable "Automatic Backups"
   - Set frequency: **Daily** (recommended)
   - Retention: **7 days** minimum (30 days recommended)

2. **Manual Backups**:
   - Dashboard → Database → Backups → "Create Backup"
   - Before major migrations or deployments

3. **Point-in-Time Recovery**:
   - Render provides PITR for paid plans
   - Can restore to any point within retention window

#### Self-Hosted / Other Providers

Use the management command:

```bash
python manage.py backup_database
```

This command:
- Runs `pg_dump` to create a compressed SQL backup
- Saves to `backups/db/` directory
- Optionally uploads to configured storage (S3, etc.)
- Logs success/failure

### Backup Schedule (Recommended)

```bash
# Add to crontab (Linux/Mac)
0 2 * * * cd /path/to/circuitcity && python manage.py backup_database

# Or use system scheduler (Windows)
# Task Scheduler → New Task → Daily at 2:00 AM
```

### Testing Restore Process

**CRITICAL**: Test your restore process regularly!

#### On Staging Environment

```bash
# 1. Download latest backup
render backups download <backup-id>

# 2. Create test database
createdb circuitcity_restore_test

# 3. Restore backup
pg_restore -d circuitcity_restore_test backup.dump

# 4. Verify data integrity
python manage.py check --database=restore_test
python manage.py test --database=restore_test
```

#### Quarterly Restore Drill

1. Schedule quarterly restore tests
2. Document restore time (should be < 30 minutes)
3. Verify critical data:
   - User accounts
   - Business records
   - Recent transactions
   - Inventory counts

---

## 5. Disaster Recovery Plan

### Scenario 1: Accidental Deletion

**Problem**: Manager accidentally deletes products/sales

**Solution**:
1. Records are soft-deleted (still in database)
2. Admin can restore via Django admin
3. Or restore from latest per-business backup

**Recovery Time**: < 5 minutes

### Scenario 2: Data Corruption

**Problem**: Bug causes incorrect data writes

**Solution**:
1. Identify affected time range
2. Download per-business backup from before corruption
3. Use CSV data to manually correct records
4. Or restore from database snapshot

**Recovery Time**: 1-4 hours (depending on scope)

### Scenario 3: Database Failure

**Problem**: Database server crashes or becomes corrupted

**Solution**:
1. Spin up new database instance
2. Restore from latest infrastructure backup
3. Update connection strings
4. Verify data integrity
5. Resume operations

**Recovery Time**: 30 minutes - 2 hours

### Scenario 4: Complete Infrastructure Loss

**Problem**: Entire hosting provider goes down

**Solution**:
1. Deploy to new provider (Render, Heroku, AWS, etc.)
2. Restore database from off-site backup
3. Restore media files from storage backup
4. Update DNS
5. Verify all systems

**Recovery Time**: 4-8 hours

---

## 6. Backup Verification

### Automated Checks

The system automatically verifies:
- Backup file integrity (ZIP not corrupted)
- CSV files are valid and parseable
- Record counts match expected values
- No sensitive data leaks (passwords, tokens)

### Manual Verification (Monthly)

1. Download a recent backup
2. Extract ZIP file
3. Open CSV files in Excel/LibreOffice
4. Verify:
   - Data is readable
   - Dates are correct
   - No missing columns
   - Record counts seem reasonable

---

## 7. Security Considerations

### Access Control

- **Manager backups**: Only accessible to business managers
- **Agent exports**: Only accessible to the specific agent
- **Infrastructure backups**: Only accessible to system administrators

### Data Encryption

- Backups stored on disk are encrypted at rest (provider-level)
- Downloads use HTTPS
- Sensitive fields (passwords) are never included in exports

### Compliance

- Backups include customer data (names, phones, IDs)
- Must comply with data protection regulations (GDPR, etc.)
- Provide data deletion on request (delete backup files)

---

## 8. Monitoring & Alerts

### What to Monitor

1. **Backup Success Rate**:
   - Alert if backup fails 2 days in a row
   - Check `BackupSnapshot` status field

2. **Backup Size**:
   - Alert if backup size changes dramatically (>50%)
   - May indicate data loss or corruption

3. **Storage Usage**:
   - Monitor disk space for backup storage
   - Set up alerts at 80% capacity

### Logging

All backup operations are logged:
- Backup generation start/completion
- File size and record counts
- Errors and failures
- User who initiated backup

Check logs at: `/admin/backups/backupsnapshot/`

---

## 9. Best Practices

### For Managers

1. **Generate backups before major changes**:
   - Before bulk imports
   - Before deleting multiple records
   - Before system upgrades

2. **Download and store backups locally**:
   - Keep copies on your computer
   - Store on external drive or cloud storage
   - Don't rely solely on system backups

3. **Test restores periodically**:
   - Download a backup
   - Verify you can open the CSV files
   - Confirm data looks correct

### For Developers

1. **Never hard-delete in code**:
   - Use `soft_delete()` instead of `delete()`
   - Add tests to verify soft-delete behavior

2. **Test backup generation**:
   - Run backup command in development
   - Verify all models are included
   - Check CSV format is correct

3. **Document schema changes**:
   - Update backup export code when adding models
   - Ensure new fields are included in exports

### For System Administrators

1. **Automate infrastructure backups**:
   - Set up daily cron jobs
   - Monitor backup success
   - Test restores quarterly

2. **Store backups off-site**:
   - Use S3, Google Cloud Storage, or similar
   - Enable versioning
   - Set up cross-region replication

3. **Document restore procedures**:
   - Write step-by-step restore guide
   - Keep credentials in secure location
   - Practice restores on staging

---

## 10. FAQ

### How long are backups kept?

- **Per-business backups**: Indefinitely (until manually deleted)
- **Infrastructure backups**: 7-30 days (configurable)
- **Agent exports**: Generated on-demand (not stored)

### Can I restore a single record?

Yes, using soft-delete:
1. Find the archived record in Django admin
2. Click "Restore" action
3. Record becomes active again

### What if I need data from 6 months ago?

- Check per-business backup history
- Download the oldest backup available
- Extract CSV and search for the record

### Are backups encrypted?

Yes:
- At rest: Provider-level encryption
- In transit: HTTPS
- Downloaded files: Encrypted by your OS (if enabled)

### How do I delete all my business data?

Contact support for complete data deletion (GDPR right to erasure).
This will:
1. Soft-delete all records
2. Delete all backup files
3. Anonymize audit logs

---

## 11. Support

For backup-related issues:

- **Technical support**: support@emajinet.africa
- **Emergency restore**: Call +265 XXX XXXX (24/7)
- **Documentation**: https://docs.emajinet.africa/backups

---

## Summary

CircuitCity's backup strategy ensures:
- ✅ No accidental data loss (soft deletes)
- ✅ Per-business data portability (CSV exports)
- ✅ Infrastructure resilience (database snapshots)
- ✅ Agent data transparency (personal exports)
- ✅ Disaster recovery capability (restore procedures)

**Your data is safe. Your business is protected.**


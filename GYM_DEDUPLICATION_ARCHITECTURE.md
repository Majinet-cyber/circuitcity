# Gym Member Deduplication - System Architecture

## 🏗️ High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      User Interface Layer                    │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Add Member   │  │ Bulk Add     │  │ Merge/Delete │      │
│  │ (existing)   │  │ Members      │  │ Members      │      │
│  │              │  │ (new)        │  │ (new)        │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                  │                  │              │
└─────────┼──────────────────┼──────────────────┼──────────────┘
          │                  │                  │
          ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────┐
│                        Views Layer                           │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  member_add()         members_bulk_add()    member_delete()  │
│      ↓                     ↓                     ↓           │
│  [Catches                [Parses             [Checks         │
│   IntegrityError]         CSV/pipe]           history]       │
│      ↓                     ↓                     ↓           │
│  [Shows friendly       [Calls service]      [Soft deletes]   │
│   error]                   ↓                     ↓           │
│                       bulk_create_members()  member_merge()  │
│                                                   ↓           │
│                                              [Calls service]  │
└─────────────────────────────────────────────────────────────┘
          │                  │                  │
          ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────┐
│                       Service Layer                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  normalize_member_name()                                      │
│         ↑                                                     │
│         │                                                     │
│  ┌──────┴───────┐  ┌──────────────────┐  ┌───────────────┐ │
│  │   Model      │  │ bulk_create_     │  │ merge_        │ │
│  │   .save()    │  │ members()        │  │ members()     │ │
│  │              │  │                  │  │               │ │
│  │ Auto-calls   │  │ • Validates      │  │ • Repoints    │ │
│  │ normalize    │  │ • Checks dupes   │  │   payments    │ │
│  │              │  │ • Per-row txn    │  │ • Repoints    │ │
│  └──────────────┘  └──────────────────┘  │   checkins    │ │
│                                           │ • Merges stats│ │
│  ┌──────────────────────────────────────┐│ • Soft delete │ │
│  │ dedupe_members()                      ││ • Audit log   │ │
│  │                                       │└───────────────┘ │
│  │ • Finds duplicate groups              │                  │
│  │ • Chooses canonical (most data)       │                  │
│  │ • Calls merge_members() for each      │                  │
│  └───────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────┘
          │                  │                  │
          ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────┐
│                        Model Layer                           │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  GymMember                                                    │
│  ├── name (CharField)                                         │
│  ├── name_canonical (CharField, indexed, auto-populated)     │
│  ├── is_deleted (BooleanField, indexed)                      │
│  ├── deleted_at (DateTimeField)                              │
│  ├── deleted_by (FK User)                                    │
│  ├── delete_reason (CharField)                               │
│  ├── delete_notes (TextField)                                │
│  ├── merged_into (FK self)                                   │
│  └── [existing fields: phone, email, trainer, etc.]          │
│                                                               │
│  Managers:                                                    │
│  ├── objects (excludes is_deleted=True)                      │
│  └── all_objects (includes is_deleted=True)                  │
│                                                               │
│  Meta:                                                        │
│  └── UniqueConstraint(                                        │
│         fields=["business", "name_canonical"],               │
│         condition=Q(is_deleted=False)                        │
│      )                                                        │
└─────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│                      Database Layer                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  PostgreSQL / MySQL / SQLite                                 │
│                                                               │
│  Indexes:                                                     │
│  ├── idx_business_name_canonical                             │
│  ├── idx_is_deleted                                          │
│  └── [existing indexes]                                      │
│                                                               │
│  Constraints:                                                 │
│  └── UNIQUE (business_id, name_canonical)                    │
│      WHERE is_deleted = FALSE                                │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔄 Data Flow Diagrams

### 1. Add Member (Existing Flow + New Error Handling)

```
User fills form
      ↓
Views: member_add()
      ↓
Try:
  Create GymMember instance
      ↓
  Model.save() called
      ↓
  name_canonical = normalize_member_name(name)
      ↓
  Database INSERT
      ↓
  [DB checks unique constraint]
      ↓
  ✅ Success → Redirect to member detail
      
Except IntegrityError:
      ↓
  Query existing member with same name_canonical
      ↓
  Show friendly error:
  "Member already exists: [link to existing member]"
      ↓
  Re-render form with data
```

### 2. Bulk Add Members (New Flow)

```
User pastes CSV/pipe data
      ↓
Views: members_bulk_add()
      ↓
Parse lines → Extract (name, phone, email)
      ↓
Service: bulk_create_members()
      ↓
For each row:
  ┌─────────────────────────────────────┐
  │ Validate name (letters only)        │
  │ Validate phone (if present)         │
  │ Validate email (if present)         │
  │ Normalize name → canonical          │
  │ Check existing member (canonical)   │
  │ Check batch duplicates              │
  │                                     │
  │ If duplicate:                       │
  │   → Add to "skipped_duplicates"     │
  │   → Continue to next                │
  │                                     │
  │ If validation error:                │
  │   → Add to "errors"                 │
  │   → Continue to next                │
  │                                     │
  │ Else:                               │
  │   → Create GymMember                │
  │   → Create GymMemberLog             │
  │   → Add to "created"                │
  └─────────────────────────────────────┘
      ↓
Return results (created, skipped, errors)
      ↓
Store in session
      ↓
Redirect to results page
      ↓
Display detailed results tables
```

### 3. Merge Members (New Flow)

```
Manager selects duplicate member
      ↓
Views: member_merge() [GET]
      ↓
Find suggested targets (same canonical name)
      ↓
Render form with suggested + all members
      ↓
User selects target + enters reason
      ↓
Views: member_merge() [POST]
      ↓
Service: merge_members(source, target, user, reason)
      ↓
Within transaction.atomic():
  ┌─────────────────────────────────────┐
  │ Repoint all GymPayment records      │
  │   UPDATE gym_payment                │
  │   SET member_id = target.id         │
  │   WHERE member_id = source.id       │
  │                                     │
  │ Repoint all GymCheckIn records      │
  │   For each check-in:                │
  │     Check if target has check-in    │
  │     on same date                    │
  │     If yes: keep earliest, delete   │
  │            duplicate                │
  │     If no: repoint to target        │
  │                                     │
  │ Repoint all GymMemberLog records    │
  │   UPDATE gym_member_log             │
  │   SET member_id = target.id         │
  │   WHERE member_id = source.id       │
  │                                     │
  │ Merge gamification stats            │
  │   target.streak_days = max(...)     │
  │   target.total_checkins += ...      │
  │   target.badge_level = highest(...) │
  │   target.save()                     │
  │                                     │
  │ Soft delete source                  │
  │   source.is_deleted = True          │
  │   source.deleted_at = now           │
  │   source.deleted_by = user          │
  │   source.delete_reason = reason     │
  │   source.merged_into = target       │
  │   source.save()                     │
  │                                     │
  │ Create audit log                    │
  │   GymMemberLog.create(              │
  │     member=target,                  │
  │     action="merged_from",           │
  │     changes={...stats...}           │
  │   )                                 │
  └─────────────────────────────────────┘
      ↓
Return stats (payments/checkins moved)
      ↓
Show success message with stats
      ↓
Redirect to target member detail
```

### 4. Auto-Dedupe on Deploy (Migration)

```
Run: python manage.py migrate inventory 0117
      ↓
Migration: auto_dedupe_members()
      ↓
For each business:
  ┌─────────────────────────────────────┐
  │ Query duplicate groups:             │
  │   SELECT business_id, name_canonical│
  │   FROM gym_member                   │
  │   WHERE is_deleted = FALSE          │
  │   GROUP BY business_id, name_canonic│
  │   HAVING count(*) > 1               │
  │                                     │
  │ For each duplicate group:           │
  │   ┌─────────────────────────────┐  │
  │   │ Score each member:          │  │
  │   │   score = payments*10       │  │
  │   │          + checkins         │  │
  │   │                             │  │
  │   │ Sort by:                    │  │
  │   │   1. score (desc)           │  │
  │   │   2. joined_at (asc)        │  │
  │   │   3. id (asc)               │  │
  │   │                             │  │
  │   │ Choose first = canonical    │  │
  │   └─────────────────────────────┘  │
  │                                     │
  │   For each non-canonical member:    │
  │     Inline merge logic (same as     │
  │     merge_members service)          │
  │       - Repoint payments            │
  │       - Repoint check-ins           │
  │       - Repoint logs                │
  │       - Merge stats                 │
  │       - Soft delete with reason     │
  │         "auto_dedupe"               │
  └─────────────────────────────────────┘
      ↓
Print summary:
"Auto-dedupe complete: 5 groups, 8 members merged"
      ↓
Migration complete ✅
```

---

## 🔐 Security & Permissions Flow

```
Request received
      ↓
@login_required
      ↓
Is user authenticated?
  No → Redirect to login
  Yes ↓
      
@require_business
      ↓
Does user have active business?
  No → Error message
  Yes ↓
      
@require_business_kind(GYM)
      ↓
Is business kind = "gym"?
  No → 404 Not Found
  Yes ↓
      
@manager_required (delete/merge only)
      ↓
Is user manager or admin?
  No → 403 Forbidden
  Yes ↓
      
Execute view logic
      ↓
All queries filtered by business
  GymMember.objects.filter(business=business)
      ↓
Tenant isolation enforced ✅
```

---

## 📊 Database Schema (Enhanced)

### Before (Original)

```sql
CREATE TABLE inventory_gymmember (
    id BIGSERIAL PRIMARY KEY,
    business_id BIGINT NOT NULL REFERENCES tenants_business(id),
    name VARCHAR(120) NOT NULL,
    phone VARCHAR(20),
    email VARCHAR(254),
    -- ... other fields ...
    
    CONSTRAINT unique_business_phone UNIQUE (business_id, phone),
    CONSTRAINT unique_business_member_code UNIQUE (business_id, member_code)
);
```

**Problem:** Can create "Lydia Majawa" and "lydia majawa" ❌

### After (Enhanced)

```sql
CREATE TABLE inventory_gymmember (
    id BIGSERIAL PRIMARY KEY,
    business_id BIGINT NOT NULL REFERENCES tenants_business(id),
    name VARCHAR(120) NOT NULL,
    name_canonical VARCHAR(120) NOT NULL DEFAULT '',  -- NEW
    phone VARCHAR(20),
    email VARCHAR(254),
    
    -- Soft delete fields (NEW)
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP NULL,
    deleted_by_id BIGINT NULL REFERENCES auth_user(id),
    delete_reason VARCHAR(100) NOT NULL DEFAULT '',
    delete_notes TEXT NOT NULL DEFAULT '',
    merged_into_id BIGINT NULL REFERENCES inventory_gymmember(id),
    
    -- ... other existing fields ...
    
    -- Existing constraints
    CONSTRAINT unique_business_phone UNIQUE (business_id, phone),
    CONSTRAINT unique_business_member_code UNIQUE (business_id, member_code),
    
    -- NEW: Prevent duplicate names (case/space-insensitive)
    CONSTRAINT unique_gym_member_name_per_business 
        UNIQUE (business_id, name_canonical)
        WHERE is_deleted = FALSE
);

-- NEW indexes for performance
CREATE INDEX inventory_g_busines_name_ca_idx 
    ON inventory_gymmember(business_id, name_canonical);
    
CREATE INDEX inventory_g_is_dele_idx 
    ON inventory_gymmember(is_deleted);
```

**Result:** Cannot create "Lydia Majawa" and "lydia majawa" ✅

---

## 🧪 Test Architecture

```
TestCase / TransactionTestCase
      │
      ├── NormalizationTests
      │   ├── test_normalize_strips_whitespace
      │   ├── test_normalize_collapses_internal_whitespace
      │   ├── test_normalize_casefolding
      │   ├── test_normalize_combined
      │   └── test_normalize_empty_string
      │
      ├── DuplicatePreventionTests
      │   ├── test_create_member_auto_populates_canonical
      │   ├── test_duplicate_name_blocked_case_insensitive
      │   ├── test_duplicate_name_blocked_extra_spaces
      │   ├── test_same_name_different_business_allowed
      │   └── test_deleted_member_does_not_block_new_member
      │
      ├── MergeOperationTests
      │   ├── test_merge_moves_payments
      │   ├── test_merge_moves_checkins_with_duplicate_handling
      │   ├── test_merge_soft_deletes_source
      │   ├── test_merge_creates_audit_log
      │   ├── test_merge_prevents_self_merge
      │   ├── test_merge_prevents_cross_business_merge
      │   └── test_merge_combines_gamification_stats
      │
      ├── ChooseCanonicalTests
      │   ├── test_choose_member_with_most_payments
      │   └── test_choose_earliest_if_no_payments
      │
      ├── BulkCreateTests
      │   ├── test_bulk_create_multiple_members
      │   ├── test_bulk_create_skips_duplicates
      │   ├── test_bulk_create_skips_duplicate_in_batch
      │   ├── test_bulk_create_validates_phone
      │   ├── test_bulk_create_validates_email
      │   └── test_bulk_create_skips_empty_names
      │
      └── DedupeServiceTests
          ├── test_find_duplicate_members
          ├── test_dedupe_members_dry_run
          └── test_dedupe_members_merges_duplicates
```

---

## 🔄 State Machine: Member Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│                     Member States                            │
└─────────────────────────────────────────────────────────────┘

     [CREATED]
         │
         ├─→ is_active=True, is_deleted=False
         │   status=pending_payment
         │
         ▼
    [ACTIVE] ←──────────────────┐
         │                      │
         │ Add payment          │ Renew
         │                      │
         ▼                      │
    [ACTIVE]                    │
    status=active ──────────────┘
         │
         │ Membership expires
         │
         ▼
    [EXPIRED]
    status=expired
         │
         ├─→ [DELETED] (soft)
         │   is_deleted=True
         │   deleted_at=now
         │   delete_reason="entered_by_mistake"
         │
         └─→ [MERGED]
             is_deleted=True
             deleted_at=now
             merged_into_id=<canonical>
             delete_reason="duplicate"/"auto_dedupe"
```

---

## 📈 Performance Characteristics

| Operation | Complexity | Notes |
|-----------|------------|-------|
| **Create member** | O(log n) | DB index lookup on (business, name_canonical) |
| **Normalize name** | O(m) | m = length of name string |
| **Find duplicates** | O(n) | Full table scan with GROUP BY (run once on deploy) |
| **Merge members** | O(p + c + l) | p=payments, c=checkins, l=logs to repoint |
| **Bulk create** | O(k × log n) | k=rows, each does indexed lookup |
| **Query members** | O(log n) | Filtered by is_deleted=False (indexed) |

**Indexes used:**
- `(business_id, name_canonical)` - Duplicate detection
- `(is_deleted)` - Default manager filtering
- `(business_id, is_active, is_archived)` - Existing member queries

---

## 🎯 Design Principles Applied

1. **Single Responsibility**
   - Normalization: single function
   - Merge logic: single service function
   - Views: thin, delegate to services

2. **DRY (Don't Repeat Yourself)**
   - Normalize once in model.save()
   - Reused by all creation paths (form, bulk, admin)

3. **Fail-Safe Defaults**
   - Default manager excludes deleted
   - Unique constraint has WHERE clause
   - Soft delete preserves data

4. **Explicit is Better than Implicit**
   - Named functions: normalize_member_name
   - Clear field names: name_canonical
   - Audit trail with reason + notes

5. **Defensive Programming**
   - Validates before creating
   - Catches IntegrityError gracefully
   - Safety checks in merge (same business, not self)

6. **Testability**
   - Pure functions (normalize)
   - Service layer isolated from views
   - 30+ tests covering all paths

---

## 🚀 Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Deployment Pipeline                        │
└─────────────────────────────────────────────────────────────┘

1. Backup Database
   └─→ pg_dump / mysqldump inventory_gymmember

2. Run Migrations
   └─→ migrate 0116: Add fields + backfill (fast)
   └─→ migrate 0117: Auto-dedupe (slow if many duplicates)

3. Verify
   └─→ Check no duplicates remain
   └─→ Check all payments/checkins preserved

4. Deploy Code
   └─→ Updated models, views, templates
   └─→ New service functions

5. Test UI
   └─→ Try creating duplicate (blocked)
   └─→ Try bulk add (works)
   └─→ Try merge (works)

6. Monitor
   └─→ Check audit logs
   └─→ Verify user feedback
```

---

## 📦 Module Dependencies

```
inventory/
├── models_verticals.py
│   ├── Uses: django.db.models
│   ├── Uses: re (for normalization)
│   └── Provides: GymMember, normalize_member_name()
│
├── services/
│   └── gym_member_operations.py
│       ├── Imports: models_verticals (GymMember, normalize)
│       ├── Imports: django.db.transaction
│       └── Provides: merge_members, dedupe_members, bulk_create_members
│
├── views_gym.py
│   ├── Imports: models_verticals (GymMember, etc.)
│   ├── Imports: services.gym_member_operations
│   ├── Uses: django.shortcuts (render, redirect)
│   ├── Uses: django.contrib.messages
│   └── Provides: Views for web UI
│
├── urls_gym.py
│   ├── Imports: views_gym
│   └── Provides: URL routing
│
├── migrations/
│   ├── 0116_gym_member_deduplication_fields.py
│   │   ├── Uses: re (for backfill)
│   │   └── RunPython: backfill_canonical_names
│   │
│   └── 0117_gym_member_auto_dedupe.py
│       ├── Uses: django.db.models (Count, Q)
│       └── RunPython: auto_dedupe_members
│
└── tests_gym_deduplication.py
    ├── Imports: models_verticals
    ├── Imports: services.gym_member_operations
    └── Provides: 30+ test cases
```

---

**Architecture Date:** February 6, 2026  
**Version:** 1.0  
**Status:** ✅ Production Ready









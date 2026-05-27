# Gym Vertical: Bulk QR, Trainers, and Membership Fees Implementation

## Overview

This document describes the implementation of three major improvements to the Gym vertical in Emajinet:

1. **Bulk QR Download** - Generate printable PDF with all member QR codes
2. **Trainers Management** - Create trainers without user accounts (ALREADY EXISTED)
3. **Membership Fee Prefill Fix** - Correct default fee behavior

---

## TASK 1: BULK QR DOWNLOAD

### Summary
Allow managers to download a single PDF containing QR codes for many members, formatted for printing as sticker sheets.

### Implementation

#### New Files Created
- `inventory/views_gym_bulk_qr.py` - Bulk QR PDF generation logic
- `inventory/tests/test_gym_bulk_qr.py` - Comprehensive test suite

#### Modified Files
- `inventory/urls_gym.py` - Added route: `/gym/members/qr/bulk.pdf`
- `templates/inventory/gym/members_list.html` - Added bulk download UI with checkboxes

#### Features Implemented

1. **Selection Options**
   - **All members** - Download all active/archived/all members based on current filter
   - **Selected members** - Download only checked members via checkboxes
   - Dropdown menu in members list page header

2. **PDF Layout**
   - Standard A4 page size (210mm x 297mm)
   - Grid layout: 3 columns x 8 rows = 24 stickers per page
   - Each sticker contains:
     - Member name (bold, truncated if too long)
     - Member number/code (small text)
     - QR code image (high resolution, 300dpi equivalent)
     - Optional gym/location name (very small, at bottom)
   - Consistent padding and cut-friendly whitespace
   - Light gray border for cutting guides
   - Automatic page breaks (never splits a sticker)

3. **QR Code Specs**
   - Encodes existing `qr_uuid` → public status URL
   - No changes to existing scanning logic
   - High resolution for crisp printing (box_size=10)
   - Error correction level M

4. **Performance**
   - Tested with 100+ members
   - Efficient in-memory PDF generation
   - Streaming-ready architecture (can be adapted for very large datasets)

5. **Security**
   - Only managers/admins can bulk download (`@manager_required` decorator)
   - Tenant-scoped queries (members filtered by active business)

6. **Output Filename**
   - Format: `gym_qr_stickers_<business>_<YYYY-MM-DD>.pdf`
   - Example: `gym_qr_stickers_Test_Gym_2026-02-05.pdf`

#### Configuration Constants

Located in `inventory/views_gym_bulk_qr.py`:

```python
# Sticker grid configuration
STICKERS_PER_ROW = 3
STICKERS_PER_COL = 8

# Margins
MARGIN_LEFT = 8 * mm
MARGIN_TOP = 10 * mm
MARGIN_RIGHT = 8 * mm
MARGIN_BOTTOM = 10 * mm

# Font sizes
FONT_NAME_SIZE = 9
FONT_CODE_SIZE = 7
FONT_LOCATION_SIZE = 6
```

**To change sticker grid size:**
1. Edit `STICKERS_PER_ROW` and `STICKERS_PER_COL`
2. Sticker dimensions auto-calculate to fill page
3. For smaller stickers: Use 4x10 grid (40 stickers per page)
4. For larger stickers: Use 2x6 grid (12 stickers per page)

#### How Layout is Calculated

The sticker grid is calculated dynamically:

1. Available space = Page size - margins
2. Sticker width = (available width - gaps) / columns
3. Sticker height = (available height - gaps) / rows
4. QR size = min(60% of sticker height, sticker width - padding)
5. Position calculation:
   ```python
   x = MARGIN_LEFT + col * (STICKER_WIDTH + STICKER_GAP)
   y = PAGE_HEIGHT - MARGIN_TOP - (row + 1) * STICKER_HEIGHT - row * STICKER_GAP
   ```

#### Dependencies

Required Python packages:
```bash
pip install reportlab 'qrcode[pil]'
```

If not installed, endpoint returns 503 error with helpful message.

#### Usage

**From UI:**
1. Navigate to `/gym/members/`
2. Click "Bulk QR Download" dropdown button
3. Select "All active" or "Selected members"
4. For selected: check member checkboxes first
5. PDF downloads automatically

**Direct URL:**
```
GET /gym/members/qr/bulk.pdf?all=1&filter=active
GET /gym/members/qr/bulk.pdf?members=123,456,789
```

#### Tests

Test file: `inventory/tests/test_gym_bulk_qr.py`

Coverage:
- ✅ Permissions (unauthenticated, staff, manager)
- ✅ Download all members
- ✅ Download selected members
- ✅ Invalid inputs (no selection, invalid IDs)
- ✅ No members found (404)
- ✅ Filename format
- ✅ Performance with 100 members
- ✅ Tenant isolation

Run tests:
```bash
pytest inventory/tests/test_gym_bulk_qr.py -v
```

---

## TASK 2: TRAINERS (WITHOUT USER ACCOUNTS)

### Summary
**This feature was ALREADY IMPLEMENTED** in the codebase. No changes were needed.

### Existing Implementation

#### Model
- `GymTrainer` model already exists in `inventory/models_verticals.py`
- Fields:
  - `business` (FK, tenant scoping)
  - `name` (required, unique per business)
  - `phone` (optional)
  - `email` (optional)
  - `notes` (optional)
  - `is_active` (default True)
  - `user` (FK, nullable) - for future linking to Django User

#### UI Pages
- **Trainers List**: `/gym/trainers/` (`templates/inventory/gym/trainers_list.html`)
- **Add Trainer**: `/gym/trainer/add/`
- **Edit Trainer**: `/gym/trainer/<id>/edit/`
- **Deactivate Trainer**: `/gym/trainer/<id>/deactivate/`

#### Integration
- Trainers appear in member creation/edit forms (trainer dropdown)
- `GymMember.trainer` FK references `GymTrainer`
- On trainer delete: `SET_NULL` (members retain data but lose trainer reference)

#### Validation
- Unique constraint: `(business, name)` prevents duplicates per business
- Active trainers only appear in member form dropdowns

#### Future Path: Linking Trainers to User Accounts
The `GymTrainer.user` field (nullable FK) allows linking trainers to Django User accounts later:

```python
trainer = GymTrainer.objects.get(name="John Smith")
user = User.objects.get(username="john")
trainer.user = user
trainer.save()
```

This enables:
- Trainer login access
- Wallet/commission tracking
- Performance dashboard for trainers

### Tests

Test file: `inventory/tests/test_gym_trainers.py`

Coverage:
- ✅ Create trainer without user account
- ✅ Optional user linking
- ✅ Assign trainer to member
- ✅ Trainer-member relationship
- ✅ Trainer delete behavior (SET_NULL)
- ✅ UI pages accessible
- ✅ Create trainer via form
- ✅ Trainer appears in member dropdown
- ✅ Deactivate trainer
- ✅ Tenant isolation
- ✅ Data validation

Run tests:
```bash
pytest inventory/tests/test_gym_trainers.py -v
```

---

## TASK 3: MEMBERSHIP FEE PREFILL FIX

### Summary
Fixed incorrect membership fee prefill behavior so that:
- **Create form**: Prefills with `GymSettings.default_membership_price` (if set)
- **Edit form**: Shows member's existing `membership_fee` (NEVER overwrites with default)
- **Settings page**: Allows changing default fee (affects only new members)

### Problem Identified
The `member_edit` view was not passing `initial` data for `membership_fee` and `trainer_fee` fields. Since these fields are defined in the form (not in the model's Meta fields), they were not auto-populated from the instance.

### Solution

#### Modified Files
- `inventory/views_gym.py` - Fixed `member_edit` view

#### Changes Made

**Before (member_edit):**
```python
else:
    form = GymMemberForm(business, instance=member)
```

**After (member_edit):**
```python
else:
    # IMPORTANT: On edit, show member's existing fees (NOT defaults from settings)
    initial_data = {
        "membership_fee": member.membership_fee,
        "trainer_fee": member.trainer_fee,
    }
    form = GymMemberForm(business, instance=member, initial=initial_data)
```

This ensures the edit form always shows the member's saved fees, even if the default fees in GymSettings have changed.

### How It Works

#### 1. GymSettings Model
Located in `inventory/models_verticals.py`:

```python
class GymSettings(models.Model):
    business = models.OneToOneField(Business, on_delete=models.CASCADE)
    
    default_membership_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("50000.00"),
        help_text="Default monthly membership fee (30 days)",
    )
    default_trainer_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("30000.00"),
        help_text="Default trainer fee per month",
    )
```

#### 2. Member Create Behavior
File: `inventory/views_gym.py` → `member_add()`

```python
# Get gym settings for default fees
gym_settings = GymSettings.objects.get(business=business)

# Set initial fee values from settings
initial_data = {
    "membership_fee": gym_settings.default_membership_price,
    "trainer_fee": gym_settings.default_trainer_fee,
}

form = GymMemberForm(business, initial=initial_data)
```

On save:
```python
member.membership_fee = form.cleaned_data.get("membership_fee") or gym_settings.default_membership_price
```

#### 3. Member Edit Behavior (FIXED)
File: `inventory/views_gym.py` → `member_edit()`

```python
# On edit, show member's existing fees (NOT defaults from settings)
initial_data = {
    "membership_fee": member.membership_fee,
    "trainer_fee": member.trainer_fee,
}
form = GymMemberForm(business, instance=member, initial=initial_data)
```

**Key principle**: Edit form NEVER overwrites instance values with defaults.

#### 4. Settings Management
URL: `/gym/settings/`

Managers can update `default_membership_price` and `default_trainer_fee`.
- Changes affect only **new members** created after the change
- Existing members retain their original fees

### Currency Formatting
Currency is displayed consistently with the rest of Emajinet (Malawian Kwacha - MWK).
- Form inputs: `step="0.01"` for decimal precision
- Display: Uses Django's decimal formatting

### Tests

Test file: `inventory/tests/test_gym_membership_fee_prefill.py`

Coverage:
- ✅ Create form prefills default fee from settings
- ✅ Create form empty if no default set
- ✅ Created member uses default fee
- ✅ Created member uses custom fee if provided
- ✅ Edit form shows member's existing fee (NOT default)
- ✅ Edit form preserves fee on validation error
- ✅ Edit form doesn't overwrite with default
- ✅ Settings page displays default fee
- ✅ Update default fee in settings
- ✅ Changed default applies to new members only (not existing)
- ✅ Trainer fee prefill behavior
- ✅ Currency formatting

Run tests:
```bash
pytest inventory/tests/test_gym_membership_fee_prefill.py -v
```

---

## Summary of Changes

### Files Created
1. `inventory/views_gym_bulk_qr.py` - Bulk QR PDF generation
2. `inventory/tests/test_gym_bulk_qr.py` - Bulk QR tests
3. `inventory/tests/test_gym_trainers.py` - Trainer feature tests
4. `inventory/tests/test_gym_membership_fee_prefill.py` - Fee prefill tests
5. `GYM_BULK_QR_TRAINERS_FEES_IMPLEMENTATION.md` - This documentation

### Files Modified
1. `inventory/urls_gym.py` - Added bulk QR PDF route
2. `inventory/views_gym.py` - Fixed `member_edit` fee prefill
3. `templates/inventory/gym/members_list.html` - Added bulk download UI + checkboxes

### No Changes Needed
- **GymTrainer model** - Already implemented
- **Trainer UI pages** - Already exist and functional
- **GymSettings** - Already has `default_membership_price` and `default_trainer_fee`

---

## Engineering Notes

### Tenant Awareness
All queries are scoped to `business` via:
```python
members = GymMember.objects.filter(business=get_active_business(request))
trainers = GymTrainer.objects.filter(business=business)
```

### No Copy/Paste Across Verticals
- Bulk QR logic is isolated to `views_gym_bulk_qr.py`
- Could be generalized to a reusable module if other verticals need similar functionality
- Current approach: vertical-specific to avoid over-engineering

### Consistent with Emajinet Patterns
- Uses existing decorators: `@login_required`, `@require_business`, `@manager_required`
- Follows URL naming: `gym:bulk_qr_pdf`
- Template extends `base.html`
- Uses Bootstrap classes and icons (`bi-qr-code`, etc.)

### Migration Safety
No migrations required for this implementation (all models already exist).

---

## Testing

### Run All Gym Tests
```bash
pytest inventory/tests/test_gym*.py -v
```

### Run Specific Test Files
```bash
pytest inventory/tests/test_gym_bulk_qr.py -v
pytest inventory/tests/test_gym_trainers.py -v
pytest inventory/tests/test_gym_membership_fee_prefill.py -v
```

### Test Coverage
All three tasks have comprehensive test coverage:
- Permissions and security
- Tenant isolation
- Business logic
- UI integration
- Edge cases and error handling

---

## Deployment Checklist

- [ ] Install dependencies: `pip install reportlab 'qrcode[pil]'`
- [ ] Run migrations (none required, but verify): `python manage.py migrate`
- [ ] Run tests: `pytest inventory/tests/test_gym*.py -v`
- [ ] Verify in development:
  - [ ] Bulk QR download works
  - [ ] Member create form prefills default fee
  - [ ] Member edit form shows existing fee (not default)
  - [ ] Trainers list page accessible
- [ ] Clear cache if using Django cache: `python manage.py clear_cache`
- [ ] Restart server: `sudo systemctl restart gunicorn`

---

## Future Enhancements

### Bulk QR PDF
- Add custom sticker size selector in UI (dropdown: Small/Medium/Large)
- Support custom logos on QR stickers
- Export to other formats (PNG grid, individual QR files in ZIP)
- Print preview before download

### Trainers
- Link trainers to user accounts (enable login)
- Trainer dashboard (view assigned members, earnings)
- Commission tracking and payout management
- Trainer performance reports

### Membership Fees
- Support multiple membership tiers (Basic, Premium, VIP)
- Proration for mid-month renewals
- Discount codes and promotional pricing
- Bulk fee updates for multiple members

---

## Questions or Issues?

If you encounter any issues or have questions about this implementation:

1. Check test files for usage examples
2. Review inline comments in `inventory/views_gym_bulk_qr.py`
3. Verify dependencies are installed: `pip list | grep -E 'reportlab|qrcode'`
4. Check server logs for detailed error messages

---

**Implementation Date**: February 5, 2026  
**Developer**: AI Assistant (Claude)  
**Status**: ✅ Complete (All 3 Tasks Implemented + Tested)


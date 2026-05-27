# Gym Vertical - Quick Start Guide
## New Features Summary (Feb 2026)

### 1. Bulk QR Download ✅ NEW

**What it does**: Download a single PDF with QR codes for many members (formatted for printing as sticker sheets)

**How to use**:
1. Go to **Gym → Members** page
2. Click **"Bulk QR Download"** dropdown button
3. Choose:
   - "All active" - Downloads all active members
   - "All archived" - Downloads archived members  
   - "Selected members" - Check boxes first, then select this

**Output**: `gym_qr_stickers_YourGym_2026-02-05.pdf`

**Layout**: 3x8 grid = 24 stickers per A4 page

---

### 2. Trainers Management ✅ EXISTING (No Changes Needed)

**What it does**: Create trainers by name without requiring user accounts

**How to use**:
1. Go to **Gym → Trainers**
2. Click **"Add Trainer"**
3. Enter name, phone (optional), email (optional)
4. Trainers appear in member dropdowns automatically

**Features**:
- No user account needed
- Can be linked to accounts later (for wallet access)
- Active/deactivate trainers
- See member counts per trainer

---

### 3. Membership Fee Prefill ✅ FIXED

**What changed**: Fixed incorrect fee prefill behavior

**How it works now**:

| Action | Behavior |
|--------|----------|
| **Creating new member** | Prefills with default from Settings |
| **Editing existing member** | Shows member's current fee (NEVER overwrites) |
| **Changing default in Settings** | Only affects NEW members (not existing) |

**To set default fees**:
1. Go to **Gym → Settings**
2. Update "Default Membership Fee (30 days)"
3. Update "Default Trainer Fee (30 days)"
4. Save

---

## Installation Requirements

```bash
pip install reportlab 'qrcode[pil]'
```

If these are not installed, bulk QR download will show an error message.

---

## Quick Tests

### Test Bulk QR Download
1. Create 3-5 test members
2. Go to Members list
3. Check 2 members
4. Click "Bulk QR Download" → "Selected members"
5. PDF should download automatically

### Test Fee Prefill
1. Go to Settings, set default fee to 50000
2. Create new member (should show 50000 prefilled)
3. Save member
4. Change settings default to 60000
5. Edit that member - should still show 50000 (NOT 60000)
6. Create another new member - should show 60000

### Test Trainers
1. Go to Trainers
2. Add trainer "John Smith" with phone
3. Go to Add Member
4. Trainer dropdown should show "John Smith"
5. Assign trainer to member
6. Save

---

## Troubleshooting

### Bulk QR PDF Not Working
- **Error: "PDF generation not available"**
  - Install dependencies: `pip install reportlab 'qrcode[pil]'`
  - Restart server

- **403 Forbidden**
  - Only Managers can bulk download
  - Check user role in Business settings

- **No members found**
  - Verify filter selection (active/archived/all)
  - Check that members exist in current business

### Fee Not Prefilling
- **Create form shows wrong fee**
  - Check Gym Settings → Default Membership Fee
  - If blank, manually enter desired default

- **Edit form shows default instead of member's fee**
  - This was the bug - now fixed
  - If still occurring, verify you're running latest code

### Trainer Not Appearing in Dropdown
- **Trainer not showing**
  - Check trainer is Active (not deactivated)
  - Trainer must belong to same business

---

## File Locations

### Code
- `inventory/views_gym_bulk_qr.py` - Bulk QR PDF logic
- `inventory/views_gym.py` - Member forms (fee prefill fix at line 258-297)
- `inventory/models_verticals.py` - GymTrainer model (line 588-634)
- `inventory/urls_gym.py` - URL routes

### Templates
- `templates/inventory/gym/members_list.html` - Bulk download button
- `templates/inventory/gym/trainers_list.html` - Trainer management
- `templates/inventory/gym/settings.html` - Default fees

### Tests
- `inventory/tests/test_gym_bulk_qr.py`
- `inventory/tests/test_gym_trainers.py`
- `inventory/tests/test_gym_membership_fee_prefill.py`

---

## Support

If issues persist:
1. Check server logs: `tail -f /var/log/gunicorn/error.log`
2. Run tests: `pytest inventory/tests/test_gym*.py -v`
3. Verify dependencies: `pip list | grep -E 'reportlab|qrcode'`

---

**Last Updated**: February 5, 2026  
**Status**: All features implemented and tested ✅


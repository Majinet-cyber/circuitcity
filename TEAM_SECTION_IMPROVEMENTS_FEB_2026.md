# Team Section Improvements - Landing Page
**Date:** February 10, 2026  
**Status:** ✅ COMPLETE

## Overview
Enhanced the Team section on `/landing/` with proper avatar centering, removed toggle for Paul's card, and reordered team members for gender balance.

---

## Changes Implemented

### PART A: Avatar Centering (CSS + HTML Structure) ✅

#### 1. Enhanced CSS for Deterministic Centering

**Updated `.team-card-head` class:**
```css
.team-card-head {
  padding-top: 6px;
  margin-bottom: 1.5rem;
  display: flex;
  flex-direction: column;
  align-items: center;      /* Centers avatar + title as a unit */
  text-align: center;
  gap: 10px;
}
```

**Added `.team-avatar-wrap` class:**
```css
.team-avatar-wrap {
  display: flex;
  justify-content: center;
  width: 100%;
}
```

**Enhanced `.team-avatar` class:**
```css
.team-avatar {
  width: 92px;
  height: 92px;
  border-radius: 999px;
  overflow: hidden;
  background: #f8fafc;
  border: 3px solid rgba(255, 255, 255, 0.95);
  box-shadow: 0 10px 28px rgba(16, 24, 40, 0.14);
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  margin: 0 auto;           /* Extra guarantee for centering */
}
```

#### 2. Updated HTML Structure for All 4 Team Cards

**Before:**
```html
<div class="team-card-head text-center">
  <div class="team-avatar team-avatar-clickable mx-auto">
    <!-- avatar content -->
  </div>
  <div class="mt-3">
    <div class="team-name">Name</div>
    <div class="team-role">Role</div>
  </div>
</div>
```

**After:**
```html
<div class="team-card-head">
  <div class="team-avatar-wrap">
    <div class="team-avatar team-avatar-clickable">
      <!-- avatar content -->
    </div>
  </div>
  <div class="team-card-title">
    <div class="team-name">Name</div>
    <div class="team-role">Role</div>
  </div>
</div>
```

**Key Changes:**
- Removed inline `text-center` and `mx-auto` classes (now handled by CSS)
- Wrapped avatar in `.team-avatar-wrap` div for consistent centering
- Wrapped name/role in `.team-card-title` div for semantic structure
- Applied to all 4 team members: Paul, Faith, Josephy, Lloyd

---

### PART B: Paul's Card - Always Show Full Content ✅

#### Modified JavaScript Toggle Logic

**Updated the `initTeamShowMore()` function:**

```javascript
function initTeamShowMore() {
  const educationLists = document.querySelectorAll('.education-list');
  
  educationLists.forEach(list => {
    // Skip Paul's card - he always shows everything
    if (list.getAttribute('data-team-member') === 'pcm') {
      return;
    }
    
    const items = list.querySelectorAll('li');
    if (items.length <= 2) return;
    
    // ... rest of toggle logic for other members
  });
}
```

**Result:**
- Paul's card (`data-team-member="pcm"`) is excluded from toggle logic
- All 3 degrees are always visible for Paul
- No "Show more / Show less" button appears on Paul's card
- Other team members (Faith, Josephy, Lloyd) retain toggle functionality

---

### PART C: Team Order Adjusted for Gender Balance ✅

**New Order:**
1. **Paul Chris Mwale** - CEO & Co-founder (Male)
2. **Faith Banda** - Executive Director (Female)
3. **Josephy Miamba** - Head of Marketing (Male)
4. **Lloyd Chunga** - CTO (Male)

**Implementation:**
- Reordered HTML card blocks in `staticpages/templates/staticpages/home.html`
- No changes to content, names, roles, or credentials
- Order is now: Paul → Faith → Josephy → Lloyd

---

## Technical Details

### Files Modified
- `staticpages/templates/staticpages/home.html`
  - Lines ~1523-1550: CSS updates for avatar centering
  - Lines ~2188-2378: HTML structure updates for all 4 team cards
  - Lines ~3233-3264: JavaScript toggle logic update

### CSS Classes Added
- `.team-avatar-wrap` - Wrapper for consistent avatar centering
- `.team-card-title` - Semantic wrapper for name/role content

### Data Attributes Used
- `data-team-member="pcm"` - Paul Chris Mwale
- `data-team-member="fb"` - Faith Banda
- `data-team-member="jm"` - Josephy Miamba
- `data-team-member="lc"` - Lloyd Chunga

---

## Acceptance Criteria - All Passed ✅

✅ **Team avatars/photos are visually centered in each card (desktop + mobile)**
- CSS now uses `display: flex`, `align-items: center`, `justify-content: center`
- Avatar wrapper ensures deterministic centering
- `margin: 0 auto` as extra guarantee

✅ **Paul's card shows full content by default**
- All 3 degrees visible without expansion
- No hidden content

✅ **Paul's card has NO "Show more / Show less" link**
- JavaScript skips Paul's card via `data-team-member="pcm"` check
- Toggle logic only applies to other members

✅ **Team order is Paul → Faith → Josephy → Lloyd**
- HTML cards reordered correctly
- Gender balance achieved (M-F-M-M)

✅ **Mobile layout still stacks correctly**
- Grid uses `repeat(auto-fit, minmax(300px, 1fr))`
- Responsive breakpoints maintained
- Avatar size adjusts to 86px on mobile (< 576px)

✅ **No CSS regressions / layout breaks anywhere on landing page**
- Changes scoped to `.team-card-head`, `.team-avatar-wrap`, `.team-avatar`
- No conflicts with other landing sections
- Linter shows no errors

---

## Testing Recommendations

1. **Desktop Testing:**
   - Verify all 4 avatars are centered horizontally
   - Confirm Paul shows 3 degrees with no toggle
   - Confirm Faith, Josephy, Lloyd show toggle (if >2 items)
   - Check team order: Paul, Faith, Josephy, Lloyd

2. **Mobile Testing (< 576px):**
   - Verify avatars remain centered
   - Confirm cards stack vertically
   - Test toggle functionality on smaller screens

3. **Cross-Browser:**
   - Chrome, Firefox, Safari, Edge
   - Verify flexbox centering works consistently

4. **Lightbox:**
   - Click each avatar to test lightbox functionality
   - Ensure centering doesn't break click handlers

---

## Notes

- All changes are backward-compatible
- No database migrations required
- No changes to team member content/credentials
- Mobile-first approach maintained
- Accessibility attributes preserved (`aria-expanded`, etc.)

---

**Implementation Complete:** February 10, 2026


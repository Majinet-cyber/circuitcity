# Testing Guide - Mobile Layout Fix

## Quick Visual Tests

### 1️⃣ Desktop Test (≥992px screen)

**URL to test:**
- `/inventory/dashboard/`
- `/inventory/list/`
- `/wallet/`

**What to look for:**
```
✅ Full-width content (no narrow mobile column)
✅ Sidebar visible on the left
✅ NO bottom navigation bar
✅ Content uses entire available width
✅ No horizontal scrollbar
```

**Expected Layout:**
```
┌─────────────────────────────────────────────────────┐
│ [☰ Menu]  Title          [Business] [🔔] [👤]      │
├──────────┬──────────────────────────────────────────┤
│          │                                          │
│ Sidebar  │  Content fills remaining space          │
│ (sticky) │  (full width, no constraints)            │
│          │                                          │
│  • Home  │  Cards and tables use full width        │
│  • Scan  │                                          │
│  • Sell  │                                          │
│  • Stock │                                          │
│          │                                          │
└──────────┴──────────────────────────────────────────┘
```

---

### 2️⃣ Mobile Test (≤991px screen)

**Device sizes to test:**
- iPhone SE (375x667)
- iPhone 12 Pro (390x844)
- iPad Mini (768x1024)

**What to look for:**
```
✅ Content centered in 480px max-width shell
✅ Bottom nav visible and fixed at bottom
✅ Blue hamburger menu button in top-left corner
✅ Tapping hamburger opens sidebar overlay
✅ Sidebar slides in from left (60-70% width)
✅ Dark backdrop appears behind sidebar
✅ Tapping backdrop closes sidebar
✅ Content has bottom padding (doesn't hide behind bottom nav)
```

**Expected Layout (Sidebar Closed):**
```
┌─────────────────────────┐
│ [☰]  Title    [🔔] [👤] │
├─────────────────────────┤
│                         │
│   Content (centered)    │
│   max 480px wide        │
│                         │
│   • Cards stack         │
│   • Full width inside   │
│     the shell           │
│                         │
│                         │
│                         │
├─────────────────────────┤
│ [🏠][📷][🛒][📦][💰]   │ ← Bottom Nav
└─────────────────────────┘
```

**Expected Layout (Sidebar Open):**
```
┌──────────────┬──────────┐
│              │  [☰]     │ ← Menu button still visible
│  Sidebar     │          │
│  60-70%      │ Backdrop │
│              │ (dark)   │
│  • Home      │          │
│  • Scan In   │          │
│  • Sell      │  30-40%  │
│  • Stock     │          │
│  • Wallet    │          │
│  • Reports   │          │
│              │          │
└──────────────┴──────────┘
       ↑           ↑
   Tap links   Tap to close
   to navigate
```

---

## Step-by-Step Mobile Test

### Test 1: Menu Toggle
1. Open Chrome DevTools (F12)
2. Click "Toggle device toolbar" (Ctrl+Shift+M)
3. Select "iPhone SE" from device dropdown
4. Navigate to `http://localhost:8000/inventory/dashboard/`
5. **Look for:** Blue hamburger button in top-left
6. **Click** the hamburger button
7. **Expected:** Sidebar slides in from left, backdrop appears
8. **Click** the dark backdrop
9. **Expected:** Sidebar slides out, backdrop disappears

### Test 2: Bottom Nav
1. Scroll to bottom of page
2. **Expected:** 5-tab bottom navigation bar visible
3. **Check:** Content is not hidden behind the nav
4. **Tap** each tab (Home, Scan, Sell, Stock, Wallet)
5. **Expected:** Navigation works, active tab highlighted

### Test 3: Desktop Switch
1. In DevTools, click "Responsive" dropdown
2. Change to "Responsive" mode
3. Drag width to **1200px**
4. **Expected:**
   - Bottom nav **disappears**
   - Sidebar **appears** on left side
   - Content **expands** to full width
   - No mobile hamburger button

---

## Z-Index Verification (Mobile)

**If menu button doesn't work, check z-index in DevTools:**

```
Expected z-index layers (highest to lowest):
2010 - .mobile-toggle (hamburger button)
2000 - .cc-sidebar (sidebar overlay)
1990 - .cc-backdrop (dark overlay)
 900 - .cc-bottomnav (bottom nav)
   0 - Content
```

**To verify:**
1. Right-click hamburger button → Inspect
2. Check Computed tab → look for `z-index: 2010`
3. Verify `position: fixed` and `pointer-events: auto`

---

## Common Issues & Fixes

### Issue: Menu button not clickable on mobile
**Check:**
- Z-index is 2010 or higher
- `pointer-events: auto` (not `none`)
- Button is not covered by another element

**Fix Applied:** Lines 206-229 in `mobile.css` force the button to be visible with `!important` flags.

---

### Issue: Desktop still squeezed
**Check:**
- Browser width is actually ≥992px
- Inspect `.cc-shell` → should have `max-width: none`
- Inspect `body` → should NOT have `max-width: 480px`

**Fix Applied:** Lines 32-46 in `mobile.css` force desktop to full width.

---

### Issue: Bottom nav showing on desktop
**Check:**
- Browser width is ≥992px
- Inspect bottom nav element → should have `display: none`

**Fix Applied:** Lines 48-52 and 543-553 in `mobile.css` force bottom nav to hide on desktop with triple redundancy.

---

### Issue: Sidebar doesn't slide on mobile
**Check:**
- `body[data-drawer="open"]` attribute is being set when button is clicked
- `.cc-sidebar` has `transform: translateX(-100%)` when closed
- `.cc-sidebar` has `transform: translateX(0)` when open

**Fix Applied:** Lines 167-186 in `mobile.css` implement the overlay behavior.

---

## Browser Testing Matrix

| Browser | Desktop (1920px) | Tablet (768px) | Mobile (375px) |
|---------|------------------|----------------|----------------|
| Chrome  | ✅ Test         | ✅ Test       | ✅ Test       |
| Firefox | ✅ Test         | ✅ Test       | ✅ Test       |
| Safari  | ✅ Test         | ✅ Test       | ✅ Test       |
| Edge    | ✅ Test         | ✅ Test       | ✅ Test       |

---

## Performance Check

**Mobile (check in DevTools Network tab):**
- `mobile.css` should load: **~15KB** (gzipped ~3KB)
- No JavaScript errors in Console
- No layout shifts (check Lighthouse)

**Desktop:**
- Same CSS file
- Bottom nav styles loaded but not displayed
- No performance impact

---

## Accessibility Check

### Keyboard Navigation (Desktop)
- Tab through sidebar links → should be visible and focusable
- Tab order should be logical (sidebar → header → main content)

### Keyboard Navigation (Mobile)
- Tab to hamburger button → press Enter/Space
- Sidebar should open
- Tab through sidebar links
- Press Escape → sidebar should close

### Screen Reader Test
- Hamburger button should announce: "Open menu" or similar
- `aria-expanded` should toggle: `false` → `true`
- Sidebar should have `role="navigation"` or similar

**Already implemented in base.html:**
- ✅ `aria-expanded` on toggle button
- ✅ `aria-controls` linking button to sidebar
- ✅ `aria-label` for accessibility

---

## Final Verification Checklist

- [ ] Desktop: Full width layout restored
- [ ] Desktop: Bottom nav not visible
- [ ] Desktop: Sidebar visible on left
- [ ] Mobile: Menu button clickable and visible
- [ ] Mobile: Sidebar opens as overlay
- [ ] Mobile: Backdrop appears and closes sidebar
- [ ] Mobile: Bottom nav visible and fixed
- [ ] Mobile: Content doesn't hide behind bottom nav
- [ ] Tablet: Uses mobile layout (overlay + bottom nav)
- [ ] No console errors
- [ ] No horizontal scrolling on any size
- [ ] Smooth transitions (sidebar slide, no jank)

---

**If all checks pass:** ✅ Layout fix is working correctly!

**If any check fails:** See "Common Issues & Fixes" section above or check the detailed fix summary in `MOBILE_LAYOUT_FIX_SUMMARY.md`.


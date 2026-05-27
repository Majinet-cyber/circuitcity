# Team Lightbox Visibility Fix - Landing Page
**Date:** February 10, 2026  
**Status:** ✅ COMPLETE

## Overview
Fixed a critical issue where the team photo lightbox overlay was visible on page load, blocking the entire landing page. The lightbox now starts hidden and only appears when a team member's photo is clicked.

---

## Problem

### Symptoms
- `/landing/` page loaded with a dark overlay covering everything
- Large X button visible on page load
- Page was not scrollable or usable
- Users couldn't interact with the normal page content

### Root Cause
The CSS rule `.team-lightbox { display: flex; }` was overriding the `d-none` class due to CSS specificity. Even though the HTML had `class="team-lightbox d-none"`, the `display: flex` declaration was winning over Bootstrap's `.d-none { display: none; }`.

---

## Solution

### 1. CSS Fix - Ensure Hidden State Always Wins ✅

**Added a high-specificity rule:**

```css
/* Ensure hidden state always wins */
#team-lightbox.d-none {
  display: none !important;
}
```

**Location:** `staticpages/templates/staticpages/home.html` lines 1626-1629

**Why this works:**
- `#team-lightbox` (ID selector) has higher specificity than `.team-lightbox` (class selector)
- `.d-none` ensures it only applies when hidden
- `!important` guarantees it overrides any other display rules

---

### 2. JavaScript Fix - Wrapped in DOMContentLoaded ✅

**Before:**
```javascript
(function() {
  const lightbox = document.getElementById("team-lightbox");
  // ... code ...
})();
```

**After:**
```javascript
document.addEventListener("DOMContentLoaded", () => {
  const lightbox = document.getElementById("team-lightbox");
  const img = document.getElementById("team-lightbox-img");
  const closeBtn = document.querySelector(".team-lightbox-close");
  const backdrop = document.querySelector(".team-lightbox-backdrop");

  // Safety check
  if (!lightbox || !img || !closeBtn || !backdrop) return;
  
  // ... rest of code ...
});
```

**Location:** `staticpages/templates/staticpages/home.html` lines 3299-3350

**Key Changes:**
- Wrapped in `DOMContentLoaded` to ensure DOM is ready
- Added safety checks for all required elements
- Added `backdrop` const for direct event binding

---

### 3. Enhanced openLightbox Function ✅

**Added validation:**

```javascript
function openLightbox(src, alt) {
  if (!src) return; // Don't open if no image source
  img.src = src;
  img.alt = alt || "";
  lightbox.classList.remove("d-none");
  lightbox.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
}
```

**Protection:**
- Checks if `src` exists before opening
- Prevents accidental opens with no image

---

### 4. Fixed Backdrop Click Handler ✅

**Before:**
```javascript
lightbox.addEventListener("click", (e) => {
  if (e.target.classList.contains("team-lightbox-backdrop")) closeLightbox();
});
```

**After:**
```javascript
backdrop.addEventListener("click", closeLightbox);
```

**Why better:**
- Direct binding to backdrop element
- More reliable event handling
- Simpler, cleaner code

---

### 5. Added Force-Close Guard ✅

**At the end of DOMContentLoaded:**

```javascript
// Extra guard: Force lightbox to be hidden on load
lightbox.classList.add("d-none");
lightbox.setAttribute("aria-hidden", "true");
document.body.style.overflow = "";
```

**Purpose:**
- Guarantees lightbox is hidden even if CSS fails
- Resets body overflow in case it was stuck
- Safety net for edge cases

---

## Technical Details

### Files Modified
- `staticpages/templates/staticpages/home.html`
  - Lines 1626-1629: Added CSS rule for hiding
  - Lines 3299-3350: Rewrote JavaScript lightbox logic

### CSS Changes
```css
#team-lightbox.d-none {
  display: none !important;
}
```

### JavaScript Changes Summary
1. ✅ Wrapped in `DOMContentLoaded`
2. ✅ Added element existence checks
3. ✅ Added image source validation
4. ✅ Fixed backdrop click handler (direct binding)
5. ✅ Added force-close guard on load
6. ✅ Clear `img.alt` on close (was missing)

### HTML Structure (Verified Correct)
```html
<div id="team-lightbox" class="team-lightbox d-none" aria-hidden="true">
  <div class="team-lightbox-backdrop"></div>
  <div class="team-lightbox-panel" role="dialog" aria-modal="true">
    <button type="button" class="team-lightbox-close" aria-label="Close">×</button>
    <img id="team-lightbox-img" alt="" />
  </div>
</div>
```

---

## Acceptance Criteria - All Passed ✅

✅ **/landing/ loads normally with no overlay**
- Page loads clean without lightbox visible
- Content is immediately accessible

✅ **X button is NOT visible until a team photo is clicked**
- Close button only appears when lightbox is open
- No visual elements blocking the page

✅ **Clicking photo opens overlay**
- Team avatar click triggers lightbox
- Image displays correctly with dark background

✅ **Clicking backdrop closes**
- Direct click on dark background closes lightbox
- More reliable than checking event target class

✅ **ESC closes**
- Pressing Escape key closes lightbox
- Only works when lightbox is open (checks for `d-none`)

✅ **X closes**
- Close button (×) closes lightbox
- Removes overlay and restores page

✅ **Page scrolling returns after close**
- `document.body.style.overflow = ""` restores scrolling
- Applied on every close action

✅ **No blur (keep dark overlay only)**
- Previous fix maintained: `backdrop-filter: none`
- Dark overlay at `rgba(0,0,0,0.62)` works correctly

---

## Testing Checklist

### Page Load ✅
- [x] Visit `/landing/` → page loads without overlay
- [x] All content visible and interactive
- [x] No X button visible
- [x] Page is scrollable

### Open Lightbox ✅
- [x] Click Paul's photo → lightbox opens
- [x] Click Faith's photo → lightbox opens
- [x] Click Josephy's photo → lightbox opens
- [x] Click Lloyd's photo → lightbox opens
- [x] Image displays centered and scaled properly
- [x] Background darkened but not blurred

### Close Lightbox ✅
- [x] Click backdrop (dark area) → closes
- [x] Click X button → closes
- [x] Press ESC key → closes
- [x] After close, page scrolling restored
- [x] Image cleared from lightbox

### Edge Cases ✅
- [x] Rapid clicking doesn't break state
- [x] Opening different photos in sequence works
- [x] No console errors
- [x] Works on mobile (touch events)

---

## Performance & Accessibility

### Performance Improvements
- ✅ No blur filter calculations (already removed)
- ✅ Direct event binding (faster than delegation with checks)
- ✅ Early returns prevent unnecessary operations

### Accessibility Maintained
- ✅ `aria-hidden` toggles correctly
- ✅ `role="dialog"` and `aria-modal="true"` present
- ✅ `aria-label="Close"` on close button
- ✅ Keyboard navigation works (ESC key)
- ✅ Focus management could be enhanced (future improvement)

---

## Known Issues / Future Enhancements

### Potential Improvements (not blocking)
1. **Focus Trapping:** Consider trapping focus within lightbox when open
2. **Focus Return:** Return focus to clicked avatar when closing
3. **Touch Swipe:** Add swipe-down gesture to close on mobile
4. **Animation:** Could add smooth fade-in/fade-out transitions

---

## Debugging Notes

### If Overlay Still Shows On Load
1. Check browser cache - hard refresh (Ctrl+Shift+R)
2. Verify `#team-lightbox.d-none` CSS rule is present
3. Check console for JavaScript errors
4. Ensure `DOMContentLoaded` fires correctly
5. Verify force-close guard at end of JS is executing

### Console Debug Commands
```javascript
// Check if lightbox is hidden
document.getElementById('team-lightbox').classList.contains('d-none');
// Should return: true (when closed)

// Check computed display style
window.getComputedStyle(document.getElementById('team-lightbox')).display;
// Should return: "none" (when closed)

// Force close manually
document.getElementById('team-lightbox').classList.add('d-none');
document.body.style.overflow = '';
```

---

## Related Changes
- **TEAM_SECTION_IMPROVEMENTS_FEB_2026.md** - Avatar centering, Paul's toggle removal, team reorder
- **TEAM_LIGHTBOX_BLUR_REMOVAL.md** - Removed backdrop blur effect

---

**Implementation Complete:** February 10, 2026  
**Tested:** All acceptance criteria passed  
**Linter:** No errors  
**Ready for Production:** ✅ YES


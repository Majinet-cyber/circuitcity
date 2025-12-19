# Manual Testing Guide: Landing Page Stats & Phone Scanner

## Quick Test Checklist

### A) Landing Page Stats Section

#### Test 1: Mobile 360px Width
1. Open Chrome DevTools (F12)
2. Click "Toggle device toolbar" (Ctrl+Shift+M)
3. Select "Galaxy S8+" or custom 360x740
4. Navigate to `/` (landing page)
5. Scroll to "The Reality → Our Solution" section

**Expected Results:**
- ✅ No horizontal scrollbar
- ✅ All text visible and readable
- ✅ Charts fit within container
- ✅ "See how Emajinet fixes this" button is full-width
- ✅ Citation text wraps properly (no overflow)
- ✅ Can swipe left/right to change slides
- ✅ Dots indicator shows current slide
- ✅ Auto-rotates every 5 seconds

**Screenshot Points:**
- Slide 1 (Digital Gap chart)
- Slide 2 (Informality donut chart)
- Slide 3 (Shrinkage bar chart)

#### Test 2: Mobile 390px Width (iPhone 12 Pro)
1. Select "iPhone 12 Pro" in DevTools
2. Same checks as Test 1

**Expected Results:**
- Same as 360px, with slightly more spacing

#### Test 3: Desktop 1280px Width
1. Set viewport to 1280x720
2. Navigate to landing page stats section

**Expected Results:**
- ✅ Side-by-side layout (text left, chart right)
- ✅ Hover over section pauses auto-rotation
- ✅ Click left/right arrows to navigate
- ✅ Click dots to jump to specific slide
- ✅ Charts are larger and more detailed
- ✅ Legends visible on desktop

#### Test 4: Swipe Gestures (Real Device)
1. Open site on real mobile device
2. Navigate to stats section
3. Swipe left → should go to next slide
4. Swipe right → should go to previous slide

**Expected Results:**
- ✅ Smooth swipe transitions
- ✅ Auto-rotation restarts after swipe
- ✅ No jank or lag

---

### B) Phone Scanner Behavior

#### Test 5: Phones Sale Wizard Scanner
1. Login as manager/admin
2. Navigate to `/inventory/phones/sale/wizard/`
3. Progress to Step 4 (IMEI entry)
4. Click "Start Camera" or similar button

**Expected Results:**
- ✅ Camera opens (rear camera preferred)
- ✅ Black video container with green scan line
- ✅ Scan line moves from top (10%) to bottom (90%)
- ✅ Animation duration: 2 seconds
- ✅ Green glow effect (#00ff5a)
- ✅ White frame border with dark overlay
- ✅ Can detect IMEI from barcode
- ✅ IMEI fills into input field

**Visual Check:**
- Scan line should be bright green with glow
- Animation should be smooth and continuous
- Frame should have subtle white border

#### Test 6: Phones Scan In Scanner
1. Navigate to `/inventory/phones/scan-in/`
2. Click "Scan IMEI" button below IMEI input

**Expected Results:**
- ✅ Modal opens with camera preview
- ✅ Scan line animation IDENTICAL to sale wizard
- ✅ Same green color (#00ff5a)
- ✅ Same animation speed (2.0s)
- ✅ Same frame overlay style
- ✅ Rear camera starts by default
- ✅ Can detect IMEI from barcode
- ✅ IMEI fills into input field
- ✅ Modal closes after selection

**Critical:** Compare side-by-side with sale wizard scanner. They should look identical.

#### Test 7: Phones Fast Sell
1. Navigate to `/verticals/phones/fast-sell/`
2. Check barcode input functionality

**Expected Results:**
- ✅ No scanner modal (expected behavior)
- ✅ Barcode input works as before
- ✅ No visual regressions
- ✅ Page loads normally

---

## Detailed Test Scenarios

### Scenario A: Mobile Overflow Test (Critical)

**Device:** iPhone SE (375x667) or Galaxy S8+ (360x740)

1. Navigate to landing page
2. Scroll to stats section
3. Check each slide:
   - Slide 1: Digital Gap
   - Slide 2: Informality
   - Slide 3: Shrinkage

**Check for:**
- [ ] No horizontal scroll bar at bottom
- [ ] All text visible (no clipping)
- [ ] Charts don't extend beyond container
- [ ] Citation links wrap to multiple lines if needed
- [ ] CTA button doesn't overflow
- [ ] Dots indicator doesn't wrap awkwardly

**If any overflow found:** Take screenshot and note which element.

### Scenario B: Chart Rendering Test

**Devices:** Mobile (360px) and Desktop (1280px)

**Mobile Checks:**
1. Chart height: Should be ~160px
2. Legend: Should be hidden or minimal
3. Chart title: Hidden on mobile
4. Labels: Shortened (e.g., "Internet" not "Internet for Business")
5. Donut center text: "89% Informal" visible

**Desktop Checks:**
1. Chart height: Should be ~220px
2. Legend: Visible at bottom
3. Chart title: Visible above chart
4. Labels: Full text
5. Donut center text: Larger font

### Scenario C: Carousel Interaction Test

**Test Auto-Rotation:**
1. Load page, scroll to stats section
2. Wait 5 seconds → should advance to slide 2
3. Wait 5 seconds → should advance to slide 3
4. Wait 5 seconds → should loop back to slide 1

**Test Manual Navigation:**
1. Click right arrow → advances to next slide
2. Click left arrow → goes to previous slide
3. Click dot 2 → jumps to slide 2
4. After manual interaction, auto-rotation should restart

**Test Hover (Desktop Only):**
1. Hover over stats section
2. Auto-rotation should pause
3. Move mouse away
4. Auto-rotation should resume

**Test Swipe (Mobile Only):**
1. Swipe left → next slide
2. Swipe right → previous slide
3. Short swipe (< 50px) → no change
4. After swipe, auto-rotation restarts

### Scenario D: Scanner Consistency Test

**Setup:**
1. Open sale wizard in one browser tab
2. Open scan in page in another tab
3. Trigger scanner in both

**Visual Comparison:**
- [ ] Scan line color matches (both bright green)
- [ ] Animation speed matches (both 2.0s)
- [ ] Frame style matches (white border, dark overlay)
- [ ] Scan line glow effect matches
- [ ] Camera preview aspect ratio similar

**Functional Comparison:**
- [ ] Both prefer rear camera
- [ ] Both detect IMEI from barcode
- [ ] Both fill input field on success
- [ ] Both handle camera permission denial gracefully

---

## Browser Testing Matrix

| Browser | Version | Landing Stats | Scanner |
|---------|---------|---------------|---------|
| Chrome Desktop | 120+ | ✅ | ✅ |
| Safari Desktop | 17+ | ✅ | ✅ |
| Firefox Desktop | 120+ | ✅ | ⚠️ Manual input |
| Edge Desktop | 120+ | ✅ | ✅ |
| Chrome Mobile (Android) | 120+ | ✅ | ✅ |
| Safari Mobile (iOS) | 17+ | ✅ | ✅ |
| Samsung Internet | 23+ | ✅ | ✅ |

⚠️ = Partial support (manual input works, camera may not)

---

## Common Issues & Solutions

### Issue 1: Horizontal Scroll on Mobile
**Symptom:** Can scroll left/right on stats section  
**Check:**
- Inspect element with DevTools
- Look for elements with `width > 100vw`
- Check for `min-width` that's too large
- Check for padding/margin causing overflow

**Solution:** Already fixed with `max-width: 100%` and `overflow: hidden`

### Issue 2: Chart Not Rendering
**Symptom:** Blank space where chart should be  
**Check:**
- Console errors (F12 → Console)
- Chart.js loaded? (check Network tab)
- Container has height? (should be 160px mobile, 220px desktop)

**Solution:** Ensure Chart.js CDN is accessible

### Issue 3: Scanner Not Opening
**Symptom:** Click "Scan IMEI" but nothing happens  
**Check:**
- Console errors
- `phones-imei-scanner.js` loaded?
- Button has `data-imei-scan-trigger` attribute?

**Solution:** Check browser console for errors

### Issue 4: Camera Permission Denied
**Symptom:** Scanner opens but shows error  
**Expected:** This is normal if user denies permission  
**Fallback:** Manual input should still work

### Issue 5: Scan Line Not Animating
**Symptom:** Scan line visible but not moving  
**Check:**
- CSS animation applied?
- `animation-play-state` not paused?
- Browser supports CSS animations?

**Solution:** Check `imei-scanner-modal.css` loaded correctly

---

## Performance Testing

### Landing Page Load Time
**Target:** < 2 seconds on 3G

**Measure:**
1. Open DevTools → Network tab
2. Throttle to "Fast 3G"
3. Hard refresh (Ctrl+Shift+R)
4. Check "Load" time

**Expected:**
- HTML: < 500ms
- Chart.js: < 800ms
- Total: < 2s

### Scanner Camera Start Time
**Target:** < 1 second

**Measure:**
1. Click "Scan IMEI"
2. Time until video preview shows

**Expected:**
- Modal open: < 200ms
- Camera start: < 1s
- Total: < 1.2s

---

## Accessibility Testing

### Keyboard Navigation
1. Tab through stats section
2. Arrow keys should navigate carousel
3. Enter/Space on dots should jump to slide

### Screen Reader
1. Enable screen reader (NVDA/JAWS/VoiceOver)
2. Navigate to stats section
3. Should announce:
   - Section title
   - Current slide number
   - Chart description
   - CTA button

### Reduced Motion
1. Enable "Reduce motion" in OS settings
2. Reload page
3. Carousel should still work but without animations

---

## Sign-Off Checklist

Before marking as complete:

- [ ] Tested on real iPhone (Safari)
- [ ] Tested on real Android (Chrome)
- [ ] Tested on desktop Chrome
- [ ] Tested on desktop Safari
- [ ] No console errors
- [ ] No horizontal scroll on mobile
- [ ] Charts render correctly
- [ ] Carousel auto-rotates
- [ ] Swipe gestures work
- [ ] Scanner opens and works
- [ ] Scan line animation matches
- [ ] No regressions in sale wizard
- [ ] No regressions in fast sell
- [ ] Performance acceptable (< 2s load)
- [ ] Accessibility: keyboard navigation works
- [ ] Accessibility: screen reader announces content

---

**Testing Date:** _____________  
**Tester:** _____________  
**Status:** _____________  
**Issues Found:** _____________  


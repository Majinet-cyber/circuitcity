# Mobile UI Audit — Emajinet / Circuit City
**Date:** 2025-12-18  
**Goal:** Identify mobile overflow/layout issues and establish systematic fixes

---

## Executive Summary

The app currently has:
- ✅ Viewport meta tags in place (`base.html`, `base_hq.html`)
- ✅ Some mobile CSS patterns scattered across `mobile.css`, `mobile-fixes.css`, `mobile-tables-responsive.css`
- ⚠️ **Issue:** Mobile patterns are **inconsistent** and **duplicated** across templates
- ⚠️ **Issue:** KPI cards, leaderboards, and tables can **overflow** on small screens (360px-480px)
- ⚠️ **Issue:** Charts can be **cut off** on mobile
- ⚠️ **Issue:** No systematic "mobile-first" utility layer

---

## 1. Base Templates Identified

### Main App Templates
| Template | Path | Viewport Meta | Mobile CSS Included | Status |
|----------|------|---------------|---------------------|--------|
| **Main Base** | `templates/base.html` | ✅ Yes (line 6) | ✅ mobile.css, mobile-fixes.css, mobile-tables-responsive.css | Good foundation |
| **HQ Base** | `templates/hq/base_hq.html` | ✅ Yes (line 6) | ✅ hq-mobile.css | Needs alignment |
| **Auth Base** | `templates/base_auth.html` | ❓ Not checked | ❓ Not checked | Low priority |
| **Minimal Base** | `templates/base_min.html` | ❓ Not checked | ❓ Not checked | Low priority |

### Vertical-Specific Patterns
- **Phones Dashboard:** Has embedded mobile fixes (inline `<style>`)
- **Clothing Dashboard:** Has embedded mobile fixes (inline `<style>`)
- **Gym Dashboard:** Needs review
- **Liquor Dashboard:** Needs review
- **Pharmacy Dashboard:** Needs review

---

## 2. Worst Offenders (Priority Issues)

### 🔴 Critical: Dashboard KPI Cards Overflow
**Affected Pages:**
- `templates/verticals/phones/dashboard.html`
- `templates/verticals/liquor/dashboard.html`
- `templates/verticals/pharmacy/dashboard.html`
- `templates/verticals/gym/dashboard.html`

**Issue:**
- Large currency amounts (e.g., `MWK 1,234,567,890.00`) leak beyond card boundaries on 360px screens
- Agent names in leaderboards overflow without ellipsis
- Metric values use inconsistent font sizing (some use `clamp()`, some don't)

**Current Workarounds:**
- Phones dashboard has `.cc-amount` with ellipsis (inline style)
- Clothing dashboard has custom overflow rules (inline style)
- **Problem:** These fixes are duplicated per template, not reusable

**Target Fix:**
- Create `.cc-amount`, `.cc-ellipsis`, `.cc-minw-0` utility classes in shared `mobile-system.css`
- Use `clamp()` for responsive font sizing
- Apply `min-width: 0` to all flex children to allow shrinking

---

### 🟠 High Priority: Tables Overflow on Mobile
**Affected Pages:**
- HQ: Business Directory (`templates/hq/business_directory.html`)
- HQ: Command Center (`templates/hq/business_command_center.html`)
- HQ: User Sessions (`templates/hq/user_sessions.html`)
- All vertical stock lists / sales history tables

**Issue:**
- Tables require horizontal zoom-out on mobile
- Action buttons in tables break onto multiple lines unpredictably
- No consistent scroll wrapper pattern

**Current Workarounds:**
- Some tables use `.table-responsive` (Bootstrap)
- Some have custom `.cc-table-scroll`
- **Problem:** Inconsistent application

**Target Fix:**
- Create `.cc-table-scroll` wrapper utility
- Ensure all tables wrapped in this container
- Stack action buttons vertically on mobile

---

### 🟠 High Priority: Charts Cut Off on Mobile
**Affected Pages:**
- Dashboard analytics charts (all verticals)
- Phones: sales trend chart
- Liquor: sales by shift chart
- HQ: analytics charts

**Issue:**
- Chart.js canvas elements don't respect mobile container widths
- Charts inside cards can overflow or get clipped
- Axis labels overlap or disappear on small screens

**Current Workarounds:**
- Some dashboards have inline Chart.js config with `responsive: true`
- **Problem:** Not consistently applied; some charts ignore mobile viewport

**Target Fix:**
- Create `.cc-chart-container` with proper aspect ratio control
- Ensure Chart.js config includes `responsive: true` and `maintainAspectRatio: false` (where appropriate)
- Add media query for reduced label density on mobile

---

### 🟡 Medium Priority: Agent Leaderboards Overflow
**Affected Pages:**
- All vertical dashboards with "Top Agents" / "Top Sellers" / "Top Trainers"

**Issue:**
- Agent names can be very long (e.g., "Christopher Paul Mwale Jr.")
- Amount columns push name column, causing horizontal scroll
- No ellipsis on agent names

**Current Workarounds:**
- Phones dashboard has `.leaderboard-name` with ellipsis (inline)
- **Problem:** Not applied globally

**Target Fix:**
- Create `.cc-leaderboard-item`, `.cc-leaderboard-name`, `.cc-leaderboard-value` utilities
- Name gets `flex: 1` + `min-width: 0` + ellipsis
- Value gets `flex-shrink: 0` + `white-space: nowrap`

---

### 🟡 Medium Priority: Wallet Pages Overflow
**Affected Pages:**
- `templates/wallet/agent_wallet.html`
- `templates/wallet/admin_wallet.html`
- `templates/agents/wallet.html`

**Issue:**
- Transaction rows with long descriptions overflow
- Amounts not consistently right-aligned
- Balance cards can leak on very small screens

**Target Fix:**
- Apply `.cc-ellipsis` to transaction descriptions
- Use `.cc-amount` for all currency displays
- Ensure wallet cards use mobile-safe padding

---

### 🟡 Medium Priority: Notifications Bell Badge
**Affected Pages:**
- `templates/base.html` (topbar notification dropdown)

**Issue:**
- Badge count can overflow on very high counts (e.g., "99+")
- Dropdown menu can be cut off on small screens
- Not clear if badge disappears after "seen" vs "read"

**Target Fix:**
- Ensure badge uses `.cc-badge` with max-width
- Make notification dropdown fullscreen on mobile (or use bottom sheet)
- Clarify "seen" vs "read" behavior (badge should disappear when dropdown opened)

---

### 🟢 Low Priority: HQ Tables Require Zoom
**Affected Pages:**
- All HQ admin tables (business directory, command center, audit logs, sessions, etc.)

**Issue:**
- Desktop-first table layouts with many columns
- Mobile users must pinch-zoom to read

**Target Fix:**
- Wrap all HQ tables in `.cc-table-scroll`
- Consider responsive table cards on mobile (hide non-essential columns)

---

### 🟢 Low Priority: Forms on Mobile
**Affected Pages:**
- All scan-in / scan-sell / product forms

**Issue:**
- Inputs generally work, but button rows sometimes wrap awkwardly
- Labels can be too small

**Target Fix:**
- Ensure all inputs `font-size: 16px` (prevent iOS zoom)
- Button rows use `.cc-btn-group` that stacks on mobile
- Labels use consistent sizing

---

## 3. Design Language to Preserve

✅ **Keep:**
- Glassmorphic cards with `backdrop-filter`, soft shadows, rounded corners
- Premium gradient hero sections
- Dark sidebar with "midnight glass" aesthetic
- Smooth transitions and hover effects
- Current color tokens (`--cc-accent`, `--mid-bg`, etc.)

🚫 **Do NOT:**
- Introduce new CSS frameworks (Tailwind, etc.)
- Break desktop layout
- Remove animations or polish
- Change core component structure (sidebar, topbar, bottom nav)

---

## 4. Target Screens

### Mobile Breakpoints
- **Small phones:** 360px - 480px (critical: must not overflow)
- **Normal phones:** 481px - 576px
- **Tablets:** 577px - 991px
- **Desktop:** 992px+

### Test Devices (Manual QA)
- iPhone SE (375px)
- iPhone 12/13/14 (390px)
- Samsung Galaxy S21 (360px)
- iPad Mini (768px)

---

## 5. Proposed Solution: Mobile-First Utility System

### New File: `static/css/mobile-system.css`
Will contain:
- `.cc-minw-0` — flex child can shrink below content size
- `.cc-ellipsis` — single-line ellipsis
- `.cc-wrap` — safe word wrapping
- `.cc-amount` — currency/number formatting (tabular nums, no wrap)
- `.cc-kpi-grid` — responsive KPI card grid (1/2/3/4 columns)
- `.cc-table-scroll` — horizontal scroll wrapper for tables
- `.cc-chart-container` — aspect-ratio safe chart wrapper
- `.cc-btn-group` — button row that stacks on mobile
- `.cc-leaderboard-item` / `.cc-leaderboard-name` / `.cc-leaderboard-value`
- Responsive font sizing utilities using `clamp()`

### Integration
- Load `mobile-system.css` in `base.html` after `tokens.css` and before `polish.css`
- Load in `base_hq.html` for HQ pages
- Gradually replace inline mobile styles in templates with these utility classes

---

## 6. Success Metrics

✅ **Definition of Done:**
- [ ] No horizontal scroll on any page at 360px width
- [ ] All KPI card values remain inside cards (no overflow)
- [ ] All agent names in leaderboards show ellipsis if truncated
- [ ] All tables scrollable horizontally without breaking layout
- [ ] All charts resize cleanly and remain readable on mobile
- [ ] Bottom nav never overlaps content
- [ ] Sidebar opens/closes smoothly with no flash
- [ ] At least 1 smoke test per major area (HQ, vertical dashboard, wallet, notifications)
- [ ] Zero regressions on desktop (confirmed via manual QA)

---

## 7. Rollout Plan (Phases)

### Phase 0 — Audit (This Document) ✅
### Phase 1 — Global Mobile Foundation
- Create `mobile-system.css`
- Add to base templates
- Define utility classes

### Phase 2 — Tables + Lists
- Wrap all tables in `.cc-table-scroll`
- Test HQ + vertical tables

### Phase 3 — Dashboards (KPI Cards + Leaderboards)
- Apply utilities to all vertical dashboards
- Remove inline duplicates

### Phase 4 — Charts / Analytics
- Create `.cc-chart-container`
- Audit all Chart.js configs

### Phase 5 — Forms + Scan Pages
- Ensure inputs mobile-safe
- Stack button rows

### Phase 6 — Nav + Sidebar + More Features
- Ensure sidebar smooth on mobile
- "More Features" collapsible in sidebar

### Phase 7 — HQ Admin Mobile-First
- Apply system to HQ pages

### Phase 8 — Notifications UX
- Badge + bell behavior
- Dropdown fullscreen on mobile

---

## 8. Testing Checklist

### Automated Tests (Minimum)
- [ ] Django test: HQ dashboard renders (200) and includes `mobile-system.css`
- [ ] Django test: Phones dashboard renders (200) and includes `mobile-system.css`
- [ ] Django test: Wallet page renders (200) and includes `mobile-system.css`
- [ ] Cypress (if available): Set viewport 360x800, assert `body.scrollWidth <= window.innerWidth` on key pages

### Manual QA (Per Phase)
- [ ] Open page on 360px viewport (Chrome DevTools)
- [ ] Scroll entire page, check for horizontal scroll
- [ ] Inspect KPI cards: values fit inside
- [ ] Inspect leaderboards: names ellipsed if long
- [ ] Inspect tables: scroll wrapper works, no layout break
- [ ] Test desktop: no regressions

---

## Appendix: Key Files

### CSS Files (Current)
- `static/css/tokens.css` — design tokens
- `static/css/ui.css` — base UI components
- `static/css/app.css` — app-specific styles
- `static/css/mobile.css` — existing mobile patterns (scattered)
- `static/css/mobile-fixes.css` — overflow fixes (partial)
- `static/css/mobile-tables-responsive.css` — table patterns
- `static/css/hq-mobile.css` — HQ-specific mobile styles

### Templates (Base)
- `templates/base.html` — main app base
- `templates/hq/base_hq.html` — HQ admin base
- `templates/base_auth.html` — auth pages base
- `templates/base_min.html` — minimal base

### Templates (Vertical Dashboards)
- `templates/verticals/phones/dashboard.html`
- `templates/verticals/clothing/dashboard.html`
- `templates/verticals/gym/dashboard.html`
- `templates/verticals/liquor/dashboard.html`
- `templates/verticals/pharmacy/dashboard.html`

### Templates (High-Traffic)
- `templates/wallet/agent_wallet.html`
- `templates/notifications/notification_list.html`
- `templates/hq/business_directory.html`
- `templates/hq/dashboard.html`

---

**Next Steps:** Proceed to Phase 1 — Create `mobile-system.css` and integrate into base templates.


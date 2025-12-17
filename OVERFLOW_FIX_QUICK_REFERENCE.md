# Mobile Overflow Fix - Quick Reference Card

**For Developers:** Use these patterns when adding new dashboard metrics to prevent mobile overflow.

---

## When to Use `.cc-amount` Class

✅ **Always use for:**
- Currency amounts (MWK, USD, etc.)
- Revenue, profit, cost metrics
- Any number that could be 5+ digits
- Leaderboard values
- Model/product revenue
- Agent earnings
- KPI card values

❌ **Don't use for:**
- Short labels (e.g., "Today", "Sales")
- Single-digit counts (e.g., "3 items")
- Percentages under 100% (e.g., "25.5%")
- Icons or badges

---

## Pattern 1: KPI Card Amount

```django
<!-- ✅ DO THIS -->
<div class="metric-card">
  <h3><i class="bi bi-cash-stack"></i> Revenue</h3>
  <p class="cc-amount" 
     style="color:#16a34a" 
     title="MK {{ revenue|floatformat:0|intcomma }}">
    MK {{ revenue|floatformat:0|intcomma }}
  </p>
  <small>total sales amount</small>
</div>

<!-- ❌ NOT THIS -->
<div class="metric-card">
  <h3>Revenue</h3>
  <p style="color:#16a34a">MK {{ revenue|floatformat:0|intcomma }}</p>
  <small>total sales amount</small>
</div>
```

**Why:** The `cc-amount` class prevents the number from overflowing the card. The `title` attribute shows the full value on hover if ellipsed.

---

## Pattern 2: Leaderboard Item

```django
<!-- ✅ DO THIS -->
<div class="leaderboard-item">
  <div class="leaderboard-rank">1</div>
  <div class="leaderboard-name" title="{{ agent.name }}">
    <strong>{{ agent.name }}</strong>
    <div style="font-size:.85rem;color:#64748b">
      {{ agent.units }} units sold
    </div>
  </div>
  <div class="leaderboard-value cc-amount" 
       title="MK {{ agent.revenue|floatformat:0|intcomma }}">
    MK {{ agent.revenue|floatformat:0|intcomma }}
  </div>
</div>

<!-- ❌ NOT THIS -->
<div style="display:flex;gap:12px">
  <span>1</span>
  <span>{{ agent.name }}</span>
  <span>MK {{ agent.revenue|floatformat:0|intcomma }}</span>
</div>
```

**Why:** The `leaderboard-item` class ensures proper flex layout with `min-width:0`. The `cc-amount` on value ensures it doesn't overflow.

---

## Pattern 3: Label/Value Row

```django
<!-- ✅ DO THIS -->
<div class="cc-amount-row">
  <span>Cost of goods</span>
  <span class="cc-amount" 
        title="MK {{ cogs|floatformat:0|intcomma }}">
    MK {{ cogs|floatformat:0|intcomma }}
  </span>
</div>

<!-- ❌ NOT THIS -->
<div style="display:flex;justify-content:space-between">
  <span>Cost of goods</span>
  <span>MK {{ cogs|floatformat:0|intcomma }}</span>
</div>
```

**Why:** The `cc-amount-row` class ensures both children have `min-width:0` so they can shrink/ellipsis properly.

---

## Pattern 4: Table Cell Amount

```django
<!-- ✅ DO THIS -->
<td class="cc-amount" 
    style="text-align:right" 
    title="MK {{ amount|floatformat:0|intcomma }}">
  MK {{ amount|floatformat:0|intcomma }}
</td>

<!-- ❌ NOT THIS -->
<td style="text-align:right">
  MK {{ amount|floatformat:0|intcomma }}
</td>
```

**Why:** Table cells can overflow on narrow screens. `cc-amount` ensures safe ellipsis.

---

## CSS Classes Reference

### Core Classes

| Class | Purpose | Use When |
|-------|---------|----------|
| `.cc-amount` | Ellipsis long amounts | Currency, large numbers |
| `.cc-metric` | Same as cc-amount | KPI metrics |
| `.cc-amount-row` | Flex row with safe shrinking | Label/value pairs |
| `.leaderboard-item` | Flex row for lists | Agent lists, model lists |
| `.leaderboard-name` | Left side (shrinks) | Name/label that can ellipsis |
| `.leaderboard-value` | Right side (fixed) | Number that stays visible |

### Key CSS Properties Applied

When you use `.cc-amount`, you automatically get:

```css
.cc-amount {
  min-width: 0;                /* Allows flex shrink */
  overflow: hidden;            /* Hides overflow */
  text-overflow: ellipsis;     /* Shows ... when overflowing */
  white-space: nowrap;         /* Prevents wrapping */
  font-variant-numeric: tabular-nums;  /* Consistent digit spacing */
}
```

---

## Mobile Testing Checklist

Before committing dashboard changes, test on mobile:

```bash
# Chrome DevTools
1. Open Chrome DevTools (F12)
2. Toggle device toolbar (Ctrl+Shift+M / Cmd+Shift+M)
3. Set viewport to 360x760 (typical Android)
4. Visit your dashboard page
5. Scroll through entire page
6. Check: No horizontal scroll bar ✓
7. Check: All amounts stay in cards ✓
8. Set viewport to 320x568 (iPhone SE - worst case)
9. Repeat checks
```

### Quick Checks

✅ **Pass:** No horizontal scroll, all amounts visible  
❌ **Fail:** Horizontal scroll appears, amounts leak out  
⚠️ **Warning:** Amounts too small to read (increase min font size)

---

## Common Mistakes

### Mistake 1: Forgetting `min-width: 0` on flex parent

```django
<!-- ❌ WRONG -->
<div style="display:flex;justify-content:space-between">
  <span>Label</span>
  <span class="cc-amount">{{ amount }}</span>
</div>
```

**Problem:** Parent doesn't have `min-width:0`, so child can't shrink.

**Fix:** Use `.cc-amount-row` or add `min-width:0` to parent:

```django
<!-- ✅ CORRECT -->
<div class="cc-amount-row">
  <span>Label</span>
  <span class="cc-amount">{{ amount }}</span>
</div>
```

### Mistake 2: Forgetting tooltip

```django
<!-- ❌ WRONG -->
<p class="cc-amount">MK {{ amount|floatformat:0|intcomma }}</p>
```

**Problem:** If ellipsed, user can't see full value.

**Fix:** Add `title` attribute:

```django
<!-- ✅ CORRECT -->
<p class="cc-amount" 
   title="MK {{ amount|floatformat:0|intcomma }}">
  MK {{ amount|floatformat:0|intcomma }}
</p>
```

### Mistake 3: Using `white-space: normal` on amounts

```django
<!-- ❌ WRONG -->
<p class="cc-amount" style="white-space:normal">MK {{ amount }}</p>
```

**Problem:** Overrides `white-space:nowrap`, breaks ellipsis.

**Fix:** Remove `white-space` override or set to `nowrap`:

```django
<!-- ✅ CORRECT -->
<p class="cc-amount">MK {{ amount }}</p>
```

---

## Testing Your Changes

### 1. Manual Test (Chrome DevTools)

```
1. Open page in Chrome
2. Press F12 → Toggle device toolbar
3. Set to 360x760 (Android)
4. Reload page
5. Scroll through entire page
6. Expected: No horizontal scroll
7. Hover over amounts → Should show tooltip
```

### 2. Automated Test (Cypress)

Add a test in `cypress/e2e/`:

```javascript
it('should NOT overflow on my new dashboard', () => {
  cy.viewport(360, 760)
  cy.visit('/my-new-dashboard/')
  
  cy.window().then((win) => {
    const scrollWidth = win.document.documentElement.scrollWidth
    const clientWidth = win.document.documentElement.clientWidth
    
    expect(scrollWidth).to.be.at.most(clientWidth + 1)
  })
})
```

### 3. Run Test Suite

```bash
# Django tests
python manage.py test inventory.tests.test_legacy_blocking

# Cypress tests
npx cypress run --spec cypress/e2e/mobile_dashboard_overflow.cy.js
```

---

## Real-World Examples

### Example 1: Phones Dashboard KPI

```django
<article class="metric-card">
  <h3><i class="bi bi-cash-stack"></i> Revenue</h3>
  <p class="cc-amount" 
     style="color:#16a34a" 
     title="MK {{ dashboard_kpis.revenue|floatformat:0|intcomma }}">
    MK {{ dashboard_kpis.revenue|floatformat:0|intcomma }}
  </p>
  <small>total sales amount</small>
</article>
```

### Example 2: Top Agents Leaderboard

```django
<div class="leaderboard-item">
  <div class="leaderboard-rank">🥇</div>
  <div class="leaderboard-name" title="{{ agent.name }}">
    <strong>{{ agent.name }}</strong>
    <div style="font-size:.85rem;color:#64748b">
      {{ agent.units }} units sold
    </div>
  </div>
  <div class="leaderboard-value cc-amount" 
       title="MK {{ agent.revenue|floatformat:0|intcomma }}">
    MK {{ agent.revenue|floatformat:0|intcomma }}
  </div>
</div>
```

### Example 3: Payment Mix Card

```django
<div class="metric-card" style="border-left:4px solid #10b981">
  <h3><i class="bi bi-cash-stack"></i> Cash</h3>
  <p class="cc-amount" 
     style="color:#10b981" 
     title="MK {{ cash_amount|floatformat:0|intcomma }}">
    MK {{ cash_amount|floatformat:0|intcomma }}
  </p>
  <small>
    <span class="badge" style="background:#d1fae5;color:#065f46">
      {{ cash_percentage }}% of revenue
    </span>
  </small>
</div>
```

---

## Troubleshooting

### Problem: Amount still overflows on mobile

**Check:**
1. Is `.cc-amount` class applied? ✓
2. Does parent have `min-width:0`? ✓
3. Is parent using `display:flex`? ✓
4. Is there a `white-space:normal` override? ❌ (remove it)
5. Is there a `max-width:none` override? ❌ (remove it)

### Problem: Ellipsis not showing

**Check:**
1. Is `overflow:hidden` applied? ✓
2. Is `white-space:nowrap` applied? ✓
3. Is `text-overflow:ellipsis` applied? ✓
4. Is element wider than parent? (if yes, should ellipsis) ✓

### Problem: Tooltip not showing

**Check:**
1. Does element have `title=""` attribute? ✓
2. Is title attribute empty? ❌ (add value)
3. Is element `pointer-events:none`? ❌ (remove it)

---

## Quick Copy-Paste Templates

### KPI Card
```django
<div class="metric-card">
  <h3><i class="bi bi-ICON"></i> LABEL</h3>
  <p class="cc-amount" title="VALUE">VALUE</p>
  <small>description</small>
</div>
```

### Leaderboard Item
```django
<div class="leaderboard-item">
  <div class="leaderboard-rank">RANK</div>
  <div class="leaderboard-name" title="NAME">
    <strong>NAME</strong>
  </div>
  <div class="leaderboard-value cc-amount" title="VALUE">VALUE</div>
</div>
```

### Amount Row
```django
<div class="cc-amount-row">
  <span>LABEL</span>
  <span class="cc-amount" title="VALUE">VALUE</span>
</div>
```

---

## Need Help?

- **File:** `static/css/mobile-fixes.css` - Contains all overflow-safe utility classes
- **Example:** `templates/verticals/phones/dashboard.html` - Reference implementation
- **Tests:** `cypress/e2e/mobile_dashboard_overflow.cy.js` - Overflow test examples
- **Docs:** `LEGACY_BLOCKING_AND_MOBILE_OVERFLOW_FIX_SUMMARY.md` - Full implementation details

---

**Remember:** When in doubt, add `.cc-amount` + `title=""`. Better safe than overflowed! 🎯


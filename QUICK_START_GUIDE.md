# Quick Start Guide: New Features

## 🚀 What's New

### 1. Intelligent IMEI Picker
When scanning in phones, you now see available IMEIs for the selected model, making it easy to avoid duplicates and see what's already in stock.

### 2. Unified Scan-In URL
The main `/inventory/scan-in/` URL now shows the beautiful gamified phone scanner with brand cards and progress tracking.

### 3. Polished Landing Page
The home page now has a mission statement, a T.S. Eliot motto, and consistent blue buttons throughout.

---

## 📱 Using the Intelligent IMEI Picker

### As a Manager
1. Navigate to **Scan IN** from the sidebar
2. Select a brand (ITEL, TECNO, or SAMSUNG)
3. Choose a model from the dropdown
4. **Look at the right sidebar** → You'll see all available IMEIs across all your locations
5. Click an IMEI to auto-fill it, or type a new one

### As an Agent
1. Navigate to **Scan IN** from the sidebar
2. Select a brand
3. Choose a model
4. **Look at the right sidebar** → You'll see available IMEIs for YOUR location only
5. Click an IMEI to auto-fill it, or type a new one

### What You'll See
- **"Available IMEIs for this model"** panel on the right (desktop) or below (mobile)
- List of IMEIs that are:
  - ✅ In stock (not sold)
  - ✅ Active
  - ✅ In your business
  - ✅ In your location (agents) or all locations (managers)
- If no IMEIs exist: "No existing IMEIs for this model. You are adding a new one."

---

## 📊 Gamification Stats (Role-Based)

### Managers See
- **Total scans for the entire business** (all locations, all agents)
- Progress toward daily target (50 phones)
- Business-wide performance

### Agents See
- **Only their own scans** in their assigned location
- Personal progress toward daily target
- Individual contribution tracking

---

## 🔒 Security Features

### What's Protected
1. **Business Isolation**: You can NEVER see or scan products from another business
2. **Location Scoping**: Agents can only see their location's data
3. **Role-Based Access**: Managers have business-wide view, agents have location-specific view
4. **Duplicate Prevention**: Existing IMEI validation prevents scanning the same phone twice

### How It Works
- Your active business is determined by your session
- Your location is determined by your membership record
- All queries are automatically filtered by business + location + role
- Cross-business attacks are blocked at the view level

---

## 🎨 Landing Page Updates

### Visit the Home Page
1. Go to the root URL (e.g., `https://yourdomain.com/`)
2. You'll see:
   - **Hero section** with "Doing business shouldn't be a headache"
   - **Mission statement**: "The Spotify of every small business..."
   - **How It Works** section with 4 steps
   - **Features** grid with 6 key features
   - **T.S. Eliot motto** in a premium glassmorphic card
   - **Simulator CTA** to try the business simulator
   - **Final CTA** to get started

### Button Styling
- All primary actions use **uniform blue buttons** (`btn-primary`)
- Consistent hover effects and shadows
- Mobile-responsive design

---

## 🧪 Testing Your Changes

### Manual Testing

#### Test 1: IMEI Picker (Manager)
1. Login as a manager
2. Go to **Scan IN**
3. Select **TECNO** → Choose a model
4. Verify you see IMEIs from ALL locations
5. Click an IMEI → Verify it auto-fills the input

#### Test 2: IMEI Picker (Agent)
1. Login as an agent
2. Go to **Scan IN**
3. Select **ITEL** → Choose a model
4. Verify you see IMEIs from YOUR location only
5. Click an IMEI → Verify it auto-fills the input

#### Test 3: Cross-Business Security
1. Login as manager of Business A
2. Try to scan in a product from Business B (if you have access to the catalog ID)
3. Verify the scan is rejected
4. Verify no stock is created in either business

#### Test 4: Role-Based Stats
1. As an agent, scan in 2 phones
2. Check the "Scanned today" counter → Should show 2
3. Login as manager
4. Check the "Scanned today" counter → Should show ALL scans (including the agent's 2)

#### Test 5: Landing Page
1. Logout (or open incognito window)
2. Visit the home page
3. Verify:
   - Mission statement is visible
   - T.S. Eliot quote is visible with attribution
   - All "Get Started" buttons are blue
   - Page looks premium and polished

### Automated Testing
```bash
# Run all tests
pytest tests/test_intelligent_imei_picker.py tests/test_landing_page.py -v

# Run specific test
pytest tests/test_intelligent_imei_picker.py::test_available_imeis_endpoint_scoped_to_business_and_location -v

# Run with output
pytest tests/test_landing_page.py::test_landing_page_contains_mission_statement -v -s
```

---

## 🐛 Troubleshooting

### IMEI Picker Not Showing
- **Check**: Is the business kind set to "PHONES"?
- **Check**: Did you select a model from the dropdown?
- **Check**: Open browser console for JavaScript errors
- **Fix**: Ensure `/inventory/phones/available-imeis/<product_id>/` endpoint is accessible

### No IMEIs in the List
- **This is normal** if:
  - The model is brand new (no stock yet)
  - All stock for this model has been sold
  - You're an agent and there's no stock in YOUR location
- **Message shown**: "No existing IMEIs for this model. You are adding a new one."

### Stats Not Updating
- **Check**: Did you scan in today? (Stats are for TODAY only)
- **Check**: Is your membership record set up correctly?
- **Check**: For agents, is `assigned_agent` field populated on InventoryItem?

### Landing Page Not Updated
- **Check**: Are you viewing the correct URL? (`/` or `/home/`)
- **Check**: Clear browser cache (Ctrl+Shift+R or Cmd+Shift+R)
- **Check**: Ensure `staticpages/templates/staticpages/home.html` is the active template

### Cross-Business Error
- **This is intentional** - you cannot scan products from another business
- **Check**: Ensure the product catalog entry belongs to YOUR active business
- **Fix**: Create the product in your business's catalog first

---

## 📝 API Reference

### Available IMEIs Endpoint

**URL**: `/inventory/phones/available-imeis/<product_id>/`

**Method**: `GET`

**Authentication**: Required (login_required)

**Parameters**:
- `product_id` (int, URL parameter): The ID of the phone product

**Response** (JSON):
```json
{
  "ok": true,
  "imeis": ["123456789012345", "123456789012346"],
  "count": 2
}
```

**Scoping**:
- Managers: All IMEIs across all locations in their business
- Agents: Only IMEIs in their assigned location

**Filters**:
- `business` = current active business
- `status` = "IN_STOCK"
- `is_active` = True
- `imei` is not null and not empty

---

## 🎯 Best Practices

### For Managers
1. **Review IMEI picker regularly** to see what's in stock across locations
2. **Monitor gamification stats** to track team performance
3. **Use the picker** to avoid duplicate entries when scanning in phones
4. **Check location distribution** by comparing IMEIs across locations

### For Agents
1. **Always check the IMEI picker** before typing a new IMEI
2. **Click existing IMEIs** when re-scanning or verifying stock
3. **Track your daily progress** with the gamification bar
4. **Report discrepancies** if an IMEI shows in the picker but isn't physically in stock

### For Developers
1. **Never bypass business scoping** - always use `get_active_business(request)`
2. **Test with multiple businesses** to ensure isolation
3. **Test with both manager and agent roles** to verify scoping
4. **Add tests** for any new features that touch stock or business data

---

## 📚 Related Documentation

- `IMPLEMENTATION_SUMMARY.md` - Full technical details
- `DASHBOARD_FIXES_SUMMARY.md` - Related dashboard improvements
- `tests/test_intelligent_imei_picker.py` - Test examples
- `tests/test_landing_page.py` - Landing page test examples

---

## 🆘 Getting Help

### Common Questions

**Q: Can I disable the IMEI picker?**
A: It's always visible but doesn't prevent manual IMEI entry. You can still type any IMEI.

**Q: Why don't I see IMEIs from other locations as an agent?**
A: This is intentional - agents are scoped to their assigned location for security and clarity.

**Q: Can I scan in a phone that's already in the picker?**
A: No - the existing duplicate IMEI validation will prevent this. The picker helps you see what's already there.

**Q: What if I need to scan the same IMEI twice (e.g., after a return)?**
A: Contact your manager to mark the original entry as sold or inactive first.

### Support Channels
- Check test files for usage examples
- Review view code in `inventory/views_phones.py`
- Consult Django admin for data inspection
- Contact system administrator for access issues

---

**Last Updated**: December 5, 2025
**Version**: 1.0
**Django**: 5.2


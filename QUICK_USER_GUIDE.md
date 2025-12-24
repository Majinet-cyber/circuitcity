# Quick User Guide - New Features

## 🏋️ Gym Features

### 1. Recording Member Payments
**Location:** Gym → Members → Add Payment

**New Behavior:**
- Payment amount fields are now **blank by default**
- You must manually enter the membership amount
- Real-time preview shows how many days will be granted
- Formula: MWK 55,000 = 30 days (daily rate: MWK 1,833.33)

**Example:**
- Enter MWK 55,000 → Get 30 days
- Enter MWK 110,000 → Get 60 days
- Enter MWK 27,500 → Get 15 days

**Trainer Fee:**
- Optional field for additional trainer charges
- Does NOT add extra membership days
- Only adds to total payment amount

---

### 2. Member QR Codes
**Location:** Gym → Members → [Select Member] → Member Detail Page

**Features:**
- Each member automatically gets a unique QR code
- QR code displays on member detail page
- Format: `GYM-XXXXXX` (6-digit unique code)
- **Print Button:** Click to print QR code for member card
- QR code can be scanned for quick check-in

**Use Cases:**
- Print QR codes for physical member cards
- Scan QR codes at gym entrance
- Quick member identification

---

## 🔄 Sale Rollback (Manager Only)

### Available In:
- 🍷 Liquor Sales History
- 💊 Pharmacy Sales History
- 👔 Clothing Sales History

### How to Rollback a Sale

1. **Navigate to Sales History**
   - Go to your vertical dashboard
   - Click "Sales History" or "Sales"

2. **Find the Sale**
   - Use filters (date range, search) to find the incorrect sale
   - Locate the sale in the table

3. **Click Rollback Button**
   - Look for the ↻ (counterclockwise arrow) button in the Actions column
   - **Note:** Only managers can see this button

4. **Confirm Rollback**
   - Read the confirmation dialog carefully
   - Confirms: Sale will be cancelled & inventory restored
   - Click "OK" to proceed or "Cancel" to abort

5. **Result**
   - ✅ Sale is marked as cancelled
   - ✅ Inventory is restored (product/batch quantity increased)
   - ✅ Page refreshes to show updated data

### What Happens During Rollback

**Liquor:**
- Product quantity restored
- Sale marked as cancelled (or note added)

**Pharmacy:**
- Batch quantity restored
- Sale marked as deleted

**Clothing:**
- Product quantity restored
- Sale marked as cancelled (or note added)

### Important Notes

⚠️ **Rollback Cannot Be Undone**
- Once rolled back, the sale is permanently cancelled
- Inventory changes are immediate
- Use with caution

🔒 **Manager-Only Feature**
- Only users with Manager role can rollback sales
- Agents will not see the rollback button
- Prevents accidental or unauthorized rollbacks

---

## 👔 Clothing: Adding Products Without Barcodes

### Location: Clothing → Scan In / Stock In

### Steps:

1. **Select "Has Barcode?"**
   - Choose "No" if product doesn't have a barcode
   - Choose "Yes" if product has a barcode

2. **If "No" Selected:**
   - Barcode field is ignored
   - Product is created without barcode
   - No errors or null values

3. **If "Yes" Selected:**
   - Barcode field becomes required
   - Must enter valid barcode
   - System checks for duplicates

### Example Workflow:

**Without Barcode:**
```
1. Category: Shirt
2. Size: M
3. Color: Blue
4. Has Barcode: No
5. Quantity: 10
6. Cost: 5000
7. Submit → Success ✅
```

**With Barcode:**
```
1. Category: Shirt
2. Size: M
3. Color: Blue
4. Has Barcode: Yes
5. Barcode: 1234567890123
6. Quantity: 10
7. Cost: 5000
8. Submit → Success ✅
```

---

## 🎨 UI Improvements

### Gym Payment Form

**Visual Enhancements:**
- 💰 Currency fields now show "MWK" prefix
- 💡 Help text with emoji icons for better visibility
- 📊 Real-time days calculation preview
- 🔘 Larger, more prominent buttons
- ✨ Cleaner, more professional layout

**Real-Time Preview:**
- As you type the membership amount
- System calculates and displays days granted
- Updates instantly without page refresh
- Helps prevent entry errors

---

## 🆘 Troubleshooting

### "I don't see the rollback button"
- **Solution:** Only managers can rollback sales. Check your role.

### "Rollback says 'Sale already cancelled'"
- **Solution:** This sale was already rolled back. Cannot rollback twice.

### "Clothing product returns null"
- **Solution:** Make sure you select "No" for "Has Barcode" if product has no barcode.

### "QR code not showing"
- **Solution:** Member must have a `member_code`. This is auto-generated on save.

### "Days calculation seems wrong"
- **Solution:** Formula is MWK 1,833.33 per day. Check your math or contact support.

---

## 📞 Support

If you encounter any issues:
1. Check this guide first
2. Verify your user role (Manager vs Agent)
3. Clear browser cache and try again
4. Contact system administrator

---

**Last Updated:** December 24, 2024
**Version:** 1.0


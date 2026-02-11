# Pharmacy Corrections - Quick Start Guide

## 🚀 How to Use (3 Steps)

### Step 1: Start the Server
```bash
python manage.py runserver
```

### Step 2: Navigate to Pharmacy Corrections

**Option A: Via URL**
```
http://localhost:8000/corrections/pharmacy/entity/pharmacy_sale/
http://localhost:8000/corrections/pharmacy/entity/pharmacy_batch/
```

**Option B: Via Sidebar**
1. Go to Pharmacy Dashboard
2. Click **"Data Correction"** in the sidebar

### Step 3: Edit a Record

1. **Click "Edit"** on any row
2. **Modify fields** (e.g., change payment method, quantity, expiry date)
3. **Enter reason** (required): "Correcting customer payment method"
4. **Click "Apply Correction"**

✅ **Done!** The correction is saved and logged.

---

## 🎯 What Can You Edit?

### Pharmacy Sales (`pharmacy_sale`)
- ✏️ Quantity sold
- ✏️ Unit price
- ✏️ Unit cost
- ✏️ Payment method (CASH, MOBILE_MONEY, BANK, CREDIT)
- ✏️ Customer name/phone
- ✏️ Sale timestamp
- 🔄 **Total amount auto-recalculates** when quantity/price changes

### Pharmacy Batches (`pharmacy_batch`)
- ✏️ Batch number
- ✏️ Expiry date
- ✏️ Quantity in stock
- ✏️ Cost price
- ✏️ Selling price
- ✏️ Supplier name
- ✏️ Received date
- ✅ **Validates** pricing and quantity (must be >= 0)

---

## 🔍 Find Problem Records

Check the **"Common Issues Only"** checkbox to see:

### Sales Issues:
- ❌ Total amount = 0 but has items
- ❌ Payment method missing
- ❌ Sold below cost
- ❌ Calculation errors (total ≠ quantity × price)

### Batch Issues:
- ❌ Expired batches still active
- ❌ Missing expiry date
- ❌ Negative stock
- ❌ Selling below cost
- ❌ Missing batch number

---

## 🔒 Safety Features

✅ **Audit Trail** - Every change is logged with who, when, why  
✅ **Tenant Isolation** - You can only edit your own business records  
✅ **Validation** - Prevents negative prices, invalid payment methods  
✅ **Auto-Recompute** - Totals recalculate automatically  
✅ **Rollback** - Can undo corrections if needed

---

## 📊 After Corrections

- Dashboard metrics update after refresh
- Audit logs are searchable
- Correction history shows on edit page

---

## ❓ Troubleshooting

**Q: I don't see the "Edit" button**  
A: You must be a **Manager** to access corrections

**Q: Changes don't save**  
A: Check that you entered a **reason** (required field)

**Q: Total amount doesn't update**  
A: It auto-updates when you change **quantity** or **unit_price**

**Q: Can I delete records?**  
A: No, use soft delete flags instead (corrections framework doesn't delete)

---

## 🎓 Example Workflow

**Scenario:** Customer paid with Mobile Money, but was recorded as Cash

1. Go to `/corrections/pharmacy/entity/pharmacy_sale/`
2. Find the sale (use search or filter)
3. Click **"Edit"**
4. Change `payment_method` from `CASH` to `MOBILE_MONEY`
5. Enter reason: "Customer paid via Airtel Money, not cash"
6. Click **"Apply Correction"**
7. ✅ Done! Change is logged and dashboard updates

---

**Need more details?** See `PHARMACY_CORRECTIONS_COMPLETE.md`





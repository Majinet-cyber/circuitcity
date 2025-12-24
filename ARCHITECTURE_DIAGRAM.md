# Architecture Diagram: Rollback & Pricing System

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   Phones     │  │    Liquor    │  │   Clothing   │              │
│  │  Dashboard   │  │  Dashboard   │  │  Dashboard   │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         │                  │                  │                       │
│         │  [Rollback Button Visible Based on Permissions]           │
│         │                  │                  │                       │
└─────────┼──────────────────┼──────────────────┼───────────────────────┘
          │                  │                  │
          ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         VIEW LAYER                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ Phone Sale   │  │ Liquor Sale  │  │ Clothing Sale│              │
│  │   Wizard     │  │   Rollback   │  │   Rollback   │              │
│  │              │  │     Views    │  │     Views    │              │
│  │ • Step 1:    │  │              │  │              │              │
│  │   IMEI       │  │ • Confirm    │  │ • Confirm    │              │
│  │ • Step 2:    │  │ • Execute    │  │ • Execute    │              │
│  │   Price ✨   │  │              │  │              │              │
│  │ • Step 3:    │  │              │  │              │              │
│  │   Payment    │  │              │  │              │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         │                  │                  │                       │
│         │  [Error Handling: No HTTP 500s]    │                       │
│         │                  │                  │                       │
└─────────┼──────────────────┼──────────────────┼───────────────────────┘
          │                  │                  │
          ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      SERVICE LAYER                                   │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              Pricing Validation Service                       │  │
│  │  • validate_selling_price()                                   │  │
│  │  • format_currency()                                          │  │
│  │  • parse_currency_input()                                     │  │
│  │                                                                │  │
│  │  Features:                                                     │  │
│  │  ✅ Below cost warning                                        │  │
│  │  ✅ High price warning                                        │  │
│  │  ✅ Profit margin calculation                                 │  │
│  │  ✅ Smart suggestions                                         │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              Rollback Service (Phones)                        │  │
│  │  • can_rollback()                                             │  │
│  │  • rollback_sale()                                            │  │
│  │  • _restore_inventory()                                       │  │
│  │  • _reverse_commissions()                                     │  │
│  │  • _create_refund_entry()                                     │  │
│  │                                                                │  │
│  │  Features:                                                     │  │
│  │  ✅ Idempotent (safe to retry)                                │  │
│  │  ✅ Transactional (atomic)                                    │  │
│  │  ✅ Permission checks                                         │  │
│  │  ✅ Audit trail                                               │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │         Vertical Rollback Services (Liquor, Clothing)         │  │
│  │  • LiquorRollbackService.rollback_liquor_sale()               │  │
│  │  • ClothingRollbackService.rollback_clothing_sale()           │  │
│  │                                                                │  │
│  │  Features:                                                     │  │
│  │  ✅ Vertical-aware stock restoration                          │  │
│  │  ✅ Same safety guarantees as Phones                          │  │
│  │  ✅ Manager-only permissions                                  │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────┬────────────────────┬──────────────────┬───────────────────┘
          │                    │                  │
          ▼                    ▼                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       DATA LAYER                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │     Sale     │  │  LiquorSale  │  │ ClothingSale │              │
│  │   (Phones)   │  │              │  │              │              │
│  │              │  │              │  │              │              │
│  │ • item       │  │ • product    │  │ • product    │              │
│  │ • agent      │  │ • quantity   │  │ • quantity   │              │
│  │ • price      │  │ • unit_price │  │ • unit_price │              │
│  │ • is_rolled  │  │ • is_rolled  │  │ • is_rolled  │              │
│  │   _back ✨   │  │   _back ✨   │  │   _back ✨   │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ InventoryItem│  │ MerchProduct │  │ MerchProduct │              │
│  │   (Phone)    │  │   (Liquor)   │  │  (Clothing)  │              │
│  │              │  │              │  │              │              │
│  │ • status     │  │ • quantity   │  │ • quantity   │              │
│  │ • sold_at    │  │   _in_stock  │  │              │              │
│  │ • sold_by    │  │              │  │              │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    SaleRollback (Audit)                       │  │
│  │  • sale                                                        │  │
│  │  • reason                                                      │  │
│  │  • refunded_amount                                             │  │
│  │  • return_to_stock                                             │  │
│  │  • created_by                                                  │  │
│  │  • created_at                                                  │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

## Rollback Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ROLLBACK EXECUTION FLOW                           │
└─────────────────────────────────────────────────────────────────────┘

1. USER CLICKS "ROLLBACK SALE"
   │
   ▼
2. VIEW: Check Permissions
   │
   ├─► Manager/Owner? ──────────────────► ✅ ALLOW
   │
   ├─► Agent + Own Sale + < 10 min? ────► ✅ ALLOW
   │
   └─► Otherwise ───────────────────────► ❌ DENY
   │
   ▼
3. VIEW: Show Confirmation Page
   │
   ├─► Sale details (formatted with commas)
   ├─► Reason dropdown
   ├─► Refund amount input
   ├─► Return to stock checkbox
   └─► Notes textarea
   │
   ▼
4. USER CONFIRMS
   │
   ▼
5. SERVICE: Validate Request
   │
   ├─► Already rolled back? ────────────► Return existing (IDEMPOTENT)
   │
   ├─► Invalid reason? ─────────────────► ❌ ERROR
   │
   ├─► Refund > sale price? ────────────► ❌ ERROR
   │
   └─► Valid? ──────────────────────────► Continue
   │
   ▼
6. SERVICE: Acquire Lock (select_for_update)
   │
   ▼
7. SERVICE: Double-check (race condition protection)
   │
   ├─► Already rolled back? ────────────► Return existing (IDEMPOTENT)
   │
   └─► Not rolled back? ────────────────► Continue
   │
   ▼
8. SERVICE: Mark Sale as Rolled Back
   │
   ├─► sale.is_rolled_back = True
   ├─► sale.rolled_back_at = now()
   └─► sale.rolled_back_by = user
   │
   ▼
9. SERVICE: Create Rollback Record (Audit)
   │
   └─► SaleRollback.objects.create(...)
   │
   ▼
10. SERVICE: Restore Inventory (if requested)
    │
    ├─► Phones: item.status = "IN_STOCK"
    │
    ├─► Liquor: product.quantity_in_stock += quantity
    │
    └─► Clothing: product.quantity += quantity
    │
    ▼
11. SERVICE: Reverse Commissions
    │
    └─► commission.is_reversed = True
    │
    ▼
12. SERVICE: Create Refund Entry (if applicable)
    │
    └─► Transaction.objects.create(amount=-refunded_amount)
    │
    ▼
13. SERVICE: Commit Transaction (ATOMIC)
    │
    ├─► Success? ────────────────────────► ✅ COMMIT
    │
    └─► Error? ──────────────────────────► ❌ ROLLBACK
    │
    ▼
14. VIEW: Show Success Message
    │
    └─► "✅ Sale #123 rolled back successfully!"
```

## Price Validation Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                  PRICE VALIDATION FLOW (PHONES)                      │
└─────────────────────────────────────────────────────────────────────┘

1. USER ENTERS PRICE
   │
   ▼
2. PARSE INPUT
   │
   └─► "MK 2,000,000" ──────► Decimal("2000000")
   │
   ▼
3. VALIDATE: Price > 0?
   │
   ├─► NO ──────────────────────────────► ❌ BLOCK
   │
   └─► YES ─────────────────────────────► Continue
   │
   ▼
4. VALIDATE: Price < 100 million?
   │
   ├─► NO ──────────────────────────────► ❌ BLOCK
   │
   └─► YES ─────────────────────────────► Continue
   │
   ▼
5. CHECK: Price vs Cost
   │
   ├─► Below cost? ─────────────────────► ⚠️ WARN
   │   └─► "Price is below cost by MK X"
   │
   ├─► Low margin (< 5%)? ──────────────► ⚠️ WARN
   │   └─► "Low profit margin (3%)"
   │
   └─► Good margin (≥ 15%)? ─────────────► ✅ FEEDBACK
       └─► "Great profit margin (25%)!"
   │
   ▼
6. CHECK: Price vs Suggested
   │
   ├─► > 20% different? ────────────────► ⚠️ WARN
   │   └─► "Price is 30% higher than suggested"
   │
   └─► Similar? ─────────────────────────► Continue
   │
   ▼
7. DISPLAY RESULTS
   │
   ├─► Warnings (yellow)
   ├─► Feedback (green)
   ├─► Profit margin
   └─► Formatted price (with commas)
   │
   ▼
8. USER DECIDES
   │
   ├─► Adjust price ────────────────────► Back to Step 1
   │
   └─► Proceed ──────────────────────────► Continue to Payment
```

## Permission Matrix

```
┌──────────────────────────────────────────────────────────────────────┐
│                      ROLLBACK PERMISSIONS                             │
├──────────────┬─────────────┬──────────────┬─────────────────────────┤
│     ROLE     │   VERTICAL  │   TIMING     │        RESULT           │
├──────────────┼─────────────┼──────────────┼─────────────────────────┤
│ Manager      │ Phones      │ Anytime      │ ✅ ALLOWED              │
│ Manager      │ Liquor      │ Anytime      │ ✅ ALLOWED              │
│ Manager      │ Clothing    │ Anytime      │ ✅ ALLOWED              │
├──────────────┼─────────────┼──────────────┼─────────────────────────┤
│ Owner        │ Phones      │ Anytime      │ ✅ ALLOWED              │
│ Owner        │ Liquor      │ Anytime      │ ✅ ALLOWED              │
│ Owner        │ Clothing    │ Anytime      │ ✅ ALLOWED              │
├──────────────┼─────────────┼──────────────┼─────────────────────────┤
│ Agent        │ Phones      │ < 10 min     │ ✅ ALLOWED (own sales)  │
│ Agent        │ Phones      │ > 10 min     │ ❌ DENIED               │
│ Agent        │ Phones      │ Other's sale │ ❌ DENIED               │
├──────────────┼─────────────┼──────────────┼─────────────────────────┤
│ Agent        │ Liquor      │ Anytime      │ ❌ DENIED               │
│ Agent        │ Clothing    │ Anytime      │ ❌ DENIED               │
└──────────────┴─────────────┴──────────────┴─────────────────────────┘
```

## Data Flow: Sale Creation → Rollback

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SALE LIFECYCLE                                    │
└─────────────────────────────────────────────────────────────────────┘

CREATION:
┌──────────────┐
│  User sells  │
│    phone     │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ Sale.objects.create(                                          │
│   item=stock_item,                                            │
│   agent=user,                                                 │
│   price=1500000,  ◄─── Validated with warnings               │
│   is_rolled_back=False                                        │
│ )                                                              │
└──────┬───────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ stock_item.status = "SOLD"                                    │
│ stock_item.sold_at = now()                                    │
│ stock_item.sold_by = user                                     │
└──────┬───────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ SaleCommission.objects.create(                                │
│   sale=sale,                                                  │
│   agent=user,                                                 │
│   base_commission=180000,  (12% of 1500000)                   │
│   is_reversed=False                                           │
│ )                                                              │
└──────┬───────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ ✅ Success message displayed (formatted with commas)          │
│ "🎉 Sale completed! MK 1,500,000 – Profit: MK 300,000"       │
└──────────────────────────────────────────────────────────────┘

ROLLBACK:
┌──────────────┐
│ Manager      │
│ clicks       │
│ "Rollback"   │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ RollbackService.rollback_sale(                                │
│   sale=sale,                                                  │
│   user=manager,                                               │
│   reason="RETURNED",                                          │
│   refunded=True,                                              │
│   refunded_amount=1500000,                                    │
│   return_to_stock=True                                        │
│ )                                                              │
└──────┬───────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ sale.is_rolled_back = True                                    │
│ sale.rolled_back_at = now()                                   │
│ sale.rolled_back_by = manager                                 │
└──────┬───────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ SaleRollback.objects.create(                                  │
│   sale=sale,                                                  │
│   reason="RETURNED",                                          │
│   refunded_amount=1500000,                                    │
│   return_to_stock=True,                                       │
│   created_by=manager                                          │
│ )                                                              │
└──────┬───────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ stock_item.status = "IN_STOCK"                                │
│ stock_item.sold_at = None                                     │
│ stock_item.sold_by = None                                     │
└──────┬───────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ commission.is_reversed = True                                 │
│ commission.reversed_at = now()                                │
└──────┬───────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ Transaction.objects.create(                                   │
│   amount=-1500000,  (negative = refund)                       │
│   description="Refund for rolled back sale #123"             │
│ )                                                              │
└──────┬───────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ ✅ Success message displayed                                  │
│ "✅ Sale #123 rolled back successfully!"                      │
│ "✅ Stock restored"                                           │
│ "✅ Refund recorded: MK 1,500,000"                            │
└──────────────────────────────────────────────────────────────┘
```

## Error Handling Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                  ERROR HANDLING LAYERS                               │
└─────────────────────────────────────────────────────────────────────┘

LAYER 1: VIEW LAYER
┌──────────────────────────────────────────────────────────────┐
│ try:                                                          │
│     result = service.rollback_sale(...)                       │
│     messages.success(request, "✅ Success!")                  │
│ except RollbackError as e:                                    │
│     messages.error(request, f"❌ {e}")  ◄─── User-friendly   │
│ except Exception as e:                                        │
│     logger.error(f"Error: {e}", exc_info=True)  ◄─── Logged  │
│     messages.error(request, "❌ Unexpected error")            │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
LAYER 2: SERVICE LAYER
┌──────────────────────────────────────────────────────────────┐
│ try:                                                          │
│     # Business logic                                          │
│     if invalid:                                               │
│         raise RollbackError("Clear reason")  ◄─── Structured │
│ except RollbackError:                                         │
│     raise  ◄─── Re-raise business errors                     │
│ except Exception as e:                                        │
│     logger.error(f"Unexpected: {e}", exc_info=True)           │
│     raise RollbackError(f"Unexpected: {e}")  ◄─── Wrap       │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
LAYER 3: DATABASE LAYER
┌──────────────────────────────────────────────────────────────┐
│ @transaction.atomic  ◄─── All-or-nothing                     │
│ def rollback_sale(...):                                       │
│     # All operations succeed or all fail                      │
│     sale.save()                                               │
│     rollback.create()                                         │
│     item.save()                                               │
│     commission.save()                                         │
└──────────────────────────────────────────────────────────────┘

RESULT: NO HTTP 500s
┌──────────────────────────────────────────────────────────────┐
│ User sees:                                                    │
│   ❌ "Rollback failed: Sale already rolled back"             │
│   ❌ "Rollback failed: Insufficient permissions"             │
│   ❌ "An unexpected error occurred. Please try again."       │
│                                                               │
│ Admin sees (in logs):                                         │
│   ERROR: Rollback error for sale 123: <full stack trace>     │
└──────────────────────────────────────────────────────────────┘
```

---

**Legend:**
- ✅ Success / Allowed
- ❌ Error / Denied
- ⚠️ Warning
- ✨ New feature
- ◄─── Flow direction / Note

---

*This diagram provides a visual overview of the rollback and pricing system architecture.*


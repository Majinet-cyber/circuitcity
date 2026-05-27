# Phase B Implementation Status

## Overview

Phase A (Fast Sell Removal) is **COMPLETE** ✅  
Phase B has 4 major tasks with varying complexity levels.

---

## TASK 2: "Has Barcode?" Workflow ⚠️ IN PROGRESS

**Goal**: Add barcode toggle to scan-in forms for inventory verticals (phones, liquor, pharmacy, clothing)

### Progress: 30% Complete

#### ✅ Completed:
1. **Barcode Utilities** - Already exist in `inventory/utils_barcodes.py`:
   - `validate_barcode()` - Format validation
   - `set_barcode()` - Store barcode on objects
   - `get_barcode()` - Retrieve barcode
   - `normalize_barcode()` - Normalize to uppercase
   - `find_by_barcode()` - Search functionality

2. **Pharmacy Backend** - Updated `inventory/views_pharmacy.py`:
   - Added `has_barcode` field extraction
   - Added `barcode` field extraction
   - Conditional validation: if has_barcode=yes, barcode is required
   - Barcode validation via `validate_barcode()`
   - Barcode storage via `set_barcode()` on product
   - Returns 200 with error messages (no 500s)

#### ⚠️ Remaining Work:

**Backend Updates Needed:**

1. **Phones Scan-In** (`inventory/views_phones.py::phone_scan_in`):
   - Note: Phones use IMEI as primary identifier (15-digit)
   - IMEI already serves as barcode
   - Could add optional additional barcode field for accessories
   - Lower priority since IMEI is mandatory

2. **Generic Scan-In** (`inventory/views.py` or `inventory/views_scan.py`):
   - Used by clothing and liquor
   - Add has_barcode/barcode fields to existing form
   - Add conditional validation logic
   - Store barcode on created items/products

3. **Clothing Scan-In** (`inventory/verticals/clothing.py::scan_in`):
   - Check if uses generic or custom form
   - Add barcode workflow if custom

4. **Liquor Stock-In**:
   - Identify the correct view (liquor uses MerchProduct model)
   - Add barcode workflow similar to pharmacy

**Template Updates Needed:**

1. **Pharmacy Stock-In Template** (`templates/verticals/pharmacy/stock_in.html`):
   ```html
   <!-- Add before category field -->
   <div class="form-group">
     <label>Does this product have a barcode?</label>
     <div class="form-check">
       <input type="radio" name="has_barcode" value="no" checked id="barcode-no">
       <label for="barcode-no">No</label>
     </div>
     <div class="form-check">
       <input type="radio" name="has_barcode" value="yes" id="barcode-yes">
       <label for="barcode-yes">Yes</label>
     </div>
   </div>
   
   <div class="form-group" id="barcode-field" style="display:none;">
     <label>Barcode / SKU</label>
     <input type="text" name="barcode" class="form-control" 
            placeholder="Scan or enter barcode">
   </div>
   
   <script>
   // Show/hide barcode field based on toggle
   document.querySelectorAll('[name="has_barcode"]').forEach(radio => {
     radio.addEventListener('change', (e) => {
       document.getElementById('barcode-field').style.display = 
         e.target.value === 'yes' ? 'block' : 'none';
     });
   });
   </script>
   ```

2. **Phones Scan-In Template** (`templates/inventory/phones_scan_in.html`):
   - Lower priority (IMEI already serves as barcode)
   - Can add for accessories if needed

3. **Generic Scan-In Template** (`templates/inventory/scan_in.html`):
   - Add barcode toggle UI
   - Wire up show/hide logic
   - Ensure mobile-friendly

4. **Clothing Scan-In Template** (`templates/verticals/clothing/scan_in.html`):
   - Check if exists or uses generic
   - Add barcode workflow UI

**Tests Needed:**

Create `inventory/tests/test_barcode_workflow.py`:
```python
@pytest.mark.django_db
class TestBarcodeWorkflow:
    def test_pharmacy_has_barcode_yes_missing_barcode_returns_error(self, ...):
        """has_barcode=yes with missing barcode should return 200 with error"""
        # POST with has_barcode=yes but no barcode value
        # Assert response.status_code == 200
        # Assert error message in response
    
    def test_pharmacy_has_barcode_no_missing_barcode_succeeds(self, ...):
        """has_barcode=no with missing barcode should succeed"""
        # POST with has_barcode=no and no barcode
        # Assert success
    
    def test_pharmacy_has_barcode_yes_with_valid_barcode_stores_correctly(self, ...):
        """Barcode should be stored on product when provided"""
        # POST with has_barcode=yes and valid barcode
        # Assert product.barcode == expected_barcode
    
    def test_pharmacy_barcode_validation_rejects_invalid_format(self, ...):
        """Invalid barcode format should return error"""
        # POST with invalid barcode (special chars, too short, etc.)
        # Assert error message
```

**Estimated Time to Complete Task 2**: 4-6 hours
- Backend: 2-3 hours (3 more views to update)
- Templates: 1-2 hours (4 templates to update)
- Tests: 1 hour (8-10 test cases)

---

## TASK 3: Liquor Roles + Assignment + Reconciliation ⚠️ NOT STARTED

**Goal**: Implement role-based stock assignment and bill reconciliation for liquor vertical

### Complexity: VERY HIGH
**Estimated Time**: 12-16 hours

### Requirements Breakdown:

#### New Models Needed:

1. **LiquorStockAssignment** (`inventory/models_liquor.py`):
   ```python
   class LiquorStockAssignment(models.Model):
       """Track which stock is assigned to which agent"""
       business = models.ForeignKey(Business, on_delete=models.CASCADE)
       agent = models.ForeignKey(User, on_delete=models.CASCADE, 
                                 related_name='liquor_assignments')
       product = models.ForeignKey(MerchProduct, on_delete=models.CASCADE)
       quantity_assigned = models.IntegerField(default=0)
       quantity_sold = models.IntegerField(default=0)
       quantity_remaining = models.IntegerField(default=0)
       assigned_at = models.DateTimeField(auto_now_add=True)
       assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, 
                                       null=True, related_name='+')
       notes = models.TextField(blank=True)
       
       class Meta:
           unique_together = ['business', 'agent', 'product']
   ```

2. **LiquorSaleBill** (`inventory/models_liquor.py`):
   ```python
   class LiquorSaleBill(models.Model):
       """Track sales bills for agents (pending/cleared status)"""
       STATUS_PENDING = 'pending'
       STATUS_CLEARED = 'cleared'
       STATUS_DISPUTED = 'disputed'
       STATUS_CHOICES = [
           (STATUS_PENDING, 'Pending'),
           (STATUS_CLEARED, 'Cleared'),
           (STATUS_DISPUTED, 'Disputed'),
       ]
       
       business = models.ForeignKey(Business, on_delete=models.CASCADE)
       agent = models.ForeignKey(User, on_delete=models.CASCADE,
                                 related_name='liquor_bills')
       sale = models.ForeignKey('LiquorSale', on_delete=models.CASCADE)
       amount = models.DecimalField(max_digits=10, decimal_places=2)
       status = models.CharField(max_length=20, choices=STATUS_CHOICES,
                                 default=STATUS_PENDING)
       created_at = models.DateTimeField(auto_now_add=True)
       cleared_at = models.DateTimeField(null=True, blank=True)
       cleared_by = models.ForeignKey(User, on_delete=models.SET_NULL,
                                      null=True, related_name='+')
       notes = models.TextField(blank=True)
   ```

#### Roles Implementation:

1. **Bar Manager Role** (extend existing LIQUOR_BARMAN group):
   - Can assign stock to agents
   - Can reconcile bills
   - Sees all stock and sales
   - Manages the bar team

2. **Liquor Sales Agent Role** (new group: LIQUOR_AGENT):
   - Sees ONLY assigned stock
   - Records sales from assigned stock
   - Sees pending/cleared bills
   - Dashboard shows balanced/unbalanced state

#### Views Needed:

1. **Assignment UI** (`inventory/views_liquor_assignment.py`):
   - `liquor_assign_stock` - Form to assign stock to agents
   - `liquor_assignment_list` - View all assignments (Bar Manager only)
   - `liquor_agent_assigned_stock` - Agent sees their assigned stock

2. **Reconciliation UI** (`inventory/views_liquor_reconciliation.py`):
   - `liquor_reconcile_bills` - Bar Manager reconciles agent bills
   - `liquor_agent_bills` - Agent sees their pending/cleared bills

3. **Modified Sell Flow** (`inventory/verticals/liquor.py`):
   - Update existing sell view
   - If seller is agent: auto-assign sale to agent
   - If seller is Bar Manager: option to assign to specific agent
   - Create LiquorSaleBill record

4. **Agent Dashboard** (`inventory/views_liquor_agent.py`):
   - KPIs: Assigned stock, Sold units, Remaining units
   - Bills: Pending vs Cleared
   - Balanced state indicator
   - Sales history scoped to agent

#### Templates Needed:

1. `templates/liquor/assign_stock.html` - Assignment form
2. `templates/liquor/assignment_list.html` - All assignments
3. `templates/liquor/agent_assigned_stock.html` - Agent's stock view
4. `templates/liquor/reconcile_bills.html` - Reconciliation UI
5. `templates/liquor/agent_bills.html` - Agent's bills
6. `templates/liquor/agent_dashboard.html` - Agent KPI dashboard

#### URL Routes:

```python
# liquor/urls.py
urlpatterns = [
    # Assignment (Bar Manager only)
    path('assign-stock/', liquor_assign_stock, name='assign_stock'),
    path('assignments/', liquor_assignment_list, name='assignment_list'),
    
    # Reconciliation (Bar Manager only)
    path('reconcile-bills/', liquor_reconcile_bills, name='reconcile_bills'),
    
    # Agent views
    path('agent/stock/', liquor_agent_assigned_stock, name='agent_stock'),
    path('agent/bills/', liquor_agent_bills, name='agent_bills'),
    path('agent/dashboard/', liquor_agent_dashboard, name='agent_dashboard'),
]
```

#### Tests Needed:

- Agent cannot see unassigned stock
- Sales reduce assigned stock correctly
- Bills created with pending status
- Bar Manager can clear bills
- Agent dashboard shows balanced state
- Permission checks enforced

---

## TASK 4: Salary Wallet for Liquor Staff ⚠️ NOT STARTED

**Goal**: Add salary allocations for liquor staff (no commission wallet)

### Complexity: MEDIUM
**Estimated Time**: 4-6 hours

### Requirements:

#### New Model:

```python
# wallet/models.py
class CostAllocation(models.Model):
    """Salary allocations for staff"""
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    staff_user = models.ForeignKey(User, on_delete=models.CASCADE,
                                    related_name='salary_allocations')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    allocation_type = models.CharField(max_length=20, 
                                       choices=[('SALARY', 'Salary'),
                                               ('BONUS', 'Bonus')])
    month = models.DateField()  # First day of month
    allocated_by = models.ForeignKey(User, on_delete=models.SET_NULL,
                                     null=True, related_name='+')
    allocated_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
```

#### Views:

1. **Admin Cost Form** - Add "Assign Salary" option:
   - Select staff member
   - Enter amount
   - Select month
   - Save as CostAllocation + WalletTransaction

2. **Agent Wallet** - Show salary allocations:
   - List all salary allocations for agent
   - Filter by month
   - Show total for current month

#### Integration:

- Update `wallet/views.py::admin_cost_create`
- Update `wallet/views.py::agent_wallet`
- Add new template or extend existing

---

## TASK 5: Tests + Hardening ⚠️ NOT STARTED

**Goal**: Comprehensive testing and optimization

### Complexity: MEDIUM
**Estimated Time**: 6-8 hours

### Components:

1. **Barcode Workflow Tests** (from Task 2)
2. **Liquor Roles Tests** (from Task 3)
3. **Salary Allocation Tests** (from Task 4)
4. **Integration Tests**:
   - End-to-end flows
   - Cross-vertical consistency
   - Permission enforcement
5. **Static Files Validation**:
   - Run collectstatic
   - Check manifest
   - Verify no missing references
6. **Query Optimization**:
   - Add indexes on new foreign keys
   - Use select_related/prefetch_related
   - Avoid N+1 queries
7. **System Checks**:
   - Run `python manage.py check`
   - Fix any warnings
   - Ensure no DB access at import time

---

## Priority Recommendation

Given the scope and complexity:

### Immediate Priority (Next Session):
1. **Complete Task 2 (Barcode Workflow)** - 70% done, needs templates + tests
   - Low risk, high data integrity value
   - Affects all inventory verticals
   - Straightforward implementation

### Medium Priority:
2. **Task 4 (Salary Wallet)** - Smaller scope than Task 3
   - Can be done independently
   - Clearer requirements
   - Less risk of breaking existing flows

### Complex Priority (Requires Careful Planning):
3. **Task 3 (Liquor Roles)** - Most complex, requires:
   - New models + migrations
   - Extensive UI work
   - Integration with existing sell flow
   - Role/permission system updates
   - Comprehensive testing

### Final Priority:
4. **Task 5 (Tests + Hardening)** - After all features complete

---

## Total Estimated Time Remaining

- **Task 2 (Barcode)**: 4-6 hours (70% done)
- **Task 3 (Liquor Roles)**: 12-16 hours
- **Task 4 (Salary Wallet)**: 4-6 hours
- **Task 5 (Tests + Hardening)**: 6-8 hours

**Total**: 26-36 hours of focused development work

---

## Recommendation for Next Steps

1. **Continue with Task 2 (Barcode Workflow)**:
   - Update remaining backend views (generic scan-in, clothing, liquor)
   - Add template UI for all affected pages
   - Write comprehensive tests
   - **Complete in 1-2 sessions**

2. **Then Task 4 (Salary Wallet)**:
   - Create CostAllocation model + migration
   - Update admin cost form
   - Update agent wallet view
   - Add tests
   - **Complete in 1 session**

3. **Then Task 3 (Liquor Roles)**:
   - Requires dedicated focus
   - Plan architecture first
   - Implement models + migrations
   - Build UI layer by layer
   - Test thoroughly
   - **Complete in 2-3 sessions**

4. **Finally Task 5 (Hardening)**:
   - Run full test suite
   - Optimize queries
   - Validate static files
   - **Complete in 1 session**


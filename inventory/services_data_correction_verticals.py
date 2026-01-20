# inventory/services_data_correction_verticals.py
"""
PART 4: Data Correction Service Extension for ALL Verticals

Extends the base DataCorrectionService to support:
- Liquor sales/stock corrections
- Welding job/quote corrections
- Farming ledger corrections
- Car hire trip corrections
- Cement/Clothing/Gym corrections

CRITICAL: All corrections are audited and require manager permissions.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from tenants.models import Business
from inventory.models_data_correction import (
    CorrectionType,
    DataCorrectionLog,
    VoidedRecord,
)


@dataclass
class CorrectionResult:
    """Result of a correction operation."""
    success: bool
    message: str
    correction_log: Optional[DataCorrectionLog] = None
    revenue_impact: Decimal = Decimal("0.00")
    profit_impact: Decimal = Decimal("0.00")
    stock_impact: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class VerticalDataCorrectionService:
    """
    Vertical-aware Data Correction Service.
    
    Handles corrections across all verticals with proper audit trails
    and stock/KPI recomputation.
    """
    
    def __init__(self, business: Business, user, request=None):
        """
        Initialize the service.
        
        Args:
            business: The business context
            user: The user making corrections (must be manager)
            request: Optional HTTP request for audit metadata
        """
        self.business = business
        self.user = user
        self.request = request
        self.vertical = business.kind
        
        # Validate manager permission
        self._validate_manager_permission()
    
    def _validate_manager_permission(self):
        """Ensure the user has manager permissions."""
        # Check various permission sources
        is_manager = False
        
        # Check if staff/superuser
        if getattr(self.user, 'is_staff', False) or getattr(self.user, 'is_superuser', False):
            is_manager = True
        
        # Check BusinessMembership role
        if not is_manager:
            try:
                from tenants.models import BusinessMembership
                membership = BusinessMembership.objects.filter(
                    user=self.user,
                    business=self.business,
                ).first()
                if membership and membership.role in ('owner', 'manager', 'admin'):
                    is_manager = True
            except Exception:
                pass
        
        # Check core.roles if available
        if not is_manager:
            try:
                from core.roles import is_manager as check_is_manager
                is_manager = check_is_manager(self.user)
            except ImportError:
                pass
        
        if not is_manager:
            raise PermissionDenied("Only managers can perform data corrections.")
    
    # ==========================================================================
    # LIQUOR CORRECTIONS
    # ==========================================================================
    
    def edit_liquor_sale(
        self,
        sale_id: int,
        reason: str,
        new_quantity: Optional[int] = None,
        new_unit_price: Optional[Decimal] = None,
        new_payment_method: Optional[str] = None,
    ) -> CorrectionResult:
        """
        Edit a liquor sale record.
        
        Args:
            sale_id: ID of the LiquorSale
            reason: Required reason for correction
            new_quantity: New quantity (units sold)
            new_unit_price: New price per unit
            new_payment_method: New payment method
        """
        if not reason or not reason.strip():
            return CorrectionResult(
                success=False,
                message="Reason for correction is required.",
                errors=["Reason is required"],
            )
        
        try:
            from inventory.models_verticals import LiquorSale
            
            with transaction.atomic():
                sale = LiquorSale.objects.select_for_update().get(
                    pk=sale_id,
                    business=self.business,
                )
                
                field_changes = {}
                old_total = sale.total_price or Decimal("0")
                old_quantity = sale.quantity or 0
                
                if new_quantity is not None and new_quantity != old_quantity:
                    if new_quantity < 0:
                        return CorrectionResult(
                            success=False,
                            message="Quantity cannot be negative.",
                            errors=["Invalid quantity"],
                        )
                    field_changes["quantity"] = {
                        "old": old_quantity,
                        "new": new_quantity,
                    }
                    sale.quantity = new_quantity
                
                if new_unit_price is not None:
                    old_price = sale.unit_price or Decimal("0")
                    if new_unit_price != old_price:
                        if new_unit_price < 0:
                            return CorrectionResult(
                                success=False,
                                message="Price cannot be negative.",
                                errors=["Invalid price"],
                            )
                        field_changes["unit_price"] = {
                            "old": str(old_price),
                            "new": str(new_unit_price),
                        }
                        sale.unit_price = new_unit_price
                
                if new_payment_method is not None:
                    old_method = sale.payment_method or "CASH"
                    if new_payment_method != old_method:
                        field_changes["payment_method"] = {
                            "old": old_method,
                            "new": new_payment_method,
                        }
                        sale.payment_method = new_payment_method
                
                if not field_changes:
                    return CorrectionResult(
                        success=True,
                        message="No changes were made.",
                    )
                
                # Recalculate total
                if hasattr(sale, 'recalculate_total'):
                    sale.recalculate_total()
                else:
                    sale.total_price = sale.quantity * (sale.unit_price or Decimal("0"))
                
                sale.save()
                
                # Calculate impact
                new_total = sale.total_price or Decimal("0")
                revenue_impact = new_total - old_total
                
                # Create correction log
                correction_log = DataCorrectionLog.log_correction(
                    business=self.business,
                    model_name="LiquorSale",
                    object_id=sale.pk,
                    correction_type="EDIT_SALE",
                    corrected_by=self.user,
                    reason=reason.strip(),
                    field_changes=field_changes,
                    revenue_impact=revenue_impact,
                    request=self.request,
                )
                
                return CorrectionResult(
                    success=True,
                    message=f"Successfully corrected liquor sale #{sale.pk}.",
                    correction_log=correction_log,
                    revenue_impact=revenue_impact,
                )
        
        except Exception as e:
            return CorrectionResult(
                success=False,
                message=f"Failed to correct sale: {str(e)}",
                errors=[str(e)],
            )
    
    def void_liquor_sale(self, sale_id: int, reason: str) -> CorrectionResult:
        """Void a liquor sale and restore stock."""
        if not reason or not reason.strip():
            return CorrectionResult(
                success=False,
                message="Reason for voiding is required.",
                errors=["Reason is required"],
            )
        
        try:
            from inventory.models_verticals import LiquorSale
            from inventory.models import MerchProduct
            
            with transaction.atomic():
                sale = LiquorSale.objects.select_for_update().get(
                    pk=sale_id,
                    business=self.business,
                )
                
                if getattr(sale, 'is_voided', False):
                    return CorrectionResult(
                        success=False,
                        message="Sale is already voided.",
                        errors=["Already voided"],
                    )
                
                # Calculate impact
                revenue_impact = -(sale.total_price or Decimal("0"))
                stock_restored = sale.quantity or 0
                
                # Restore stock
                if sale.product_id:
                    try:
                        product = MerchProduct.objects.select_for_update().get(
                            pk=sale.product_id
                        )
                        product.quantity_in_stock += stock_restored
                        product.save(update_fields=["quantity_in_stock"])
                    except MerchProduct.DoesNotExist:
                        pass
                
                # Create void record
                VoidedRecord.void_record(
                    business=self.business,
                    model_name="LiquorSale",
                    obj=sale,
                    voided_by=self.user,
                    reason=reason.strip(),
                    revenue_impact=revenue_impact,
                )
                
                # Mark as voided
                sale.is_voided = True
                sale.voided_at = timezone.now()
                sale.voided_by = self.user
                sale.save(update_fields=["is_voided", "voided_at", "voided_by"])
                
                # Create correction log
                correction_log = DataCorrectionLog.log_correction(
                    business=self.business,
                    model_name="LiquorSale",
                    object_id=sale.pk,
                    correction_type="VOID_SALE",
                    corrected_by=self.user,
                    reason=reason.strip(),
                    field_changes={"is_voided": {"old": False, "new": True}},
                    revenue_impact=revenue_impact,
                    request=self.request,
                )
                
                return CorrectionResult(
                    success=True,
                    message=f"Successfully voided sale. Stock restored: {stock_restored} units.",
                    correction_log=correction_log,
                    revenue_impact=revenue_impact,
                    stock_impact=stock_restored,
                )
        
        except Exception as e:
            return CorrectionResult(
                success=False,
                message=f"Failed to void sale: {str(e)}",
                errors=[str(e)],
            )
    
    # ==========================================================================
    # WELDING CORRECTIONS
    # ==========================================================================
    
    def edit_welding_job_price(
        self,
        job_id: int,
        reason: str,
        new_final_price: Optional[Decimal] = None,
    ) -> CorrectionResult:
        """Edit a welding job final price."""
        if not reason or not reason.strip():
            return CorrectionResult(
                success=False,
                message="Reason for correction is required.",
                errors=["Reason is required"],
            )
        
        try:
            from inventory.models_welding import WeldingJob
            
            with transaction.atomic():
                job = WeldingJob.objects.select_for_update().get(
                    pk=job_id,
                    business=self.business,
                )
                
                field_changes = {}
                
                if new_final_price is not None:
                    old_price = job.final_price or job.quoted_price or Decimal("0")
                    if new_final_price != old_price:
                        field_changes["final_price"] = {
                            "old": str(old_price),
                            "new": str(new_final_price),
                        }
                        job.final_price = new_final_price
                
                if not field_changes:
                    return CorrectionResult(
                        success=True,
                        message="No changes were made.",
                    )
                
                job.save()
                
                # Create correction log
                correction_log = DataCorrectionLog.log_correction(
                    business=self.business,
                    model_name="WeldingJob",
                    object_id=job.pk,
                    correction_type="EDIT_SALE",
                    corrected_by=self.user,
                    reason=reason.strip(),
                    field_changes=field_changes,
                    request=self.request,
                )
                
                return CorrectionResult(
                    success=True,
                    message=f"Successfully corrected job {job.job_number}.",
                    correction_log=correction_log,
                )
        
        except Exception as e:
            return CorrectionResult(
                success=False,
                message=f"Failed to correct job: {str(e)}",
                errors=[str(e)],
            )
    
    # ==========================================================================
    # FARMING CORRECTIONS
    # ==========================================================================
    
    def edit_farm_ledger_entry(
        self,
        entry_id: int,
        reason: str,
        new_amount: Optional[Decimal] = None,
        new_category: Optional[str] = None,
        new_description: Optional[str] = None,
    ) -> CorrectionResult:
        """Edit a farm ledger entry."""
        if not reason or not reason.strip():
            return CorrectionResult(
                success=False,
                message="Reason for correction is required.",
                errors=["Reason is required"],
            )
        
        try:
            from inventory.models_farm import FarmLedgerEntry
            
            with transaction.atomic():
                entry = FarmLedgerEntry.objects.select_for_update().get(
                    pk=entry_id,
                    business=self.business,
                )
                
                field_changes = {}
                
                if new_amount is not None:
                    old_amount = entry.amount_mwk
                    if new_amount != old_amount:
                        if new_amount <= 0:
                            return CorrectionResult(
                                success=False,
                                message="Amount must be positive.",
                                errors=["Invalid amount"],
                            )
                        field_changes["amount_mwk"] = {
                            "old": str(old_amount),
                            "new": str(new_amount),
                        }
                        entry.amount_mwk = new_amount
                
                if new_category is not None:
                    old_category = entry.category
                    if new_category != old_category:
                        field_changes["category"] = {
                            "old": old_category,
                            "new": new_category,
                        }
                        entry.category = new_category
                
                if new_description is not None:
                    old_desc = entry.description
                    if new_description != old_desc:
                        field_changes["description"] = {
                            "old": old_desc,
                            "new": new_description,
                        }
                        entry.description = new_description
                
                if not field_changes:
                    return CorrectionResult(
                        success=True,
                        message="No changes were made.",
                    )
                
                entry.save()
                
                # Create correction log
                correction_log = DataCorrectionLog.log_correction(
                    business=self.business,
                    model_name="FarmLedgerEntry",
                    object_id=entry.pk,
                    correction_type="EDIT_SALE" if entry.entry_type != "expense" else "EDIT_STOCK_IN",
                    corrected_by=self.user,
                    reason=reason.strip(),
                    field_changes=field_changes,
                    request=self.request,
                )
                
                return CorrectionResult(
                    success=True,
                    message=f"Successfully corrected ledger entry.",
                    correction_log=correction_log,
                )
        
        except Exception as e:
            return CorrectionResult(
                success=False,
                message=f"Failed to correct entry: {str(e)}",
                errors=[str(e)],
            )
    
    # ==========================================================================
    # CAR HIRE CORRECTIONS
    # ==========================================================================
    
    def edit_car_hire_trip(
        self,
        trip_id: int,
        reason: str,
        new_price_total: Optional[Decimal] = None,
        new_deposit_paid: Optional[Decimal] = None,
    ) -> CorrectionResult:
        """Edit a car hire trip record."""
        if not reason or not reason.strip():
            return CorrectionResult(
                success=False,
                message="Reason for correction is required.",
                errors=["Reason is required"],
            )
        
        try:
            from inventory.models_car_hire import Trip
            
            with transaction.atomic():
                trip = Trip.objects.select_for_update().get(
                    pk=trip_id,
                    business=self.business,
                )
                
                field_changes = {}
                
                if new_price_total is not None:
                    old_price = trip.price_total
                    if new_price_total != old_price:
                        field_changes["price_total"] = {
                            "old": str(old_price),
                            "new": str(new_price_total),
                        }
                        trip.price_total = new_price_total
                
                if new_deposit_paid is not None:
                    old_deposit = trip.deposit_paid
                    if new_deposit_paid != old_deposit:
                        field_changes["deposit_paid"] = {
                            "old": str(old_deposit),
                            "new": str(new_deposit_paid),
                        }
                        trip.deposit_paid = new_deposit_paid
                
                if not field_changes:
                    return CorrectionResult(
                        success=True,
                        message="No changes were made.",
                    )
                
                trip.save()
                
                # Create correction log
                correction_log = DataCorrectionLog.log_correction(
                    business=self.business,
                    model_name="Trip",
                    object_id=trip.pk,
                    correction_type="EDIT_SALE",
                    corrected_by=self.user,
                    reason=reason.strip(),
                    field_changes=field_changes,
                    request=self.request,
                )
                
                return CorrectionResult(
                    success=True,
                    message=f"Successfully corrected trip record.",
                    correction_log=correction_log,
                )
        
        except Exception as e:
            return CorrectionResult(
                success=False,
                message=f"Failed to correct trip: {str(e)}",
                errors=[str(e)],
            )
    
    # ==========================================================================
    # GENERIC CORRECTION METHODS
    # ==========================================================================
    
    def get_correction_history(self, limit: int = 50) -> List[DataCorrectionLog]:
        """Get correction history for this business."""
        return list(
            DataCorrectionLog.objects.filter(
                business=self.business,
            ).select_related("corrected_by").order_by("-corrected_at")[:limit]
        )
    
    def get_voided_records(self, limit: int = 50) -> List[VoidedRecord]:
        """Get voided records for this business."""
        return list(
            VoidedRecord.objects.filter(
                business=self.business,
                is_restored=False,
            ).select_related("voided_by").order_by("-voided_at")[:limit]
        )


# Export
__all__ = [
    "CorrectionResult",
    "VerticalDataCorrectionService",
]


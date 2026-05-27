# inventory/services_data_correction.py
"""
Data Correction Service Layer

Handles all business logic for data corrections including:
- Editing sold items (phones, accessories)
- Editing stock-in records
- Voiding records safely
- Recomputing affected totals

CRITICAL: All corrections are audited and require manager permissions.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone

from tenants.models import Business
from inventory.models import InventoryItem, Product, Location, AuditLog
from inventory.models_accessories import AccessoryProduct, AccessoryStock, AccessoryStockLog
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
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class DataCorrectionService:
    """
    Service class for handling data corrections safely.
    
    All methods require a manager user and create audit logs.
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
        
        # Validate manager permission
        self._validate_manager_permission()
    
    def _validate_manager_permission(self):
        """Ensure the user has manager permissions."""
        from core.roles import is_manager
        
        if not is_manager(self.user):
            raise PermissionDenied("Only managers can perform data corrections.")
    
    # ==========================================================================
    # PHONE SALE CORRECTIONS
    # ==========================================================================
    
    def edit_phone_sale(
        self,
        item_id: int,
        reason: str,
        new_selling_price: Optional[Decimal] = None,
        new_order_price: Optional[Decimal] = None,
        new_imei: Optional[str] = None,
        new_payment_method: Optional[str] = None,
    ) -> CorrectionResult:
        """
        Edit a phone sale or stock item (including sold items).
        
        CRITICAL: This bypasses the normal restriction on editing sold items.
        All changes are fully audited.
        
        Args:
            item_id: ID of the InventoryItem
            reason: Required reason for the correction
            new_selling_price: New selling price (if changing)
            new_order_price: New cost/order price (if changing)
            new_imei: New IMEI (if changing, must be unique)
            new_payment_method: New payment method (if changing)
        
        Returns:
            CorrectionResult with success status and impact
        """
        if not reason or not reason.strip():
            return CorrectionResult(
                success=False,
                message="Reason for correction is required.",
                errors=["Reason is required"],
            )
        
        try:
            with transaction.atomic():
                # Get the item with lock
                item = InventoryItem.objects.select_for_update().get(
                    pk=item_id,
                    business=self.business,
                )
                
                old_values = {}
                new_values = {}
                field_changes = {}
                
                # Track old financial values for impact calculation
                old_selling_price = item.selling_price or Decimal("0.00")
                old_order_price = item.order_price or Decimal("0.00")
                old_profit = old_selling_price - old_order_price
                
                # Update selling price
                if new_selling_price is not None:
                    if new_selling_price <= 0:
                        return CorrectionResult(
                            success=False,
                            message="Selling price must be greater than 0.",
                            errors=["Invalid selling price"],
                        )
                    
                    if new_selling_price != old_selling_price:
                        field_changes["selling_price"] = {
                            "old": str(old_selling_price),
                            "new": str(new_selling_price),
                        }
                        item.selling_price = new_selling_price
                
                # Update order price
                if new_order_price is not None:
                    if new_order_price < 0:
                        return CorrectionResult(
                            success=False,
                            message="Order price must be 0 or greater.",
                            errors=["Invalid order price"],
                        )
                    
                    if new_order_price != old_order_price:
                        field_changes["order_price"] = {
                            "old": str(old_order_price),
                            "new": str(new_order_price),
                        }
                        item.order_price = new_order_price
                
                # Update IMEI
                if new_imei is not None:
                    # Normalize IMEI
                    from inventory.models import normalize_imei
                    new_imei_clean = normalize_imei(new_imei)
                    old_imei = item.imei or ""
                    
                    if new_imei_clean != old_imei:
                        # Validate IMEI format
                        if len(new_imei_clean) != 15 or not new_imei_clean.isdigit():
                            return CorrectionResult(
                                success=False,
                                message="IMEI must be exactly 15 digits.",
                                errors=["Invalid IMEI format"],
                            )
                        
                        # Check for uniqueness
                        existing = InventoryItem.objects.filter(
                            imei=new_imei_clean
                        ).exclude(pk=item.pk).exists()
                        
                        if existing:
                            return CorrectionResult(
                                success=False,
                                message=f"IMEI {new_imei_clean} already exists in the system.",
                                errors=["IMEI already exists"],
                            )
                        
                        field_changes["imei"] = {
                            "old": old_imei,
                            "new": new_imei_clean,
                        }
                        item.imei = new_imei_clean
                
                # Update payment method
                if new_payment_method is not None:
                    old_payment_method = item.payment_method or "CASH"
                    if new_payment_method != old_payment_method:
                        valid_methods = ["CASH", "BANK", "MOBILE_MONEY"]
                        if new_payment_method not in valid_methods:
                            return CorrectionResult(
                                success=False,
                                message=f"Invalid payment method. Must be one of: {', '.join(valid_methods)}",
                                errors=["Invalid payment method"],
                            )
                        
                        field_changes["payment_method"] = {
                            "old": old_payment_method,
                            "new": new_payment_method,
                        }
                        item.payment_method = new_payment_method
                
                # If no changes, return early
                if not field_changes:
                    return CorrectionResult(
                        success=True,
                        message="No changes were made.",
                    )
                
                # Calculate impact
                new_selling = item.selling_price or Decimal("0.00")
                new_order = item.order_price or Decimal("0.00")
                new_profit = new_selling - new_order
                
                revenue_impact = new_selling - old_selling_price
                profit_impact = new_profit - old_profit
                
                # Save the item (bypass the sold item check by using update_fields)
                item.updated_at = timezone.now()
                item.save(update_fields=[
                    "selling_price",
                    "order_price",
                    "imei",
                    "payment_method",
                    "updated_at",
                ])
                
                # Create correction log
                correction_type = (
                    CorrectionType.EDIT_SALE
                    if item.status == "SOLD"
                    else CorrectionType.EDIT_STOCK_IN
                )
                
                correction_log = DataCorrectionLog.log_correction(
                    business=self.business,
                    model_name="InventoryItem",
                    object_id=item.pk,
                    correction_type=correction_type,
                    corrected_by=self.user,
                    reason=reason.strip(),
                    field_changes=field_changes,
                    revenue_impact=revenue_impact,
                    profit_impact=profit_impact,
                    request=self.request,
                )
                
                # Also create legacy audit log for compatibility
                AuditLog.objects.create(
                    action="EDIT",
                    by_user=self.user,
                    item=item,
                    business=self.business,
                    details=f"Data Correction: {json.dumps(field_changes)}; Reason: {reason}",
                )
                
                return CorrectionResult(
                    success=True,
                    message=f"Successfully corrected {item}.",
                    correction_log=correction_log,
                    revenue_impact=revenue_impact,
                    profit_impact=profit_impact,
                )
        
        except InventoryItem.DoesNotExist:
            return CorrectionResult(
                success=False,
                message="Item not found or doesn't belong to your business.",
                errors=["Item not found"],
            )
        except Exception as e:
            return CorrectionResult(
                success=False,
                message=f"Failed to apply correction: {str(e)}",
                errors=[str(e)],
            )
    
    def void_phone_item(self, item_id: int, reason: str) -> CorrectionResult:
        """
        Void (soft-delete) a phone inventory item or sale.
        
        Effects:
        - If SOLD: marks voided, removes from revenue/profit calculations
        - If IN_STOCK: marks voided, removes from stock counts
        
        Args:
            item_id: ID of the InventoryItem
            reason: Required reason for voiding
        
        Returns:
            CorrectionResult with impact details
        """
        if not reason or not reason.strip():
            return CorrectionResult(
                success=False,
                message="Reason for voiding is required.",
                errors=["Reason is required"],
            )
        
        try:
            with transaction.atomic():
                # Get item with lock
                item = InventoryItem.objects.select_for_update().get(
                    pk=item_id,
                    business=self.business,
                    is_active=True,  # Only void active items
                )
                
                # Calculate impact
                selling_price = item.selling_price or Decimal("0.00")
                order_price = item.order_price or Decimal("0.00")
                
                if item.status == "SOLD":
                    # Voiding a sale removes its revenue and profit
                    revenue_impact = -selling_price
                    profit_impact = -(selling_price - order_price)
                    correction_type = CorrectionType.VOID_SALE
                else:
                    # Voiding stock-in removes stock value
                    revenue_impact = Decimal("0.00")
                    profit_impact = Decimal("0.00")
                    correction_type = CorrectionType.VOID_STOCK_IN
                
                # Create void record with snapshot
                void_record = VoidedRecord.void_record(
                    business=self.business,
                    model_name="InventoryItem",
                    obj=item,
                    voided_by=self.user,
                    reason=reason.strip(),
                    revenue_impact=revenue_impact,
                    profit_impact=profit_impact,
                )
                
                # Mark item as inactive (soft delete)
                item.is_active = False
                item.archived_at = timezone.now()
                item.archived_by = self.user
                item.save(update_fields=["is_active", "archived_at", "archived_by", "updated_at"])
                
                # Create correction log
                correction_log = DataCorrectionLog.log_correction(
                    business=self.business,
                    model_name="InventoryItem",
                    object_id=item.pk,
                    correction_type=correction_type,
                    corrected_by=self.user,
                    reason=reason.strip(),
                    field_changes={"is_active": {"old": True, "new": False}},
                    revenue_impact=revenue_impact,
                    profit_impact=profit_impact,
                    request=self.request,
                )
                
                # Legacy audit log
                AuditLog.objects.create(
                    action="DELETE",
                    by_user=self.user,
                    item=item,
                    business=self.business,
                    details=f"VOIDED via Data Correction; Reason: {reason}",
                )
                
                return CorrectionResult(
                    success=True,
                    message=f"Successfully voided {item}.",
                    correction_log=correction_log,
                    revenue_impact=revenue_impact,
                    profit_impact=profit_impact,
                )
        
        except InventoryItem.DoesNotExist:
            return CorrectionResult(
                success=False,
                message="Item not found, doesn't belong to your business, or already voided.",
                errors=["Item not found or already voided"],
            )
        except Exception as e:
            return CorrectionResult(
                success=False,
                message=f"Failed to void item: {str(e)}",
                errors=[str(e)],
            )
    
    # ==========================================================================
    # ACCESSORY CORRECTIONS
    # ==========================================================================
    
    def edit_accessory_stock(
        self,
        stock_id: int,
        reason: str,
        new_qty: Optional[int] = None,
        new_avg_cost: Optional[Decimal] = None,
    ) -> CorrectionResult:
        """
        Edit accessory stock record.
        
        Args:
            stock_id: ID of the AccessoryStock
            reason: Required reason
            new_qty: New quantity (must be >= 0)
            new_avg_cost: New average cost
        
        Returns:
            CorrectionResult
        """
        if not reason or not reason.strip():
            return CorrectionResult(
                success=False,
                message="Reason for correction is required.",
                errors=["Reason is required"],
            )
        
        try:
            with transaction.atomic():
                stock = AccessoryStock.objects.select_for_update().get(
                    pk=stock_id,
                    business=self.business,
                )
                
                field_changes = {}
                old_qty = stock.qty_on_hand
                old_cost = stock.avg_cost
                
                if new_qty is not None:
                    if new_qty < 0:
                        return CorrectionResult(
                            success=False,
                            message="Quantity cannot be negative.",
                            errors=["Invalid quantity"],
                        )
                    
                    if new_qty != old_qty:
                        field_changes["qty_on_hand"] = {
                            "old": old_qty,
                            "new": new_qty,
                        }
                        stock.qty_on_hand = new_qty
                
                if new_avg_cost is not None:
                    if new_avg_cost < 0:
                        return CorrectionResult(
                            success=False,
                            message="Average cost cannot be negative.",
                            errors=["Invalid cost"],
                        )
                    
                    if new_avg_cost != old_cost:
                        field_changes["avg_cost"] = {
                            "old": str(old_cost),
                            "new": str(new_avg_cost),
                        }
                        stock.avg_cost = new_avg_cost
                
                if not field_changes:
                    return CorrectionResult(
                        success=True,
                        message="No changes were made.",
                    )
                
                stock.save(update_fields=["qty_on_hand", "avg_cost", "updated_at"])
                
                # Create correction log
                correction_log = DataCorrectionLog.log_correction(
                    business=self.business,
                    model_name="AccessoryStock",
                    object_id=stock.pk,
                    correction_type=CorrectionType.EDIT_ACCESSORY,
                    corrected_by=self.user,
                    reason=reason.strip(),
                    field_changes=field_changes,
                    request=self.request,
                )
                
                # Create accessory stock log for audit
                AccessoryStockLog.objects.create(
                    business=self.business,
                    product=stock.product,
                    location=stock.location,
                    action="ADJUSTMENT",
                    quantity=new_qty - old_qty if new_qty is not None else 0,
                    unit_cost=new_avg_cost if new_avg_cost is not None else old_cost,
                    by_user=self.user,
                    notes=f"Data Correction: {reason}",
                )
                
                return CorrectionResult(
                    success=True,
                    message=f"Successfully corrected accessory stock for {stock.product.name}.",
                    correction_log=correction_log,
                )
        
        except AccessoryStock.DoesNotExist:
            return CorrectionResult(
                success=False,
                message="Accessory stock not found.",
                errors=["Stock not found"],
            )
        except Exception as e:
            return CorrectionResult(
                success=False,
                message=f"Failed to apply correction: {str(e)}",
                errors=[str(e)],
            )
    
    def edit_accessory_product(
        self,
        product_id: int,
        reason: str,
        new_selling_price: Optional[Decimal] = None,
        new_order_price: Optional[Decimal] = None,
        new_name: Optional[str] = None,
        new_sku: Optional[str] = None,
    ) -> CorrectionResult:
        """
        Edit accessory product details.
        
        Args:
            product_id: ID of the AccessoryProduct
            reason: Required reason
            new_selling_price: New default selling price
            new_order_price: New default order price
            new_name: New product name (must be unique per business)
            new_sku: New SKU (must be unique per business)
        
        Returns:
            CorrectionResult
        """
        if not reason or not reason.strip():
            return CorrectionResult(
                success=False,
                message="Reason for correction is required.",
                errors=["Reason is required"],
            )
        
        try:
            with transaction.atomic():
                product = AccessoryProduct.objects.select_for_update().get(
                    pk=product_id,
                    business=self.business,
                    is_active=True,
                )
                
                field_changes = {}
                
                if new_selling_price is not None:
                    if new_selling_price <= 0:
                        return CorrectionResult(
                            success=False,
                            message="Selling price must be greater than 0.",
                            errors=["Invalid selling price"],
                        )
                    
                    old_price = product.default_selling_price
                    if new_selling_price != old_price:
                        field_changes["default_selling_price"] = {
                            "old": str(old_price),
                            "new": str(new_selling_price),
                        }
                        product.default_selling_price = new_selling_price
                
                if new_order_price is not None:
                    if new_order_price < 0:
                        return CorrectionResult(
                            success=False,
                            message="Order price must be 0 or greater.",
                            errors=["Invalid order price"],
                        )
                    
                    old_price = product.default_order_price
                    if new_order_price != old_price:
                        field_changes["default_order_price"] = {
                            "old": str(old_price),
                            "new": str(new_order_price),
                        }
                        product.default_order_price = new_order_price
                
                if new_name is not None:
                    new_name = new_name.strip()
                    if not new_name:
                        return CorrectionResult(
                            success=False,
                            message="Product name cannot be empty.",
                            errors=["Invalid name"],
                        )
                    
                    old_name = product.name
                    if new_name != old_name:
                        # Check uniqueness
                        existing = AccessoryProduct.objects.filter(
                            business=self.business,
                            name=new_name,
                        ).exclude(pk=product.pk).exists()
                        
                        if existing:
                            return CorrectionResult(
                                success=False,
                                message=f"Product name '{new_name}' already exists.",
                                errors=["Name already exists"],
                            )
                        
                        field_changes["name"] = {
                            "old": old_name,
                            "new": new_name,
                        }
                        product.name = new_name
                
                if new_sku is not None:
                    new_sku = new_sku.strip()
                    old_sku = product.sku
                    if new_sku != old_sku:
                        # Check uniqueness
                        existing = AccessoryProduct.objects.filter(
                            business=self.business,
                            sku=new_sku,
                        ).exclude(pk=product.pk).exists()
                        
                        if existing:
                            return CorrectionResult(
                                success=False,
                                message=f"SKU '{new_sku}' already exists.",
                                errors=["SKU already exists"],
                            )
                        
                        field_changes["sku"] = {
                            "old": old_sku,
                            "new": new_sku,
                        }
                        product.sku = new_sku
                
                if not field_changes:
                    return CorrectionResult(
                        success=True,
                        message="No changes were made.",
                    )
                
                product.save()
                
                correction_log = DataCorrectionLog.log_correction(
                    business=self.business,
                    model_name="AccessoryProduct",
                    object_id=product.pk,
                    correction_type=CorrectionType.EDIT_ACCESSORY,
                    corrected_by=self.user,
                    reason=reason.strip(),
                    field_changes=field_changes,
                    request=self.request,
                )
                
                return CorrectionResult(
                    success=True,
                    message=f"Successfully corrected {product.name}.",
                    correction_log=correction_log,
                )
        
        except AccessoryProduct.DoesNotExist:
            return CorrectionResult(
                success=False,
                message="Accessory product not found.",
                errors=["Product not found"],
            )
        except Exception as e:
            return CorrectionResult(
                success=False,
                message=f"Failed to apply correction: {str(e)}",
                errors=[str(e)],
            )
    
    # ==========================================================================
    # QUERY METHODS
    # ==========================================================================
    
    def get_correctable_items(
        self,
        search: Optional[str] = None,
        filter_type: str = "all",
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Get items that can be corrected with search and filtering.
        
        Args:
            search: Search query (IMEI, SKU, product name, etc.)
            filter_type: "all", "sales", "stock_in", "accessories", "voided"
            limit: Max items to return
            offset: Pagination offset
        
        Returns:
            Dict with items, total_count, and filters
        """
        results = {
            "phones": [],
            "accessories": [],
            "voided": [],
            "total_count": 0,
        }
        
        # Build phone items queryset
        if filter_type in ("all", "sales", "stock_in"):
            phone_qs = InventoryItem.objects.filter(
                business=self.business,
                is_active=True,
            ).select_related("product", "current_location", "assigned_agent", "sold_by")
            
            if filter_type == "sales":
                phone_qs = phone_qs.filter(status="SOLD")
            elif filter_type == "stock_in":
                phone_qs = phone_qs.filter(status="IN_STOCK")
            
            if search:
                phone_qs = phone_qs.filter(
                    Q(imei__icontains=search) |
                    Q(product__brand__icontains=search) |
                    Q(product__model__icontains=search) |
                    Q(product__code__icontains=search)
                )
            
            phone_qs = phone_qs.order_by("-updated_at")
            
            # Count before pagination
            phone_count = phone_qs.count()
            
            # Apply pagination
            phone_items = list(phone_qs[offset:offset + limit])
            
            results["phones"] = [
                {
                    "id": item.pk,
                    "type": "phone",
                    "date": item.sold_at or item.received_at,
                    "imei": item.imei,
                    "product_name": str(item.product) if item.product else "Unknown",
                    "brand": item.product.brand if item.product else "",
                    "model": item.product.model if item.product else "",
                    "order_price": item.order_price or Decimal("0.00"),
                    "selling_price": item.selling_price or Decimal("0.00"),
                    "profit": (item.selling_price or Decimal("0.00")) - (item.order_price or Decimal("0.00")),
                    "status": item.status,
                    "payment_method": item.payment_method,
                    "location": item.current_location.name if item.current_location else "",
                }
                for item in phone_items
            ]
            results["total_count"] += phone_count
        
        # Build accessories queryset
        if filter_type in ("all", "accessories"):
            acc_qs = AccessoryStock.objects.filter(
                business=self.business,
            ).select_related("product", "location")
            
            if search:
                acc_qs = acc_qs.filter(
                    Q(product__name__icontains=search) |
                    Q(product__sku__icontains=search) |
                    Q(product__barcode__icontains=search)
                )
            
            acc_qs = acc_qs.order_by("-updated_at")
            acc_count = acc_qs.count()
            acc_items = list(acc_qs[offset:offset + limit])
            
            results["accessories"] = [
                {
                    "id": stock.pk,
                    "type": "accessory",
                    "product_id": stock.product.pk,
                    "product_name": stock.product.name,
                    "category": stock.product.get_category_display(),
                    "sku": stock.product.sku,
                    "qty_on_hand": stock.qty_on_hand,
                    "avg_cost": stock.avg_cost,
                    "stock_value": stock.stock_value,
                    "selling_price": stock.product.default_selling_price,
                    "location": stock.location.name if stock.location else "",
                }
                for stock in acc_items
            ]
            results["total_count"] += acc_count
        
        # Build voided records queryset
        if filter_type in ("all", "voided"):
            void_qs = VoidedRecord.objects.filter(
                business=self.business,
                is_restored=False,
            ).select_related("voided_by")
            
            if search:
                void_qs = void_qs.filter(
                    Q(record_snapshot__icontains=search)
                )
            
            void_qs = void_qs.order_by("-voided_at")
            void_count = void_qs.count()
            void_items = list(void_qs[offset:offset + limit])
            
            results["voided"] = [
                {
                    "id": void.pk,
                    "type": "voided",
                    "model_name": void.model_name,
                    "object_id": void.object_id,
                    "voided_at": void.voided_at,
                    "voided_by": void.voided_by.get_full_name() or void.voided_by.username,
                    "reason": void.reason,
                    "revenue_impact": void.revenue_impact,
                    "profit_impact": void.profit_impact,
                    "snapshot": void.record_snapshot,
                }
                for void in void_items
            ]
            results["total_count"] += void_count
        
        return results
    
    def get_correction_history(
        self,
        model_name: Optional[str] = None,
        object_id: Optional[int] = None,
        limit: int = 50,
    ) -> List[DataCorrectionLog]:
        """
        Get correction history for audit display.
        
        Args:
            model_name: Filter by model name
            object_id: Filter by object ID
            limit: Max records to return
        
        Returns:
            List of DataCorrectionLog entries
        """
        qs = DataCorrectionLog.objects.filter(
            business=self.business,
        ).select_related("corrected_by")
        
        if model_name:
            qs = qs.filter(model_name=model_name)
        
        if object_id:
            qs = qs.filter(object_id=object_id)
        
        return list(qs[:limit])


# Export
__all__ = [
    "CorrectionResult",
    "DataCorrectionService",
]

